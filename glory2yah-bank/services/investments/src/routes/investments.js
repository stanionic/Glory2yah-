const express = require("express");
const router = express.Router();
const db = require("../db");
const gkach = require("../gkachClient");

router.get("/plans", (_req, res) => {
  res.json(Array.from(db.plans.values()));
});

/**
 * POST /investment/create
 * body: { user_id, wallet_id, plan_id, amount }
 */
router.post("/create", async (req, res, next) => {
  try {
    const { user_id, wallet_id, plan_id, amount } = req.body;
    const plan = db.plans.get(plan_id);
    if (!plan) return res.status(400).json({ error: "Plan d'investissement inconnu" });
    if (amount < plan.min_amount) {
      return res.status(422).json({ error: `Montant minimum pour ${plan.name}: ${plan.min_amount}` });
    }

    await gkach.withdraw(wallet_id, amount, "investment_subscription");
    const investment = db.createInvestment({ user_id, wallet_id, plan_id, amount });
    res.status(201).json(investment);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /investment/:id/performance
 */
router.get("/:id/performance", (req, res) => {
  const investment = db.getInvestment(req.params.id);
  if (!investment) return res.status(404).json({ error: "Investissement introuvable" });
  res.json({ investment, ...db.currentPerformance(investment) });
});

/**
 * POST /investment/:id/withdraw
 * Rachat de l'investissement (au terme ou anticipé avec pénalité simplifiée).
 */
router.post("/:id/withdraw", async (req, res, next) => {
  try {
    const investment = db.getInvestment(req.params.id);
    if (!investment) return res.status(404).json({ error: "Investissement introuvable" });
    if (investment.status !== "active") return res.status(409).json({ error: "Investissement déjà clôturé" });

    const { accrued_interest } = db.currentPerformance(investment);
    const isMatured = new Date() >= new Date(investment.end_date);
    const penalty = isMatured ? 0 : investment.amount * 0.03;
    const total = investment.amount + accrued_interest - penalty;

    await gkach.deposit(investment.wallet_id, total, "investment_redemption");
    investment.status = "closed";

    res.json({ redeemed_amount: total, penalty, matured: isMatured, investment });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
