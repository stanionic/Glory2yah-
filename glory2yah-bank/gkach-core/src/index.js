require("dotenv").config();
const express = require("express");
const cors = require("cors");
const morgan = require("morgan");

const walletRoutes = require("./routes/wallet");
const paymentRoutes = require("./routes/payment");
const { getEventLog } = require("./events");

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors());
app.use(morgan("dev"));
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok", service: "gkach-core" }));

app.use("/wallet", walletRoutes);
app.use("/payment", paymentRoutes);

// Endpoint de debug pour visualiser le flux d'événements publiés (démo uniquement)
app.get("/events", (_req, res) => res.json(getEventLog()));

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: "Erreur interne GKach" });
});

app.listen(PORT, () => {
  console.log(`🏦  GKach Core Banking & Payment Engine — écoute sur le port ${PORT}`);
});
