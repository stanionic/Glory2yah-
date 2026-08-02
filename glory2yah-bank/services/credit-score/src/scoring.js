/**
 * Moteur de scoring — implémentation de référence à base de règles pondérées.
 * En production, remplacer par un modèle entraîné (XGBoost / réseau de neurones)
 * exposé via une API Python (FastAPI) ; cette version JS sert de contrat d'API
 * stable et de comportement par défaut testable.
 */

const alerts = [];

/**
 * Score de confiance sur 1000, basé sur activité, revenus, ancienneté,
 * historique, comportement, remboursements, stabilité.
 */
function computeCreditScore(profile) {
  const {
    account_age_months = 0,
    monthly_income = 0,
    avg_monthly_transactions = 0,
    on_time_repayments_ratio = 1, // 0..1
    balance_stability_index = 0.5, // 0..1 (1 = très stable)
  } = profile;

  const weights = {
    ancienneté: Math.min(account_age_months / 60, 1) * 150, // max 150 pts sur 5 ans
    revenus: Math.min(monthly_income / 5000, 1) * 200, // max 200 pts
    activité: Math.min(avg_monthly_transactions / 50, 1) * 150, // max 150 pts
    remboursements: on_time_repayments_ratio * 350, // max 350 pts — le plus déterminant
    stabilité: balance_stability_index * 150, // max 150 pts
  };

  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  return { score: Math.round(Math.min(1000, total)), breakdown: weights };
}

function riskLevelFromScore(score) {
  if (score >= 750) return "faible";
  if (score >= 500) return "modéré";
  if (score >= 300) return "élevé";
  return "très élevé";
}

/**
 * Prévision simplifiée de probabilité de défaut à partir du score et du type de prêt.
 */
function predictDefaultProbability(score, loanType) {
  const base = Math.max(0, (1000 - score) / 1000); // 0..1
  const typeMultiplier = { urgence: 1.3, personnel: 1.1, etudiant: 0.9, agricole: 1.0, commercial: 1.05 };
  const probability = Math.min(0.95, base * (typeMultiplier[loanType] || 1));
  return Number(probability.toFixed(3));
}

/**
 * Détection de fraude simplifiée à base de règles (montant atypique, fréquence, device).
 */
function evaluateFraud(transaction) {
  const reasons = [];
  if (transaction.amount > 10000) reasons.push("Montant inhabituellement élevé");
  if (transaction.transactions_last_hour > 10) reasons.push("Fréquence de transactions anormale");
  if (transaction.new_device) reasons.push("Nouvel appareil non reconnu");
  if (transaction.country_mismatch) reasons.push("Localisation incohérente avec l'historique");

  const riskScore = reasons.length / 4;
  const flagged = riskScore >= 0.5;

  if (flagged) {
    alerts.push({
      transaction_id: transaction.id || null,
      reasons,
      risk_score: riskScore,
      created_at: new Date().toISOString(),
    });
  }

  return { flagged, risk_score: riskScore, reasons };
}

module.exports = { computeCreditScore, riskLevelFromScore, predictDefaultProbability, evaluateFraud, alerts };
