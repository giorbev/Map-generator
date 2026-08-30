# Organisation App.py — État des Lieux

**Date:** 2026-08-02
**Version app:** v5.1
**Auteur:** Analyse technique complète

---

## Vue d'ensemble

Map Generator Pro v5.1 est une application Streamlit complexe de **génération de cartes topographiques** pour le moteur Enfusion (Arma Reforger). L'application orchestre :
- Analyse terrain depuis heightmaps (ASC, PNG 16-bit)
- Génération de masques textures (pipeline multi-passes)
- Export vers format Reforger (.terr, .ttile, .edds)
- Validation QTRE (budget textures par bloc)
- Génération satmap et végétation

**Architecture:** Monolithique avec modules métier découplés
**Interface:** Streamlit (onglets multiples)
**Stockage:** Système de projets JSON + cache NPZ
**Lignes de code app.py:** 3641 lignes

---

## Architecture Globale

```
┌───────────────────────────────────────────────────────────────┐
│                         APP.PY                                │
│                  (Streamlit orchestrator)                     │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Sidebar    │  │   Onglets    │  │  Session     │       │
│  │  - Heightmap │  │  - Terrain   │  │  State       │       │
│  │  - Satmap    │  │  - Satmap    │  │  - Projet    │       │
│  │  - Reforger  │  │  - Génération│  │  - Terrain   │       │
│  │  - Export    │  │  - Validation│  │  - Résultats │       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
│         │                 │                 │                │
└─────────┼─────────────────┼─────────────────┼────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    MODULES MÉTIER                           │
├──────────────────┬────────────────────┬─────────────────────┤
│  DATA LOADING    │   TERRAIN ANALYSIS │  PIPELINE GEN       │
│  - base_map.py   │   - terrain_       │  - pipeline_v2.py   │
│  - app_config.py │     analysis.py    │  - pipeline_v3.py   │
│                  │   - hypsometric_   │  - tab_gen_v3.py    │
│                  │     colormap.py    │  - vegetation_map.py│
├──────────────────┼────────────────────┼─────────────────────┤
│  VALIDATION      │   SATMAP EXPORT    │  REFORGER I/O       │
│  - pipeline_     │   - satmap_v2_     │  - reforger_        │
│    validation.py │     generator.py   │    texture_budget.py│
│  - mask_utils.py │   - satmap_v2_     │  - emat_scanner_    │
│                  │     textured.py    │    simple.py        │
│                  │   - edds_decoder.py│  - layer_dds_       │
│                  │                    │    reader.py        │
└──────────────────┴────────────────────┴─────────────────────┘
```

---

## Composants détaillés

### 📦 app.py

**Rôle:** Orchestrateur principal, interface Streamlit
**Lignes:** 3641
**Imports métier:**
```python
from base_map import BaseMap
from hypsometric_colormap import HypsometricColormapGenerator
import pipeline_validation as pv
# + 10+ imports dynamiques dans fonctions
```

**Structure:**
```
┌─ Configuration (l.1-90)
│  ├─ Imports, config Streamlit
│  └─ Constantes, CSS personnalisé
│
┌─ Gestion Projets (l.91-684)
│  ├─ CRUD projets JSON
│  ├─ load_project() → charge heightmap + terrain_data
│  ├─ save_project() → persistence complète
│  └─ Gestion cache terrain_data.npz
│
┌─ Session State (l.685-874)
│  ├─ initialize_session()
│  ├─ Cache terrain_data (NPZ + validation version)
│  └─ Variables globales projet/heightmap/reforger
│
┌─ Sidebar (l.875-1485)
│  ├─ Upload heightmap (ASC, PNG, TGA)
│  ├─ Upload satmap (optionnel)
│  ├─ Configuration Reforger (.terr path + catalog.json)
│  └─ Export heightmap (PNG 16-bit, RAW, ASC)
│
└─ Onglets Principaux (l.1486-3641)
   ├─ TAB 1: Terrain
   │  ├─ Hypsométrique (HypsometricColormapGenerator)
   │  ├─ Masques Terrain (Gaea import + Mode B flow/deposit)
   │  └─ Atlas Métrique (stats terrain_data)
   │
   ├─ TAB 2: Satmap Export
   │  └─ Satmap v2.0 (Layer.dds + LRS2 + mode texturé)
   │
   ├─ TAB 3: Génération
   │  ├─ Textures (render_tab_gen_v3)
   │  └─ Végétation (vegetation_map)
   │
   ├─ TAB 4: Validation Masks
   │  ├─ Chargement masks PNG 16-bit
   │  ├─ Analyse QTRE (budget 5-7 textures/bloc)
   │  └─ Nettoyage par priorité
   │
   └─ TAB 5-7: (non détaillés ici)
```

