// Probability of passing the real exam right now, from practice history.
//
// PBA rules (Manual del Conductor, Disposición 46/2019): at least 40 questions for the
// license class, 5 of them eliminatory; a pass needs >= 75 % correct AND every eliminatory
// question right. So: P(pass) = pE^5 * P(Binomial(35, pN) >= 25), where pE and pN are the
// mean chances of answering an eliminatory / regular question correctly. Drawing 40 out of
// several hundred questions is close enough to drawing with replacement.
import { EXAM } from "./exam-rules.js";
import { boxOf } from "./progress.js";

// Chance of a correct answer by Leitner box; box 0 (never answered) is a blind guess.
const BOX_P = { 1: 0.35, 2: 0.6, 3: 0.8, 4: 0.95 };

export function questionP(question, record) {
  const box = boxOf(record);
  if (box > 0) return BOX_P[box];
  const n = question.es.answers.length;
  return question.correct.length > 1 ? 1 / (2 ** n - 1) : 1 / n;
}

// P(X >= k) for X ~ Binomial(n, p)
export function binomialAtLeast(k, n, p) {
  if (k <= 0) return 1;
  if (k > n) return 0;
  if (p <= 0) return 0;
  if (p >= 1) return 1;
  let term = (1 - p) ** n; // P(X = 0)
  let below = 0;
  for (let i = 0; i < k; i++) {
    if (i > 0) term *= ((n - i + 1) / i) * (p / (1 - p));
    below += term;
  }
  return Math.min(1, Math.max(0, 1 - below));
}

function mean(values) {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
}

export function readiness(questions, records, rules = EXAM) {
  const elim = questions.filter((q) => q.eliminatory);
  const regular = questions.filter((q) => !q.eliminatory);
  const pElim = mean(elim.map((q) => questionP(q, records[q.id])));
  const pN = mean(regular.map((q) => questionP(q, records[q.id])));
  // A bank without eliminatory questions (should not happen) falls back to regular odds.
  const pE = elim.length ? pElim : pN;
  const regularCount = rules.questions - rules.eliminatory;
  const regularNeeded = Math.ceil(rules.questions * rules.passRatio) - rules.eliminatory;
  const pass = pE ** rules.eliminatory * binomialAtLeast(regularNeeded, regularCount, pN);
  return { pass, pE, pN };
}
