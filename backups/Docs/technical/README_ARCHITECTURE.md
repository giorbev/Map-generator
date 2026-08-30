# Documentation Architecture — Map Generator Pro v7.0

**Index de la documentation technique complète**

---

## 📚 Documents disponibles

### 1. [ARCHITECTURE_GLOBALE.md](ARCHITECTURE_GLOBALE.md) — Vue d'ensemble complète

**Pour** : Comprendre l'application dans son ensemble

**Contenu** :
- ✅ Vue d'ensemble architecture globale
- ✅ Description détaillée de chaque script (rôle, responsabilités, fonctions)
- ✅ Structure projet (`project.json`, arborescence fichiers)
- ✅ Flux de données principal (chargement → pipeline → export)
- ✅ Graph de dépendances entre modules
- ✅ Cas d'usage typiques avec exemples code
- ✅ Configuration & paramètres
- ✅ Performance & optimisations
- ✅ Debugging & erreurs courantes
- ✅ Roadmap évolution

**Quand l'utiliser** :
- Nouveau sur le projet → lire en premier
- Comprendre comment tout s'articule
- Chercher un workflow complet (exemple : "Comment générer un terrain complet ?")
- Référence architecture globale

---

### 2. [REFERENCE_FONCTIONS.md](REFERENCE_FONCTIONS.md) — Guide de référence rapide

**Pour** : Trouver rapidement une fonction spécifique

**Contenu** :
- ✅ Liste exhaustive fonctions par script
- ✅ Signatures avec paramètres et retours
- ✅ Docstrings condensées
- ✅ Constantes globales
- ✅ Exemples CLI pour scripts standalone

**Quand l'utiliser** :
- Chercher signature exacte d'une fonction
- Vérifier paramètres d'une API
- Copier-coller exemple CLI
- Référence développeur rapide

**Format** :
```python
fonction(param1: type, param2: type) → type_retour
    """Description concise"""
```

---

### 3. [DIAGRAMMES_ARCHITECTURE.md](DIAGRAMMES_ARCHITECTURE.md) — Représentations visuelles

**Pour** : Visualiser flux et structures

**Contenu** :
- ✅ Architecture globale (couches logiques)
- ✅ Pipeline V5 complet (9 modules)
- ✅ Structure fichier `.ttile` (IFF, LRS2, GCTD)
- ✅ Encodage GCTD (4 slots + sub-index)
- ✅ Arbitrage budget QTRE (diagramme décision)
- ✅ Organisation terrain Reforger (grille 32×32)
- ✅ Flux Satmap v2 (layer.edds → PNG)
- ✅ Gestion cache `terrain_data` (chargement/invalidation)
- ✅ Workflows CLI (diagnostic, merge, correction)
- ✅ Systèmes de coordonnées (bx/by, tuile, fichier, LRS2)
- ✅ Analyse distribution matériaux

**Quand l'utiliser** :
- Comprendre flux de données visuellement
- Débugger format binaire `.ttile`
- Comprendre système coordonnées
- Visualiser processus pipeline

**Format** : Diagrammes ASCII art avec annotations

---

## 🎯 Par cas d'usage

### Je débute sur le projet

1. **Lire** : [ARCHITECTURE_GLOBALE.md](ARCHITECTURE_GLOBALE.md) — Section "Vue d'ensemble"
2. **Visualiser** : [DIAGRAMMES_ARCHITECTURE.md](DIAGRAMMES_ARCHITECTURE.md) — "Architecture globale"
3. **Parcourir** : [REFERENCE_FONCTIONS.md](REFERENCE_FONCTIONS.md) — Scripts principaux

### Je veux comprendre le pipeline terrain

1. **Lire** : [ARCHITECTURE_GLOBALE.md](ARCHITECTURE_GLOBALE.md) — Section "Pipeline texture (V5)"
2. **Visualiser** : [DIAGRAMMES_ARCHITECTURE.md](DIAGRAMMES_ARCHITECTURE.md) — "Pipeline V5 — Flux complet"
3. **Code** : [REFERENCE_FONCTIONS.md](REFERENCE_FONCTIONS.md) — `pipeline_v5.py`

### Je veux modifier/corriger des blocs terrain

1. **Visualiser** : [DIAGRAMMES_ARCHITECTURE.md](DIAGRAMMES_ARCHITECTURE.md) — "Structure .ttile" + "Systèmes coordonnées"
2. **Lire** : [ARCHITECTURE_GLOBALE.md](ARCHITECTURE_GLOBALE.md) — Section "ttile_manager.py" + "merge_mat.py"
3. **CLI** : [REFERENCE_FONCTIONS.md](REFERENCE_FONCTIONS.md) — Modes CLI `ttile_manager`

