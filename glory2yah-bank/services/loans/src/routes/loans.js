const express = require("express");
const router = express.Router();
const db = require("../db");
const gkach = require("../gkachClient");

const AI_SERVICE_URL = process.env.AI_SERVICE_URL || "http://localhost:4600";

/**
 * POST /loan/apply
 * body: { user_id, wallet_id, type, amount, term_months }
 * Pipeline: Demande -> Analyse IA -> (attente validation admin)
 */
router.post("/apply", async (req, res, next) => {
  try {
    const { user_id, wallet_id, type, amount, term_months } = req.body;
    const config = db.LOAN_TYPES[type];
    if (!config) return res.status(400).json({ error: `Type de prêt inconnu. Options: ${Object.keys(db.LOAN_TYPES).join(", ")}` });
    if (amount > config.max_amount) return res.status(422).json({ error: `Montant max pour ${type}: ${config.max_amount}` });
    if (term_months > config.max_term_months) {
      return res.status(422).json({ error: `Durée max pour ${type}: ${config.max_term_months} mois` });
    }

    const loan = db.createLoan({ user_id, wallet_id, type, amount, term_months });

    // Étape 2 : Analyse IA (score de crédit + évaluation de risque)
    try {
      const aiRes = await fetch(`${AI_SERVICE_URL}/risk/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id, amount, type, term_months }),
      });
      const aiData = await aiRes.json();
      loan.ai_score = aiData.credit_score;
      loan.ai_risk = aiData.risk_level;
    } catch {
      loan.ai_score = null;
      loan.ai_risk = "indisponible"; // le service IA peut être down sans bloquer la demande
    }

    loan.status = "under_review";
    res.status(201).json(loan);
  } catch (err) {
    next(err);
  }
});

router.get("/:id", (req, res) => {
  const loan = db.getLoan(req.params.id);
  if (!loan) return res.status(404).json({ error: "Prêt introuvable" });
  res.json(loan);
});

router.get("/:id/status", (req, res) => {
  const loan = db.getLoan(req.params.id);
  if (!loan) return res.status(404).json({ error: "Prêt introuvable" });
  res.json({ id: loan.id, status: loan.status });
});

router.get("/:id/schedule", (req, res) => {
  const loan = db.getLoan(req.params.id);
  if (!loan) return res.status(404).json({ error: "Prêt introuvable" });
  res.json(loan.schedule);
});

/**
 * POST /loan/:id/approve
 * Étape 3+4 : Validation Admin -> Décaissement via GKach -> Génération du calendrier
 */
router.post("/:id/approve", async (req, res, next) => {
  try {
    const loan = db.getLoan(req.params.id);
    if (!loan) return res.status(404).json({ error: "Prêt introuvable" });
    if (loan.status !== "under_review") return res.status(409).json({ error: "Le prêt n'est pas en attente de validation" });

    db.generateSchedule(loan);
    await gkach.disburse(loan.wallet_id, loan.amount, loan.id);

    loan.status = "active";
    loan.approved_at = new Date().toISOString();
    loan.approved_by = req.body.admin_id || "admin";

    res.json(loan);
  } catch (err) {
    next(err);
  }
});

router.post("/:id/reject", (req, res) => {
  const loan = db.getLoan(req.params.id);
  if (!loan) return res.status(404).json({ error: "Prêt introuvable" });
  if (loan.status !== "under_review") return res.status(409).json({ error: "Le prêt n'est pas en attente de validation" });

  loan.status = "rejected";
  loan.rejected_reason = req.body.reason || "Non spécifié";
  res.json(loan);
});

/**
 * POST /loan/:id/repay
 * Paiement d'une échéance (automatique ou manuel) -> prélèvement via GKach
 */
router.post("/:id/repay", async (req, res, next) => {
  try {
    const loan = db.getLoan(req.params.id);
    if (!loan) return res.status(404).json({ error: "Prêt introuvable" });
    if (loan.status !== "active") return res.status(409).json({ error: "Le prêt n'est pas actif" });

    const { installment_number } = req.body;
    const installment = loan.schedule.find((i) => i.installment_number === installment_number);
    if (!installment) return res.status(404).json({ error: "Échéance introuvable" });
    if (installment.status === "paid") return res.status(409).json({ error: "Échéance déjà payée" });

    if (new Date() > new Date(installment.due_date)) installment.status = "late";
    const penalty = db.computePenalty(installment);
    const totalDue = installment.amount_due + penalty;

    await gkach.repay(loan.wallet_id, totalDue, `${loan.id}#${installment_number}`);

    installment.amount_paid = totalDue;
    installment.penalty = penalty;
    installment.status = "paid";
    installment.paid_at = new Date().toISOString();

    const allPaid = loan.schedule.every((i) => i.status === "paid");
    if (allPaid) loan.status = "closed";

    res.json({ installment, loan_status: loan.status });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
