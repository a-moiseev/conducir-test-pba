PY := .venv/bin/python -I
PDF_URL := https://www.gba.gob.ar/static/seguridadvial/docs/cuestionario.pdf

.PHONY: venv fetch parse i18n-check site test serve

venv:
	python3 -m venv .venv
	.venv/bin/pip install -q -r requirements.txt

# Download the official question bank (Anexo I, Disposición 46/2019)
fetch:
	mkdir -p source
	curl -fL --retry 3 -o source/cuestionario.pdf $(PDF_URL)

# PDF -> data/pba/questions.json + data/pba/images/
parse:
	$(PY) tools/parse_cuestionario.py source/cuestionario.pdf data/pba

i18n-check:
	$(PY) tools/i18n.py check ru

# data/pba -> site/data/{a,b}.json + site/img/
site:
	$(PY) tools/build_site.py data/pba site

test:
	.venv/bin/python -m unittest discover -s tests
	npm test --silent

# Local preview at http://127.0.0.1:8000 (run `make site` first)
serve:
	cd site && python3 -m http.server 8000 --bind 127.0.0.1
