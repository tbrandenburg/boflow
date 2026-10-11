BOFLOW_PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
BOFLOW := $(BOFLOW_PYTHON) src/boflow.py
.DEFAULT_GOAL := help
.PHONY: help setup approve open status update doctor logs native remove-user export-managed-flows lock check acceptance
help:
	@printf '%s\n' 'Everyday:' '  setup    Guided installation or resume (create/join household)' '  approve  Admin approves a member’s public enrollment request' '  open     Open your tools' '  status   Service and update status' '  update   Check household updates now' '' 'Maintenance (see AGENTS.md):' '  doctor / logs       Diagnose problems locally' '  native              Install missing native packages; UPGRADE=1 upgrades' '  remove-user         Remove startup; retain all data' '  export-managed-flows / lock BOFLOW_DIR=...   Prepare household changes' '  check               Developer checks; no native installation' '  acceptance          Explicit Ubuntu native roundtrip on disposable account'
setup:
	@bash setup.sh
approve:
	@bash bootstrap.sh
	@.venv/bin/python src/boflow.py approve
open status update doctor logs remove-user:
	@$(BOFLOW) $@
native:
	@$(BOFLOW) native $(if $(filter 1,$(UPGRADE)),--upgrade,)
export-managed-flows lock:
	@$(BOFLOW) $@ --directory "$(BOFLOW_DIR)"
check:
	@$(BOFLOW_PYTHON) -m unittest discover -s tests -v
	@$(BOFLOW_PYTHON) -m compileall -q src tests
	@bash -n bootstrap.sh setup.sh

acceptance:
	@$(BOFLOW_PYTHON) tests/native_roundtrip.py --port-base "$(or $(BOFLOW_PORT_BASE),11880)"
