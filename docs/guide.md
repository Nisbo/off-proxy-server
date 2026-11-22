# OFF Proxy Server guide

[Quick start](../README.md) · [Deutsch](guide.de.md) · [Releases](https://github.com/Nisbo/off-proxy-server/releases)

## Requirements

You need a Linux system and a shell as `root`. On Proxmox, open the console
of the VM or container running Docker. If you are signed in as a regular user
with `sudo` access, run `sudo -i` to switch to `root`.

The installer uses Bash and three small Linux tools. `curl` downloads files,
`tar` extracts them, and `flock` prevents two installations or updates from
running at the same time. If any of these are missing on Debian or Ubuntu,
install the packages as root:

```sh
apt update && apt install bash curl tar util-linux
```

[`flock` comes with the `util-linux` package.](https://packages.debian.org/trixie/amd64/util-linux/filelist)

### Set up Docker

Install Docker before running the OFF Proxy installer. Docker Compose starts
OFF Proxy and its MongoDB database together.

On a **fresh test machine** that needs Docker, you can download and run
Docker's official convenience script as root in one line.
[Docker's installation script guide](https://docs.docker.com/engine/install/debian/#install-using-the-convenience-script)

```sh
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
```

For a long-running server, Docker recommends installing from its package
repository. [Debian](https://docs.docker.com/engine/install/debian/#install-using-the-apt-repository) · [Ubuntu](https://docs.docker.com/engine/install/ubuntu/#install-using-the-apt-repository)

If Docker is already installed or you have just set it up, check from
the terminal:

```sh
docker compose version
```

A version number tells you Compose is available. If Docker is present but
the `compose` command is missing, install the Compose plugin.
[Docker Compose plugin guide](https://docs.docker.com/compose/install/linux/)

A systemd host service enables program and component updates from the dashboard.
The application runs as an unprivileged user in its containers. MongoDB has no
published host port.

### Storage and hardware

MongoDB 8 requires a supported CPU and AVX on x86-64. A starting point is two CPU
cores and 2–4 GiB of available RAM. A deployment with about five million products
used 36 GiB of disk space after import. Allow space for both copies during a full
refresh plus images, backups and growth. For a dataset of that observed size,
80–100 GiB of free space was a reasonable reserve.

## Network access

The installer prompts for a password (8–256 characters), then offers three options.

- **All IPv4 addresses** is the default. The dashboard and API listen on all
  IPv4 interfaces, including public interfaces if the firewall allows the port.
- **Specific addresses** are listed by number. Enter the numbers separated by
  spaces to select more than one.
- **Local only** binds to `127.0.0.1`, for example for a reverse proxy on
  the same system.

Open one of the browser links printed by the installer. An installation without
an interactive terminal starts with local access. Run `off-proxy password`
as `root` afterward to set the password and choose the addresses.

Run `off-proxy bind` as `root` to change the selection later. Without an
interactive terminal, the command prints the current binding and links.
To change the binding directly, run `off-proxy bind all`, `off-proxy bind local`
or, for example, `off-proxy bind 192.168.1.50 10.0.0.50`. Changing the binding
briefly restarts the web service if it is running. Updates preserve your
selection. CLI commands from older versions support only the first selected address. Use HTTPS at the reverse proxy for domain access.

## Updates and rollback

For a stable or beta release, open **Components → Program updates**, choose a
channel and select **Check for releases**. Review the release notes, choose
**Install release…** and confirm. The host service checks the selected release
again before installation. The dashboard remembers the channel in this browser.
Checking or opening the dashboard never installs an update.

The installer and updater leave data, network bindings, settings and credentials
in the installation directory. An update prepares the image first, defers while
an import is active and checks the API after restarting. If activation fails,
the updater attempts to restore the previous services. `off-proxy rollback`
switches to the previous software version. Keep a separate database backup.

Use the published stable release for a new installation. For a development
installation from `main`, run the downloaded installer with `bash off-proxy-install.sh --main`.
An optional absolute path after the arguments selects a custom installation
directory. The bootstrap pins the command and application source to the same
Git commit. A stable release tag uses the format `v0.2.0`. A beta prerelease uses
`v0.2.0-beta.1`. The tag's version must match the source's `VERSION` file.

| Command | Purpose |
| --- | --- |
| `off-proxy status` | Version and dataset status |
| `off-proxy logs` | Follow synchronization logs |
| `off-proxy test 4062139025398 all` | Look up a barcode across all datasets |
| `off-proxy password` | Set or reset the dashboard password |
| `off-proxy bind` | Show or change the dashboard and API addresses |
| `off-proxy update` | Install the latest published stable release |
| `off-proxy update beta` | Install the latest published beta release |
| `off-proxy update beta --head` | Install the latest commit from `beta` |
| `off-proxy components-update` | Rebuild the installed program with refreshed container components |
| `off-proxy rollback` | Return to the previous locally stored software version |
| `off-proxy stop` / `off-proxy start` | Stop or start the services |
| `off-proxy down` | Remove the project's containers and networks while keeping data |

If the selected channel has no published release, the updater reports that
no release is available and leaves the installation as it is.

### Container components

In **Components**, use **Check for updates** to compare the installed
Python/Linux, Gunicorn and MongoDB components against their compatible upstream
versions. A newer container build can retain the same version number. **Update
components…** and **Reinstall components…** both require confirmation. During an
update the dashboard reconnects after the service restart and shows the result.

A components update uses the current Python 3.13/Linux base, Gunicorn 27.x and
MongoDB 8.0.x. PyMongo stays pinned by the program. Manage the host OS, Docker
and reverse proxy separately. On systems with systemd, `off-proxy host-agent install`
repairs the host helper if necessary. Its latest job log is in `.state/components.log`.

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

For a curl lookup, use the browser address shown by the installer or by
`off-proxy bind`. Copy the current API key from the dashboard.

```sh
read -r -p 'Browser address: ' BASE_URL
read -r -s -p 'Current API key: ' TOKEN
printf '\n'
curl -sS -H "Authorization: Bearer $TOKEN" \
  "${BASE_URL%/}/api/v3/product/4062139025398.json?product_type=all&lc=de&fields=code,product_name,product_name_de,brands,quantity,image_front_thumb_url"
unset TOKEN BASE_URL
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
All source URLs are configured in [app.py](../server/app.py); images are not downloaded.

## Backups, troubleshooting and removal

For a consistent filesystem backup, first run `off-proxy stop`. Back up `.env`,
`.state`, retained source versions and **both MongoDB directories `data` and
`configdb`**. Start again with `off-proxy start`. The runtime data directory is
recorded in `/opt/off-proxy-server/.state/runtime`. Backups contain
API credentials and password hashes; restrict access and test restoration in a
separate environment. Software rollback does not replace these backups.

- GUI locked: run `off-proxy password`, then reload the page.
- Import error: check `off-proxy status` and `off-proxy logs`; do not delete data.
- No space left: check host disk usage, including Docker images and import staging.
- Update deferred: let the active synchronization finish, then retry.
- GUI reports a delta gap: choose continue/pause; approve a full import when suitable.
- After an update: reload the browser page; API key changes do not require a restart.

`off-proxy down` removes the project containers and networks. The systemd helper
stays installed and enabled. Delete directories only if you also intend to
remove their data. There is no global Docker prune or automatic cleanup
of unrelated images. Retained application images/source versions permit rollback.

## Development and verification

```sh
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements-dev.txt
.venv/bin/python -m pytest -q tests
```

Tests use generated fixtures, never real user product dumps. Set `MONGO_TEST_URI`
to a disposable MongoDB endpoint for real database tests; only uniquely named
test databases are created/dropped. CLI tests simulate download/Docker boundaries.
An additional opt-in Docker smoke test performs actual install, key rotation,
update and rollback on a disposable Docker host, with local archives and no OFF
imports. Run it only as root with `DOCKER_SMOKE=1`; it uses port 8097 and the
`off-proxy-server` Compose project. Never run it on an installed server.

CI runs these tests, coverage reporting, Ruff, Bandit, ShellCheck, Compose
validation and image builds. Runtime dependency audit: `pip-audit -r server/requirements.txt`.
Tests and development tools remain in GitHub for reproducibility but are excluded
from installed releases and the application image. Passing checks are not a
promise of complete security or full OFF API compatibility.

## License

Code: [MIT](../LICENSE), copyright Nisbo. Product data has separate terms:
**Open Food Facts contributors**, ODbL for the database, DbCL for contents;
images have their own licenses. See [OFF data and reuse](https://world.openfoodfacts.org/data).
This is an independent project, not an official OFF service. No product dump,
private configuration or API credential is distributed in this repository.