### Je cherche une fonction précise

1. **Référence** : [REFERENCE_FONCTIONS.md](REFERENCE_FONCTIONS.md) — Ctrl+F sur nom fonction
2. **Contexte** : [ARCHITECTURE_GLOBALE.md](ARCHITECTURE_GLOBALE.md) — Lire section script concerné

### Je veux optimiser performance

1. **Lire** : [ARCHITECTURE_GLOBALE.md](ARCHITECTURE_GLOBALE.md) — Section "Performance & Optimisations"
2. **Visualiser** : [DIAGRAMMES_ARCHITECTURE.md](DIAGRAMMES_ARCHITECTURE.md) — "Gestion cache terrain_data"

### J'ai un bug à débugger

1. **Lire** : [ARCHITECTURE_GLOBALE.md](ARCHITECTURE_GLOBALE.md) — Section "Debugging & Logs"
2. **Visualiser** : [DIAGRAMMES_ARCHITECTURE.md](DIAGRAMMES_ARCHITECTURE.md) — Workflow concerné
3. **CLI** : [REFERENCE_FONCTIONS.md](REFERENCE_FONCTIONS.md) — `check_terrain_health.py`

---

## 📂 Structure scripts par domaine

### Interface utilisateur
- **`app.py`** — Application Streamlit principale (hub central)
- **`tab_pipeline_v5.py`** — Onglet Pipeline V5 (UI)
- **`tab_gen_v3.py`** — Onglet génération (legacy)

### Données terrain core
- **`base_map.py`** — BaseMap (heightmap + slopes + biomes)
- **`terrain_analysis.py`** — Calcul dérivés terrain (flow, TPI, curvature)
- **`hypsometric_colormap.py`** — Cartes hypsométriques

### Pipeline texture
- **`pipeline_v5.py`** — Pipeline unifié moderne (13 masques → .ttile)
- **`pipeline_unified.py`** — Pipeline legacy (deprecated v7.0)
- **`pipeline_v2.py`** — Fonctions calcul terrain (utilisé par `terrain_analysis`)

### Gestion terrain binaire
- **`ttile_manager.py`** — Gestionnaire complet .ttile (CLI 15+ modes)
- **`merge_mat.py`** — Merge matériaux standalone
- **`write_ttile_block.py`** — Écriture blocs depuis masques

### Satmap (cartes satellitaires)
- **`satmap_v2_generator.py`** — Génération Satmap v2 (layer.edds → PNG)
- **`satmap_v2_textured.py`** — Variante photoréaliste
- **`satmap_classifier.py`** — Classification pixels (legacy)

### Parsers & Readers
- **`terrain_terr_reader.py`** — Parse .terr (matériaux)
- **`edds_decoder.py`** — Décodeur layer.edds (poids GPU)
- **`lrs2_parser.py`** — Parse LRS2 (index matériaux)

### Validation & Diagnostics
- **`pipeline_validation.py`** — Validation masques (conflits, simulation QTRE)
- **`check_terrain_health.py`** — Diagnostic santé terrain global
- **`validation_zone_b.py`** — Vérification Zone B préservée

### Utilitaires
- **`project_manager.py`** — Gestion surfaces.json
- **`reforger_texture_budget.py`** — Calcul budget QTRE
- **`app_config.py`** — Configuration centralisée

### Scripts analyse
- **`compare_texture_blocks.py`** — Compare deux blocs
- **`scan_exclusion_zone.py`** — Scanne Zone B
- **`simulate_masks.py`** — Simule pipeline sans écrire
- **`tile_inspector.py`** — Inspecte tuile complète
- **`read_texture_blocks.py`** — Lecture blocs (debug)

---

## 🗂️ Structure données projet

### Arborescence type

```
data/projects/Mon_Projet/
├── project.json              ← Configuration centrale
├── surfaces.json             ← Matériaux terrain (auto-généré)
│
├── inputs/                   ← Fichiers source
│   ├── heightmap/
│   │   └── Terrain.asc
│   ├── satmap/
│   │   └── satmap_source.png
│   ├── masks/
│   │   └── exclusion.png
│   └── gaea/
│       ├── flow.png
│       └── sediment.png
│
├── outputs/                  ← Fichiers générés
│   ├── masks/
│   │   └── latest/
│   │       ├── 01_seabed.png
│   │       ├── 02_coastal.png
│   │       └── ...
│   ├── satmap/
│   │   └── satmap_v2.png
│   ├── reports/
│   │   ├── pipeline_preview.png
│   │   └── health_report.json
│   ├── generated/
│   │   └── satmap_v2_textured_4097.png
│   └── cache/
│       ├── terrain_data.npz
│       └── terrain_meta.json
│
└── backups/                  ← Sauvegardes manuelles
```

