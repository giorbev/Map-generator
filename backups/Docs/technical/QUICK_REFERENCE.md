# Quick Reference — Map Generator Pro v7.0

**Référence ultra-rapide** : Qui fait quoi en une ligne

---

## 🎯 Scripts principaux par fonction

### Interface & Orchestration

| Script | Rôle |
|--------|------|
| **app.py** | Application Streamlit principale — Hub central navigation + gestion projets |
| **tab_pipeline_v5.py** | Onglet Pipeline V5 — Interface UI mapping masques → textures |
| **tab_gen_v3.py** | Onglet génération legacy (deprecated) |

### Données Terrain Core

| Script | Rôle |
|--------|------|
| **base_map.py** | Classe BaseMap — Heightmap + slopes + 7 biomes (source unique vérité) |
| **terrain_analysis.py** | Calcul TOUS dérivés terrain (flow, TPI, curvature) — CŒUR DU PIPELINE |
| **hypsometric_colormap.py** | Génération cartes hypsométriques pures (altitude → couleur gradient) |

### Pipeline Texture

| Script | Rôle |
|--------|------|
| **pipeline_v5.py** | Pipeline unifié moderne — 13 masques → .ttile avec arbitrage budget 6 slots |
| **pipeline_unified.py** | Pipeline legacy (deprecated v7.0, remplacé par V5) |
| **pipeline_v2.py** | Fonctions calcul terrain (utilisé par terrain_analysis.py) |
| **pipeline_preview.py** | Génération preview pipeline (overlay Satmap V2) |

### Gestion Terrain Binaire

| Script | Rôle |
|--------|------|
| **ttile_manager.py** | Gestionnaire COMPLET .ttile — CLI 15+ modes (inspect, replace, merge, optimize, backup) |
| **merge_mat.py** | Script standalone merge matériaux .ttile (LRS2 + GCTD, conditionnel) |
| **write_ttile_block.py** | Écriture blocs .ttile depuis masques (encodage GCTD 4 slots + sub) |

### Satmap (Cartes Satellitaires)

| Script | Rôle |
|--------|------|
| **satmap_v2_generator.py** | Génération Satmap v2 depuis layer.edds + LRS2 (mode colored/textured) |
| **satmap_v2_textured.py** | Variante photoréaliste Satmap v2 (charge textures BCR réelles) |
| **satmap_classifier.py** | Classification pixels satmap (legacy, rarement utilisé) |
| **satmap_verifiers.py** | Vérificateurs qualité satmap |

### Parsers & Readers

| Script | Rôle |
|--------|------|
| **terrain_terr_reader.py** | Parse fichiers .terr Reforger (binaire IFF) → liste matériaux + GUID |
| **edds_decoder.py** | Décodeur layer.edds (poids GPU) — Supporte RGBA, BC5, format 7-canaux |
| **lrs2_parser.py** | Parse section LRS2 des .ttile → index matériaux par bloc |
| **layer_dds_reader.py** | Lecteur layer DDS (legacy) |

### Validation & Diagnostics

| Script | Rôle |
|--------|------|
| **pipeline_validation.py** | Validation masques — Détecte conflits, simule QTRE, charge masques PNG 16-bit |
| **check_terrain_health.py** | Diagnostic santé terrain global — Blocs corrompus, vides, overbudget, LRS2≠GCTD |
| **validation_zone_b.py** | Vérification Zone B préservée (compare avant/après pipeline) |

### Utilitaires

| Script | Rôle |
|--------|------|
| **project_manager.py** | Gestion surfaces.json par projet — Auto-génération depuis .terr |
| **reforger_texture_budget.py** | Calcul budget QTRE + arbitrage smart per-bloc |
| **app_config.py** | Configuration centralisée chemins + résolution paths |
| **vegetation_map.py** | Carte végétation 2D (roadmap Phase 2) |

### Scripts Analyse & Debug

| Script | Rôle |
|--------|------|
| **compare_texture_blocks.py** | Compare deux blocs .ttile (distribution matériaux, différences) |
| **scan_exclusion_zone.py** | Scanne Zone B pour backup (sauvegarde état avant pipeline) |
| **simulate_masks.py** | Simule pipeline sans écrire (test conflits, budget) |
| **tile_inspector.py** | Inspecte tuile complète (4×4 blocs) — Distribution globale |
| **read_texture_blocks.py** | Lecture blocs debug (affiche LRS2 + GCTD brut) |
| **extract_texture_maps.py** | Extrait textures depuis .edds (debug) |
| **emat_scanner_simple.py** | Scanne fichiers .emat (matériaux Reforger) |
| **reforger_emat_parser.py** | Parse fichiers .emat (extraction propriétés) |

### Scripts Cleanup & Maintenance

