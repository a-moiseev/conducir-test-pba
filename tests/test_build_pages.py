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
                 item("m1", "3) Preguntas para la clase de motos:", page=9, img=["img/0001.jpg"],
                      alt=['Señal de "PARE"'])]
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(build_pages.build_pages({"a": items}, tmp), 2)
            seguridad = (Path(tmp) / "preguntas" / "seguridad" / "index.html").read_text()
            self.assertIn("Pregunta s1 &lt;b&gt;", seguridad)
            self.assertIn("Sí &amp; no", seguridad)
            self.assertIn('<li class="is-right"><span class="sq__key">B</span><span>No', seguridad)
            self.assertIn('href="https://conducir.ar/preguntas/seguridad/"', seguridad)
            motos = (Path(tmp) / "preguntas" / "motos-clase-a" / "index.html").read_text()
            self.assertIn('<img src="/img/0001.jpg" alt="Señal de &quot;PARE&quot;"', motos)
            self.assertIn('"@type": "BreadcrumbList"', motos)
            self.assertIn('<meta property="og:image" content="https://conducir.ar/og.png">', motos)
            sitemap = (Path(tmp) / "sitemap.xml").read_text()
            self.assertIn("<loc>https://conducir.ar/preguntas/motos-clase-a/</loc>", sitemap)
            self.assertTrue((Path(tmp) / "preguntas" / "index.html").exists())
            self.assertIn('href="/#/web"', seguridad)
            self.assertNotIn("hreflang", seguridad)  # no translations, no other languages
            self.assertFalse((Path(tmp) / "en").exists())

    def test_translated_pages_link_each_other(self):
        tr = {"en": {"q": "Question s1", "answers": ["Yes", "No"]},
              "ru": {"q": "Вопрос s1", "answers": ["Да", "Нет"]}}
        items = [item("s1", "1) Preguntas para todas las clases: Seguridad", correct=(1,), eliminatory=True,
                      fix={"es": "Corregida.", "en": "Fixed."}, **tr)]
        with tempfile.TemporaryDirectory() as tmp:
            build_pages.build_pages({"b": items}, tmp)
            en = (Path(tmp) / "en" / "questions" / "safety" / "index.html").read_text()
            self.assertIn('<html lang="en">', en)
            self.assertIn('Question s1<span class="trans" lang="es">Pregunta s1 &lt;b&gt;</span>', en)
            self.assertIn('<li class="is-right"><span class="sq__key">B</span><span>No<span class="trans" lang="es">No</span>'
                          '<span class="sq__mark">Correct answer</span>', en)
            self.assertIn('<p class="notice">Fixed.</p>', en)
            self.assertIn("Class B. Official question bank, p. 1.", en)
            self.assertIn('href="/?lang=en#/practice"', en)
            for code, path in [("es", "/preguntas/seguridad/"), ("en", "/en/questions/safety/"),
                               ("ru", "/ru/voprosy/safety/"), ("x-default", "/preguntas/seguridad/")]:
                self.assertIn(f'<link rel="alternate" hreflang="{code}" href="https://conducir.ar{path}">', en)
            ru = (Path(tmp) / "ru" / "voprosy" / "safety" / "index.html").read_text()
            self.assertIn("1 вопрос из официального", ru)
            self.assertIn('<p class="notice">Corregida.</p>', ru)  # no Russian note: Spanish one
            self.assertIn('<a href="/en/questions/safety/" hreflang="en" lang="en">English</a>', ru)
            sitemap = (Path(tmp) / "sitemap.xml").read_text()
            self.assertIn("<loc>https://conducir.ar/ru/voprosy/</loc>", sitemap)
            self.assertIn("<loc>https://conducir.ar/en/questions/safety/</loc>", sitemap)

    def test_language_with_a_missing_translation_is_left_out(self):
        tr = {"en": {"q": "Q", "answers": ["Yes", "No"]}}
        items = [item("s1", "Seguridad", **tr), item("s2", "Seguridad")]
        with tempfile.TemporaryDirectory() as tmp:
            build_pages.build_pages({"b": items}, tmp)
            self.assertFalse((Path(tmp) / "en").exists())
            self.assertFalse((Path(tmp) / "ru").exists())
            self.assertTrue((Path(tmp) / "preguntas" / "seguridad" / "index.html").exists())

    def test_ru_plural(self):
        forms = [build_pages.ru_plural(n, "вопрос", "вопроса", "вопросов") for n in (1, 2, 5, 11, 12, 21, 24, 112)]
        self.assertEqual(forms, ["вопрос", "вопроса", "вопросов", "вопросов", "вопросов", "вопрос", "вопроса", "вопросов"])


if __name__ == "__main__":
    unittest.main()
