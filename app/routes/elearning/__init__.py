"""
E-LEARNING (Konferans extension) Blueprint package.

Package structure (convention Flask so static_folder / template_folder work):
  app/routes/elearning/
    __init__.py       → exports elearning_bp + registers sub-module routes
    routes.py         → stub HTTP routes (dashboards, class/course/lesson/assignment)
    static/css/elearning.css  → isolated stylesheet
"""
from app.routes.elearning.routes import elearning_bp

__all__ = ['elearning_bp']
