"""Static, indexable pages for search engines: every question with its answer, one page per topic.

The app itself stays a single page that loads the whole bank at once; these pages are what
search engines see and where search visitors land. They link to the app in their language.

    /preguntas/                topics with question counts (Spanish)
    /preguntas/<topic>/        every question of the topic, correct answers marked
    /en/questions/<topic>/     the same in English, Spanish original under each line
    /ru/voprosy/<topic>/       the same in Russian
    /sitemap.xml

The language versions point at each other with hreflang; Spanish is the x-default.
"""
import json
import re
import unicodedata
from html import escape
from pathlib import Path

SITE_URL = "https://conducir.ar"
APP_NAME = "Test de Conducir PBA"
LETTERS = "ABCDEFGH"

# Section headings of the PDF, cleaned up ("4) Preguntas para todas las Clases: varias").
# Headings not listed here keep their own wording.
TOPIC_NAMES = {
    "varias": "Preguntas generales",
    "preguntas para la clase de motos": "Motos (clase A)",
    "preguntas para clase de auto y camioneta": "Autos y camionetas (clase B)",
    "actores en la via publica": "Actores en la vía pública",
    "seguridad activa y pasiva": "Seguridad activa y pasiva",
    "señales de tránsito e indicaciones": "Señales de tránsito e indicaciones",
}


# Topic names in the other languages, keyed by the Spanish name; their slugs come from English.
TOPIC_TRANSLATIONS = {
    "Actores en la vía pública": ("Road users", "Участники дорожного движения"),
    "Adelantamiento": ("Overtaking", "Обгон"),
    "Autopistas": ("Motorways", "Автомагистрали"),
    "Autos y camionetas (clase B)": ("Cars and pickups (class B)", "Легковые автомобили и пикапы (класс B)"),
    "Conducción segura": ("Safe driving", "Безопасное вождение"),
    "Documentación": ("Documents", "Документы"),
    "Estacionamiento": ("Parking", "Стоянка"),
    "Giros y rotondas": ("Turns and roundabouts", "Повороты и круговое движение"),
    "Intoxicación y otros factores de riesgo en la conducción":
        ("Alcohol, drugs and other risk factors", "Алкоголь, лекарства и другие факторы риска"),
    "Luces": ("Lights", "Фары и огни"),
    "Motos (clase A)": ("Motorcycles (class A)", "Мотоциклы (класс A)"),
    "Preguntas generales": ("General questions", "Общие вопросы"),
    "Seguridad": ("Safety", "Безопасность"),
    "Seguridad activa y pasiva": ("Active and passive safety", "Активная и пассивная безопасность"),
    "Semáforo": ("Traffic lights", "Светофор"),
    "Señales de tránsito e indicaciones": ("Road signs and signals", "Дорожные знаки и сигналы"),
    "Velocidades": ("Speed", "Скорость"),
}


def ru_plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _elim_es(elim):
    return f" {elim} son eliminatorias: si respondés mal una en el examen, desaprobás." if elim else ""


def _elim_en(elim):
    if not elim:
        return ""
    if elim == 1:
        return " One question here is eliminatory: a wrong answer to it on the exam means you fail."
    return f" {elim} questions here are eliminatory: a wrong answer to any of them on the exam means you fail."


def _elim_ru(elim):
    if not elim:
        return ""
    if elim == 1:
        return " Один вопрос здесь критический: ошибка в нём на экзамене — и экзамен не сдан."
    return f" Критических вопросов здесь {elim}: ошибка в любом из них на экзамене — и экзамен не сдан."


def _q_ru(n):
    return f"{n} {ru_plural(n, 'вопрос', 'вопроса', 'вопросов')}"


