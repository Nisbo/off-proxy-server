# Anleitung zum OFF Proxy Server

[Schnellstart](../README.de.md) · [English](guide.md) · [Releases](https://github.com/Nisbo/off-proxy-server/releases)

## Voraussetzungen

Du brauchst einen Linux-Rechner und ein Terminal mit Administratorrechten
(`root`). Wenn du als normaler Benutzer angemeldet bist und `sudo` verwenden
kannst, öffne mit `sudo -i` ein solches Terminal.

Der Installer nutzt Bash und drei kleine Linux-Werkzeuge. `curl` lädt Dateien
herunter, `tar` entpackt sie und `flock` verhindert, dass zwei Installationen
oder Updates gleichzeitig laufen. Falls etwas fehlt, installiere auf Debian
oder Ubuntu die nötigen Pakete als root:

```sh
apt update && apt install bash curl tar util-linux
```

[`flock` gehört zum Paket `util-linux`.](https://packages.debian.org/trixie/amd64/util-linux/filelist)

### Docker einrichten

Docker muss installiert sein, bevor du den OFF-Proxy-Installer startest.
Docker Compose startet den OFF Proxy und seine MongoDB gemeinsam.

Auf einem **frischen Testrechner**, auf dem Docker noch fehlt, kannst du das
offizielle Docker-Skript als root mit einem Einzeiler herunterladen und starten.
[Docker-Dokumentation zum Installationsskript](https://docs.docker.com/engine/install/debian/#install-using-the-convenience-script)

```sh
curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh
```

Für einen dauerhaft genutzten Server empfiehlt Docker die Installation über
sein Paket-Repository. [Debian](https://docs.docker.com/engine/install/debian/#install-using-the-apt-repository) · [Ubuntu](https://docs.docker.com/engine/install/ubuntu/#install-using-the-apt-repository)

Wenn Docker schon installiert ist oder du es gerade eingerichtet hast, prüfe
im Terminal:

```sh
docker compose version
```

Erscheint eine Versionsnummer, ist Compose verfügbar. Wenn Docker installiert
ist, aber der Befehl `compose` fehlt, ergänze das Compose-Plugin.
[Docker-Anleitung zum Compose-Plugin](https://docs.docker.com/compose/install/linux/)

Ein systemd-Host-Dienst ermöglicht Programm- und Komponenten-Updates über die GUI.
In den Containern läuft die Anwendung ohne Root-Rechte. MongoDB veröffentlicht
keinen Host-Port.

### Speicher und Hardware

MongoDB 8 setzt eine geeignete CPU und bei x86-64 AVX voraus. Ein Ausgangspunkt
sind zwei CPU-Kerne und 2–4 GiB freier RAM. In einer Installation mit rund fünf
Millionen Produkten belegte die Datenbank nach dem Import 36 GiB. Für einen
Vollimport müssen beide Bestände gleichzeitig Platz finden. Dazu kommen
Images, Sicherungen und Wachstum. Bei der gemessenen Größe waren 80–100 GiB
freier Speicher eine sinnvolle Reserve.

## Zugriff über LAN oder VPN

Standardmäßig lauscht die Oberfläche auf `127.0.0.1:8097`. Für den Zugriff von
einem anderen Gerät setze `BIND_IP` in `/opt/off-proxy-server/.env` auf die
LAN- oder VPN-Adresse des Servers und führe `off-proxy start` aus. Ändere die
Bindung bei ruhendem Import. Für Zugriff über eine Domain nutze HTTPS am Reverse Proxy.

Der interaktive Installer fragt nach einem Administrator-Passwort (8–256 Zeichen).
Ohne Terminal legst du es nachträglich mit `off-proxy password` fest.

## Updates und Rollback

Unter **Komponenten → Programmupdates** kannst du **Stabil** oder **Beta**
wählen und **Nach Releases suchen**. Lies die Release Notes, wähle
**Release installieren …** und bestätige. Der Host-Dienst prüft das gewählte
Release vor der Installation erneut. Die GUI merkt sich den Kanal in diesem
Browser. Die Installation startet durch deine Bestätigung.

Der Updater erhält Daten, Netzwerkeinstellungen, Einstellungen und Zugangsdaten.
Er baut zuerst das neue Image, stellt das Update während laufender Importe zurück
und prüft nach dem Neustart die API. Schlägt die Aktivierung fehl, versucht er die vorherigen
Dienste wiederherzustellen. `off-proxy rollback` wechselt zur vorherigen
Programmversion. Eine separate Datensicherung ist weiterhin sinnvoll.

Für neue Installationen ist der stabile Release-Kanal vorgesehen. Für eine
Entwicklungsinstallation von `main` starte das heruntergeladene Skript mit
`bash off-proxy-install.sh --main`. Ein optionaler absoluter Pfad hinter den
Argumenten wählt das Installationsverzeichnis. Installer und Programm werden auf
denselben Git-Commit festgelegt. Stabile Release-Tags haben die Form `v0.2.0`.
Beta-Pre-Releases verwenden `v0.2.0-beta.1`. Der Tag muss zur `VERSION`-Datei passen.

| Befehl | Funktion |
| --- | --- |
| `off-proxy status` | Version und Status der Bestände |
| `off-proxy logs` | Abgleich-Logs verfolgen |
| `off-proxy test 4062139025398 all` | Barcode über alle Bestände abfragen |
| `off-proxy password` | GUI-Passwort festlegen oder zurücksetzen |
| `off-proxy update` | Neuesten Commit von `main` installieren |
| `off-proxy update beta` | Neuestes veröffentlichtes Beta-Release installieren |
| `off-proxy update beta --head` | Neuesten Commit von `beta` installieren |
| `off-proxy components-update` | Installierten Programmstand mit neuen Container-Komponenten aufbauen |
| `off-proxy rollback` | Vorherige lokal gespeicherte Programmversion starten |
| `off-proxy stop` / `off-proxy start` | Dienste stoppen oder starten |
| `off-proxy down` | Projektcontainer und Netzwerke entfernen, Daten behalten |

### Container-Komponenten

Unter **Komponenten** vergleicht **Nach Updates suchen** die installierte
Python-/Linux-Basis, Gunicorn und MongoDB mit den passenden verfügbaren Versionen.
Bei einem neueren Container-Build kann die Versionsnummer gleich bleiben.
**Komponenten aktualisieren …** und **Komponenten erneut installieren …** benötigen
eine Bestätigung. Die Oberfläche verbindet sich nach dem Neustart erneut und zeigt
das Ergebnis.

Ein Komponenten-Update verwendet die aktuelle Python-3.13-/Linux-Basis, Gunicorn
27.x und MongoDB 8.0.x. Die PyMongo-Version ist durch das Programm festgelegt.
Host-System, Docker und Reverse Proxy verwaltest du separat. Auf systemd-Systemen
kannst du den Host-Helfer bei Bedarf mit `off-proxy host-agent install` reparieren.
Das Log des letzten Auftrags steht in `.state/components.log`.

## Oberfläche und Zugriff

Die GUI unterstützt Deutsch und Englisch und merkt sich die Sprache im Browser.
Statistiken, GUI-Abfrage und Steuerung benötigen eine Administrator-Anmeldung.

- **Anzeige aktualisieren** lädt nur die Anzeige neu. Metadatenzählungen können
  30 Sekunden zwischengespeichert sein. Der Speicherwert umfasst Daten und Indizes,
  aber nicht den gesamten Dateisystem-Overhead.
- **Daten jetzt abgleichen** fordert eine Delta-Prüfung an. Mehrfachklicks werden
  zusammengefasst; der einzige Hintergrunddienst übernimmt den Auftrag, sobald er frei ist.
- **Vollimport …** öffnet zuerst eine Bestätigung. Download und Entpacken erfolgen
  direkt in einen separaten Bestand. Erst ein vollständig erfolgreicher, geprüfter
  Import ersetzt die veröffentlichte Zuordnung. Danach wird die alte Kopie entfernt.
  Bei einem Fehler davor bleibt der alte Bestand erhalten. Vorübergehend brauchen
  beide Kopien Speicherplatz.
- **Einstellungen** regelt Delta-Lücken, Vollimport-Bestätigung und optionale Intervalle.
  Standard: verfügbare Deltas fortsetzen, Vollimporte bestätigen und Intervall `0`
  (deaktiviert). Automatische Vollimporte benötigen eine zusätzliche ausdrückliche Zustimmung.
- **Zugriff & API** regelt Inaktivitätsablauf (standardmäßig 30 Minuten, 8 Stunden,
  eigene Dauer oder deaktiviert), Passwortwechsel und Abmelden aller Sitzungen.
  Statusabfragen verlängern die Sitzung nicht, tatsächliche Bedienung schon.
  Cookies bleiben höchstens ein Jahr erhalten. Passwortänderung und Zurücksetzen
  im Terminal widerrufen alle Sitzungen.

Unterbrochene oder vor der Veröffentlichung gescheiterte Vollimporte benötigen
standardmäßig eine neue Bestätigung. Ein späterer Fehler der Delta-Quelle macht
einen erfolgreich abgeschlossenen Vollimport nicht nachträglich zu einem gescheiterten
Vollimport-Auftrag. Leere Exporte oder mehr als 25 Prozent weniger Datensätze werden
zur Prüfung abgewiesen.

Mit dem Auge den gespeicherten API-Schlüssel anzeigen/verbergen oder verdeckt
**Kopieren**. Einen neuen erzeugen oder selbst 24–256 ASCII-Zeichen ohne Leerzeichen
eingeben. Erst Speichern übernimmt die Änderung; vorhandene Clients brauchen dann
sofort den neuen Schlüssel. `API_TOKEN` in `.env` wird nur beim ersten Start übernommen.
Spätere Schlüssel liegen wieder auslesbar in MongoDB; Status, Update und Test nutzen
immer diesen aktuellen Schlüssel.

API-Authentifizierung ist standardmäßig aktiv. Eine ausdrücklich bestätigte
Freigabe ohne Schlüssel öffnet **nur Produktabfragen über die API**. GUI-Abfrage,
Statistiken, Einstellungen, Importsteuerung und `/health` bleiben geschützt.
Öffentliche GUI-Suche ist für später vorgesehen.

Passwörter liegen als individuell gesalzene PBKDF2-HMAC-SHA256-Hashes mit 600.000
Iterationen vor. Zufällige Sitzungstokens werden nur als Hash gespeichert; Cookies
sind HttpOnly und SameSite=Strict. Steuerung benötigt zusätzlich CSRF-Schutz;
Anmeldeversuche werden dauerhaft begrenzt. Für Domains HTTPS verwenden. Der Proxy
muss fremde Forwarded-Header überschreiben und `X-Forwarded-Proto: https` setzen,
damit Cookies Secure erhalten. Direktes HTTP ist für vertrauenswürdige lokale
Testnetze möglich, verschlüsselt aber weder Zugangsdaten noch Verkehr.

## Produkt-API

Ein einfacher Test auf dem Server nutzt den aktuellen Schlüssel automatisch:

```sh
off-proxy test 0000527000057 beauty
```

Für curl den aktuellen Schlüssel aus der GUI kopieren und verdeckt eingeben:

```sh
read -r -s -p 'Aktueller API-Schlüssel: ' TOKEN
printf '\n'
curl -sS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8097/api/v3/product/4062139025398.json?product_type=all&lc=de&fields=code,product_name,product_name_de,brands,quantity,image_front_thumb_url'
unset TOKEN
```

| Parameter | Unterstützte Werte |
| --- | --- |
| `product_type` | `food` (Standard), `beauty`, `petfood`, `product`, `all` |
| `lc` | Sprache für ausgewählte Bild-URLs, etwa `de` oder `en` |
| `fields` | Kommagetrennte Felder der obersten Ebene; ohne Angabe/`all`/`raw` vollständiges Dokument |

Barcodes sind Ziffernfolgen mit höchstens 256 Zeichen; führende Nullen bleiben
erhalten. Die Antwort verwendet die OFF-v3-Produktstruktur. Treffer liefern 200.
Unbekannte Produkte liefern 404, wenn alle angefragten Bestände verfügbar sind,
andernfalls 503. Treffer können auch bei anderen noch fehlenden Beständen
zurückgegeben werden. `/health` benötigt immer den aktuellen API-Schlüssel.
`all_ready` bedeutet vorhandene Vollbestände; `all_synced` zusätzlich erfolgreiche
Delta-Prüfungen ohne bekannte Lücke. Keine allgemeine OFF-Suche, Schreib-API,
Barcode-Normalisierung oder vollständige Nachbildung berechneter Felder.
Schlüssel und Passwörter niemals in URLs eintragen.

## Deltas und Ausfälle

Der Dienst prüft alle sechs Stunden. Vorübergehende Zeitüberschreitungen, HTTP 429
oder 5xx lassen den Dateifortschritt unverändert; spätere Abgleiche versuchen erneut.
Andere Bestände laufen weiter. Unvollständige Delta-Dateien können schon einzelne
Produkte geändert haben, werden aber sicher wiederholt. Versionsprüfungen verhindern
das Überschreiben neuerer Produkte mit älteren Daten.

Start-/Endzeitstempel in Dateinamen bestimmen die Abdeckung. Fehlende Zeiträume
in einem erfolgreich geladenen Index oder dort genannte Dateien mit 404/410 werden
als dauerhafte Lücke vermerkt. Neuere verfügbare Deltas laufen standardmäßig weiter;
optional pausieren nur die neueren Aktualisierungen des betroffenen Bestands.
Vorhandene Produkte bleiben abfragbar. Eine zurückkehrende alte Datei kann die
Lücke schließen; andernfalls ist ein bestätigter Vollimport erforderlich.
Fehlende Änderungen innerhalb einer ansonsten gültigen Quelldatei sind so nicht erkennbar.

OFF hält üblicherweise ungefähr 14 Tage Deltas vor und liefert keine Löschmeldungen.
Wenige verpasste Tage werden nachgeholt, solange die Dateien verfügbar sind.
Abgelaufene Dateien starten keinen ungefragten Vollimport: Warnung und standardmäßige
Bestätigungspflicht bleiben bestehen. Optionale Vollabgleiche übernehmen auch
Löschungen. Die Quelladressen stehen in [app.py](../server/app.py); Bilder werden nicht heruntergeladen.

## Sicherungen, Fehler und Entfernen

Für eine konsistente Dateisicherung zuerst `off-proxy stop` ausführen. `.env`,
`.state`, aufbewahrte Quellcode-Versionen und **beide MongoDB-Verzeichnisse `data`
und `configdb`** sichern. Danach `off-proxy start`. Der Datenpfad steht in
`/opt/off-proxy-server/.state/runtime`. Sicherungen
enthalten API-Zugangsdaten und Passwort-Hashes; Zugriff beschränken und Wiederherstellung
getrennt testen. Software-Rollback ersetzt keine Datensicherung.

- GUI gesperrt: `off-proxy password`, danach Seite neu laden.
- Importfehler: `off-proxy status` und `off-proxy logs`; keine Daten löschen.
- Kein Speicherplatz: Host-Belegung einschließlich Docker-Images und Importkopien prüfen.
- Update zurückgestellt: laufenden Abgleich beenden lassen und erneut versuchen.
- Delta-Lücke: Fortsetzen/Pausieren wählen; Vollimport zu einem passenden Zeitpunkt bestätigen.
- Nach Update: Browserseite neu laden. Schlüsselwechsel benötigen keinen Neustart.

Zum Entfernen der Dienste `off-proxy down`. Verzeichnisse nur löschen, wenn auch
ihre Daten entfernt werden sollen. Es gibt kein globales Docker-Prune und keine
Bereinigung fremder Images. Aufbewahrte Anwendungsimages und Quellen erlauben Rollback.

## Entwicklung und Prüfungen

```sh
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements-dev.txt
.venv/bin/python -m pytest -q tests
```

Tests nutzen erzeugte Beispieldaten, keine echten Produkt-Dumps. `MONGO_TEST_URI`
kann auf eine separate MongoDB zeigen; erstellt/gelöscht werden nur zufällig benannte
Testdatenbanken. CLI-Tests simulieren Downloads/Docker. Ein zusätzlicher, ausdrücklich
aktivierter Docker-Test führt Installation, Schlüsselwechsel, Update und Rollback
wirklich aus, mit lokalen Quellarchiven und ohne OFF-Import. Nur als root mit
`DOCKER_SMOKE=1` auf einem entbehrlichen Docker-Testhost starten; verwendet werden
Port 8097 und das Compose-Projekt `off-proxy-server`. Niemals auf dem installierten Server ausführen.

CI prüft diese Abläufe, Testabdeckung, Ruff, Bandit, ShellCheck, Compose und Image-Build.
Laufzeitabhängigkeiten prüfen: `pip-audit -r server/requirements.txt`. Tests und Werkzeuge
bleiben für Nachvollziehbarkeit auf GitHub, gelangen aber weder in installierte
Versionen noch ins Anwendungsimage. Erfolgreiche Prüfungen sind keine Garantie für
vollständige Sicherheit oder volle OFF-API-Kompatibilität.

## Lizenz

Code: [MIT](../LICENSE), Nisbo. Produktdaten haben eigene Bedingungen:
**Open Food Facts contributors**, ODbL für die Datenbank, DbCL für Inhalte;
Bilder mit eigenen Lizenzen. [OFF-Daten und Nutzung](https://world.openfoodfacts.org/data).
Unabhängiges Projekt, kein offizieller OFF-Dienst. Keine Produkt-Dumps,
privaten Konfigurationen oder API-Zugangsdaten werden hier verteilt.
