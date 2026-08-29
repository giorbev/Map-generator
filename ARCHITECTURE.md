# Architecture — Map Generator Pro v7.0

> Documentation de la structure actuelle de l'application  
> Date : 2026-08-29  
> Version : 7.0 (PyWebView desktop)

---

## 📋 Vue d'ensemble

**Map Generator Pro** est une application desktop native (PyWebView) pour générer et manipuler des terrains Arma Reforger.

### Technologies
- **Backend** : Python 3.x + PyWebView
- **Frontend** : HTML/CSS/JavaScript pur (pas de framework)
- **Communication** : API exposée via `window.pywebview.api.*`

### Point d'entrée
```bash
python main.py
```

---

## 🏗️ Structure des dossiers

```
Map generator/
├── main.py                      # Point d'entrée application
├── config.json                  # Configuration persistante (chemin addon)
├── *.py                         # 19 scripts Python (backend)
│
├── web/                         # Interface utilisateur (frontend)
│   ├── accueil_preview.html     # Page d'accueil animée
│   ├── projects.html            # Gestion des projets
│   ├── navigation_preview.html  # Menu principal
│   ├── terrain.html             # Onglet Heightmap
│   ├── inspection.html          # Onglet Inspection tuiles
│   ├── generation.html          # Onglet Pipeline V5
│   ├── satmap.html              # Onglet Satmap v2
│   ├── corrections.html         # Onglet Corrections
│   ├── help.html                # Documentation
│   └── log_panel.js             # Module JS partagé (logs)
│
└── data/
    ├── projects/                # Projets utilisateur
    └── Textures_ArmaReforger/   # Catalogue textures
        ├── catalog.json         # Métadonnées textures
        ├── biomes_presets.json  # Presets biomes
        └── texture_mapping.json # Mapping masques → textures
```

---

## 🧩 Scripts Python — Organisation fonctionnelle

### 🏗️ CORE / INFRASTRUCTURE (3 scripts)

| Script | Lignes | Rôle |
|--------|--------|------|
| **main.py** | **1405** | **Point d'entrée** — Fenêtre PyWebView + API Python exposée au JS |
| app_config.py | 168 | Configuration persistante (chemin addon dans config.json) |
| project_manager.py | 278 | Gestion surfaces.json (matériaux depuis .terr) |

#### main.py — API exposée au JavaScript

```python
class Api:
    # Projets
    def list_projects() -> list
    def create_project(name, author, description) -> dict
    def load_project(project_path) -> dict
    def delete_project(project_path) -> dict
    
    # Navigation
    def navigate(tab)           # Charge un onglet
    def go_navigation()         # Menu principal
    def go_projects()           # Page projets
    def go_accueil()            # Page accueil
    
    # Terrain
    def get_paths() -> dict
    def pick_file(key, extensions) -> dict
    def pick_folder(key) -> dict
    def get_terrain_stats() -> dict
    def gen_hypsometric(hillshade, enrichment) -> dict
    
    # Inspection
    def get_qtre_cache() -> dict
    def scan_tiles() -> dict
    def inspect_tile(tx, ty) -> dict
    
    # Pipeline V5 (génération)
    def get_generation_data() -> dict
    def apply_biome_preset(biome_key) -> dict
    def auto_calibrate_params(biome_key) -> dict
    def save_mask_mapping(mask_config, default_mat) -> dict
    def run_pipeline_preview(params, mask_config, default_mat) -> dict
    def export_masks_png() -> dict
    
    # Satmap
    def check_satmap_catalog() -> dict
    def scan_emat() -> dict
    def generate_satmap_v2(resolution, middles_dir) -> dict
    def run_kmeans_classifier(satmap_path, n_clusters, reuse)
    
    # Corrections
    def corrections_scan_global(threshold) -> dict
    def corrections_scan_zone(mask_path) -> dict
    def corrections_inspect_tile(tx, ty, mode) -> dict
    def corrections_terrain_health() -> dict
    
    # Logs
    def get_log() -> list
    def clear_log() -> dict
```