**Fonctions clés:**
```python
load_project(path)                    # Charge projet + heightmap + cache terrain
save_project()                        # Sauvegarde état complet dans project.json
load_terrain_data_cache(...)          # Charge NPZ si version pipeline OK
save_terrain_data_cache(...)          # Sauvegarde NPZ + métadonnées JSON
parse_reforger_world_data(text)       # Parse copier-coller Reforger World Composition
load_merged_library(project_path)     # Fusionne bibliothèques vanilla + custom
```

**État actuel:**
- ✅ **Fonctionnel:** Gestion projets, sidebar, onglets Terrain/Satmap/Validation
- ✅ **Cache terrain_data:** Invalidation automatique selon version pipeline
- ✅ **Pipeline V2/V3:** Génération masques via tab_gen_v3.py
- ✅ **Satmap v2.0:** Lecture Layer.dds + LRS2 + mode texturé
- ⚠️ **Incomplet:** Onglets Terrain Binaire, Correction Terrain, Pipeline Unifié (stubs)

---

### 📦 base_map.py

**Rôle:** Classe BaseMap — couche fondamentale données terrain
**Lignes:** 411
**Import:** Numpy, OpenCV, PIL

**Classe BaseMap:**
```python
class BaseMap:
    """
    Source unique de vérité pour toutes les cartes dérivées.
    Calcule une seule fois : heightmap, slopes, flow, biomes.
    """

    # Données chargées
    heightmap_float: np.ndarray    # Altitudes réelles (m)
    heightmap_uint8: np.ndarray    # Normalisé 0-255 (affichage)
    heightmap_normalized: np.ndarray  # Normalisé 0-1

    # Métadonnées
    altitude_min, altitude_max, altitude_range: float
    width, height: int
    cellsize: float  # m/px (si ASC)

    # Dérivés terrain
    slopes: np.ndarray             # Pentes (degrés, Sobel)
    flow_accum: np.ndarray         # Flow accumulation (proxy multi-échelle)
    water_mask: np.ndarray         # Eau (booléen)
    water_level: float             # Seuil eau (Otsu)
    distance_to_water: np.ndarray  # Distance euclidienne (px)

    # Biomes (7 types hiérarchiques)
    biome_masks: dict[str, np.ndarray]  # bool masks
    COLORS: dict[str, tuple]            # Couleurs BGR
```

**Méthodes:**
```python
__init__(heightmap_path, vertical_exaggeration=10.0)
_load_heightmap(path) → (float32, uint8)
_load_asc_file(path) → (float32, uint8)
_compute_slopes() → np.ndarray
_compute_flow_accum() → np.ndarray
_calculate_water_level() → float  # Otsu threshold
_calculate_distance_to_water() → np.ndarray
_calculate_biome_masks() → dict   # 7 biomes hiérarchiques
get_altitude_at_pixel(x, y) → float
get_biome_at_pixel(x, y) → str
```

**Hiérarchie biomes (ordre priorité):**
1. **Eau** (< seuil_eau)
2. **Sable** (distance_eau < 3px)
3. **Neige** (altitude > tier4 ET pentes < 30°)
4. **Roche** (altitude > tier3 ET pentes > 35°)
5. **Toundra** (tier3 < altitude <= tier4 ET pentes < 35°)
6. **Forêt dense** (altitude < tier3 ET 15° <= pentes <= 40° ET distance_eau < 200px)
7. **Prairie** (altitude < tier2 ET pentes < 15° — FALLBACK)

**État actuel:**
- ✅ **Fonctionnel:** Chargement ASC/PNG 16-bit/8-bit
- ✅ **Slopes:** Calcul Sobel avec vertical_exaggeration
- ✅ **Flow:** Proxy multi-échelle (downsampling si > 1024px)
- ✅ **Biomes:** 7 types avec fallback complet
- ⚠️ **Incomplet:** cellsize non extrait depuis PNG (uniquement ASC)

