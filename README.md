# Test de Conducir — Provincia de Buenos Aires

A free practice tool for the **Province of Buenos Aires** (PBA) driver's-license theory exam,
built on the official question bank, with Russian (and later English) translations.

> Unofficial. The questions and answer keys come from the province's published study material;
> the real exam may differ. Always check the official sources before your test.

## Source

The question bank is the official PDF published by the Dirección Provincial de Política y
Seguridad Vial:
[`cuestionario.pdf`](https://www.gba.gob.ar/static/seguridadvial/docs/cuestionario.pdf)
— *Anexo I: Preguntas Examen Teórico Licencia de Conducir* (IF-2019-33101289-GDEBA-DPPYSVMGGP,
Disposición 46/2019).

The PDF has a real text layer, so the bank is parsed automatically:

- the correct option is printed in green;
- eliminatory questions are marked *(Pregunta de carácter eliminatorio)*;
- bold headings split the bank into general questions (all license classes) and
  class-specific sections (cars, motorcycles, trucks, taxis, …).

Known gaps in the source: some questions have no answer key (most of them in the heavy-vehicle
sections), and some answers predate later law changes (e.g. *Alcohol Cero*). The parser reports
unkeyed questions instead of guessing. For the car and motorcycle classes the missing keys are
filled in by hand in `data/pba/answer_keys.json`, each with its basis: a keyed twin of the same
question elsewhere in the bank, the official *Manual del Conductor*, Ley 24.449, or plain
arithmetic.

## Repository layout

```
tools/parse_cuestionario.py   PDF -> data/pba/questions.json + data/pba/images/
tools/i18n.py                 translation store: pending / apply / check
data/pba/questions.json       parsed bank (Spanish), one record per question
data/pba/images/              question images cropped from the PDF
data/pba/i18n/ru.json         Russian translations, keyed by a hash of the Spanish text
data/pba/glossary.json        road terms (es / en / ru): translation reference and glossary page
data/pba/answer_keys.json     answer keys the PDF leaves unmarked, with sources
```

### Question record

```json
{
  "id": 0,
  "page": 2,
  "group": "general",
  "section": "Preguntas para todas las clases: actores en la via publica",
  "topic": "",
  "type": "tf",
  "eliminatory": false,
  "notes": [],
  "es": {"q": "…", "answers": ["Verdadero.", "Falso."]},
  "correct": [0],
  "images": ["0000.jpg"]
}
```

- `group`: `general` (all classes), `auto`, `moto`, `carga`, `taxi`, `pasajeros`, …
- `type`: `choice`, `tf` (true/false) or `multi` (several correct options).
- `correct`: indices of the correct options; empty when the source has no answer key.

### Translations

Style: accurate and neutral, plain "you"; options must stay exactly as (un)obvious as in the
original, so a translation never hints at the answer. References to options ("A y B") keep Latin
letters. Argentine documents and terms with no local equivalent keep the Spanish name in
parentheses (cédula azul, VTV, patente), because that is what the exam calls them. Terminology
follows `data/pba/glossary.json`.

Translations are stored per Spanish string, not per question, so they survive re-parsing and
identical strings ("Verdadero.", "Ninguna de las anteriores.") are translated once:

```json
{"1948296a8f70": {"es": "Según la Organización…", "t": "По данным Всемирной…"}}
```

### Site data

`tools/build_site.py` turns the bank into one file per license category
(`site/data/a.json`, `site/data/b.json`) and copies the images they use to `site/img/`:

- category **A** (motorcycles) = general + motorcycle questions, **B** (cars) = general + car questions;
- questions without an answer key and exact text duplicates are left out;
- every question gets a content-based `id` (hash of its normalized text and image bytes), so
  stored progress survives re-parsing and reordering;
- `fixedOrder` marks true/false questions and questions whose options refer to each other
  ("Ambas respuestas, A y B…", "Ninguna de las anteriores"): their options are not shuffled;
- both output directories are built aside and swapped in only after a successful build.

## Site

`site/` is a static single-page app: plain HTML, CSS and ES modules, no build step, no
backend. Progress is kept in the browser's `localStorage`.

```
site/index.html
site/css/style.css
site/js/app.js              views and routing (#/, #/practice, #/exam, #/review, #/glossary)
site/js/lib/                pure logic, unit-tested with node --test
  progress.js               Leitner boxes and next-question selection
  readiness.js              chance of passing the real exam
  exam-rules.js             official exam format
  exam.js                   draw and score a mock exam
  question.js, strings.js, storage.js, random.js
```

Questions are shown in the selected language with the Spanish original always underneath,
because the real exam is in Spanish. The mock exam is in Spanish only, like the real one.

The mock exam draws 5 eliminatory and 35 regular questions, shows results only at the end,
and feeds its answers into practice progress. A running exam survives a page reload.

"Review mistakes" drills only the questions whose latest answer (in practice or an exam) was
wrong; a right answer takes a question out of that pool.

The glossary page lists road terms from `data/pba/glossary.json`, alphabetically within each section, with a translation into the
interface language (English for the Spanish interface); search ignores accents.

Practice uses five Leitner boxes: a wrong answer sends a question back to box 1 (it returns
after a few other questions), three right answers in a row make it "learned".

The pass estimate follows the official rules (Manual del Conductor, Disposición 46/2019:
40 questions, 5 of them eliminatory, at least 75 % correct and every eliminatory question right):

    P(pass) = pE^5 * P(Binomial(35, pN) >= 25)

where `pE` and `pN` are the average chances of answering an eliminatory / regular question
correctly, estimated from the box each question is in.

The visual language borrows from Argentine road signage: the pass estimate is drawn as a
speed-limit roundel, colours are semantic (informative blue for actions, regulatory red for
eliminatory questions and wrong answers, motorway green for correct ones), and the single
typeface is Overpass, a descendant of the Highway Gothic road-sign lettering.

## Usage

```sh
make venv      # create .venv and install PyMuPDF
make fetch     # download the official PDF into source/
make parse     # rebuild data/pba from the PDF
make i18n-check
make site      # build site/data and site/img
make test      # Python and JavaScript unit tests
make serve     # preview at http://127.0.0.1:8000
```

Translation workflow:

```sh
.venv/bin/python tools/i18n.py pending ru --limit 200   # untranslated strings, in question order
.venv/bin/python tools/i18n.py apply ru batch.json      # merge {key: translation}
.venv/bin/python tools/i18n.py check ru                 # coverage, numbers, leftover Spanish
.venv/bin/python tools/i18n.py prune ru                 # drop translations of removed strings
```
