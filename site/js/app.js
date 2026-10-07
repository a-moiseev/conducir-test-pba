// Single-page app: hash routes, plain DOM. Pure logic lives in ./lib (unit-tested with node).
import { load, save, remove } from "./lib/storage.js";
import { t, UI_LANGS, LANG_NAMES } from "./lib/strings.js";
import { optionOrder, isCorrect, isMulti, localized, hasTranslation } from "./lib/question.js";
import { grade, pickNext, summary, RECENT_WINDOW } from "./lib/progress.js";
import { readiness } from "./lib/readiness.js";

const CLASSES = ["A", "B"];
const SOURCE_PDF = "https://www.gba.gob.ar/static/seguridadvial/docs/cuestionario.pdf";
const REPO_URL = "https://github.com/a-moiseev/conducir-test-pba";
const LETTERS = "ABCDEFGH";

const app = document.getElementById("app");

// ---------- state ----------

const settings = { lang: null, cls: null, theme: null, showOriginal: false, ...load("settings", {}) };
if (!["es", "en", "ru"].includes(settings.lang)) settings.lang = null;
if (!["A", "B"].includes(settings.cls)) settings.cls = null;

function saveSettings(patch) {
  Object.assign(settings, patch);
  save("settings", settings);
}

const bankCache = new Map();

async function loadBank(cls) {
  if (!bankCache.has(cls)) {
    const promise = fetch(`data/${cls.toLowerCase()}.json`).then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    });
    bankCache.set(cls, promise);
    promise.catch(() => bankCache.delete(cls));
  }
  return bankCache.get(cls);
}

const progressKey = (cls) => `progress:${cls}`;
const recentKey = (cls) => `recent:${cls}`;
const currentKey = (cls) => `current:${cls}`;

// ---------- DOM helpers ----------

// h("p.muted", {onclick}, "text", child) — tag with optional .classes, attributes, children.
function h(spec, attrs, ...children) {
  if (attrs == null || typeof attrs !== "object" || attrs instanceof Node || Array.isArray(attrs)) {
    children.unshift(attrs);
    attrs = {};
  }
  const [tag, ...classes] = spec.split(".");
  const el = document.createElement(tag || "div");
  if (classes.length) el.className = classes.join(" ");
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "html") el.innerHTML = value; // only for static SVG icons
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const tr = (key, vars) => t(settings.lang || "es", key, vars);

// Bumped on every navigation; async views check it after each await.
let navId = 0;

function render(...nodes) {
  app.replaceChildren(...nodes);
  window.scrollTo(0, 0);
}

function applyTheme() {
  if (settings.theme) document.documentElement.dataset.theme = settings.theme;
  else delete document.documentElement.dataset.theme;
  document.documentElement.lang = settings.lang || "es";
}

const ICON_SUN =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
const ICON_MOON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

