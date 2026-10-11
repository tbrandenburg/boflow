PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
BOFLOW := $(PYTHON) src/boflow.py
.PHONY: help bootstrap init-home enroll register-user update login native update-system-tools status doctor logs open export-managed-flows lock check remove-user
help:
	@$(BOFLOW) --help
bootstrap:
	@bash bootstrap.sh
init-home:
	@$(BOFLOW) init-home --repo "$(REPO)" --directory "$(DIR)"
enroll:
	@$(BOFLOW) enroll --repo "$(REPO)"
register-user:
	@$(BOFLOW) register-user
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
	@$(BOFLOW) export-managed-flows --directory "$(DIR)"
lock:
	@$(BOFLOW) lock --directory "$(DIR)"
remove-user:
	@$(BOFLOW) remove-user
check:
	@$(PYTHON) -m unittest discover -s tests -v
	@$(PYTHON) -m compileall -q src tests
	@bash -n bootstrap.sh
