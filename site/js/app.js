// Single-page app: hash routes, plain DOM. Pure logic lives in ./lib (unit-tested with node).
import { load, save, remove } from "./lib/storage.js";
import { t, UI_LANGS, LANG_NAMES } from "./lib/strings.js";
import { optionOrder, isCorrect, isMulti, localized, hasTranslation } from "./lib/question.js";
import { grade, pickNext, summary, RECENT_WINDOW } from "./lib/progress.js";
import { readiness } from "./lib/readiness.js";
import { drawExam, scoreExam } from "./lib/exam.js";
import { EXAM } from "./lib/exam-rules.js";

const CLASSES = ["A", "B"];
const SOURCE_PDF = "https://www.gba.gob.ar/static/seguridadvial/docs/cuestionario.pdf";
const REPO_URL = "https://github.com/a-moiseev/conducir-test-pba";
const LETTERS = "ABCDEFGH";
const HISTORY_LIMIT = 20;

const app = document.getElementById("app");

// ---------- state ----------

const settings = { lang: null, cls: null, theme: null, ...load("settings", {}) };
delete settings.examTranslation; // the mock exam is always in Spanish now
if (!UI_LANGS.includes(settings.lang)) settings.lang = null;
if (!CLASSES.includes(settings.cls)) settings.cls = null;

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
const currentKey = (cls, mode = "practice") => (mode === "review" ? `currentReview:${cls}` : `current:${cls}`);
const examKey = (cls) => `exam:${cls}`;
const historyKey = (cls) => `examHistory:${cls}`;

// Grades answers into the stored progress (practice and exam both go through here).
function recordAnswers(cls, results) {
  const records = { ...load(progressKey(cls), {}) };
  const now = Date.now();
  for (const [id, ok] of results) records[id] = grade(records[id], ok, now);
  save(progressKey(cls), records);
  return records;
}

// A saved exam is usable only if every question still exists with the same options.
function examSessionValid(session, byId) {
  if (!session || !Array.isArray(session.ids)) return false;
  return session.ids.every((id) => {
    const q = byId.get(id);
    if (!q) return false;
    const n = q.es.answers.length;
    const order = session.orders?.[id];
    const answer = session.answers?.[id] || [];
    const isPermutation = Array.isArray(order) && order.length === n && [...order].sort((a, b) => a - b).every((v, i) => v === i);
    return isPermutation && answer.every((i) => Number.isInteger(i) && i >= 0 && i < n);
  });
}

function stopTimer() {
  clearInterval(timer);
  timer = null;
}

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
  for (const child of children.flat(Infinity)) {  // children may nest arrays (card.nodes, image lists)
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const tr = (key, vars) => t(settings.lang || "es", key, vars);

// Bumped on every navigation; async views and timers check it before touching the page.
let navId = 0;
let timer = null;

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
    // The license-class plate doubles as the class switch (there are only two classes).
    settings.cls &&
      h(
        "button.plate",
        {
          type: "button",
          "aria-label": tr("switchClass", { cls: otherClass() }),
          title: tr("switchClass", { cls: otherClass() }),
          onclick: () => {
            saveSettings({ cls: otherClass() });
            route();
          },
        },
        settings.cls,
      ),
    h("button.icon-btn", {
      type: "button",
      "data-theme-toggle": true,
      "aria-label": dark ? tr("themeLight") : tr("themeDark"),
      html: dark ? ICON_SUN : ICON_MOON,
      onclick: () => {
        // Switching to what the system already uses means "follow the system" again,
        // so the single toggle can always get back to the automatic theme.
        const next = isDark() ? "light" : "dark";
        const system = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
        saveSettings({ theme: next === system ? null : next });
        applyTheme();
        refreshThemeButtons();
      },
    }),
  );
}

function otherClass() {
  return CLASSES.find((c) => c !== settings.cls);
}

