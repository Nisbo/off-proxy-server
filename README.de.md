> **Achtung: Frühe Entwicklung — derzeit nicht produktiv einsetzen. Updates können fehlschlagen. Eine getrennte Testinstallation und Datensicherungen verwenden.**

# OFF Proxy Server

[English](README.md) · [GitHub](https://github.com/Nisbo/off-proxy-server) · [Änderungen](CHANGELOG.md)

Ein selbst gehosteter Produktserver für Barcode-Abfragen mit lokaler Kopie von
**Open Food Facts, Open Beauty Facts, Open Pet Food Facts und Open Products Facts**.
Die vollständigen exportierten Produktdokumente bleiben erhalten. Bilder werden
als externe URLs verwendet und nicht heruntergeladen.

Unterstützt wird die Produktabfrage per Barcode, nicht die komplette OFF-API.
Namenssuche, Produktbearbeitung, öffentliche GUI-Suche und automatisches Nachladen
unbekannter Produkte fehlen noch. Die Anbindung an HA List Manager ist noch nicht enthalten.

## Voraussetzungen

- Linux, Bash, Docker mit Docker Compose v2, curl, tar und util-linux (`flock`).
  Installation und Verwaltung als root. Docker und Betriebssystempakete werden
  nicht automatisch installiert. Python, pip, Git und ein zusätzlicher Webserver
  sind auf dem Host nicht erforderlich.
- MongoDB 8 benötigt eine passende CPU; bei x86-64 ist AVX erforderlich.
- Als Ausgangspunkt etwa 2 CPU-Kerne und 2–4 GiB verfügbaren RAM für diese Dienste
  vorsehen. Die Containerlimits ergeben zusammen rund 2 GiB, ohne den Host.
- In einer Installation belegten etwa fünf Millionen Produkte **36 GiB auf Platte**
  und die Dienste nach dem Import ungefähr 1 GiB RAM. Für einen Vollimport müssen
  alter und neuer Bestand nebeneinander passen; bei dieser Messung waren etwa
  80–100 GiB freier Speicher eine Reserve. Das ist keine Größengarantie.
  Docker-Images, Sicherungen und Wachstum kommen hinzu. CPU-Limits begrenzen keine Plattenlast.

## Installieren und anmelden

In einer **Bash-Shell als root**:

```sh
set -o pipefail
curl -fsSL --proto '=https' https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/install.sh | bash
```

Der Installer fragt zweimal nach deinem selbst gewählten Administrator-Passwort
mit **8–256 Zeichen**. Eingabe und Einfügen bleiben verdeckt; es gibt keinen erzeugten
Einrichtungscode. Ohne interaktives Terminal bleibt die GUI gesperrt. Passwort
nachträglich festlegen oder zurücksetzen:

```sh
off-proxy password
```

Neue Installationen liegen unter `/opt/off-proxy-server`. Startskript und Anwendung
stammen aus demselben festgelegten GitHub-Commit. Installiert werden nur Laufzeitdateien,
keine Tests, CI-Konfiguration oder Entwicklungswerkzeuge. Die Anwendung läuft im
Container ohne Root-Rechte. MongoDB veröffentlicht keinen Host-Port. Andere
Container und Datenbanken werden nicht verändert.

Standardmäßig ist die Oberfläche **nur auf dem Server selbst** unter
`http://127.0.0.1:8097/` erreichbar. Für einen anderen Rechner `BIND_IP` in
`/opt/off-proxy-server/.env` auf die konkrete LAN-/VPN-Adresse des Servers setzen,
anschließend `off-proxy start` ausführen. `PORT` ist standardmäßig `8097`.
`0.0.0.0` gibt bewusst alle IPv4-Schnittstellen frei; besser eine konkrete Adresse
und eingeschränkten Netzwerkzugriff verwenden. Bindings außerhalb laufender
Importe ändern, weil Compose Container neu erstellen kann.

`http://<Serveradresse>:8097/` öffnen, anmelden und für jeden gewünschten Bestand
**Vollimport …** bestätigen. Es gibt keinen automatischen Erstimport. Lebensmittel
können beim ersten Import Stunden benötigen. Sobald der Installationsbefehl fertig
ist, läuft der Hintergrunddienst unabhängig von Shell und Browser weiter.

## Befehle im Alltag

| Befehl | Funktion |
| --- | --- |
| `off-proxy status` | Version und Status der Bestände |
| `off-proxy logs` | Abgleich-Logs verfolgen; Strg+C schließt nur die Ansicht |
| `off-proxy test 4062139025398 all` | Produkt in allen verfügbaren Beständen abfragen |
| `off-proxy password` | GUI-Passwort setzen/zurücksetzen und alle Sitzungen abmelden |
| `off-proxy update` | Aktuellen Commit von `main` herunterladen und aktivieren |
| `off-proxy update beta` | Neuestes veröffentlichtes Beta-Release installieren |
| `off-proxy update beta --head` | Aktuellen Commit von `beta` herunterladen und aktivieren |
| `off-proxy components-update` | Container-Komponenten manuell erneuern; Programmcode beibehalten |
| `off-proxy rollback` | Zur vorherigen lokal gespeicherten Software zurückkehren |
| `off-proxy stop` / `off-proxy start` | Diese Installation stoppen/starten; Daten behalten |
| `off-proxy down` | Nur eigene Container/Netzwerke entfernen; Daten behalten |

Derzeit gibt es **keine getrennten Stable-/Beta-Kanäle und keine unbeaufsichtigten
Updates**. Manuelle Updates folgen `main`; getrennte Veröffentlichungskanäle sind
noch zu besprechen. Derselbe Commit löst keinen erneuten Build oder Neustart aus.

Updates bauen das neue Image vor dem Stoppen, werden bei aktiven Importen
zurückgestellt und prüfen danach die API-Version. Hintergrunddienst und Updater
stimmen den Start eines Abgleichs über eine vorübergehende Wartungssperre ab.
Bei fehlgeschlagener Aktivierung wird versucht, die bisherigen Dienste wieder zu
starten. Nach einem abgebrochenen Updater läuft die Sperre innerhalb von zehn
Minuten aus. Sie setzt den aktualisierten Dienst voraus; alte Prototypen kennen
sie nicht. Daten, Passwörter, API-Schlüssel, Bindings und Einstellungen bleiben erhalten.

**Rollback stellt Software zurück, keine Datenbanksicherung.** Eine Rückkehr auf
Versionen vor 0.1.7 entfernt außerdem den GUI-Schutz und nutzt wieder den ursprünglichen
API-Schlüssel aus `.env`.

### Einmaliger Umstieg auf die Ordnerstruktur ab 0.1.20

Bis 0.1.19 erwartet der installierte Updater die Programmdateien im Root des
Archivs. Für den ersten Umstieg den aktuellen Installer einmal als root
ausführen:

```sh
curl -fsSL --proto '=https' https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/install.sh | bash
```

Der Installer erkennt die bestehende Installation und verwendet ihre Daten und
Einstellungen weiter. Bei einem eigenen Installationspfad hänge
`-s -- /pfad/zur/installation` an `bash` an. Anschließend funktioniert
`off-proxy update` wieder wie gewohnt. Rollback kann auch einen älteren,
lokal gespeicherten Stand im bisherigen Format starten.

### Upgrade von 0.1.10 oder älter / fehlende Laufzeitdateien

Alte Verwaltungsskripte kopieren eine feste Dateiliste. Beim Wechsel auf 0.1.11
kann deshalb vor dem Neustart `components.py: not found` auftreten. Einmal den
aktuellen Bootstrap-Installer statt des alten Updatebefehls verwenden:

```sh
curl -fsSL https://raw.githubusercontent.com/Nisbo/off-proxy-server/main/install.sh | bash
```

Er erkennt die vorhandene verwaltete Installation und behält Datenverzeichnis,
Einstellungen, Passwort, Sitzungen, API-Schlüssel und Netzwerkbindung. Unvollständige
Quell-Caches werden repariert. Bei einem eigenen Installationsverzeichnis stattdessen
`bash -s -- /dein/installationsverzeichnis` verwenden. Danach funktionieren Updates
wieder mit `off-proxy update`. Neue Laufzeitdateien stehen in `server/runtime-files.txt`
statt in einer unveränderlichen Liste des installierten Updaters. Die Produktdatenbank
wird vom Installer nicht gelöscht.

### Programm-Releases in der Oberfläche

Öffne **Komponenten → Programmupdates**, wähle **Stabil** oder **Beta** und
klicke auf **Nach Releases suchen**. Die Oberfläche prüft veröffentlichte
GitHub-Releases und zeigt Version und Release Notes. Mit **Release installieren …**
und anschließender Bestätigung startest du das Update. Der Host-Dienst prüft das
ausgewählte Release vor dem Wechsel erneut. Hat es sich geändert, starte eine
neue Prüfung.

Die Oberfläche merkt sich den Kanal in diesem Browser. Shell-Befehle ändern
diese Auswahl nicht. Die Oberfläche bietet neuere Releases und den Wechsel
auf einen veröffentlichten Commit derselben Version an. Für einen Rückschritt
gibt es die ausdrücklichen Shell-Befehle oder, wo anwendbar, `off-proxy rollback`.
Bestehende Installationen erhalten diese Funktion mit `off-proxy update`.

Stabile Releases verwenden einen Tag wie `v0.2.0`. Beta-Releases verwenden
einen als Pre-Release veröffentlichten Tag wie `v0.2.0-beta.1`. Die
`VERSION`-Datei im getaggten Stand muss genau dieser Version entsprechen.
Gibt es im gewählten Kanal kein veröffentlichtes Release, zeigt die Oberfläche
das an.

### Komponenten manuell aktualisieren

Diese Version zuerst mit `off-proxy update` installieren, danach:

```sh
off-proxy components-update
```

Der Befehl baut den **bereits installierten Programmstand** erneut, auch bei
gleichem Commit. Er lädt die neueste veröffentlichte Python-3.13-Containerbasis
samt Linux-Paketen, installiert die neueste passende Gunicorn-Version aus
**27.x** und erneuert MongoDB innerhalb von **8.0.x**. PyMongo bleibt auf der mit
dem Programm getesteten Version. Debian und Docker auf dem Host, ein eigener
Reverse Proxy und der Programmcode werden damit nicht aktualisiert. Neue
Versionsreihen von Python, MongoDB oder Gunicorn benötigen ein Programmupdate.
Es gibt **keine automatischen Komponenten-Updates** und keinen Update-Zeitplan.

Download und Build werden vor dem Stoppen abgeschlossen. Ein laufender Import
oder ein gerade gestarteter Abgleich stellt den Vorgang ohne Neustart zurück.
Nach einem kurzen Neustart muss die API-Prüfung mit dem aktuellen Schlüssel
bestehen. Eigene Image-Kennungen und ein festgehaltenes MongoDB-Image erhalten die
bisherigen Images für einen Wiederherstellungsversuch bei fehlgeschlagenem Start.
Datenbankdateien, Einstellungen, Passwort-Hashes, Sitzungen, API-Schlüssel,
Bindings und Programmstand bleiben erhalten. Es wird kein Vollimport angefordert.
Ein Software-Rollback macht ein erfolgreiches Komponenten-Update nicht rückgängig
und stellt keine Datenbankdateien zurück: vorher eine Datenbanksicherung erstellen.
Nach einer Unterbrechung den Befehl erneut ausführen; `.state` und Datenverzeichnisse
nicht löschen.

API und GUI verwenden jetzt **Gunicorn**, einen für den Produktivbetrieb ausgelegten
WSGI-Webserver, statt Pythons Entwicklungsserver. Anfragen und Verbindungen sind
begrenzt; der Container läuft weiterhin ohne Rootrechte. HTTPS übernimmt weiterhin
der Reverse Proxy. `X-Forwarded-Proto: https` dient ausschließlich wie bisher als
Hinweis für Secure-Cookies. Weitergeleitete Client-Adressen und Hosts werden nicht
für Identität oder Zugriffskontrollen übernommen. Der Proxy muss `Host` erhalten
und den Protokoll-Header selbst setzen.

### Komponenten-Updates in der GUI

**Komponenten** öffnet installierte Python-, Gunicorn- und MongoDB-Versionen,
Update-Verfügbarkeit, die letzte Prüfung und die aktuelle/letzte Aktion.
**Nach Updates suchen** vergleicht veröffentlichte Gunicorn-27.x-Versionen und die
Python-/MongoDB-Image-Digests mit den tatsächlich installierten Images. Fehlende
Build-Herkunft oder nicht erreichbare Quellen werden als **unbekannt** angezeigt,
niemals als aktuell. Änderungen der Python-/Linux-Basis erscheinen als Image-Update;
die genaue neue Python-Version steht erst nach der Installation fest. Die
Programmversion bleibt im Seitenkopf sichtbar; neuer Programmcode wird hier weder
geprüft noch installiert.

Wenn alle drei Komponenten als aktuell geprüft sind, ist **Komponenten
aktualisieren …** deaktiviert; auch die API lehnt dann ein normales Update ab.
Unbekannte oder unvollständige Prüfungen gelten nicht als aktuell. **Komponenten
erneut installieren …** steht separat mit eigener ausdrücklicher Bestätigung
bereit und baut die Komponenten auch ohne verfügbares Update neu auf. Daten,
Einstellungen und Schlüssel bleiben erhalten. Ein Versionspfeil erscheint nur
zwischen zwei bekannten, unterschiedlichen Gunicorn-Versionen. Der Shell-Befehl
`off-proxy components-update` bleibt ein ausdrücklich erzwungener Neuaufbau.

**Komponenten aktualisieren …** verlangt eine zusätzliche ausdrückliche Bestätigung.
Download, Build, Neustart und Prüfung werden angezeigt. Die geöffnete Seite verbindet
sich nach dem kurzen Neustart wieder; die bestehende Anmeldung bleibt erhalten.
Laufende Importe stellen Updates zurück. Unterbrochene, abgelaufene oder gescheiterte
Aufträge benötigen eine neue Benutzeraktion. Mehrfachklicks werden zusammengefasst.
Anzeige aktualisieren, Anmeldung, Dienststart und Booten planen **niemals ein Update
oder eine Netzwerkprüfung**. Nach einem ausdrücklich gestarteten Update wird das
Ergebnis einmal geprüft.

Installer/Updater richten auf unterstützten Docker-Hosts automatisch einen eigenen
systemd-Host-Dienst ein. Er wartet ausschließlich auf ausdrücklich bestätigte,
authentifizierte Aufträge und führt festgelegte Verwaltungsbefehle aus. Der
GUI-Container bekommt **keinen Docker-Socket und keinen Zugriff auf Host-Dateien**.
Debian benötigt dafür keine zusätzliche Python-Umgebung. Ohne systemd oder bei
fehlgeschlagenem Dienststart erklärt die GUI, dass Host-Aktionen nicht verfügbar
sind; die CLI funktioniert weiterhin. Einrichtung erneut versuchen:
`off-proxy host-agent install`.
Die Unit heißt `off-proxy-components-<Installations-ID>.service`; prüfen mit
`systemctl status 'off-proxy-components-*'`. Diagnoseausgaben bleiben lokal in
`.state/components.log` (letzter Auftrag, nach Abschluss maximal 1 MiB), nicht in
der GUI. Der Helfer startet keinen gestoppten Docker-Stack. Neustartregeln für
Container und Helfer starten nur Dienste neu; sie aktualisieren keine Software.

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
Löschungen. Die Quelladressen stehen in [app.py](app.py); Bilder werden nicht heruntergeladen.

## Sicherungen, Fehler und Entfernen

Für eine konsistente Dateisicherung zuerst `off-proxy stop` ausführen. `.env`,
`.state`, aufbewahrte Quellcode-Versionen und **beide MongoDB-Verzeichnisse `data`
und `configdb`** sichern. Danach `off-proxy start`. Der Datenpfad steht in
`/opt/off-proxy-server/.state/runtime`; bei früher übernommener Installation kann
er `/opt/off-local-api` sein und muss zusätzlich gesichert werden. Sicherungen
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

## Bestehende Prototypen übernehmen

Versionen 0.1.0–0.1.2 unter `/opt/off-local-api` werden weiterhin erkannt. Compose-Projekt,
Datenbankpfad und Konfiguration bleiben erhalten; die Datenbank wird weder kopiert
noch erneut importiert. Die bisherigen Quellen werden lokal gesichert.
Danach **nur `off-proxy`** verwenden, nicht das alte `manage.sh` oder Compose-Projekt.
Diese Kompatibilität ist vom normalen Einstieg für neue Installationen getrennt.

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

Code: [MIT](LICENSE), Nisbo. Produktdaten haben eigene Bedingungen:
**Open Food Facts contributors**, ODbL für die Datenbank, DbCL für Inhalte;
Bilder mit eigenen Lizenzen. [OFF-Daten und Nutzung](https://world.openfoodfacts.org/data).
Unabhängiges Projekt, kein offizieller OFF-Dienst. Keine Produkt-Dumps,
privaten Konfigurationen oder API-Zugangsdaten werden hier verteilt.
