"""Static, indexable pages for search engines: every question with its answer, one page per topic.

The app itself stays a single page that loads the whole bank at once; these pages are what
search engines see and where search visitors land. They are in Spanish only and link to the app.

    /preguntas/            topics with question counts
    /preguntas/<topic>/    every question of the topic, correct answers marked
    /sitemap.xml
"""
import json
import re
import unicodedata
from html import escape
from pathlib import Path

SITE_URL = "https://conducir.ar"
APP_NAME = "Test de Conducir PBA"
LETTERS = "ABCDEFGH"
# The author's website offer lives in the app (#/web), in the visitor's language.
PROMO_LINK = '<p><a href="/#/web">¿Necesitás un sitio web para tu negocio?</a></p>'

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
        topic = topics.setdefault(name, {"name": name, "slug": slugify(name), "entries": []})
        topic["entries"].append((item, classes))
    slugs = [t["slug"] for t in topics.values()]
    if len(set(slugs)) != len(slugs):
        raise SystemExit(f"two topics share a slug: {slugs}")
    return list(topics.values())


def classes_label(classes):
    return "Clase " + classes[0] if len(classes) == 1 else "Clases " + " y ".join(classes)


def breadcrumbs(*crumbs):
    """schema.org BreadcrumbList from (name, path) pairs, root first."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i, "name": name, "item": SITE_URL + path}
                            for i, (name, path) in enumerate(crumbs, 1)],
    }


def page(title, description, path, body, jsonld=None):
    url = SITE_URL + path
    # A "</" inside the JSON would end the script element early.
    ld = ""
    if jsonld:
        data = json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")
        ld = f'\n  <script type="application/ld+json">{data}</script>'
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <link rel="canonical" href="{url}">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="es_AR">
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
<header class="bar"><a class="bar__home" href="/"><span>{APP_NAME}</span><span class="bar__sub">Provincia de Buenos Aires</span></a></header>
{body}
<footer class="footer">
  <p>Herramienta no oficial. Las preguntas y respuestas salen del cuestionario publicado por la Dirección Provincial de Política y Seguridad Vial; el examen real puede variar.</p>
  <p class="footer__links">
    <a href="/preguntas/">Todas las preguntas</a>
    <a href="/#/about">Acerca del sitio</a>
  </p>
  {PROMO_LINK}
</footer>
</main>
</body>
</html>
"""


def question_html(item, classes, number):
    es = item["es"]
    parts = [f'<article class="sq" id="q-{escape(item["id"])}">']
    if item.get("eliminatory"):
        parts.append('<p class="badge-elim">Eliminatoria</p>')
    parts.append(f'<h2 class="sq__q"><span class="sq__n">{number}.</span> {escape(es["q"])}</h2>')
    images = item.get("img", [])
    for src, alt in zip(images, item.get("alt") or [""] * len(images)):
        parts.append(f'<figure class="qimg"><img src="/{escape(src)}" alt="{escape(alt)}" loading="lazy"></figure>')
    parts.append('<ol class="sq__opts">')
    for i, answer in enumerate(es["answers"]):
        right = i in item["correct"]
        mark = '<span class="sq__mark">Respuesta correcta</span>' if right else ""
        cls = ' class="is-right"' if right else ""
        parts.append(f'<li{cls}><span class="sq__key">{LETTERS[i]}</span><span>{escape(answer)}{mark}</span></li>')
    parts.append("</ol>")
    if item.get("fix"):
        parts.append(f'<p class="notice">{escape(item["fix"]["es"])}</p>')
    parts.append(f'<p class="sq__meta muted small">{classes_label(classes)}. '
                 f'Cuestionario oficial, pág. {item["src"]["page"]}.</p>')
    parts.append("</article>")
    return "\n".join(parts)


