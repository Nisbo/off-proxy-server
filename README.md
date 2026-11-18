> **Warning: Early development — do not use in production yet. Updates may fail, interrupt imports or cause unexpected errors. Use only in a test environment with backups.**

# OFF Proxy Server

[Deutsch](README.de.md) · [GitHub](https://github.com/Nisbo/off-proxy-server)

A small self-hosted product lookup API backed by a local MongoDB mirror of the
Open Food Facts family of databases. Built for barcode scans and applications
such as HA List Manager. **Early version; API compatibility is limited to product
lookup, not the entire Open Food Facts API.**

## What works

- Preserve complete exported product documents from Open Food Facts, Open Beauty
  Facts, Open Pet Food Facts and Open Products Facts. Images remain remote URLs.
- Indexed barcode lookup: `/api/v3/product/<barcode>.json` with `product_type`,
  simple `fields` selection and `lc` for selected image URLs.
- Background full imports; check daily delta files every six hours.
- Atomic full-dataset publication, replayable deltas, older-version protection,
  detection of missing delta intervals and periodic full refreshes for deletions.
- Retain source records without barcodes, report them separately, and never
  fabricate an EAN. Preserve leading zeros and nonstandard source identifiers.
- Token-protected API on localhost by default; MongoDB has no published port.
- Public test dashboard with dataset statistics, live import progress, next synchronization times and EAN lookup across all datasets.
- Install, update, status, logs, product test, stop/start and rollback commands.

There is **no product editing, search-by-name API or automatic online lookup for
unknown barcodes yet**. User-written product records are not planned. A future
optional upstream fallback will fetch and cache products found at OFF.

## Requirements

Linux with Bash, Docker Engine, Docker Compose v2, curl, tar and util-linux
(`flock`). Root is required for Docker and installing the management command.
No Python, pip, Git, external database or web server is needed on the host.
MongoDB 8 requires a compatible CPU; x86-64 hosts need AVX support.

Start with approximately 2 CPU cores and 2–4 GiB RAM available to the services.
In one low-traffic deployment, about five million complete product records used
36 GiB of disk and roughly 1 GiB RAM after import. This is an observation, not a
guarantee. Allow space for a second dataset during full replacement; about
80–100 GiB free before a full import provides headroom at that observed size.
Images, Docker images, backups and future data growth need separate space.
CPU limits do not cap disk I/O. First import may take hours and continues after
the shell closes, once installation has returned successfully.

## Install

As root:

```sh
curl -fsSL https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/install.sh | bash
```

You may inspect [install.sh](install.sh) and [off-proxy](off-proxy) before running
them. The installer downloads a commit-specific source archive from this
repository, builds the application image once, and starts an isolated Compose
project. It does not run apt or change unrelated containers.

New installations use `/opt/off-proxy-server`. A random API token is generated
in `.env`, with mode 600. Data and config stay outside versioned source folders.
The latest main commit is the update channel; there are no stable releases yet.

### Existing `/opt/off-local-api` prototype

The same install command recognizes prototype versions 0.1.0–0.1.2 automatically:

- Existing MongoDB files remain in `/opt/off-local-api/data` and `configdb`.
- The existing Compose project `off-local-api` is retained.
- API token, address and port are copied unchanged into the new management `.env`.
- Original files remain untouched and a legacy source snapshot enables rollback.
- No second database is created and no full import is triggered merely by migration.
  Normal scheduled synchronization still applies.
- An active full/delta import defers migration before any service is stopped.

After migration use **`off-proxy` instead of the old `manage.sh`**. In particular,
do not start a second stack from the old Compose file. The old `.env` is retained
as a historical copy; subsequent settings belong to `/opt/off-proxy-server/.env`.

## Commands

```sh
off-proxy status                       # dataset state; no credentials printed
off-proxy logs                         # Ctrl+C exits the viewer only
off-proxy test 0000527000057 beauty     # known cosmetic example, availability may change
off-proxy test 4062139025398 food       # food example
off-proxy update                       # latest main; preserves config and database
off-proxy rollback                     # previous source version, same data
off-proxy stop                         # stop services; preserve data
off-proxy start                        # start existing version
off-proxy down                         # remove project containers/networks; preserve data
```

Updates download/build before stopping existing services, check for active imports,
and verify the new API version. A failed activation attempts to restart the old
version. Rollback restores software, **not a database backup**; no destructive
database schema changes are made by this version. Releases are kept locally for
rollback. If main has not changed, update does not restart services.

The installer/update command must finish before closing the shell. Background
imports then run independently. An interrupted unfinished full import restarts
from the beginning; completed datasets remain published.

## Test dashboard (no login yet)

Open `http://<BIND_IP>:8097/` after updating. A browser running directly on the
server can use `http://127.0.0.1:8097/`. The dashboard supports English and German;
the language selection is retained locally in the browser.

**The dashboard and its read-only `/ui/status` and `/ui/lookup` routes are
intentionally accessible without a login in this early test version.** Anyone
who can reach the port can view these statistics and the selected product fields.
The existing `/health` and `/api/v3/product/...` routes still require the API key.
No key is embedded in the web page, sent to the browser or required for GUI lookup.
There are no dashboard controls that write product data or start imports.

Progress shows processed records and compressed download bytes when a content
length is available. A full first import has no known total record count, so no
record percentage is invented. The next synchronization is recorded by the actual
worker at cycle completion; the full-refresh date is the due date, checked on a
subsequent synchronization cycle. Missing or overdue worker reports are indicated.
Statistics use MongoDB metadata and a 30-second cache, not full product scans.
The storage value includes allocated data and indexes (and ongoing import
collections), excluding journal/filesystem overhead. It may differ from `du`.

The first update installs the dashboard without reimporting existing datasets.
Progress starts being recorded by the updated worker on its next import.

## API example

On the server, with an imported cosmetic dataset:

```sh
TOKEN=$(sed -n 's/^API_TOKEN=//p' /opt/off-proxy-server/.env)
curl -sS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8097/api/v3/product/0000527000057.json?product_type=beauty&fields=code,product_name,brands,quantity'
unset TOKEN
```

Types: `food` (default), `beauty`, `petfood`, `product`, `all`.
`GET /health` uses the same authentication and reports each dataset.
`all_ready` means all snapshots exist; `all_synced` additionally means the last
delta check succeeded for all four sources. An upstream outage can leave one
source unavailable while the others work. A 503 for an unknown code in an
incomplete set avoids incorrectly reporting that the product does not exist.

Only simple exported fields are supported. This is not an implementation of
OFF search, write APIs, every computed field, barcode normalization or cross-site
redirect behavior. It does not automatically add missing products from OFF yet.
HA List Manager requires a separate server-URL/token option to use this API.
This repository does not modify Home Assistant.

For access over a VPN/site-to-site connection, set `BIND_IP` to the server's
specific VPN/LAN address in `/opt/off-proxy-server/.env`, then use `off-proxy start`.
Do this outside active imports: changing environment settings can recreate services.
Use VPN transport or HTTPS; avoid publishing the API directly on all interfaces.

## Synchronization and source outages

All four original JSONL sources are configured. An unavailable source is reported
and retried. Pet-food source routing has intentionally not been switched to a
different mirror in this version. Other datasets continue importing independently.

OFF retains approximately 14 days of deltas, without deletion events. A gap
requires a full import; every 30 days a full refresh also reconciles deletions.
A >25% snapshot size decrease requires review rather than automatically
discarding a large part of a published dataset. Full import publication is atomic.
Delta files advance the cursor only when complete; a failed file may have already
updated some records, which are safely replayed on the next attempt.

## Remove

`off-proxy down` removes only this project's containers/networks and keeps data.
Afterward the installation directory and wrapper can be removed manually.
For migrated prototypes, the database still resides in `/opt/off-local-api`:
do not delete it unless you explicitly want to delete the product mirror.
No command runs a global Docker prune. Images remain cached.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Unit tests use mongomock; CLI tests simulate GitHub/Docker boundaries and verify
migration, unchanged data/token, update refusal during imports, failure recovery
and rollback. Set `MONGO_TEST_URI=mongodb://127.0.0.1:27017/` to run the database
tests against real MongoDB. Tests create/drop uniquely named test databases only.
CI runs both modes, validates Compose/shell syntax and builds the Docker image.

## License and attribution

Project code: [MIT](LICENSE), copyright Nisbo. OFF data is separate from this
code license: **Open Food Facts contributors**, ODbL for the database and DbCL for
its contents; product images have their own licensing. See
[OFF data and reuse terms](https://world.openfoodfacts.org/data).
No database dump, user secret or API token is distributed in this repository.
Independent project; not an official Open Food Facts service.
