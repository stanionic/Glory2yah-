const { v4: uuid } = require("uuid");

const interestRates = new Map(); // product_type -> { rate, effective_date, set_by_admin_id }
const investmentPlans = new Map();
const users = new Map();
const guaranteeFund = { balance: 0, cap: 1000000, coverage_percent: 80 };

function setInterestRate({ product_type, rate, admin_id }) {
  const record = { product_type, rate, effective_date: new Date().toISOString(), set_by_admin_id: admin_id };
  interestRates.set(product_type, record);
  return record;
}

function createInvestmentPlan(plan) {
  const id = plan.id || uuid();
  const record = { ...plan, id, created_at: new Date().toISOString() };
  investmentPlans.set(id, record);
  return record;
}

function upsertUser(user) {
  const existing = users.get(user.id) || {};
  const merged = { ...existing, ...user };
  users.set(merged.id, merged);
  return merged;
}

module.exports = {
  interestRates,
  investmentPlans,
  users,
  guaranteeFund,
  setInterestRate,
  createInvestmentPlan,
  upsertUser,
};
