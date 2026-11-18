# Changelog

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
