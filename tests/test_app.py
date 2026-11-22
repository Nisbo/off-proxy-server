import gzip
import io
import json
import os
import threading
import urllib.error
import urllib.request
from unittest.mock import patch

import mongomock
import pytest
import yaml

import app
from .test_support import Server
import security

UI_COOKIES = {}


@pytest.fixture
def db():
    import uuid
    app.STOP.clear()
    if os.environ.get("MONGO_TEST_URI"):
        from pymongo import MongoClient
        client = MongoClient(os.environ["MONGO_TEST_URI"], serverSelectionTimeoutMS=5000)
        name = "off_proxy_test_" + uuid.uuid4().hex
        yield client[name]
        client.drop_database(name)
        client.close()
    else:
        yield mongomock.MongoClient().off_local


def product(code="4062139025398", version=10, **extra):
    return dict(code=code, last_modified_t=version,
                product_name_de="Pepsi Lemon Zero", brands="Pepsi", quantity="1.25l",
                product_name_en="Pepsi Lemon Zero", **extra)


def publish(db, kind="food", data=None):
    name = kind + "_" + "a" * 32
    app.save_product(db[name], data or product())
    db.state.update_one({"_id": kind}, {"$set": {
        "ready": True, "collection": name, "records": 1,
        "delta_cursor": 100, "full_epoch": 9999999999}}, upsert=True)


def response(data, modified="Wed, 18 Nov 2026 04:00:00 GMT"):
    result = io.BytesIO(data)
    result.headers = {"Last-Modified": modified}
    return result


def compressed(*records):
    return gzip.compress(b"\n".join(json.dumps(p).encode() for p in records) + b"\n")


def test_preserve_every_field_and_leading_zero(db):
    p = product("0123456789012", arbitrary={"nested": [1, "ä", None]})
    app.save_product(db.products, p)
    assert db.products.find_one({"_id": p["code"]})["product"] == p


@pytest.mark.parametrize("code", [
    "1054223232322323323232233232325635",
    "7777777777777777777777777777777777777777",
    "nonstandard-source-code",
])
def test_keep_nonstandard_export_codes_without_changing_original(db, code):
    p = product(code)
    app.save_product(db.products, p)
    assert db.products.find_one({"_id": code})["product"] == p


@pytest.mark.parametrize("code", [None, "", "  ", 123456789])
def test_missing_or_non_string_code_preserved_without_fabricated_ean(db, code):
    p = product(code)
    assert app.save_product(db.products, p) is False
    assert app.save_product(db.products, p) is False
    assert db.products.count_documents({}) == 1
    record = db.products.find_one()
    assert record["product"] == p
    assert record["indexed"] is False
    assert isinstance(record["_id"], dict)


def test_actual_export_empty_placeholder_does_not_abort_full_import(db):
    placeholder = {"code": "", "_id": ""}
    with patch.object(app, "open_url", return_value=response(compressed(product(), placeholder))):
        app.full_import(db, "beauty")
    state = db.state.find_one({"_id": "beauty"})
    assert state["ready"] and state["records"] == 2
    assert state["unindexed_records"] == 1
    assert db[state["collection"]].count_documents({}) == 2
    assert app.lookup(db, "4062139025398", "beauty", "en")[0] == 200


def test_delta_idempotent_old_does_not_overwrite_and_removed_field_cleared(db):
    p = product(temporary="gone")
    app.save_product(db.products, p)
    app.save_product(db.products, product(version=11))
    app.save_product(db.products, p)
    app.save_product(db.products, product(version=11))
    assert db.products.count_documents({}) == 1
    assert db.products.find_one()["product"] == product(version=11)


@pytest.mark.parametrize("kind", list(app.PROJECTS))
def test_lookup_all_four_types(db, kind):
    publish(db, kind)
    status, payload = app.lookup(db, "4062139025398", "all", "de")
    assert status == 200
    assert payload["product"]["product_type"] == kind


def test_fields_and_german_name(db):
    publish(db)
    status, payload = app.lookup(db, "4062139025398", "food", "de", ["product_name_de", "quantity"])
    assert status == 200
    assert payload["product"] == {"product_name_de": "Pepsi Lemon Zero", "quantity": "1.25l"}


def test_incomplete_database_does_not_claim_not_found(db):
    publish(db)
    assert app.lookup(db, "0000000000000", "all", "en")[0] == 503
    for kind in app.PROJECTS:
        publish(db, kind)
    status, payload = app.lookup(db, "0000000000000", "all", "en")
    assert status == 404
    assert payload["result"]["id"] == "product_not_found"


def test_image_urls_and_existing_url_preserved(db):
    p = product(lc="de", images={"front_de": {"rev": "7"}})
    app.image_fields(p, "food", "en")
    assert p["image_front_thumb_url"].endswith("406/213/902/5398/front_de.7.100.jpg")
    assert p["image_url"].endswith(".400.jpg")
    p["image_front_thumb_url"] = "https://existing.test/image.jpg"
    app.image_fields(p, "food", "de")
    assert p["image_front_thumb_url"] == "https://existing.test/image.jpg"


