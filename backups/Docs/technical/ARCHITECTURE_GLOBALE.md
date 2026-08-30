# Architecture Globale — Map Generator Pro v7.0

**Dernière mise à jour** : 2026-08-14  
**Version application** : 7.0

---

## 📋 Vue d'ensemble

**Map Generator Pro** est une application Streamlit de génération et édition de cartes topographiques pour Arma Reforger/Enfusion. Elle orchestre un pipeline complet depuis la heightmap jusqu'à l'écriture des fichiers terrain binaires (.ttile).

### Principes architecturaux

1. **Interface centralisée** : `app.py` — Application Streamlit avec navigation par cartes
2. **Modules métier** : Scripts spécialisés pour chaque étape du pipeline
3. **Gestion de projets** : Système de projets avec `project.json` (chemins, config, métadonnées)
4. **Cache intelligent** : Données terrain calculées une fois et mises en cache
5. **Scripts standalone** : Outils CLI indépendants (`merge_mat.py`, `ttile_manager.py`)

---

## 🗂️ Structure des fichiers principaux

### 1. Application principale

#### **`app.py`** (3130 lignes)
**Rôle** : Interface Streamlit principale — Hub central de l'application

**Responsabilités** :
- Navigation par cartes (7 onglets thématiques)
- Gestion projets (création, chargement, sauvegarde)
- Configuration chemins centralisés
- Chargement heightmap + calcul `terrain_data` (avec cache)
- Import modules UI (`tab_*.py`)
- Session state management

**Fonctions principales** :
```python
create_project(name, author, description) → Path
load_project(project_path) → None  # Charge dans session_state
save_project() → None  # Sauvegarde project.json
auto_save() → None  # Sauvegarde automatique
initialize_session() → None
render_navigation_cards() → None
```

**Onglets disponibles** :
1. **Heightmap** — Visualisation, Atlas, Chemins
2. **Pipeline** — Configuration pipeline legacy (deprecated)
3. **Satmap** — Génération cartes satellitaires texturées
4. **Terrain** — Inspection binaires .ttile, QTRE, budget
5. **Corrections** — Scan Zone B, nettoyage, force-mat
6. **Validation** — Simulation, conflits masques
7. **Pipeline V5** — Pipeline unifié avec mapping masque → texture

---

### 2. Modules métier core

#### **`base_map.py`** (~400 lignes)
**Rôle** : Classe `BaseMap` — Couche fondamentale de données terrain

**Responsabilités** :
- Chargement heightmap (.asc, .png, .tif)
- Calcul altitudes réelles (min/max en mètres)
- Calcul slopes (degrés via Sobel)
- Génération water_mask + biome_masks (7 biomes)

**Classe principale** :
```python
class BaseMap:
    __init__(heightmap_path, vertical_exaggeration=10.0)
    
    # Données
    heightmap_float: np.ndarray  # Altitudes réelles (m)
    heightmap_uint8: np.ndarray  # Normalisé 0-255
    altitude_min, altitude_max: float
    slopes: np.ndarray  # Degrés
    water_mask: np.ndarray  # Booléen
    biome_masks: dict  # 7 masques (water, sand, snow, rock, tundra, forest, prairie)
```

**Usage** : Source unique de vérité pour toutes cartes dérivées (ColorMap, NatureMap, Hypsometric)

---

#### **`terrain_analysis.py`** (~800 lignes)
**Rôle** : Calcul centralisé des dérivés terrain — CŒUR DU PIPELINE

**Version pipeline** : `2.3.0` (pour invalidation cache)

**Responsabilités** :
- Calcul TOUS les dérivés terrain UNE SEULE FOIS
- Flow accumulation (priority flood + post-processing)
- TPI multi-échelle (local 11px + macro 51px)
- Curvature (plan + profile)
- Coastal distance, aspect, roughness
- Auto-calibration seuils

