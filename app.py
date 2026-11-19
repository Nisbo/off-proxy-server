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
import secrets
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bson import json_util
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from dashboard import ASSETS, LOOKUP_FIELDS, WEB, Dashboard
import control
import security

VERSION = "0.1.9"
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


class HTTPSRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        if urllib.parse.urlsplit(new_url).scheme != "https":
            raise ValueError("Export redirect must use HTTPS")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def open_url(url):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("Export download must use HTTPS")
    request = urllib.request.Request(url, headers={
        "User-Agent": f"Nisbo-OFF-Local-API/{VERSION}", "Accept-Encoding": "identity"})
    return urllib.request.build_opener(HTTPSRedirects()).open(request, timeout=90)


def export_url(kind):
    project = PROJECTS[kind]
    if kind == "food":
        return "https://openfoodfacts-ds.s3.eu-west-3.amazonaws.com/openfoodfacts-products.jsonl.gz"
    return f"https://static.{project}.org/data/{project}-products.jsonl.gz"


def delta_url(kind):
    return f"https://static.{PROJECTS[kind]}.org/data/delta/"


class CountingReader:
    def __init__(self, response):
        self.response, self.count = response, 0

    def read(self, size=-1):
        data = self.response.read(size)
        self.count += len(data)
        return data


def import_stream(response, collection, label, progress=None):
    count = unindexed = 0
    reader = CountingReader(response)
    try:
        total = int(response.headers.get("Content-Length", "0")) or None
    except (TypeError, ValueError):
        total = None
    started = time.time()
    last_report = time.monotonic()

    def report(finished=False):
        if progress:
            now = time.time()
            progress({"records": count, "unindexed": unindexed, "downloaded_bytes": reader.count,
                      "total_bytes": total, "started_epoch": started, "updated_epoch": now,
                      "records_per_second": count / max(0.001, now - started), "finished": finished})

    report()
    with gzip.GzipFile(fileobj=reader) as stream:
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
            if count % 250 == 0 and time.monotonic() - last_report >= 2:
                report()
                last_report = time.monotonic()
    report(finished=True)
    LOG.info("%s: finished %s records (%s without barcode, preserved)", label, count, unindexed)
    return count, unindexed


def progress_reporter(db, kind, mode):
    def report(progress):
        db.state.update_one({"_id": kind}, {"$set": {"progress": dict(progress, mode=mode)}}, upsert=True)
        db.scheduler.update_one({"_id": "sync"}, {"$set": {"heartbeat_epoch": time.time()}}, upsert=True)
    return report


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
        "phase": "full_import", "attempt_at": timestamp(),
        "progress": {"mode": "full", "records": 0, "unindexed": 0,
                     "started_epoch": started, "updated_epoch": started,
                     "downloaded_bytes": 0, "total_bytes": None, "finished": False}}}, upsert=True)
    published = False
    try:
        with open_url(export_url(kind)) as response:
            modified = response.headers.get("Last-Modified")
            source_time = email.utils.parsedate_to_datetime(modified).timestamp() if modified else started
            count, unindexed = import_stream(response, collection, kind, progress_reporter(db, kind, "full"))
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
            "phase": "ready", "error": None, "delta_gaps": [], "full_reasons": []}}, upsert=True)
        published = True
        # Readers retry the pointer if an old generation disappeared mid-request.
        if old.get("collection") and old["collection"] != stage:
            try:
                db.drop_collection(old["collection"])
            except PyMongoError:
                LOG.warning("%s: old snapshot retained after successful publication", kind)
        LOG.info("%s: published %s products", kind, count)
    finally:
        if not published:
            # A lost acknowledgement can mean publication succeeded despite an exception.
            # Never remove a generation unless its unpublished state can be established.
            try:
                current = db.state.find_one({"_id": kind}) or {}
                if current.get("collection") != stage:
                    db.drop_collection(stage)
            except PyMongoError:
                LOG.warning("%s: cleanup deferred until the published pointer can be verified", kind)


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
    gaps = control.merge_ranges(state.get("delta_gaps", []))
    horizon = max([cursor] + [end for _, end in gaps])
    pause = control.settings(db)["delta_gap_policy"] == "pause"

    def persist():
        db.state.update_one({"_id": kind}, {"$set": {"delta_gaps": gaps}})

    for start, end, name in files:
        if end <= cursor and not any(start < high and end > low for low, high in gaps):
            continue
        if start > horizon:
            gaps = control.merge_ranges([*gaps, [horizon, start]])
            horizon = start
            persist()
        # A returning historical file may repair the earliest gap even in pause mode.
        if pause and gaps and start > gaps[0][0]:
            break
        db.state.update_one({"_id": kind}, {"$set": {"phase": "delta_import",
            "progress": {"mode": "delta", "records": 0, "unindexed": 0,
                         "started_epoch": time.time(), "updated_epoch": time.time(),
                         "downloaded_bytes": 0, "total_bytes": None, "finished": False}}})
        try:
            with open_url(delta_url(kind) + name) as response:
                count, unindexed = import_stream(response, db[state["collection"]], name,
                                                 progress_reporter(db, kind, "delta"))
        except urllib.error.HTTPError as error:
            if error.code not in (404, 410):
                raise
            # Only an explicitly absent file establishes a gap, not a timeout/5xx.
            if end > horizon:
                gaps = control.merge_ranges([*gaps, [max(start, horizon), end]])
                horizon = end
                persist()
            if pause and gaps:
                break
            continue
        gaps = control.cover_range(gaps, start, end)
        cursor = max(cursor, end)
        horizon = max(horizon, end)
        # Commit coverage only after gzip validation; failed files are replayed.
        db.state.update_one({"_id": kind}, {"$set": {
            "delta_cursor": cursor, "delta_gaps": gaps, "last_delta": name,
            "delta_at": timestamp(), "delta_records": count,
            "delta_unindexed_records": unindexed}})
    db.state.update_one({"_id": kind}, {"$set": {
        "phase": ("gap_paused" if pause else "partial") if gaps else "ready",
        "delta_gaps": gaps, "error": None, "checked_at": timestamp()}})