@pytest.mark.parametrize("kind", list(app.PROJECTS))
@pytest.mark.parametrize("language", ["de", "en"])
def test_nested_dump_images_use_available_language_and_preserve_source(db, kind, language):
    # Real 5000159384209 dump shape: the selected front image is Spanish only.
    images = {"selected": {"front": {"es": {"imgid": "6", "rev": "28"}},
                            "ingredients": {"es": {"imgid": "4", "rev": "32"}}},
              "uploaded": {"6": {"sizes": {"100": {"h": 65, "w": 100}}}}}
    p = product(code="5000159384209", lc="de", lang="de", images=images)
    publish(db, kind, p)
    original = db[kind + "_" + "a" * 32].find_one({"_id": p["code"]})
    status, payload = app.lookup(db, p["code"], kind, language,
                                 ["image_front_thumb_url", "image_front_url", "image_ingredients_small_url"])
    root = f"https://images.{app.PROJECTS[kind]}.org/images/products/500/015/938/4209/"
    assert status == 200
    assert payload["product"]["image_front_thumb_url"] == root + "front_es.28.100.jpg"
    assert payload["product"]["image_front_url"] == root + "front_es.28.400.jpg"
    assert payload["product"]["image_ingredients_small_url"] == root + "ingredients_es.32.200.jpg"
    assert db[kind + "_" + "a" * 32].find_one({"_id": p["code"]}) == original


@pytest.mark.parametrize("nested", [False, True])
def test_image_language_priority_skips_bad_metadata_and_keeps_existing_urls(nested):
    selected = {"de": {"rev": "8"}, "fr": {"rev": "7"}, "en": {"rev": "6"}}
    def data():
        return {"selected": {"front": selected}} if nested else {
            f"front_{language}": info for language, info in selected.items()}
    p = product(lc="fr", lang="en", images=data())
    app.image_fields(p, "food", "de")
    assert p["image_front_thumb_url"].endswith("front_de.8.100.jpg")
    selected["de"]["rev"] = "../bad"
    p = product(lc="fr", lang="en", images=data())
    app.image_fields(p, "food", "de")
    assert p["image_front_thumb_url"].endswith("front_fr.7.100.jpg")
    p["image_front_thumb_url"] = "https://images.openfoodfacts.org/existing.jpg"
    app.image_fields(p, "food", "en")
    assert p["image_front_thumb_url"] == "https://images.openfoodfacts.org/existing.jpg"


def test_only_uploaded_images_do_not_invent_a_front_selection():
    p = product(images={"uploaded": {"1": {"rev": "7"}}})
    app.image_fields(p, "food", "de")
    assert "image_front_thumb_url" not in p


def test_nested_image_paths_and_revisions_are_not_taken_from_untrusted_values():
    p = product(images={"selected": {"front": {"../../wrong": {"rev": "1"},
        "de": {"rev": "../../wrong"}, "es": {"rev": 28}}}})
    app.image_fields(p, "food", "de")
    assert p["image_front_thumb_url"].endswith("front_es.28.100.jpg")


@pytest.mark.parametrize("deleted,kind", [(True, "food"), (False, "beauty")])
def test_deleted_or_moved_records_not_returned(db, deleted, kind):
    publish(db, data=product(deleted=deleted, product_type=kind))
    assert app.lookup(db, "4062139025398", "food", "de")[0] == 404


def test_full_import_publishes_new_generation(db):
    publish(db)
    with patch.object(app, "open_url", return_value=response(compressed(product(version=20)))):
        app.full_import(db, "food")
    state = db.state.find_one({"_id": "food"})
    assert state["ready"]
    assert db[state["collection"]].find_one()["version"] == 20
    assert "food_" + "a" * 32 not in db.list_collection_names()


@pytest.mark.parametrize("body", [b"invalid", gzip.compress(b""), compressed(product())[:-7]])
def test_failed_full_import_preserves_old_generation(db, body):
    publish(db)
    before = db.state.find_one({"_id": "food"})["collection"]
    with patch.object(app, "open_url", return_value=response(body)), pytest.raises(Exception):
        app.full_import(db, "food")
    assert db.state.find_one({"_id": "food"})["collection"] == before
    assert app.lookup(db, "4062139025398", "food", "de")[0] == 200


def test_snapshot_shrink_guard_and_unpublished_orphan_cleanup(db):
    publish(db)
    db.state.update_one({"_id": "food"}, {"$set": {"records": 100}})
    orphan = "food_" + "b" * 32
    db[orphan].insert_one({"old": True})
    with patch.object(app, "open_url", return_value=response(compressed(product()))), pytest.raises(ValueError):
        app.full_import(db, "food")
    assert orphan not in db.list_collection_names()
    assert len([n for n in db.list_collection_names() if n.startswith("food_")]) == 1


def test_deltas_processed_chronologically(db):
    publish(db)
    index = b"openfoodfacts_products_150_200.json.gz\nopenfoodfacts_products_100_150.json.gz\n"
    with patch.object(app, "open_url", side_effect=[response(index), response(compressed(product(version=15))),
                                                   response(compressed(product(version=20)))]):
        app.apply_deltas(db, "food")
    state = db.state.find_one({"_id": "food"})
    assert state["delta_cursor"] == 200
    assert db[state["collection"]].find_one()["version"] == 20


def test_broken_delta_does_not_advance_cursor_and_can_retry(db):
    publish(db)
    index = b"openfoodfacts_products_100_150.json.gz\n"
    with patch.object(app, "open_url", side_effect=[response(index), response(compressed(product(version=15))[:-6])]), pytest.raises(EOFError):
        app.apply_deltas(db, "food")
    assert db.state.find_one({"_id": "food"})["delta_cursor"] == 100
    with patch.object(app, "open_url", side_effect=[response(index), response(compressed(product(version=15)))]):
        app.apply_deltas(db, "food")
    assert db.state.find_one({"_id": "food"})["delta_cursor"] == 150


