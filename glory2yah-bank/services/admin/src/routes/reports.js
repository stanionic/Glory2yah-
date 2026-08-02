const express = require("express");
const router = express.Router();

/**
 * Ces endpoints sont des squelettes de référence : en production, ils
 * agrègent les données depuis le data warehouse (ClickHouse/BigQuery)
 * alimenté par les événements Kafka de GKach et des microservices.
 */

router.get("/financial", (_req, res) => {
  res.json({
    period: "monthly",
    interest_earned: 0,
    interest_paid: 0,
    commissions: 0,
    net_profit: 0,
    note: "Brancher sur le data warehouse pour des valeurs réelles.",
  });
});

router.get("/loans", (_req, res) => {
  res.json({ total_outstanding: 0, default_rate: 0, late_installments: 0 });
});

router.get("/investors", (_req, res) => {
  res.json({ total_invested: 0, average_return: 0, active_investors: 0 });
});

module.exports = router;
