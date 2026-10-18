"""Build per-category question files for the static site.

Reads data/pba/questions.json, data/pba/i18n/<lang>.json, data/pba/glossary.json and
data/pba/image_alts.json (Spanish alt text for every image, keyed by file stem),
applies the hand-made answer keys and corrections for later laws (answer_keys.json,
corrections.json), writes site/data/<category>.json and site/data/glossary.json, copies the WebP versions of
the images the questions use (data/pba/webp, made by make_webp.py) to site/img/, and writes the static pages for search engines
(site/preguntas/, site/sitemap.xml; see build_pages.py).
Everything is built aside and swapped in only when everything succeeded.

Usage: .venv/bin/python tools/build_site.py [data_dir] [site_dir]
"""
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from i18n import key as translation_key  # noqa: E402  (same key as the translation store)
from build_pages import build_pages  # noqa: E402

LANGS = ["en", "ru"]
SOURCE_URL = "https://www.gba.gob.ar/static/seguridadvial/docs/cuestionario.pdf"

# License category -> question groups it is examined on. The general block applies
# to every class; questions noted "para todas las clases menos para moto" skip A.
CATEGORIES = {
    "a": {"groups": {"general", "moto"}, "skip_note": "menos para moto"},
    "b": {"groups": {"general", "auto"}, "skip_note": None},
}

# Options that point at other options only make sense in the original order:
# "Ambas respuestas, A y B…", "Ninguna de las anteriores", "Opción A", "Cualquiera de los dos".
# Letters are matched case-sensitively: "A" is also a Spanish preposition ("A menor cantidad…").
FIXED_ORDER_RE = re.compile(
    r"(?i:anteriores|\bambas\s+(?:respuestas|opciones)|\btodas\s+las\s+(?:respuestas|opciones)"
    r"|\bcualquiera\s+de\s+(?:los|las)\s+dos)"
    r"|\b(?i:opci[oó]n(?:es)?|figura|imagen|señal|elementos|la|las)\s+[A-H]\b"
)


def norm(text):
    return re.sub(r"\W+", " ", text.lower()).strip()


def content_key(q, image_hashes):
    """Normalized text plus image bytes: questions that differ only by image stay distinct."""
    parts = [norm(q["es"]["q"]), *map(norm, q["es"]["answers"]), *image_hashes]
    return "\n".join(parts)


def stable_ids(questions, image_hash=lambda name: name):
    """Content-based ids, so stored progress survives re-parsing and reordering.

    `image_hash(name)` should return a hash of the image file; image-only variants
    ("La siguiente señal indica:") are told apart by it. Exact repeats of the same
    content get a "-n" suffix in bank order (they are dropped from the site anyway).
    """
    seen = Counter()
    owner = {}
    ids = []
    for q in questions:
        content = content_key(q, [image_hash(n) for n in q.get("images", [])])
        base = hashlib.sha1(content.encode()).hexdigest()[:8]
        if owner.setdefault(base, content) != content:
            raise SystemExit(f"id collision for {base}: two different questions hash alike")
        seen[base] += 1
        ids.append(base if seen[base] == 1 else f"{base}-{seen[base]}")
    return ids


def fixed_order(q):
    if q["type"] == "tf":  # always "Verdadero." / "Falso."
        return True
    return any(FIXED_ORDER_RE.search(a) for a in q["es"]["answers"])


def localize(q, store):
    def t(text):
        entry = store.get(translation_key(text))
        return entry["t"] if entry else None

    q_t = t(q["es"]["q"])
    answers_t = [t(a) for a in q["es"]["answers"]]
    if q_t is None or None in answers_t:
        return None
    return {"q": q_t, "answers": answers_t}


def apply_answer_keys(questions, entries):
    """Fill in keys the PDF leaves unmarked (data/pba/answer_keys.json).

    Every entry must match exactly one question that has no key of its own, and name
    existing options; anything else stops the build.
    """
    for entry in entries:
        matches = [q for q in questions if q["page"] == entry["page"] and q["es"]["q"] == entry["q"]]
        if len(matches) != 1:
            raise SystemExit(f"answer key matches {len(matches)} questions: p{entry['page']} {entry['q'][:60]!r}")
        q = matches[0]
        if q["correct"]:
            raise SystemExit(f"answer key for an already keyed question: {entry['q'][:60]!r}")
        answers = q["es"]["answers"]
        missing = [a for a in entry["correct"] if a not in answers]
        if missing:
            raise SystemExit(f"answer key names unknown options {missing} in {entry['q'][:60]!r}")
        q["correct"] = sorted(answers.index(a) for a in entry["correct"])
        if len(q["correct"]) > 1:
            q["type"] = "multi"
        q["key_basis"] = entry["basis"]
    return len(entries)


def apply_corrections(questions, entries):
    """Fix the 2019 bank where its answers no longer hold (data/pba/corrections.json).

    Each entry applies to every question with exactly its Spanish text and options (the PDF
    repeats some): "key" replaces the answer key, which must already exist, and attaches the
    note shown with the question; "drop" leaves the question out of the site, counted under
    the entry's "kind". Anything that does not match stops the build.
    """
    for entry in entries:
        matches = [q for q in questions
                   if q["es"]["q"] == entry["q"] and q["es"]["answers"] == entry["answers"]]
        if not matches:
            raise SystemExit(f"correction matches no question: {entry['q'][:60]!r}")
        for q in matches:
            if entry["action"] == "drop":
                q["dropped_for"] = entry["kind"]
                continue
            if entry["action"] != "key":
                raise SystemExit(f"unknown correction action {entry['action']!r}")
            answers = q["es"]["answers"]
            missing = [a for a in entry["correct"] if a not in answers]
            if missing or not q["correct"]:
                raise SystemExit(f"correction does not fit {entry['q'][:60]!r}: options {missing}, key {q['correct']}")
            q["correct"] = sorted(answers.index(a) for a in entry["correct"])
            if len(q["correct"]) > 1:
                q["type"] = "multi"
            q["fix"] = entry["note"]
    return len(entries)


