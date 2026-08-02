/**
 * GKach — Couche de persistance (démo en mémoire).
 *
 * En production, remplacer par PostgreSQL (voir /shared/sql/schema.sql)
 * avec transactions ACID strictes sur les tables Wallets / Ledger.
 * GKach est la SEULE source de vérité pour l'argent : aucun autre
 * service ne doit écrire directement dans ces structures.
 */

const { v4: uuid } = require("uuid");

const wallets = new Map();       // wallet_id -> { id, owner_ref, currency, balance, status, created_at }
const ledger = [];               // liste append-only de toutes les écritures comptables
const transactions = new Map();  // transaction_id -> transaction record
const qrCodes = new Map();       // qr_code -> { wallet_id, amount, expires_at, used }

function createWallet({ owner_ref, currency = "USD", type = "standard" }) {
  const id = uuid();
  const wallet = {
    id,
    owner_ref,
    currency,
    type,
    balance: 0,
    status: "active",
    created_at: new Date().toISOString(),
  };
  wallets.set(id, wallet);
  return wallet;
}

function getWallet(id) {
  return wallets.get(id) || null;
}

function writeLedgerEntry({ wallet_id, type, amount, ref, metadata }) {
  const entry = {
    id: uuid(),
    wallet_id,
    type, // deposit | withdrawal | transfer_in | transfer_out | fee | interest | disbursement | repayment
    amount,
    ref: ref || null,
    metadata: metadata || {},
    created_at: new Date().toISOString(),
  };
  ledger.push(entry);
  return entry;
}

function recordTransaction({ type, status, amount, wallet_id, counterparty_wallet_id, metadata }) {
  const id = uuid();
  const txn = {
    id,
    type, // deposit | withdrawal | transfer | payment | qr_payment | disbursement | repayment
    status, // completed | failed | pending
    amount,
    wallet_id,
    counterparty_wallet_id: counterparty_wallet_id || null,
    metadata: metadata || {},
    created_at: new Date().toISOString(),
  };
  transactions.set(id, txn);
  return txn;
}

function listWalletTransactions(wallet_id) {
  return Array.from(transactions.values())
    .filter((t) => t.wallet_id === wallet_id || t.counterparty_wallet_id === wallet_id)
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
}

module.exports = {
  wallets,
  ledger,
  transactions,
  qrCodes,
  createWallet,
  getWallet,
  writeLedgerEntry,
  recordTransaction,
  listWalletTransactions,
};
