"""
Bank Flask Blueprint — point d'entree du package racine `bank/`.

Pattern: `from bank.app import bank_bp` (identique a mennem.app / dok.app / party.app)
L'objet Blueprint et TOUTES ses routes sont definis dans `app.routes.bank`;
ce module ne fait que le re-exporter pour satisfaire la convention d'import
des blueprints autonome a la racine du projet.
"""
from app.routes.bank import bank_bp

__all__ = ['bank_bp']
