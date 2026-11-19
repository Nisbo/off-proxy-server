# Changelog

## 0.1.11

- EN: Replace Waitress with Gunicorn 27.x, one bounded threaded worker, no
  exposed Gunicorn control socket, and database initialization after fork.
- EN: Add authenticated DE/EN component dialogs, explicit update confirmation,
  installed versions, manual update checks, progress and reconnect support.
- EN: Install a systemd host request agent without exposing Docker to the GUI;
  pin Python build provenance, compare upstream images/releases, preserve data,
  sessions, settings and API keys. No automatic checks or updates.
- DE: Waitress durch Gunicorn 27.x ersetzt; begrenzter Thread-Worker, kein
  Gunicorn-Steuerungssocket und Datenbankinitialisierung nach dem Fork.
- DE: Geschützte DE/EN-Komponentenverwaltung mit Bestätigung, installierten
  Versionen, manueller Update-Prüfung, Fortschritt und Wiederverbindung ergänzt.
- DE: systemd-Host-Dienst für explizite Aufträge ohne Docker-Zugriff der GUI;
  Python-Build-Herkunft und veröffentlichte Images/Releases vergleichen.
  Daten, Sitzungen, Einstellungen und Schlüssel bleiben erhalten. Keine
  automatischen Prüfungen oder Updates.

## 0.1.10

- EN: Replace the development HTTP server with bounded Waitress WSGI serving;
  retain API routes, GUI authentication, sessions, CSRF and API key behavior.
- EN: Add manual `off-proxy components-update` for the installed source, refreshed
  Python/Linux base, compatible Waitress patches and MongoDB 8.0 patches. Build
  before downtime, defer during imports, pin images and recover previous images
  on failed activation. No automatic updates; data and credentials are retained.
- DE: Entwicklungs-Webserver durch Waitress mit begrenzten Verbindungen und
  Anfragen ersetzt; API, GUI-Anmeldung, Sitzungen und Schlüssel bleiben erhalten.
- DE: Manueller Befehl `off-proxy components-update` für Python-/Linux-Basis,
  passende Waitress-Patches und MongoDB 8.0. Build vor dem Neustart, Zurückstellen
  bei Importen und bisherige Images bei Startfehlern wiederherstellen. Keine
  automatischen Updates; Daten und Zugangsdaten bleiben erhalten.

## 0.1.9

- EN: Upgrade PyMongo to 4.18.3, enforce HTTPS source redirects and run the application
  without root. Preserve published snapshots after an ambiguous database acknowledgement;
  separate full-import completion from later delta failures.
- EN: Coordinate worker starts with updater maintenance, pin bootstrap/source commits,
  install runtime files only, and guard GUI responses after logout. Remove the GUI test
  banner and rewrite both guides. Add static checks and actual Docker management tests.
- DE: PyMongo auf 4.18.3 aktualisieren, HTTPS-Quellen erzwingen und Anwendung ohne Root
  betreiben. Veröffentlichte Bestände bei unklarer Datenbankbestätigung erhalten;
  Vollimport-Erfolg unabhängig von späteren Delta-Fehlern behandeln.
- DE: Abgleichstart und Updater abstimmen, Installer/Quellen auf denselben Commit festlegen,
  nur Laufzeitdateien installieren und verspätete GUI-Antworten nach Abmeldung verwerfen.
  GUI-Testhinweis entfernen, Anleitungen überarbeiten und Docker-/statische Prüfungen ergänzen.

## 0.1.8

- EN: Lower the GUI password minimum to eight characters in backend validation,
  terminal prompts, browser validation and both languages. Existing passwords remain valid.
- DE: Mindestlänge des GUI-Passworts auf acht Zeichen reduzieren: Backend, Terminal,
  Browser-Prüfung und beide Sprachen. Vorhandene Passwörter bleiben gültig.

## 0.1.7