def build_category(questions, ids, stores, spec):
    """Returns (items, dropped, warnings) for one license category."""
    out, dropped, warnings = [], Counter(), []
    by_text = {}
    for q, qid in zip(questions, ids):
        if q["group"] not in spec["groups"]:
            continue
        if spec["skip_note"] and any(spec["skip_note"] in n.lower() for n in q["notes"]):
            dropped["not for this class"] += 1
            continue
        if not q["correct"]:
            dropped["no answer key in source"] += 1
            continue
        if q.get("dropped_for"):
            dropped[f"corrections: {q['dropped_for']}"] += 1
            continue
        # Exact repeats without images add nothing to practice; keep the first copy,
        # but never lose an eliminatory flag and report inconsistent answer keys.
        text_key = (norm(q["es"]["q"]), tuple(map(norm, q["es"]["answers"])))
        if not q.get("images") and text_key in by_text:
            kept = by_text[text_key]
            if kept["correct"] != q["correct"]:
                warnings.append(f"duplicate {qid} has a different key than {kept['id']} "
                                f"(p{q['page']}), kept {kept['id']}")
            if q["eliminatory"]:
                kept["eliminatory"] = True
            dropped["duplicate"] += 1
            continue

        item = {"id": qid, "type": q["type"], "es": q["es"], "correct": q["correct"]}
        if q["eliminatory"]:
            item["eliminatory"] = True
        if fixed_order(q):
            item["fixedOrder"] = True
        if q.get("images"):
            item["img"] = [f"img/{webp_name(name)}" for name in q["images"]]
        if q.get("fix"):
            item["fix"] = q["fix"]
        for lang, store in stores.items():
            loc = localize(q, store)
            if loc:
                item[lang] = loc
            else:
                warnings.append(f"{qid} has no {lang} translation")
        item["src"] = {"page": q["page"], "section": q["section"]}
        if not q.get("images"):
            by_text[text_key] = item
        out.append(item)
    return out, dropped, warnings


def webp_name(name):
    """The site serves WebP copies; the JPEG sources stay what question ids are hashed from."""
    return Path(name).stem + ".webp"


def swap_in(tmp, final):
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)


def main():
    data = Path(sys.argv[1] if len(sys.argv) > 1 else "data/pba")
    site = Path(sys.argv[2] if len(sys.argv) > 2 else "site")
    questions = json.loads((data / "questions.json").read_text(encoding="utf-8"))
    stores = {lang: json.loads((data / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
              for lang in LANGS if (data / "i18n" / f"{lang}.json").exists()}

    def image_hash(name):
        return hashlib.sha1((data / "images" / name).read_bytes()).hexdigest()

    ids = stable_ids(questions, image_hash)  # before keys are added: ids depend on text only
    keys_file = data / "answer_keys.json"
    if keys_file.exists():
        count = apply_answer_keys(questions, json.loads(keys_file.read_text(encoding="utf-8"))["keys"])
        print(f"answer keys added by hand: {count}")
    fixes_file = data / "corrections.json"
    if fixes_file.exists():
        count = apply_corrections(questions, json.loads(fixes_file.read_text(encoding="utf-8"))["corrections"])
        print(f"corrections: {count}")

    data_tmp, img_tmp, pages_tmp = site / "data.tmp", site / "img.tmp", site / "pages.tmp"
    for tmp in (data_tmp, img_tmp, pages_tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)

    alts = json.loads((data / "image_alts.json").read_text(encoding="utf-8"))
    used_images = set()
    built = {}
    for cat, spec in CATEGORIES.items():
        items, dropped, warnings = build_category(questions, ids, stores, spec)
        for item in items:
            if item.get("img"):
                stems = [Path(p).stem for p in item["img"]]
                if not all(alts.get(stem) for stem in stems):
                    raise SystemExit(f"{item['id']}: add alt text for {stems} to image_alts.json")
                item["alt"] = [alts[stem] for stem in stems]
        built[cat] = items
        payload = {"category": cat.upper(), "source": SOURCE_URL, "questions": items}
        (data_tmp / f"{cat}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        for item in items:
            used_images.update(Path(p).name for p in item.get("img", []))
        elim = sum(1 for i in items if i.get("eliminatory"))
        print(f"{cat.upper()}: {len(items)} questions ({elim} eliminatory), left out {dict(dropped)}")
        for w in warnings:
            print(f"  warning: {w}")

    # Glossary page data: the same file the translations follow, minus the editor's note.
    glossary = json.loads((data / "glossary.json").read_text(encoding="utf-8"))
    glossary.pop("note", None)
    (data_tmp / "glossary.json").write_text(
        json.dumps(glossary, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    missing = sorted(name for name in used_images if not (data / "webp" / name).exists())
    if missing:
        raise SystemExit(f"no WebP version of {missing[:5]}…: run tools/make_webp.py")
    for name in sorted(used_images):
        shutil.copy2(data / "webp" / name, img_tmp / name)
    topics = build_pages(built, pages_tmp)

    swap_in(data_tmp, site / "data")
    swap_in(img_tmp, site / "img")
    swap_in(pages_tmp / "preguntas", site / "preguntas")
    (pages_tmp / "sitemap.xml").replace(site / "sitemap.xml")
    pages_tmp.rmdir()
    print(f"images: {len(used_images)}, topic pages: {topics}")


if __name__ == "__main__":
    main()
