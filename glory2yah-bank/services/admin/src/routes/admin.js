const express = require("express");
const router = express.Router();
const db = require("../db");

/**
 * GET /admin/dashboard
 * Vue agrégée — dans un système réel, interroge chaque microservice
 * (Loans, Investments, Savings) et le data warehouse de reporting.
 */
router.get("/dashboard", (_req, res) => {
  res.json({
    users_total: db.users.size,
    investment_plans: db.investmentPlans.size,
    interest_rates_configured: db.interestRates.size,
    guarantee_fund: db.guaranteeFund,
    generated_at: new Date().toISOString(),
  });
});

router.get("/liquidity", (_req, res) => {
  // Exemple simplifié — en production agrégé depuis GKach + Reporting Service
  res.json({
    reserve_ratio_target: 0.1,
    note: "Brancher sur les soldes agrégés GKach pour un ratio de liquidité réel.",
  });
});

router.post("/interest-rates", (req, res) => {
  const { product_type, rate, admin_id } = req.body;
  if (!product_type || rate == null) return res.status(400).json({ error: "product_type et rate sont requis" });
  res.status(201).json(db.setInterestRate({ product_type, rate, admin_id }));
});

router.get("/interest-rates", (_req, res) => {
  res.json(Array.from(db.interestRates.values()));
});

router.post("/investment-plans", (req, res) => {
  res.status(201).json(db.createInvestmentPlan(req.body));
});

router.get("/investment-plans", (_req, res) => {
  res.json(Array.from(db.investmentPlans.values()));
});

router.get("/users", (_req, res) => {
  res.json(Array.from(db.users.values()));
});

router.patch("/users/:id/role", (req, res) => {
  const user = db.upsertUser({ id: req.params.id, role: req.body.role });
  res.json(user);
});

module.exports = router;
