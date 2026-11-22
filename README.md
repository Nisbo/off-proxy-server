> **Warning: Early development. Use a test installation and keep a backup.**

# OFF Proxy Server

[Deutsch](README.de.md) · [User guide](docs/guide.md) · [Releases](https://github.com/Nisbo/off-proxy-server/releases)

A self-hosted barcode lookup API. Mirror Open Food Facts, Open Beauty Facts,
Open Pet Food Facts and Open Products Facts locally, then look up products by
barcode from the dashboard or a compatible application.

![OFF Proxy Server dashboard in English with dataset statistics, synchronization status and barcode lookup](docs/images/dashboard-en.png)

## Quick start

1. You need a Linux machine with Docker. If Docker is missing, follow the
   [Docker setup instructions](docs/guide.md#set-up-docker).
2. Open a terminal as an administrator (`root`) on the server. The command below
   installs the latest published stable release.

   ```sh
   curl -fsSL https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/install.sh -o off-proxy-install.sh && bash off-proxy-install.sh
   ```

3. Set an administrator password and open `http://127.0.0.1:8097/` on the server.
   For access from another computer, see [LAN or VPN access](docs/guide.md#lan-or-vpn-access).
4. Confirm **Full import…** for each dataset you want. The first food import can
   take hours and runs in the background.

## Use and update

- Test a lookup with `off-proxy test 4062139025398 all`.
- Check for releases and start updates under **Components → Program updates**.
- Find the [API, synchronization, backups and CLI commands](docs/guide.md) in the guide.

Code under the [MIT license](LICENSE). Product data has
[separate terms](https://world.openfoodfacts.org/data).