- EN: Protect GUI data and controls with administrator login, salted password hashes,
  revocable persistent sessions, configurable inactivity expiry and login rate limits.
  Set/reset the password with `off-proxy password`; fresh interactive installs prompt
  directly. Preserve existing API keys, data and network settings.
- EN: Add key reveal/copy/generation/rotation and explicit optional keyless product
  API access. Management and GUI search always require login. Management commands
  use the current stored key after rotation. Public search remains deferred.
- DE: GUI-Daten und Steuerung mit Anmeldung, Passwort-Hashes, widerrufbaren dauerhaften
  Sitzungen, einstellbarem Inaktivitätsablauf und begrenzten Fehlversuchen schützen.
  Passwort über `off-proxy password` setzen/zurücksetzen; neue interaktive Installationen
  fragen direkt. Vorhandene Schlüssel, Daten und Netzwerkeinstellungen bleiben erhalten.
- DE: Schlüssel anzeigen/kopieren/generieren/wechseln; Produkt-API optional ausdrücklich
  ohne Schlüssel freigeben. Verwaltung und GUI-Suche bleiben geschützt. Shell-Befehle
  nutzen nach einem Wechsel den aktuellen Schlüssel. Öffentliche Suche später.

## 0.1.6

- EN: Scope the lookup form grid to the lookup form. Redesign settings and full-import
  confirmation dialogs with grouped fields, fixed action areas and a clear explanation
  of the staged import. Unify button sizing and remove the read-only lookup badge.
- DE: Suchformular-Layout auf die Suche begrenzen. Einstellungen und Vollimport-Abfrage
  mit gruppierten Feldern, festen Aktionsbereichen und Erklärung des sicheren
  Importablaufs überarbeiten. Buttongrößen vereinheitlichen, „Nur lesen“ entfernen.

## 0.1.5

- EN: Refresh display and queue manual synchronization through the existing worker.
  Persistent settings default to continuing available deltas, confirmed full imports
  only, and no regular full refresh. Optional automatic imports require explicit consent.
- EN: Track missing delta intervals and 404/410 files without treating temporary
  outages as gaps. Repair returning historical deltas, preserve incomplete coverage
  warnings, and optionally pause affected datasets. Add per-dataset full-import confirmation.
- DE: Anzeige aktualisieren und manuellen Datenabgleich über den vorhandenen Dienst
  anfordern. Dauerhafte Einstellungen: standardmäßig verfügbare Deltas fortsetzen,
  Vollimporte nur bestätigt und kein regelmäßiger Vollabgleich. Automatik nur nach Zustimmung.
- DE: Delta-Lücken und fehlende Dateien dauerhaft erfassen; vorübergehende Ausfälle
  gelten nicht als Lücke. Wieder verfügbare Deltas nachholen, Lücken anzeigen und
  betroffene Bestände optional pausieren. Vollimporte pro Bestand bestätigen.

## 0.1.4

Adds a German/English dashboard on the existing HTTP port: published dataset
counts, MongoDB storage, live import progress, worker state, next synchronization
and full-refresh due dates, and EAN lookup across all datasets. The dashboard
is intentionally unauthenticated for early local testing. The existing product
API and health endpoint remain token-protected; no token is sent to the browser.
Importer progress and scheduler metadata are additive. Existing product data,
credentials and bindings are preserved. Prominent early-development warnings
were added to the top of both READMEs.

## 0.1.3

First public repository version. Existing standalone prototype functionality:
full product mirror, read-only v3 product lookup, deltas and safe snapshot
publication. Adds the `off-proxy` installer/manager with prototype migration,
commit-specific updates, active-import checks and software rollback.
Database, API token, binding and port are preserved. No database schema change.
Pet-food source remains unchanged. No automatic upstream lookup yet.

## Prototype history

- 0.1.2: preserve and count source records without barcodes instead of aborting.
- 0.1.1: preserve numeric source identifiers longer than 32 characters.
- 0.1.0: initial local API/import proof of concept.
