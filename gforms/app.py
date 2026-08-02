"""
G-Forms Flask Blueprint — point d'entree du package racine `gforms/`.

Pattern: `from gforms.app import gforms_bp` (identique a mennem.app / dok.app).
L'objet Blueprint et sa logique (sert G-Forms/dist SPA build, fallback placeholder
sinon) sont definis dans `app.routes.gforms`; ce module ne fait que re-exporter.
"""
from app.routes.gforms import gforms_bp

__all__ = ['gforms_bp']
