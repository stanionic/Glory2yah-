require("dotenv").config();
const express = require("express");
const cors = require("cors");
const morgan = require("morgan");
const investmentRoutes = require("./routes/investments");

const app = express();
const PORT = process.env.PORT || 4300;

app.use(cors());
app.use(morgan("dev"));
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok", service: "investments-service" }));
app.use("/investment", investmentRoutes);

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(err.status || 500).json({ error: err.message || "Erreur interne" });
});

app.listen(PORT, () => console.log(`📈  Investments Service — écoute sur le port ${PORT}`));
