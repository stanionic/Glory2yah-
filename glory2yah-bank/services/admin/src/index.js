require("dotenv").config();
const express = require("express");
const cors = require("cors");
const morgan = require("morgan");
const adminRoutes = require("./routes/admin");
const reportRoutes = require("./routes/reports");

const app = express();
const PORT = process.env.PORT || 4700;

app.use(cors());
app.use(morgan("dev"));
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok", service: "admin-service" }));
app.use("/admin", adminRoutes);
app.use("/reports", reportRoutes);

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(err.status || 500).json({ error: err.message || "Erreur interne" });
});

app.listen(PORT, () => console.log(`🛠️  Admin & Reporting Service — écoute sur le port ${PORT}`));