---

### 📦 hypsometric_colormap.py

**Rôle:** Générateur colormap hypsométrique pure (altitude → couleur)
**Lignes:** 415
**Import:** Numpy, PIL, Scipy, Matplotlib, OpenCV

**Classe HypsometricColormapGenerator:**
```python
class HypsometricColormapGenerator:
    """
    Génère carte colorée basée sur altitudes ABSOLUES.
    Zones fixes (-500m → +3000m) avec couleurs SIG standards.
    """

    heightmap_original: np.ndarray      # Altitudes brutes
    heightmap_normalized: np.ndarray    # 0-1
    h_min, h_max: float
    palette: np.ndarray                 # 256 niveaux BGR
    altitude_zones: list[dict]          # Zones SIG standards
```

**Zones d'altitude ABSOLUES:**
```python
altitude_zones = [
    {"min": -500, "max": 0,    "label": "🌊 Eau/Dépression", "color": (255, 0, 0)},
    {"min": 0,    "max": 100,  "label": "🌾 Plaines basses", "color": (0, 200, 50)},
    {"min": 100,  "max": 300,  "label": "🏞️ Collines",       "color": (0, 255, 255)},
    {"min": 300,  "max": 600,  "label": "🏔️ Montagnes",      "color": (50, 100, 200)},
    {"min": 600,  "max": 1200, "label": "⛰️ Hauts pics",     "color": (0, 50, 255)},
    {"min": 1200, "max": 3000, "label": "❄️ Sommets",        "color": (128, 128, 128)},
]
```

**Méthodes:**
```python
generate(smooth=True) → (Image, colormap_array)
add_hillshading(colormap, strength=0.3) → array
add_enrichment(colormap, tpi_strength=0.18, ...) → array
_compute_tpi_local(window_size=25) → array
_compute_flow_log() → array  # Flow D8 log(1+n)
_compute_depression_mask() → bool_array
save(output_path, add_hillshade=True, add_enrichment=False)
```

**Enrichissement morphologique:**
- **TPI** (Topographic Position Index) : modulation luminosité (crêtes +, creux -)
- **Flow D8** : filets bleutés sur talwegs (top 5%)
- **Dépressions** : teinte cyan sur cavités fermées

**État actuel:**
- ✅ **Fonctionnel:** Génération colormap altitudes absolues
- ✅ **Hillshading:** Ombrage directionnel (lumière 315°, élévation 45°)
- ✅ **Enrichissement:** TPI + Flow D8 + dépressions
- ⚠️ **Obsolescence:** Utilise BaseMap mais incomplet (zones fixes, pas terrain-data)

---

### 📦 terrain_analysis.py

**Rôle:** Calcul centralisé des dérivés terrain (UNE SEULE FOIS)
**Lignes:** 384
**Import:** Numpy, Scipy, pipeline_v2
**Version pipeline:** 2.3.0 (pour invalidation cache)

**Fonction principale:**
```python
def compute_terrain_data(heightmap_path, params=None, progress_callback=None):
    """
    Calcule TOUS les dérivés terrain depuis heightmap.
    Stocké dans session_state['terrain_data'].

    Returns:
        dict {
            # Données brutes
            'heightmap': array float32,
            'heightmap_smooth': array float32,
            'meta': dict (ncols, nrows, cellsize, etc.),
            'cellsize': float,

            # Dérivés terrain
            'slope': array (degrés),
            'curvature_plan': array (normalisé),
            'curvature_profile': array (normalisé),
            'tpi_local': array (normalisé),
            'tpi_macro': array (normalisé),
            'flow': array (normalisé),
            'deposit': array (normalisé),
            'distance_cote': array (mètres),
            'aspect': array (degrés 0-360),
            'roughness': array (normalisé),

            # Paramètres calibrés
            'params': dict,

            # Métadonnées
            'computation_time': float (secondes),
            'timestamp': str (ISO 8601),
            'pipeline_version': str
        }
    """
```

