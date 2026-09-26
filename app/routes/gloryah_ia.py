"""Integrated GlorYah IA chat blueprint.

The standalone multimodal project remains available under ``GlorYah_IA/``;
this adapter gives the main application one safe, namespaced entry point.
"""
import logging
from functools import lru_cache

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ImportError:  # pragma: no cover - the main app normally provides it
    Limiter = None
    get_remote_address = None


logger = logging.getLogger(__name__)
gloryah_ia_bp = Blueprint("gloryah_ia", __name__, url_prefix="/gloryah-ia")
MAX_PROMPT_LENGTH = 5000
ALLOWED_MODES = {"chat", "code"}


@lru_cache(maxsize=1)
def _fallback_engine():
    from GlorYah_IA.models.smart_fallback import SmartFallback

    return SmartFallback()


@gloryah_ia_bp.get("/")
@login_required
def index():
    return render_template("gloryah_ia/index.html")


@gloryah_ia_bp.post("/chat")
@login_required
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(success=False, error="Fòma demann lan pa valid."), 400

    prompt = data.get("prompt")
    if not isinstance(prompt, str):
        return jsonify(success=False, error="Mesaj la dwe yon tèks."), 400
    prompt = prompt.strip()
    if not prompt:
        return jsonify(success=False, error="Ou dwe ekri yon mesaj."), 400
    if len(prompt) > MAX_PROMPT_LENGTH:
        return jsonify(
            success=False,
            error=f"Mesaj la pa ka depase {MAX_PROMPT_LENGTH} karaktè.",
        ), 400

    mode = data.get("mode", "chat")
    if mode not in ALLOWED_MODES:
        return jsonify(success=False, error="Mòd sa a pa disponib."), 400

    try:
        response = _fallback_engine().generate(prompt, use_web_search=False)
    except Exception:
        logger.exception("GlorYah IA fallback generation failed")
        return jsonify(
            success=False,
            error="GlorYah IA pa disponib kounye a. Eseye ankò pita.",
        ), 503

    return jsonify(success=True, response=response, mode=mode)
