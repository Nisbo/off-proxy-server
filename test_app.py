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


@pytest.mark.parametrize("index", [b"openfoodfacts_products_101_150.json.gz\n", b"../../evil.gz\n", b""])
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
    server = app.Server(("127.0.0.1", 0), db, "x" * 32)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def get(url, auth=True):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + "x" * 32} if auth else {})
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
        "*", "!app.py", "!Dockerfile", "!requirements.txt"]






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
