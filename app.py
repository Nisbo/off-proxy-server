"""Read-only OFF product API; full records, atomic snapshots, replayable deltas."""
import copy
import datetime as dt
import email.utils
import gzip
import hashlib
import hmac
import json
import logging
import math
import os
import re
import signal
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bson import json_util
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

VERSION = "0.1.3"
PROJECTS = {
    "food": "openfoodfacts",
    "beauty": "openbeautyfacts",
    "petfood": "openpetfoodfacts",
    "product": "openproductsfacts",
}
ORDER = ("beauty", "product", "petfood", "food")
MAX_LINE = 32 * 1024 * 1024
LOG = logging.getLogger("off-local-api")
STOP = threading.Event()


def database():
    return MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017/"),
                       serverSelectionTimeoutMS=5000, socketTimeoutMS=60000,
                       maxPoolSize=8)["off_local"]


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def revision(product):
    values = []
    for key in ("last_modified_t", "last_updated_t"):
        try:
            value = float(product.get(key, 0))
            values.append(value if math.isfinite(value) else 0)
        except (ValueError, TypeError):
            values.append(0)
    return max(values)


def save_product(collection, product):
    """Keep the original document intact; the envelope supplies an EAN index."""
    code = product.get("code")
    indexed = isinstance(code, str) and bool(code.strip())
    if not indexed:
        # Exported placeholders have no EAN. Preserve them under an object key
        # that cannot collide with a genuine string barcode; never invent an EAN.
        digest = hashlib.sha256(json.dumps(product, sort_keys=True,
                                           ensure_ascii=False).encode()).hexdigest()
        code = {"unindexed_sha256": digest}
    version = revision(product)
    query = {"_id": code, "$or": [{"version": {"$lte": version}},
                                    {"version": {"$exists": False}}]}
    try:
        collection.replace_one(query, {"_id": code, "version": version, "indexed": indexed,
                                       "product": product}, upsert=True)
    except DuplicateKeyError:
        # An older delta must not overwrite a newer snapshot record.
        pass
    return indexed


