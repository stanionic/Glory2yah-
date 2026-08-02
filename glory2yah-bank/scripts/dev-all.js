/**
 * Lance tous les services en local (sans Docker) avec `concurrently`.
 * Usage : npm run dev  (depuis la racine du projet, après npm install)
 */
const concurrently = require("concurrently");

concurrently(
  [
    { command: "npm start", cwd: "gkach-core", name: "gkach", prefixColor: "yellow" },
    { command: "npm start", cwd: "services/accounts", name: "accounts", prefixColor: "blue" },
    { command: "npm start", cwd: "services/savings", name: "savings", prefixColor: "green" },
    { command: "npm start", cwd: "services/investments", name: "investments", prefixColor: "magenta" },
    { command: "npm start", cwd: "services/loans", name: "loans", prefixColor: "cyan" },
    { command: "npm start", cwd: "services/crowdlending", name: "crowdlending", prefixColor: "red" },
    { command: "npm start", cwd: "services/credit-score", name: "ai-engine", prefixColor: "white" },
    { command: "npm start", cwd: "services/admin", name: "admin", prefixColor: "gray" },
    { command: "npm start", cwd: "services/notification", name: "notification", prefixColor: "blackBright" },
    { command: "npm start", cwd: "api-gateway", name: "gateway", prefixColor: "bgBlue.white" },
  ],
  { killOthers: ["failure"], restartTries: 1 }
).result.catch(() => process.exit(1));