**Pipeline de calcul:**
```
1. load_asc(heightmap_path)                    → heightmap, meta
2. gaussian_filter(heightmap, sigma=32m)       → heightmap_smooth
3. calculate_slope(heightmap, cellsize)        → slope (Sobel)
4. calculate_curvature_zt(...)                 → curvature_plan, curvature_profile
5. calculate_tpi(heightmap_smooth, ...)        → tpi_local, tpi_macro
6. calculate_flow_accumulation(...)            → flow (priority-flood)
7. calculate_deposit(...)                      → deposit (TPI multi-échelle)
8. calculate_coastal_distance(...)             → distance_cote
9. calculate_aspect(heightmap_smooth, ...)     → aspect
10. calculate_roughness(heightmap_smooth, ...) → roughness
11. auto_calibrate(heightmap, slope, flow)     → params
```

**Paramètres auto-calibrés:**
```python
params = {
    "coastal_alt_max_m": float,     # Seuil altitude côtière (percentile)
    "grass_low_max_m": float,       # Altitude max grass low (p30)
    "grass_mid_max_m": float,       # Altitude max grass mid (p60)
    "grass_high_max_m": float,      # Altitude max grass high (p85)
    "debris_min_deg": float,        # Pente min debris (p70)
    "rock_min_deg": float,          # Pente min rock (p90)
    "tpi_local_radius_m": 100.0,
    "tpi_macro_radius_m": 500.0,
    "flow_threshold": float,
}
```

**État actuel:**
- ✅ **Fonctionnel:** Calcul complet 11 dérivés + auto-calibration
- ✅ **Cache NPZ:** Sauvegarde/chargement avec invalidation version pipeline
- ✅ **Progress callback:** Retour progression pour UI
- ⚠️ **Version pipeline:** v2.3.0 (flow post-traitement + deposit TPI multi-échelle)

---

### 📦 pipeline_validation.py

**Rôle:** Validation et nettoyage masques terrain (fonctions pures)
**Lignes:** 945
**Import:** Numpy, OpenCV, Pathlib, Re

**Fonctions principales:**
```python
# 1. Chargement
load_masks_from_paths(file_paths, max_size=None) → dict
    # Retourne: {'masks': list, 'paths': list, 'shape': tuple, 'errors': list}

# 2. Analyse conflits
build_conflict_stack(masks, threshold=0.15) → (stack_bool, threshold)
analyze_conflicts_qtre(masks, cellsize=4.0, threshold=0.05, budget_max=5) → dict
    # Budget QTRE configurable : 5 (défaut), 7 (Zimnitrita)
    # Retourne: heatmap, critical_blocs, limit_blocs, ok_blocs, verdict

# 3. Nettoyage
clean_masks_by_priority(masks, priority_order, ...) → dict
    # Atténuation progressive textures moins prioritaires
    # Normalisation finale pour somme <= 1.0

# 4. Assemblage
assemble_masks(masks, mode='homogeneous', ordered_indices=None) → array
    # Modes: 'max', 'add', 'average', 'priority', 'union_white'

clean_masks_by_order(masks, paths, blend_mode=True) → list

# 5. Reforger errors
load_reforger_errors(file_paths, target_shape) → bool_mask
compute_combined_heatmap(masks, reforger_error_mask, threshold=0.15) → dict
    # Rouge=QTRE seul, Magenta=QTRE+Reforger, Cyan=Reforger seul

# 6. Correction
correct_magenta_zones(masks, heatmap_rgb) → list
    # Garde seulement masque dominant sur pixels magenta

# 7. Export
export_cyan_coords_csv(cyan_mask, meter_per_px) → str
export_masks_png(masks, paths, output_dir, suffix='_noconflict') → list
```

**Analyse QTRE:**
```python
# Budget QTRE par bloc 32m
budget_max = 5  # Défaut (sûr)
budget_max = 7  # Zimnitrita (limite haute)

# Résultats
{
    'critical_blocs': int,  # > budget_max (CRASH Reforger)
    'limit_blocs': int,     # == budget_max (risque)
    'ok_blocs': int,        # < budget_max (sûr)
    'verdict': "OK" | "ATTENTION"
}
```

**État actuel:**
- ✅ **Fonctionnel:** Chargement PNG 16-bit, analyse QTRE, nettoyage par priorité
- ✅ **Budget configurable:** Permet Zimnitrita (7 textures/bloc)
- ✅ **Heatmap combinée:** QTRE + erreurs Reforger
- ✅ **Tests unitaires:** 10 tests basiques (fin de fichier)
- ⚠️ **Deprecated:** `analyze_conflicts()` (pixel-wise) remplacé par `analyze_conflicts_qtre()`

