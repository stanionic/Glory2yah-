"""
G-Forms Blueprint Package (racine Glory2YahPub)
Pattern identique a mennem/ / dok/ / party/ : app.py expose l'objet Blueprint.

Adaptateur mince: re-exporte gforms_bp defini dans app.routes.gforms, qui sert
le SPA Vite/React du dossier `G-Forms/dist` si build, sinon le placeholder
templates/gforms/index.html.
"""
from app.routes.gforms import gforms_bp

__all__ = ['gforms_bp']
