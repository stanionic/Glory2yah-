require("dotenv").config();
const express = require("express");
const cors = require("cors");
const morgan = require("morgan");
const rateLimit = require("express-rate-limit");
const proxy = require("express-http-proxy");

const { authMiddleware, requireRole, issueDemoToken } = require("./auth");

const app = express();
const PORT = process.env.PORT || 8080;

const SERVICES = {
  gkach: process.env.GKACH_URL || "http://localhost:4000",
  accounts: process.env.ACCOUNTS_URL || "http://localhost:4100",
  savings: process.env.SAVINGS_URL || "http://localhost:4200",
  investments: process.env.INVESTMENTS_URL || "http://localhost:4300",
  loans: process.env.LOANS_URL || "http://localhost:4400",
  crowdlending: process.env.CROWDLENDING_URL || "http://localhost:4500",
  ai: process.env.AI_URL || "http://localhost:4600",
  admin: process.env.ADMIN_URL || "http://localhost:4700",
  notification: process.env.NOTIFICATION_URL || "http://localhost:4800",
};

app.use(cors());
app.use(morgan("dev"));

app.use(
  rateLimit({
    windowMs: 60 * 1000,
    max: 120, // 120 requêtes / minute / IP — ajuster en production
    standardHeaders: true,
    legacyHeaders: false,
  })
);

app.get("/health", (_req, res) => res.json({ status: "ok", service: "api-gateway" }));

// Endpoint de démo pour obtenir un token JWT (à remplacer par un vrai service Auth/KYC)
app.use(express.json());
app.post("/auth/login", (req, res) => {
  const { user_id, role } = req.body;
  if (!user_id) return res.status(400).json({ error: "user_id est requis" });
  res.json({ token: issueDemoToken(user_id, role || "client") });
});

app.use(authMiddleware);

// Routage vers les microservices
app.use("/wallet", proxy(SERVICES.gkach));
app.use("/payment", proxy(SERVICES.gkach));
app.use("/accounts", proxy(SERVICES.accounts));
app.use("/savings", proxy(SERVICES.savings));
app.use("/investment", proxy(SERVICES.investments));
app.use("/loan", proxy(SERVICES.loans));
app.use("/crowdlending", proxy(SERVICES.crowdlending));
app.use("/credit-score", proxy(SERVICES.ai));
app.use("/risk", proxy(SERVICES.ai));
app.use("/fraud", proxy(SERVICES.ai));
app.use("/notifications", proxy(SERVICES.notification));

// Le tableau de bord et la gestion des taux/plans exigent le rôle admin
app.use("/admin", requireRole("admin"), proxy(SERVICES.admin));
app.use("/reports", requireRole("admin"), proxy(SERVICES.admin));

app.listen(PORT, () => console.log(`🚪  API Gateway — écoute sur le port ${PORT}`));