### `project.json` — Sections principales

```json
{
  "version": "1.1",
  "project": { ... },           // Métadonnées projet
  "assets": {                   // Fichiers source
    "heightmap": { ... },
    "satmap": { ... }
  },
  "reforger_grid": { ... },     // Structure terrain Reforger
  "paths": {                    // Chemins centralisés
    "heightmap": "...",
    "addon_reforger": "...",
    "data_dir": "...",
    ...
  },
  "modules": {                  // Config modules UI
    "terrain_preview": { ... },
    "vegetation": { ... }
  }
}
```

---

## 🔧 Outils CLI — Résumé

### `ttile_manager.py` — Gestionnaire .ttile

**15+ modes disponibles** :

```bash
# Inspection
python ttile_manager.py --mode inspect --addon-path "I:/..." --bx 34 --by 79
python ttile_manager.py --mode visualize --bx 34 --by 79 --out grid.png
python ttile_manager.py --mode scan --mask exclusion.png --out scan.json

# Statistiques
python ttile_manager.py --mode stats --out materials.csv
python ttile_manager.py --mode validate

# Modifications
python ttile_manager.py --mode replace --all --old-mat 0 --new-mat 3
python ttile_manager.py --mode merge --bx 34 --by 79 --src 8 --dst 7
python ttile_manager.py --mode optimize --bx 34 --by 79 --threshold 5

# Masques
python ttile_manager.py --mode apply-mask --bx 34 --by 79 --mask rock.png --mat 8
python ttile_manager.py --mode apply-pipeline --mask-dir outputs/masks/latest/

# Backup/Restore
python ttile_manager.py --mode backup-zone-b --mask exclusion.png --out zone_b.json
python ttile_manager.py --mode restore-zone-b --backup zone_b.json
python ttile_manager.py --mode restore --bx 34 --by 79
```

### `merge_mat.py` — Merge matériaux

```bash
# Merge simple
python merge_mat.py --src 0 --dst 3 --tile 4,27

# Merge conditionnel
python merge_mat.py --src 0,mat:9 --dst 3 --all

# Restore
python merge_mat.py --restore
```

### `check_terrain_health.py` — Diagnostic

```bash
python check_terrain_health.py --addon-path "I:/addon" --out health.json
```

---

## 📖 Concepts clés

### 1. Terrain data cache

**Quoi** : Tous dérivés terrain (slope, flow, TPI, curvature) calculés UNE fois et mis en cache

**Où** : `outputs/cache/terrain_data.npz` + `terrain_meta.json`

**Invalidation** :
- Si `pipeline_version` change
- Si heightmap modifiée (mtime)

**Gain** : Chargement 0.1s au lieu de 30-60s

### 2. Pipeline V5 — Modules

**9 étapes** :
1. Lecture heightmap
2. Calcul terrain
3. Masques base (seabed, coastal, rock, landes)
4. Végétation (prairie, maquis, alpages, forêts)
5. Application exclusion (Zone B)
6. Normalisation exclusive
7. **Arbitrage budget par bloc** (6 slots max)
8. Visualisation preview
9. Export (PNG | .ttile)

### 3. Format .ttile (IFF)

**Structure** :
- **HEADER** : IFF (`FORM` + size + type)
- **CHUNK LRS2** : Index matériaux par bloc `{(bx,by): [mat_ids]}`
- **CHUNK GCTD** : Grilles 45×45 encodées (4 slots + sub-index)

**Encodage GCTD** : 1 byte par cellule
- Bits 7-4 : slot (0-15)
- Bits 3-0 : sub-index (0-15)

### 4. Systèmes coordonnées

**Global** : `(bx, by)` où `0 ≤ bx,by < 128`

**Tuile** : `(tx, ty, local_bx, local_by)` où `0 ≤ local < 4`

**Conversion** :
```python
bx = tx × 4 + local_bx
by = ty × 4 + local_by
```

**Fichier** : `{bx:04x}_{by:04x}.ttile`

**LRS2 packed** : `index = bx | (by << 7)`

### 5. Arbitrage QTRE

**Problème** : Reforger supporte max 7 textures/bloc (6 utiles + 1 réservé)

**Solution** : Per-bloc, garder top 6 matériaux par priorité, arbitrer per-pixel si >6

