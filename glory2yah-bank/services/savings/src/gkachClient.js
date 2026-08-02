/**
 * Client HTTP partagé vers GKach (Core Banking & Payment Engine).
 * Copié dans chaque microservice — RÈGLE D'OR : aucun microservice
 * Glory2Yah Bank ne doit stocker un solde ou écrire un mouvement
 * d'argent lui-même. Tout passe par ce client.
 */

const GKACH_URL = process.env.GKACH_URL || "http://localhost:4000";

async function call(path, method = "GET", body) {
  const res = await fetch(`${GKACH_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `Erreur GKach (${res.status})`);
    err.status = res.status;
    err.details = data;
    throw err;
  }
  return data;
}

module.exports = {
  createWallet: (owner_ref, currency = "USD", type = "standard") =>
    call("/wallet/create", "POST", { owner_ref, currency, type }),
  getBalance: (wallet_id) => call(`/wallet/balance?wallet_id=${wallet_id}`),
  getTransactions: (wallet_id) => call(`/wallet/transactions?wallet_id=${wallet_id}`),
  deposit: (wallet_id, amount, method) => call("/wallet/deposit", "POST", { wallet_id, amount, method }),
  withdraw: (wallet_id, amount, method) => call("/wallet/withdraw", "POST", { wallet_id, amount, method }),
  transfer: (from_wallet_id, to_wallet_id, amount) =>
    call("/wallet/transfer", "POST", { from_wallet_id, to_wallet_id, amount }),
  generateQr: (wallet_id, amount) => call("/wallet/qr/generate", "POST", { wallet_id, amount }),
  payQr: (qr_code, payer_wallet_id, amount) =>
    call("/wallet/qr/pay", "POST", { qr_code, payer_wallet_id, amount }),
  disburse: (to_wallet_id, amount, ref) => call("/payment/disburse", "POST", { to_wallet_id, amount, ref }),
  repay: (from_wallet_id, amount, ref) => call("/payment/repay", "POST", { from_wallet_id, amount, ref }),
  escrowHold: (wallet_id, amount, ref) => call("/payment/escrow-hold", "POST", { wallet_id, amount, ref }),
};
