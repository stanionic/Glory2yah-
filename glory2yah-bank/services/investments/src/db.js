const { v4: uuid } = require("uuid");

// Plans configurables par l'administrateur (voir POST /admin/investment-plans)
const plans = new Map([
  ["bronze", { id: "bronze", name: "Bronze", duration_months: 3, rate: 0.05, risk: "faible", min_amount: 50 }],
  ["silver", { id: "silver", name: "Silver", duration_months: 6, rate: 0.075, risk: "modéré", min_amount: 200 }],
  ["gold", { id: "gold", name: "Gold", duration_months: 12, rate: 0.11, risk: "moyen-élevé", min_amount: 1000 }],
  ["platinum", { id: "platinum", name: "Platinum", duration_months: 24, rate: 0.155, risk: "élevé", min_amount: 5000 }],
]);

const investments = new Map();

function createInvestment({ user_id, wallet_id, plan_id, amount }) {
  const plan = plans.get(plan_id);
  const id = uuid();
  const startDate = new Date();
  const endDate = new Date(startDate);
  endDate.setMonth(endDate.getMonth() + plan.duration_months);

  const investment = {
    id,
    user_id,
    wallet_id,
    plan_id,
    amount,
    rate: plan.rate,
    status: "active",
    start_date: startDate.toISOString(),
    end_date: endDate.toISOString(),
  };
  investments.set(id, investment);
  return investment;
}

function getInvestment(id) {
  return investments.get(id) || null;
}

function currentPerformance(investment) {
  const elapsedMs = Date.now() - new Date(investment.start_date).getTime();
  const elapsedDays = Math.max(0, elapsedMs / (1000 * 60 * 60 * 24));
  const accrued = investment.amount * investment.rate * (elapsedDays / 365);
  const totalDurationDays =
    (new Date(investment.end_date) - new Date(investment.start_date)) / (1000 * 60 * 60 * 24);
  const progressPercent = Math.min(100, (elapsedDays / totalDurationDays) * 100);
  return { accrued_interest: Number(accrued.toFixed(2)), progress_percent: Number(progressPercent.toFixed(2)) };
}

module.exports = { plans, investments, createInvestment, getInvestment, currentPerformance };