**Algorithme** :
1. Extraire région 128×128 pour chaque masque
2. Compter matériaux actifs
3. Si >6 : trier par priorité, garder top 6
4. Per-pixel : matériau gagnant = max poids parmi top 6
5. Downsampling 128→45 (nearest)
6. Encodage GCTD

---

## 🚀 Points d'entrée rapides

### Interface graphique

```bash
streamlit run app.py
```
→ `http://localhost:8501`

### Pipeline complet (CLI)

```python
from pipeline_v5 import run_pipeline

result = run_pipeline(
    asc_path="inputs/heightmap.asc",
    output_dir="outputs/latest",
    mode='ttile',
    terrain_root=Path("I:/addon/World/Map/Terrain")
)
```

### Diagnostic complet

```bash
python check_terrain_health.py --addon-path "I:/addon"
python ttile_manager.py --mode validate
python ttile_manager.py --mode stats --out materials.csv
```

---

## 🐛 Résolution problèmes courants

### Cache obsolète

**Symptôme** : Données terrain anciennes, calculs incorrects

**Solution** :
```bash
rm outputs/cache/terrain_data.npz
rm outputs/cache/terrain_meta.json
# Recharger projet dans app.py → recalcul auto
```

### Budget QTRE dépassé

**Symptôme** : Bloc avec >6 matériaux, textures manquantes in-game

**Diagnostic** :
```bash
python ttile_manager.py --mode inspect --bx 34 --by 79
```

**Solution** :
1. Fusionner matériaux sous-représentés
2. Réduire nombre masques actifs
3. Ajuster priorités mapping

### Zone B corrompue

**Symptôme** : Textures Zone B écrasées par erreur

**Diagnostic** :
```bash
python ttile_manager.py --mode scan --mask exclusion.png
```

**Solution** :
```bash
python ttile_manager.py --mode restore-zone-b --backup zone_b_backup.json
```

### Blocs vides (100% default)

**Symptôme** : Blocs avec 100% matériau 0 (Grass_03_default)

**Diagnostic** :
```bash
python check_terrain_health.py --addon-path "I:/addon"
```

**Solution** : Vérifier masque exclusion (blanc=Zone A, noir=Zone B)

---

## 📊 Métriques performance

### Calcul terrain_data
- **Temps** : 30-60s pour 16k×16k heightmap
- **Composants** :
  - Flow accumulation : ~15-25s (priority flood)
  - TPI multi-échelle : ~8-12s
  - Curvature : ~5-8s
  - Autres : ~5s
- **Optimisation** : Cache NPZ → 0.1s chargement

### Pipeline V5
- **Temps** : 5-15min pour 16k×16k (dépend zone A)
- **Goulots** :
  - Normalisation masques : 30-60s
  - Arbitrage budget : 1-2min
  - Écriture .ttile : 3-10min (fonction zone A)

### Satmap V2
- **Mode colored** : 2-5min
- **Mode textured** : 15-30min (charge textures BCR)

---

## 🔮 Évolution & Roadmap

### Phase actuelle (v7.0)
✅ Pipeline V5 opérationnel  
✅ Écriture directe .ttile  
✅ Arbitrage budget automatique  
✅ Cache terrain_data  

### Prochaines étapes
🔜 Bibliothèque matériaux → **OBSOLÈTE** (suppression prévue)  
🔜 Onglet Végétation (carte potentielle, export SVG)  
🔜 Éditeur heightmap (génération île, érosion)  
🔜 Layer generator (OSM → .layer bâtiments)  

---

## 📚 Ressources complémentaires

### Documentation technique spécialisée
- [FORMAT_LAYER_EDDS.md](FORMAT_LAYER_EDDS.md) — Reverse engineering `.edds` layer
- [ANALYSE_LOGIQUE_BOHEMIA_LAYER_EDDS.md](ANALYSE_LOGIQUE_BOHEMIA_LAYER_EDDS.md) — Logique slots QTRE

### Mémoire projet
- `C:\Users\jordi\.claude\projects\h--logiciel-perso-Map-generator\memory\MEMORY.md`

### Fichiers référence (mémoire)
- `reference_zimnitrita.md` — Map 16km, 56 matériaux, QTRE 4-mat
- `reference_reforger_constraints.md` — Contraintes QTRE, seuils calibrés
- `project_pipeline_7_masques.md` — Pipeline 7 masques optimisé actuel

---

## 📞 Contact & Contribution

**Auteur** : [otea] Giorbev  
**Email** : giordano.bevini@gmail.com  
**Version** : 7.0 (2026-08-14)

---

**Documentation générée le** : 2026-08-14  
**Par** : Claude Code (analyse codebase complète)  
**Mise à jour** : Synchronisée avec état actuel projet