# Everything that differs between the language versions of the pages.
LANGS = {
    "es": {
        "root": "/preguntas/", "app": "/", "locale": "es_AR", "name": "Español",
        "home": "Inicio", "index_crumb": "Preguntas del examen",
        "index_title": "Preguntas del examen de manejo PBA con respuestas",
        "index_h1": "Preguntas del examen teórico de manejo de la Provincia de Buenos Aires",
        "index_desc": lambda total: (f"Las {total} preguntas oficiales del examen teórico de la licencia de conducir "
                                     "de la Provincia de Buenos Aires, por tema y con respuestas."),
        "index_intro": lambda total: (
            f"Las {total} preguntas del cuestionario oficial para las licencias clase A (motos) y "
            "clase B (autos y camionetas), ordenadas por tema y con la respuesta correcta marcada. "
            "El examen tiene 40 preguntas: aprobás con 30 correctas y las 5 eliminatorias bien."),
        "topic_title": lambda name: f"{name}: preguntas del examen de manejo PBA",
        "topic_desc": lambda n, name: (f"{n} preguntas de «{name}» del examen teórico de la licencia de conducir "
                                       "de la Provincia de Buenos Aires, con las respuestas correctas."),
        "topic_intro": lambda n, elim: (f"{n} preguntas del cuestionario oficial del examen teórico de manejo de la "
                                        "Provincia de Buenos Aires, con la respuesta correcta marcada." + _elim_es(elim)),
        "practice": "Practicar con el simulador", "exam": "Hacer un simulacro de examen",
        "prev": "Anterior", "next": "Siguiente",
        "eliminatory": "Eliminatoria", "right": "Respuesta correcta",
        "classes": lambda c: ("Clase " if len(c) == 1 else "Clases ") + " y ".join(c),
        "source_page": lambda page: f"Cuestionario oficial, pág. {page}.",
        "disclaimer": ("Herramienta no oficial. Las preguntas y respuestas salen del cuestionario publicado por la "
                       "Dirección Provincial de Política y Seguridad Vial; el examen real puede variar."),
        "all": "Todas las preguntas", "about": "Acerca del sitio",
        "promo": "¿Necesitás un sitio web para tu negocio?",
    },
    "en": {
        "root": "/en/questions/", "app": "/?lang=en", "locale": "en_US", "name": "English",
        "home": "Home", "index_crumb": "Exam questions",
        "index_title": "Buenos Aires driving test questions in English, with answers",
        "index_h1": "Province of Buenos Aires driving theory test questions in English",
        "index_desc": lambda total: (f"All {total} official questions of the Province of Buenos Aires driving "
                                     "theory test in English, by topic, with the Spanish original and the answers."),
        "index_intro": lambda total: (
            f"All {total} questions of the official question bank for class A (motorcycles) and class B "
            "(cars and pickups) licenses, by topic, translated into English with the Spanish original and "
            "the correct answer marked. The exam has 40 questions and is in Spanish: you pass with 30 "
            "correct and all 5 eliminatory ones right."),
        "topic_title": lambda name: f"{name}: Buenos Aires driving test questions in English",
        "topic_desc": lambda n, name: (f"{n} “{name}” questions of the Province of Buenos Aires driving theory "
                                       "test in English, with the Spanish original and the correct answers."),
        "topic_intro": lambda n, elim: (
            f"{n} questions of the official theory exam question bank of the Province of Buenos Aires, "
            "translated into English, with the Spanish original under each line and the correct answer "
            "marked. The exam itself is in Spanish." + _elim_en(elim)),
        "practice": "Practice with the simulator", "exam": "Take a mock exam (in Spanish, like the real one)",
        "prev": "Previous", "next": "Next",
        "eliminatory": "Eliminatory", "right": "Correct answer",
        "classes": lambda c: ("Class " if len(c) == 1 else "Classes ") + " and ".join(c),
        "source_page": lambda page: f"Official question bank, p. {page}.",
        "disclaimer": ("Unofficial tool. Questions and answers come from the bank published by the provincial "
                       "road safety office; the real exam may differ."),
        "all": "All questions", "about": "About",
        "promo": "Need a website for your business?",
    },
    "ru": {
        "root": "/ru/voprosy/", "app": "/?lang=ru", "locale": "ru_RU", "name": "Русский",
        "home": "Главная", "index_crumb": "Вопросы экзамена",
        "index_title": "Вопросы экзамена на права в Буэнос-Айресе на русском, с ответами",
        "index_h1": "Вопросы теоретического экзамена на права провинции Буэнос-Айрес на русском",
        "index_desc": lambda total: (f"Все {total} официальных вопросов теоретического экзамена на права "
                                     "провинции Буэнос-Айрес на русском, по темам, с испанским оригиналом и ответами."),
        "index_intro": lambda total: (
            f"Все {total} вопросов официального вопросника для прав класса A (мотоциклы) и класса B "
            "(легковые автомобили и пикапы) по темам: перевод на русский, испанский оригинал и отмеченный "
            "правильный ответ. На экзамене 40 вопросов на испанском: нужно 30 верных ответов и все "
            "5 критических вопросов без ошибок."),
        "topic_title": lambda name: f"{name}: вопросы экзамена на права в Буэнос-Айресе на русском",
        "topic_desc": lambda n, name: (f"{_q_ru(n)} темы «{name}» теоретического экзамена на права провинции "
                                       "Буэнос-Айрес на русском, с испанским оригиналом и правильными ответами."),
        "topic_intro": lambda n, elim: (
            f"{_q_ru(n)} из официального вопросника теоретического экзамена на права провинции Буэнос-Айрес "
            "в переводе на русский: под каждой строкой испанский оригинал, правильный ответ отмечен. "
            "Сам экзамен сдаётся на испанском." + _elim_ru(elim)),
        "practice": "Тренироваться в тренажёре", "exam": "Пробный экзамен (на испанском, как настоящий)",
        "prev": "Назад", "next": "Далее",
        "eliminatory": "Критический вопрос", "right": "Правильный ответ",
        "classes": lambda c: ("Класс " if len(c) == 1 else "Классы ") + " и ".join(c),
        "source_page": lambda page: f"Официальный вопросник, стр. {page}.",
        "disclaimer": ("Неофициальный тренажёр. Вопросы и ответы взяты из вопросника, опубликованного дорожной "
                       "службой провинции; на настоящем экзамене они могут отличаться."),
        "all": "Все вопросы", "about": "О сайте",
        "promo": "Нужен сайт для вашего бизнеса?",
    },
}