@pytest.mark.parametrize("index", [b"../../evil.gz\n", b""])
def test_delta_gaps_and_invalid_index_rejected(db, index):
    publish(db)
    with patch.object(app, "open_url", return_value=response(index)), pytest.raises(ValueError):
        app.apply_deltas(db, "food")


def test_one_source_failure_does_not_block_others(db):
    calls = []
    def sync(db, kind):
        calls.append(kind)
        if kind == "petfood":
            raise TimeoutError("source unreachable")
    with patch.object(app, "sync_one", side_effect=sync):
        assert app.sync_loop(db, once=True) == 1
    assert calls == list(app.ORDER)
    assert db.state.find_one({"_id": "petfood"})["phase"] == "error"


@pytest.fixture
def http(db):
    server = Server(("127.0.0.1", 0), db, "x" * 32)
    server.security.set_password("test-admin-password")
    raw = server.security.login("test-admin-password", "fixture")
    UI_COOKIES[f"http://127.0.0.1:{server.server_port}"] = f"{security.COOKIE}={raw}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    UI_COOKIES.pop(f"http://127.0.0.1:{server.server_port}", None)
    server.shutdown()
    server.server_close()
    thread.join()


def get(url, auth=True):
    headers = {"Authorization": "Bearer " + "x" * 32} if auth else {}
    base = urllib.parse.urlsplit(url)
    if base.path.startswith('/ui/'):
        headers['Cookie'] = UI_COOKIES.get(f'{base.scheme}://{base.netloc}', '')
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_http_auth_and_health(http):
    assert get(http + "/health", auth=False)[0] == 401
    status, data = get(http + "/health")
    assert status == 200 and data["all_ready"] is False
    assert len(data["datasets"]) == 4


@pytest.mark.parametrize("code,name,brand,quantity", [
    ("8715700117140", "Zero Tomaten Ketchup", "Heinz", "425g"),
    ("4062139025398", "Pepsi Lemon Zero", "Pepsi", "1.25l"),
])
def test_actual_list_manager_request(http, db, code, name, brand, quantity):
    p = product(code)
    p.update(product_name_de=name, brands=brand, quantity=quantity)
    publish(db, data=p)
    status, data = get(http + f"/api/v3/product/{code}.json?product_type=all&fields=product_name_de,brands,quantity")
    assert status == 200
    assert data["product"] == dict(product_name_de=name, brands=brand, quantity=quantity)


@pytest.mark.parametrize("code", [
    "1054223232322323323232233232325635",
    "7777777777777777777777777777777777777777",
])
def test_lookup_actual_export_codes_longer_than_32_characters(http, db, code):
    publish(db, data=product(code))
    status, payload = get(http + f"/api/v3/product/{code}.json?product_type=all")
    assert status == 200
    assert payload["product"]["code"] == code


def test_build_context_excludes_database_and_secrets():
    from pathlib import Path
    assert Path(".dockerignore").read_text().splitlines() == [
        "*", "!app.py", "!dashboard.py", "!control.py", "!security.py", "!components.py", "!releases.py", "!Dockerfile", "!requirements.txt", "!web/", "!web/**"]






@pytest.mark.parametrize("path", ["/api/v3/product/123.json?product_type=bad",
                                 "/api/v3/product/123.json?fields=x.y",
                                 "/api/v3/product/123.json?lc=../../",
                                 "/api/v3/product/not-a-code.json",
                                 "/api/v2/search"])
def test_invalid_or_unsupported_requests(http, path):
    assert get(http + path)[0] in (400, 404)


def test_compose_only_api_port_is_published():
    with open("compose.yaml") as file:
        compose = yaml.safe_load(file)
    assert "ports" not in compose["services"]["mongo"]
    assert "127.0.0.1" in compose["services"]["api"]["ports"][0]
    assert all(s["memswap_limit"] == s["mem_limit"] for s in compose["services"].values())


@pytest.mark.parametrize("path,content_type", [
    ("/", "text/html"), ("/assets/dashboard.js", "text/javascript"),
    ("/assets/dashboard.css", "text/css"),
])
def test_dashboard_assets_public_but_contain_no_api_key(http, path, content_type):
    with urllib.request.urlopen(http + path) as response:
        body = response.read().decode()
        assert response.status == 200
        assert content_type in response.headers["Content-Type"]
        assert response.headers["Cache-Control"] == "no-store"
        assert "x" * 32 not in body


def test_authenticated_dashboard_lookup_and_existing_api_remains_protected(http, db):
    publish(db, "beauty", product("0000527000057", internal_sensitive="must not be exposed"))
    status, data = get(http + "/ui/lookup?ean=0000527000057", auth=False)
    assert status == 200 and data["product"]["product_type"] == "beauty"
    assert data["product"]["code"] == "0000527000057"
    assert "internal_sensitive" not in data["product"]
    assert data["elapsed_ms"] >= 0
    assert get(http + "/health", auth=False)[0] == 401
    assert get(http + "/api/v3/product/0000527000057.json?product_type=all", auth=False)[0] == 401
    assert get(http + "/api/v3/product/0000527000057.json?product_type=all")[0] == 200


@pytest.mark.parametrize("query", [
    "ean=123&fields=internal_sensitive", "ean=123&url=http://localhost",
    "ean=%3Cscript%3E", "ean=123&lc=xx", "ean=123&product_type=unknown",
])
def test_dashboard_lookup_rejects_unsupported_requests(http, query):
    assert get(http + "/ui/lookup?" + query, auth=False)[0] == 400


