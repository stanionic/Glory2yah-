# TODO - Fix ADS disparus après commit

## Étapes
- [x] 1. Ajouter `invalidate_all_ad_caches()` dans `app/services/ad_service.py`
- [x] 2. Vider le cache Redis au démarrage dans `app/__init__.py` (`create_app()`)
- [x] 3. Supprimer `_flush_approved_cache()` dans `app/routes/main.py` (N/A — pas présent dans main.py)
- [x] 4. Supprimer `_flush_approved_cache()` dans `app/routes/marketplace.py`
- [x] 5. Tester que les annonces approuvées sont visibles après redémarrage
