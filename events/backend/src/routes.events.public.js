// src/routes.events.public.js
// Routes PUBLIQUES du module Événements. Montez ce routeur sur /api/events
// dans votre app existante : app.use('/api/events', require('./routes.events.public'));
//
// Si vous êtes sur Next.js (app router), transposez chaque handler dans
// /app/api/events/[slug]/route.js, /app/api/events/[slug]/participants/route.js, etc.
// La logique SQL ci-dessous reste identique.

const express = require('express');
const crypto = require('crypto');
const rateLimit = require('express-rate-limit'); // npm install express-rate-limit
const { pool } = require('./db');
const { validateParticipant, validateOrganization, sanitizeText } = require('./validators');

const router = express.Router();

// ---- Anti-abus : limite les soumissions de formulaires ----
const formLimiter = rateLimit({
  windowMs: 10 * 60 * 1000, // 10 min
  max: 5,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Trop de soumissions. Réessayez plus tard.' },
});

function hashIp(ip) {
  return crypto.createHash('sha256').update(String(ip)).digest('hex');
}

// ---------------------------------------------------------------
// GET /api/events/:slug — détail complet d'un événement publié
// ---------------------------------------------------------------
router.get('/:slug', async (req, res) => {
  const { slug } = req.params;
  try {
    const eventRes = await pool.query(
      `SELECT id, slug, title, subtitle, summary, hero_image_url, start_at, end_at,
              timezone, location_label, status, registration_enabled, livestream_enabled, livestream_url
       FROM events WHERE slug = $1 AND status = 'published'`,
      [slug]
    );
    if (eventRes.rowCount === 0) return res.status(404).json({ error: 'Événement introuvable' });
    const event = eventRes.rows[0];

    const [leaders, program, faq, media, news] = await Promise.all([
      pool.query('SELECT full_name, role_label, photo_url, bio FROM event_leaders WHERE event_id=$1 ORDER BY display_order', [event.id]),
      pool.query('SELECT time_label, title FROM event_program_items WHERE event_id=$1 ORDER BY display_order', [event.id]),
      pool.query('SELECT question, answer FROM event_faq WHERE event_id=$1 ORDER BY display_order', [event.id]),
      pool.query('SELECT media_type, url, caption FROM event_media WHERE event_id=$1 ORDER BY display_order', [event.id]),
      pool.query('SELECT title, body, published_at FROM event_news WHERE event_id=$1 ORDER BY published_at DESC LIMIT 20', [event.id]),
    ]);

    res.json({
      ...event,
      leaders: leaders.rows,
      program: program.rows,
      faq: faq.rows,
      media: media.rows,
      news: news.rows,
    });
  } catch (err) {
    console.error('GET /events/:slug error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// ---------------------------------------------------------------
// GET /api/events/:slug/stats — statistiques anonymisées
// ---------------------------------------------------------------
router.get('/:slug/stats', async (req, res) => {
  try {
    const result = await pool.query(
      'SELECT participants_count, eglises_count, organizations_types_count, regions_represented, shares_count FROM event_public_stats WHERE slug = $1',
      [req.params.slug]
    );
    if (result.rowCount === 0) return res.status(404).json({ error: 'Événement introuvable' });
    res.json(result.rows[0]);
  } catch (err) {
    console.error('GET /events/:slug/stats error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// ---------------------------------------------------------------
// POST /api/events/:slug/participants — inscription individuelle
// ---------------------------------------------------------------
router.post('/:slug/participants', formLimiter, async (req, res) => {
  const errors = validateParticipant(req.body);
  if (errors.length) return res.status(400).json({ errors });

  try {
    const eventRes = await pool.query(
      "SELECT id, registration_enabled FROM events WHERE slug=$1 AND status='published'",
      [req.params.slug]
    );
    if (eventRes.rowCount === 0) return res.status(404).json({ error: 'Événement introuvable' });
    if (!eventRes.rows[0].registration_enabled) return res.status(403).json({ error: 'Inscriptions fermées' });

    const eventId = eventRes.rows[0].id;
    let regionId = null;
    if (req.body.region) {
      const r = await pool.query('SELECT id FROM event_regions WHERE event_id=$1 AND name=$2', [eventId, req.body.region]);
      if (r.rowCount) regionId = r.rows[0].id;
    }

    const ipHash = hashIp(req.ip);

    const insert = await pool.query(
      `INSERT INTO event_participants
        (event_id, full_name, phone, email, city, region_id, organization_name, role_label, participation_type, consent_public_stats, ip_hash)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
       RETURNING id`,
      [
        eventId,
        sanitizeText(req.body.full_name, 255),
        sanitizeText(req.body.phone, 40),
        sanitizeText(req.body.email, 255),
        sanitizeText(req.body.city, 120),
        regionId,
        sanitizeText(req.body.organization_name, 255),
        req.body.role_label || 'membre',
        req.body.participation_type || 'individuelle',
        !!req.body.consent_public_stats,
        ipHash,
      ]
    );
    res.status(201).json({ id: insert.rows[0].id });
  } catch (err) {
    console.error('POST /events/:slug/participants error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// ---------------------------------------------------------------
// POST /api/events/:slug/organizations — inscription Église/organisation
// ---------------------------------------------------------------
router.post('/:slug/organizations', formLimiter, async (req, res) => {
  const errors = validateOrganization(req.body);
  if (errors.length) return res.status(400).json({ errors });

  try {
    const eventRes = await pool.query("SELECT id FROM events WHERE slug=$1 AND status='published'", [req.params.slug]);
    if (eventRes.rowCount === 0) return res.status(404).json({ error: 'Événement introuvable' });
    const eventId = eventRes.rows[0].id;

    let regionId = null;
    if (req.body.region) {
      const r = await pool.query('SELECT id FROM event_regions WHERE event_id=$1 AND name=$2', [eventId, req.body.region]);
      if (r.rowCount) regionId = r.rows[0].id;
    }

    const ipHash = hashIp(req.ip);

    const insert = await pool.query(
      `INSERT INTO event_organizations
        (event_id, org_name, org_type, contact_name, phone, whatsapp, email, city, region_id, approx_participants, message, consent_public_stats, ip_hash)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
       RETURNING id, status`,
      [
        eventId,
        sanitizeText(req.body.org_name, 255),
        req.body.org_type,
        sanitizeText(req.body.contact_name, 255),
        sanitizeText(req.body.phone, 40),
        sanitizeText(req.body.whatsapp, 40),
        sanitizeText(req.body.email, 255),
        sanitizeText(req.body.city, 120),
        regionId,
        req.body.approx_participants || null,
        sanitizeText(req.body.message, 2000),
        !!req.body.consent_public_stats,
        ipHash,
      ]
    );
    res.status(201).json(insert.rows[0]);
  } catch (err) {
    console.error('POST /events/:slug/organizations error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// ---------------------------------------------------------------
// POST /api/events/:slug/shares — compteur de partage (analytique)
// ---------------------------------------------------------------
router.post('/:slug/shares', async (req, res) => {
  const validChannels = ['whatsapp', 'facebook', 'messenger', 'x', 'telegram', 'link'];
  if (!validChannels.includes(req.body.channel)) return res.status(400).json({ error: 'channel invalide' });
  try {
    const eventRes = await pool.query('SELECT id FROM events WHERE slug=$1', [req.params.slug]);
    if (eventRes.rowCount === 0) return res.status(404).end();
    await pool.query('INSERT INTO event_shares (event_id, channel) VALUES ($1,$2)', [eventRes.rows[0].id, req.body.channel]);
    res.status(204).end();
  } catch (err) {
    console.error('POST /events/:slug/shares error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

module.exports = router;