**Fonction principale** :
```python
compute_terrain_data(heightmap_path, params=None, progress_callback=None) → dict
    """
    Retourne:
        {
            # Données brutes
            'heightmap': array float32,
            'heightmap_smooth': array float32,
            'meta': dict (ncols, nrows, cellsize),
            'cellsize': float,
            
            # Dérivés terrain
            'slope': array float32,  # degrés
            'curvature': array float32,  # normalisé
            'curvature_plan': array float32,
            'curvature_profile': array float32,
            'tpi_local': array float32,
            'tpi_macro': array float32,
            'flow': array float32,  # normalisé
            'deposit': array float32,
            'distance_cote': array float32,  # mètres
            'aspect': array float32,  # degrés 0-360
            'roughness': array float32,
            
            # Métadonnées
            'params': dict,  # Paramètres calibrés
            'computation_time': float,  # secondes
            'timestamp': str,
            'pipeline_version': str  # "2.3.0"
        }
    """
```

**Cache** : Sauvegardé dans `outputs/cache/terrain_data.npz` + `terrain_meta.json`  
**Invalidation** : Si `pipeline_version` change ou heightmap modifiée

---

#### **`hypsometric_colormap.py`** (~300 lignes)
**Rôle** : Génération cartes hypsométriques pures (altitude → couleur)

**Responsabilités** :
- Gradient couleur basé altitude (vert bas → rouge haut)
- Hillshading optionnel
- Enrichissement morphologique (TPI, talwegs, dépressions)

**Classe** :
```python
class HypsometricColormapGenerator:
    __init__(heightmap_path, output_dir)
    save(filename, add_hillshade=False, add_enrichment=False) → str
```