def full_reasons(state, settings):
    reasons = []
    if not state.get("ready"):
        reasons.append("initial")
    if state.get("delta_gaps"):
        reasons.append("gap")
    days = settings["full_interval_days"]
    if state.get("ready") and days and time.time() - state.get("full_epoch", 0) >= days * 86400:
        reasons.append("scheduled")
    return reasons


def sync_one(db, kind):
    options = control.settings(db)
    state = db.state.find_one({"_id": kind}) or {}
    approved = control.claim(db, "full:" + kind)
    imported = False
    try:
        if approved or (options["full_import_policy"] == "automatic" and full_reasons(state, options)):
            full_import(db, kind)
            imported = True
            if approved:
                control.finish(db, "full:" + kind)
                approved = None
        elif not state.get("ready"):
            db.state.update_one({"_id": kind}, {"$set": {
                "phase": "needs_full_import", "full_reasons": ["initial"]}}, upsert=True)
            return
        apply_deltas(db, kind)
        state = db.state.find_one({"_id": kind}) or {}
        if (not imported and state.get("delta_gaps") and options["full_import_policy"] == "automatic"):
            full_import(db, kind)
            apply_deltas(db, kind)
    except Exception as error:
        if approved:
            control.finish(db, "full:" + kind, str(error)[:500])
        raise
    else:
        if approved:
            control.finish(db, "full:" + kind)
    finally:
        state = db.state.find_one({"_id": kind}) or {}
        db.state.update_one({"_id": kind}, {"$set": {"full_reasons": full_reasons(state, options)}})


