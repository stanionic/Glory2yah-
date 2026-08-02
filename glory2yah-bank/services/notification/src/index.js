require("dotenv").config();
const express = require("express");
const cors = require("cors");
const morgan = require("morgan");
const { v4: uuid } = require("uuid");

const app = express();
const PORT = process.env.PORT || 4800;

app.use(cors());
app.use(morgan("dev"));
app.use(express.json());

const notifications = new Map();
const VALID_CHANNELS = ["email", "sms", "push", "whatsapp", "in_app"];

/**
 * Intégrer ici les vrais fournisseurs en production :
 * - Email  : SendGrid / SES
 * - SMS    : Twilio / Africa's Talking
 * - Push   : Firebase Cloud Messaging / APNs
 * - WhatsApp : WhatsApp Business API
 */
function dispatch(channel, to, message) {
  console.log(`📣 [${channel.toUpperCase()}] → ${to}: ${message}`);
  return { delivered: true, provider_ref: uuid() };
}

app.get("/health", (_req, res) => res.json({ status: "ok", service: "notification-service" }));

/**
 * POST /notifications
 * body: { user_id, channel, to, message }
 */
app.post("/notifications", (req, res) => {
  const { user_id, channel, to, message } = req.body;
  if (!VALID_CHANNELS.includes(channel)) {
    return res.status(400).json({ error: `Canal invalide. Options: ${VALID_CHANNELS.join(", ")}` });
  }

  const result = dispatch(channel, to, message);
  const record = {
    id: uuid(),
    user_id,
    channel,
    message,
    status: result.delivered ? "delivered" : "failed",
    provider_ref: result.provider_ref,
    sent_at: new Date().toISOString(),
  };
  notifications.set(record.id, record);
  res.status(201).json(record);
});

app.get("/notifications", (req, res) => {
  const { user_id } = req.query;
  const list = Array.from(notifications.values()).filter((n) => !user_id || n.user_id === user_id);
  res.json(list);
});

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: "Erreur interne Notification Service" });
});

app.listen(PORT, () => console.log(`🔔  Notification Service — écoute sur le port ${PORT}`));