def app_link(lang, route):
    """A route of the app (#/practice) opened in the page's language."""
    return f"{LANGS[lang]['app']}#/{route}"


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def topic_name(section):
    name = re.sub(r"^\s*\d+\)\s*", "", section)
    name = re.sub(r"(?i)^pr?eguntas para todas las clases[\s.:]*", "", name).strip(" .:")
    if not name:
        return "Preguntas generales"
    return TOPIC_NAMES.get(name.lower(), name[0].upper() + name[1:])


def merge_categories(categories):
    """{"a": items, "b": items} -> [(item, classes)] in bank order, each question once.

    A question is eliminatory if either category flags it (duplicates can carry the flag over
    in one category only).
    """
    merged = {}
    for cat, items in sorted(categories.items()):
        for item in items:
            if item["id"] in merged:
                kept, classes = merged[item["id"]]
                if item.get("eliminatory") and not kept.get("eliminatory"):
                    merged[item["id"]] = ({**kept, "eliminatory": True}, classes)
            else:
                merged[item["id"]] = (item, [])
            merged[item["id"]][1].append(cat.upper())
    return sorted(merged.values(), key=lambda entry: entry[0]["src"]["page"])


def group_by_topic(entries):
    """[(item, classes)] -> [{"name", "slug", "entries"}] in order of first appearance."""
    topics = {}
    for item, classes in entries:
        name = topic_name(item["src"]["section"])
        if name not in topics:
            if name not in TOPIC_TRANSLATIONS:
                raise SystemExit(f"add {name!r} to TOPIC_TRANSLATIONS")
            en, ru = TOPIC_TRANSLATIONS[name]
            topics[name] = {"name": {"es": name, "en": en, "ru": ru},
                            "slug": {"es": slugify(name), "en": slugify(en), "ru": slugify(en)},
                            "entries": []}
        topic = topics[name]
        topic["entries"].append((item, classes))
    slugs = [t["slug"]["es"] for t in topics.values()]
    if len(set(slugs)) != len(slugs):
        raise SystemExit(f"two topics share a slug: {slugs}")
    return list(topics.values())


