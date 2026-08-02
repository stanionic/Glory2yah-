const jwt = require("jsonwebtoken");

const JWT_SECRET = process.env.JWT_SECRET || "dev-secret-change-me";

// Routes publiques ne nécessitant pas de token (démo)
const PUBLIC_PATHS = ["/health", "/auth/login", "/investment/plans", "/crowdlending/opportunities"];

function isPublic(path) {
  return PUBLIC_PATHS.some((p) => path === p || path.startsWith(p));
}

function authMiddleware(req, res, next) {
  if (isPublic(req.path)) return next();

  const header = req.headers.authorization;
  if (!header || !header.startsWith("Bearer ")) {
    return res.status(401).json({ error: "Token JWT manquant" });
  }

  const token = header.slice(7);
  try {
    const payload = jwt.verify(token, JWT_SECRET);
    req.user = payload; // { sub, role, ... }
    next();
  } catch {
    return res.status(401).json({ error: "Token JWT invalide ou expiré" });
  }
}

/**
 * RBAC minimal : vérifie que l'utilisateur possède l'un des rôles requis.
 * Utilisation : requireRole("admin")
 */
function requireRole(...roles) {
  return (req, res, next) => {
    if (!req.user || !roles.includes(req.user.role)) {
      return res.status(403).json({ error: "Permission refusée" });
    }
    next();
  };
}

function issueDemoToken(sub, role = "client") {
  return jwt.sign({ sub, role }, JWT_SECRET, { expiresIn: "1h" });
}

module.exports = { authMiddleware, requireRole, issueDemoToken, JWT_SECRET };