def topic_page(topic, prev_topic, next_topic):
    entries = topic["entries"]
    n = len(entries)
    elim = sum(1 for item, _ in entries if item.get("eliminatory"))
    intro = (f"{n} preguntas del cuestionario oficial del examen teórico de manejo de la Provincia "
             f"de Buenos Aires, con la respuesta correcta marcada.")
    if elim:
        intro += f" {elim} son eliminatorias: si respondés mal una en el examen, desaprobás."
    nav = []
    if prev_topic:
        nav.append(f'<a href="/preguntas/{prev_topic["slug"]}/">Anterior: {escape(prev_topic["name"])}</a>')
    if next_topic:
        nav.append(f'<a href="/preguntas/{next_topic["slug"]}/">Siguiente: {escape(next_topic["name"])}</a>')
    body = "\n".join([
        f'<nav class="crumbs small"><a href="/preguntas/">Preguntas del examen</a></nav>',
        f'<h1 class="title">{escape(topic["name"])}</h1>',
        f"<p>{escape(intro)}</p>",
        '<p class="sq-cta"><a class="btn" href="/#/practice">Practicar con el simulador</a></p>',
        *(question_html(item, classes, i) for i, (item, classes) in enumerate(entries, 1)),
        '<p class="sq-cta"><a class="btn" href="/#/exam">Hacer un simulacro de examen</a></p>',
        f'<nav class="topic-nav">{"".join(nav)}</nav>',
    ])
    title = f"{topic['name']}: preguntas del examen de manejo PBA"
    description = (f"{n} preguntas de «{topic['name']}» del examen teórico de la licencia de conducir "
                   f"de la Provincia de Buenos Aires, con las respuestas correctas.")
    path = f"/preguntas/{topic['slug']}/"
    crumbs = breadcrumbs(("Inicio", "/"), ("Preguntas del examen", "/preguntas/"), (topic["name"], path))
    return page(title, description, path, body, crumbs)


def index_page(topics):
    total = sum(len(t["entries"]) for t in topics)
    items = "\n".join(
        f'<li><a href="/preguntas/{t["slug"]}/">{escape(t["name"])}</a> '
        f'<span class="muted">{len(t["entries"])}</span></li>'
        for t in topics
    )
    body = "\n".join([
        '<h1 class="title">Preguntas del examen teórico de manejo de la Provincia de Buenos Aires</h1>',
        f"<p>Las {total} preguntas del cuestionario oficial para las licencias clase A (motos) y "
        "clase B (autos y camionetas), ordenadas por tema y con la respuesta correcta marcada. "
        "El examen tiene 40 preguntas: aprobás con 30 correctas y las 5 eliminatorias bien.</p>",
        '<p class="sq-cta"><a class="btn" href="/">Practicar con el simulador</a></p>',
        f'<ul class="topic-list">\n{items}\n</ul>',
    ])
    title = "Preguntas del examen de manejo PBA con respuestas"
    description = (f"Las {total} preguntas oficiales del examen teórico de la licencia de conducir de la "
                   "Provincia de Buenos Aires, por tema y con respuestas.")
    return page(title, description, "/preguntas/", body,
                breadcrumbs(("Inicio", "/"), ("Preguntas del examen", "/preguntas/")))


def sitemap(paths):
    urls = "\n".join(f"  <url><loc>{escape(SITE_URL + p)}</loc></url>" for p in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}\n</urlset>\n")


def build_pages(categories, out_dir):
    """Writes preguntas/ and sitemap.xml into out_dir; returns the number of topic pages."""
    topics = group_by_topic(merge_categories(categories))
    root = Path(out_dir) / "preguntas"
    root.mkdir(parents=True)
    (root / "index.html").write_text(index_page(topics), encoding="utf-8")
    for i, topic in enumerate(topics):
        prev_topic = topics[i - 1] if i > 0 else None
        next_topic = topics[i + 1] if i + 1 < len(topics) else None
        (root / topic["slug"]).mkdir()
        (root / topic["slug"] / "index.html").write_text(
            topic_page(topic, prev_topic, next_topic), encoding="utf-8")
    paths = ["/", "/preguntas/", *(f"/preguntas/{t['slug']}/" for t in topics)]
    (Path(out_dir) / "sitemap.xml").write_text(sitemap(paths), encoding="utf-8")
    return len(topics)