---

### 🗺️ LECTURE FORMATS REFORGER (5 scripts)

| Script | Lignes | Rôle | Format lu |
|--------|--------|------|-----------|
| terrain_terr_reader.py | 96 | Lit chunk MATS du .terr | `.terr` |
| edds_decoder.py | 753 | Décode textures compressées LZ4 | `.edds` |
| lrs2_parser.py | 271 | Parse chunk LRS2 (matériaux par bloc) | `.ttile` |
| layer_dds_reader.py | 161 | Lit poids GPU R32_UINT 512×512 | `layer.dds` |
| reforger_emat_parser.py | 383 | Parse fichiers matériaux texte | `.emat` |

#### Formats Arma Reforger / Enfusion

```
.terr        → Fichier terrain (chunk MATS = liste matériaux)
.ttile       → Tuile terrain (chunk LRS2 = matériaux par bloc 4×4)
.edds        → Texture compressée (format DDS + compression LZ4/COPY)
layer.dds    → Poids GPU par texture (R32_UINT, 512×512, non compressé)
.emat        → Matériau texte (références textures BCR, MiddleScaleUV, Color)
```

#### Dépendances de lecture

```
satmap_v2_generator.py
├─ edds_decoder.py         (lecture GPU)
├─ lrs2_parser.py          (matériaux par bloc)
├─ layer_dds_reader.py     (poids GPU)
└─ terrain_terr_reader.py  (liste matériaux)

clean_weights.py
├─ edds_decoder.py
├─ terrain_terr_reader.py
└─ lrs2_parser.py

project_manager.py
└─ terrain_terr_reader.py
```

---

### ⛰️ CALCUL TERRAIN (3 scripts)

| Script | Lignes | Rôle |
|--------|--------|------|
| **terrain_algorithms.py** | **557** | **Algorithmes géomorphologiques** (flow, TPI, curvature, fBm) |
| terrain_analysis.py | 383 | Calcul centralisé + cache `.npz` (version pipeline 2.3.0) |
| hypsometric_colormap.py | 414 | Génère cartes hypsométriques (altitude + hillshade) |

#### Signaux terrain calculés

```python
# terrain_algorithms.py
def calculate_slope(heightmap, cellsize)           # Pente (%)
def calculate_curvature(heightmap, cellsize)       # Courbure (concave/convexe)
def calculate_tpi(heightmap, radius)               # Topographic Position Index
def calculate_flow_accumulation(heightmap)         # Accumulation flux hydro
def generate_coastal_mask(heightmap, threshold)    # Zones côtières
def apply_fbm_noise(size, octaves, persistence)    # Bruit fractal

# terrain_analysis.py
compute_terrain_data(heightmap_path, params)
→ Retourne dict avec tous les signaux + cache NPZ
→ Version pipeline : 2.3.0 (invalide cache si version change)
```

---

### 🎨 PIPELINE TEXTURE (4 scripts — CŒUR FONCTIONNEL)

| Script | Lignes | Rôle | Statut |
|--------|--------|------|--------|
| **pipeline_v5.py** | **1672** | **Pipeline complet** : calcul masques + budget QTRE + export | **ACTIF** |
| tab_pipeline_v5.py | 1231 | Interface Streamlit (legacy) | **OBSOLÈTE** |
| pipeline_validation.py | 944 | Validation masques (conflits, trous, stats) | ACTIF |
| clean_weights.py | 2117 | Écriture directe .ttile (masques → GPU) | CLI seul |

#### Pipeline V5 — Workflow

