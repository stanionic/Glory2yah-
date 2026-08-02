"""
Bank Blueprint Package (racine Glory2YahPub)
Pattern identique a mennem/ / dok/ / party/ : app.py expose l'objet Blueprint.

Ce package est un adaptateur mince: il re-exporte bank_bp defini dans
app.routes.bank (qui contient toutes les routes / models / logique pret+invest).
Ainsi register_blueprint() utilise:
    from bank.app import bank_bp
    app.register_blueprint(bank_bp)
(url_prefix='/bank' est DEJA defini dans le Blueprint de app.routes.bank,
ne PAS le repasser ici pour eviter double prefixe /bank/bank/...).
"""
from app.routes.bank import bank_bp

__all__ = ['bank_bp']
