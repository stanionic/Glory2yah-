require("dotenv").config();
const express = require("express");
const cors = require("cors");
const morgan = require("morgan");
const accountsRoutes = require("./routes/accounts");

const app = express();
const PORT = process.env.PORT || 4100;

app.use(cors());
app.use(morgan("dev"));
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok", service: "accounts-service" }));
app.use("/accounts", accountsRoutes);

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(err.status || 500).json({ error: err.message || "Erreur interne" });
});

app.listen(PORT, () => console.log(`🏛️  Accounts Service — écoute sur le port ${PORT}`));