| Script | Rôle |
|--------|------|
| **cleanup_ttile.py** | Nettoyage .ttile (suppression blocs corrompus/orphelins) |
| **clean_weights.py** | Nettoyage poids layer.edds (normalisation) |
| **cross_mask_diff.py** | Différence croisée entre masques (détecte overlaps) |

---

## 🔥 Top 10 scripts les plus utilisés

1. **app.py** — Point d'entrée application
2. **terrain_analysis.py** — Calcul dérivés terrain (requis pour pipeline)
3. **pipeline_v5.py** — Pipeline moderne complet
4. **tab_pipeline_v5.py** — Interface pipeline
5. **ttile_manager.py** — Gestion .ttile (CLI puissant)
6. **satmap_v2_generator.py** — Génération satmap
7. **base_map.py** — Données terrain fondamentales
8. **merge_mat.py** — Merge matériaux rapide
9. **check_terrain_health.py** — Diagnostic terrain
10. **pipeline_validation.py** — Validation masques avant export

---

## 📋 Workflows typiques

### Workflow 1 : Nouveau projet

```
1. app.py → Créer projet
2. Uploader heightmap → terrain_analysis calcul auto
3. tab_pipeline_v5 → Configurer mapping masques
4. pipeline_v5 → Générer + écrire .ttile
5. satmap_v2_generator → Générer satmap
```

### Workflow 2 : Correction matériau global

```
1. ttile_manager --mode scan → Analyser état actuel
2. ttile_manager --mode replace → Remplacer matériau
3. ttile_manager --mode validate → Vérifier cohérence
4. satmap_v2_generator → Régénérer satmap
```

### Workflow 3 : Diagnostic problème

```
1. check_terrain_health → Rapport global
2. ttile_manager --mode stats → Distribution matériaux
3. ttile_manager --mode inspect → Détail blocs suspects
4. compare_texture_blocks → Comparer avant/après
```

---

## 🎨 Modules par couche logique

### Couche Présentation (UI)
→ `app.py`, `tab_*.py`

### Couche Métier (Business Logic)
→ `pipeline_v5.py`, `satmap_v2_generator.py`, `pipeline_validation.py`

### Couche Données (Data Access)
→ `base_map.py`, `terrain_analysis.py`, `edds_decoder.py`

### Couche Persistance (Storage)
→ `ttile_manager.py`, `write_ttile_block.py`, `project_manager.py`

---

## 🔧 Outils CLI en une commande

```bash
# Diagnostic complet
python check_terrain_health.py --addon-path "I:/addon"

# Inspecter bloc
python ttile_manager.py --mode inspect --bx 34 --by 79

# Remplacer matériau global
python ttile_manager.py --mode replace --all --old-mat 0 --new-mat 3

# Merge conditionnel
python merge_mat.py --src 0,mat:9 --dst 3 --all

# Backup Zone B
python ttile_manager.py --mode backup-zone-b --mask exclusion.png --out backup.json

# Statistiques matériaux
python ttile_manager.py --mode stats --out materials.csv
```

---

## 📦 Dépendances critiques

```
app.py
├── base_map.py
├── terrain_analysis.py
│   └── pipeline_v2.py
└── tab_pipeline_v5.py
    └── pipeline_v5.py
        └── write_ttile_block.py
            ├── terrain_terr_reader.py
            └── lrs2_parser.py

ttile_manager.py (standalone)
merge_mat.py (standalone)
check_terrain_health.py (standalone)
```

---

## 🗂️ Format fichiers clés

| Format | Description | Parseur |
|--------|-------------|---------|
| `.ttile` | Blocs terrain binaire IFF (LRS2 + GCTD) | `ttile_manager.py`, `merge_mat.py` |
| `.terr` | Config terrain binaire (matériaux, GUID) | `terrain_terr_reader.py` |
| `.edds` | Layer poids GPU (7 canaux) | `edds_decoder.py` |
| `.asc` | Heightmap ESRI Grid ASCII | `base_map.py`, `pipeline_v5.py` |
| `project.json` | Config projet (v1.1) | `app.py`, `project_manager.py` |
| `surfaces.json` | Matériaux terrain (auto-généré) | `project_manager.py` |

---

## 🎯 Constantes importantes

```python
BUDGET_MAX = 6          # Slots QTRE max (7 total - 1 réservé)
GCTD_GRID = 45          # Cellules par axe grille GCTD
GRID_W = 32             # Tuiles par axe (map 32×32)
NUM_BLK = 4             # Blocs par tuile par axe
OUTPUT_SIZE = 4096      # Résolution masques PNG
SATMAP_SIZE = 4097      # Résolution Satmap
```

---

## 📚 Documentation complète

→ Voir [README_ARCHITECTURE.md](README_ARCHITECTURE.md) pour index complet

---

**Mise à jour** : 2026-08-14  
**Version** : 7.0