def test_authenticated_status_redacts_internal_state_and_counts_published_records(http, db):
    publish(db)
    db.state.update_one({"_id": "food"}, {"$set": {"API_TOKEN": "private-value", "internal_path": "/private/path"}})
    db.scheduler.insert_one({"_id": "sync", "phase": "waiting", "next_check_epoch": 20000, "full_days": 14})
    status, data = get(http + "/ui/status", auth=False)
    assert status == 200
    assert data["statistics"]["records"] == 1
    assert 0 < data["server_started_epoch"] <= data["server_epoch"]
    assert get(http + "/ui/status", auth=False)[1]["server_started_epoch"] == data["server_started_epoch"]
    assert data["datasets"]["food"]["next_full_epoch"] is None
    assert data["settings"]["full_import_policy"] == "confirm"
    assert data["datasets"]["beauty"]["ready"] is False
    assert data["scheduler"]["next_check_epoch"] == 20000
    text = json.dumps(data)
    assert "private-value" not in text and "internal_path" not in text
    assert "collection" not in data["datasets"]["food"]


def test_dashboard_statistics_are_cached_without_scanning_products(db):
    from dashboard import Dashboard
    publish(db)
    dashboard = Dashboard(db, app.VERSION, app.PROJECTS)
    first = dashboard.snapshot()
    app.save_product(db[db.state.find_one({"_id": "food"})["collection"]], product("8715700117140"))
    assert dashboard.snapshot()["statistics"] == first["statistics"]
    dashboard._sampled = -100000
    assert dashboard.snapshot()["statistics"]["records"] == 2


def test_progress_counts_compressed_bytes_and_keeps_no_false_completion(db):
    updates = []
    body = compressed(product(), {"code": "", "_id": ""})
    data = response(body)
    data.headers["Content-Length"] = str(len(body))
    count, unindexed = app.import_stream(data, db.products, "test", updates.append)
    assert (count, unindexed) == (2, 1)
    assert updates[0]["records"] == 0 and not updates[0]["finished"]
    assert updates[-1]["records"] == 2 and updates[-1]["finished"]
    assert updates[-1]["downloaded_bytes"] == len(body)
    assert updates[-1]["total_bytes"] == len(body)
    updates.clear()
    with pytest.raises(EOFError):
        app.import_stream(response(body[:-6]), db.products, "test", updates.append)
    assert not any(update["finished"] for update in updates)


def test_published_full_import_retains_progress_for_gui(db):
    with patch.object(app, "open_url", return_value=response(compressed(product()))):
        app.full_import(db, "food")
    state = db.state.find_one({"_id": "food"})
    assert state["progress"]["mode"] == "full"
    assert state["progress"]["records"] == 1 and state["progress"]["finished"]
    assert db.scheduler.find_one({"_id": "sync"})["heartbeat_epoch"] > 0


def test_next_check_is_recorded_from_actual_cycle_end_and_cleared_on_stop(db):
    import time
    before = time.time()
    captured = []
    def wait(seconds):
        captured.append(db.scheduler.find_one({"_id": "sync"}))
        assert 0 < seconds <= 2
        app.STOP.set()
    with patch.object(app, "sync_one"), patch.object(app.STOP, "wait", side_effect=wait), patch.dict(os.environ, SYNC_SECONDS="600", FULL_DAYS="14"):
        app.sync_loop(db)
    assert captured[0]["phase"] == "waiting"
    assert before + 600 <= captured[0]["next_check_epoch"] <= time.time() + 600
    stopped = db.scheduler.find_one({"_id": "sync"})
    assert stopped["phase"] == "stopped" and stopped["next_check_epoch"] is None


def test_scheduler_detects_overdue_worker_but_not_normal_wait(db):
    import time
    from dashboard import Dashboard
    now = time.time()
    dashboard = Dashboard(db, app.VERSION, app.PROJECTS)
    db.scheduler.insert_one({"_id": "sync", "phase": "waiting", "heartbeat_epoch": now-3600, "next_check_epoch": now+30})
    assert dashboard.snapshot()["scheduler"]["stale"] is False
    db.scheduler.update_one({"_id": "sync"}, {"$set": {"phase": "running", "heartbeat_epoch": now-121}})
    assert dashboard.snapshot()["scheduler"]["stale"] is True


def test_gui_readmes_begin_with_development_warning():
    from pathlib import Path
    assert Path("README.md").read_text().startswith("> **Warning:")
    assert Path("README.de.md").read_text().startswith("> **Achtung:")


def delta_index(*intervals):
    return ''.join(f'openfoodfacts_products_{a}_{b}.json.gz\n' for a, b in intervals).encode()


def test_defaults_do_not_reimport_old_datasets_or_honor_legacy_env(db):
    import control
    publish(db)
    db.state.update_one({'_id': 'food'}, {'$set': {'full_epoch': 1}})
    with patch.dict(os.environ, FULL_DAYS='1'), patch.object(app, 'full_import') as full, patch.object(app, 'apply_deltas') as delta:
        app.sync_one(db, 'food')
    full.assert_not_called()
    delta.assert_called_once()
    assert control.settings(db) == control.DEFAULTS