def sync_loop(db, once=False):
    interval = max(60, int(os.environ.get("SYNC_SECONDS", "21600")))
    recovering = True
    try:
        while not STOP.is_set():
            if not control.begin_cycle(db, {
                    "cycle_started_at": timestamp(), "heartbeat_epoch": time.time(),
                    "next_check_epoch": None, "active_kind": None, "sync_seconds": interval}):
                STOP.wait(2)
                continue
            if recovering:
                # A process restart never silently reauthorizes an interrupted full import.
                db.requests.update_many({"status": "running"}, {"$set": {
                    "status": "failed", "error": "Worker restarted; request again", "finished_epoch": time.time()}})
                db.state.update_many({"phase": {"$in": ["full_import", "delta_import"]}}, {"$set": {
                    "phase": "error", "error": "Worker restarted; interrupted import retained no completion marker",
                    "error_at": timestamp()}})
                recovering = False
            db.requests.update_one({"_id": "sync"}, {"$set": {
                "status": "running", "started_epoch": time.time(), "error": None}}, upsert=True)
            failed = False
            for kind in ORDER:
                if STOP.is_set():
                    break
                db.scheduler.update_one({"_id": "sync"}, {"$set": {
                    "active_kind": kind, "heartbeat_epoch": time.time()}})
                try:
                    sync_one(db, kind)
                except InterruptedError:
                    db.state.update_one({"_id": kind}, {"$set": {
                        "phase": "error", "error": "Synchronization interrupted", "error_at": timestamp()}})
                    return
                except Exception as error:
                    failed = True
                    LOG.exception("%s: synchronization failed", kind)
                    db.state.update_one({"_id": kind}, {"$set": {
                        "phase": "error", "error": str(error)[:500],
                        "error_at": timestamp()}}, upsert=True)
            control.finish(db, "sync", "One or more sources failed" if failed else None)
            finished = time.time()
            db.scheduler.update_one({"_id": "sync"}, {"$set": {
                "phase": "idle" if once else "waiting", "active_kind": None,
                "finished_at": timestamp(), "heartbeat_epoch": finished,
                "next_check_epoch": None if once else finished + interval}})
            if once:
                return 1 if failed else 0
            # The sole worker polls durable UI requests; the API never imports products.
            deadline = time.monotonic() + interval
            while not STOP.is_set() and time.monotonic() < deadline:
                if db.requests.find_one({"status": "pending"}):
                    break
                STOP.wait(min(2, max(0, deadline - time.monotonic())))
    finally:
        if STOP.is_set():
            db.scheduler.update_one({"_id": "sync"}, {"$set": {
                "phase": "stopped", "active_kind": None, "next_check_epoch": None}})


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
        self.db = db
        self.security = security.Security(db, token)
        self.dashboard = Dashboard(db, VERSION, PROJECTS)
        self.control_nonce = secrets.token_urlsafe(32)
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

    def send_body(self, status, body, content_type, cookie=None):
        self.send_response(status)
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data: https://images.openfoodfacts.org "
                         "https://images.openbeautyfacts.org https://images.openpetfoodfacts.org "
                         "https://images.openproductsfacts.org; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("X-Data-Attribution", "Open Food Facts contributors; ODbL-1.0")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload, cookie=None):
        self.send_body(status, json_util.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", cookie)

    def current_session(self):
        return self.server.security.session(self.headers.get("Cookie", ""))

    def session_cookie(self, raw=""):
        secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
        return (f"{security.COOKIE}={raw}; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age={security.MAX_AGE if raw else 0}" + ("; Secure" if secure else ""))

    def public_dashboard(self, parsed):
        if parsed.path in ASSETS:
            filename, content_type = ASSETS[parsed.path]
            self.send_body(200, (WEB / filename).read_bytes(), content_type)
            return True
        session = self.current_session() if parsed.path == "/auth/status" or parsed.path.startswith("/ui/") else None
        if parsed.path == "/auth/status":
            self.send_json(200, {"authenticated": bool(session),
                "configured": bool(self.server.security.config()["password_hash"]),
                "control_nonce": session["csrf"] if session else self.server.control_nonce})
            return True
        if parsed.path.startswith("/ui/") and not session:
            self.send_json(401, {"error": "authentication_required"})
            return True
        if parsed.path == "/ui/security":
            self.send_json(200, self.server.security.public_settings())
            return True
        if parsed.path == "/ui/api-key":
            if not hmac.compare_digest(self.headers.get("X-Off-Proxy-Control", "").encode(), session["csrf"].encode()):
                self.send_json(403, {"error": "control_denied"})
            else:
                self.send_json(200, {"api_token": self.server.security.api_key()})
            return True
        if parsed.path == "/ui/status":
            self.send_json(200, {**self.server.dashboard.snapshot(), "control_nonce": session["csrf"]})
            return True
        if parsed.path == "/ui/lookup":
            params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            code = params.get("ean", [""])[0]
            kind = params.get("product_type", ["all"])[0]
            language = params.get("lc", ["en"])[0]
            if (set(params) - {"ean", "lc", "product_type"} or any(len(v) != 1 for v in params.values()) or not re.fullmatch(r"[0-9]{1,256}", code)
                    or kind not in (*PROJECTS, "all") or language not in ("de", "en")):
                self.send_json(400, {"error": "invalid_lookup"})
                return True
            started = time.perf_counter()
            status, result = lookup(self.server.db, code, kind, language, LOOKUP_FIELDS)
            result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
            self.send_json(status, result)
            return True
        return False

    def do_GET(self):
        try:
            parsed = urllib.parse.urlsplit(self.path)
        except ValueError:
            self.send_json(400, {"error": "invalid_request"})
            return
        try:
            if self.public_dashboard(parsed):
                return
        except (PyMongoError, ValueError, TypeError):
            LOG.exception("Dashboard request failed")
            self.send_json(503, {"error": "database_unavailable"})
            return
        try:
            expected = "Bearer " + self.server.security.api_key()
            public_product = (not self.server.security.config()["api_auth_required"]
                              and re.fullmatch(r"/api/v3/product/[0-9]+(?:\.json)?", parsed.path))
            if not public_product and not hmac.compare_digest(self.headers.get("Authorization", "").encode(), expected.encode()):
                self.send_json(401, {"error": "authentication_required"})
                return
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
            if len(match[1]) > 256:
                self.send_json(400, {"error": "invalid_barcode"})
                return
            params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if set(params) - {"fields", "product_type", "lc"} or any(len(v) != 1 for v in params.values()):
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

    def do_POST(self):
        try:
            session = self.current_session()
            path = urllib.parse.urlsplit(self.path).path
            if path != "/auth/login" and not session:
                raise security.Denied()
            origin = urllib.parse.urlsplit(self.headers.get("Origin", ""))
            expected = self.server.control_nonce if path == "/auth/login" else session["csrf"]
            if (not hmac.compare_digest(self.headers.get("X-Off-Proxy-Control", "").encode(), expected.encode())
                    or self.headers.get("Sec-Fetch-Site") == "cross-site"
                    or (origin.netloc and origin.netloc != self.headers.get("Host"))):
                raise security.Denied("control_denied", 403)
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096 or self.headers.get_content_type() != "application/json":
                raise ValueError("Invalid request body")
            values = json.loads(self.rfile.read(length))
            if not isinstance(values, dict):
                raise ValueError("Expected an object")
            if path == "/auth/login":
                raw = self.server.security.login(values.get("password"), self.client_address[0])
                self.send_json(200, {"ok": True}, self.session_cookie(raw))
            elif path == "/auth/logout":
                self.server.db.sessions.delete_one({"_id": session["_id"]})
                self.send_json(200, {"ok": True}, self.session_cookie())
            elif path == "/auth/logout-all":
                self.server.security.revoke_all()
                self.send_json(200, {"ok": True}, self.session_cookie())
            elif path == "/auth/activity":
                self.server.security.activity(session)
                self.send_json(200, {"ok": True})
            elif path == "/auth/password":
                self.server.security.limit_login(self.client_address[0])
                if not security.password_matches(values.get("current_password"), self.server.security.config()["password_hash"]):
                    raise security.Denied("invalid_password")
                self.server.security.set_password(values.get("new_password"))
                self.send_json(200, {"ok": True}, self.session_cookie())
            elif path == "/ui/security":
                self.send_json(200, self.server.security.save(values))
            elif path == "/ui/settings":
                self.send_json(200, {"settings": control.save_settings(self.server.db, values)})
            elif path == "/ui/sync" and not values:
                queued = control.request(self.server.db, "sync")
                self.send_json(202, {"queued": queued})
            elif path == "/ui/full-import":
                if (set(values) != {"kind", "confirmed"} or values.get("kind") not in PROJECTS
                        or values.get("confirmed") is not True):
                    raise ValueError("Full import requires a dataset and confirmation")
                state = self.server.db.state.find_one({"_id": values["kind"]}) or {}
                queued = False if state.get("phase") == "full_import" else control.request(self.server.db, "full:" + values["kind"])
                self.send_json(202, {"queued": queued})
            else:
                self.send_json(400, {"error": "invalid_control"})
        except security.Denied as error:
            self.send_json(error.status, {"error": error.code})
        except (ValueError, TypeError):
            self.send_json(400, {"error": "invalid_control"})
        except PyMongoError:
            LOG.exception("Dashboard control failed")
            self.send_json(503, {"error": "database_unavailable"})

    def log_message(self, fmt, *args):
        # Query strings may contain accidentally pasted credentials; never log them.
        LOG.info("%s %r", getattr(self, "command", "HTTP"), self.path.split("?", 1)[0])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    db = database()
    if mode in ("sync", "sync-once"):
        signal.signal(signal.SIGTERM, lambda *_: STOP.set())
        signal.signal(signal.SIGINT, lambda *_: STOP.set())
        return sync_loop(db, once=mode == "sync-once")
    if mode in ("password", "password-configured"):
        access = security.Security(db, os.environ.get("API_TOKEN", ""))
        if mode == "password-configured":
            print("yes" if access.config()["password_hash"] else "no")
            return 0
        try:
            password = sys.stdin.buffer.readline(2048).decode().rstrip("\n")
            access.set_password(password)
        except (ValueError, UnicodeError) as error:
            raise SystemExit(str(error))
        print("Password saved; all sessions signed out / Passwort gespeichert; alle Sitzungen abgemeldet.")
        return 0
    if mode != "api":
        raise SystemExit("Usage: app.py api|sync|sync-once")
    token = os.environ.get("API_TOKEN", "")
    if len(token) < 24:
        raise SystemExit("API_TOKEN must contain at least 24 characters")
    Server(("0.0.0.0", 8080), db, token).serve_forever()  # nosec B104 # Container listener; host binding is controlled by BIND_IP.


if __name__ == "__main__":
    sys.exit(main())
