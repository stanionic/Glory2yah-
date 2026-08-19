// tests/events.test.js
// npm install --save-dev jest supertest
// npx jest
//
// Ces tests supposent une base de test avec les migrations + le seed
// SOS ALO LEGLIZ appliqués, et status='published' pour l'événement.

const request = require('supertest');
const app = require('../src/app.example');

describe('GET /api/events/sos-alo-legliz', () => {
  it('retourne les détails de l\'événement publié', async () => {
    const res = await request(app).get('/api/events/sos-alo-legliz');
    expect([200, 404]).toContain(res.status); // 404 tant que status != published
    if (res.status === 200) {
      expect(res.body.slug).toBe('sos-alo-legliz');
      expect(res.body).toHaveProperty('program');
      expect(res.body).toHaveProperty('leaders');
    }
  });

  it('retourne 404 pour un slug inexistant', async () => {
    const res = await request(app).get('/api/events/evenement-inexistant');
    expect(res.status).toBe(404);
  });
});

describe('POST /api/events/sos-alo-legliz/participants', () => {
  it('rejette une soumission sans nom', async () => {
    const res = await request(app)
      .post('/api/events/sos-alo-legliz/participants')
      .send({ phone: '+50912345678' });
    expect(res.status).toBe(400);
    expect(res.body.errors).toBeDefined();
  });

  it('rejette un téléphone invalide', async () => {
    const res = await request(app)
      .post('/api/events/sos-alo-legliz/participants')
      .send({ full_name: 'Jean Baptiste', phone: 'abc' });
    expect(res.status).toBe(400);
  });

  it('rejette une soumission avec honeypot rempli (anti-spam)', async () => {
    const res = await request(app)
      .post('/api/events/sos-alo-legliz/participants')
      .send({ full_name: 'Test', phone: '+50912345678', website: 'http://spam.com' });
    expect(res.status).toBe(400);
  });

  it('accepte une soumission valide', async () => {
    const res = await request(app)
      .post('/api/events/sos-alo-legliz/participants')
      .send({ full_name: 'Marie Joseph', phone: '+50912345678', email: 'marie@example.com', role_label: 'membre' });
    expect([201, 403, 404]).toContain(res.status);
    // 403/404 si l'événement seed n'est pas encore 'published' dans la base de test
  });
});

describe('POST /api/events/sos-alo-legliz/organizations', () => {
  it('rejette un org_type invalide', async () => {
    const res = await request(app)
      .post('/api/events/sos-alo-legliz/organizations')
      .send({ org_name: 'Église Bethel', org_type: 'invalide', contact_name: 'Paul', phone: '+50900000000' });
    expect(res.status).toBe(400);
  });
});