def test_initial_full_import_requires_confirmation_and_runs_once(db):
    import control
    with patch.object(app, 'full_import') as full:
        app.sync_one(db, 'food')
    full.assert_not_called()
    assert db.state.find_one({'_id': 'food'})['phase'] == 'needs_full_import'
    assert control.request(db, 'full:food') is True
    assert control.request(db, 'full:food') is False
    with patch.object(app, 'full_import', side_effect=lambda db, kind: publish(db, kind)) as full, patch.object(app, 'apply_deltas'):
        app.sync_one(db, 'food')
        app.sync_one(db, 'food')
    assert full.call_count == 1
    assert db.requests.find_one({'_id': 'full:food'})['status'] == 'done'


def test_failed_confirmed_full_import_needs_another_confirmation(db):
    import control
    publish(db)
    control.request(db, 'full:food')
    with patch.object(app, 'full_import', side_effect=TimeoutError('unreachable')), pytest.raises(TimeoutError):
        app.sync_one(db, 'food')
    with patch.object(app, 'full_import') as full, patch.object(app, 'apply_deltas'):
        app.sync_one(db, 'food')
    full.assert_not_called()
    assert db.requests.find_one({'_id': 'full:food'})['status'] == 'failed'
    assert app.lookup(db, '4062139025398', 'food', 'de')[0] == 200


def test_gap_continues_with_newer_deltas_and_later_repairs_missing_file(db):
    publish(db)
    with patch.object(app, 'open_url', side_effect=[response(delta_index((100, 150), (200, 250))), response(compressed(product(version=15))), response(compressed(product(version=25)))]):
        app.sync_one(db, 'food')
    state = db.state.find_one({'_id': 'food'})
    assert state['delta_cursor'] == 250 and state['delta_gaps'] == [[150, 200]]
    assert state['phase'] == 'partial' and state['full_reasons'] == ['gap']
    assert state['ready'] is True
    # A delayed historical file fills coverage; older product revisions do not overwrite newer ones.
    with patch.object(app, 'open_url', side_effect=[response(delta_index((100, 150), (150, 200), (200, 250))), response(compressed(product(version=20)))]):
        app.sync_one(db, 'food')
    state = db.state.find_one({'_id': 'food'})
    assert state['delta_gaps'] == [] and state['phase'] == 'ready' and state['full_reasons'] == []
    assert db[state['collection']].find_one({'_id': '4062139025398'})['version'] == 25


def test_expired_delta_window_is_visible_and_continues(db):
    publish(db)
    with patch.object(app, 'open_url', side_effect=[response(delta_index((200, 250))), response(compressed(product(version=25)))]):
        app.apply_deltas(db, 'food')
    state = db.state.find_one({'_id': 'food'})
    assert state['delta_gaps'] == [[100, 200]] and state['delta_cursor'] == 250


def test_pause_policy_stops_at_gap_but_allows_historical_repair(db):
    import control
    publish(db)
    control.save_settings(db, {'delta_gap_policy': 'pause'})
    with patch.object(app, 'open_url', side_effect=[response(delta_index((100, 150), (200, 250))), response(compressed(product(version=15)))]) as opened:
        app.apply_deltas(db, 'food')
    assert opened.call_count == 2
    state = db.state.find_one({'_id': 'food'})
    assert state['delta_gaps'] == [[150, 200]] and state['delta_cursor'] == 150 and state['phase'] == 'gap_paused'
    with patch.object(app, 'open_url', side_effect=[response(delta_index((150, 200), (200, 250))), response(compressed(product(version=20))), response(compressed(product(version=25)))]):
        app.apply_deltas(db, 'food')
    assert db.state.find_one({'_id': 'food'})['delta_gaps'] == []


@pytest.mark.parametrize('code', [404, 410])
def test_listed_but_missing_single_delta_is_recorded_as_gap(db, code):
    publish(db)
    error = urllib.error.HTTPError('https://example.invalid/delta', code, 'missing', {}, None)
    with patch.object(app, 'open_url', side_effect=[response(delta_index((100, 150), (150, 200), (200, 250))), response(compressed(product(version=15))), error, response(compressed(product(version=25)))]):
        app.apply_deltas(db, 'food')
    state = db.state.find_one({'_id': 'food'})
    assert state['delta_gaps'] == [[150, 200]] and state['delta_cursor'] == 250


@pytest.mark.parametrize('where', ['index', 'file'])
@pytest.mark.parametrize('code', [429, 500, 504])
def test_temporary_http_failure_does_not_invent_gap_or_advance_cursor(db, where, code):
    publish(db)
    error = urllib.error.HTTPError('https://example.invalid/delta', code, 'temporary', {}, None)
    responses = [error] if where == 'index' else [response(delta_index((100, 150))), error]
    with patch.object(app, 'open_url', side_effect=responses), pytest.raises(urllib.error.HTTPError):
        app.apply_deltas(db, 'food')
    state = db.state.find_one({'_id': 'food'})
    assert state['delta_cursor'] == 100 and not state.get('delta_gaps')
    # The next successful check downloads all missed intervals, regardless of days offline.
    with patch.object(app, 'open_url', side_effect=[response(delta_index((100, 150), (150, 200))), response(compressed(product(version=15))), response(compressed(product(version=20)))]):
        app.apply_deltas(db, 'food')
    assert db.state.find_one({'_id': 'food'})['delta_cursor'] == 200


def test_full_import_closes_persistent_gaps(db):
    publish(db)
    db.state.update_one({'_id': 'food'}, {'$set': {'delta_gaps': [[100, 150]]}})
    with patch.object(app, 'open_url', return_value=response(compressed(product()))):
        app.full_import(db, 'food')
    assert db.state.find_one({'_id': 'food'})['delta_gaps'] == []