---

### 📦 tab_gen_v3.py

**Rôle:** Onglet Génération Pipeline V3 (intégré dans app.py)
**Lignes:** 604
**Import:** Streamlit, Numpy, OpenCV, PIL, pipeline_v3

**Fonction principale:**
```python
def render_tab_gen_v3():
    """
    Point d'entrée appelé depuis app.py dans with _g_textures.
    Génère 13+ masques terrain depuis heightmap + masques Gaea.
    """
```

**Pipeline V3:**
```python
# 1. Sources Gaea (auto-détection + upload manuel)
sources = {
    "flow": gaea/flow.png | upload,
    "deposit": gaea/deposit.png | upload,
    "exclusion": gaea/exclusion.png | upload (optionnel)
}

# 2. Enrichissement slope (fBm)
modes = ["slope_perturb", "domain_warp", "additive", "Désactivé"]
params = {"amplitude": 8.0, "scale": 0.008, "octaves": 6}

# 3. Génération masques
output_4k = [
    "mask_landes_rocheuses.png",
    "mask_rock.png",
    "mask_seabed.png",
    "mask_coastal_flat.png",
    "mask_coastal_slope.png",
    "mask_flow.png",
    "mask_deposit.png",
    # + 7 masques végétation
    "mask_foret_coniferes.png",
    "mask_foret_feuillue.png",
    "mask_maquis_landes.png",
    "mask_landes_plateau.png",
    "mask_prairie_humide.png",
    "mask_prairie_seche.png",
    "mask_alpages.png",
]

# 4. Post-processing
- Stretch auto (p2-p98)
- Weight min (0.10)
- Cut_low flow/deposit
- Gamma flow/deposit

# 5. Normalisation exclusive (QTRE)
- Budget 5-7 textures/bloc
- Analyse QTRE
- Renommage avec préfixe ordre d'insertion (01_, 02_, ...)
```

**État actuel:**
- ✅ **Fonctionnel:** Génération complète 13+ masques 4K PNG 16-bit
- ✅ **Mode B:** Calcul flow/deposit depuis heightmap (fallback terrain_data)
- ✅ **Végétation:** 7 masques depuis végétation potentielle
- ✅ **QTRE:** Analyse + carte heatmap
- ✅ **Sauvegarde:** project.json + préfixe numérique

---

### 📦 vegetation_map.py

**Rôle:** Génération carte végétation potentielle (16 types)
**Lignes:** ~800 (estimé depuis extrait)
**Import:** Numpy, PIL, Scipy

**Types de végétation (16):**
```python
VEGETATION_TYPES = {
    "foret_feuillue": "Forêt feuillue dense",
    "foret_clearing_deciduous": "Forêt feuillue clairsemée",
    "foret_pins": "Forêt de pins",
    "foret_coniferes": "Forêt de conifères dense",
    "foret_clearing_coniferous": "Forêt de conifères clairsemée",
    "maquis_landes": "Maquis / Landes",
    "landes_plateau": "Landes de plateau",
    "haies_lisieres": "Haies / Lisières",
    "prairie_humide": "Prairie humide",
    "prairie_seche": "Prairie sèche",
    "prairie_plateau": "Prairie de plateau",
    "alpages": "Alpages",
    "roseaux_marais": "Roseaux / Marais",
    "ripisylve": "Ripisylve",
    "veg_rupestre": "Végétation rupestre",
    "landes_rocheuses": "Landes rocheuses",
}
```

**Fonctions:**
```python
compute_vegetation_scores(
    heightmap, slope, curvature, tpi_local, tpi_macro,
    flow, aspect, distance_cote, params, cellsize
) → dict {type_veg: array_float32 [0-1]}

render_vegetation_rgb(scores, heightmap, min_score=0.05, blend=True) → rgb_array

export_vegetation_png(rgb, output_path)
export_vegetation_masks(scores, output_dir, min_score=0.1) → dict {type: path}

compute_vegetation_stats(scores, cellsize, min_score) → dict
```

