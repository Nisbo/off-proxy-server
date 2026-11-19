> **Warning: Early development — do not use in production yet. Updates may fail. Use a separate test installation and keep backups.**

# OFF Proxy Server

[Deutsch](README.de.md) · [GitHub](https://github.com/Nisbo/off-proxy-server) · [Changes](CHANGELOG.md)

A self-hosted barcode lookup API with a local mirror of **Open Food Facts,
Open Beauty Facts, Open Pet Food Facts and Open Products Facts**. The complete
exported product documents are retained; images remain remote URLs.

The project provides product-by-barcode lookups, not the entire OFF API.
It currently has no name search, product editing, public dashboard search or
online fallback for unknown products. HA List Manager integration is not yet included.

## Before installing

- Linux, Bash, Docker Engine with Docker Compose v2, curl, tar and util-linux (`flock`).
  Run installation and management as root. The installer does not install Docker
  or OS packages. Host Python, pip, Git and a separate web server are unnecessary.
- MongoDB 8 needs a supported CPU; x86-64 hosts require AVX.
- A useful starting point is 2 CPU cores and 2–4 GiB RAM available to these services.
  The configured container memory limits total about 2 GiB, excluding the host.
- In one deployment, about five million products used **36 GiB on disk** and
  approximately 1 GiB RAM after import. Allow room for both old and replacement
  datasets: roughly 80–100 GiB free was a reasonable reserve at that observed size.
  These are measurements, not size guarantees. Docker images, backups and growth
  require additional room. CPU limits do not limit disk I/O.

## Install and sign in

In a root **Bash** shell:

```sh
set -o pipefail
curl -fsSL --proto '=https' https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/install.sh | bash
```

The installer asks twice for your own **8–256 character** administrator password.
Input and pasted text remain hidden; there is no generated setup code. If no
interactive terminal is available, the GUI stays locked. Set/reset the password with:

```sh
off-proxy password
```

The installation directory is `/opt/off-proxy-server`. The bootstrap and application
archive are pinned to the same GitHub commit. Only runtime files are installed;
tests, CI configuration and development tools are excluded. The application runs
without root privileges inside its containers. MongoDB publishes no host port.
No unrelated containers or databases are changed.

By default the HTTP listener is available **only on the server itself**, at
`http://127.0.0.1:8097/`. To use another computer, edit `BIND_IP` in
`/opt/off-proxy-server/.env` to the server's specific LAN/VPN address, then run
`off-proxy start`. `PORT` defaults to `8097`. `0.0.0.0` deliberately exposes all
IPv4 interfaces; prefer a specific address and restrict network access.
Change bindings outside active imports because Compose may recreate containers.

Open `http://<server-address>:8097/`, sign in and confirm **Full import…** for each
desired dataset. There is no automatic initial full import. The first food import
can take hours. Once the installation command has finished, the importer runs in
the background and does not depend on the shell or browser remaining open.

## Everyday commands

| Command | Purpose |
| --- | --- |
| `off-proxy status` | Version and dataset status |
| `off-proxy logs` | Follow synchronization logs; Ctrl+C closes only the view |
| `off-proxy test 4062139025398 all` | Query a product across all available datasets |
| `off-proxy password` | Set/reset the GUI password and revoke all sessions |
| `off-proxy update` | Download and activate the current `main` commit |
| `off-proxy components-update` | Manually refresh container components without changing application code |
| `off-proxy rollback` | Return to the previous locally retained software version |
| `off-proxy stop` / `off-proxy start` | Stop/start this installation; retain data |
| `off-proxy down` | Remove only this project's containers/networks; retain data |

There are currently **no stable/beta update channels or unattended updates**.
Manual updates follow `main`; separate release channels are still to be designed.
A repeated update to the same commit does not rebuild or restart services.

Updates build the replacement image before stopping services, defer during active
imports, and verify the API version after activation. The worker's cycle start
and updater share a temporary maintenance gate. Failed activation attempts to
restore the previous services. An interrupted updater's gate expires within ten
minutes. This gate requires the updated worker; old prototypes do not implement it.
Existing data, passwords, API keys, bindings and settings are retained.

**Rollback restores software, not a database backup.** Returning to versions before
0.1.7 also removes GUI protection and uses the original `.env` API key again.

### Upgrading from 0.1.10 or earlier / missing runtime files

Old management scripts copy a fixed list of runtime files. When upgrading to
0.1.11, this can fail with `components.py: not found` before services restart.
Run the current bootstrap installer once instead of the old update command:

```sh
curl -fsSL https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/install.sh | bash
```

It detects the existing managed installation and preserves the data directory,
settings, password, sessions, API key and network binding. It repairs incomplete
cached source releases. For a custom installation directory, append its path to
`bash -s -- /your/installation`. Subsequent updates use `off-proxy update` again.
New runtime files are listed in `runtime-files.txt` rather than a frozen list in
the installed updater. The installer never deletes the product database.

### Manual component updates

After installing this version with `off-proxy update`, run:

```sh
off-proxy components-update
```

This rebuilds the **currently installed source**, even if its commit has not changed.
It pulls the latest published Python 3.13 container base (including its Linux
packages), installs the latest compatible Gunicorn **27.x**, and refreshes MongoDB
within **8.0.x**. PyMongo stays pinned to the version tested with the application.
It does not update the host's Debian, Docker, your reverse proxy, or our application
code. A new Python/MongoDB/Gunicorn version series requires an application update.
There are **no automatic component updates** and no scheduled update job.

Downloads and the replacement build finish before services stop. Active imports
or a racing synchronization cycle defer the operation without stopping services.
After a short restart, the authenticated API health check must succeed. Separate
application image tags and a pinned MongoDB image preserve the previous images
for a failed-activation recovery attempt. Database files, settings, password hashes,
sessions, API keys, bindings and installed source pointers are retained. A component
update does not request a full import. Software rollback does not undo a successful
component update or restore database files: make a database backup beforehand.
If interrupted, rerun the command; do not delete `.state` or database directories.

The API and GUI now run on **Gunicorn**, a production WSGI server, instead of
Python's development HTTP server. Requests and connections are bounded; the image
still runs without root privileges. HTTPS remains the responsibility of your
reverse proxy. `X-Forwarded-Proto: https` is retained solely as the existing Secure
cookie hint; forwarded client addresses and hosts are not trusted for identity or
access checks. The proxy must preserve `Host` and overwrite the protocol header.

### Component updates in the GUI

**Components** opens installed Python, Gunicorn and MongoDB versions, update
availability, the last check, and the current/last action. **Check for updates**
compares published Gunicorn 27.x releases and the upstream Python/MongoDB image
digests with the actual installed images. Missing build provenance or an unreachable
source is shown as **unknown**, never as up to date. Python/Linux changes are
reported as an image update; its exact new Python version is known after installation.
The application version remains visible in the page header; this action does not
check for or install new application code.

**Update components…** requires another explicit confirmation. It shows download,
build, restart and verification stages. An open page reconnects after the short
restart; the existing login session survives. Imports defer updates; interrupted,
expired and failed requests need a new user action. Repeated clicks are coalesced.
A refresh, login, service start or boot **never schedules an update or a network
update check**. After an explicitly requested update, its result is checked once.

The installer/updater automatically installs a project-specific systemd host service
on supported Docker hosts. It polls only for explicit, authenticated requests and
runs fixed management commands. The GUI container has **no Docker socket or host
filesystem access**. Host Debian needs no additional Python environment. If systemd
is absent or the helper cannot start, the GUI explains that host actions are unavailable;
the CLI still works. To retry installation: `off-proxy host-agent install`.
The unit name is `off-proxy-components-<installation-id>.service`; inspect it with
`systemctl status 'off-proxy-components-*'`. Diagnostic output is kept locally in
`.state/components.log` (last job, at most 1 MiB after completion), not exposed in
the GUI. The helper does not start the Docker stack when it is stopped. A container
restart policy and helper restart policy restart services only; they do not update software.

## Dashboard and access

The GUI supports German and English and remembers the language in the browser.
Its statistics, lookup and controls require administrator sign-in.

- **Refresh display** reloads status only. Metadata product counts may be cached
  for 30 seconds; storage includes allocated data/indexes, not all filesystem overhead.
- **Synchronize now** requests a delta check. Repeated clicks are coalesced;
  the single worker handles the request when it is available.
- **Full import…** first opens a confirmation. Download and decompression stream
  into a separate collection. Only a completed, validated import replaces the
  published pointer; the previous copy is removed afterward. A failure before
  publication retains the old data. Temporarily, both copies require disk space.
- **Settings** controls gap handling, full-import confirmation and optional intervals.
  Defaults: continue available deltas, require full-import confirmation, interval `0`
  (disabled). Automatic full imports require separate explicit consent.
- **Access & API** controls inactivity expiry (30 minutes by default, 8 hours,
  custom or disabled), password changes, and signing out all sessions. Status
  polling does not extend a session; actual interaction does. Cookies can persist
  for up to one year. Password changes and terminal resets revoke every session.

Full imports that are interrupted or fail before publication need another
confirmation under the default policy. A later delta-source failure does not
turn a successfully completed full import into a failed full-import request.
An empty snapshot or a record-count decrease exceeding 25% is rejected for review.

Use the eye to reveal/hide the saved API key, or **Copy** while it is hidden.
You can generate a new key or enter your own 24–256 non-space ASCII characters.
Only saving applies a change; old clients then need the new key immediately.
`API_TOKEN` in `.env` bootstraps the access record once. Later key changes are
stored recoverably in MongoDB; status/update/test commands use that current key.

API authentication is enabled by default. Explicitly enabling keyless access
opens **only product API lookups**. It never opens GUI lookup, statistics,
settings, import controls or `/health`. Public GUI search is deferred.

Passwords are salted PBKDF2-HMAC-SHA256 hashes with 600,000 iterations. Random
session tokens are stored only as hashes; cookies are HttpOnly and SameSite=Strict.
Controls also require CSRF protection; login attempts are rate-limited persistently.
Use HTTPS for domain access. The proxy must overwrite client forwarded headers
and set `X-Forwarded-Proto: https` for Secure cookies. Plain HTTP is supported for
trusted local test networks but does not encrypt credentials or traffic.

## Product API

A convenient server-side test uses the stored key automatically:

```sh
off-proxy test 0000527000057 beauty
```

For curl, copy the current key from the GUI and enter it at the hidden prompt:

```sh
read -r -s -p 'Current API key: ' TOKEN
printf '\n'
curl -sS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8097/api/v3/product/4062139025398.json?product_type=all&lc=de&fields=code,product_name,product_name_de,brands,quantity,image_front_thumb_url'
unset TOKEN
```

| Parameter | Supported values |
| --- | --- |
| `product_type` | `food` (default), `beauty`, `petfood`, `product`, `all` |
| `lc` | Language for selected image URLs, e.g. `de` or `en` |
| `fields` | Comma-separated top-level field names; omitted/`all`/`raw` returns the full document |

Barcodes are digit strings up to 256 characters; leading zeros are retained.
The response uses the OFF v3 product-result structure. Found products return 200.
Unknown products return 404 when all requested datasets are available, otherwise
503. A hit can be returned even if another dataset is not ready. `/health` always
requires the current API key. `all_ready` means snapshots exist; `all_synced` also
requires successful delta checks with no known gaps. No general OFF search,
write API, barcode normalization or full computed-field parity is promised.
Never put a key or password in a URL.

## Deltas and outages

The worker checks every six hours. A transient timeout, HTTP 429 or 5xx keeps the
file cursor unchanged and is retried on a later check; other datasets continue.
Interrupted delta files may have applied some product writes but are replayed
safely. Revision checks prevent older data from overwriting newer products.

Coverage is tracked using the start/end timestamps in delta filenames. Missing
intervals in a successfully loaded index, or listed files returning 404/410, create
a persistent gap. Available newer deltas continue by default; an optional policy
pauses newer updates for just that dataset. Existing products remain queryable.
A returning historical file can close the gap. Otherwise a confirmed full import
is needed to restore complete coverage. Changes missing inside an apparently
valid upstream file cannot be detected this way.

OFF generally retains about 14 days of deltas and does not supply deletion events.
A few missed days are caught up if the files remain available. No full import is
started merely because files have expired: the warning persists and confirmation
is required by default. Optional full refreshes reconcile deletions as well.
All source URLs are configured in [app.py](app.py); images are not downloaded.

## Backups, troubleshooting and removal

For a consistent filesystem backup, first run `off-proxy stop`. Back up `.env`,
`.state`, retained source versions and **both MongoDB directories `data` and
`configdb`**. Start again with `off-proxy start`. The runtime data directory is
recorded in `/opt/off-proxy-server/.state/runtime`; older migrated installations
may use `/opt/off-local-api`, which must be backed up separately. Backups contain
API credentials and password hashes; restrict access and test restoration in a
separate environment. Software rollback does not replace these backups.

- GUI locked: run `off-proxy password`, then reload the page.
- Import error: check `off-proxy status` and `off-proxy logs`; do not delete data.
- No space left: check host disk usage, including Docker images and import staging.
- Update deferred: let the active synchronization finish, then retry.
- GUI reports a delta gap: choose continue/pause; approve a full import when suitable.
- After an update: reload the browser page; API key changes do not require a restart.

To remove services, use `off-proxy down`. Delete directories only if you also
intend to remove their data. There is no global Docker prune or automatic cleanup
of unrelated images. Retained application images/source versions permit rollback.

## Existing prototype migration

The installer still recognizes prototypes 0.1.0–0.1.2 under `/opt/off-local-api`.
It retains the original Compose project, database location and configuration,
without copying the database or reimporting it. Old source is backed up locally.
After migration use **only `off-proxy`**, not the old `manage.sh` or Compose file.
This compatibility path is separate from the normal fresh installation.

## Development and verification

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests use generated fixtures, never real user product dumps. Set `MONGO_TEST_URI`
to a disposable MongoDB endpoint for real database tests; only uniquely named
test databases are created/dropped. CLI tests simulate download/Docker boundaries.
An additional opt-in Docker smoke test performs actual install, key rotation,
update and rollback on a disposable Docker host, with local archives and no OFF
imports. Run it only as root with `DOCKER_SMOKE=1`; it uses port 8097 and the
`off-proxy-server` Compose project. Never run it on an installed server.

CI runs these tests, coverage reporting, Ruff, Bandit, ShellCheck, Compose
validation and image builds. Runtime dependency audit: `pip-audit -r requirements.txt`.
Tests and development tools remain in GitHub for reproducibility but are excluded
from installed releases and the application image. Passing checks are not a
promise of complete security or full OFF API compatibility.

## License

Code: [MIT](LICENSE), copyright Nisbo. Product data has separate terms:
**Open Food Facts contributors**, ODbL for the database, DbCL for contents;
images have their own licenses. See [OFF data and reuse](https://world.openfoodfacts.org/data).
This is an independent project, not an official OFF service. No product dump,
private configuration or API credential is distributed in this repository.