```
1. Lecture heightmap (.asc)
2. Calcul signaux terrain (slope, fBm, coastal, flow, deposit)
3. Génération masques base (seabed, coastal, rock, landes, flow, deposit)
4. Génération masques végétation (prairie, maquis, alpages, forêts)
5. Application masque exclusion (Zone B préservée)
6. Normalisation exclusive (vectorisée)
7. Arbitrage budget par bloc (max 4-5 tex/bloc pour QTRE)
8. Visualisation carte colorisée (satmap-like)
9. Export masques PNG OU écriture .ttile
```

#### Contraintes QTRE (Quad-Tree)

```
✅ Max 4-5 textures/bloc (6 = crash Workbench)
✅ Normalisation exclusive (sum = 65535 par pixel)
✅ Budget dynamique par bloc (arbitrage priorités)
✅ Zone B préservée (textures existantes intactes)
```

---

### 🗺️ SATMAP (Cartes texturées) (3 scripts)

| Script | Lignes | Rôle |
|--------|--------|------|
| satmap_v2_generator.py | 396 | Génère satmap depuis .edds + LRS2 (lecture GPU) |
| satmap_v2_textured.py | 503 | Version enrichie (textures middles, gamma, scaling) |
| satmap_classifier.py | 671 | Classification K-means (couleurs → masques terrain) |

#### Satmap V2 — Pipeline

```
1. Scan dossier editordata/ (layer.edds + .ttile par tuile)
2. Lecture poids GPU (edds_decoder.py)
3. Lecture matériaux par bloc (lrs2_parser.py)
4. Chargement textures middles (.edds RGB)
5. Composition par bloc (blending poids GPU)
6. Correction gamma + scaling
7. Export PNG haute résolution (4097×4097)
```

---

### 🌲 VÉGÉTATION (1 script — Roadmap)

| Script | Lignes | Rôle | Statut |
|--------|--------|------|--------|
| vegetation_map.py | 635 | Génère carte végétation potentielle (scores par type) | **Non intégré UI** |

#### Types de végétation supportés

```python
VEGETATION_TYPES = {
    "foret_feuillue": {...},    # Forêt dense (deciduous)
    "foret_conifere": {...},    # Forêt conifères
    "maquis": {...},            # Maquis méditerranéen
    "prairie": {...},           # Prairies
    "alpages": {...},           # Zones alpines
    "landes": {...},            # Landes rocheuses
}
```

**Action nécessaire** : Ajouter méthode API dans main.py + page HTML vegetation.html

---

## 🔄 Graphe de dépendances

### Scripts indépendants (pas d'imports locaux)

```
terrain_terr_reader.py
edds_decoder.py
lrs2_parser.py
layer_dds_reader.py
reforger_emat_parser.py
terrain_algorithms.py
hypsometric_colormap.py
satmap_classifier.py
vegetation_map.py
app_config.py
```

### Scripts orchestrateurs (importent d'autres scripts)

```
main.py
├─ terrain_analysis.py
├─ hypsometric_colormap.py
├─ pipeline_v5.py
├─ satmap_v2_generator.py
├─ pipeline_validation.py
└─ reforger_emat_parser.py

pipeline_v5.py
└─ terrain_algorithms.py

satmap_v2_generator.py
└─ satmap_v2_textured.py
    ├─ edds_decoder.py
    ├─ lrs2_parser.py
    ├─ layer_dds_reader.py
    └─ terrain_terr_reader.py

clean_weights.py
├─ terrain_terr_reader.py
├─ edds_decoder.py
└─ lrs2_parser.py

project_manager.py
└─ terrain_terr_reader.py
```

---

## 🌐 Interface utilisateur — Pages HTML

| Page | Onglet correspondant | Méthodes API principales |
|------|---------------------|--------------------------|
| accueil_preview.html | — | Branding, logo, animation |
| projects.html | — | list_projects, create_project, load_project, delete_project |
| navigation_preview.html | — | Menu principal (6 onglets) |
| terrain.html | Heightmap | get_paths, pick_file, get_terrain_stats, gen_hypsometric |
| inspection.html | Inspection | get_qtre_cache, scan_tiles, inspect_tile |
| generation.html | Pipeline V5 | get_generation_data, run_pipeline_preview, export_masks_png |
| satmap.html | Satmap | check_satmap_catalog, scan_emat, generate_satmap_v2 |
| corrections.html | Corrections | corrections_scan_global, corrections_scan_zone |
| help.html | Aide | Documentation utilisateur |

