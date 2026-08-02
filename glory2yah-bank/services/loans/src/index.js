require("dotenv").config();
const express = require("express");
const cors = require("cors");
const morgan = require("morgan");
const loanRoutes = require("./routes/loans");
const db = require("./db");

const app = express();
const PORT = process.env.PORT || 4400;

app.use(cors());
app.use(morgan("dev"));
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok", service: "loans-service" }));
app.use("/loan", loanRoutes);

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(err.status || 500).json({ error: err.message || "Erreur interne" });
});

// Job périodique : marque les échéances impayées en retard
setInterval(() => {
  const now = new Date();
  for (const loan of db.loans.values()) {
    if (loan.status !== "active") continue;
    for (const installment of loan.schedule) {
      if (installment.status === "upcoming" && new Date(installment.due_date) < now) {
        installment.status = "late";
      }
    }
  }
}, 60 * 60 * 1000); // toutes les heures

app.listen(PORT, () => console.log(`🏦  Loans Service — écoute sur le port ${PORT}`));
