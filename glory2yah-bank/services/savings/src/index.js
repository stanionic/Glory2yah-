require("dotenv").config();
const express = require("express");
const cors = require("cors");
const morgan = require("morgan");
const cron = require("node-cron");

const savingsRoutes = require("./routes/savings");
const db = require("./db");

const app = express();
const PORT = process.env.PORT || 4200;

app.use(cors());
app.use(morgan("dev"));
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok", service: "savings-service" }));
app.use("/savings", savingsRoutes);

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(err.status || 500).json({ error: err.message || "Erreur interne" });
});

/**
 * Job planifié : calcul quotidien des intérêts pour tous les comptes actifs.
 * En production : orchestré par un scheduler dédié (ex. Kubernetes CronJob).
 */
cron.schedule("0 0 * * *", () => {
  for (const account of db.savingsAccounts.values()) {
    if (account.status !== "active") continue;
    const dailyInterest = db.computeInterest(account, 1);
    account.accrued_interest += dailyInterest;
  }
  console.log(`💰 Intérêts journaliers calculés pour ${db.savingsAccounts.size} comptes épargne`);
});

app.listen(PORT, () => console.log(`💵  Savings Service — écoute sur le port ${PORT}`));
