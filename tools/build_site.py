"""Build per-category question files for the static site.

Reads data/pba/questions.json, data/pba/i18n/<lang>.json and data/pba/glossary.json,
writes site/data/<category>.json and site/data/glossary.json, and copies the images the
questions use to site/img/.
Both directories are built aside and swapped in only when everything succeeded.

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

LANGS = ["ru"]
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
            item["img"] = [f"img/{name}" for name in q["images"]]
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

    ids = stable_ids(questions, image_hash)

    data_tmp, img_tmp = site / "data.tmp", site / "img.tmp"
    for tmp in (data_tmp, img_tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)

    used_images = set()
    for cat, spec in CATEGORIES.items():
        items, dropped, warnings = build_category(questions, ids, stores, spec)
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

    for name in sorted(used_images):
        shutil.copy2(data / "images" / name, img_tmp / name)
    swap_in(data_tmp, site / "data")
    swap_in(img_tmp, site / "img")
    print(f"images: {len(used_images)}")


if __name__ == "__main__":
    main()
