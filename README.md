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
- Check daily delta files every six hours; manual synchronization from the dashboard.
- Full imports require confirmation by default; regular full refreshes are disabled.
- Atomic full-dataset publication, replayable deltas, older-version protection,
  detection of missing delta intervals and optional full refreshes for deletions.
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

The installer/update command must finish before closing the shell. Approved
imports then run independently in the background. An interrupted unfinished full import
needs a new confirmation and restarts from the beginning; completed datasets remain published.
On a fresh installation, open the dashboard and confirm the initial import for each dataset.

## Protected dashboard and API access

Open `http://<BIND_IP>:8097/` after updating. A browser running directly on the
server can use `http://127.0.0.1:8097/`. The dashboard supports English and German;
the language selection is retained locally in the browser.

The dashboard is locked until you set an administrator password. Fresh interactive
installations ask for a password twice in the terminal; there is no generated
setup code. After upgrading an existing installation, or to reset the password:

```sh
off-proxy password
```

The entry is hidden (including pasted text) and is passed on stdin, never as a
command argument. Use 12–256 characters. Until setup is complete, existing API
clients and synchronization continue, but no dashboard data or controls are
available without a session. There is no public GUI search in this version.

**Access & API** provides:

- Inactivity timeout: 30 minutes (default), 8 hours, a custom duration, or no
  inactivity timeout. Status polling does not keep sessions alive; user activity
  does. Cookies persist across browser restarts, with a one-year maximum lifetime.
- Sign out, sign out all sessions, and change the password using the current
  password. A password change or terminal reset revokes all sessions.
- Reveal/hide the stored API key with the eye or copy it while hidden. Set your
  own 24–256 character key or generate a new one. Confirm and save the change;
  the old key stops working immediately, including for existing API clients.
- Require an API key (default), or explicitly confirm keyless **product API**
  lookups. Statistics, GUI lookup, settings, import controls and `/health` are
  never made public by that switch.

Existing product data, synchronization settings and API keys are retained.
`API_TOKEN` in `.env` bootstraps the persistent access record on first start only.
After rotation, the current key is stored recoverably in MongoDB so an authenticated
administrator can reveal it. Status/update/test commands read the current key;
`.env` remains unchanged. A rollback to software before 0.1.7 uses its original
`.env` key again and does not provide this GUI protection.

Passwords use a salted PBKDF2-HMAC-SHA256 hash with 600,000 iterations. Session
tokens are random, stored only as hashes, and sent in HttpOnly, SameSite=Strict
cookies. Failed logins are rate-limited persistently. Controls require a session
and CSRF token. These choices follow the [OWASP password guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
and [session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Use HTTPS for domain access. The reverse proxy must set `X-Forwarded-Proto: https`
for Secure cookies and overwrite client-supplied forwarded headers. Direct plain
HTTP remains supported for trusted local test networks; it does not encrypt the
password or product traffic. No password or API key belongs in a URL.
Product editing is not available. Import controls use the existing single worker.

Progress shows processed records and compressed download bytes when a content
length is available. A full first import has no known total record count, so no
record percentage is invented. The next synchronization is recorded by the actual
worker at cycle completion. An optional full-refresh date is a due date, checked
on a subsequent synchronization cycle; it does not override confirmation
requirements. Missing or overdue worker reports are indicated.
Statistics use MongoDB metadata and a 30-second cache, not full product scans.
The storage value includes allocated data and indexes (and ongoing import
collections), excluding journal/filesystem overhead. It may differ from `du`.

The first update installs the dashboard without reimporting existing datasets.
Progress starts being recorded by the updated worker on its next import.

## API example

On the server, with an imported cosmetic dataset:

```sh
read -r -s -p 'Current API key: ' TOKEN
printf '\n'
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

The dashboard controls are:

- **Refresh display:** reload status only. Product counts may be cached for 30 seconds.
- **Synchronize now:** queue a delta check across all datasets. Repeated requests
  while queued/running are coalesced. The single worker checks requests every two
  seconds when idle; a running import finishes first.
- **Full import…:** explicitly confirm a complete download/rebuild for one dataset.
  Existing published data remains readable. Failed/interrupted requests are not
  automatically retried as full imports.
- **Settings:** choose how to handle delta gaps and full imports. Settings and
  requests persist in MongoDB, survive updates, and do not modify `.env`.

Safe defaults, including after upgrading from 0.1.4: continue applying available
**deltas**, require confirmation for **all full imports**, and disable regular
full refreshes (interval `0`). Legacy `FULL_DAYS=30` no longer enables automatic
imports. An optional interval merely marks a refresh as due while confirmation
is required. Automatic full imports require a separate explicit consent in settings;
this opt-in covers initial imports, gap recovery and enabled intervals.

OFF retains approximately 14 days of deltas, without deletion events. A full
refresh reconciles deletions and permanently missing changes. When continuing
past a gap, newer products become up to date but products changed only in the
missing interval may remain outdated; the dataset stays marked as incomplete.
Optionally pause newer deltas for only the affected dataset instead. Existing
products and other datasets stay available.

Coverage is determined from the start/end timestamps in delta filenames, not
from calendar days. A missing interval in a successfully loaded index, or a
listed file returning HTTP 404/410, is recorded as a persistent gap. HTTP 5xx,
429 and timeouts alone do **not** establish a gap: the file cursor is retained
and incomplete files are retried. After three offline days, all still available
contiguous deltas are replayed. If a missing file reappears, historical deltas
are replayed to close that gap; revision checks prevent overwriting newer data.
Otherwise the warning remains until a confirmed full import succeeds. These
checks cannot detect changes omitted inside an otherwise valid upstream file.
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
