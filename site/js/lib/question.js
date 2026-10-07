// Question helpers: option order, grading, localized text.
import { shuffle } from "./random.js";

// Option indices in display order. Questions whose options refer to each other
// ("Ambas respuestas, A y B…") keep the original order.
export function optionOrder(question, rng = Math.random) {
  const order = question.es.answers.map((_, i) => i);
  return question.fixedOrder ? order : shuffle(order, rng);
}

// `selected` is a list of original option indices. Multi-answer questions need the exact set.
export function isCorrect(question, selected) {
  const want = new Set(question.correct);
  const got = new Set(selected);
  if (want.size !== got.size) return false;
  for (const i of got) if (!want.has(i)) return false;
  return true;
}

export function isMulti(question) {
  return question.type === "multi" || question.correct.length > 1;
}

// Text in the requested language, falling back to the Spanish original.
export function localized(question, lang) {
  const tr = lang !== "es" && question[lang];
  return tr || question.es;
}

export function hasTranslation(question, lang) {
  return lang !== "es" && Boolean(question[lang]);
}