function isDark() {
  if (settings.theme) return settings.theme === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function topBar() {
  const dark = isDark();
  return h(
    "header.bar",
    h("a.bar__home", { href: "#/" }, tr("appName")),
    settings.cls && h("span.plate", { title: tr("licenseClass") }, settings.cls),
    h("button.icon-btn", {
      type: "button",
      "data-theme-toggle": true,
      "aria-label": dark ? tr("themeLight") : tr("themeDark"),
      html: dark ? ICON_SUN : ICON_MOON,
      onclick: () => {
        saveSettings({ theme: isDark() ? "light" : "dark" });
        applyTheme();
        refreshThemeButtons();
      },
    }),
  );
}

// Theme changes never re-render the page: an answered question must keep its state.
function refreshThemeButtons() {
  const dark = isDark();
  for (const btn of document.querySelectorAll("[data-theme-toggle]")) {
    btn.innerHTML = dark ? ICON_SUN : ICON_MOON;
    btn.setAttribute("aria-label", dark ? tr("themeLight") : tr("themeDark"));
  }
  for (const btn of document.querySelectorAll("[data-theme-choice]")) {
    btn.setAttribute("aria-pressed", String((btn.dataset.themeChoice || null) === (settings.theme || null)));
  }
}

function footer() {
  return h(
    "footer.footer",
    h("p", tr("disclaimer")),
    h(
      "p.footer__links",
      h("a", { href: SOURCE_PDF, target: "_blank", rel: "noopener" }, tr("sourceLink")),
      h("a", { href: REPO_URL, target: "_blank", rel: "noopener" }, tr("codeLink")),
    ),
  );
}

function segmented(label, options, current, onPick, dataName) {
  return h(
    "div.field",
    h("span.field__label", label),
    h(
      "div.segmented",
      { role: "group", "aria-label": label },
      options.map(([value, text]) => {
        const attrs = { type: "button", "aria-pressed": String(value === current), onclick: () => onPick(value) };
        if (dataName) attrs[`data-${dataName}`] = value || "";
        return h("button", attrs, text);
      }),
    ),
  );
}

// ---------- onboarding ----------

function viewLanguage() {
  // Shown before a language is known, so the prompt is given in every language.
  render(
    h("header.bar", h("span.bar__home", t("es", "appName"))),
    h(
      "section",
      h("h1.title", UI_LANGS.map((l) => h("span.title__line", { lang: l }, t(l, "languagePrompt")))),
      h(
        "div.choices",
        UI_LANGS.map((lang) =>
          h(
            "button.choice",
            { type: "button", lang, onclick: () => (saveSettings({ lang }), applyTheme(), route()) },
            h("strong", LANG_NAMES[lang]),
          ),
        ),
      ),
    ),
  );
}

function viewClass() {
  render(
    topBar(),
    h(
      "section",
      h("h1.title", tr("classPrompt")),
      h(
        "div.choices",
        CLASSES.map((cls) =>
          h(
            "button.choice",
            { type: "button", onclick: () => (saveSettings({ cls }), route()) },
            h("strong", tr(`class${cls}`)),
            h("span.muted", tr(`class${cls}Hint`)),
          ),
        ),
      ),
    ),
  );
}

// ---------- home ----------

// Loads the bank for the current class; returns null if the user navigated away meanwhile.
async function bankForView() {
  const nav = navId;
  const cls = settings.cls;
  render(topBar(), h("p.muted", tr("loading")));
  try {
    const bank = await loadBank(cls);
    return nav === navId ? { bank, cls } : null;
  } catch {
    if (nav === navId) render(topBar(), h("p.notice", tr("loadError")), settingsPanel(), footer());
    return null;
  }
}

async function viewHome() {
  const loaded = await bankForView();
  if (!loaded) return;
  const { bank } = loaded;
  const records = load(progressKey(settings.cls), {});
  const stats = summary(bank.questions, records);
  const chance = Math.round(readiness(bank.questions, records).pass * 100);

  render(
    topBar(),
    h(
      "section.hero",
      h(
        "div.roundel",
        { role: "img", "aria-label": `${tr("chanceTitle")}: ${chance} %` },
        h("span.roundel__value", String(chance), h("span.roundel__unit", "%")),
      ),
      h(
        "div.hero__text",
        h("h1.subtitle", tr("chanceTitle")),
        h("p", tr("chanceBody", { learned: stats.mastered, total: stats.total, cls: settings.cls })),
        h("p.muted.small", tr("rulesNote")),
      ),
    ),
    h(
      "ul.actions",
      h(
        "li",
        h(
          "a.action.action--primary",
          { href: "#/practice" },
          h("span.action__label", tr("practice")),
          h("span.action__hint", tr("practiceHint")),
        ),
      ),
    ),
    settingsPanel(),
    footer(),
  );
}

function settingsPanel() {
  return h(
    "section.settings",
    { "aria-label": tr("settings") },
    h("h2.subtitle", tr("settings")),
    segmented(tr("language"), UI_LANGS.map((l) => [l, LANG_NAMES[l]]), settings.lang, (lang) => {
      saveSettings({ lang });
      applyTheme();
      route();
    }),
    segmented(tr("licenseClass"), CLASSES.map((c) => [c, tr(`class${c}`)]), settings.cls, (cls) => {
      saveSettings({ cls });
      route();
    }),
    segmented(
      tr("theme"),
      [[null, tr("themeAuto")], ["light", tr("themeLight")], ["dark", tr("themeDark")]],
      settings.theme,
      (theme) => {
        saveSettings({ theme });
        applyTheme();
        refreshThemeButtons();
      },
      "theme-choice",
    ),
    h(
      "button.link-btn",
      {
        type: "button",
        onclick: () => {
          if (!window.confirm(tr("resetConfirm", { cls: settings.cls }))) return;
          for (const key of [progressKey, recentKey, currentKey]) remove(key(settings.cls));
          route();
        },
      },
      tr("resetProgress"),
    ),
  );
}

// ---------- practice ----------

async function viewPractice() {
  const loaded = await bankForView();
  if (!loaded) return;
  const { bank, cls } = loaded;
  const questions = bank.questions;
  const byId = new Map(questions.map((q) => [q.id, q]));
  let records = load(progressKey(cls), {});
  let recent = load(recentKey(cls), []);
  let answeredInSession = 0;

  function nextQuestion() {
    // Resume the question that was on screen before a reload.
    const saved = byId.get(load(currentKey(cls), null));
    const q = saved || pickNext(questions, records, recent);
    save(currentKey(cls), q.id);
    showQuestion(q);
  }

  function showQuestion(q) {
    const lang = settings.lang;
    const text = localized(q, lang);
    const translated = hasTranslation(q, lang);
    const order = optionOrder(q);
    const multi = isMulti(q);
    const selected = new Set();
    let checked = false;

    const verdict = h("p.verdict", { role: "status" });
    const button = h("button.btn", { type: "button", disabled: true }, multi ? tr("pickAll") : tr("pickOne"));

    const optionButtons = order.map((orig, pos) => {
      const btn = h(
        "button.opt",
        {
          type: "button",
          "aria-pressed": "false",
          class: multi ? "opt opt--multi" : "opt",
          onclick: () => toggle(orig),
        },
        h("span.opt__key", LETTERS[pos]),
        h(
          "span.opt__text",
          text.answers[orig],
          translated && h("span.original", { lang: "es" }, q.es.answers[orig]),
        ),
      );
      btn.dataset.orig = orig;
      return btn;
    });

    function refresh() {
      for (const btn of optionButtons) btn.setAttribute("aria-pressed", String(selected.has(Number(btn.dataset.orig))));
      button.disabled = selected.size === 0;
      button.textContent = selected.size ? tr("check") : multi ? tr("pickAll") : tr("pickOne");
    }

    function toggle(orig) {
      if (checked) return;
      if (multi) selected.has(orig) ? selected.delete(orig) : selected.add(orig);
      else {
        selected.clear();
        selected.add(orig);
      }
      refresh();
    }

    function check() {
      checked = true;
      const ok = isCorrect(q, [...selected]);
      records = { ...records, [q.id]: grade(records[q.id], ok) };
      recent = [...recent, q.id].slice(-RECENT_WINDOW);
      save(progressKey(cls), records);
      save(recentKey(cls), recent);
      remove(currentKey(cls));
      answeredInSession += 1;

      for (const btn of optionButtons) {
        const orig = Number(btn.dataset.orig);
        btn.disabled = true;
        btn.removeAttribute("aria-pressed");
        if (q.correct.includes(orig)) btn.classList.add("opt--right");
        else if (selected.has(orig)) btn.classList.add("opt--wrong");
        else btn.classList.add("opt--dim");
      }
      verdict.textContent = ok ? tr("correct") : tr("wrong");
      verdict.className = `verdict ${ok ? "verdict--right" : "verdict--wrong"}`;
      button.disabled = false;
      button.textContent = tr("next");
      learned.textContent = tr("learnedOf", { learned: summary(questions, records).mastered, total: questions.length });
      button.focus();
    }

    button.addEventListener("click", () => (checked ? nextQuestion() : check()));

    const stats = summary(questions, records);
    const learned = h("span", { title: tr("learnedHint") }, tr("learnedOf", { learned: stats.mastered, total: questions.length }));

    const article = h(
        "article",
        { class: settings.showOriginal ? "show-original" : null },
        h("div.qhead", h("span.qhead__n", tr("questionN", { n: answeredInSession + 1 })), h("a", { href: "#/" }, tr("home"))),
        lang === "en" && !translated && h("p.notice", tr("noTranslation")),
        q.eliminatory && h("p.badge-elim", { title: tr("eliminatoryHint") }, tr("eliminatory")),
        h(
          "h1.qtext",
          text.q,
          translated && h("span.original", { lang: "es" }, q.es.q),
        ),
        translated &&
          h(
            "button.link-btn.toggle-original",
            {
              type: "button",
              "aria-pressed": String(settings.showOriginal),
              onclick: (e) => {
                // Only toggles visibility, so an answered question keeps its state.
                saveSettings({ showOriginal: !settings.showOriginal });
                article.classList.toggle("show-original", settings.showOriginal);
                e.currentTarget.setAttribute("aria-pressed", String(settings.showOriginal));
                e.currentTarget.textContent = settings.showOriginal ? tr("hideOriginal") : tr("showOriginal");
              },
            },
            settings.showOriginal ? tr("hideOriginal") : tr("showOriginal"),
          ),
        (q.img || []).map((src) => h("figure.qimg", h("img", { src, alt: "", loading: "eager" }))),
        h("ul.options", optionButtons.map((btn) => h("li", btn))),
        verdict,
        button,
        h(
          "footer.qfoot",
          learned,
          h(
            "a",
            { href: `${SOURCE_PDF}#page=${q.src.page}`, target: "_blank", rel: "noopener" },
            tr("sourcePage", { page: q.src.page }),
          ),
        ),
      );
    render(topBar(), article);
    keyHandler = (e) => {
      if (e.target.closest("input, select, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
      const pos = LETTERS.indexOf(e.key.toUpperCase());
      const digit = Number(e.key) - 1;
      const index = pos >= 0 ? pos : digit;
      if (index >= 0 && index < order.length && !checked) {
        e.preventDefault();
        toggle(order[index]);
      } else if (
        e.key === "Enter" &&
        !button.disabled &&
        (document.activeElement === document.body || document.activeElement === null)
      ) {
        e.preventDefault();
        button.click();
      }
    };
  }

  nextQuestion();
}

// ---------- router ----------

let keyHandler = null;
document.addEventListener("keydown", (e) => keyHandler && keyHandler(e));

const ROUTES = {
  "": viewHome,
  practice: viewPractice,
};

function route() {
  navId += 1;
  keyHandler = null;
  applyTheme();
  if (!settings.lang) return viewLanguage();
  if (!settings.cls) return viewClass();
  const name = location.hash.replace(/^#\/?/, "");
  const view = ROUTES[name] || viewHome;
  document.title = name === "practice" ? `${tr("practice")} — ${tr("appName")}` : tr("appName");
  view();
}

window.addEventListener("hashchange", route);
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", refreshThemeButtons);
route();