// Theme changes never re-render the page: an answered question must keep its state.
function refreshThemeButtons() {
  const dark = isDark();
  for (const btn of document.querySelectorAll("[data-theme-toggle]")) {
    btn.innerHTML = dark ? ICON_SUN : ICON_MOON;
    btn.setAttribute("aria-label", dark ? tr("themeLight") : tr("themeDark"));
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

function segmented(label, options, current, onPick) {
  return h(
    "div.field",
    h("span.field__label", label),
    h(
      "div.segmented",
      { role: "group", "aria-label": label },
      options.map(([value, text]) =>
        h("button", { type: "button", "aria-pressed": String(value === current), onclick: () => onPick(value) }, text),
      ),
    ),
  );
}

function sourceLink(q) {
  return h(
    "a",
    { href: `${SOURCE_PDF}#page=${q.src.page}`, target: "_blank", rel: "noopener" },
    tr("sourcePage", { page: q.src.page }),
  );
}

function formatDuration(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  return `${mm}:${String(s % 60).padStart(2, "0")}`;
}

// ---------- question card (practice, exam and reviews share it) ----------

// Renders a question with its options. The translation, when there is one, is shown with
// the Spanish original under it: the real exam is in Spanish. `translate: false` shows
// Spanish only. Options are numbered by display position (A, B, C…).
function questionCard(q, { order, selected, translate = true, onToggle }) {
  const lang = translate ? settings.lang : "es";
  const text = localized(q, lang);
  const translated = hasTranslation(q, lang);
  const multi = isMulti(q);

  const optionButtons = order.map((orig, pos) => {
    const btn = h(
      "button",
      {
        type: "button",
        class: multi ? "opt opt--multi" : "opt",
        "aria-pressed": String(selected.has(orig)),
        onclick: () => onToggle && onToggle(orig),
      },
      h("span.opt__key", LETTERS[pos]),
      h(
        "span.opt__text",
        h("span", { lang: translated ? lang : "es" }, text.answers[orig]),
        translated && h("span.original", { lang: "es" }, q.es.answers[orig]),
      ),
    );
    btn.dataset.orig = orig;
    return btn;
  });

  const nodes = [
    q.eliminatory && h("p.badge-elim", { title: tr("eliminatoryHint") }, tr("eliminatory")),
    h(
      "h2.qtext",
      h("span", { lang: translated ? lang : "es" }, text.q),
      translated && h("span.original", { lang: "es" }, q.es.q),
    ),
    (q.img || []).map((src) => h("figure.qimg", h("img", { src, alt: "", loading: "eager" }))),
    multi && h("p.multi-hint", tr("pickAll")),
    h("ul.options", { "aria-label": multi ? tr("pickAll") : tr("pickOne") }, optionButtons.map((b) => h("li", b))),
  ];

  return {
    nodes,
    multi,
    refresh() {
      for (const btn of optionButtons) btn.setAttribute("aria-pressed", String(selected.has(Number(btn.dataset.orig))));
    },
    // Lock the options and mark right / wrong / untouched ones.
    reveal() {
      for (const btn of optionButtons) {
        const orig = Number(btn.dataset.orig);
        btn.disabled = true;
        btn.removeAttribute("aria-pressed");
        if (q.correct.includes(orig)) btn.classList.add("opt--right");
        else if (selected.has(orig)) btn.classList.add("opt--wrong");
        else btn.classList.add("opt--dim");
      }
    },
  };
}

function toggleIn(selected, orig, multi) {
  if (multi) selected.has(orig) ? selected.delete(orig) : selected.add(orig);
  else {
    selected.clear();
    selected.add(orig);
  }
}

// Letter/digit keys pick options; Enter presses `button` when nothing else has focus.
function optionKeys(order, onPick, button) {
  return (e) => {
    if (e.target.closest("input, select, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
    const pos = LETTERS.indexOf(e.key.toUpperCase());
    const index = pos >= 0 ? pos : Number(e.key) - 1;
    if (index >= 0 && index < order.length && onPick(order[index]) !== false) {
      e.preventDefault();
    } else if (
      e.key === "Enter" &&
      button &&
      !button.disabled &&
      (document.activeElement === document.body || document.activeElement === null)
    ) {
      e.preventDefault();
      button.click();
    }
  };
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

function roundel(value, unit, label) {
  return h(
    "div.roundel",
    { role: "img", "aria-label": label },
    h("span.roundel__value", String(value), h("span.roundel__unit", unit)),
  );
}

function action(href, label, hint, { primary = false, warning = false, count = null } = {}) {
  return h(
    "li",
    h(
      primary ? "a.action.action--primary" : warning ? "a.action.action--warning" : "a.action",
      { href },
      h("span.action__label", label),
      h("span.action__hint", hint),
      count != null && h("span.action__count", String(count)),
    ),
  );
}

async function viewHome() {
  const loaded = await bankForView();
  if (!loaded) return;
  const { bank, cls } = loaded;
  const records = load(progressKey(cls), {});
  const stats = summary(bank.questions, records);
  const chance = Math.round(readiness(bank.questions, records).pass * 100);
  const exam = load(examKey(cls), null);
  const byId = new Map(bank.questions.map((q) => [q.id, q]));
  const examRunning = examSessionValid(exam, byId) && !exam.finished;

  render(
    topBar(),
    h(
      "section.hero",
      roundel(chance, "%", `${tr("chanceTitle")}: ${chance} %`),
      h(
        "div.hero__text",
        h("h1.subtitle", tr("chanceTitle")),
        h("p", tr("chanceBody", { learned: stats.mastered, total: stats.total, cls })),
        h("p.muted.small", tr("rulesNote")),
      ),
    ),
    h(
      "ul.actions",
      action("#/practice", tr("practice"), tr("practiceHint"), { primary: true }),
      action("#/exam", tr("exam"), examRunning ? tr("examResume") : tr("examHint", { total: EXAM.questions })),
      action("#/review", tr("review"), stats.mistakes ? tr("reviewHint") : tr("reviewNone"), {
        count: stats.mistakes || null,
        warning: stats.mistakes > 0,
      }),
      action("#/glossary", tr("glossary"), tr("glossaryHint")),
    ),
    settingsPanel(),
    footer(),
  );
}

function settingsPanel() {
  return h(
    "section.settings",
    { "aria-label": tr("settings") },
    segmented(tr("language"), UI_LANGS.map((l) => [l, LANG_NAMES[l]]), settings.lang, (lang) => {
      saveSettings({ lang });
      applyTheme();
      route();
    }),
    h(
      "button.link-btn",
      {
        type: "button",
        onclick: () => {
          if (!window.confirm(tr("resetConfirm", { cls: settings.cls }))) return;
          for (const key of [progressKey, recentKey, currentKey, examKey, historyKey]) remove(key(settings.cls));
          remove(currentKey(settings.cls, "review"));
          route();
        },
      },
      tr("resetProgress"),
    ),
  );
}

// ---------- practice ----------

// mode "practice": the whole bank, weakest first; mode "review": only questions whose
// latest answer was wrong — a right answer takes a question out of the review pool.
async function viewPractice(mode = "practice") {
  const loaded = await bankForView();
  if (!loaded) return;
  const { bank, cls } = loaded;
  const questions = bank.questions;
  const review = mode === "review";
  const byId = new Map(questions.map((q) => [q.id, q]));
  let records = load(progressKey(cls), {});
  let recent = load(recentKey(cls), []);
  let answeredInSession = 0;

  const pool = () => (review ? questions.filter((q) => records[q.id]?.miss) : questions);

  function nextQuestion() {
    // Resume the question that was on screen before a reload.
    let saved = byId.get(load(currentKey(cls, mode), null));
    // A saved review question may have been fixed in practice since.
    if (saved && review && !records[saved.id]?.miss) saved = null;
    const candidates = pool();
    if (!saved && candidates.length === 0) return reviewEmpty();
    const q = saved || pickNext(candidates, records, recent);
    save(currentKey(cls, mode), q.id);
    showQuestion(q);
  }

  function reviewEmpty() {
    keyHandler = null;
    render(
      topBar(),
      h(
        "section.stack",
        h("h1.title", tr("review")),
        h("p", answeredInSession ? tr("reviewDone") : tr("reviewEmpty")),
        h("div.btn-row", h("a.btn", { href: "#/practice" }, tr("practice")), h("a.btn.btn--quiet", { href: "#/" }, tr("home"))),
      ),
    );
  }

  function showQuestion(q) {
    const order = optionOrder(q);
    const selected = new Set();
    let checked = false;

    const verdict = h("p.verdict", { role: "status" });
    const button = h("button.btn", { type: "button", disabled: true });
    const card = questionCard(q, { order, selected, onToggle: pick });
    const learned = h("span", { title: tr("learnedHint") });

    function updateButton() {
      button.disabled = !checked && selected.size === 0;
      button.textContent = checked ? tr("next") : selected.size ? tr("check") : card.multi ? tr("pickAll") : tr("pickOne");
    }

    function updateLearned() {
      learned.textContent = review
        ? tr("reviewLeft", { count: pool().length })
        : tr("learnedOf", { learned: summary(questions, records).mastered, total: questions.length });
    }

    function pick(orig) {
      if (checked) return false;
      toggleIn(selected, orig, card.multi);
      card.refresh();
      updateButton();
    }

    function check() {
      checked = true;
      const ok = isCorrect(q, [...selected]);
      records = recordAnswers(cls, [[q.id, ok]]);
      recent = [...recent, q.id].slice(-RECENT_WINDOW);
      save(recentKey(cls), recent);
      remove(currentKey(cls, mode));
      answeredInSession += 1;
      card.reveal();
      verdict.textContent = ok ? tr("correct") : tr("wrong");
      verdict.className = `verdict ${ok ? "verdict--right" : "verdict--wrong"}`;
      updateButton();
      updateLearned();
      button.focus();
    }

    button.addEventListener("click", () => (checked ? nextQuestion() : check()));
    updateButton();
    updateLearned();

    render(
      topBar(),
      h(
        "article",
        h(
          "div.qhead",
          h("h1.qhead__n", review ? tr("review") : tr("questionN", { n: answeredInSession + 1 })),
          h("a", { href: "#/" }, tr("home")),
        ),
        settings.lang === "en" && !hasTranslation(q, "en") && h("p.notice", tr("noTranslation")),
        card.nodes,
        verdict,
        button,
        h("footer.qfoot", learned, sourceLink(q)),
      ),
    );
    keyHandler = optionKeys(order, pick, button);
  }

  nextQuestion();
}

// ---------- mock exam ----------

// Session: { ids, orders: {id: [option order]}, answers: {id: [selected]}, pos, started,
// finished?, translate } in localStorage, so a reload resumes the exam where it was.
async function viewExam() {
  const loaded = await bankForView();
  if (!loaded) return;
  const { bank, cls } = loaded;
  const byId = new Map(bank.questions.map((q) => [q.id, q]));
  let session = load(examKey(cls), null);
  // A bank update can remove questions or change options; such a session can't be scored.
  if (session && !examSessionValid(session, byId)) {
    remove(examKey(cls));
    session = null;
  }

  if (!session) return examIntro();
  if (session.finished) return examResult();
  return examQuestion();

  function persist() {
    save(examKey(cls), session);
  }

  function examIntro() {
    stopTimer();
    keyHandler = null;
    const history = load(historyKey(cls), []);
    render(
      topBar(),
      h(
        "section.stack",
        h("h1.title", tr("exam")),
        h("p", tr("examRules", { total: EXAM.questions, elim: EXAM.eliminatory, needed: Math.ceil(EXAM.questions * EXAM.passRatio) })),
        h("p.muted", tr("examNoLimit")),
        h("p.muted", tr("examSpanish")),
        h(
          "button.btn",
          {
            type: "button",
            onclick: () => {
              const ids = drawExam(bank.questions);
              session = {
                ids,
                orders: Object.fromEntries(ids.map((id) => [id, optionOrder(byId.get(id))])),
                answers: {},
                pos: 0,
                started: Date.now(),
                elapsed: 0,
              };
              persist();
              examQuestion();
            },
          },
          tr("examStart"),
        ),
        history.length > 0 && examHistory(history),
      ),
    );
  }

  function examHistory(history) {
    const fmt = new Intl.DateTimeFormat(settings.lang, { dateStyle: "medium", timeStyle: "short" });
    return h(
      "section.history",
      h("h2.subtitle", tr("examHistory")),
      h(
        "ol.history__list",
        history.slice(0, 5).map((r) =>
          h(
            "li",
            h("span", fmt.format(r.at)),
            h("strong", `${r.correct}/${r.total}`),
            h(r.passed ? "span.verdict--right" : "span.verdict--wrong", r.passed ? tr("passed") : tr("failed")),
          ),
        ),
      ),
    );
  }

  function examQuestion() {
    const total = session.ids.length;
    const id = session.ids[session.pos];
    const q = byId.get(id);
    const order = session.orders[id] || optionOrder(q);
    const selected = new Set(session.answers[id] || []);
    // Like the real exam: Spanish only.
    const card = questionCard(q, { order, selected, translate: false, onToggle: pick });

    function pick(orig) {
      toggleIn(selected, orig, card.multi);
      session.answers[id] = [...selected];
      persist();
      card.refresh();
      updateNav();
    }

    function go(pos) {
      session.pos = pos;
      persist();
      examQuestion();
    }

    function finish() {
      const unanswered = session.ids.filter((x) => !(session.answers[x] || []).length).length;
      if (unanswered && !window.confirm(tr("examFinishConfirm", { count: unanswered }))) return;
      const questions = session.ids.map((x) => byId.get(x));
      const score = scoreExam(questions, session.answers);
      stopTimer();
      session.finished = Date.now();
      persist();
      recordAnswers(cls, questions.map((x) => [x.id, !score.wrong.includes(x.id)]));
      const history = [
        { at: session.finished, correct: score.correct, total: score.total, passed: score.passed },
        ...load(historyKey(cls), []),
      ].slice(0, HISTORY_LIMIT);
      save(historyKey(cls), history);
      examResult();
    }

    const navCells = session.ids.map((x, i) =>
      h(
        "button.nav-cell",
        {
          type: "button",
          "aria-label": tr("questionOf", { n: i + 1, total }),
          "aria-current": i === session.pos ? "step" : null,
          onclick: () => go(i),
        },
        String(i + 1),
      ),
    );

    function updateNav() {
      navCells.forEach((cell, i) => cell.classList.toggle("nav-cell--done", (session.answers[session.ids[i]] || []).length > 0));
    }
    updateNav();

    // 6: count only time spent with the exam on screen, not wall-clock time since start.
    session.elapsed = session.elapsed || 0;
    const clock = h("span.clock", formatDuration(session.elapsed));
    stopTimer();
    timer = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      session.elapsed += 1000;
      persist();
      clock.textContent = formatDuration(session.elapsed);
    }, 1000);

    const last = session.pos === total - 1;
    const next = h(
      "button.btn",
      { type: "button", onclick: () => (last ? finish() : go(session.pos + 1)) },
      last ? tr("examFinish") : tr("examNext"),
    );

    render(
      topBar(),
      h(
        "article",
        h("div.qhead", h("h1.qhead__n", tr("questionOf", { n: session.pos + 1, total })), clock),
        card.nodes,
        h(
          "div.btn-row",
          session.pos > 0 && h("button.btn.btn--quiet", { type: "button", onclick: () => go(session.pos - 1) }, tr("examPrev")),
          next,
        ),
        h("nav.exam-nav", { "aria-label": tr("exam") }, navCells),
        h(
          "footer.qfoot",
          !last && h("button.link-btn", { type: "button", onclick: finish }, tr("examFinish")),
          sourceLink(q),
        ),
      ),
    );
    keyHandler = optionKeys(order, pick, next);
  }

  function examResult() {
    stopTimer();
    keyHandler = null;
    const questions = session.ids.map((x) => byId.get(x));
    const score = scoreExam(questions, session.answers);
    const reasons = [];
    if (score.correct < score.needed) reasons.push(tr("failScore", { needed: score.needed }));
    if (score.elimWrong) reasons.push(tr("failElim", { count: score.elimWrong }));

    render(
      topBar(),
      h(
        "section.hero",
        roundel(score.correct, `/${score.total}`, tr("scoreLabel", { correct: score.correct, total: score.total })),
        h(
          "div.hero__text",
          h(score.passed ? "h1.subtitle.verdict--right" : "h1.subtitle.verdict--wrong", score.passed ? tr("passed") : tr("failed")),
          reasons.map((r) => h("p", r)),
          h("p.muted.small", tr("examTime", { time: formatDuration(session.elapsed || 0) })),
        ),
      ),
      h(
        "div.btn-row",
        h("button.btn", { type: "button", onclick: () => (remove(examKey(cls)), viewExam()) }, tr("examAgain")),
        h("a.btn.btn--quiet", { href: "#/" }, tr("home")),
      ),
      h(
        "section.review-list",
        h("h2.subtitle", score.wrong.length ? tr("examMistakes", { count: score.wrong.length }) : tr("examNoMistakes")),
        score.wrong.map((id) => {
          const q = byId.get(id);
          const card = questionCard(q, {
            order: session.orders[id] || optionOrder(q),
            selected: new Set(session.answers[id] || []),
            translate: false,
          });
          card.reveal();
          return h("article.review-item", card.nodes, h("p.small", sourceLink(q)));
        }),
      ),
    );
  }
}

// ---------- glossary ----------

let glossaryPromise = null;

async function viewGlossary() {
  const nav = navId;
  render(topBar(), h("p.muted", tr("loading")));
  glossaryPromise ||= fetch("data/glossary.json").then((res) => {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  });
  let glossary;
  try {
    glossary = await glossaryPromise;
  } catch {
    glossaryPromise = null;
    if (nav === navId) render(topBar(), h("p.notice", tr("loadError")));
    return;
  }
  if (nav !== navId) return;

  // Spanish speakers get the English column; everyone else their own language.
  const lang = settings.lang === "es" ? "en" : settings.lang;
  const fold = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

  const collator = new Intl.Collator("es", { sensitivity: "base" });
  const rows = [];
  const sections = glossary.sections.map((section) => {
    const list = h("dl.terms");
    const el = h("section.gloss-section", h("h2.subtitle", section.title[settings.lang] || section.title.en), list);
    for (const term of [...section.terms].sort((x, y) => collator.compare(x.es, y.es))) {
      const row = h("div.term", h("dt", { lang: "es" }, term.es), h("dd", { lang }, term[lang] || term.en));
      list.append(row);
      rows.push({ row, section: el, text: fold(`${term.es} ${term[lang] || ""} ${term.en}`) });
    }
    return el;
  });

  const empty = h("p.muted", { hidden: true }, tr("glossaryNoMatch"));
  const search = h("input.search", {
    type: "search",
    placeholder: tr("glossarySearch"),
    "aria-label": tr("glossarySearch"),
    oninput: () => {
      const query = fold(search.value.trim());
      const visible = new Set();
      for (const r of rows) {
        const show = !query || r.text.includes(query);
        r.row.hidden = !show;
        if (show) visible.add(r.section);
      }
      for (const section of sections) section.hidden = !visible.has(section);
      empty.hidden = visible.size > 0;
    },
  });

  render(
    topBar(),
    h("section", h("h1.title", tr("glossary")), h("p.gloss-intro", tr("glossaryIntro")), search, empty, sections),
    footer(),
  );
}

// ---------- router ----------

let keyHandler = null;
document.addEventListener("keydown", (e) => keyHandler && keyHandler(e));

const ROUTES = {
  "": [viewHome, null],
  practice: [viewPractice, "practice"],
  exam: [viewExam, "exam"],
  review: [() => viewPractice("review"), "review"],
  glossary: [viewGlossary, "glossary"],
};

function route() {
  navId += 1;
  keyHandler = null;
  stopTimer();
  applyTheme();
  if (!settings.lang) return viewLanguage();
  if (!settings.cls) return viewClass();
  const [view, titleKey] = ROUTES[location.hash.replace(/^#\/?/, "")] || ROUTES[""];
  document.title = titleKey ? `${tr(titleKey)} — ${tr("appName")}` : tr("appName");
  view();
}

window.addEventListener("hashchange", route);
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", refreshThemeButtons);
route();