**Calcul scores (multi-facteurs):**
```python
# Facteurs de base
alt_pine = _bell(heightmap, 0, 250, slope=40)
alt_deciduous = _bell(heightmap, 150, 400, slope=50)
flat = np.clip(1 - slope / debris_min, 0, 1)
north_f = np.clip((cos(aspect) + 1) / 2, 0, 1)
humid = np.clip(flow * 0.6 + (1 - dist_w_norm) * 0.4, 0, 1)

# Combinaison par type (exemples)
scores["foret_feuillue"] = (
    alt_deciduous * gentle * humid * north_f * land
)
scores["prairie_humide"] = (
    alt_low * flat * humid * tpi_neg * land
)
```

**État actuel:**
- ✅ **Fonctionnel:** Calcul 16 scores végétation depuis terrain_data
- ✅ **Export:** PNG aperçu + 16 masques PNG 16-bit
- ✅ **Statistiques:** Couverture par type (ha, %)
- ✅ **Intégration:** Appelé depuis tab_gen_v3.py
- ⚠️ **Adaptation:** Zones altitudinales calibrées pour Zimnitrita (0-500m)

---

### 📦 pipeline_v2.py

**Rôle:** Pipeline complet génération masques terrain
**Lignes:** ~2000+ (estimé)
**Import:** Numpy, Scipy, OpenCV, Matplotlib

**Fonctions de calcul terrain:**
```python
load_asc(path) → (heightmap, meta)
calculate_slope(heightmap, cellsize) → slope
calculate_aspect(heightmap, cellsize) → (aspect, humidity)
calculate_curvature_zt(heightmap, cellsize) → (curvature_profile, curvature_plan)
calculate_tpi(heightmap, cellsize, r_local, r_macro) → (tpi_local, tpi_macro)
calculate_flow_accumulation(heightmap, cellsize) → flow
calculate_deposit(heightmap_smooth, flow, cellsize) → deposit
calculate_coastal_distance(heightmap, cellsize) → distance_cote
calculate_roughness(heightmap, cellsize) → roughness
auto_calibrate(heightmap, slope, flow, params) → params_calibrated
```

**Génération masques:**
```python
generate_mask_coastal(distance_cote, heightmap, ...) → mask_coastal
generate_mask_grass(heightmap, slope, ...) → masks_grass (low/mid/high)
generate_mask_debris(slope, heightmap, ...) → mask_debris
generate_mask_rock(slope, heightmap, ...) → mask_rock
generate_mask_mud_river(flow, tpi_local, ...) → mask_mud_river
generate_mask_forest(heightmap, slope, aspect, ...) → mask_forest
```

**Post-processing:**
```python
apply_output_curve(mask, gamma=1.0, cut_low=0.0, cut_high=1.0) → mask
feather_edges(mask, distance_m, cellsize) → mask
normalize_stack(masks, priority_order) → masks_normalized
```

**État actuel:**
- ✅ **Fonctionnel:** Calcul dérivés terrain + génération masques
- ✅ **Flow accumulation:** Priority-flood optimisé
- ✅ **Deposit:** TPI multi-échelle
- ✅ **Auto-calibration:** Seuils adaptatifs depuis percentiles
- ⚠️ **Version pipeline:** v2.3.0 (flow post-traitement + deposit)

---

### 📦 app_config.py

**Rôle:** Configuration persistante addon Reforger
**Lignes:** 132
**Import:** JSON, Pathlib

**Fonctions:**
```python
save_config(addon_path) → None
load_config() → str  # Chemin addon

resolve_paths(addon_path) → dict
    # Retourne structure complète depuis addon_path
    {
        "valid": bool,
        "addon_path": str,
        "terrain_dir": str,
        "data_dir": str,          # .Data/
        "editor_dir": str,        # .EditorData/
        "terr_file": str,
        "num_tiles": int,
        "grid_size": int,
        "world_name": str,
    }
```

**Structure attendue:**
```
addon_path/
└── World/
    └── [nom_monde]/
        └── Terrain/
            ├── [nom_monde].terr
            ├── .Data/          (Terrain_N.ttile, Terrain_N_layer.edds)
            └── .EditorData/    (Terrain_N.bterr, Terrain_N_layer.dds)
```

