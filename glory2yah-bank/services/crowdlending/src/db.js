const { v4: uuid } = require("uuid");

// Opportunités de financement publiées (миroir d'un prêt validé par l'admin
// et ouvert au financement participatif plutôt qu'au décaissement direct)
const opportunities = new Map();
const contributions = new Map(); // id -> { opportunity_id, investor_id, investor_wallet_id, amount }

function publishOpportunity({ loan_id, borrower_wallet_id, amount, expected_return, risk_level, duration_months }) {
  const opportunity = {
    id: loan_id,
    borrower_wallet_id,
    amount_requested: amount,
    amount_funded: 0,
    expected_return,
    risk_level,
    duration_months,
    status: "open", // open -> funded -> disbursed -> repaying -> closed
    created_at: new Date().toISOString(),
  };
  opportunities.set(loan_id, opportunity);
  return opportunity;
}

function getOpportunity(id) {
  return opportunities.get(id) || null;
}

function addContribution({ opportunity_id, investor_id, investor_wallet_id, amount }) {
  const id = uuid();
  const contribution = { id, opportunity_id, investor_id, investor_wallet_id, amount, created_at: new Date().toISOString() };
  contributions.set(id, contribution);
  return contribution;
}

function listContributionsByOpportunity(opportunity_id) {
  return Array.from(contributions.values()).filter((c) => c.opportunity_id === opportunity_id);
}

function listContributionsByInvestor(investor_id) {
  return Array.from(contributions.values()).filter((c) => c.investor_id === investor_id);
}

module.exports = {
  opportunities,
  contributions,
  publishOpportunity,
  getOpportunity,
  addContribution,
  listContributionsByOpportunity,
  listContributionsByInvestor,
};
