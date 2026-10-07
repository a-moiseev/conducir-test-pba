"""Translation store for the PBA question bank.

Translations live in data/pba/i18n/<lang>.json as {key: {"es": source, "t": translation}},
keyed by a hash of the Spanish string, so they survive re-parsing and identical strings
("Verdadero.", "Ninguna de las anteriores.") are translated once.

  i18n.py pending <lang> [--limit N] [--groups general,auto,moto]   untranslated strings, question order
  i18n.py apply <lang> <file.json>                                  merge {key: translation}
  i18n.py check <lang> [--groups ...]                               coverage and sanity checks
  i18n.py prune <lang>                                              drop entries whose source is gone
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DATA = Path("data/pba")
DEFAULT_GROUPS = "general,auto,moto"


def key(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def load_questions(groups):
    qs = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))
    return [q for q in qs if q["group"] in groups]


def source_strings(questions):
    """Spanish strings in question order, deduplicated."""
    seen, out = set(), []
    for q in questions:
        for text in [q["es"]["q"], *q["es"]["answers"]]:
            k = key(text)
            if k not in seen:
                seen.add(k)
                out.append((k, text, q["id"]))
    return out


def store_path(lang):
    return DATA / "i18n" / f"{lang}.json"


def load_store(lang):
    path = store_path(lang)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_store(lang, store):
    path = store_path(lang)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")


def numbers(text):
    text = re.sub(r"(?<=[cс][mм])3\b", "³", text, flags=re.I)  # "cm3"/"см3" is a unit
    return sorted(re.findall(r"\d+(?:[.,]\d+)?", text))


def cmd_pending(args):
    store = load_store(args.lang)
    pending = [(k, t, qid) for k, t, qid in source_strings(load_questions(args.groups))
               if k not in store]
    print(f"# pending {len(pending)}", file=sys.stderr)
    batch = pending[: args.limit]
    last_q = None
    for k, text, qid in batch:
        if qid != last_q:
            print(f"## q{qid}")
            last_q = qid
        print(f"{k}\t{text}")


def cmd_apply(args):
    store = load_store(args.lang)
    sources = {k: t for k, t, _ in source_strings(load_questions(set(DEFAULT_GROUPS.split(",")) | args.groups))}
    new = json.loads(Path(args.file).read_text(encoding="utf-8"))
    unknown = [k for k in new if k not in sources]
    if unknown:  # source text changed after a re-parse: re-translate those strings
        print(f"skipped {len(unknown)} stale keys: {unknown[:10]}", file=sys.stderr)
    for k, t in new.items():
        if k in unknown:
            continue
        store[k] = {"es": sources[k], "t": t.strip()}
    save_store(args.lang, store)
    print(f"applied {len(new)}, store has {len(store)}")


def cmd_check(args):
    store = load_store(args.lang)
    strings = source_strings(load_questions(args.groups))
    missing = [k for k, _, _ in strings if k not in store]
    issues = []
    for k, text, qid in strings:
        entry = store.get(k)
        if not entry:
            continue
        t = entry["t"]
        if not t:
            issues.append((qid, k, "empty"))
        elif numbers(text) != numbers(t):
            issues.append((qid, k, f"numbers {numbers(text)} -> {numbers(t)}"))
        elif re.search(r"[áéíóúñ¿¡]", re.sub(r"\([^)]*\)", "", t)):
            issues.append((qid, k, "spanish letters left"))  # Spanish terms are allowed in (...)
        elif re.search(r"[а-яё][a-z]|[a-z][а-яё]", t, re.I):
            issues.append((qid, k, "mixed latin/cyrillic word"))
    print(f"{args.lang}: {len(strings) - len(missing)}/{len(strings)} translated, {len(issues)} issues")
    for qid, k, why in issues:
        print(f"  q{qid} {k}: {why} | {store[k]['es'][:70]!r} -> {store[k]['t'][:70]!r}")


def cmd_prune(args):
    store = load_store(args.lang)
    live = {k for k, _, _ in source_strings(load_questions(args.groups))}
    stale = [k for k in store if k not in live]
    for k in stale:
        print(f"  drop {k}: {store.pop(k)['es'][:70]!r}")
    save_store(args.lang, store)
    print(f"pruned {len(stale)}, store has {len(store)}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pending", "apply", "check", "prune"):
        p = sub.add_parser(name)
        p.add_argument("lang")
        if name == "apply":
            p.add_argument("file")
        p.add_argument("--groups", default=DEFAULT_GROUPS, type=lambda s: set(s.split(",")))
        if name == "pending":
            p.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    {"pending": cmd_pending, "apply": cmd_apply, "check": cmd_check,
     "prune": cmd_prune}[args.cmd](args)


if __name__ == "__main__":
    main()