def test_optional_interval_only_requests_confirmation(db):
    import control
    publish(db)
    control.save_settings(db, {'full_interval_days': 14})
    db.state.update_one({'_id': 'food'}, {'$set': {'full_epoch': 1}})
    with patch.object(app, 'full_import') as full, patch.object(app, 'apply_deltas'):
        app.sync_one(db, 'food')
    full.assert_not_called()
    assert db.state.find_one({'_id': 'food'})['full_reasons'] == ['scheduled']
    assert app.Dashboard(db, app.VERSION, app.PROJECTS).snapshot()['datasets']['food']['next_full_epoch'] == 1+14*86400


@pytest.mark.parametrize('values', [{'full_import_policy': 'automatic'}, {'full_interval_days': True}, {'full_interval_days': -1}, {'full_interval_days': 0.5}, {'full_interval_days': 3651}, {'delta_gap_policy': 'bad'}, {'API_TOKEN': 'bad'}])
def test_settings_reject_invalid_or_unconfirmed_values(db, values):
    import control
    with pytest.raises(ValueError):
        control.save_settings(db, values)
    assert control.settings(db) == control.DEFAULTS


def test_automatic_full_imports_are_explicit_opt_in(db):
    import control
    control.save_settings(db, {'full_import_policy': 'automatic', 'confirm_automatic_full_imports': True})
    with patch.object(app, 'full_import', side_effect=lambda db, kind: publish(db, kind)) as full, patch.object(app, 'apply_deltas'):
        app.sync_one(db, 'food')
    full.assert_called_once()


