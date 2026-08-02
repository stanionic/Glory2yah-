const express = require("express");
const router = express.Router();
const db = require("../db");
const gkach = require("../gkachClient");

/**
 * POST /savings/accounts
 * body: { user_id, wallet_id, product_type, term_days, initial_amount }
 */
router.post("/accounts", async (req, res, next) => {
  try {
    const { user_id, wallet_id, product_type, term_days, initial_amount } = req.body;
    if (!db.PRODUCT_TYPES.includes(product_type)) {
      return res.status(400).json({ error: `product_type doit être l'un de: ${db.PRODUCT_TYPES.join(", ")}` });
    }

    if (initial_amount > 0) {
      await gkach.withdraw(wallet_id, initial_amount, "savings_lock");
    }

    const account = db.createSavingsAccount({ user_id, wallet_id, product_type, term_days, initial_amount });
    res.status(201).json(account);
  } catch (err) {
    next(err);
  }
});

router.get("/accounts/:id", (req, res) => {
  const account = db.getSavingsAccount(req.params.id);
  if (!account) return res.status(404).json({ error: "Compte épargne introuvable" });
  res.json(account);
});

/**
 * POST /savings/:id/deposit
 */
router.post("/:id/deposit", async (req, res, next) => {
  try {
    const account = db.getSavingsAccount(req.params.id);
    if (!account) return res.status(404).json({ error: "Compte épargne introuvable" });
    if (account.product_type !== "libre" && account.status === "locked") {
      return res.status(422).json({ error: "Dépôt non autorisé sur ce produit une fois verrouillé" });
    }

    const { amount } = req.body;
    await gkach.withdraw(account.wallet_id, amount, "savings_deposit");
    account.principal += amount;
    res.status(201).json(account);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /savings/:id/withdraw
 * Applique une pénalité si retrait anticipé sur un produit bloqué.
 */
router.post("/:id/withdraw", async (req, res, next) => {
  try {
    const account = db.getSavingsAccount(req.params.id);
    if (!account) return res.status(404).json({ error: "Compte épargne introuvable" });

    const { amount } = req.body;
    if (amount > account.principal + account.accrued_interest) {
      return res.status(422).json({ error: "Solde épargne insuffisant" });
    }

    let penalty = 0;
    const isEarly = account.maturity_date && new Date() < new Date(account.maturity_date);
    if (account.product_type === "bloquee" && isEarly) {
      penalty = amount * 0.02; // pénalité de 2% en cas de retrait anticipé
    }

    const netAmount = amount - penalty;
    account.principal -= amount;
    await gkach.deposit(account.wallet_id, netAmount, "savings_withdrawal");

    res.status(200).json({ withdrawn: amount, penalty, net_credited: netAmount, account });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /savings/:id/close
 * Clôture le compte épargne, verse capital + intérêts accumulés au wallet.
 */
router.post("/:id/close", async (req, res, next) => {
  try {
    const account = db.getSavingsAccount(req.params.id);
    if (!account) return res.status(404).json({ error: "Compte épargne introuvable" });

    const total = account.principal + account.accrued_interest;
    if (total > 0) await gkach.deposit(account.wallet_id, total, "savings_closure");

    account.status = "closed";
    account.principal = 0;
    account.accrued_interest = 0;
    res.json({ closed_amount: total, account });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