### Communication Frontend ↔ Backend

```javascript
// Depuis le HTML (JavaScript)
const result = await pywebview.api.list_projects();
const stats = await pywebview.api.get_terrain_stats();
const preview = await pywebview.api.run_pipeline_preview(params, config, mat);

// Toutes les méthodes retournent des Promises
// Format retour : { ok: true/false, ...data }
```

### Module partagé : log_panel.js

```javascript
// Inclus dans tous les HTML (sauf accueil_preview.html)
// Affiche panneau de logs en temps réel
// Appelle pywebview.api.get_log() toutes les 2 secondes
```

---

## 📊 Scripts par priorité fonctionnelle

### ✅ CRITIQUES (l'app ne fonctionne pas sans)

```
main.py                    ← Point d'entrée
terrain_algorithms.py      ← Calculs terrain
pipeline_v5.py             ← Génération masques
terrain_terr_reader.py     ← Lecture .terr
edds_decoder.py            ← Lecture .edds
lrs2_parser.py             ← Lecture .ttile
layer_dds_reader.py        ← Lecture layer.dds
satmap_v2_generator.py     ← Satmap
satmap_v2_textured.py      ← Satmap enrichie
```

### ⚪ OPTIONNELS (fonctionnalités secondaires)

```
hypsometric_colormap.py    ← Onglet Terrain → cartes
pipeline_validation.py     ← Onglet Corrections
satmap_classifier.py       ← Onglet Satmap → K-means
reforger_emat_parser.py    ← Onglet Satmap → scan matériaux
project_manager.py         ← Gestion surfaces.json
app_config.py              ← Config persistante
terrain_analysis.py        ← Cache terrain (fallback si absent)
```

### 🔵 NON INTÉGRÉS (standalone / roadmap)

```
clean_weights.py           ← CLI : écriture .ttile
vegetation_map.py          ← Roadmap : onglet Végétation
tab_pipeline_v5.py         ← LEGACY Streamlit (à supprimer)
```

---

## 🗄️ Fichiers de données

### Catalogue textures Reforger

```json
// data/Textures_ArmaReforger/catalog.json
{
  "Grass_01": {
    "middle_path": "Terrains/.../Grass_01_BCR_middle.edds",
    "middle_scale": 100.0,
    "color_srgb": [r, g, b],
    "biome": ["temperate", "continental"],
    ...
  }
}
```

### Presets biomes

```json
// data/Textures_ArmaReforger/biomes_presets.json
{
  "ile_mediterraneenne": {
    "label": "Île méditerranéenne",
    "params": { ... },
    "masks": [
      { "name": "seabed", "texture": "Seabed_01", "priority": 1 },
      ...
    ]
  }
}
```

### Configuration projet

```json
// data/projects/<projet>/project.json
{
  "version": "1.2",
  "project": {
    "name": "Zbk_island",
    "author": "...",
    "description": "..."
  },
  "paths": {
    "heightmap": "inputs/heightmap/",
    "addon_reforger": "I:/Reforger_addons travail/...",
    ...
  },
  "modules": {
    "terrain_preview": {
      "climate_profile": "tempere",
      "snow_percentile": 95,
      "flow_percentile": 85
    }
  }
}
```

---

## 🚀 Workflow utilisateur type

