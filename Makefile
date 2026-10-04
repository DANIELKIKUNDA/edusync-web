PYTHON ?= python

.PHONY: test compile hash finance-ts g2 zip

test:
	cd backend && PYTHONPATH=src $(PYTHON) -m pytest -q

compile:
	cd backend && PYTHONPATH=src $(PYTHON) -m compileall -q src tests


hash:
	node frontend/verify-offline-hash.mjs

finance-ts:
	npx tsc --noEmit --target ES2022 --module ESNext --moduleResolution Bundler --lib ES2022,DOM --strict frontend/src/offline/financeJournal.ts

g2:
	cd backend && PYTHONPATH=src $(PYTHON) scripts/g2_offline_finance_protocol_probe.py