**Palette** : Vert (#2ca25f) → Jaune → Orange → Rouge → Brun (#993404)

---

### 3. Pipeline texture (V5)

#### **`pipeline_v5.py`** (~2500 lignes)
**Rôle** : Pipeline terrain unifié MODERNE — Remplace `pipeline_unified`

**⚠️ BREAKING CHANGES v7.0** :
- Écriture directe `.ttile` binaire (plus de PNG intermédiaire)
- Arbitrage budget QTRE automatique (6 slots/bloc max)
- Mapping masque → texture configurable (61 matériaux)
- Préservation Zone B (textures existantes intactes)

**Modules du pipeline** :
1. Lecture heightmap .asc
2. Calcul terrain (slope, fBm, coastal)
3. Masques de base (seabed, coastal, rock, landes, flow, deposit)
4. Végétation (prairie, maquis, alpages, forêts)
5. Application masque exclusion (Zone B préservée)
6. Normalisation exclusive (vectorisée)
7. **Arbitrage budget par bloc** (nouveau)
8. Visualisation carte colorisée
9. Export masques PNG OU écriture `.ttile`

**Fonction principale** :
```python
run_pipeline(
    asc_path,
    output_dir,
    exclusion_mask=None,
    gaea_flow=None,
    gaea_deposit=None,
    mask_config=None,  # Mapping masque → texture
    mode='preview',  # 'preview' | 'png' | 'ttile'
    terrain_root=None,
    data_dir=None,
    terr_path=None
) → dict  # Résultats pipeline
```

**Mapping masque → texture** :
```python
MASK_TEXTURE_MAP = {
    'seabed': [1, 10, 11],  # SeaBed_01, Pebbles_01/02
    'coastal': [16],  # BeachGrass_01
    'rock': [8],  # Rock_01
    # ... 13 masques au total
}

DEFAULT_PRIORITIES = {
    'seabed': 90,
    'coastal': 85,
    'rock': 80,
    # ... ordre d'application
}
```

---

#### **`tab_pipeline_v5.py`** (~800 lignes)
**Rôle** : Interface Streamlit pour pipeline V5

**Sections UI** :
1. Sources (fichiers entrée avec Browse tkinter)
2. Mapping masque → texture (`st.data_editor`)
3. Paramètres pipeline (expanders)
4. Bouton "Générer preview"
5. Boutons export (PNG / `.ttile`)

**Fonction** :
```python
render_tab_pipeline_v5() → None
```

---

### 4. Gestion terrain binaire Reforger

#### **`ttile_manager.py`** (~2000 lignes)
**Rôle** : Gestionnaire COMPLET des `.ttile` — OUTIL CLI PUISSANT

**Modes disponibles** :
- `inspect` — Affiche état bloc (matériaux, budget, distribution)
- `visualize` — Exporte grille 45×45 en PNG
- `scan` — Scanne tous blocs Zone A/B/complète
- `stats` — Liste tous matériaux + comptage
- `validate` — Vérifie cohérence LRS2 ↔ GCTD
- `replace` — Remplace matériau (1 bloc / liste / all)
- `merge` — Fusionne matériau vers autre
- `optimize` — Fusionne sous-représentés (libère slots)
- `apply-mask` — Applique masque PNG sur bloc(s)
- `apply-pipeline` — Applique dossier masques sur Zone A
- `backup-zone-b` — Sauvegarde état Zone B → JSON
- `restore-zone-b` — Restaure état Zone B
- `clean-zone-a` — Écrit texture neutre sur Zone A
- `restore` — Restaure depuis backup `.bak`
- `export-csv` — Exporte état tous blocs CSV
- `compare` — Compare deux états map

**Fonctions clés** :
```python
# Lecture/écriture IFF
parse_ttile(data) → dict  # chunks {tag: (pos, size, payload)}
rebuild_ttile(original, replacements) → bytes

# Sections terrain
parse_lrs2(payload) → dict  # {(bx,by): ([mat_ids], index)}
parse_gctd(payload, n_blocs) → tuple  # (header, sections, size)
build_lrs2(entries) → bytes
build_gctd(header, sections) → bytes

# Opérations blocs
apply_mask_to_block(block_data, mask_png, mat_id) → bytes
get_block_distribution(block_data) → dict  # comptage matériaux
optimize_block(block_data, threshold=5) → bytes  # fusionne sous-seuil
```

**Usage CLI** :
```bash
python ttile_manager.py --mode inspect --addon-path "I:/..." --bx 34 --by 79
python ttile_manager.py --mode replace --all --old-mat 0 --new-mat 3
python ttile_manager.py --mode backup-zone-b --mask exclusion.png --out zone_b.json
```

---

#### **`merge_mat.py`** (~400 lignes)
**Rôle** : Script standalone merge matériaux `.ttile` (LRS2 + GCTD)

**⚠️ NE TOUCHE PAS aux `.edds`** — Workbench les régénère au Save

**Fonctions** :
```python
# IFF
parse_ttile(data) → dict
rebuild_ttile(original, replacements) → bytes

# LRS2
parse_lrs2(payload) → dict
build_lrs2(entries) → bytes

# GCTD
parse_gctd(payload, n_blocs) → tuple
build_gctd(header, sections) → bytes

# Merge
merge_block(bx, by, src_mat, dst_mat, mat_filter=None) → bool
```

**Usage** :
```bash
# Dry-run bloc spécifique
python merge_mat.py --src 0 --dst 3 --tile 4,27 --bloc 18,110 --dry-run

# Merge tile complète
python merge_mat.py --src 0 --dst 3 --tile 4,27

# Merge conditionnel (seulement matériau 9)
python merge_mat.py --src 0,mat:9 --dst 3 --all

# Restore depuis backup
python merge_mat.py --restore
```

---

### 5. Satmap (cartes satellitaires texturées)

#### **`satmap_v2_generator.py`** (~800 lignes)
**Rôle** : Génération Satmap v2.0 depuis layer.edds + LRS2

**Améliorations v2** :
- Lit vrais poids GPU depuis `layer.edds` (supporte 1-7 textures)
- Plus de trous comme avec QTRE approximatif
- Blending précis matériaux par bloc

**Fonctions** :
```python
load_catalog(catalog_path) → dict
get_material_color(mat_id, catalog, surfaces) → np.ndarray  # RGB
load_material_texture(mat_id, catalog, surfaces, root) → np.ndarray
generate_satmap_v2(
    terrain_root,
    catalog_path,
    output_path,
    mode='colored',  # 'colored' | 'textured'
    exclusion_mask=None
) → Path
```

**Modes** :
- `colored` — Tint sRGB par matériau (rapide, léger)
- `textured` — Textures BCR réelles blendées (lourd, photoréaliste)

---

#### **`satmap_v2_textured.py`** (~600 lignes)
**Rôle** : Variante texturée Satmap v2 (mode photoréaliste)

**Spécificités** :
- Charge textures middle BCR `.edds` (8192×8192 par défaut)
- Blending GPU-like des poids par cellule
- Export PNG haute résolution

---

### 6. Parsers & Readers

#### **`terrain_terr_reader.py`** (~300 lignes)
**Rôle** : Parse fichiers `.terr` Reforger (binaire IFF)

**Fonctions** :
```python
read_mats_from_terr(terr_path) → list[dict]
    """
    Retourne:
        [
            {'id': 0, 'name': 'Grass_03_default', 'guid': '...'},
            {'id': 1, 'name': 'SeaBed_01', 'guid': '...'},
            ...
        ]
    """
```

**Format** : Binaire IFF avec chunks `FORM`, `SURF`, `GUID`

---

#### **`edds_decoder.py`** (~500 lignes)
**Rôle** : Décodeur fichiers `.edds` layer (poids terrain GPU)

**Fonctions** :
```python
decode_edds_layer(file_path) → dict
    """
    Retourne:
        {
            'width': int,
            'height': int,
            'channels': int,  # 1-7 (RGBA + BC5)
            'data': np.ndarray uint8,  # (H, W, channels)
        }
    """

extract_all_weights(file_path) → np.ndarray
    # Retourne (H, W, 7) float32 normalisé [0-1]
```

**Formats supportés** :
- `RGBA` (4 canaux)
- `BC5` (2 canaux — RG pour weight 5-6)
- Format custom Enfusion 7-canaux

---

#### **`lrs2_parser.py`** (~200 lignes)
**Rôle** : Parse section LRS2 des `.ttile` (index matériaux par bloc)

**Fonctions** :
```python
load_lrs2_from_ttile(ttile_path) → dict
    """
    Retourne:
        {
            (bx, by): [mat0, mat1, mat2, ...],  # Liste matériaux actifs bloc
            ...
        }
    """
```

**Format LRS2** : Liste compressée `[(index_bloc, count, [mat_ids])]`

---

### 7. Validation & Diagnostics

#### **`pipeline_validation.py`** (~600 lignes)
**Rôle** : Validation masques terrain — Fonctions pures numpy/cv2

**Fonctions** :
```python
load_masks_from_paths(file_paths, max_size=None) → dict
    """
    Retourne:
        {
            'masks': list[np.ndarray],  # uint16
            'paths': list[str],
            'shape': tuple,
            'errors': list[str],
            'warnings': list[str]
        }
    """

analyze_conflicts(masks, threshold=0.15) → dict
    """
    Détecte conflits masques (overlap > seuil)
    Retourne:
        {
            'conflict_map': np.ndarray,  # uint16
            'conflict_pixels': int,
            'conflict_pct': float,
            'pairs': list[tuple],  # [(i, j, overlap_pct)]
        }
    """

simulate_qtre(masks, priorities, max_slots=4) → dict
    """
    Simule arbitrage QTRE 4-textures
    Retourne:
        {
            'final_map': np.ndarray,  # mat_id par pixel
            'stats': dict,  # Distribution matériaux
            'warnings': list[str]
        }
    """
```

**Usage** : Appelé par onglet "Validation" pour détecter problèmes avant export

---

#### **`check_terrain_health.py`** (~400 lignes)
**Rôle** : Diagnostic santé terrain global

**Vérifications** :
- Blocs corrompus (chunk manquant)
- Distribution matériaux anormale
- Blocs vides (100% default)
- Budget QTRE dépassé (>6 slots)
- Cohérence LRS2 ↔ GCTD

**Fonction** :
```python
check_all_blocks(terrain_root) → dict
    """
    Retourne:
        {
            'total_blocks': int,
            'corrupted': list[tuple],  # [(bx, by)]
            'empty': list[tuple],
            'overbudget': list[tuple],
            'inconsistent': list[tuple],
            'report': str
        }
    """
```

---

### 8. Utilitaires

#### **`project_manager.py`** (~150 lignes)
**Rôle** : Gestion `surfaces.json` par projet

**Fonction** :
```python
load_or_update_surfaces(project_path, terr_path) → tuple[dict, dict]
    """
    Charge ou génère surfaces.json depuis .terr
    
    Retourne:
        (
            name_to_id: {"Grass_01": 0, ...},
            id_to_name: {0: "Grass_01", ...}
        )
    """
```

**Invalidation** : Si `.terr` modifié (chemin ou taille)

---

#### **`reforger_texture_budget.py`** (~500 lignes)
**Rôle** : Calcul budget QTRE et arbitrage smart

**Fonctions** :
```python
arbitrate_qtre_block(
    masks: list[np.ndarray],
    priorities: list[int],
    max_slots=4
) → np.ndarray
    """
    Arbitrage intelligent per-pixel selon priorités
    Retourne: array (H, W) avec mat_id gagnant
    """

compute_block_budget(masks: list[np.ndarray]) → dict
    """
    Calcul distribution matériaux et slots nécessaires
    Retourne:
        {
            'slots_needed': int,
            'materials': dict,  # {mat_id: pixel_count}
            'coverage': dict,   # {mat_id: pct}
        }
    """
```

---

#### **`write_ttile_block.py`** (~300 lignes)
**Rôle** : Écriture blocs `.ttile` depuis masques

**Fonction** :
```python
write_block_from_masks(
    bx, by,
    masks: list[np.ndarray],
    mat_ids: list[int],
    terrain_root: Path,
    terr_path: Path
) → bool
```

**Format GCTD** : Grille 45×45 compressée (4 slots × sub-index)

---

## 🔄 Flux de données principal

### Workflow complet

```
1. CHARGEMENT PROJET
   app.py::load_project()
      ↓
   Charge project.json
      ↓
   Charge heightmap (.asc) → BaseMap
      ↓
   Calcul terrain_data (ou charge cache)
      ↓
   terrain_analysis::compute_terrain_data()
      ↓
   Sauvegarde cache (terrain_data.npz + terrain_meta.json)

2. GÉNÉRATION PIPELINE V5
   tab_pipeline_v5::render_tab_pipeline_v5()
      ↓
   Configuration mapping masque → texture
      ↓
   pipeline_v5::run_pipeline()
      ↓
   Modules 1-6 : Génération masques
      ↓
   Module 7 : Arbitrage budget par bloc
      ↓
   Module 8 : Visualisation preview
      ↓
   Module 9 : Export (PNG | .ttile)

3. ÉCRITURE .TTILE
   pipeline_v5 → write_ttile_block
      ↓
   Pour chaque bloc (bx, by):
      - Calcul grille 45×45
      - Arbitrage 6 slots max
      - Encode GCTD (4 slots + sub)
      - Encode LRS2 (index matériaux)
      - Rebuild IFF
      - Écriture .ttile

4. VÉRIFICATION
   ttile_manager.py --mode validate
      ↓
   Vérifie cohérence LRS2 ↔ GCTD
      ↓
   check_terrain_health.py
      ↓
   Rapport diagnostic

5. GÉNÉRATION SATMAP
   satmap_v2_generator::generate_satmap_v2()
      ↓
   Lit layer.edds (poids GPU)
      ↓
   Lit LRS2 (matériaux par bloc)
      ↓
   Blend couleurs/textures
      ↓
   Export PNG 4097×4097
```

---

## 📦 Dépendances entre modules

### Graph de dépendances

```
app.py
├── base_map.py
├── hypsometric_colormap.py
├── terrain_analysis.py
│   └── pipeline_v2.py (fonctions calcul)
├── pipeline_validation.py
├── tab_pipeline_v5.py
│   └── pipeline_v5.py
│       ├── write_ttile_block.py
│       │   ├── terrain_terr_reader.py
│       │   └── lrs2_parser.py
│       └── reforger_texture_budget.py
├── project_manager.py
│   └── terrain_terr_reader.py
└── satmap_v2_generator.py
    ├── edds_decoder.py
    └── lrs2_parser.py

STANDALONE (pas importé par app.py):
merge_mat.py
├── terrain_terr_reader.py
└── [écriture binaire directe]

ttile_manager.py
├── terrain_terr_reader.py
├── lrs2_parser.py
└── [CLI complet]
```

---

## 🗃️ Structure projet (`project.json`)

### Format v1.1

```json
{
  "version": "1.1",
  "created_at": "2026-08-01T14:30:00",
  "updated_at": "2026-08-14T10:45:00",
  
  "project": {
    "name": "Zimnitrita",
    "author": "[otea] Giorbev",
    "description": "Carte 16km² inspirée Monténégro",
    "tags": ["mediterranean", "mountains"]
  },
  
  "assets": {
    "heightmap": {
      "filename": "Terrain_modified5.asc",
      "format": "asc",
      "cellsize": 1.0,
      "width": 16385,
      "height": 16385,
      "alt_min": -47.2,
      "alt_max": 1873.5
    },
    "satmap": {
      "filename": "satmap_source.png",
      "width": 4097,
      "height": 4097
    }
  },
  
  "reforger_grid": {
    "tiles": [32, 32],
    "blocks_per_tile": [4, 4],
    "block_size_m": [128, 128],
    "tile_size_m": [512, 512],
    "planar_resolution_m": 1.0,
    "height_min_m": -47.2,
    "height_max_m": 1873.5
  },
  
  "paths": {
    "heightmap": "inputs/heightmap/Terrain_modified5.asc",
    "satmap": "inputs/satmap/satmap_source.png",
    "exclusion_mask": "inputs/masks/new_exclusion4.png",
    "gaea_flow": "inputs/gaea/flow_uint16.png",
    "gaea_deposit": "inputs/gaea/sediment_uint16.png",
    "exports_mask": "outputs/masks/latest/",
    "addon_reforger": "I:/Reforger_addons/Zimnitrita_map",
    "catalog_json": "H:/data/catalog.json",
    "satmap_v2": "outputs/generated/satmap_v2_textured_4097.png",
    "data_dir": "I:/Reforger_addons/Zimnitrita_map/World/Zimnitrita/Terrain/.Data"
  },
  
  "modules": {
    "terrain_preview": {
      "climate_profile": "tempere",
      "max_slots": 4,
      "snow_pct": 92,
      "flow_pct": 88,
      "coastal_dist_m": 60,
      "snowline_pct": 0.75,
      "sat_strength": 0.35
    },
    "vegetation": {
      "blend": true,
      "min_score": 0.05,
      "resolution": 1024,
      "use_lock": false,
      "lock_folder": ""
    }
  },
  
  "terr_project_path": "I:/Reforger_addons/Zimnitrita_map/World/Zimnitrita/Terrain/terrain.terr",
  "world_terrain_path": "I:/Reforger_addons/Zimnitrita_map/World/Zimnitrita/Terrain/terrain.terr"
}
```

---

## 🎯 Cas d'usage typiques

### 1. Nouveau projet depuis heightmap

```python
# Dans app.py
new_path = create_project("Ma_carte", "Auteur", "Description")
load_project(str(new_path))

# Uploader heightmap → inputs/
# → Auto-calcul terrain_data
# → Sauvegarde cache
```

### 2. Génération pipeline complet

```python
# Dans tab_pipeline_v5.py
from pipeline_v5 import run_pipeline

result = run_pipeline(
    asc_path="inputs/heightmap.asc",
    output_dir="outputs/latest",
    exclusion_mask="inputs/masks/exclusion.png",
    gaea_flow="inputs/gaea/flow.png",
    mode='ttile',  # Écriture directe
    terrain_root=Path("I:/addon/World/Map/Terrain"),
    terr_path=Path("I:/addon/World/Map/Terrain/terrain.terr")
)
# → Écrit .ttile pour tous blocs Zone A
```

### 3. Correction manuelle matériau

```bash
# Remplacer Grass_03_default (0) par Grass_03 (3) sur tous blocs
python ttile_manager.py \
    --mode replace \
    --addon-path "I:/addon" \
    --all \
    --old-mat 0 \
    --new-mat 3
```

### 4. Merge conditionnel

```bash
# Merger 0 vers 3 SEULEMENT où il y a du matériau 9 (Dirt_02)
python merge_mat.py --src 0,mat:9 --dst 3 --all
```

### 5. Génération Satmap photoréaliste

```python
from satmap_v2_generator import generate_satmap_v2

output = generate_satmap_v2(
    terrain_root=Path("I:/addon/World/Map/Terrain"),
    catalog_path=Path("H:/data/catalog.json"),
    output_path=Path("outputs/satmap_v2.png"),
    mode='textured',  # Textures réelles
    exclusion_mask=Path("inputs/masks/exclusion.png")
)
# → PNG 4097×4097 texturé
```

---

## 🔧 Configuration & Paramètres

### Constantes pipeline V5

```python
# pipeline_v5.py
BUDGET_MAX = 6         # Slots max par bloc (QTRE)
OUTPUT_SIZE = 4096     # Résolution masques PNG
GCTD_GRID = 45         # Cellules par axe payload GCTD
GRID_W = 32            # Tuiles par axe
NUM_BLK = 4            # Blocs par tuile par axe

# Seuils pente
THRESHOLD_GENTLE = None  # Auto p70
THRESHOLD_LANDES = None  # Auto p85
THRESHOLD_ROCK = 22.0
THRESHOLD_CLIFF = 26.0

# Végétation
VEG_MIN_SCORE = 0.15
```

### Mapping masque → texture

```python
MASK_TEXTURE_MAP = {
    'seabed': [1, 10, 11],      # SeaBed_01, Pebbles_01/02
    'coastal': [16],            # BeachGrass_01
    'flow': [2, 9],             # Dirt_01/02
    'deposit': [10, 11],        # Pebbles_01/02
    'landes_rocheuses': [7],    # Debris_Rock_01
    'rock': [8],                # Rock_01
    'prairie_humide': [14],     # Grass_01
    'prairie_seche': [3, 20],   # Grass_03, Grass_02
    'landes_plateau': [21, 22], # ZI_Landes_Rocheuses_01/02
    'maquis_landes': [23],      # ZI_Maquis_Landes_01
    'alpages': [24],            # ZI_Alpages_01
    'foret_feuillue': [4],      # ForestDeciduous_02
    'foret_coniferes': [19]     # ForestConiferous_02
}
```

---

## 📝 Nomenclature & Conventions

### Nommage fichiers

- **Masques** : `{ordre}_{role}.png` (ex: `01_seabed.png`, `12_foret_feuillue.png`)
- **Heightmap** : `Terrain_*.asc` ou `.png`
- **Satmap** : `satmap_source.png` (entrée), `satmap_v2_*.png` (sortie)
- **Exclusion** : `exclusion*.png` ou `new_exclusion*.png`
- **Cache** : `terrain_data.npz`, `terrain_meta.json`

### Coordonnées blocs

- **Format global** : `(bx, by)` où `0 ≤ bx,by < 128` (pour map 32×32 tuiles × 4×4 blocs)
- **Format tuile** : `(tx, ty, local_bx, local_by)` où `0 ≤ local_bx,local_by < 4`

### Matériaux

- **ID** : Index global dans liste `surfaces` du `.terr` (0-based)
- **Nom** : Stem sans extension (ex: `Grass_03`, `Rock_01`)
- **GUID** : Identifiant Reforger 16 bytes (stocké dans `.terr`)

---

## 🚀 Points d'entrée

### Interface Streamlit

```bash
streamlit run app.py
```

**Port** : `http://localhost:8501`

### CLI Standalone

```bash
# Diagnostic terrain
python check_terrain_health.py --addon-path "I:/addon"

# Manager .ttile
python ttile_manager.py --mode <mode> --addon-path "I:/addon" [options]

# Merge matériaux
python merge_mat.py --src 0 --dst 3 --all

# Pipeline direct (rare)
python pipeline_v5.py
```

---

## 📊 Performance & Optimisations

### Cache terrain_data

**Gain** : Chargement ~0.1s au lieu de 30-60s  
**Invalidation** : Si `pipeline_version` change ou heightmap modifiée  
**Taille** : ~50-200 MB selon résolution heightmap

### Calcul flow (priority flood)

**Algorithme** : Queue prioritaire (heap)  
**Complexité** : O(n log n) où n = nombre pixels  
**Temps typique** : 15-25s pour 16k×16k  
**Post-processing** : Blur sigma=3 + gamma correction

### QTRE arbitrage

**Algorithme** : Per-pixel priorité descendante  
**Optimisation** : Vectorisé numpy (pas de boucles Python)  
**Temps** : <1s pour 4096×4096×13 masques

---

## 🐛 Debugging & Logs

### Logs pipeline

```python
# pipeline_v5.py utilise safe_print()
safe_print("[MODULE 1/9] Lecture heightmap...")
safe_print(f"  • Altitude : {h_min:.1f} → {h_max:.1f}m")
```

### Vérification .ttile

```bash
# Inspecter bloc
python ttile_manager.py --mode inspect --addon-path "I:/..." --bx 34 --by 79

# Valider cohérence
python ttile_manager.py --mode validate --addon-path "I:/..."
```

### Erreurs courantes

1. **Cache obsolète** : Supprimer `outputs/cache/terrain_data.npz`
2. **Budget dépassé** : Réduire nombre masques actifs ou fusionner matériaux
3. **Zone B corrompue** : Restaurer depuis backup JSON
4. **Blocs vides** : Vérifier masque exclusion (blanc = Zone A, noir = Zone B)

---

## 🔮 Évolution prévue

### Roadmap Phase 2 (post-v7.0)

1. **Bibliothèque matériaux** : Obsolète (déclarée 2026-07-08), suppression prévue
2. **Onglet Végétation** : Carte 2D potentielle, export SVG → splines Reforger
3. **Éditeur heightmap** : Génération île, érosion, aplanissement (après végétation)
4. **Layer generator** : Outil standalone génération `.layer` depuis OSM (bâtiments)

---

## 📚 Ressources complémentaires

### Documentation technique

- [FORMAT_LAYER_EDDS.md](FORMAT_LAYER_EDDS.md) — Reverse engineering `.edds` layer
- [ANALYSE_LOGIQUE_BOHEMIA_LAYER_EDDS.md](ANALYSE_LOGIQUE_BOHEMIA_LAYER_EDDS.md) — Logique slots QTRE
- Mémoire projet : `C:\Users\jordi\.claude\projects\h--logiciel-perso-Map-generator\memory\MEMORY.md`

### Fichiers référence

- `reference_zimnitrita.md` — Map 16km, 56 matériaux, QTRE 4-mat
- `reference_reforger_constraints.md` — Contraintes QTRE, seuils calibrés
- `project_pipeline_7_masques.md` — Pipeline 7 masques optimisé actuel

---

**Document généré le** : 2026-08-14  
**Auteur** : Claude Code (analyse codebase Map Generator Pro v7.0)  
**Mise à jour** : Synchronisé avec état actuel projet
