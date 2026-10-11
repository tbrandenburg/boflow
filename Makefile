BOFLOW_PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
BOFLOW := $(BOFLOW_PYTHON) src/boflow.py
.PHONY: help bootstrap init-home enroll register-user update login native update-system-tools status doctor logs open export-managed-flows lock check remove-user uninstall acceptance
help:
	@$(BOFLOW) --help
bootstrap:
	@bash bootstrap.sh
init-home:
	@$(BOFLOW) init-home --repo "$(BOFLOW_REPO)" --directory "$(BOFLOW_DIR)"
enroll:
	@$(BOFLOW) enroll --repo "$(BOFLOW_REPO)"
register-user:
	@$(BOFLOW) register-user $(if $(BOFLOW_PORT_BASE),--port-base "$(BOFLOW_PORT_BASE)")
update:
	@$(BOFLOW) update
login:
	@$(BOFLOW) login
native:
	@$(BOFLOW) native
update-system-tools:
	@$(BOFLOW) native --upgrade
status:
	@$(BOFLOW) status
doctor:
	@$(BOFLOW) doctor
logs:
	@$(BOFLOW) logs
open:
	@$(BOFLOW) open
export-managed-flows:
	@$(BOFLOW) export-managed-flows --directory "$(BOFLOW_DIR)"
lock:
	@$(BOFLOW) lock --directory "$(BOFLOW_DIR)"
remove-user:
	@$(BOFLOW) remove-user
uninstall: remove-user
acceptance:
	@$(BOFLOW_PYTHON) tests/native_roundtrip.py --port-base "$(or $(BOFLOW_PORT_BASE),11880)"
check:
	@$(BOFLOW_PYTHON) -m unittest discover -s tests -v
	@$(BOFLOW_PYTHON) -m compileall -q src tests
	@bash -n bootstrap.sh
