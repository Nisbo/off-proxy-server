"""Read-only OFF product API; full records, atomic snapshots, replayable deltas."""
import copy
import datetime as dt
import email.utils
from email.message import Message
from http import HTTPStatus
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
from gunicorn.app.base import BaseApplication

from bson import json_util
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from dashboard import ASSETS, LOOKUP_FIELDS, WEB, Dashboard
import control
import security
import components
import releases

VERSION = "0.1.20"
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
    published = publication_attempted = False
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
        publication_attempted = True
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
            # An acknowledgement failure cannot prove that publication did not commit.
            # Retain that candidate, even if a subsequent read still shows the old pointer.
            if publication_attempted:
                LOG.warning("%s: publication result uncertain; candidate snapshot retained", kind)
            else:
                try:
                    db.drop_collection(stage)
                except PyMongoError:
                    LOG.warning("%s: unpublished snapshot cleanup deferred", kind)


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

    applied = 0
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
        applied += 1
    db.state.update_one({"_id": kind}, {"$set": {
        "phase": ("gap_paused" if pause else "partial") if gaps else "ready",
        "delta_gaps": gaps, "error": None, "checked_at": timestamp()}})
    return applied


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
            return False
        applied = apply_deltas(db, kind)
        state = db.state.find_one({"_id": kind}) or {}
        if (not imported and state.get("delta_gaps") and options["full_import_policy"] == "automatic"):
            full_import(db, kind)
            imported = True
            apply_deltas(db, kind)
    except Exception as error:
        if approved:
            control.finish(db, "full:" + kind, str(error)[:500])
        raise
    else:
        if approved:
            control.finish(db, "full:" + kind)
        return imported or bool(applied)
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
                "status": "running", "started_epoch": time.time(), "error": None},
                "$unset": {"finished_epoch": "", "outcome": ""}}, upsert=True)
            failed = changed = incomplete = False
            for kind in ORDER:
                if STOP.is_set():
                    control.finish(db, "sync", "Synchronization interrupted")
                    return
                db.scheduler.update_one({"_id": "sync"}, {"$set": {
                    "active_kind": kind, "heartbeat_epoch": time.time()}})
                try:
                    changed |= bool(sync_one(db, kind))
                    state = db.state.find_one({"_id": kind}, {"phase": 1, "full_reasons": 1}) or {}
                    incomplete |= state.get("phase") in ("needs_full_import", "gap_paused", "partial") or bool(state.get("full_reasons"))
                except InterruptedError:
                    db.state.update_one({"_id": kind}, {"$set": {
                        "phase": "error", "error": "Synchronization interrupted", "error_at": timestamp()}})
                    control.finish(db, "sync", "Synchronization interrupted")
                    return
                except Exception as error:
                    failed = True
                    LOG.exception("%s: synchronization failed", kind)
                    db.state.update_one({"_id": kind}, {"$set": {
                        "phase": "error", "error": str(error)[:500],
                        "error_at": timestamp()}}, upsert=True)
            outcome = ("updated_incomplete" if changed else "incomplete") if incomplete else ("updated" if changed else "unchanged")
            control.finish(db, "sync", "One or more sources failed" if failed else None,
                           outcome=None if failed else outcome)
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


def _selected_image(images, role, languages):
    """Read both dump schemas and fall back to another available translation."""
    candidates = {}
    for key, info in images.items():
        if isinstance(key, str) and (key == role or key.startswith(role + "_")):
            candidates[key] = info
    selected = images.get("selected")
    if isinstance(selected, dict) and isinstance(selected.get(role), dict):
        for language, info in selected[role].items():
            if isinstance(language, str):
                candidates[f"{role}_{language}"] = info
    # Requested language, product language, generic image, English, then another
    # selected language. A Spanish-only front image is still useful in German.
    preferred = [f"{role}_{language}" for language in languages if language]
    preferred.extend((role, f"{role}_en"))
    for key in dict.fromkeys([*preferred, *sorted(candidates)]):
        info = candidates.get(key)
        if not isinstance(info, dict) or not re.fullmatch(r"[a-z_0-9-]+", key):
            continue
        revision = str(info.get("rev", ""))
        if re.fullmatch(r"[0-9]+", revision):
            return key, revision
    return None


