# Changelog

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
