const express = require("express");
const router = express.Router();
const db = require("../db");
const gkach = require("../gkachClient");

/**
 * POST /crowdlending/opportunities
 * Publication d'une opportunité par l'admin, généralement après validation
 * d'un prêt côté Loan Service qui n'a pas encore été décaissé.
 * body: { loan_id, borrower_wallet_id, amount, expected_return, risk_level, duration_months }
 */
router.post("/opportunities", (req, res) => {
  const opportunity = db.publishOpportunity(req.body);
  res.status(201).json(opportunity);
});

router.get("/opportunities", (_req, res) => {
  res.json(Array.from(db.opportunities.values()).filter((o) => o.status === "open"));
});

router.get("/:loanId/progress", (req, res) => {
  const opp = db.getOpportunity(req.params.loanId);
  if (!opp) return res.status(404).json({ error: "Opportunité introuvable" });
  const contributions = db.listContributionsByOpportunity(opp.id);
  res.json({
    ...opp,
    progress_percent: Number(((opp.amount_funded / opp.amount_requested) * 100).toFixed(2)),
    contributors_count: contributions.length,
  });
});

/**
 * POST /crowdlending/:loanId/fund
 * body: { investor_id, investor_wallet_id, amount }
 * Met les fonds en séquestre via GKach ; déclenche le décaissement
 * au bénéficiaire lorsque le montant total est atteint.
 */
router.post("/:loanId/fund", async (req, res, next) => {
  try {
    const opp = db.getOpportunity(req.params.loanId);
    if (!opp) return res.status(404).json({ error: "Opportunité introuvable" });
    if (opp.status !== "open") return res.status(409).json({ error: "Cette opportunité n'accepte plus de financement" });

    const { investor_id, investor_wallet_id, amount } = req.body;
    const remaining = opp.amount_requested - opp.amount_funded;
    if (amount > remaining) return res.status(422).json({ error: `Montant maximum finançable restant: ${remaining}` });

    await gkach.escrowHold(investor_wallet_id, amount, opp.id);
    db.addContribution({ opportunity_id: opp.id, investor_id, investor_wallet_id, amount });
    opp.amount_funded += amount;

    if (opp.amount_funded >= opp.amount_requested) {
      opp.status = "funded";
      // Décaissement vers l'emprunteur — l'escrow GKach libère les fonds réunis
      await gkach.disburse(opp.borrower_wallet_id, opp.amount_funded, opp.id);
      opp.status = "disbursed";
    }

    res.status(201).json(opp);
  } catch (err) {
    next(err);
  }
});

/**
 * GET /crowdlending/portfolio?investor_id=...
 */
router.get("/portfolio", (req, res) => {
  const { investor_id } = req.query;
  const contributions = db.listContributionsByInvestor(investor_id);
  const portfolio = contributions.map((c) => ({
    ...c,
    opportunity: db.getOpportunity(c.opportunity_id),
  }));
  res.json(portfolio);
});

module.exports = router;
