> **Achtung: Frühe Entwicklung. Verwende eine Testinstallation und halte eine Datensicherung bereit.**

# OFF Proxy Server

[English](README.md) · [Anleitung](docs/guide.de.md) · [Releases](https://github.com/Nisbo/off-proxy-server/releases)

Ein selbst gehosteter Produktserver für Barcode-Abfragen. Er hält eine lokale
Kopie von Open Food Facts, Open Beauty Facts, Open Pet Food Facts und Open
Products Facts für die Suche im Dashboard oder per API bereit.

![Deutsche Oberfläche des OFF Proxy Servers mit Bestandsstatistik, Synchronisierungsstatus und Barcode-Suche](docs/images/dashboard-de.png)

## Schnellstart

1. Nutze einen Linux-Host mit Bash, Docker Compose v2, curl, tar und flock.
   Beachte die [Anforderungen an Speicher und CPU](docs/guide.de.md#voraussetzungen).
2. Führe den Installer als root aus. Er verwendet das neueste veröffentlichte stabile Release.

   ```sh
   curl -fsSL https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/install.sh -o off-proxy-install.sh && bash off-proxy-install.sh
   ```

3. Lege ein Administrator-Passwort fest und öffne `http://127.0.0.1:8097/` auf dem Server.
   Für andere Rechner siehe [Zugriff über LAN oder VPN](docs/guide.de.md#zugriff-über-lan-oder-vpn).
4. Bestätige **Vollimport …** für jeden gewünschten Bestand. Der erste Lebensmittelimport
   kann Stunden dauern und läuft im Hintergrund.

## Nutzung und Updates

- Teste eine Abfrage mit `off-proxy test 4062139025398 all`.
- Unter **Komponenten → Programmupdates** kannst du nach Releases suchen und die Installation starten.
- Die Anleitung enthält [API, Datenabgleich, Sicherungen und Shell-Befehle](docs/guide.de.md).

Code unter der [MIT-Lizenz](LICENSE). Für Produktdaten gelten
[eigene Nutzungsbedingungen](https://world.openfoodfacts.org/data).
