// Per-question learning state (a small Leitner system) and next-question selection.
//
// Record: { box, seen, right, miss, at }
//   box   0 = never answered, 1 = learning (last answer wrong), 2..MASTERED_BOX = growing confidence
//   seen  total answers, right = correct answers
//   miss  true while the latest answer was wrong (feeds "Review mistakes")
//   at    timestamp of the latest answer
import { weightedPick } from "./random.js";

export const MASTERED_BOX = 4;

// How often each box is offered in practice, relative to each other.
const BOX_WEIGHT = { 0: 4, 1: 8, 2: 3, 3: 1.5, 4: 0.25 };

// Wrong answers come back soon, but not immediately.
export const RECENT_WINDOW = 6;

// Stored records may be old, corrupted or hand-edited: never trust the box value.
export function boxOf(record) {
  const box = record && record.box;
  return Number.isInteger(box) && box >= 0 && box <= MASTERED_BOX ? box : 0;
}

export function emptyRecord() {
  return { box: 0, seen: 0, right: 0, miss: false, at: 0 };
}

export function grade(record, ok, now = Date.now()) {
  const r = { ...emptyRecord(), ...record, box: boxOf(record) };
  r.seen = (Number(r.seen) || 0) + 1;
  r.right = Number(r.right) || 0;
  r.at = now;
  if (ok) {
    r.right += 1;
    r.box = Math.min(MASTERED_BOX, Math.max(r.box, 1) + 1);
    r.miss = false;
  } else {
    r.box = 1;
    r.miss = true;
  }
  return r;
}

export function isMastered(record) {
  return boxOf(record) >= MASTERED_BOX;
}

// Next question for practice: weighted by box, skipping the most recently shown ones
// (unless the pool is too small to skip them).
export function pickNext(questions, records, recent = [], rng = Math.random) {
  if (questions.length === 0) return null;
  const window = Math.min(RECENT_WINDOW, questions.length - 1);
  const skip = new Set(window > 0 ? recent.slice(-window) : []);
  const pool = questions.filter((q) => !skip.has(q.id));
  const weight = (q) => BOX_WEIGHT[boxOf(records[q.id])];
  return weightedPick(pool, weight, rng) || pool[0] || questions[0];
}

export function summary(questions, records) {
  let mastered = 0;
  let seen = 0;
  let mistakes = 0;
  for (const q of questions) {
    const r = records[q.id];
    if (!r) continue;
    seen += 1;
    if (isMastered(r)) mastered += 1;
    if (r.miss) mistakes += 1;
  }
  return { total: questions.length, seen, mastered, mistakes };
}