```
1. Lancer app : python main.py
2. Page accueil → "Gérer mes projets"
3. Créer/charger projet → Menu principal (6 onglets)

4. Onglet Heightmap
   → Import heightmap (.asc/.png/.tif)
   → Génération carte hypsométrique
   → Stats terrain (dénivelé, % terre/mer)

5. Onglet Pipeline V5
   → Choix preset biome
   → Auto-calibration paramètres
   → Mapping masques → textures
   → Génération preview
   → Export PNG ou .ttile

6. Onglet Satmap
   → Scan matériaux (.emat)
   → Génération satmap v2 (4097×4097)
   → Classification K-means (optionnel)

7. Onglet Inspection
   → Scan tuiles QTRE
   → Inspection détaillée par tuile
   → Vérification budget textures

8. Onglet Corrections
   → Scan conflits masques
   → Analyse zones problématiques
   → Diagnostic santé terrain
```

---

## 📚 Ressources et références

### Formats Enfusion

- **IFF (Interchange File Format)** : Format chunks (4 bytes ID + 4 bytes size)
- **MATS** : Chunk liste matériaux dans .terr
- **LRS2** : Chunk Layer Resources v2 dans .ttile
- **EDDS** : DDS + compression LZ4/COPY (table mips @ offset variable)
- **QTRE** : Quad-Tree encoding (max 6 textures/bloc = limite hard)

### Mémoires projet

- `project_pipeline_7_masques.md` : Pipeline 7 masques optimisé QTRE (actuel)
- `reference_reforger_constraints.md` : Contraintes QTRE, seuils calibrés
- `reference_crash_solutions.md` : Solutions crashs Workbench
- `feedback_workbench_limits.md` : Limites RAM/VRAM Workbench

---

## 🔮 Roadmap / Améliorations futures

### Court terme (optimisations)

- [ ] Supprimer `tab_pipeline_v5.py` (legacy Streamlit)
- [ ] Externaliser `log_panel.js` (éviter duplication HTML)
- [ ] Documenter dépendances (`requirements.txt` à jour)

### Moyen terme (modules)

- [ ] Module `reforger_io.py` : Centraliser lecteurs formats
- [ ] Fusionner `satmap_v2_generator.py` + `satmap_v2_textured.py`
- [ ] Intégrer `vegetation_map.py` dans UI (nouvelle page HTML)

### Long terme (refactoring)

- [ ] Module `terrain_core.py` : Unifier traitement terrain
- [ ] Cache terrain unifié (réutilisation entre modules)
- [ ] Tests unitaires (lecteurs formats, algorithmes terrain)

---

## 📝 Notes de maintenance

### Versions pipeline

```
terrain_analysis.py  : TERRAIN_PIPELINE_VERSION = "2.3.0"
project.json         : "version": "1.2"
```

**Important** : Incrémenter version pipeline force recalcul cache (invalide `.npz` obsolètes)

### Conventions de nommage

```
Masques terrain     : snake_case (seabed, coastal, rock)
Textures Reforger   : PascalCase (Grass_01, Dirt_02)
Matériaux .emat     : PascalCase + .emat (Surface_Grass_01.emat)
Fichiers Python     : snake_case.py
Fichiers HTML       : snake_case.html
```

### Structure projet utilisateur

```
data/projects/<nom_projet>/
├── project.json                    ← Métadonnées projet
├── inputs/
│   ├── heightmap/                  ← .asc/.png/.tif
│   ├── satmap/                     ← Satmap source
│   ├── masks/                      ← Masques exclusion
│   └── gaea/                       ← Flow/deposit depuis Gaea
├── outputs/
│   ├── masks/latest/               ← Masques générés (PNG 16-bit)
│   ├── satmap/                     ← Satmap générée
│   ├── cache/                      ← terrain_data.npz
│   ├── reports/                    ← Rapports validation
│   ├── generated/                  ← Previews, cartes
│   └── logs/                       ← session_YYYYMMDD.log
└── surfaces.json                   ← Matériaux depuis .terr
```

---

**Version document** : 1.0  
**Dernière mise à jour** : 2026-08-29  
**Auteur** : Documentation automatique depuis analyse codebase
