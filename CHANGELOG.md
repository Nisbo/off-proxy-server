# Changelog

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
