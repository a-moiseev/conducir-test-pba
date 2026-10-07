import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build_site  # noqa: E402


def q(text, answers, group="general", correct=(0,), notes=(), images=None, **extra):
    item = {
        "es": {"q": text, "answers": list(answers)},
        "group": group,
        "correct": list(correct),
        "notes": list(notes),
        "type": "choice",
        "eliminatory": False,
        "page": 1,
        "section": "",
    }
    if images:
        item["images"] = images
    item.update(extra)
    return item


class StableIdsTest(unittest.TestCase):
    def test_image_variants_get_independent_ids(self):
        sign = "La siguiente señal indica:"
        hashes = {"1.jpg": "aaa", "2.jpg": "bbb", "3.jpg": "ccc"}
        qs = [q(sign, ["A", "B"], images=["1.jpg"]), q(sign, ["A", "B"], images=["2.jpg"])]
        a, b = build_site.stable_ids(qs, hashes.get)
        self.assertNotEqual(a, b)
        # Inserting another sign before them must not change their ids.
        qs.insert(0, q(sign, ["A", "B"], images=["3.jpg"]))
        self.assertEqual(build_site.stable_ids(qs, hashes.get)[1:], [a, b])

    def test_exact_repeats_get_suffix(self):
        a, b = build_site.stable_ids([q("igual", ["x", "y"]), q("igual", ["x", "y"])])
        self.assertEqual(b, f"{a}-2")

    def test_ids_ignore_punctuation_and_case(self):
        one = build_site.stable_ids([q("¿Qué es?", ["Sí.", "No."])])
        two = build_site.stable_ids([q("qué es", ["sí", "no"])])
        self.assertEqual(one, two)

    def test_different_answers_different_id(self):
        a = build_site.stable_ids([q("Pregunta", ["Uno", "Dos"])])
        b = build_site.stable_ids([q("Pregunta", ["Uno", "Tres"])])
        self.assertNotEqual(a, b)


class FixedOrderTest(unittest.TestCase):
    def check(self, answers):
        return build_site.fixed_order(q("x", answers))

    def test_references_to_other_options(self):
        self.assertTrue(self.check(["Sí.", "No.", "Ambas respuestas, A y B, son correctas."]))
        self.assertTrue(self.check(["Uno.", "Ninguna de las anteriores."]))
        self.assertTrue(self.check(["Opción A.", "Opción B."]))
        self.assertTrue(self.check(["Las opciones A, B y C.", "Las opciones A y C."]))
        self.assertTrue(self.check(["Imagen A.", "Imagen B."]))
        self.assertTrue(self.check(["El peatón.", "El conductor.", "Cualquiera de los dos."]))

    def test_true_false_keeps_order(self):
        self.assertTrue(build_site.fixed_order(q("x", ["Verdadero.", "Falso."], type="tf")))

    def test_spanish_preposition_is_not_a_reference(self):
        self.assertFalse(self.check(["A menor cantidad de vehículos.", "A no más de 30 km/h."]))
        self.assertFalse(self.check(["El vehículo A, ya que circula por la derecha.", "Nadie."]))
        self.assertFalse(self.check(["Para las clases C, D y E.", "Para todas."]))
        self.assertFalse(self.check(["Con ambas manos sobre el volante.", "Con una."]))


class BuildCategoryTest(unittest.TestCase):
    def build(self, questions, cat="b", stores=None):
        ids = build_site.stable_ids(questions)
        items, dropped, self.warnings = build_site.build_category(
            questions, ids, stores or {}, build_site.CATEGORIES[cat])
        return items, dropped

    def test_groups_per_category(self):
        qs = [q("general", ["a", "b"]), q("auto", ["a", "b"], group="auto"),
              q("moto", ["a", "b"], group="moto"), q("taxi", ["a", "b"], group="taxi")]
        b, _ = self.build(qs, "b")
        a, _ = self.build(qs, "a")
        self.assertEqual([i["es"]["q"] for i in b], ["general", "auto"])
        self.assertEqual([i["es"]["q"] for i in a], ["general", "moto"])

    def test_drops_unkeyed_and_not_for_moto(self):
        qs = [q("sin clave", ["a", "b"], correct=()),
              q("marcha atrás", ["a", "b"], notes=["para todas las clases menos para moto"])]
        a, dropped = self.build(qs, "a")
        b, _ = self.build(qs, "b")
        self.assertEqual(a, [])
        self.assertEqual(dropped["no answer key in source"], 1)
        self.assertEqual([i["es"]["q"] for i in b], ["marcha atrás"])

    def test_text_duplicates_dropped_unless_they_have_images(self):
        qs = [q("igual", ["a", "b"]), q("igual", ["a", "b"]),
              q("señal", ["a", "b"], images=["1.jpg"]), q("señal", ["a", "b"], images=["2.jpg"])]
        items, dropped = self.build(qs)
        self.assertEqual(len(items), 3)
        self.assertEqual(dropped["duplicate"], 1)
        self.assertEqual(items[1]["img"], ["img/1.jpg"])

    def test_translation_attached_when_complete(self):
        key = build_site.translation_key
        store = {key("Hola"): {"t": "Привет"}, key("Sí"): {"t": "Да"}, key("No"): {"t": "Нет"}}
        items, _ = self.build([q("Hola", ["Sí", "No"])], stores={"ru": store})
        self.assertEqual(items[0]["ru"], {"q": "Привет", "answers": ["Да", "Нет"]})
        items, dropped = self.build([q("Hola", ["Sí", "Quizás"])], stores={"ru": store})
        self.assertNotIn("ru", items[0])
        self.assertEqual(len(items), 1)
        self.assertEqual(sum(dropped.values()), 0)
        self.assertEqual(len(self.warnings), 1)

    def test_duplicate_keeps_eliminatory_and_reports_key_conflict(self):
        qs = [q("igual", ["a", "b"]), q("igual", ["a", "b"], correct=(1,), eliminatory=True)]
        items, _ = self.build(qs)
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["eliminatory"])
        self.assertEqual(len(self.warnings), 1)


if __name__ == "__main__":
    unittest.main()
