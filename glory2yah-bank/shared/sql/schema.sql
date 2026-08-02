-- ============================================================================
-- Glory2Yah Bank — Schéma PostgreSQL de référence (production)
-- NOTE: GKach (Wallets, Ledger) est gérée dans une base séparée et n'est
-- PAS dupliquée ici. Glory2Yah Bank ne stocke que des références de wallet.
-- Pattern recommandé : "Database per Service" — ce fichier peut être
-- éclaté en un schema.sql par microservice.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Identité & accès
-- ---------------------------------------------------------------------------
CREATE TABLE roles (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(50) UNIQUE NOT NULL,   -- admin, client, investisseur, marchand...
    description TEXT
);

CREATE TABLE permissions (
    id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role_id  UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    resource VARCHAR(100) NOT NULL,             -- ex: 'loans', 'admin.rates'
    action   VARCHAR(50)  NOT NULL              -- ex: 'read', 'write', 'approve'
);

CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name   VARCHAR(255) NOT NULL,
    email       VARCHAR(255) UNIQUE NOT NULL,
    phone       VARCHAR(30) UNIQUE,
    kyc_status  VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending, verified, rejected
    role_id     UUID REFERENCES roles(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL,
    device_info JSONB,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE api_keys (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash   VARCHAR(255) NOT NULL,
    scopes     TEXT[] NOT NULL DEFAULT '{}',
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Devises
-- ---------------------------------------------------------------------------
CREATE TABLE currencies (
    id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code   CHAR(3) UNIQUE NOT NULL,   -- USD, EUR, CDF...
    name   VARCHAR(50) NOT NULL,
    symbol VARCHAR(5) NOT NULL
);

CREATE TABLE exchange_rates (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    base_currency   CHAR(3) NOT NULL REFERENCES currencies(code),
    target_currency CHAR(3) NOT NULL REFERENCES currencies(code),
    rate            NUMERIC(18,8) NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (base_currency, target_currency)
);

-- ---------------------------------------------------------------------------
-- Wallets (référence vers GKach — pas de solde stocké ici)
-- ---------------------------------------------------------------------------
CREATE TABLE wallets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gkach_wallet_id UUID NOT NULL UNIQUE,   -- ID du wallet dans le système GKach
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    currency        CHAR(3) NOT NULL REFERENCES currencies(code),
    type            VARCHAR(30) NOT NULL DEFAULT 'standard',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Comptes bancaires
-- ---------------------------------------------------------------------------
CREATE TABLE bank_accounts (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    wallet_id    UUID NOT NULL REFERENCES wallets(id),
    account_type VARCHAR(20) NOT NULL CHECK (account_type IN
                    ('personnel','entreprise','eglise','ong','institution')),
    status       VARCHAR(20) NOT NULL DEFAULT 'active', -- active, suspended, closed
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Transactions (miroir en lecture des écritures GKach, pour requêtage local)
-- ---------------------------------------------------------------------------
CREATE TABLE transactions (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wallet_id     UUID NOT NULL REFERENCES wallets(id),
    type          VARCHAR(30) NOT NULL,   -- deposit, withdrawal, transfer, qr_payment...
    amount        NUMERIC(18,2) NOT NULL,
    status        VARCHAR(20) NOT NULL,   -- completed, failed, pending
    gkach_txn_ref UUID NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE deposits (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wallet_id  UUID NOT NULL REFERENCES wallets(id),
    amount     NUMERIC(18,2) NOT NULL,
    method     VARCHAR(30) NOT NULL,
    status     VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE withdrawals (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wallet_id  UUID NOT NULL REFERENCES wallets(id),
    amount     NUMERIC(18,2) NOT NULL,
    method     VARCHAR(30) NOT NULL,
    status     VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Épargne
-- ---------------------------------------------------------------------------
CREATE TABLE savings_accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id),
    wallet_id       UUID NOT NULL REFERENCES wallets(id),
    product_type    VARCHAR(20) NOT NULL CHECK (product_type IN ('libre','bloquee','programmee')),
    rate            NUMERIC(6,4) NOT NULL,
    principal       NUMERIC(18,2) NOT NULL DEFAULT 0,
    accrued_interest NUMERIC(18,2) NOT NULL DEFAULT 0,
    term_days       INT,
    maturity_date   TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Investissements
-- ---------------------------------------------------------------------------
CREATE TABLE investment_plans (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name           VARCHAR(20) NOT NULL CHECK (name IN ('Bronze','Silver','Gold','Platinum')),
    rate           NUMERIC(6,4) NOT NULL,
    duration_months INT NOT NULL,
    risk_level     VARCHAR(20) NOT NULL,
    min_amount     NUMERIC(18,2) NOT NULL,
    created_by     UUID REFERENCES users(id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE investments (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES users(id),
    wallet_id  UUID NOT NULL REFERENCES wallets(id),
    plan_id    UUID NOT NULL REFERENCES investment_plans(id),
    amount     NUMERIC(18,2) NOT NULL,
    status     VARCHAR(20) NOT NULL DEFAULT 'active',
    start_date TIMESTAMPTZ NOT NULL DEFAULT now(),
    end_date   TIMESTAMPTZ NOT NULL
);

-- ---------------------------------------------------------------------------
-- Prêts
-- ---------------------------------------------------------------------------
CREATE TABLE loans (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    borrower_id   UUID NOT NULL REFERENCES users(id),
    wallet_id     UUID NOT NULL REFERENCES wallets(id),
    type          VARCHAR(20) NOT NULL CHECK (type IN
                    ('personnel','commercial','agricole','urgence','etudiant')),
    amount        NUMERIC(18,2) NOT NULL,
    interest_rate NUMERIC(6,4) NOT NULL,
    term_months   INT NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    ai_score      INT,
    ai_risk       VARCHAR(20),
    approved_by   UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at   TIMESTAMPTZ
);

CREATE TABLE loan_schedules (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    loan_id            UUID NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    installment_number INT NOT NULL,
    due_date           TIMESTAMPTZ NOT NULL,
    principal          NUMERIC(18,2) NOT NULL,
    interest           NUMERIC(18,2) NOT NULL,
    amount_due         NUMERIC(18,2) NOT NULL,
    status             VARCHAR(20) NOT NULL DEFAULT 'upcoming',
    UNIQUE (loan_id, installment_number)
);

CREATE TABLE loan_repayments (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    loan_id        UUID NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
    schedule_id    UUID NOT NULL REFERENCES loan_schedules(id),
    amount_paid    NUMERIC(18,2) NOT NULL,
    penalty        NUMERIC(18,2) NOT NULL DEFAULT 0,
    gkach_txn_ref  UUID,
    paid_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Crowdlending
-- ---------------------------------------------------------------------------
CREATE TABLE crowdlending_opportunities (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    loan_id           UUID NOT NULL REFERENCES loans(id),
    amount_requested  NUMERIC(18,2) NOT NULL,
    amount_funded     NUMERIC(18,2) NOT NULL DEFAULT 0,
    expected_return   NUMERIC(6,4) NOT NULL,
    risk_level        VARCHAR(20) NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'open',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE crowdlending_contributions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    opportunity_id  UUID NOT NULL REFERENCES crowdlending_opportunities(id) ON DELETE CASCADE,
    investor_id     UUID NOT NULL REFERENCES users(id),
    amount          NUMERIC(18,2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Taux, pénalités, fonds de garantie
-- ---------------------------------------------------------------------------
CREATE TABLE interest_rates (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_type   VARCHAR(30) NOT NULL,
    rate           NUMERIC(6,4) NOT NULL,
    effective_date TIMESTAMPTZ NOT NULL DEFAULT now(),
    set_by_admin_id UUID NOT NULL REFERENCES users(id)
);

CREATE TABLE penalty_rules (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_type       VARCHAR(30) NOT NULL,
    penalty_rate       NUMERIC(6,4) NOT NULL,
    grace_period_days  INT NOT NULL DEFAULT 0
);

CREATE TABLE guarantee_fund (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    balance          NUMERIC(18,2) NOT NULL DEFAULT 0,
    cap              NUMERIC(18,2) NOT NULL,
    coverage_percent NUMERIC(5,2) NOT NULL,
    last_updated     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Notifications, audit, paramètres
-- ---------------------------------------------------------------------------
CREATE TABLE notifications (
    id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id),
    channel VARCHAR(20) NOT NULL CHECK (channel IN ('email','sms','push','whatsapp','in_app')),
    message TEXT NOT NULL,
    status  VARCHAR(20) NOT NULL DEFAULT 'pending',
    sent_at TIMESTAMPTZ
);

CREATE TABLE audit_logs (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_id   UUID REFERENCES users(id),
    action     VARCHAR(100) NOT NULL,
    entity     VARCHAR(100) NOT NULL,
    entity_id  UUID,
    ip_address INET,
    timestamp  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE settings (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key        VARCHAR(100) UNIQUE NOT NULL,
    value      JSONB NOT NULL,
    updated_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Index recommandés
-- ---------------------------------------------------------------------------
CREATE INDEX idx_transactions_wallet ON transactions(wallet_id);
CREATE INDEX idx_loans_borrower ON loans(borrower_id);
CREATE INDEX idx_loan_schedules_loan ON loan_schedules(loan_id);
CREATE INDEX idx_investments_user ON investments(user_id);
CREATE INDEX idx_notifications_user ON notifications(user_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity, entity_id);
