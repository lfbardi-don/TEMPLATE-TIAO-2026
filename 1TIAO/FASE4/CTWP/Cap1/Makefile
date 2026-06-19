# FarmTech Solutions — FASE 4 / CAP 1
# Pipeline shortcuts. Usage: `make setup`, `make pipeline`, `make run`.
PY := .venv/bin/python

.PHONY: help setup dataset eda train pipeline db-up db-down db-test run clean

help:
	@echo "Available targets:"
	@echo "  make setup     - create the venv (uv) and install dependencies"
	@echo "  make pipeline  - generate dataset + EDA + train models"
	@echo "  make db-up     - start PostgreSQL (docker compose)"
	@echo "  make db-test   - test the connection and insert a sample reading"
	@echo "  make run       - start the Streamlit dashboard"
	@echo "  make db-down   - stop PostgreSQL"
	@echo "  make clean     - remove generated dataset/models/figures"

setup:
	uv venv --python 3.13 .venv
	uv pip install --python $(PY) -r requirements.txt

dataset:
	$(PY) src/generate_dataset.py

eda:
	$(PY) src/eda.py

train:
	$(PY) src/train.py

pipeline: dataset eda train

db-up:
	docker compose up -d

db-down:
	docker compose down

db-test:
	$(PY) src/database.py

run:
	$(PY) -m streamlit run src/dashboard.py

clean:
	rm -f data/farmtech_soybean_dataset.csv src/models/*.pkl src/models/metrics.csv docs/figures/*.png
