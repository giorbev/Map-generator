# Architecture Clean — Tentative Refactoring (Mai 2025)

## Contexte
Tentative de migration vers Clean Architecture (Domain/Application/Infrastructure)

## Statut
- **Démarré** : 25 mai 2025
- **Abandonné** : ~25 mai 2025 (même jour)
- **Archivé** : 8 juillet 2026
- **Raison** : Complexité excessive pour un projet solo, scripts plats plus rapides

## Ce qui a été fait
- Structure Domain/Application/Infrastructure complète
- SatMapAnalyzerFacade fonctionnel
- Use Cases : analyze_satmap, generate_masks, generate_terrain_preview
- Factory pattern implémenté
- Models : Mask, SatMap, Terrain
- Services : SatMapIndexService, TerrainScoreService
- Adapters : PillowRgbAligner, Percentile99Normalizer

## Ce qui manque
- Implémentation complète des Use Cases
- Tests unitaires
- Migration progressive depuis app.py
- Documentation complète
- Intégration avec le reste du projet

## Structure
```
map_generator/
├── domain/          # Modèles métier, Services, Ports
├── application/     # Use Cases, Factories, Facades
└── infrastructure/  # Adapters techniques
```

## Si reprise future
1. Finir les Use Cases manquants
2. Écrire tests unitaires (pytest)
3. Créer facades pour chaque module app.py
4. Migration progressive module par module
5. Garder scripts legacy en parallèle pendant transition
6. Mesurer gains vs complexité ajoutée

## Notes
- Code bien structuré mais sur-engineering pour un projet solo
- Scripts plats actuels (racine/) fonctionnent bien
- Reprendre seulement si projet devient multi-dev ou librairie
