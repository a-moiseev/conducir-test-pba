"""Parse the official PBA question bank PDF into JSON.

Source: https://www.gba.gob.ar/static/seguridadvial/docs/cuestionario.pdf
(Anexo I, IF-2019-33101289-GDEBA-DPPYSVMGGP). The PDF has a real text layer:
the correct answer is printed in green, eliminatory questions carry a red
"(Pregunta de carácter eliminatorio)" mark, section headings are bold >= 14pt.

Usage: .venv/bin/python tools/parse_cuestionario.py [pdf] [out_dir]
"""
import json
import re
import shutil
import sys
from pathlib import Path

import pymupdf

GREEN = 0x90C852
RED = 0xEE302E

HEADER_MAX_Y = 70     # "Dirección Provincial / de Política y Seguridad Vial"
FOOTER_MIN_Y = 760    # page number, IF-... id, "BATERÍA DE PREGUNTAS Y RESPUESTAS"
CONTINUATION_GAP = 4  # max vertical gap (pt) between wrapped lines of one paragraph
HANGING_INDENT = 8    # wrapped answer lines are indented by ~14pt
IMAGE_DPI = 110

# "A. ", "a) ", "a-\t", "A – ", "• ", ".• " and a bare letter followed by a tab ("C\t"); matched on raw text
ANSWER_RE = re.compile(r"^\s*\.?\s*(?:[A-Ha-h]\s*[.)]|[A-H]\t|[A-H] {2,}|[A-Ha-h]\s*[-–](?:\t|\s+)|•)\s*")
TF_RE = re.compile(r"^V\s+F$")
QNUM_RE = re.compile(r"^\d{1,3}\s*[)-]\s*")
ELIM_RE = re.compile(r"\(?\s*Pregunta\s+de\s+car[aá]cter\s+eliminatorio\s*\)?", re.I)
DANGLING_ELIM_RE = re.compile(r"\(\s*(?:Pregunta(?:\s+de(?:\s+car[aá]cter)?)?)?\s*$", re.I)
# Typos in the source that would otherwise reach the site verbatim.
SOURCE_TYPOS = {"1, 5 metros": "1,5 metros"}
NOTE_RE = re.compile(r"\(\s*(Bah[ií]a Blanca|para todas las clases menos para moto)\s*\)", re.I)

# Section heading keyword -> question group. Headings that match nothing are
# only sub-topics (e.g. "SEÑALES DE TRANSITO") and keep the current group.
GROUPS = [
    ("traccion a sangre", "traccion_sangre"),
    ("todas las clases", "general"),
    ("seguridad activa y pasiva", "general"),
    ("auto y camioneta", "auto"),
    ("camionetas y vehículos de carga", "carga_liviana"),
    ("clase de motos", "moto"),
    ("urgencia", "emergencia"),
    ("taxis", "taxi"),
    ("transporte de cargas", "carga"),
    ("sin acoplado", "camion"),
    ("con acoplado", "camion_acoplado"),
    ("pasajeros", "pasajeros"),
]


def clean(text):
    text = text.replace("\t", " ").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def join_lines(parts):
    """Join wrapped lines, undoing end-of-line hyphenation ("co-" + "rreaje")."""
    out = ""
    for part in parts:
        part = clean(part)
        if not part:
            continue
        if re.search(r"[a-záéíóúñ]-$", out) and part[:1].islower():
            out = out[:-1] + part
        else:
            out = f"{out} {part}" if out else part
    return out


def iter_items(doc):
    """Yield page content in reading order: text lines and image blocks."""
    for pno in range(1, doc.page_count - 1):  # first page is the cover, last the signature
        page = doc[pno]
        for block in page.get_text("dict")["blocks"]:
            x0, y0, x1, y1 = block["bbox"]
            if y1 < HEADER_MAX_Y or y0 > FOOTER_MIN_Y:
                continue
            if block["type"] == 1:
                if y1 - y0 > 20:
                    yield {"kind": "image", "page": pno + 1, "bbox": block["bbox"]}
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                yield {
                    "kind": "line",
                    "page": pno + 1,
                    "bbox": line["bbox"],
                    "spans": spans,
                    "raw": "".join(s["text"] for s in line["spans"]),
                    "text": clean("".join(s["text"] for s in line["spans"])),
                }