def open_url(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": f"Nisbo-OFF-Local-API/{VERSION}", "Accept-Encoding": "identity"})
    return urllib.request.urlopen(request, timeout=90)


def export_url(kind):
    project = PROJECTS[kind]
    if kind == "food":
        return "https://openfoodfacts-ds.s3.eu-west-3.amazonaws.com/openfoodfacts-products.jsonl.gz"
    return f"https://static.{project}.org/data/{project}-products.jsonl.gz"


def delta_url(kind):
    return f"https://static.{PROJECTS[kind]}.org/data/delta/"


def import_stream(response, collection, label):
    count = unindexed = 0
    with gzip.GzipFile(fileobj=response) as stream:
        while True:
            if STOP.is_set():
                raise InterruptedError("Import stopped; published collection retained")
            line = stream.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                raise ValueError("Export record exceeds 32 MiB")
            if not line.strip():
                continue
            product = json.loads(line)
            if not isinstance(product, dict):
                raise ValueError("Export record is not an object")
            indexed = save_product(collection, product)
            count += 1
            if not indexed:
                unindexed += 1
                if unindexed <= 10:
                    LOG.warning("%s: record %s has no barcode; preserved without EAN index", label, count)
            if count % 10000 == 0:
                LOG.info("%s: %s records processed", label, count)
    LOG.info("%s: finished %s records (%s without barcode, preserved)", label, count, unindexed)
    return count, unindexed


def full_import(db, kind):
    """Publish only after gzip EOF/CRC and every database write succeeded."""
    old = db.state.find_one({"_id": kind}) or {}
    # Exactly one sync service owns imports; discard interrupted unpublished generations.
    for name in db.list_collection_names():
        if re.fullmatch(kind + r"_[0-9a-f]{32}", name) and name != old.get("collection"):
            db.drop_collection(name)
    stage = f"{kind}_{uuid.uuid4().hex}"
    collection = db[stage]
    started = time.time()
    db.state.update_one({"_id": kind}, {"$set": {
        "phase": "full_import", "attempt_at": timestamp()}}, upsert=True)
    published = False
    try:
        with open_url(export_url(kind)) as response:
            modified = response.headers.get("Last-Modified")
            source_time = email.utils.parsedate_to_datetime(modified).timestamp() if modified else started
            count, unindexed = import_stream(response, collection, kind)
        if not count:
            raise ValueError("Empty snapshot; previous collection retained")
        # Abort suspiciously truncated snapshots even if the gzip is valid.
        previous_count = old.get("records", 0)
        if previous_count and count < previous_count * 0.75:
            raise ValueError("Snapshot shrank by over 25%; manual review required")
        cursor = min(started, source_time) - 86400
        db.state.update_one({"_id": kind}, {"$set": {
            "collection": stage, "ready": True, "records": count,
            "unindexed_records": unindexed,
            "full_at": timestamp(), "full_epoch": time.time(),
            "delta_cursor": cursor, "source_modified": modified,
            "phase": "ready", "error": None}}, upsert=True)
        published = True
        # Readers retry the pointer if an old generation disappeared mid-request.
        if old.get("collection") and old["collection"] != stage:
            db.drop_collection(old["collection"])
        LOG.info("%s: published %s products", kind, count)
    finally:
        if not published:
            db.drop_collection(stage)


def parse_deltas(text, project):
    files = []
    pattern = re.compile(re.escape(project) + r"_products_(\d+)_(\d+)\.json\.gz")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = pattern.fullmatch(line)
        if not match:
            raise ValueError("Unexpected delta index entry")
        start, end = map(int, match.groups())
        if start >= end:
            raise ValueError("Invalid delta interval")
        files.append((start, end, line))
    if not files:
        raise ValueError("Empty delta index")
    return sorted(set(files))


def apply_deltas(db, kind):
    state = db.state.find_one({"_id": kind})
    with open_url(delta_url(kind) + "index.txt") as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("Delta index too large")
    files = parse_deltas(raw.decode("utf-8"), PROJECTS[kind])
    cursor = state["delta_cursor"]
    if cursor < files[0][0]:
        raise ValueError("Delta gap: full import required")
    for start, end, name in files:
        if end <= cursor:
            continue
        if start > cursor:
            raise ValueError("Delta gap: full import required")
        db.state.update_one({"_id": kind}, {"$set": {"phase": "delta_import"}})
        with open_url(delta_url(kind) + name) as response:
            count, unindexed = import_stream(response, db[state["collection"]], name)
        # A failed file is replayed in full, never recorded as completed.
        cursor = end
        db.state.update_one({"_id": kind}, {"$set": {
            "delta_cursor": cursor, "last_delta": name,
            "delta_at": timestamp(), "delta_records": count,
            "delta_unindexed_records": unindexed}})
    db.state.update_one({"_id": kind}, {"$set": {
        "phase": "ready", "error": None, "checked_at": timestamp()}})


def sync_one(db, kind):
    state = db.state.find_one({"_id": kind}) or {}
    due = time.time() - state.get("full_epoch", 0) > float(os.environ.get("FULL_DAYS", "30")) * 86400
    if not state.get("ready") or due:
        full_import(db, kind)
    try:
        apply_deltas(db, kind)
    except ValueError as error:
        if str(error) != "Delta gap: full import required":
            raise
        full_import(db, kind)
        apply_deltas(db, kind)


def sync_loop(db, once=False):
    while not STOP.is_set():
        failed = False
        # Import small projects before the multi-GB food snapshot.
        for kind in ORDER:
            if STOP.is_set():
                break
            try:
                sync_one(db, kind)
            except InterruptedError:
                return
            except Exception as error:
                failed = True
                LOG.exception("%s: synchronization failed", kind)
                db.state.update_one({"_id": kind}, {"$set": {
                    "phase": "error", "error": str(error)[:500],
                    "error_at": timestamp()}}, upsert=True)
        if once:
            return 1 if failed else 0
        STOP.wait(max(60, int(os.environ.get("SYNC_SECONDS", "21600"))))


def image_fields(product, kind, language):
    """OFF exports contain image metadata; construct missing selected-image URLs."""
    images = product.get("images") or {}
    if not isinstance(images, dict):
        return
    code = str(product.get("code", ""))
    if not code.isdigit():
        return
    if len(code) > 8:
        path = "/".join((code[:3], code[3:6], code[6:9], code[9:]))
    else:
        path = code
    root = f"https://images.{PROJECTS[kind]}.org/images/products/{path}"
    for role in ("front", "ingredients", "nutrition", "packaging"):
        keys = [f"{role}_{language}", f"{role}_{product.get('lc', '')}", role]
        key = next((key for key in keys if isinstance(images.get(key), dict)), None)
        if key is None:
            continue
        info = images[key]
        rev = str(info.get("rev", ""))
        if not rev.isdigit() or not re.fullmatch(r"[a-z_0-9-]+", key):
            continue
        for suffix, size in (("thumb", "100"), ("small", "200"), ("", "400")):
            field = f"image_{role}_{suffix}_url" if suffix else f"image_{role}_url"
            product.setdefault(field, f"{root}/{key}.{rev}.{size}.jpg")
    for suffix in ("thumb_url", "small_url", "url"):
        if f"image_front_{suffix}" in product:
            product.setdefault(f"image_{suffix}", product[f"image_front_{suffix}"])


def lookup(db, code, kind, language, fields=None):
    kinds = list(PROJECTS) if kind == "all" else [kind]
    missing = []
    for candidate in kinds:
        for attempt in range(2):
            state = db.state.find_one({"_id": candidate}) or {}
            if not state.get("ready"):
                missing.append(candidate)
                break
            record = db[state["collection"]].find_one({"_id": code})
            if record is None:
                fresh = db.state.find_one({"_id": candidate}) or {}
                if fresh.get("collection") != state["collection"] and not attempt:
                    continue
                break
            product = copy.deepcopy(record["product"])
            if product.get("deleted") or product.get("product_type", candidate) != candidate:
                break
            product.setdefault("product_type", candidate)
            image_fields(product, candidate, language)
            if fields is not None:
                product = {key: product[key] for key in fields if key in product}
            return 200, {"code": code, "product": product, "status": "success",
                         "result": {"id": "product_found", "name": "Product found",
                                    "lc_name": "Product found"}, "errors": [], "warnings": []}
    if missing:
        return 503, {"status": "failure", "error": "datasets_not_ready", "missing": missing}
    return 404, {"code": code, "status": "failure", "warnings": [],
                 "result": {"id": "product_not_found", "name": "Product not found",
                            "lc_name": "Product not found"},
                 "errors": [{"field": {"id": "code", "value": code},
                             "impact": {"id": "failure", "name": "Failure", "lc_name": "Failure"},
                             "message": {"id": "product_not_found", "name": "", "lc_name": ""}}]}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, db, token):
        super().__init__(address, Handler)
        self.db, self.token = db, token
        self.slots = threading.BoundedSemaphore(8)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def send_json(self, status, payload):
        body = json_util.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Data-Attribution", "Open Food Facts contributors; ODbL-1.0")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        expected = "Bearer " + self.server.token
        if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            self.send_json(401, {"error": "authentication_required"})
            return
        try:
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path == "/health":
                states = {state.pop("_id"): state for state in self.server.db.state.find({})}
                for kind in PROJECTS:
                    states.setdefault(kind, {"ready": False, "phase": "pending"})
                self.send_json(200, {"version": VERSION, "datasets": states,
                                     "all_ready": all(s.get("ready") for s in states.values()),
                                     "all_synced": all(s.get("ready") and s.get("phase") == "ready"
                                                       for s in states.values()),
                                     "attribution": "Open Food Facts contributors — ODbL-1.0",
                                     "source": "https://world.openfoodfacts.org/data"})
                return
            match = re.fullmatch(r"/api/v3/product/([0-9]+)(?:\.json)?", parsed.path)
            if not match:
                self.send_json(404, {"error": "unsupported_endpoint"})
                return
            params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if set(params) - {"fields", "product_type", "lc"}:
                self.send_json(400, {"error": "unsupported_parameters"})
                return
            kind = params.get("product_type", ["food"])[0]
            language = params.get("lc", ["en"])[0]
            if kind not in (*PROJECTS, "all") or not re.fullmatch(r"[a-z]{2,3}(?:-[a-z]{2})?", language):
                self.send_json(400, {"error": "invalid_parameters"})
                return
            fields = None
            if "fields" in params and params["fields"][0] not in ("", "all", "raw"):
                fields = params["fields"][0].split(",")
                if len(fields) > 100 or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", f) for f in fields):
                    self.send_json(400, {"error": "unsupported_fields"})
                    return
            status, payload = lookup(self.server.db, match[1], kind, language, fields)
            self.send_json(status, payload)
        except (PyMongoError, ValueError, TypeError):
            LOG.exception("API request failed")
            self.send_json(503, {"error": "database_unavailable"})

    def log_message(self, fmt, *args):
        LOG.info(fmt, *args)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    db = database()
    if mode in ("sync", "sync-once"):
        signal.signal(signal.SIGTERM, lambda *_: STOP.set())
        signal.signal(signal.SIGINT, lambda *_: STOP.set())
        return sync_loop(db, once=mode == "sync-once")
    if mode != "api":
        raise SystemExit("Usage: app.py api|sync|sync-once")
    token = os.environ.get("API_TOKEN", "")
    if len(token) < 24:
        raise SystemExit("API_TOKEN must contain at least 24 characters")
    Server(("0.0.0.0", 8080), db, token).serve_forever()


if __name__ == "__main__":
    sys.exit(main())