**État actuel:**
- ✅ **Fonctionnel:** Détection auto arborescence Reforger
- ✅ **Fallback:** Recherche récursive si structure non standard
- ✅ **Validation:** Vérification .Data/ et .EditorData/
- ✅ **Sauvegarde:** Persistence dans config.json

---

### 📦 Modules secondaires

**mask_utils.py**
- Utilitaires manipulation masques Gaea
- `scan_gaea_folder()` : détection PNG + conversion float32
- `apply_mask_profile()` : application profils (flow, deposit, exclusion)
- `load_and_normalize_mask()` : chargement PNG → float32 [0-1]

**satmap_v2_generator.py**
- Générateur satmap v2.0 (mode couleurs)
- Lecture Layer.dds depuis .EditorData/
- Parse chunk LRS2 depuis .Data/.ttile
- Downscale résolution (4K, 8K, 16K)

**satmap_v2_textured.py**
- Générateur satmap v2.0 (mode texturé)
- Lecture textures middle BCR depuis catalog.json
- Rendu tuilé avec blending
- 100% couverture, 1-7 textures/bloc

**emat_scanner_simple.py**
- Scanner fichiers .emat Reforger
- Extraction couleurs BCR
- Enrichissement catalog.json

**reforger_texture_budget.py**
- Parse .terr → liste matériaux
- Budget textures QTRE
- Analyse blocs 32m

**edds_decoder.py, layer_dds_reader.py, lrs2_parser.py**
- Décodage formats Reforger propriétaires
- EDDS : DDS encapsulé (header 16 bytes)
- LRS2 : Chunk matériaux par bloc

---

## État d'implémentation global

### ✅ Fonctionnel complet

| Module | État | Dépendances | Tests |
|--------|------|-------------|-------|
| app.py | ✅ Production | base_map, terrain_analysis, tab_gen_v3 | Manuel |
| base_map.py | ✅ Stable | numpy, opencv | Démo intégrée |
| terrain_analysis.py | ✅ Production | pipeline_v2 | Tests CLI |
| pipeline_validation.py | ✅ Production | numpy, opencv | 10 tests unitaires |
| tab_gen_v3.py | ✅ Production | pipeline_v3, vegetation_map | Intégré app.py |
| vegetation_map.py | ✅ Production | terrain_analysis | Intégré |
| pipeline_v2.py | ✅ Production | numpy, scipy, opencv | Tests CLI |
| app_config.py | ✅ Stable | - | Tests fonctionnels |

### ⚠️ Partiellement implémenté

| Module | Manques | TODO |
|--------|---------|------|
| hypsometric_colormap.py | Zones fixes, pas terrain-data | Migration vers params auto-calibrés |
| mask_utils.py | Profils limités | Ajouter profils curvature, sediment |

### ❌ Incomplet / Stubs

| Feature | État | Onglet app.py |
|---------|------|---------------|
| Terrain Binaire | Stub vide | TAB 5 |
| Correction Terrain | Stub vide | TAB 6 |
| Pipeline Unifié | Stub vide | TAB 7 |

---

## Dépendances entre modules

```
app.py
├── base_map.py
│   └── (aucune dépendance locale)
│
├── hypsometric_colormap.py
│   └── (aucune dépendance locale)
│
├── terrain_analysis.py
│   └── pipeline_v2.py
│       └── (numpy, scipy, opencv)
│
├── tab_gen_v3.py
│   ├── pipeline_v3.py
│   │   └── vegetation_map.py
│   │       └── terrain_analysis.py
│   └── mask_utils.py
│
├── pipeline_validation.py
│   └── (numpy, opencv)
│
├── satmap_v2_textured.py
│   ├── satmap_v2_generator.py
│   ├── layer_dds_reader.py
│   └── emat_scanner_simple.py
│
└── app_config.py
    └── (json, pathlib)
```

---

## Formats de données

### Stockage projet (project.json)

