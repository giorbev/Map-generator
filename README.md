# Map Generator Pro

Outil de génération et d'analyse de cartes terrain pour **Arma Reforger / Enfusion Engine**.

## Fonctionnalités

### Gestion de projets
- Projets indépendants avec `project.json` (heightmap, grille Reforger, profils, masques IT)
- Support heightmap ASC (ESRI ASCII Grid), PNG 8/16-bit
- **Masques Instant Terra** : slopes, curvature, sediment — source de vérité prioritaire du pipeline texture
- Migration automatique des anciens formats de projet
- **Bibliothèque de matériaux** vanilla + custom par projet (JSON éditables)

### 🏔️ Onglet Terrain

**Hypsométrique** — Colormap par paliers d'altitude, hillshade intégré, export PNG

**Analyse** — Statistiques d'altitude, distribution, pentes, grille Reforger

### 🎨 Onglet Génération

**Aperçu Texture** — Pipeline morphologique en 2 passes :

- **Passe 1 — Textures de base** : fond marin, côtier, galets, prairie, herbe dense, lande, heather
- **Passe 2 — Textures d'érosion** (pilotée par masques Instant Terra) :
  - `slopes.png` → roche (pentes > 30°) + debris (frange + crevasses)
  - `mask_curv.png` → roche convexe (crêtes), érosion concave (fond de ravine), debris flancs (talweg)
  - `mask_sediment.png` → renforce l'érosion au fond des talwegs
  - Propagation organique sur plateaux adjacents (évite les frontières géométriques)
- Profils climatiques : Tempéré, Aride, Continental, Tropical, Subarctique, Alpin
- Budget QTRE : max 4 textures par bloc 32 m, diagnostic et correction automatique
- Export PNG 16-bit par rôle, prêt pour import Workbench

**Végétation** — Carte 2D de végétation potentielle :
- 13 types de zones (forêt bouleaux, pins, épicéas, maquis, roseaux, saule, pierres…)
- 3 types linéaires (haies, roseaux, lisière)
- Règles écologiques : altitude, pente, exposition, flow, humidité
- Option : exclusion des zones verrouillées (champs, urbain)
- Export PNG, légende complète

### 🗂️ Onglet Calques & Export

**Calque Texture** — Masques morphologiques générés, export par rôle

**Calque TMAT** — Lecture des `.ttile` / `.terr` Workbench, visualisation RGB blendée

**Calque SatMap** — Génération SatMap tuilée par matériau BCRMiddleMap, segmentation K-means

**Carte Reconstruction** — Vue aérienne depuis masques exportés + overlay de zones

**Fusion Masques** — Zones verrouillées (villes, champs) préservées + auto-material sur zones naturelles → ZIP prêt Workbench

## Démarrage rapide

```bash
pip install streamlit pillow numpy scipy matplotlib opencv-python pandas
streamlit run app.py
```

L'interface s'ouvre sur `http://localhost:8501`.

## Format de projet

```
data/projects/<nom>/
├── project.json                    — métadonnées et configuration
├── material_library_custom.json    — matériaux custom du projet
├── sources/
│   └── import instant/             — masques Instant Terra (slopes, curvature, sediment)
├── generated/                      — sorties générées par l'outil
└── masks/                          — masques de surface exportés (PNG 16-bit)
```

Bibliothèque vanilla partagée : `data/material_library_vanilla.json`

## Masques Instant Terra

| Fichier | Encodage | Rôle dans le pipeline |
|---------|----------|-----------------------|
| `slopes.png` | 0 = 0°, 1 = 90° | Seuil roche (~30°), frange debris |
| `mask_curv.png` | 0.5 = neutre, sombre = concave | Crêtes (roche), fond de ravine (érosion) |
| `mask_sediment.png` | 0 = aucun, 1 = accumulation | Renforce dirt au fond des talwegs |

Résolution requise : identique à la heightmap (ex. 8193×8193 pour 8 km à 1 m/px).

---

Développé par **[otea] Giorbev** with Claude AI
