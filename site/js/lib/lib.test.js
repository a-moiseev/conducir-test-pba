import { test } from "node:test";
import assert from "node:assert/strict";

import { shuffle, weightedPick, seeded } from "./random.js";
import { optionOrder, isCorrect, isMulti, localized } from "./question.js";
import { grade, emptyRecord, isMastered, pickNext, summary, MASTERED_BOX } from "./progress.js";
import { t, UI_LANGS, _STRINGS_FOR_TESTS } from "./strings.js";

const q = (id, extra = {}) => ({
  id,
  type: "choice",
  es: { q: `q${id}`, answers: ["a", "b", "c"] },
  correct: [1],
  ...extra,
});

test("shuffle keeps all items", () => {
  const out = shuffle([1, 2, 3, 4, 5], seeded(1));
  assert.deepEqual([...out].sort(), [1, 2, 3, 4, 5]);
});

test("weightedPick never returns zero-weight items", () => {
  const rng = seeded(7);
  for (let i = 0; i < 200; i++) {
    assert.notEqual(weightedPick(["x", "y"], (v) => (v === "x" ? 0 : 1), rng), "x");
  }
  assert.equal(weightedPick(["x"], () => 0), null);
});

test("fixed-order questions are not shuffled", () => {
  const question = q(1, { fixedOrder: true, es: { q: "", answers: ["a", "b", "c", "d"] } });
  for (let s = 0; s < 20; s++) assert.deepEqual(optionOrder(question, seeded(s)), [0, 1, 2, 3]);
});

test("isCorrect needs the exact set for multi-answer questions", () => {
  const multi = q(1, { type: "multi", correct: [0, 2] });
  assert.ok(isMulti(multi));
  assert.ok(isCorrect(multi, [2, 0]));
  assert.ok(!isCorrect(multi, [0]));
  assert.ok(!isCorrect(multi, [0, 1, 2]));
  assert.ok(isCorrect(q(2), [1]));
  assert.ok(!isCorrect(q(2), [0]));
});

test("localized falls back to Spanish", () => {
  const question = q(1, { ru: { q: "в", answers: ["а", "б", "в"] } });
  assert.equal(localized(question, "ru").q, "в");
  assert.equal(localized(question, "en").q, "q1");
  assert.equal(localized(question, "es").q, "q1");
});

test("three right answers in a row master a new question; a miss resets it", () => {
  let r = emptyRecord();
  r = grade(r, true, 1);
  r = grade(r, true, 2);
  assert.ok(!isMastered(r));
  r = grade(r, true, 3);
  assert.ok(isMastered(r));
  assert.equal(r.box, MASTERED_BOX);
  r = grade(r, false, 4);
  assert.equal(r.box, 1);
  assert.ok(r.miss);
  assert.equal(r.seen, 4);
  assert.equal(r.right, 3);
});

test("pickNext avoids recently shown questions and prefers weak ones", () => {
  const qs = [q("a"), q("b"), q("c"), q("d")];
  const records = { a: { box: 4 }, b: { box: 4 }, c: { box: 1 }, d: { box: 4 } };
  const rng = seeded(3);
  const counts = { a: 0, b: 0, c: 0, d: 0 };
  for (let i = 0; i < 400; i++) counts[pickNext(qs, records, [], rng).id] += 1;
  assert.ok(counts.c > counts.a * 5, JSON.stringify(counts));
  for (let i = 0; i < 50; i++) assert.notEqual(pickNext(qs, records, ["c"], rng).id, "c");
});

test("pickNext still works with a single question", () => {
  assert.equal(pickNext([q("only")], {}, ["only"]).id, "only");
  assert.equal(pickNext([], {}), null);
});

test("summary counts", () => {
  const qs = [q("a"), q("b"), q("c")];
  const s = summary(qs, { a: { box: 4 }, b: { box: 1, miss: true } });
  assert.deepEqual(s, { total: 3, seen: 2, mastered: 1, mistakes: 1 });
});

test("every UI language defines every string", () => {
  const keys = Object.keys(_STRINGS_FOR_TESTS.en);
  for (const lang of UI_LANGS) {
    assert.deepEqual(Object.keys(_STRINGS_FOR_TESTS[lang]).sort(), [...keys].sort(), lang);
  }
  assert.equal(t("ru", "learnedOf", { learned: 2, total: 5 }), "Выучено: 2 из 5");
});

import { readiness, binomialAtLeast, questionP } from "./readiness.js";

test("binomialAtLeast edge cases and a known value", () => {
  assert.equal(binomialAtLeast(0, 10, 0.3), 1);
  assert.equal(binomialAtLeast(11, 10, 0.9), 0);
  assert.ok(Math.abs(binomialAtLeast(1, 2, 0.5) - 0.75) < 1e-12);
  assert.ok(Math.abs(binomialAtLeast(25, 35, 1) - 1) < 1e-12);
});

test("readiness is near zero for a beginner and high once everything is learned", () => {
  const qs = [];
  for (let i = 0; i < 100; i++) qs.push(q(`n${i}`));
  for (let i = 0; i < 20; i++) qs.push(q(`e${i}`, { eliminatory: true }));
  assert.ok(readiness(qs, {}).pass < 0.001);
  const all = Object.fromEntries(qs.map((x) => [x.id, { box: 4 }]));
  const r = readiness(qs, all);
  assert.ok(r.pass > 0.7 && r.pass < 1, String(r.pass));
  // Eliminatory questions weigh more: forgetting them hurts more than forgetting regular ones.
  const weakElim = { ...all, ...Object.fromEntries(qs.filter((x) => x.eliminatory).map((x) => [x.id, { box: 1 }])) };
  assert.ok(readiness(qs, weakElim).pass < 0.05);
});

test("guess probability for unseen multi-answer questions", () => {
  assert.equal(questionP(q("x"), undefined), 1 / 3);
  assert.equal(questionP(q("y", { correct: [0, 2] }), undefined), 1 / 7);
});

test("corrupted records are treated as unseen instead of producing NaN", () => {
  const qs = [q("a"), q("b"), q("c", { eliminatory: true })];
  const bad = { a: { box: 5 }, b: { box: "2" }, c: null };
  assert.ok(Number.isFinite(readiness(qs, bad).pass));
  assert.ok(["a", "b", "c"].includes(pickNext(qs, bad, [], seeded(2)).id));
  assert.equal(grade({ box: 9, seen: "x" }, true, 1).box, 2);
});

test("a bank without eliminatory questions still gets a pass estimate", () => {
  const qs = Array.from({ length: 50 }, (_, i) => q(`r${i}`));
  const all = Object.fromEntries(qs.map((x) => [x.id, { box: 4 }]));
  assert.ok(readiness(qs, all).pass > 0.5);
});