def image_fields(product, kind, language):
    """Construct original image-server URLs without changing stored metadata."""
    images = product.get("images") or {}
    if not isinstance(images, dict):
        return
    code = str(product.get("code", ""))
    if not re.fullmatch(r"[0-9]+", code):
        return
    if len(code) > 8:
        path = "/".join((code[:3], code[3:6], code[6:9], code[9:]))
    else:
        path = code
    root = f"https://images.{PROJECTS[kind]}.org/images/products/{path}"
    languages = (language, product.get("lc"), product.get("lang"))
    for role in ("front", "ingredients", "nutrition", "packaging"):
        selected = _selected_image(images, role, languages)
        if selected is None:
            continue
        key, revision = selected
        for suffix, size in (("thumb", "100"), ("small", "200"), ("", "400")):
            field = f"image_{role}_{suffix}_url" if suffix else f"image_{role}_url"
            if not product.get(field):
                product[field] = f"{root}/{key}.{revision}.{size}.jpg"
    for suffix in ("thumb_url", "small_url", "url"):
        if product.get(f"image_front_{suffix}") and not product.get(f"image_{suffix}"):
            product[f"image_{suffix}"] = product[f"image_front_{suffix}"]


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


class Application:
    """Shared WSGI routes, independent of the HTTP server."""

    def __init__(self, db, token):
        self.db = db
        self.security = security.Security(db, token)
        self.dashboard = Dashboard(db, VERSION, PROJECTS)
        self.control_nonce = secrets.token_urlsafe(32)

    def application(self, environ, start_response):
        request = Request(self, environ)
        try:
            length = environ.get("CONTENT_LENGTH") or "0"
            if not length.isdigit() or int(length) > 4096:
                request.send_json(413, {"error": "request_too_large"})
            elif request.command in ("GET", "HEAD"):
                request.do_GET()
            elif request.command == "POST":
                request.do_POST()
            else:
                request.send_json(405, {"error": "method_not_allowed"})
        except Exception:
            LOG.exception("Unhandled application error")
            request.send_json(500, {"error": "internal_error"})
        # Never log query strings: they may contain accidentally pasted keys.
        LOG.info("%s %r", request.command, environ.get("PATH_INFO", ""))
        start_response(f"{request.status} {HTTPStatus(request.status).phrase}", request.response_headers)
        return [b"" if request.command == "HEAD" else request.body]



class Gunicorn(BaseApplication):
    def load_config(self):
        options = dict(bind="0.0.0.0:8080", workers=1, worker_class="gthread", threads=8,
                       worker_connections=32, backlog=16, timeout=30, graceful_timeout=30,
                       keepalive=5, limit_request_line=8190, limit_request_fields=64,
                       limit_request_field_size=8190, forwarded_allow_ips="",
                       secure_scheme_headers={}, control_socket_disable=True,
                       accesslog=None, errorlog="-", worker_tmp_dir="/tmp")  # nosec B108 # Private container tmpfs; Gunicorn creates secure temporary files.
        for name, value in options.items():
            self.cfg.set(name, value)

    def load(self):
        # Create MongoClient after fork; one threaded worker keeps login throttling
        # and the anonymous login nonce consistent across requests.
        return create_app().application


def create_app():
    token = os.environ.get("API_TOKEN", "")
    if len(token) < 24:
        raise ValueError("API_TOKEN must contain at least 24 characters")
    return Application(database(), token)