def post_ui(base, path, values, nonce=None, origin=None):
    headers = {'Content-Type': 'application/json', 'Cookie': UI_COOKIES.get(base, '')}
    if nonce:
        headers['X-Off-Proxy-Control'] = nonce
    if origin:
        headers['Origin'] = origin
    request = urllib.request.Request(base + path, data=json.dumps(values).encode(), headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_ui_control_requires_nonce_and_full_confirmation(http, db):
    nonce = get(http + '/ui/status', auth=False)[1]['control_nonce']
    assert post_ui(http, '/ui/sync', {})[0] == 403
    assert post_ui(http, '/ui/sync', {}, nonce, 'https://unrelated.invalid')[0] == 403
    for values in ({}, {'confirmed': False}, {'confirmed': 1}, {'confirmed': True, 'extra': True}):
        assert post_ui(http, '/ui/sync', values, nonce)[0] == 400
    assert post_ui(http, '/ui/sync', {'confirmed': True}, nonce)[1]['queued'] is True
    assert post_ui(http, '/ui/sync', {'confirmed': True}, nonce)[1]['queued'] is False
    assert post_ui(http, '/ui/full-import', {'kind': 'food'}, nonce)[0] == 400
    assert post_ui(http, '/ui/full-import', {'kind': 'food', 'confirmed': False}, nonce)[0] == 400
    assert post_ui(http, '/ui/full-import', {'kind': 'food', 'confirmed': True}, nonce)[0] == 202
    assert db.requests.count_documents({'status': 'pending'}) == 2
    assert not any(name.startswith(('food_', 'beauty_', 'petfood_', 'product_')) for name in db.list_collection_names())
    assert get(http + '/api/v3/product/123.json', auth=False)[0] == 401


def test_ui_settings_are_persistent_and_do_not_trigger_import(http, db):
    import control
    nonce = get(http + '/ui/status', auth=False)[1]['control_nonce']
    assert post_ui(http, '/ui/settings', {'full_interval_days': 45}, nonce)[0] == 200
    assert control.settings(db)['full_interval_days'] == 45
    assert db.requests.count_documents({}) == 0


def test_ui_refresh_is_read_only(http, db):
    for _ in range(3):
        assert get(http + '/ui/status', auth=False)[0] == 200
    assert db.requests.count_documents({}) == db.settings.count_documents({}) == 0


def test_worker_consumes_manual_request_without_second_importer(db):
    import control
    calls = []
    def sync(db, kind):
        calls.append(kind)
        assert control.request(db, 'sync') is False  # Coalesced while active.
    waits = []
    def wait(seconds):
        waits.append(seconds)
        if len(waits) == 1:
            control.request(db, 'sync')
        else:
            app.STOP.set()
    with patch.object(app, 'sync_one', side_effect=sync), patch.object(app.STOP, 'wait', side_effect=wait):
        app.sync_loop(db)
    assert calls == list(app.ORDER) * 2


@pytest.mark.parametrize("window, expected", [
    ((50, 100), "unchanged"), ((100, 150), "updated"), ((150, 200), "updated_incomplete"),
])
def test_sync_reports_real_delta_outcome(db, window, expected):
    import control
    from dashboard import Dashboard
    for kind in app.PROJECTS:
        publish(db, kind)
    assert control.request(db, "sync")
    start, end = window

    def download(url):
        kind = next(kind for kind in app.PROJECTS if url.startswith(app.delta_url(kind)))
        low, high = window if kind == "food" else (50, 100)
        if url.endswith("index.txt"):
            return response(f"{app.PROJECTS[kind]}_products_{low}_{high}.json.gz".encode())
        assert kind == "food" and url.endswith(f"_{start}_{end}.json.gz")
        return response(compressed(product(version=end)))

    with patch.object(app, "open_url", side_effect=download):
        assert app.sync_loop(db, once=True) == 0
    job = Dashboard(db, app.VERSION, app.PROJECTS).snapshot()["requests"]["sync"]
    assert job["status"] == "done" and job["outcome"] == expected
    assert job["started_epoch"] <= job["finished_epoch"]
    assert control.request(db, "sync")
    job = Dashboard(db, app.VERSION, app.PROJECTS).snapshot()["requests"]["sync"]
    assert job == {"status": "pending", "error": None}


def test_sync_does_not_report_no_changes_when_initial_import_is_waiting(db):
    from dashboard import Dashboard
    assert app.sync_loop(db, once=True) == 0
    assert Dashboard(db, app.VERSION, app.PROJECTS).snapshot()["requests"]["sync"]["outcome"] == "incomplete"


def test_restart_does_not_replay_interrupted_full_approval(db):
    db.requests.insert_one({'_id': 'full:food', 'status': 'running'})
    with patch.object(app, 'full_import') as full:
        app.sync_loop(db, once=True)
    full.assert_not_called()
    assert db.requests.find_one({'_id': 'full:food'})['status'] == 'failed'


def test_range_merge_and_partial_repair():
    import control
    assert control.merge_ranges([[150, 200], [100, 160], [300, 400]]) == [[100, 200], [300, 400]]
    assert control.cover_range([[100, 200]], 130, 170) == [[100, 130], [170, 200]]


def test_full_request_during_automatic_import_is_coalesced(http, db):
    nonce = get(http + '/ui/status', auth=False)[1]['control_nonce']
    db.state.insert_one({'_id': 'food', 'phase': 'full_import'})
    assert post_ui(http, '/ui/full-import', {'kind': 'food', 'confirmed': True}, nonce)[1]['queued'] is False
    assert db.requests.count_documents({}) == 0


def test_covering_delta_does_not_create_a_false_gap(db):
    publish(db)
    with patch.object(app, 'open_url', side_effect=[response(delta_index((50, 200), (150, 250))), response(compressed(product(version=20))), response(compressed(product(version=25)))]):
        app.apply_deltas(db, 'food')
    state = db.state.find_one({'_id': 'food'})
    assert state['delta_cursor'] == 250 and state['delta_gaps'] == []


def test_timeout_retries_without_inventing_gap(db):
    publish(db)
    with patch.object(app, 'open_url', side_effect=TimeoutError('offline')), pytest.raises(TimeoutError):
        app.apply_deltas(db, 'food')
    assert db.state.find_one({'_id': 'food'})['delta_cursor'] == 100
    assert not db.state.find_one({'_id': 'food'}).get('delta_gaps')


def test_gap_stays_visible_after_later_checks(db):
    publish(db)
    db.state.update_one({'_id': 'food'}, {'$set': {'delta_cursor': 250, 'delta_gaps': [[150, 200]]}})
    with patch.object(app, 'open_url', return_value=response(delta_index((200, 250)))):
        app.sync_one(db, 'food')
    assert db.state.find_one({'_id': 'food'})['delta_gaps'] == [[150, 200]]
    dashboard = app.Dashboard(db, app.VERSION, app.PROJECTS).snapshot()
    assert dashboard['datasets']['food']['ready'] is True
    assert dashboard['datasets']['food']['phase'] == 'partial'
    assert dashboard['datasets']['food']['delta_gaps'] == [[150, 200]]
    assert dashboard['all_synced'] is False


def test_interrupted_full_import_clears_busy_phase_for_new_confirmation(db):
    import control
    publish(db)
    control.request(db, 'full:food')
    def stop(*_):
        app.STOP.set()
        raise InterruptedError('stop requested')
    with patch.object(app, 'open_url', side_effect=stop):
        app.sync_loop(db, once=True)
    state = db.state.find_one({'_id': 'food'})
    assert state['phase'] == 'error' and state['ready'] is True
    assert db.requests.find_one({'_id': 'full:food'})['status'] == 'failed'
    assert control.request(db, 'full:food') is True


def test_full_import_keeps_old_products_readable_while_new_copy_is_written(db):
    publish(db)
    old = db.state.find_one({'_id': 'food'})['collection']
    def import_new(response, collection, label, progress):
        assert collection.name != old
        assert db.state.find_one({'_id': 'food'})['collection'] == old
        app.save_product(collection, product(version=20))
        # Even after the new record is written, API reads still use the published copy.
        assert app.lookup(db, '4062139025398', 'food', 'de')[1]['product']['last_modified_t'] == 10
        assert old in db.list_collection_names()
        return 1, 0
    with patch.object(app, 'open_url', return_value=response(b'')), patch.object(app, 'import_stream', side_effect=import_new):
        app.full_import(db, 'food')
    assert app.lookup(db, '4062139025398', 'food', 'de')[1]['product']['last_modified_t'] == 20
    assert old not in db.list_collection_names()


@pytest.mark.parametrize('committed', [False, True])
def test_lost_publish_acknowledgement_never_deletes_either_possible_snapshot(db, committed):
    from pymongo.errors import AutoReconnect
    publish(db)
    real_state = db.state
    class State:
        def update_one(self, query, update, **kwargs):
            if 'collection' in update.get('$set', {}):
                if committed:
                    real_state.update_one(query, update, **kwargs)
                raise AutoReconnect('acknowledgement lost; commit outcome unknown')
            return real_state.update_one(query, update, **kwargs)
        def find_one(self, query):
            return real_state.find_one(query)
    class Database:
        state = State()
        def __getattr__(self, name):
            return getattr(db, name)
        def __getitem__(self, name):
            return db[name]
    with patch.object(app, 'open_url', return_value=response(compressed(product(version=20)))), pytest.raises(AutoReconnect):
        app.full_import(Database(), 'food')
    assert len([n for n in db.list_collection_names() if n.startswith('food_')]) == 2
    state = real_state.find_one({'_id':'food'})
    assert state['collection'] in db.list_collection_names()
    assert app.lookup(db, '4062139025398', 'food', 'de')[1]['product']['last_modified_t'] == (20 if committed else 10)


def test_retirement_failure_does_not_turn_successful_full_import_into_failure(db):
    from pymongo.errors import AutoReconnect
    publish(db)
    old = db.state.find_one({'_id':'food'})['collection']
    class Database:
        def __getattr__(self, name):
            return getattr(db, name)
        def __getitem__(self, name):
            return db[name]
        def drop_collection(self, name):
            if name == old:
                raise AutoReconnect('cleanup unavailable')
            db.drop_collection(name)
    with patch.object(app, 'open_url', return_value=response(compressed(product(version=20)))):
        app.full_import(Database(), 'food')
    assert app.lookup(db, '4062139025398', 'food', 'de')[1]['product']['last_modified_t'] == 20
    assert old in db.list_collection_names()


def test_delta_failure_after_full_import_does_not_requeue_or_fail_the_full_request(db):
    import control
    control.request(db, 'full:food')
    with patch.object(app, 'full_import', side_effect=lambda db, kind: publish(db, kind)), patch.object(app, 'apply_deltas', side_effect=TimeoutError('delta source offline')):
        with pytest.raises(TimeoutError):
            app.sync_one(db, 'food')
    assert db.requests.find_one({'_id':'full:food'})['status'] == 'done'
    assert db.state.find_one({'_id':'food'})['ready'] is True


def test_update_gate_and_cycle_start_cannot_both_win(db):
    import control
    now = app.time.time()
    db.scheduler.insert_one({'_id':'sync','phase':'waiting','maintenance_until':now+600})
    assert control.begin_cycle(db, {'active_kind':None}) is None
    assert db.scheduler.find_one({'_id':'sync'})['phase'] == 'waiting'
    with patch('control.time.time', return_value=now+601):
        assert control.begin_cycle(db, {'active_kind':None})['phase'] == 'running'
    assert db.scheduler.update_one({'_id':'sync','phase':{'$ne':'running'}}, {'$set':{'maintenance_until':now+1200}}).matched_count == 0


def test_worker_waits_for_update_without_touching_products_or_requests(db):
    db.scheduler.insert_one({'_id':'sync','phase':'waiting','maintenance_until':app.time.time()+600})
    with patch.object(app, 'sync_one') as sync, patch.object(app.STOP, 'wait', side_effect=lambda _:app.STOP.set()):
        app.sync_loop(db)
    sync.assert_not_called()
    assert db.requests.count_documents({}) == 0


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://example.invalid/data.gz'])
def test_export_downloads_reject_non_https(url):
    with pytest.raises(ValueError, match='HTTPS'):
        app.open_url(url)
    with pytest.raises(ValueError, match='HTTPS'):
        app.HTTPSRedirects().redirect_request(None, None, 302, 'redirect', {}, url)


@pytest.mark.parametrize('query', ['product_type=food&product_type=all', 'lc=de&lc=en'])
def test_ambiguous_query_parameters_are_rejected(http, query):
    assert get(http+'/api/v3/product/123.json?'+query)[0] == 400
    assert get(http+'/ui/lookup?ean=123&'+query, auth=False)[0] == 400


def test_oversized_barcode_is_rejected_before_database_lookup(http):
    assert get(http+'/api/v3/product/'+('1'*257)+'.json')[0] == 400



def test_query_string_credentials_are_not_written_to_request_logs(http):
    with patch.object(app.LOG, 'info') as info:
        assert get(http+'/health?accidental_key=do-not-log-this-secret')[0] == 200
    assert 'do-not-log-this-secret' not in repr(info.call_args_list)


def test_wsgi_head_returns_headers_without_a_body(http):
    request = urllib.request.Request(http+'/', method='HEAD')
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        assert response.read() == b''
        assert int(response.headers['Content-Length']) > 0
        assert response.headers['X-Content-Type-Options'] == 'nosniff'


def test_wsgi_unsupported_method_cannot_trigger_control(http):
    request = urllib.request.Request(http+'/ui/sync', method='PUT', data=b'{}')
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)
    assert caught.value.code == 405


def test_large_bodies_are_rejected(http):
    request = urllib.request.Request(http+'/auth/login', data=b'x'*4097,
                                     headers={'Content-Type':'application/json'})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)
    assert caught.value.code == 413
    assert get(http+'/health')[0] == 200


def test_http_nested_image_metadata_is_resolved_before_fields_projection(db, http):
    publish(db, data=product(code="5000159384209", lc="de", images={
        "selected": {"front": {"es": {"imgid": "6", "rev": "28"}}},
        "uploaded": {"6": {"sizes": {"100": {"h": 65, "w": 100}}}},
    }))
    for language in ("de", "en"):
        status, payload = get(http + "/api/v3/product/5000159384209.json?"
                              f"product_type=all&lc={language}&fields=code,image_front_thumb_url")
        assert status == 200
        assert payload["product"] == {
            "code": "5000159384209",
            "image_front_thumb_url": "https://images.openfoodfacts.org/images/products/500/015/938/4209/front_es.28.100.jpg",
        }
