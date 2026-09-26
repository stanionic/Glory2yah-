"""
Blueprint registry — all registered blueprints in the application.
Each entry contains: name, import path, prefix, status.
"""
BLUEPRINTS = [
    # ── Core ──────────────────────────────────────────────────────────────
    ("admin_bp",          "app.routes.admin",         "/admin",          "registered"),
    ("main_bp",           "app.routes.main",          "/",               "registered"),
    ("auth_bp",           "app.routes.auth",          "/auth",           "registered"),
    ("gkach_bp",          "app.routes.gkach",         "/gkach",          "registered"),
    ("marketplace_bp",    "app.routes.marketplace",   "/marketplace",    "registered"),
    ("cart_bp",           "app.routes.cart",          "/cart",           "registered"),
    ("events_bp",         "app.routes.events",        "/events",         "registered"),
    ("pwa_bp",            "app.routes.pwa",           "/pwa",            "registered"),
    ("bank_bp",           "app.routes.bank",          "/bank",           "registered"),
    ("delivery_bp",       "app.routes.delivery",      "/delivery",       "registered"),
    ("gforms_bp",         "app.routes.gforms",        "/gforms",         "registered"),
    ("jere_biznis_web",   "app.routes.jere_biznis",   "/jere-biznis",    "registered"),
    ("share_bp",          "app.routes.share",         "/share",          "registered"),

    # ── Features ──────────────────────────────────────────────────────────
    ("elearning_bp",      "app.routes.elearning",     "/elearning",      "registered"),
    ("story_bp",          "app.routes.story",         "/story",          "registered"),
    ("ad_bp",             "app.routes.ad",            "/ad",             "registered"),

    # ── Context-dependent ─────────────────────────────────────────────────
    ("admin_bp",         "app.routes.admin",         "/admin",          "depends_on_admin_mode"),
]