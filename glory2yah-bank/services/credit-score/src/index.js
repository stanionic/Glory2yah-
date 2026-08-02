require("dotenv").config();
const express = require("express");
const cors = require("cors");
const morgan = require("morgan");
const {
  computeCreditScore,
  riskLevelFromScore,
  predictDefaultProbability,
  evaluateFraud,
  alerts,
} = require("./scoring");

const app = express();
const PORT = process.env.PORT || 4600;

app.use(cors());
app.use(morgan("dev"));
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok", service: "ai-engine" }));

/**
 * GET /credit-score/:userId
 * Dans un système réel, le profil serait récupéré depuis les services
 * Accounts/Savings/Loans. Ici, il peut être fourni en query string pour la démo.
 */
app.get("/credit-score/:userId", (req, res) => {
  const profile = {
    account_age_months: Number(req.query.account_age_months) || 12,
    monthly_income: Number(req.query.monthly_income) || 500,
    avg_monthly_transactions: Number(req.query.avg_monthly_transactions) || 10,
    on_time_repayments_ratio: Number(req.query.on_time_repayments_ratio) || 0.9,
    balance_stability_index: Number(req.query.balance_stability_index) || 0.6,
  };
  const { score, breakdown } = computeCreditScore(profile);
  res.json({ user_id: req.params.userId, credit_score: score, risk_level: riskLevelFromScore(score), breakdown });
});

/**
 * POST /risk/evaluate
 * Utilisé par le Loan Service dans le pipeline de demande de prêt.
 * body: { user_id, amount, type, term_months, profile? }
 */
app.post("/risk/evaluate", (req, res) => {
  const { user_id, type, profile = {} } = req.body;
  const { score, breakdown } = computeCreditScore(profile);
  const risk_level = riskLevelFromScore(score);
  const default_probability = predictDefaultProbability(score, type);

  res.json({ user_id, credit_score: score, risk_level, default_probability, breakdown });
});

/**
 * POST /fraud/evaluate
 * body: transaction { id, amount, transactions_last_hour, new_device, country_mismatch }
 */
app.post("/fraud/evaluate", (req, res) => {
  res.json(evaluateFraud(req.body));
});

/**
 * GET /fraud/alerts
 */
app.get("/fraud/alerts", (_req, res) => {
  res.json(alerts);
});

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: "Erreur interne AI Engine" });
});

app.listen(PORT, () => console.log(`🤖  AI Engine (Credit Score / Fraud) — écoute sur le port ${PORT}`));
