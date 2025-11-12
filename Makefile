PYTHON ?= python

.PHONY: run test setup

run:
	$(PYTHON) -m uvicorn backend.main:app --reload

test:
	$(PYTHON) -m pytest

setup:
	$(PYTHON) -m pip install -r requirements.txt
