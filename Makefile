PYTHON ?= .venv/bin/python
STREAMLIT ?= .venv/bin/streamlit

.PHONY: setup run ingest transform test app

setup:
	python3.11 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -r requirements.txt

run:
	$(PYTHON) -m src.pipeline

ingest:
	$(PYTHON) -m src.pipeline --ingest-only

transform:
	$(PYTHON) -m src.pipeline --transform-only

test:
	$(PYTHON) -m src.pipeline --test-only

app:
	$(STREAMLIT) run app/Home.py --server.headless true
