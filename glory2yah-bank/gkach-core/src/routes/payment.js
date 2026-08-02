const express = require("express");
const router = express.Router();
const db = require("../db");
const { publish } = require("../events");

/**
 * POST /payment/disburse
 * Utilisé par le Loan Service pour décaisser un prêt approuvé.
 * body: { to_wallet_id, amount, ref }
 */
router.post("/disburse", (req, res) => {
  const { to_wallet_id, amount, ref } = req.body;
  const wallet = db.getWallet(to_wallet_id);
  if (!wallet) return res.status(404).json({ error: "Wallet introuvable" });
  if (!(amount > 0)) return res.status(400).json({ error: "Montant invalide" });

  wallet.balance += amount;
  db.writeLedgerEntry({ wallet_id: to_wallet_id, type: "disbursement", amount, ref });
  const txn = db.recordTransaction({
    type: "disbursement",
    status: "completed",
    amount,
    wallet_id: to_wallet_id,
    metadata: { ref },
  });

  publish("loan.disbursed", { to_wallet_id, amount, ref, txn_id: txn.id });
  res.status(201).json({ transaction: txn, balance: wallet.balance });
});

/**
 * POST /payment/repay
 * Prélèvement d'une échéance de prêt sur le wallet de l'emprunteur.
 * body: { from_wallet_id, amount, ref }
 */
router.post("/repay", (req, res) => {
  const { from_wallet_id, amount, ref } = req.body;
  const wallet = db.getWallet(from_wallet_id);
  if (!wallet) return res.status(404).json({ error: "Wallet introuvable" });
  if (wallet.balance < amount) return res.status(422).json({ error: "Solde insuffisant" });

  wallet.balance -= amount;
  db.writeLedgerEntry({ wallet_id: from_wallet_id, type: "repayment", amount, ref });
  const txn = db.recordTransaction({
    type: "repayment",
    status: "completed",
    amount,
    wallet_id: from_wallet_id,
    metadata: { ref },
  });

  publish("loan.repayment.received", { from_wallet_id, amount, ref, txn_id: txn.id });
  res.status(201).json({ transaction: txn, balance: wallet.balance });
});

/**
 * POST /payment/escrow-hold
 * Utilisé par le Crowdlending Service pour mettre des fonds en séquestre.
 * body: { wallet_id, amount, ref }
 */
router.post("/escrow-hold", (req, res) => {
  const { wallet_id, amount, ref } = req.body;
  const wallet = db.getWallet(wallet_id);
  if (!wallet) return res.status(404).json({ error: "Wallet introuvable" });
  if (wallet.balance < amount) return res.status(422).json({ error: "Solde insuffisant" });

  wallet.balance -= amount;
  db.writeLedgerEntry({ wallet_id, type: "escrow_hold", amount, ref });
  const txn = db.recordTransaction({
    type: "escrow_hold",
    status: "completed",
    amount,
    wallet_id,
    metadata: { ref },
  });

  publish("escrow.held", { wallet_id, amount, ref, txn_id: txn.id });
  res.status(201).json({ transaction: txn, balance: wallet.balance });
});

module.exports = router;