def is_green(spans):
    green = sum(len(s["text"].strip()) for s in spans if s["color"] == GREEN)
    total = sum(len(s["text"].strip()) for s in spans)
    return total > 0 and green * 2 > total


def is_heading(item):
    s = item["spans"][0]
    bold = "Bold" in s["font"] or "Medi" in s["font"]
    return bold and s["size"] >= 13.5


def is_subheading(item):
    s = item["spans"][0]
    return ("Bold" in s["font"] and s["color"] == GREEN and round(s["size"]) == 11
            and not ANSWER_RE.match(item["raw"]) and not TF_RE.match(item["text"]))


class Parser:
    def __init__(self):
        self.questions = []
        self.cur = None
        self.group = "general"
        self.section = ""
        self.topic = ""
        self.heading_buf = []
        self.last = None  # previous text item, for continuation checks
        self.in_answer = False  # previous text item was (part of) an answer option
        self.answer_x = 0  # left edge of the last answer marker
        self.pending_bullet = False

    def flush_heading(self):
        if not self.heading_buf:
            return
        text = join_lines(self.heading_buf)
        self.heading_buf = []
        low = text.lower()
        for key, group in GROUPS:
            if key in low:
                self.group = group
                self.section = text
                self.topic = ""
                return
        self.topic = text

    def finish(self):
        if self.cur:
            self.questions.append(self.cur)
        self.cur = None

    def new_question(self, item):
        self.finish()
        self.cur = {
            "page": item["page"],
            "group": self.group,
            "section": self.section,
            "topic": self.topic,
            "q_parts": [],
            "q_green": [],
            "answers": [],  # [{"parts": [...], "correct": bool, "letter": "a"}]
            "images": [],
            "eliminatory": False,
            "type": "choice",
        }

    def continues(self, item):
        last = self.last
        return (last is not None and last["page"] == item["page"]
                and item["bbox"][1] - last["bbox"][3] < CONTINUATION_GAP)

    def feed(self, item):
        was_answer, self.in_answer = self.in_answer, False
        self._feed(item, was_answer)

    def _feed(self, item, was_answer):
        bullet, self.pending_bullet = self.pending_bullet, False
        if item["kind"] == "image":
            self.flush_heading()
            if self.cur is None or self.cur["answers"]:
                self.new_question(item)
            self.cur["images"].append((item["page"], item["bbox"]))
            self.last = None
            return

        text = item["text"]

        if is_heading(item):
            if self.heading_buf and not self.continues(item):
                self.flush_heading()
            self.finish()
            self.heading_buf.append(text)
            self.last = item
            return
        self.flush_heading()

        wraps_answer = was_answer and (
            self.continues(item) or item["bbox"][0] - self.answer_x >= HANGING_INDENT)
        if is_subheading(item) and not wraps_answer:
            self.finish()
            self.topic = text
            self.last = item
            return

        if ELIM_RE.fullmatch(text):  # the mark on its own line, sometimes printed black
            if self.cur:
                self.cur["eliminatory"] = True
            self.last = item
            return

        red = [s for s in item["spans"] if s["color"] == RED]
        if red:
            rest = [s for s in item["spans"] if s["color"] != RED]
            if not rest:  # the mark on its own line follows the question's options
                if self.cur:
                    self.cur["eliminatory"] = True
                self.last = item
                return
            # Mark at the end of a line: it belongs to whatever question this line
            # ends up in, which may be a new one ("73) Inhabilitados...(Pregunta").
            self.pending_bullet = bullet
            self._feed({**item, "spans": rest, "text": clean("".join(s["text"] for s in rest)),
                        "raw": "".join(s["text"] for s in rest)}, was_answer)
            if self.cur:
                self.cur["eliminatory"] = True
            return

        if TF_RE.match(text):
            if self.cur is None:
                return
            v_green = any(s["color"] == GREEN and "V" in s["text"] for s in item["spans"])
            self.cur["type"] = "tf"
            self.cur["answers"] = [
                {"parts": ["Verdadero."], "correct": v_green},
                {"parts": ["Falso."], "correct": not v_green},
            ]
            self.last = item
            return

        if text == "•":  # bullet drawn apart from its "\tVerdadero." line
            self.pending_bullet = True
            return
        if self.cur is not None and (ANSWER_RE.match(item["raw"]) or bullet):
            self.answer_x = item["bbox"][0]
            m = ANSWER_RE.match(item["raw"])
            marker = m.group(0) if m else "•"  # detached bullet case
            self.cur["answers"].append({
                "parts": [ANSWER_RE.sub("", item["raw"])],
                "correct": is_green(item["spans"]),
                "letter": next((c.lower() for c in marker if c.isalpha()), ""),
                "green": [s["text"] for s in item["spans"] if s["color"] == GREEN],
            })
            self.last = item
            self.in_answer = True
            return

        if self.cur is not None and self.cur["answers"]:
            indented = item["bbox"][0] - self.answer_x >= HANGING_INDENT
            lowercase = text[:1].islower()  # new questions never start lowercase
            if was_answer and (self.continues(item) or indented or lowercase):
                answer = self.cur["answers"][-1]
                answer["parts"].append(text)
                answer["correct"] = answer["correct"] or is_green(item["spans"])
                answer.setdefault("green", []).extend(
                    s["text"] for s in item["spans"] if s["color"] == GREEN)
                self.last = item
                self.in_answer = True
                return
            self.new_question(item)
        elif self.cur is None or (self.cur["q_parts"] and QNUM_RE.match(text)):
            # a numbered line ("138) ...") always opens a new question
            self.new_question(item)

        self.cur["q_parts"].append(text)
        self.cur["q_green"].append(is_green(item["spans"]))
        self.last = item

    def close(self):
        self.flush_heading()
        self.finish()


