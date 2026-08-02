const express = require("express");
const router = express.Router();
const db = require("../db");
const gkach = require("../gkachClient");

/**
 * POST /accounts
 * body: { user_id, account_type, currency }
 * Crée un compte bancaire Glory2Yah Bank ET son wallet GKach associé.
 */
router.post("/", async (req, res, next) => {
  try {
    const { user_id, account_type, currency } = req.body;
    if (!user_id || !db.VALID_TYPES.includes(account_type)) {
      return res.status(400).json({ error: `account_type doit être l'un de: ${db.VALID_TYPES.join(", ")}` });
    }

    const wallet = await gkach.createWallet(user_id, currency);
    const account = db.createAccount({ user_id, account_type, wallet_id: wallet.id, currency });

    res.status(201).json(account);
  } catch (err) {
    next(err);
  }
});

router.get("/:id", (req, res) => {
  const account = db.getAccount(req.params.id);
  if (!account) return res.status(404).json({ error: "Compte introuvable" });
  res.json(account);
});

router.patch("/:id", (req, res) => {
  const account = db.updateAccount(req.params.id, req.body);
  if (!account) return res.status(404).json({ error: "Compte introuvable" });
  res.json(account);
});

router.post("/:id/suspend", (req, res) => {
  const account = db.updateAccount(req.params.id, { status: "suspended" });
  if (!account) return res.status(404).json({ error: "Compte introuvable" });
  res.json(account);
});

/**
 * GET /accounts/:id/statement
 * Agrège le solde et l'historique depuis GKach.
 */
router.get("/:id/statement", async (req, res, next) => {
  try {
    const account = db.getAccount(req.params.id);
    if (!account) return res.status(404).json({ error: "Compte introuvable" });

    const balance = await gkach.getBalance(account.wallet_id);
    const transactions = await gkach.getTransactions(account.wallet_id);

    res.json({ account, balance: balance.balance, currency: balance.currency, transactions });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
