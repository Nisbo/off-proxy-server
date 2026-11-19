"""Sanitized dashboard data for authenticated sessions. Never expose API credentials or raw state."""
import threading
import time
from pathlib import Path

from pymongo.errors import PyMongoError
import control

WEB = Path(__file__).with_name("web")
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
    "/assets/dashboard.js": ("dashboard.js", "text/javascript; charset=utf-8"),
}
LOOKUP_FIELDS = (
    "code", "product_name", "product_name_de", "product_name_en", "brands",
    "quantity", "product_quantity", "product_quantity_unit", "product_type",
    "image_front_thumb_url",
)
STATE_FIELDS = (
    "phase", "ready", "full_at", "full_epoch", "checked_at", "delta_at",
    "source_modified", "error", "error_at", "unindexed_records",
    "delta_gaps", "full_reasons",
)
PROGRESS_FIELDS = (
    "mode", "records", "unindexed", "downloaded_bytes", "total_bytes",
    "started_epoch", "updated_epoch", "records_per_second", "finished",
)
SCHEDULER_FIELDS = (
    "phase", "active_kind", "cycle_started_at", "finished_at", "heartbeat_epoch",
    "next_check_epoch", "sync_seconds",
)


class Dashboard:
    def __init__(self, db, version, projects):
        self.db, self.version, self.projects = db, version, projects
        self._lock = threading.Lock()
        self._stats = None
        self._stats_key = None
        self._sampled = 0

    def statistics(self, states):
        key = tuple((kind, state.get("collection")) for kind, state in states.items())
        with self._lock:
            if self._stats is not None and key == self._stats_key and time.monotonic() - self._sampled < 30:
                return self._stats
            counts = {}
            for kind, state in states.items():
                counts[kind] = None
                if state.get("ready") and state.get("collection"):
                    # MongoDB metadata: no scan over millions of product documents.
                    counts[kind] = self.db[state["collection"]].estimated_document_count()
            allocated = logical = None
            try:
                stats = self.db.command("dbStats", scale=1)
                allocated = stats.get("storageSize", 0) + stats.get("indexSize", 0)
                logical = stats.get("dataSize")
            except (PyMongoError, NotImplementedError):
                # A restricted database user may not be permitted to read dbStats.
                pass
            self._stats = {"counts": counts, "records": sum(v or 0 for v in counts.values()),
                           "database_bytes": allocated, "logical_bytes": logical,
                           "sampled_epoch": time.time(), "counts_estimated": True}
            self._stats_key, self._sampled = key, time.monotonic()
            return self._stats

    def snapshot(self):
        raw = {state["_id"]: state for state in self.db.state.find({})}
        states = {kind: raw.get(kind, {}) for kind in self.projects}
        scheduler = self.db.scheduler.find_one({"_id": "sync"}) or {}
        stats = self.statistics(states)
        options = control.settings(self.db)
        days = options["full_interval_days"]
        datasets = {}
        for kind, state in states.items():
            public = {key: state[key] for key in STATE_FIELDS if key in state}
            public.setdefault("ready", False)
            public.setdefault("phase", "pending")
            public["records"] = stats["counts"][kind]
            public["snapshot_records"] = state.get("records")
            public["next_full_epoch"] = state["full_epoch"] + days * 86400 if days and state.get("full_epoch") else None
            progress = state.get("progress")
            public["progress"] = {key: progress[key] for key in PROGRESS_FIELDS if key in progress} if isinstance(progress, dict) else None
            datasets[kind] = public
        schedule = {key: scheduler[key] for key in SCHEDULER_FIELDS if key in scheduler}
        schedule.setdefault("phase", "unknown")
        schedule.setdefault("next_check_epoch", None)
        now = time.time()
        heartbeat = schedule.get("heartbeat_epoch", 0)
        deadline = schedule.get("next_check_epoch")
        schedule["stale"] = bool(heartbeat and (
            (schedule["phase"] == "running" and now - heartbeat > 120) or
            (schedule["phase"] == "waiting" and deadline and now > deadline + 120)))
        return {"version": self.version, "server_epoch": now, "datasets": datasets,
                "settings": options,
                "requests": {r["_id"]: {k: r[k] for k in ("status", "error") if k in r}
                             for r in self.db.requests.find({}) if r["_id"] in ("sync", *("full:" + k for k in self.projects))},
                "scheduler": schedule, "statistics": {k: v for k, v in stats.items() if k != "counts"},
                "all_ready": all(s["ready"] for s in datasets.values()),
                "all_synced": all(s["ready"] and s["phase"] == "ready" for s in datasets.values())}
