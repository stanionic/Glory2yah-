const { v4: uuid } = require("uuid");

const loans = new Map();

const LOAN_TYPES = {
  personnel: { max_amount: 5000, default_rate: 0.14, max_term_months: 24 },
  commercial: { max_amount: 100000, default_rate: 0.12, max_term_months: 60 },
  agricole: { max_amount: 20000, default_rate: 0.09, max_term_months: 36 },
  urgence: { max_amount: 1000, default_rate: 0.18, max_term_months: 6 },
  etudiant: { max_amount: 10000, default_rate: 0.06, max_term_months: 48 },
};

const PENALTY_RATE_PER_DAY = 0.005; // 0.5%/jour de retard

function createLoan({ user_id, wallet_id, type, amount, term_months }) {
  const config = LOAN_TYPES[type];
  const id = uuid();
  const loan = {
    id,
    user_id,
    wallet_id,
    type,
    amount,
    interest_rate: config.default_rate,
    term_months,
    status: "pending", // pending -> approved -> disbursed -> active -> closed | rejected | defaulted
    ai_score: null,
    ai_risk: null,
    created_at: new Date().toISOString(),
    schedule: [],
  };
  loans.set(id, loan);
  return loan;
}

function getLoan(id) {
  return loans.get(id) || null;
}

/**
 * Génère un échéancier à mensualités constantes (amortissement linéaire simplifié).
 */
function generateSchedule(loan) {
  const monthlyPrincipal = loan.amount / loan.term_months;
  const monthlyRate = loan.interest_rate / 12;
  const schedule = [];
  let remaining = loan.amount;

  for (let i = 1; i <= loan.term_months; i++) {
    const interest = remaining * monthlyRate;
    const dueDate = new Date();
    dueDate.setMonth(dueDate.getMonth() + i);

    schedule.push({
      installment_number: i,
      due_date: dueDate.toISOString(),
      principal: Number(monthlyPrincipal.toFixed(2)),
      interest: Number(interest.toFixed(2)),
      amount_due: Number((monthlyPrincipal + interest).toFixed(2)),
      amount_paid: 0,
      status: "upcoming", // upcoming -> paid | late | defaulted
    });
    remaining -= monthlyPrincipal;
  }

  loan.schedule = schedule;
  return schedule;
}

function computePenalty(installment) {
  if (installment.status !== "late") return 0;
  const daysLate = Math.floor((Date.now() - new Date(installment.due_date)) / (1000 * 60 * 60 * 24));
  return Number((installment.amount_due * PENALTY_RATE_PER_DAY * Math.max(0, daysLate)).toFixed(2));
}

module.exports = { loans, LOAN_TYPES, createLoan, getLoan, generateSchedule, computePenalty, PENALTY_RATE_PER_DAY };