def breadcrumbs(*crumbs):
    """schema.org BreadcrumbList from (name, path) pairs, root first."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i, "name": name, "item": SITE_URL + path}
                            for i, (name, path) in enumerate(crumbs, 1)],
    }


def page(lang, title, description, path, body, alternates, jsonld=None):
    """`alternates` maps every language to the path of this page in it."""
    L = LANGS[lang]
    url = SITE_URL + path
    # A "</" inside the JSON would end the script element early.
    ld = ""
    if jsonld:
        data = json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")
        ld = f'\n  <script type="application/ld+json">{data}</script>'
    hreflang = switch = ""
    if len(alternates) > 1:
        hreflang = "".join(f'\n  <link rel="alternate" hreflang="{code}" href="{SITE_URL}{alt}">'
                           for code, alt in [*alternates.items(), ("x-default", alternates["es"])])
        switch = "\n  <p class=\"footer__links\">" + "".join(
            f'\n    <a href="{alt}" hreflang="{code}" lang="{code}">{LANGS[code]["name"]}</a>'
            for code, alt in alternates.items() if code != lang) + "\n  </p>"
    return f"""<!doctype html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <link rel="canonical" href="{url}">{hreflang}
  <meta property="og:type" content="website">
  <meta property="og:locale" content="{L["locale"]}">
  <meta property="og:site_name" content="conducir.ar">
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{SITE_URL}/og.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">{ld}
  <meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#23262b" media="(prefers-color-scheme: dark)">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="preload" href="/fonts/overpass-latin.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="/css/style.css">
  <script>
    try {{
      const s = JSON.parse(localStorage.getItem("pba:settings") || "{{}}");
      if (s.theme) document.documentElement.dataset.theme = s.theme;
    }} catch {{}}
  </script>
</head>
<body>
<main class="page">
<header class="bar"><a class="bar__home" href="{L["app"]}"><span>{APP_NAME}</span><span class="bar__sub">Provincia de Buenos Aires</span></a></header>
{body}
<footer class="footer">
  <p>{escape(L["disclaimer"])}</p>
  <p class="footer__links">
    <a href="{L["root"]}">{escape(L["all"])}</a>
    <a href="{app_link(lang, "about")}">{escape(L["about"])}</a>
  </p>{switch}
  <p><a href="{app_link(lang, "web")}">{escape(L["promo"])}</a></p>