class Request:
    """Routes consume WSGI requests; Gunicorn owns HTTP parsing and sockets."""

    def __init__(self, server, environ):
        self.server = server
        self.command = environ["REQUEST_METHOD"]
        self.path = environ.get("PATH_INFO", "") + ("?" + environ["QUERY_STRING"] if environ.get("QUERY_STRING") else "")
        self.client_address = (environ.get("REMOTE_ADDR", ""), 0)
        self.headers = Message()
        for name, value in environ.items():
            if name.startswith("HTTP_"):
                self.headers[name[5:].replace("_", "-")] = value
        self.headers["Content-Length"] = environ.get("CONTENT_LENGTH", "0")
        self.headers["Content-Type"] = environ.get("CONTENT_TYPE", "")
        self.rfile = environ["wsgi.input"]

    def send_body(self, status, body, content_type, cookie=None):
        self.status, self.body = status, body
        self.response_headers = [
            ("Content-Type", content_type), ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
             "connect-src 'self'; img-src 'self' data: https://images.openfoodfacts.org "
             "https://images.openbeautyfacts.org https://images.openpetfoodfacts.org "
             "https://images.openproductsfacts.org; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
            ("X-Data-Attribution", "Open Food Facts contributors; ODbL-1.0"),
        ]
        if cookie is not None:
            self.response_headers.append(("Set-Cookie", cookie))

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
        if parsed.path == "/ui/components":
            self.send_json(200, components.snapshot(self.server.db))
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
            elif path in ("/ui/program/check", "/ui/program/update"):
                channel = values.get("channel")
                if channel not in releases.CHANNELS:
                    raise ValueError("Invalid release channel")
                if path.endswith("/check"):
                    if set(values) != {"channel"}:
                        raise ValueError("Invalid check")
                    try:
                        release = releases.latest(channel)
                    except (OSError, ValueError, KeyError, TypeError, AttributeError):
                        raise security.Denied("program_check_failed", 502)
                    can_install = releases.available(release, VERSION, os.environ.get("OFF_PROXY_PROGRAM_COMMIT"))
                    if release:
                        self.server.db.program_releases.replace_one({"_id": channel},
                            {"_id": channel, "release": release, "checked_at": time.time()}, upsert=True)
                    else:
                        self.server.db.program_releases.delete_one({"_id": channel})
                    self.send_json(200, {"release": release, "available": can_install, "installed": VERSION})
                else:
                    if set(values) != {"channel", "commit", "confirmed"} or values["confirmed"] is not True:
                        raise ValueError("Program update requires confirmation")
                    checked = self.server.db.program_releases.find_one({"_id": channel}) or {}
                    target = checked.get("release")
                    if (not target or target["commit"] != values["commit"]
                            or time.time() - checked["checked_at"] >= 3600):
                        raise security.Denied("program_release_changed", 409)
                    if not releases.available(target, VERSION, os.environ.get("OFF_PROXY_PROGRAM_COMMIT")):
                        raise security.Denied("program_already_current", 409)
                    job_target = {key: target[key] for key in ("channel", "commit", "version")}
                    self.send_json(202, {"queued": components.request(self.server.db, "program-update", target=job_target)})
            elif path in ("/ui/components/check", "/ui/components/update"):
                action = "check" if path.endswith("/check") else "update"
                invalid_update = action == "update" and (
                    set(values) - {"confirmed", "reinstall"} or values.get("confirmed") is not True
                    or ("reinstall" in values and values["reinstall"] is not True))
                if (action == "check" and values) or invalid_update:
                    raise ValueError("Explicit confirmation required")
                self.send_json(202, {"queued": components.request(self.server.db, action, reinstall=values.get("reinstall", False))})
            elif path == "/ui/settings":
                self.send_json(200, {"settings": control.save_settings(self.server.db, values)})
            elif path == "/ui/sync":
                if set(values) != {"confirmed"} or values.get("confirmed") is not True:
                    raise ValueError("Synchronization requires confirmation")
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


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    db = database() if mode != "api" else None
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
    Gunicorn().run()


if __name__ == "__main__":
    sys.exit(main())