def finalize(raw, idx):
    # Option "a)" printed without its marker: options start at "b)" and the last
    # question line is really the first option ("210) La siguiente señal indica:" / "Hotel.").
    missing_a = False
    if raw["answers"][0].get("letter") == "b":
        if len(raw["q_parts"]) > 1:
            raw["answers"].insert(0, {"parts": [raw["q_parts"].pop()],
                                      "correct": raw["q_green"].pop()})
        else:
            missing_a = True
    # Two options printed on one line: "... pocos metros. C. Sí, siempre que ..."
    split = []
    for a in raw["answers"]:
        text = join_lines(a["parts"])
        nxt = chr(ord("a") + len(split) + 1).upper()
        m = re.search(rf"(?<=\.)\s+{nxt}\.\s+(?=[A-ZÁÉÍÓÚ¿])", text)
        if m:
            print(f"split inline option p{raw['page']}: {text[m.start():][:50]!r}")
            first, second = text[:m.start()], text[m.end():]
            green = [clean(g) for g in a.get("green", []) if clean(g)]

            def green_share(half):
                return sum(len(g) for g in green if g in half) * 2 > len(half)

            split += [{"parts": [first], "correct": green_share(first)},
                      {"parts": [second], "correct": green_share(second)}]
        else:
            split.append(a)
    raw["answers"] = split
    correct = [i for i, a in enumerate(raw["answers"]) if a["correct"]]
    q = join_lines(raw["q_parts"])
    eliminatory = raw["eliminatory"] or bool(ELIM_RE.search(q))
    q = ELIM_RE.sub("", q)
    q = DANGLING_ELIM_RE.sub("", q)
    notes = [m.group(1) for m in NOTE_RE.finditer(q)]
    q = clean(NOTE_RE.sub("", q))
    q = QNUM_RE.sub("", q)
    qtype = raw["type"] if len(correct) <= 1 else "multi"
    answers = []
    for a in raw["answers"]:
        text = re.sub(r"\s+X$", "", join_lines(a["parts"]))  # stray checkbox mark
        for typo, fixed in SOURCE_TYPOS.items():
            text = text.replace(typo, fixed)
        if ELIM_RE.search(text):
            eliminatory = True
            text = clean(ELIM_RE.sub("", text))
        answers.append(text)
    return {
        "id": idx,
        "page": raw["page"],
        "group": raw["group"],
        "section": raw["section"],
        "topic": raw["topic"],
        "type": qtype,
        "eliminatory": eliminatory,
        "notes": notes,
        "es": {"q": q, "answers": answers},
        "correct": correct,
        "_images": raw["images"],
        "_missing_a": missing_a,
    }