```json
{
  "version": "1.1",
  "created_at": "2026-08-01T14:30:00",
  "updated_at": "2026-08-02T10:15:00",
  "project": {
    "name": "Zimnitrita",
    "author": "[otea] Giorbev",
    "description": "Île méditerranéenne 16km",
    "tags": []
  },
  "sources": {
    "heightmap": "sources/zimnitrita_16k.asc",
    "satmap": "sources/satmap_aerial.png",
    "it_masks_dir": "sources/instant_terra/"
  },
  "assets": {
    "heightmap": {
      "filename": "zimnitrita_16k.asc",
      "format": "asc",
      "cellsize": 4.0,
      "width": 4097,
      "height": 4097,
      "alt_min": 0.0,
      "alt_max": 487.0
    }
  },
  "reforger_grid": {
    "tiles": [4, 4],
    "blocks_per_tile": [4, 4],
    "block_size_m": [32, 32],
    "planar_resolution_m": 4.0,
    "height_min_m": 0.0,
    "height_max_m": 487.0
  },
  "pipeline_v2": {
    "params": { /* sliders */ },
    "params_auto": { /* auto-calibrés */ },
    "output_dir": "exports_mask/",
    "base_texture": "Grass_03",
    "qtre_verdict": "OK"
  },
  "modules": {
    "terrain_preview": {
      "climate_profile": "tempere",
      "max_slots": 4,
      "snow_pct": 92
    }
  }
}
```

### Cache terrain_data (NPZ + JSON)

```
cache/
├── terrain_data.npz       # Arrays numpy compressés
└── terrain_meta.json      # Métadonnées + version pipeline
```

**terrain_meta.json:**
```json
{
  "meta": {"ncols": 4097, "nrows": 4097, "cellsize": 4.0},
  "cellsize": 4.0,
  "params": { /* auto-calibrés */ },
  "computation_time": 45.3,
  "timestamp": "2026-08-02T10:15:00",
  "heightmap_path": "H:/path/to/heightmap.asc",
  "pipeline_version": "2.3.0"
}
```

---

## Points d'attention

### 🔴 Critique

1. **Cache terrain_data invalidation**: Version pipeline doit être incrémentée à chaque modification des algorithmes
2. **QTRE budget**: Respecter 5 textures/bloc (7 max Zimnitrita) pour éviter crashs Reforger
3. **Normalisation masks**: Somme poids <= 1.0 par pixel (QTRE strict)

### 🟠 Important

1. **Cellsize extraction**: Base_map ne lit pas cellsize depuis PNG (uniquement ASC)
2. **Flow accumulation**: Downsampling si > 1024px (approximation)
3. **Biomes hiérarchie**: Fallback prairie pour pixels non classifiés

### 🟡 Amélioration

1. **Hypsometric zones**: Migration zones fixes → params auto-calibrés
2. **Pipeline unifié**: Onglets Terrain Binaire/Correction/Pipeline vides
3. **Tests unitaires**: Manquent pour base_map.py, hypsometric_colormap.py

---

## Roadmap technique

### Phase 1 — Consolidation (priorité 1)
- [ ] Migrer hypsometric_colormap.py vers params auto-calibrés
- [ ] Implémenter extraction cellsize depuis PNG (métadonnées exif/tiff)
- [ ] Ajouter tests unitaires pour base_map.py

### Phase 2 — Complétion features (priorité 2)
- [ ] Implémenter onglet Terrain Binaire (export .ttile)
- [ ] Implémenter onglet Correction Terrain (édition manuelle masks)
- [ ] Implémenter onglet Pipeline Unifié (orchestration complète)

### Phase 3 — Optimisation (priorité 3)
- [ ] Cache partiel terrain_data (recalcul sélectif)
- [ ] Parallélisation calculs (multiprocessing)
- [ ] Downgrade optionnel résolution (économie RAM)

---

## Conclusion

Map Generator Pro v5.1 est une application **mature et fonctionnelle** pour la génération de cartes Reforger. L'architecture modulaire permet :
- Réutilisation des calculs terrain (cache NPZ)
- Pipeline flexible (v2/v3 coexistent)
- Validation QTRE stricte (évite crashs Reforger)

**Points forts:**
- Séparation claire données/logique métier
- Cache intelligent avec invalidation version
- Pipeline complet heightmap → export Reforger

**Points à améliorer:**
- Compléter onglets stubs (Terrain Binaire, Correction)
- Migration hypsometric vers params auto-calibrés
- Tests unitaires (couverture actuelle ~30%)

**Maturité estimée:** 75% production-ready
**Dette technique:** Modérée (stubs, tests manquants)
**Qualité code:** Bonne (documentation, séparation concerns)
