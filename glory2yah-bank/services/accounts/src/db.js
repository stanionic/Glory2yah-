const { v4: uuid } = require("uuid");

const accounts = new Map(); // id -> BankAccount

const VALID_TYPES = ["personnel", "entreprise", "eglise", "ong", "institution"];

function createAccount({ user_id, account_type, wallet_id, currency }) {
  const id = uuid();
  const account = {
    id,
    user_id,
    account_type,
    wallet_id,
    currency: currency || "USD",
    status: "active",
    created_at: new Date().toISOString(),
  };
  accounts.set(id, account);
  return account;
}

function getAccount(id) {
  return accounts.get(id) || null;
}

function updateAccount(id, patch) {
  const acc = accounts.get(id);
  if (!acc) return null;
  Object.assign(acc, patch, { updated_at: new Date().toISOString() });
  return acc;
}

module.exports = { accounts, VALID_TYPES, createAccount, getAccount, updateAccount };
