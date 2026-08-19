// src/routes.events.admin.js
// Routes ADMIN. IMPORTANT : montez ce routeur derrière le middleware
// d'authentification admin déjà utilisé ailleurs dans Glory2YahPub, ex :
//   app.use('/api/admin/events', requireAdminAuth, require('./routes.events.admin'));
// Ne dupliquez pas un système d'auth : réutilisez l'existant.

const express = require('express');
const { pool } = require('./db');
const { sanitizeText } = require('./validators');

const router = express.Router();

// ---- Modifier un événement ----
router.patch('/:slug', async (req, res) => {
  const fields = ['title','subtitle','summary','hero_image_url','start_at','end_at',
    'location_label','status','registration_enabled','livestream_enabled','livestream_url'];
  const updates = [];
  const values = [];
  let i = 1;
  for (const f of fields) {
    if (req.body[f] !== undefined) {
      updates.push(`${f} = $${i++}`);
      values.push(req.body[f]);
    }
  }
  if (!updates.length) return res.status(400).json({ error: 'Aucun champ à modifier' });
  values.push(req.params.slug);
  try {
    const result = await pool.query(
      `UPDATE events SET ${updates.join(', ')}, updated_at = now() WHERE slug = $${i} RETURNING id`,
      values
    );
    if (result.rowCount === 0) return res.status(404).json({ error: 'Événement introuvable' });
    res.json({ ok: true });
  } catch (err) {
    console.error('PATCH /admin/events/:slug error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// ---- Liste paginée des participants ----
router.get('/:slug/participants', async (req, res) => {
  const page = Math.max(parseInt(req.query.page) || 1, 1);
  const perPage = Math.min(parseInt(req.query.per_page) || 50, 200);
  const offset = (page - 1) * perPage;
  try {
    const eventRes = await pool.query('SELECT id FROM events WHERE slug=$1', [req.params.slug]);
    if (eventRes.rowCount === 0) return res.status(404).json({ error: 'Événement introuvable' });
    const result = await pool.query(
      `SELECT p.id, p.full_name, p.phone, p.email, p.city, r.name AS region, p.organization_name,
              p.role_label, p.participation_type, p.created_at
       FROM event_participants p
       LEFT JOIN event_regions r ON r.id = p.region_id
       WHERE p.event_id = $1
       ORDER BY p.created_at DESC
       LIMIT $2 OFFSET $3`,
      [eventRes.rows[0].id, perPage, offset]
    );
    res.json({ page, per_page: perPage, items: result.rows });
  } catch (err) {
    console.error('GET /admin/events/:slug/participants error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// ---- Liste + validation des organisations ----
router.get('/:slug/organizations', async (req, res) => {
  try {
    const eventRes = await pool.query('SELECT id FROM events WHERE slug=$1', [req.params.slug]);
    if (eventRes.rowCount === 0) return res.status(404).json({ error: 'Événement introuvable' });
    const result = await pool.query(
      `SELECT o.id, o.org_name, o.org_type, o.contact_name, o.phone, o.whatsapp, o.email,
              o.city, r.name AS region, o.approx_participants, o.message, o.status, o.created_at
       FROM event_organizations o
       LEFT JOIN event_regions r ON r.id = o.region_id
       WHERE o.event_id = $1
       ORDER BY o.created_at DESC`,
      [eventRes.rows[0].id]
    );
    res.json({ items: result.rows });
  } catch (err) {
    console.error('GET /admin/events/:slug/organizations error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

router.patch('/:slug/organizations/:id', async (req, res) => {
  if (!['pending', 'confirmed', 'rejected'].includes(req.body.status)) {
    return res.status(400).json({ error: 'status invalide' });
  }
  try {
    const result = await pool.query(
      'UPDATE event_organizations SET status=$1 WHERE id=$2 RETURNING id',
      [req.body.status, req.params.id]
    );
    if (result.rowCount === 0) return res.status(404).json({ error: 'Introuvable' });
    res.json({ ok: true });
  } catch (err) {
    console.error('PATCH organizations/:id error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// ---- FAQ ----
router.post('/:slug/faq', async (req, res) => {
  try {
    const eventRes = await pool.query('SELECT id FROM events WHERE slug=$1', [req.params.slug]);
    if (eventRes.rowCount === 0) return res.status(404).json({ error: 'Événement introuvable' });
    const result = await pool.query(
      'INSERT INTO event_faq (event_id, question, answer, display_order) VALUES ($1,$2,$3,$4) RETURNING id',
      [eventRes.rows[0].id, sanitizeText(req.body.question, 500), sanitizeText(req.body.answer, 3000), req.body.display_order || 0]
    );
    res.status(201).json({ id: result.rows[0].id });
  } catch (err) {
    console.error('POST faq error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

// ---- Actualités ----
router.post('/:slug/news', async (req, res) => {
  try {
    const eventRes = await pool.query('SELECT id FROM events WHERE slug=$1', [req.params.slug]);
    if (eventRes.rowCount === 0) return res.status(404).json({ error: 'Événement introuvable' });
    const result = await pool.query(
      'INSERT INTO event_news (event_id, title, body) VALUES ($1,$2,$3) RETURNING id',
      [eventRes.rows[0].id, sanitizeText(req.body.title, 255), sanitizeText(req.body.body, 5000)]
    );
    res.status(201).json({ id: result.rows[0].id });
  } catch (err) {
    console.error('POST news error', err);
    res.status(500).json({ error: 'Erreur serveur' });
  }
});

module.exports = router;
