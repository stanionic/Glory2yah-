// src/db.js
// Pool de connexion PostgreSQL réutilisable.
// Remplacez par votre pool existant si Glory2YahPub en a déjà un (ne pas dupliquer).
const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_SSL === 'true' ? { rejectUnauthorized: false } : false,
  max: 10,
});

module.exports = { pool };
