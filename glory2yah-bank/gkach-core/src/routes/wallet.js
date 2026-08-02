const express = require("express");
const router = express.Router();
const db = require("../db");
const { publish } = require("../events");

/**
 * POST /wallet/create
 * Crée un wallet GKach pour un compte Glory2Yah Bank.
 */
router.post("/create", (req, res) => {
  const { owner_ref, currency, type } = req.body;
  if (!owner_ref) return res.status(400).json({ error: "owner_ref est requis" });

  const wallet = db.createWallet({ owner_ref, currency, type });
  publish("wallet.created", wallet);
  res.status(201).json(wallet);
});

/**
 * GET /wallet/balance?wallet_id=...
 */
router.get("/balance", (req, res) => {
  const { wallet_id } = req.query;
  const wallet = db.getWallet(wallet_id);
  if (!wallet) return res.status(404).json({ error: "Wallet introuvable" });
  res.json({ wallet_id: wallet.id, balance: wallet.balance, currency: wallet.currency });
});

/**
 * GET /wallet/transactions?wallet_id=...
 */
router.get("/transactions", (req, res) => {
  const { wallet_id } = req.query;
  if (!db.getWallet(wallet_id)) return res.status(404).json({ error: "Wallet introuvable" });
  res.json(db.listWalletTransactions(wallet_id));
});

/**
 * POST /wallet/deposit
 * body: { wallet_id, amount, method }
 */
router.post("/deposit", (req, res) => {
  const { wallet_id, amount, method = "manual" } = req.body;
  const wallet = db.getWallet(wallet_id);
  if (!wallet) return res.status(404).json({ error: "Wallet introuvable" });
  if (!(amount > 0)) return res.status(400).json({ error: "Montant invalide" });

  wallet.balance += amount;
  db.writeLedgerEntry({ wallet_id, type: "deposit", amount, metadata: { method } });
  const txn = db.recordTransaction({
    type: "deposit",
    status: "completed",
    amount,
    wallet_id,
    metadata: { method },
  });

  publish("wallet.deposited", { wallet_id, amount, txn_id: txn.id });
  res.status(201).json({ transaction: txn, balance: wallet.balance });
});

/**
 * POST /wallet/withdraw
 * body: { wallet_id, amount, method }
 */
router.post("/withdraw", (req, res) => {
  const { wallet_id, amount, method = "manual" } = req.body;
  const wallet = db.getWallet(wallet_id);
  if (!wallet) return res.status(404).json({ error: "Wallet introuvable" });
  if (!(amount > 0)) return res.status(400).json({ error: "Montant invalide" });
  if (wallet.balance < amount) return res.status(422).json({ error: "Solde insuffisant" });

  wallet.balance -= amount;
  db.writeLedgerEntry({ wallet_id, type: "withdrawal", amount, metadata: { method } });
  const txn = db.recordTransaction({
    type: "withdrawal",
    status: "completed",
    amount,
    wallet_id,
    metadata: { method },
  });

  publish("wallet.withdrawn", { wallet_id, amount, txn_id: txn.id });
  res.status(201).json({ transaction: txn, balance: wallet.balance });
});

/**
 * POST /wallet/transfer
 * body: { from_wallet_id, to_wallet_id, amount }
 */
router.post("/transfer", (req, res) => {
  const { from_wallet_id, to_wallet_id, amount } = req.body;
  const from = db.getWallet(from_wallet_id);
  const to = db.getWallet(to_wallet_id);
  if (!from || !to) return res.status(404).json({ error: "Wallet source ou destination introuvable" });
  if (!(amount > 0)) return res.status(400).json({ error: "Montant invalide" });
  if (from.balance < amount) return res.status(422).json({ error: "Solde insuffisant" });

  from.balance -= amount;
  to.balance += amount;

  db.writeLedgerEntry({ wallet_id: from_wallet_id, type: "transfer_out", amount, ref: to_wallet_id });
  db.writeLedgerEntry({ wallet_id: to_wallet_id, type: "transfer_in", amount, ref: from_wallet_id });

  const txn = db.recordTransaction({
    type: "transfer",
    status: "completed",
    amount,
    wallet_id: from_wallet_id,
    counterparty_wallet_id: to_wallet_id,
  });

  publish("wallet.transferred", { from_wallet_id, to_wallet_id, amount, txn_id: txn.id });
  res.status(201).json({ transaction: txn, from_balance: from.balance, to_balance: to.balance });
});

/**
 * POST /wallet/qr/generate
 * body: { wallet_id, amount }
 */
router.post("/qr/generate", (req, res) => {
  const { wallet_id, amount } = req.body;
  const wallet = db.getWallet(wallet_id);
  if (!wallet) return res.status(404).json({ error: "Wallet introuvable" });

  const code = `QR-${wallet_id.slice(0, 8)}-${Date.now()}`;
  db.qrCodes.set(code, {
    wallet_id,
    amount: amount || null,
    used: false,
    expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
  });
  res.status(201).json({ qr_code: code, expires_in_seconds: 900 });
});

/**
 * POST /wallet/qr/pay
 * body: { qr_code, payer_wallet_id, amount }
 */
router.post("/qr/pay", (req, res) => {
  const { qr_code, payer_wallet_id, amount } = req.body;
  const qr = db.qrCodes.get(qr_code);
  if (!qr) return res.status(404).json({ error: "QR code introuvable" });
  if (qr.used) return res.status(409).json({ error: "QR code déjà utilisé" });
  if (new Date(qr.expires_at) < new Date()) return res.status(410).json({ error: "QR code expiré" });

  const finalAmount = qr.amount || amount;
  const payer = db.getWallet(payer_wallet_id);
  const merchant = db.getWallet(qr.wallet_id);
  if (!payer || !merchant) return res.status(404).json({ error: "Wallet introuvable" });
  if (payer.balance < finalAmount) return res.status(422).json({ error: "Solde insuffisant" });

  payer.balance -= finalAmount;
  merchant.balance += finalAmount;
  qr.used = true;

  db.writeLedgerEntry({ wallet_id: payer_wallet_id, type: "qr_payment_out", amount: finalAmount, ref: qr.wallet_id });
  db.writeLedgerEntry({ wallet_id: qr.wallet_id, type: "qr_payment_in", amount: finalAmount, ref: payer_wallet_id });

  const txn = db.recordTransaction({
    type: "qr_payment",
    status: "completed",
    amount: finalAmount,
    wallet_id: payer_wallet_id,
    counterparty_wallet_id: qr.wallet_id,
  });

  publish("wallet.qr_paid", { qr_code, amount: finalAmount, txn_id: txn.id });
  res.status(201).json({ transaction: txn });
});

module.exports = router;
