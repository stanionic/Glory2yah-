const { v4: uuid } = require("uuid");

const savingsAccounts = new Map();

// Taux annuels par défaut par produit (modifiables via /admin/interest-rates dans un système réel)
const PRODUCT_RATES = {
  libre: 0.03,
  bloquee: 0.08,
  programmee: 0.05,
};

const PRODUCT_TYPES = Object.keys(PRODUCT_RATES);

function createSavingsAccount({ user_id, wallet_id, product_type, term_days, initial_amount }) {
  const id = uuid();
  const account = {
    id,
    user_id,
    wallet_id,
    product_type,
    rate: PRODUCT_RATES[product_type],
    term_days: term_days || null,
    principal: initial_amount || 0,
    accrued_interest: 0,
    status: "active",
    created_at: new Date().toISOString(),
    maturity_date: term_days
      ? new Date(Date.now() + term_days * 24 * 60 * 60 * 1000).toISOString()
      : null,
  };
  savingsAccounts.set(id, account);
  return account;
}

function getSavingsAccount(id) {
  return savingsAccounts.get(id) || null;
}

/**
 * Intérêt simple : Capital x Taux annuel x (jours / 365)
 */
function computeInterest(account, days) {
  return account.principal * account.rate * (days / 365);
}

module.exports = { savingsAccounts, PRODUCT_TYPES, PRODUCT_RATES, createSavingsAccount, getSavingsAccount, computeInterest };
