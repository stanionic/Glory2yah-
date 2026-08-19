-- ============================================================
-- Glory2YahPub — Module ÉVÉNEMENTS
-- Schéma générique : chaque événement est une entité indépendante,
-- identifiée par un slug. Ajouter un nouvel événement = une ligne
-- dans `events`, aucune modification de code nécessaire.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- pour gen_random_uuid()

-- ---------- ÉVÉNEMENT ----------
CREATE TABLE IF NOT EXISTS events (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug                  VARCHAR(160) UNIQUE NOT NULL,       -- ex: 'sos-alo-legliz'
  title                 VARCHAR(255) NOT NULL,
  subtitle              VARCHAR(255),
  summary               TEXT,                                -- résumé officiel affiché sur la landing page
  hero_image_url        TEXT,
  start_at              TIMESTAMPTZ NOT NULL,
  end_at                TIMESTAMPTZ NOT NULL,
  timezone              VARCHAR(64) NOT NULL DEFAULT 'America/Port-au-Prince',
  location_label        VARCHAR(255),                        -- ex: "En ligne + Églises locales"
  status                VARCHAR(20) NOT NULL DEFAULT 'draft'  -- draft | published | archived
                          CHECK (status IN ('draft','published','archived')),
  registration_enabled  BOOLEAN NOT NULL DEFAULT TRUE,
  livestream_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
  livestream_url        TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- INITIATEURS / LEADERS ----------
CREATE TABLE IF NOT EXISTS event_leaders (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  full_name     VARCHAR(255) NOT NULL,
  role_label    VARCHAR(120) NOT NULL,     -- "Initiateur", "Coordination générale"...
  photo_url     TEXT,
  bio           TEXT,
  display_order INT NOT NULL DEFAULT 0
);

-- ---------- PROGRAMME (timeline modifiable) ----------
CREATE TABLE IF NOT EXISTS event_program_items (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  time_label    VARCHAR(20) NOT NULL,      -- "06:00"
  title         VARCHAR(255) NOT NULL,     -- "Ouverture"
  display_order INT NOT NULL DEFAULT 0
);

-- ---------- FAQ ----------
CREATE TABLE IF NOT EXISTS event_faq (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  question      TEXT NOT NULL,
  answer        TEXT NOT NULL,
  display_order INT NOT NULL DEFAULT 0
);

-- ---------- ACTUALITÉS ----------
CREATE TABLE IF NOT EXISTS event_news (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  title         VARCHAR(255) NOT NULL,
  body          TEXT NOT NULL,
  published_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    UUID -- FK optionnelle vers votre table admins/users existante
);

-- ---------- MÉDIA (photos / vidéos / affiches / témoignages) ----------
CREATE TABLE IF NOT EXISTS event_media (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  media_type    VARCHAR(20) NOT NULL CHECK (media_type IN ('photo','video','poster','testimony')),
  url           TEXT NOT NULL,
  caption       VARCHAR(255),
  display_order INT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- DÉPARTEMENTS / RÉGIONS (généralisable hors Haïti) ----------
CREATE TABLE IF NOT EXISTS event_regions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id      UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name          VARCHAR(120) NOT NULL,      -- "Ouest", "Artibonite", "Diaspora"...
  UNIQUE(event_id, name)
);

-- ---------- COORDINATEURS DÉPARTEMENTAUX ----------
CREATE TABLE IF NOT EXISTS event_coordinators (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id          UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  region_id         UUID REFERENCES event_regions(id) ON DELETE SET NULL,
  full_name         VARCHAR(255) NOT NULL,
  photo_url         TEXT,
  phone_professional VARCHAR(40),
  whatsapp          VARCHAR(40),
  email             VARCHAR(255),
  status            VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','pending','inactive')),
  -- Ces coordonnées ne sont PAS publiques par défaut : contrôlé par is_public_contact
  is_public_contact BOOLEAN NOT NULL DEFAULT FALSE
);

-- ---------- PARTICIPANTS INDIVIDUELS ----------
CREATE TABLE IF NOT EXISTS event_participants (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id            UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  full_name           VARCHAR(255) NOT NULL,
  phone               VARCHAR(40) NOT NULL,
  email               VARCHAR(255),
  city                VARCHAR(120),
  region_id           UUID REFERENCES event_regions(id) ON DELETE SET NULL,
  organization_name   VARCHAR(255),
  role_label          VARCHAR(30) NOT NULL DEFAULT 'membre'
                        CHECK (role_label IN ('pasteur','responsable','membre','jeune','groupe_de_priere','organisation','autre')),
  participation_type  VARCHAR(30) NOT NULL DEFAULT 'individuelle'
                        CHECK (participation_type IN ('individuelle','eglise','mission','organisation','ligue_de_pasteurs','groupe_de_priere')),
  consent_public_stats BOOLEAN NOT NULL DEFAULT FALSE, -- consentement pour apparaître dans des stats/carte publiques
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip_hash             VARCHAR(64) -- hash de l'IP (anti-spam), jamais l'IP en clair
);

CREATE INDEX IF NOT EXISTS idx_participants_event ON event_participants(event_id);
CREATE INDEX IF NOT EXISTS idx_participants_region ON event_participants(region_id);

-- ---------- INSCRIPTIONS D'ÉGLISES / ORGANISATIONS ----------
CREATE TABLE IF NOT EXISTS event_organizations (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id              UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  org_name              VARCHAR(255) NOT NULL,
  org_type              VARCHAR(30) NOT NULL
                          CHECK (org_type IN ('eglise','mission','organisation','ligue_de_pasteurs','groupe_de_priere')),
  contact_name          VARCHAR(255) NOT NULL,
  phone                 VARCHAR(40) NOT NULL,
  whatsapp              VARCHAR(40),
  email                 VARCHAR(255),
  city                  VARCHAR(120),
  region_id             UUID REFERENCES event_regions(id) ON DELETE SET NULL,
  approx_participants   INT,
  message               TEXT,
  status                VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','rejected')),
  consent_public_stats  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip_hash               VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_orgs_event ON event_organizations(event_id);
CREATE INDEX IF NOT EXISTS idx_orgs_region ON event_organizations(region_id);

-- ---------- PARTAGES (compteur, optionnel) ----------
CREATE TABLE IF NOT EXISTS event_shares (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id    UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  channel     VARCHAR(20) NOT NULL, -- whatsapp | facebook | messenger | x | telegram | link
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- VUE STATISTIQUES ANONYMISÉES (publiques) ----------
CREATE OR REPLACE VIEW event_public_stats AS
SELECT
  e.id AS event_id,
  e.slug,
  (SELECT COUNT(*) FROM event_participants p WHERE p.event_id = e.id) AS participants_count,
  (SELECT COUNT(*) FROM event_organizations o WHERE o.event_id = e.id AND o.org_type='eglise') AS eglises_count,
  (SELECT COUNT(DISTINCT o.org_type) FROM event_organizations o WHERE o.event_id = e.id) AS organizations_types_count,
  (SELECT COUNT(DISTINCT region_id) FROM event_participants p WHERE p.event_id = e.id AND region_id IS NOT NULL) AS regions_represented,
  (SELECT COUNT(*) FROM event_shares s WHERE s.event_id = e.id) AS shares_count
FROM events e;

-- ---------- SEED DE L'ÉVÉNEMENT SOS ALO LEGLIZ ----------
INSERT INTO events (slug, title, subtitle, summary, start_at, end_at, location_label, status)
VALUES (
  'sos-alo-legliz',
  'SOS ALO LEGLIZ',
  'Demi Jounen Jèn Pou Peyi a',
  'SOS ALO LEGLIZ — Demi Jounen Jèn Pou Peyi a est une mobilisation chrétienne consacrée au jeûne, à la prière et à l''intercession en faveur d''Haïti. Lancée par l''Apôtre Stanley Désinat et le Pasteur Nixon Dieudonnée, l''initiative est coordonnée par ALO LEGLIZ, "Yon Mouvman Inite & Sali pou Ayiti".',
  '2026-08-30T06:00:00-05:00',
  '2026-08-30T12:00:00-05:00',
  'Haïti + Diaspora (en ligne et en Église)',
  'draft'
)
ON CONFLICT (slug) DO NOTHING;

-- Leaders
INSERT INTO event_leaders (event_id, full_name, role_label, display_order)
SELECT id, 'Apôtre Stanley Désinat', 'Initiateur', 1 FROM events WHERE slug='sos-alo-legliz'
UNION ALL
SELECT id, 'Pasteur Nixon Dieudonnée', 'Initiateur', 2 FROM events WHERE slug='sos-alo-legliz'
UNION ALL
SELECT id, 'ALO LEGLIZ', 'Coordination générale', 3 FROM events WHERE slug='sos-alo-legliz';

-- Programme
INSERT INTO event_program_items (event_id, time_label, title, display_order)
SELECT id, t.time_label, t.title, t.ord FROM events e,
(VALUES
  ('06:00','Ouverture',1),
  ('06:15','Louange / Adoration',2),
  ('06:45','Priere de consecration personnelle',3),
  ('07:30','Temps de jeûne et méditation',4),
  ('08:30','Prière pour les familles',5),
  ('09:30','Prière pour l''Église',6),
  ('10:30','Intercession nationale',7),
  ('11:30','Action de grâce',8),
  ('12:00','Clôture',9)
) AS t(time_label, title, ord)
JOIN events e ON e.slug='sos-alo-legliz';

-- Départements d'Haïti + Diaspora
INSERT INTO event_regions (event_id, name)
SELECT id, r.name FROM events e,
(VALUES ('Ouest'),('Artibonite'),('Nord'),('Nord-Est'),('Nord-Ouest'),
        ('Centre'),('Sud'),('Sud-Est'),('Grand''Anse'),('Nippes'),('Diaspora')) AS r(name)
JOIN events e ON e.slug='sos-alo-legliz'
ON CONFLICT DO NOTHING;
