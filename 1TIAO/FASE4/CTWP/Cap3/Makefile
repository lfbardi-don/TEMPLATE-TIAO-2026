# Da Terra ao Código — FASE 4 / CAP 3
# Classificação de grãos de trigo (Seeds Dataset). Usage: `make setup`, `make pipeline`.
PY := .venv/bin/python
NOTEBOOK := src/seeds_classification.ipynb

.PHONY: help setup data notebook pipeline lab clean

help:
	@echo "Available targets:"
	@echo "  make setup     - create the venv (uv) and install dependencies"
	@echo "  make data      - build the clean labeled CSV from the raw UCI file"
	@echo "  make notebook  - execute the notebook end-to-end (writes outputs in place)"
	@echo "  make pipeline  - data + notebook (full reproducible run)"
	@echo "  make lab       - open JupyterLab to explore the notebook interactively"
	@echo "  make clean     - remove generated CSVs, models, figures and outputs"

setup:
	uv venv --python 3.13 .venv
	uv pip install --python $(PY) -r requirements.txt

data:
	$(PY) src/data.py

notebook:
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace \
		--ExecutePreprocessor.timeout=600 $(NOTEBOOK)

pipeline: data notebook

lab:
	$(PY) -m jupyter lab $(NOTEBOOK)

clean:
	rm -f data/seeds_clean.csv
	rm -f src/models/*.csv src/models/*.json src/models/*.pkl
	rm -f docs/figures/*.png
