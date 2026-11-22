"""Persistent worker settings and coalesced requests shared with the local UI."""
import time

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

DEFAULTS = {"delta_gap_policy": "continue", "full_import_policy": "confirm", "full_interval_days": 0}


def settings(db):
    saved = db.settings.find_one({"_id": "sync"}) or {}
    return {key: saved.get(key, value) for key, value in DEFAULTS.items()}


def save_settings(db, values):
    if set(values) - {*DEFAULTS, "confirm_automatic_full_imports"}:
        raise ValueError("Unknown setting")
    updated = {**settings(db), **{k: v for k, v in values.items() if k in DEFAULTS}}
    days = updated["full_interval_days"]
    if (updated["delta_gap_policy"] not in ("continue", "pause")
            or updated["full_import_policy"] not in ("confirm", "automatic")
            or type(days) is not int or not 0 <= days <= 3650):
        raise ValueError("Invalid settings")
    if (updated["full_import_policy"] == "automatic" and settings(db)["full_import_policy"] != "automatic"
            and values.get("confirm_automatic_full_imports") is not True):
        raise ValueError("Automatic full imports require confirmation")
    db.settings.update_one({"_id": "sync"}, {"$set": updated}, upsert=True)
    return updated


def request(db, job):
    # A stable unique ID makes concurrent clicks/tabs coalesce in MongoDB.
    try:
        result = db.requests.update_one({"_id": job, "status": {"$nin": ["pending", "running"]}},
            {"$set": {"status": "pending", "requested_epoch": time.time(), "error": None},
             "$unset": {"started_epoch": "", "finished_epoch": "", "outcome": ""}}, upsert=True)
        return bool(result.modified_count or result.upserted_id)
    except DuplicateKeyError:
        return False


def claim(db, job):
    return db.requests.find_one_and_update({"_id": job, "status": "pending"},
        {"$set": {"status": "running", "started_epoch": time.time()}}, return_document=ReturnDocument.AFTER)


def finish(db, job, error=None, *, outcome=None):
    values = {"status": "failed" if error else "done", "finished_epoch": time.time(), "error": error}
    if outcome is not None:
        values["outcome"] = outcome
    db.requests.update_one({"_id": job, "status": "running"}, {"$set": values})


def merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def cover_range(ranges, start, end):
    remaining = []
    for low, high in ranges:
        if end <= low or start >= high:
            remaining.append([low, high])
        else:
            if low < start:
                remaining.append([low, start])
            if end < high:
                remaining.append([end, high])
    return remaining


def begin_cycle(db, values):
    """Claim the cycle atomically against the updater's temporary maintenance gate."""
    db.scheduler.update_one({'_id': 'sync'}, {'$setOnInsert': {'phase': 'waiting'}}, upsert=True)
    now = time.time()
    return db.scheduler.find_one_and_update({'_id': 'sync', '$or': [
        {'maintenance_until': {'$exists': False}}, {'maintenance_until': {'$lte': now}}]},
        {'$set': dict(values, phase='running')}, return_document=ReturnDocument.AFTER)
