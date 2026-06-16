PY := $(if $(wildcard venv/bin/python3),venv/bin/python3,python3)

.PHONY: lang logs start stop restart status policy-safe policy-dangerous install test lint fmt

# ── daemon operations ─────────────────────────────────────────────────────────

# Pass LANG=es or LANG=en to change language, e.g.: make lang LANG=es
lang:
	$(PY) -m mirach.cli lang $(LANG)

logs:
	$(PY) -m mirach.cli logs

start:
	$(PY) -m mirach.cli start

stop:
	$(PY) -m mirach.cli stop

restart:
	$(PY) -m mirach.cli restart

status:
	$(PY) -m mirach.cli status

# Permission policy toggle (safe = restrictive default, dangerous = no prompts)
policy-safe:
	$(PY) -m mirach.cli policy safe

policy-dangerous:
	$(PY) -m mirach.cli policy dangerous

# ── dev shortcuts ─────────────────────────────────────────────────────────────

install:
	pip install -e ".[dev]"

test:
	$(PY) -m pytest

lint:
	ruff check .

fmt:
	ruff check --fix . && ruff format .
