// Mock exam: draw a paper like the real one and score it by the official rules.
import { EXAM } from "./exam-rules.js";
import { shuffle } from "./random.js";
import { isCorrect } from "./question.js";

// `rules.eliminatory` eliminatory questions plus regular ones up to `rules.questions`,
// in random order. If the bank has too few eliminatory questions, regular ones fill in.
export function drawExam(questions, rules = EXAM, rng = Math.random) {
  const elim = shuffle(questions.filter((q) => q.eliminatory), rng).slice(0, rules.eliminatory);
  const regular = questions.filter((q) => !q.eliminatory);
  const rest = shuffle(regular, rng).slice(0, rules.questions - elim.length);
  return shuffle([...elim, ...rest], rng).map((q) => q.id);
}

// `answers`: { [id]: [selected option indices] }; unanswered questions count as wrong.
export function scoreExam(questions, answers, rules = EXAM) {
  let correct = 0;
  let elimWrong = 0;
  const wrong = [];
  for (const q of questions) {
    const ok = isCorrect(q, answers[q.id] || []);
    if (ok) correct += 1;
    else {
      wrong.push(q.id);
      if (q.eliminatory) elimWrong += 1;
    }
  }
  const needed = Math.ceil(questions.length * rules.passRatio);
  return { correct, total: questions.length, needed, elimWrong, wrong, passed: correct >= needed && elimWrong === 0 };
}
