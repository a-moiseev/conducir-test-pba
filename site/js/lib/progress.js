// Per-question learning state and next-question selection.
//
// Record: { box, seen, right, miss, at, step }
//   box   0 = never answered, 1 = last answer wrong, 2 = right but not learned yet,
//         MASTERED_BOX = learned: two right answers in total and the latest one right
//   seen  total answers, right = correct answers
//   miss  true while the latest answer was wrong (feeds "Review mistakes")
//   at    timestamp of the latest answer
//   step  how many answers the class had before this question's latest answer
import { weightedPick } from "./random.js";

export const MASTERED_BOX = 3;
const RIGHT_TO_LEARN = 2;

// Hard floor: the last few questions never come back immediately, whatever the records say.
export const RECENT_WINDOW = 6;

// Answers in between before a question may come back, by box. Wrong answers return
// soon, right ones later, learned ones only now and then.
export const MIN_GAP = { 1: 10, 2: 30, 3: 150 };

// When questions due for another try exist, this share of picks goes to them;
// the rest are new questions, and a few are learned ones to keep them fresh.
const DUE_SHARE = 0.4;
const REFRESH_SHARE = 0.1;

const count = (value) => (Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0);

// Stored records may be old, corrupted or hand-edited: derive the box from what is known.
// Records from when learning took three right answers in a row (boxes 3 and 4) stay learned.
export function boxOf(record) {
  const box = record && record.box;
  if (!Number.isInteger(box) || box <= 0) return 0;
  if (record.miss) return 1;
  if (box >= MASTERED_BOX || count(record.right) >= RIGHT_TO_LEARN) return MASTERED_BOX;
  return box === 1 ? 1 : 2;
}

export function emptyRecord() {
  return { box: 0, seen: 0, right: 0, miss: false, at: 0, step: 0 };
}

// Total answers given in a class: the clock that question gaps are measured in.
export function answerCount(records) {
  let total = 0;
  for (const r of Object.values(records)) total += count(r && r.seen);
  return total;
}

export function grade(record, ok, now = Date.now(), step = 0) {
  const r = { ...emptyRecord(), ...record };
  r.seen = count(r.seen) + 1;
  r.right = count(r.right) + (ok ? 1 : 0);
  r.miss = !ok;
  r.at = now;
  r.step = step;
  r.box = ok ? (r.right >= RIGHT_TO_LEARN ? MASTERED_BOX : 2) : 1;
  return r;
}

export function isMastered(record) {
  return boxOf(record) >= MASTERED_BOX;
}

// Next question: due tries first (now and then), otherwise new questions, sometimes a
// learned one. Nothing returns before its gap has passed, unless every question waits;
// then the most overdue one comes, still skipping the most recently shown.
export function pickNext(questions, records, recent = [], rng = Math.random) {
  if (questions.length === 0) return null;
  const window = Math.min(RECENT_WINDOW, questions.length - 1);
  const skip = new Set(window > 0 ? recent.slice(-window) : []);
  const pool = questions.filter((q) => !skip.has(q.id));
  const now = answerCount(records);

  const fresh = [];
  const due = [];
  const refresh = [];
  const waiting = [];
  for (const q of pool) {
    const r = records[q.id];
    const box = boxOf(r);
    if (box === 0) {
      fresh.push(q);
      continue;
    }
    // Records saved before steps existed have no step: treat them as long ago.
    const age = Number.isFinite(r.step) ? now - r.step : Infinity;
    if (age < MIN_GAP[box]) waiting.push({ q, overdue: age / MIN_GAP[box] });
    else if (box === MASTERED_BOX) refresh.push(q);
    else due.push(q);
  }

  const any = (list) => list[Math.floor(rng() * list.length)];
  if (due.length && (!fresh.length || rng() < DUE_SHARE)) {
    return weightedPick(due, (q) => (boxOf(records[q.id]) === 1 ? 2 : 1), rng) || due[0];
  }
  if (fresh.length && (!refresh.length || rng() >= REFRESH_SHARE)) return any(fresh);
  if (refresh.length) return any(refresh);
  if (waiting.length) return waiting.reduce((a, b) => (b.overdue > a.overdue ? b : a)).q;
  return questions[0];
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