def save_images(doc, question, img_dir):
    """Render image regions (with vector overlays like red circles/arrows) to JPEG."""
    by_page = {}
    for page, bbox in question.pop("_images"):
        r = pymupdf.Rect(bbox)
        by_page[page] = by_page[page] | r if page in by_page else r
    names = []
    for n, (page, rect) in enumerate(sorted(by_page.items())):
        name = f"{question['id']:04d}" + (f"-{n + 1}" if n else "") + ".jpg"
        pix = doc[page - 1].get_pixmap(clip=rect, dpi=IMAGE_DPI)
        pix.save(img_dir / name, jpg_quality=72)
        names.append(name)
    if names:
        question["images"] = names


def validate(questions):
    problems = []
    for q in questions:
        why = []
        if not q["es"]["q"]:
            why.append("empty question text")
        if len(q["es"]["answers"]) < 2:
            why.append(f"{len(q['es']['answers'])} answers")
        if not q["correct"]:
            why.append("no answer key")
        if any(not a for a in q["es"]["answers"]):
            why.append("empty answer")
        if q.pop("_missing_a", False):
            why.append("options start at b)")
        if why:
            problems.append((q["id"], q["page"], ", ".join(why), q["es"]["q"][:80]))
    return problems


def main():
    pdf = Path(sys.argv[1] if len(sys.argv) > 1 else "source/cuestionario.pdf")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/pba")
    img_dir = out / "images"

    doc = pymupdf.open(pdf)
    parser = Parser()
    for item in iter_items(doc):
        parser.feed(item)
    parser.close()

    # Lines without answer options are sub-headings or a fill-in table, not questions.
    skipped = [raw for raw in parser.questions if not raw["answers"]]
    questions = [finalize(raw, i) for i, raw in
                 enumerate(r for r in parser.questions if r["answers"])]
    # Render into a temp dir and swap it in only after everything succeeded.
    tmp_dir = out / "images.tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)
    for q in questions:
        save_images(doc, q, tmp_dir)

    problems = validate(questions)
    (out / "questions.json").write_text(
        json.dumps(questions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    shutil.rmtree(img_dir, ignore_errors=True)
    tmp_dir.rename(img_dir)

    groups = {}
    for q in questions:
        groups[q["group"]] = groups.get(q["group"], 0) + 1
    print(f"questions: {len(questions)}  images: {sum(len(q.get('images', [])) for q in questions)}"
          f"  eliminatory: {sum(q['eliminatory'] for q in questions)}"
          f"  true/false: {sum(q['type'] == 'tf' for q in questions)}"
          f"  multi: {sum(q['type'] == 'multi' for q in questions)}")
    print("groups:", groups)
    for raw in skipped:
        print(f"skipped (no options) p{raw['page']}: {join_lines(raw['q_parts'])[:80]!r}")
    print(f"problems: {len(problems)}")
    for p in problems:
        print("  #{} p{}: {} | {}".format(*p))
    # Unkeyed questions are a known gap of the source; anything else is a parser bug.
    unexpected = [p for p in problems if p[2] != "no answer key"]
    if unexpected:
        sys.exit(f"{len(unexpected)} unexpected problems")


if __name__ == "__main__":
    main()
