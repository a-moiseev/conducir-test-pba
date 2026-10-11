import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build_pages  # noqa: E402


def item(qid, section, page=1, correct=(0,), **extra):
    out = {
        "id": qid,
        "es": {"q": f"Pregunta {qid} <b>", "answers": ["Sí & no", "No"]},
        "correct": list(correct),
        "src": {"page": page, "section": section},
    }
    out.update(extra)
    return out


class TopicNameTest(unittest.TestCase):
    def test_pdf_headings_are_cleaned(self):
        cases = {
            "4) Preguntas para todas las Clases: varias": "Preguntas generales",
            "7) Preguntas para todas las clases. : Adelantamiento": "Adelantamiento",
            "6) Peguntas para todas las clases: Velocidades": "Velocidades",
            "11) Preguntas para todas las clases: Giros y rotondas:": "Giros y rotondas",
            "3) Preguntas para la clase de motos:": "Motos (clase A)",
            "1) Preguntas para clase de Auto y Camioneta": "Autos y camionetas (clase B)",
            "Preguntas para todas las clases: actores en la via publica": "Actores en la vía pública",
            "14) Seguridad Activa y Pasiva": "Seguridad activa y pasiva",
        }
        for section, name in cases.items():
            self.assertEqual(build_pages.topic_name(section), name, section)

    def test_slugs_are_ascii(self):
        self.assertEqual(build_pages.slugify("Señales de tránsito e indicaciones"), "senales-de-transito-e-indicaciones")


class BuildPagesTest(unittest.TestCase):
    def test_questions_appear_once_with_their_classes(self):
        shared = item("s1", "1) Preguntas para todas las clases: Seguridad", page=2)
        moto = item("m1", "3) Preguntas para la clase de motos:", page=9, eliminatory=True)
        entries = build_pages.merge_categories({"b": [shared], "a": [moto, shared]})
        self.assertEqual([(i["id"], c) for i, c in entries], [("s1", ["A", "B"]), ("m1", ["A"])])

    def test_eliminatory_in_either_category_wins(self):
        plain = item("s1", "Seguridad")
        flagged = {**plain, "eliminatory": True}
        entries = build_pages.merge_categories({"a": [plain], "b": [flagged]})
        self.assertTrue(entries[0][0]["eliminatory"])
        self.assertNotIn("eliminatory", plain)

    def test_writes_escaped_topic_pages_and_sitemap(self):
        items = [item("s1", "1) Preguntas para todas las clases: Seguridad", correct=(1,)),
                 item("m1", "3) Preguntas para la clase de motos:", page=9, img=["img/0001.jpg"])]
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(build_pages.build_pages({"a": items}, tmp), 2)
            seguridad = (Path(tmp) / "preguntas" / "seguridad" / "index.html").read_text()
            self.assertIn("Pregunta s1 &lt;b&gt;", seguridad)
            self.assertIn("Sí &amp; no", seguridad)
            self.assertIn('<li class="is-right"><span class="sq__key">B</span><span>No', seguridad)
            self.assertIn('href="https://conducir.ar/preguntas/seguridad/"', seguridad)
            motos = (Path(tmp) / "preguntas" / "motos-clase-a" / "index.html").read_text()
            self.assertIn('<img src="/img/0001.jpg"', motos)
            sitemap = (Path(tmp) / "sitemap.xml").read_text()
            self.assertIn("<loc>https://conducir.ar/preguntas/motos-clase-a/</loc>", sitemap)
            self.assertTrue((Path(tmp) / "preguntas" / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