</footer>
</main>
</body>
</html>
"""


def question_html(item, classes, number, lang):
    """Spanish pages show the original; the others show the translation with the original under it."""
    L = LANGS[lang]
    es = item["es"]
    local = es if lang == "es" else item[lang]

    def text(local_text, es_text):
        if lang == "es":
            return escape(es_text)
        return f'{escape(local_text)}<span class="trans" lang="es">{escape(es_text)}</span>'

    parts = [f'<article class="sq" id="q-{escape(item["id"])}">']
    if item.get("eliminatory"):
        parts.append(f'<p class="badge-elim">{escape(L["eliminatory"])}</p>')
    parts.append(f'<h2 class="sq__q"><span class="sq__n">{number}.</span> {text(local["q"], es["q"])}</h2>')
    images = item.get("img", [])
    img_lang = "" if lang == "es" else ' lang="es"'
    for src, alt in zip(images, item.get("alt") or [""] * len(images)):
        parts.append(f'<figure class="qimg"><img src="/{escape(src)}" alt="{escape(alt)}"{img_lang} loading="lazy"></figure>')
    parts.append('<ol class="sq__opts">')
    for i, answer in enumerate(es["answers"]):
        right = i in item["correct"]
        mark = f'<span class="sq__mark">{escape(L["right"])}</span>' if right else ""
        cls = ' class="is-right"' if right else ""
        parts.append(f'<li{cls}><span class="sq__key">{LETTERS[i]}</span>'
                     f'<span>{text(local["answers"][i], answer)}{mark}</span></li>')
    parts.append("</ol>")
    if item.get("fix"):
        parts.append(f'<p class="notice">{escape(item["fix"].get(lang) or item["fix"]["es"])}</p>')
    parts.append(f'<p class="sq__meta muted small">{L["classes"](classes)}. '
                 f'{L["source_page"](item["src"]["page"])}</p>')
    parts.append("</article>")
    return "\n".join(parts)


def topic_path(topic, lang):
    return f"{LANGS[lang]['root']}{topic['slug'][lang]}/"


def topic_page(topic, prev_topic, next_topic, lang, langs):
    L = LANGS[lang]
    entries = topic["entries"]
    name = topic["name"][lang]
    n = len(entries)
    elim = sum(1 for item, _ in entries if item.get("eliminatory"))
    nav = []
    if prev_topic:
        nav.append(f'<a href="{topic_path(prev_topic, lang)}">{L["prev"]}: {escape(prev_topic["name"][lang])}</a>')
    if next_topic:
        nav.append(f'<a href="{topic_path(next_topic, lang)}">{L["next"]}: {escape(next_topic["name"][lang])}</a>')
    body = "\n".join([
        f'<nav class="crumbs small"><a href="{L["root"]}">{escape(L["index_crumb"])}</a></nav>',
        f'<h1 class="title">{escape(name)}</h1>',
        f"<p>{escape(L['topic_intro'](n, elim))}</p>",
        f'<p class="sq-cta"><a class="btn" href="{app_link(lang, "practice")}">{escape(L["practice"])}</a></p>',
        *(question_html(item, classes, i, lang) for i, (item, classes) in enumerate(entries, 1)),
        f'<p class="sq-cta"><a class="btn" href="{app_link(lang, "exam")}">{escape(L["exam"])}</a></p>',
        f'<nav class="topic-nav">{"".join(nav)}</nav>',
    ])
    path = topic_path(topic, lang)
    crumbs = breadcrumbs((L["home"], L["app"]), (L["index_crumb"], L["root"]), (name, path))
    alternates = {code: topic_path(topic, code) for code in langs}
    return page(lang, L["topic_title"](name), L["topic_desc"](n, name), path, body, alternates, crumbs)


def index_page(topics, lang, langs):
    L = LANGS[lang]
    total = sum(len(t["entries"]) for t in topics)
    items = "\n".join(
        f'<li><a href="{topic_path(t, lang)}">{escape(t["name"][lang])}</a> '
        f'<span class="muted">{len(t["entries"])}</span></li>'
        for t in topics
    )
    body = "\n".join([
        f'<h1 class="title">{escape(L["index_h1"])}</h1>',
        f"<p>{escape(L['index_intro'](total))}</p>",
        f'<p class="sq-cta"><a class="btn" href="{L["app"]}">{escape(L["practice"])}</a></p>',
        f'<ul class="topic-list">\n{items}\n</ul>',
    ])
    alternates = {code: LANGS[code]["root"] for code in langs}
    return page(lang, L["index_title"], L["index_desc"](total), L["root"], body, alternates,
                breadcrumbs((L["home"], L["app"]), (L["index_crumb"], L["root"])))


def sitemap(paths):
    urls = "\n".join(f"  <url><loc>{escape(SITE_URL + p)}</loc></url>" for p in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}\n</urlset>\n")


def has_translation(item, lang):
    return lang == "es" or bool(item.get(lang))


def build_pages(categories, out_dir):
    """Writes the pages of every language and sitemap.xml into out_dir; returns the number of topics.

    A language version is written only when every question has its translation.
    """
    topics = group_by_topic(merge_categories(categories))
    langs = [lang for lang in LANGS
             if all(has_translation(item, lang) for t in topics for item, _ in t["entries"])]
    paths = ["/"]
    for lang in langs:
        root = Path(out_dir) / LANGS[lang]["root"].strip("/")
        root.mkdir(parents=True)
        (root / "index.html").write_text(index_page(topics, lang, langs), encoding="utf-8")
        paths.append(LANGS[lang]["root"])
        for i, topic in enumerate(topics):
            prev_topic = topics[i - 1] if i > 0 else None
            next_topic = topics[i + 1] if i + 1 < len(topics) else None
            (root / topic["slug"][lang]).mkdir()
            (root / topic["slug"][lang] / "index.html").write_text(
                topic_page(topic, prev_topic, next_topic, lang, langs), encoding="utf-8")
            paths.append(topic_path(topic, lang))
    (Path(out_dir) / "sitemap.xml").write_text(sitemap(paths), encoding="utf-8")
    return len(topics)
