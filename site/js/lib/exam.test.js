import { test } from "node:test";
import assert from "node:assert/strict";

import { drawExam, scoreExam } from "./exam.js";
import { EXAM } from "./exam-rules.js";
import { seeded } from "./random.js";

const bank = [];
for (let i = 0; i < 100; i++) bank.push({ id: `n${i}`, es: { q: "", answers: ["a", "b"] }, correct: [0] });
for (let i = 0; i < 12; i++) bank.push({ id: `e${i}`, eliminatory: true, es: { q: "", answers: ["a", "b"] }, correct: [0] });
const byId = new Map(bank.map((q) => [q.id, q]));

test("a drawn exam has 40 distinct questions, exactly 5 of them eliminatory", () => {
  for (let s = 0; s < 20; s++) {
    const ids = drawExam(bank, EXAM, seeded(s));
    assert.equal(ids.length, 40);
    assert.equal(new Set(ids).size, 40);
    assert.equal(ids.filter((id) => byId.get(id).eliminatory).length, 5);
  }
});

test("regular questions fill in when there are too few eliminatory ones", () => {
  const small = bank.filter((q) => !q.eliminatory).concat(bank.find((q) => q.eliminatory));
  const ids = drawExam(small, EXAM, seeded(1));
  assert.equal(ids.length, 40);
  assert.equal(ids.filter((id) => byId.get(id).eliminatory).length, 1);
});

function paper(wrongRegular, wrongElim) {
  const qs = drawExam(bank, EXAM, seeded(5)).map((id) => byId.get(id));
  const answers = {};
  let r = wrongRegular;
  let e = wrongElim;
  for (const q of qs) {
    const miss = q.eliminatory ? e-- > 0 : r-- > 0;
    answers[q.id] = [miss ? 1 : 0];
  }
  return scoreExam(qs, answers);
}

test("30 of 40 with all eliminatory questions right passes", () => {
  const s = paper(10, 0);
  assert.equal(s.correct, 30);
  assert.equal(s.needed, 30);
  assert.ok(s.passed);
});

test("31 of 40 fails if one eliminatory question is wrong", () => {
  const s = paper(8, 1);
  assert.equal(s.correct, 31);
  assert.equal(s.elimWrong, 1);
  assert.ok(!s.passed);
});

test("29 of 40 fails; unanswered questions count as wrong", () => {
  assert.ok(!paper(11, 0).passed);
  const qs = bank.slice(0, 40);
  const s = scoreExam(qs, {});
  assert.equal(s.correct, 0);
  assert.equal(s.wrong.length, 40);
});
