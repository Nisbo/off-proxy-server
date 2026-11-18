# OFF Proxy Server

[English](README.md) · [GitHub](https://github.com/Nisbo/off-proxy-server)

Ein kleiner selbst gehosteter Produktserver mit lokaler MongoDB-Kopie der
Open-Food-Facts-Datenbestände. Für Barcode-Abfragen und Anwendungen wie den
HA List Manager. **Frühe Version: unterstützt die Produktabfrage, keinen
vollständigen Nachbau aller OFF-API-Funktionen.**

## Funktionen

- Vollständige exportierte Produktdatensätze aus Lebensmittel, Kosmetik,
  Tiernahrung und sonstigen Produkten. Bilder bleiben externe URLs.
- EAN-Abfrage über `/api/v3/product/<barcode>.json`, mit `product_type`,
  Auswahl einfacher Felder über `fields` und `lc` für Bildauswahl.
- Vollimport im Hintergrund, Delta-Prüfung alle sechs Stunden, Vollabgleich
  nach 30 Tagen sowie bei fehlenden Änderungszeiträumen.
- Veröffentlichung eines Vollimports erst nach dessen vollständigem Erfolg.
- Wiederholbare Deltas mit Schutz gegen Überschreiben durch ältere Produktstände.
- Datensätze ohne Barcode bleiben erhalten und werden separat gezählt;
  führende Nullen und ungewöhnliche Quellcodes bleiben erhalten.
- API mit Zugangsschlüssel, zunächst nur lokal erreichbar. Kein veröffentlichter
  Datenbank-Port.
- Kurze Befehle für Installation, Updates, Status, Logs, Produkttest und Rücknahme.

**Noch nicht enthalten:** Namenssuche, Benutzer-Schreibzugriffe oder automatische
OFF-Abfragen bei unbekannten Codes. Letzteres ist als optionale Erweiterung
geplant, die gefundene Originaldaten lokal zwischenspeichert.

## Voraussetzungen

Linux mit Bash, Docker, Docker Compose v2, curl, tar und util-linux (`flock`).
Installation und Verwaltung erfolgen als root. Auf dem Host werden kein Python,
pip, Git, zusätzlicher Webserver oder Datenbankdienst benötigt. MongoDB 8 setzt
eine kompatible CPU voraus; bei x86-64 ist AVX erforderlich.

Als Ausgangspunkt etwa 2 CPU-Kerne und 2–4 GiB RAM für die Dienste vorsehen.
In einer bisherigen Installation belegten knapp fünf Millionen vollständige
Produktdatensätze 36 GiB und die Dienste nach dem Import rund 1 GiB RAM.
Das ist eine Messung, keine Garantie für andere Systeme oder künftige Datenmengen.
Vollimporte brauchen vorübergehend Platz für alten und neuen Bestand; bei dieser
Größe sind etwa 80–100 GiB freier Speicher vor dem Import eine Reserve.
Docker-Images, Bilder, Sicherungen und Wachstum kommen gegebenenfalls dazu.
CPU-Limits begrenzen keine Plattenlast.

## Installation und Übernahme des Prototyps

Als root in die Shell kopieren:

```sh
curl -fsSL https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/install.sh | bash
```

Die Skripte [install.sh](install.sh) und [off-proxy](off-proxy) sind vollständig
einsehbar. Der Installer lädt einen bestimmten GitHub-Commit, baut das Image
und startet ein eigenes Compose-Projekt. Andere Container werden nicht verändert;
es werden keine apt-Pakete installiert.

Neue Installationen liegen unter `/opt/off-proxy-server`. Der zufällige
API-Schlüssel wird in `.env` mit Dateirechten 600 gespeichert. Daten und
Konfiguration liegen außerhalb der ausgetauschten Quellcode-Versionen.
Updates beziehen sich zunächst auf `main`; stabile Releases gibt es noch nicht.

**Ein vorhandener Prototyp unter `/opt/off-local-api` wird automatisch erkannt:**

- Unterstützung für Versionen 0.1.0 bis 0.1.2.
- Datenbank bleibt in `data` und `configdb` am bisherigen Ort.
- Docker-Projektname `off-local-api` bleibt erhalten; keine zweite Datenbank.
- `.env` mit Schlüssel, Adresse und Port wird unverändert übernommen.
- Alte Dateien bleiben unverändert, eine Quellcode-Sicherung erlaubt die Rücknahme.
- Ein laufender Import verhindert das Update zunächst, bevor Dienste gestoppt werden.
- Die Übernahme allein löst keinen erneuten Vollimport aus. Der reguläre
  Aktualisierungsplan gilt weiterhin.

**Danach `off-proxy` verwenden**, nicht mehr das alte `manage.sh` oder die alte
Compose-Datei. Weitere Einstellungen gehören in `/opt/off-proxy-server/.env`;
die alte `.env` bleibt als historische Kopie bestehen.

## Befehle

```sh
off-proxy status
off-proxy logs
off-proxy test 0000527000057 beauty
off-proxy test 4062139025398 food
off-proxy update
off-proxy rollback
off-proxy stop
off-proxy start
off-proxy down
```

`logs`: Strg+C schließt nur die Ansicht. `stop` erhält sämtliche Daten; `down`
entfernt zusätzlich die eigenen Container und Netzwerke. `start` startet die
vorhandene Version. `rollback` wechselt zur vorherigen Software, stellt aber
keine Datenbanksicherung wieder her. Diese Version ändert kein Datenbankschema.

Updates bauen das neue Image vor dem Stoppen der bisherigen Dienste und prüfen
danach die neue API-Version. Bei fehlgeschlagener Aktivierung wird versucht,
die bisherigen Dienste wieder zu starten. Ohne neuen Commit wird nichts neu
gestartet. Quellcode-Versionen bleiben für die Rücknahme lokal gespeichert.

Die Shell erst schließen, wenn der Installations-/Updatebefehl fertig ist.
Anschließende Importe laufen selbstständig im Hintergrund, gegebenenfalls
mehrere Stunden. Ein unterbrochener, unfertiger Vollimport beginnt erneut;
bereits veröffentlichte Bestände bleiben erhalten.

## API-Test mit curl

Nach erfolgreichem Kosmetikimport auf dem Server:

```sh
TOKEN=$(sed -n 's/^API_TOKEN=//p' /opt/off-proxy-server/.env)
curl -sS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8097/api/v3/product/0000527000057.json?product_type=beauty&fields=code,product_name,brands,quantity'
unset TOKEN
```

`product_type`: `food` (Standard), `beauty`, `petfood`, `product`, `all`.
`/health` benötigt denselben Schlüssel und meldet alle vier Bestände.
`all_ready` bedeutet, dass die Vollimporte vorhanden sind; `all_synced` zusätzlich,
dass der letzte Delta-Abgleich überall erfolgreich war. Bei unvollständigen
Beständen kommt für unbekannte EANs 503 statt einer irreführenden 404-Antwort.

Die API bietet einfache Produktfelder und die vom List Manager benötigte
Produktabfrage. Keine allgemeine OFF-Suche, Schreib-API, vollständige Nachbildung
berechneter Felder, Barcode-Normalisierung oder Weiterleitungen. Der List Manager
benötigt für die Nutzung noch eine separate Serveradresse-/Token-Einstellung.
Dieses Projekt verändert Home Assistant nicht.

Für Site-to-Site-Zugriff später `BIND_IP` in `.env` auf die konkrete VPN-/LAN-Adresse
des Servers setzen und `off-proxy start` verwenden. Außerhalb laufender Importe
ändern: geänderte Umgebungseinstellungen können Container neu erstellen.
VPN oder HTTPS für die Übertragung nutzen; API nicht pauschal öffentlich freigeben.

## Quellen und Aktualisierung

Die vier ursprünglichen JSONL-Quellen sind eingerichtet. Ein Quellenfehler wird
angezeigt und erneut versucht; andere Bestände werden unabhängig verarbeitet.
Die Tiernahrungsquelle wird in dieser Version bewusst nicht auf einen anderen
Spiegel umgestellt.

OFF stellt ungefähr 14 Tage Deltas bereit, ohne Löschmeldungen. Löschungen
werden durch Vollabgleich übernommen. Bei einer Größenabnahme des Vollbestands
um mehr als 25 Prozent wird zur Prüfung abgebrochen. Abgebrochene Delta-Dateien
können einzelne Produkte bereits aktualisiert haben; der Dateifortschritt wird
erst nach erfolgreichem Ende gespeichert und die Datei gegebenenfalls wiederholt.

## Entfernen

Zuerst `off-proxy down`. Danach können Programmordner und Befehlsdatei manuell
entfernt werden. Bei übernommener Installation liegen die Daten weiterhin unter
`/opt/off-local-api`: diesen Ordner nur bei ausdrücklich gewünschter Datenlöschung
entfernen. Kein Befehl führt eine globale Docker-Bereinigung aus. Images bleiben
im Docker-Cache.

## Entwicklung und Lizenz

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Unit-Tests verwenden mongomock. CLI-Tests simulieren Docker/GitHub und prüfen
insbesondere Daten-/Schlüsselerhalt, Übernahme, Updatefehler, Importschutz und
Rücknahme. Mit `MONGO_TEST_URI=mongodb://127.0.0.1:27017/` werden die Datenbanktests
gegen echte MongoDB ausgeführt. Dafür werden ausschließlich eigene, zufällig
benannte Testdatenbanken angelegt und entfernt. GitHub CI prüft beide Varianten,
Shell-/Compose-Konfiguration und Docker-Build.

Programmcode: [MIT](LICENSE), Nisbo. Die Produktdaten haben eine eigene Lizenz:
**Open Food Facts contributors**, ODbL für die Datenbank und DbCL für Inhalte;
Bilder unterliegen eigenen Bedingungen. [OFF-Daten und Nutzungsbedingungen](https://world.openfoodfacts.org/data).
Keine Produkt-Dumps, privaten Konfigurationen oder Schlüssel im Repository.
Unabhängiges Projekt, kein offizieller OFF-Dienst.
