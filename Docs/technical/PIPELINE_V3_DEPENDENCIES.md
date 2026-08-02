# Pipeline V3 — Architecture et Dépendances

**Version** : 3.0  
**Date** : 2026-08-01  
**Statut** : Production

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture du pipeline](#architecture-du-pipeline)
3. [Fichiers sources](#fichiers-sources)
4. [Modules de support](#modules-de-support)
5. [Dépendances externes](#dépendances-externes)
6. [Flux de données](#flux-de-données)
7. [Outils de diagnostic](#outils-de-diagnostic)
8. [Schéma global](#schéma-global)

---

## Vue d'ensemble

Le **Pipeline V3** est le système unifié de génération de masques terrain depuis heightmap et masques Gaea (flow, deposit). Il génère 14 masques PNG 16 bits représentant les différents biomes et zones écologiques.

### Principe fondamental

```
Heightmap .asc + Masques Gaea (flow, deposit)
        ↓
Enrichissement slope via fBm
        ↓
Calcul seuils adaptatifs (percentiles)
        ↓
Génération 14 masques avec règles écologiques
        ↓
Normalisation + Post-processing
        ↓
Export PNG 16 bits (seabed, coastal, prairie, alpages, forêts, etc.)
```

### Différence avec pipeline satmap EDDS

| Aspect | Pipeline V3 (masques) | Pipeline Satmap EDDS |
|--------|----------------------|----------------------|
| **Entrée** | heightmap.asc + flow/deposit.png | .ttile + _layer.edds |
| **Sortie** | 14 masques PNG 16 bits | satmap RGB 4097×4097 |
| **Dépendances** | numpy, cv2, scipy | edds_decoder, lrs2_parser, catalogue |
| **Usage** | Génération contenu terrain | Rendu visuel final |
| **Format** | Masques normalisés 0-65535 | Image RGB 0-255 |

---

## Architecture du pipeline

### Vue modulaire

```
┌─────────────────────────────────────────────────────────────┐
│ PIPELINE V3 (Génération masques)                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐                       ┌──────────────┐    │
│  │ pipeline_v3  │──────────────────────▶│   app.py     │    │
│  │    .py       │  (indépendant)        │  (UI Tab)    │    │
│  └──────────────┘                       └──────────────┘    │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────────────────────────────┐               │
│  │      ENTRÉES                             │               │
│  ├──────────────────────────────────────────┤               │
│  │ • heightmap.asc      (altitude)          │               │
│  │ • flow.png           (Gaea flow)         │               │
│  │ • deposit.png        (Gaea deposit)      │               │
│  └──────────────────────────────────────────┘               │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────────────────────────────┐               │
│  │      SORTIES                             │               │
│  ├──────────────────────────────────────────┤               │
│  │ • 14 masques PNG 16 bits                 │               │
│  │   (seabed, flow, deposit, coastal, etc.) │               │
│  └──────────────────────────────────────────┘               │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PIPELINE SATMAP (Rendu texturé depuis .edds)               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ satmap_v2_   │───▶│ edds_decoder │───▶│   app.py     │  │
│  │ textured.py  │    │    .py       │    │  (UI Tab)    │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                    │                               │
│         ▼                    ▼                               │
│  ┌──────────────────────────────────────────┐               │
│  │      MODULES DE SUPPORT                  │               │
│  ├──────────────────────────────────────────┤               │
│  │ • lrs2_parser.py     (lecture .ttile)    │               │
│  │ • terrain_terr_reader.py (catalogue)     │               │
│  └──────────────────────────────────────────┘               │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ OUTILS DE DIAGNOSTIC                                        │
├─────────────────────────────────────────────────────────────┤
│ • clean_weights.py   (validation blocs terrain)             │
│ • satmap_verifiers.py (vérification satmap)                 │
│ • pipeline_validation.py (debug pipeline)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Fichiers sources

### 🎯 Fichiers principaux

#### `pipeline_v3.py`
**Rôle** : Pipeline unifié de génération de masques terrain

**Description** : Génère les 14 masques PNG 16 bits depuis la heightmap `.asc` et les masques Gaea (flow, deposit)

**Fonctions clés** :
- Lecture heightmap `.asc` + enrichissement slope via fBm
- Calcul seuils automatiques depuis percentiles
- Génération masques pente : landes_rocheuses + rock
- Normalisation masques Gaea : flow + deposit
- Post-processing : stretch, gamma, weight_min
- Export 14 masques PNG 16 bits dans OUTPUT_DIR

**Dépendances** :
```python
import numpy as np
import cv2
from pathlib import Path
from scipy.ndimage import uniform_filter

# Pas de dépendances vers edds_decoder, lrs2_parser,
# terrain_terr_reader ou satmap_v2_textured
```

**Pipeline** :
1. Charger heightmap `.asc`
2. Enrichir slope via fBm si nécessaire
3. Calculer percentiles et seuils adaptatifs
4. Générer 14 masques avec règles écologiques
5. Normaliser et post-traiter chaque masque
6. Exporter PNG 16 bits

**Format sortie** :
- 14 masques PNG 16 bits dans OUTPUT_DIR :
  - `01_mask_seabed.png`
  - `02_mask_flow.png`
  - `03_mask_deposit.png`
  - `04_mask_coastal_flat.png`
  - `05_mask_coastal_slope.png`
  - `06_mask_landes_rocheuses.png`
  - `07_mask_rock.png`
  - `08_mask_prairie_humide.png`
  - `09_mask_prairie_seche.png`
  - `10_mask_landes_plateau.png`
  - `11_mask_maquis_landes.png`
  - `12_mask_alpages.png`
  - `13_mask_foret_feuillue.png`
  - `14_mask_foret_coniferes.png`

---

#### `satmap_v2_textured.py`
**Rôle** : Module de rendu texturé (utilisé pour génération satmap depuis `.edds`)

**Fonctions clés** :
- `load_middle_texture(mat_name, catalog)` — Charge une texture Middle
- `tile_texture(middle_img, tiling_scale)` — Répète une texture
- `apply_tint(img, tint_color)` — Applique teinte sRGB

**Dépendances** :
```python
import cv2, numpy as np
from pathlib import Path
```

**Utilisation** :
- Chargement des textures Middle (BCR 256×256)
- Tiling selon `tiling_scale` du catalogue
- Fallback couleur plate si texture absente

**Note** : Non utilisé par `pipeline_v3.py` (génération masques), mais utilisé par le pipeline satmap EDDS (rendu texturé)

---

#### `app.py`
**Rôle** : Interface graphique Tkinter — Onglet "Satmap V2"

**Fonctions clés** :
- `setup_satmap_v2_tab()` — Crée l'onglet UI
- `on_generate_satmap_v2()` — Callback bouton "Générer"
- `update_satmap_preview()` — Affiche aperçu 800×800

**Dépendances** :
```python
from pipeline_v3 import generate_satmap_v3
import tkinter as tk
from PIL import Image, ImageTk
```

**Workflow UI** :
1. Utilisateur sélectionne projet (menu déroulant)
2. Clic "Générer Satmap V2"
3. Barre de progression (par tuile)
4. Affichage aperçu + stats
5. Export PNG + logs

---

### 🔧 Modules de support

#### `edds_decoder.py`
**Rôle** : Lecture/écriture format `.edds` Enfusion

**Fonctions principales** :
```python
decode_edds_layer(path: Path) → np.ndarray
    # Lit un .edds et retourne array (H,W) uint32

extract_all_weights(pixels: np.ndarray) → np.ndarray
    # Décode uint32 → (H,W,7) float32 (poids w0..w6)

encode_edds_layer(pixels: np.ndarray, path: Path) → bool
    # Patch in-place du mip principal

pack_weights_to_pixel(weights: np.ndarray) → np.ndarray
    # Inverse : (H,W,7) float32 → uint32

decompress_lz4_chained(data: bytes) → bytes
    # Décompression LZ4 chaînée avec dictionnaire

compress_lz4_chained(data: bytes) → bytes
    # Compression LZ4 chaînée avec dictionnaire
```

**CLI** :
```bash
python edds_decoder.py --scan-health "chemin/.Data"
# Diagnostic de tous les .edds d'un dossier
```

**Format EDDS** :
- Header DDS 128 bytes (marqueur ENF1)
- Table mips (offset 128 ou 148 selon map)
- Blobs LZ4 chaînés (64 Ko par chunk, dict précédent)
- Mip principal = 512×512 R32_UINT

**Voir** : [FORMAT_LAYER_EDDS.md](FORMAT_LAYER_EDDS.md)

---

#### `lrs2_parser.py`
**Rôle** : Lecture chunk LRS2 depuis `.ttile` (IFF TERR)

**Fonctions principales** :
```python
read_lrs2_from_ttile(ttile_path: Path) → Dict
    # Retourne {(bx, by): (mat_ids, orig_index), ...}
    # bx, by = coordonnées locales 0-3
    # mat_ids = [3, 15, 42, ...] (IDs surfaces)
    # orig_index = index LRS2 global
```

**Format LRS2** :
```
Pour chaque bloc (4×4 = 16 blocs par tuile) :
    u32 index       # (by << 7) | bx → identifie le bloc
    u16 n           # Nombre de matériaux (1-7)
    u16[n] ids      # IDs globaux des surfaces
```

**Exemple** :
```python
lrs2_blocks = read_lrs2_from_ttile(Path("Terrain_123.ttile"))
# {
#   (0, 0): ([3, 15], 0x0000),
#   (1, 0): ([3, 15, 42], 0x0001),
#   ...
# }
```

---

#### `terrain_terr_reader.py`
**Rôle** : Lecture fichier `terrain.terr` (catalogue matériaux)

**Fonctions principales** :
```python
read_mats_from_terr(terr_path: Path) → List[Dict]
    # Retourne liste des surfaces avec métadonnées
    # [
    #   {
    #     "name": "Grass_03.emat",
    #     "middle_bcr": "Grass_03_Middle_BCR.png",
    #     "tiling_scale": 8.0,
    #     "avg_color": [75, 110, 48],
    #     "tint": [255, 255, 255],
    #     ...
    #   },
    #   ...
    # ]
```

**Structure `terrain.terr`** :
- Header IFF TERR
- Chunk MATS : liste des `.emat`
- Chunk LMAT : métadonnées par matériau
- Autres chunks (QUAD, VEGE, etc.)

**Usage dans pipeline** :
```python
surfaces = read_mats_from_terr(terr_path)
mat_name = surfaces[mat_id]["name"]
middle_bcr = surfaces[mat_id]["middle_bcr"]
```

---

#### `mask_utils.py`
**Rôle** : Utilitaires de normalisation masques

**Fonctions principales** :
```python
normalize_mask_percentile(mask: np.ndarray, p_min=2, p_max=98) → np.ndarray
    # Normalise un masque 0-1 via percentiles

apply_colormap_hypsometric(heightmap: np.ndarray) → np.ndarray
    # Applique colormap hypsométrique

blend_alpha(base: np.ndarray, overlay: np.ndarray, alpha: float) → np.ndarray
    # Blend deux images avec transparence
```

**Usage** :
- Normalisation heightmap avant export
- Génération aperçus colorés
- Composition masques multiples

---

#### `hypsometric_colormap.py`
**Rôle** : Gestion colormaps terrain (altitude → couleur)

**Fonctions principales** :
```python
get_hypsometric_colormap(name="earth") → np.ndarray
    # Retourne LUT 256×3 RGB

apply_hypsometric(heightmap: np.ndarray, colormap: str) → np.ndarray
    # Applique colormap sur heightmap normalisée
```

**Colormaps disponibles** :
- `earth` — Bleu (mer) → Vert (plaines) → Marron (montagnes) → Blanc (neige)
- `grayscale` — Noir → Blanc
- `terrain` — Colormap Matplotlib standard

---

### 🧹 Outils de diagnostic

#### `clean_weights.py`
**Rôle** : Nettoyage et validation blocs terrain

**Modes principaux** :
```bash
# Scanner slots négligeables
python clean_weights.py --scan

# Inspecter une tuile (image PNG)
python clean_weights.py --inspect 2,11

# Nettoyer une tuile
python clean_weights.py --clean 25,0

# Valider cohérence LRS2 ↔ layer
python clean_weights.py --validate 2,12

# Afficher poids réels (0-31)
python clean_weights.py --weights 1,18

# Diagnostic Zone B
python clean_weights.py --scan-zone --mask zone_b.png
python clean_weights.py --clean-zone --mask zone_b.png
python clean_weights.py --reset-zone --mask zone_b.png
```

**Dépendances** :
```python
from edds_decoder import decode_edds_layer, extract_all_weights, encode_edds_layer
from lrs2_parser import read_lrs2_from_ttile
from terrain_terr_reader import read_mats_from_terr
import cv2, numpy as np
```

**Voir** : [SCRIPTS_REFERENCE.md](SCRIPTS_REFERENCE.md)

---

#### `satmap_verifiers.py`
**Rôle** : Vérification qualité satmap générée

**Fonctions principales** :
```python
verify_satmap_coverage(satmap_path: Path) → Dict
    # Vérifie couverture pixels (noir/blanc/couleur)

check_tile_boundaries(satmap: np.ndarray) → List[Tuple]
    # Détecte artefacts aux jonctions de tuiles

analyze_color_distribution(satmap: np.ndarray) → Dict
    # Histogramme RGB, saturation, etc.
```

**Usage** :
```python
from satmap_verifiers import verify_satmap_coverage

stats = verify_satmap_coverage(Path("satmap_4k.png"))
# {
#   "total_pixels": 16777217,
#   "black_pixels": 0,
#   "white_pixels": 120,
#   "colored_pixels": 16777097,
#   "coverage_pct": 99.9993
# }
```

---

#### `pipeline_validation.py`
**Rôle** : Debug pipeline (logs détaillés par tuile)

**Fonctions principales** :
```python
validate_tile_processing(tile_id: int, config: Dict) → Dict
    # Valide traitement complet d'une tuile
    # Retourne diagnostics détaillés

compare_qtre_vs_edds(tile_id: int) → Dict
    # Compare QTRE (v1) vs EDDS (v3) pour une tuile
```

**Sortie exemple** :
```
[VALIDATE] Tuile 123 (3,3)
  ✓ .ttile trouvé (12.5 Ko)
  ✓ _layer.edds trouvé (256 Ko)
  ✓ LRS2 : 16 blocs parsés
  ✓ Layer : 512×512 pixels décodés
  ✓ Matériaux : 5 textures différentes
  ✓ Textures Middle : 5/5 chargées
  ✓ Rendu : 512×512 RGB généré
  ⚠ 3 pixels noirs (0.001%) — bloc (2,1) LRS2 vide
```

---

## Dépendances externes

### Bibliothèques Python

```python
# Core
numpy >= 1.24.0          # Arrays, calculs vectorisés
opencv-python >= 4.8.0   # Lecture/écriture images, resize
lz4 >= 4.3.0             # Compression LZ4 chaînée

# UI
tkinter                  # Interface graphique (built-in Python)
Pillow >= 10.0.0         # Manipulation images UI

# Optionnel
matplotlib >= 3.7.0      # Colormaps (hypsometric)
```

### Installation

```bash
pip install numpy opencv-python lz4 Pillow matplotlib
```

---

### Données externes

#### Catalogue textures

**Localisation** : `data/Textures_ArmaReforger/`

**Fichiers requis** :
```
catalog.json              # Métadonnées toutes textures
texture_Middle/
  ├── Grass_03_Middle_BCR.png
  ├── Rock_01_Middle_BCR.png
  ├── Dirt_01_Middle_BCR.png
  └── ... (56 textures)
```

**Format `catalog.json`** :
```json
{
  "Grass_03.emat": {
    "middle_bcr": "Grass_03_Middle_BCR.png",
    "tiling_scale": 8.0,
    "avg_color": [75, 110, 48],
    "tint": [255, 255, 255],
    "tint_srgb": [255, 255, 255]
  },
  ...
}
```

**Génération catalogue** :
```bash
python emat_scanner_simple.py
# Scanne dossier Reforger/Textures et génère catalog.json
```

---

#### Terrain Reforger

**Localisation** : `I:\Reforger_addons travail\<Nom_Map>\World\<Nom_Map>\Terrain\`

**Fichiers requis** :
```
terrain.terr              # Catalogue matériaux
.Data/
  ├── Terrain_0.ttile
  ├── Terrain_0_layer.edds
  ├── Terrain_1.ttile
  ├── Terrain_1_layer.edds
  └── ... (max 1024 tuiles)
```

**Vérification santé** :
```bash
python edds_decoder.py --scan-health "chemin/.Data"
# Détecte fichiers corrompus ou manquants
```

---

## Flux de données

### Pipeline complet (end-to-end)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. ENTRÉE UTILISATEUR (UI)                                  │
├─────────────────────────────────────────────────────────────┤
│ • Sélection projet (menu déroulant)                         │
│ • Clic "Générer Satmap V2"                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. CHARGEMENT CONFIGURATION (app.py)                        │
├─────────────────────────────────────────────────────────────┤
│ project_config = {                                          │
│   "name": "Zimnitrita",                                     │
│   "terrain_root": "I:/Reforger.../Terrain",                │
│   "output_dir": "data/projects/Zimnitrita",                │
│ }                                                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. LECTURE CATALOGUE (terrain_terr_reader.py)              │
├─────────────────────────────────────────────────────────────┤
│ surfaces = read_mats_from_terr("terrain.terr")             │
│ # [{"name": "Grass_03.emat", ...}, ...]                    │
│                                                              │
│ catalog = load_json("catalog.json")                         │
│ # {"Grass_03.emat": {"middle_bcr": ..., ...}}              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. BOUCLE TUILES (pipeline_v3.py)                          │
├─────────────────────────────────────────────────────────────┤
│ Pour chaque tuile (0-1023) :                                │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐  │
│   │ 4a. Lecture LRS2 (lrs2_parser.py)                   │  │
│   ├─────────────────────────────────────────────────────┤  │
│   │ lrs2 = read_lrs2_from_ttile("Terrain_N.ttile")     │  │
│   │ # {(0,0): ([3,15], 0x0000), ...}                   │  │
│   └─────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│   ┌─────────────────────────────────────────────────────┐  │
│   │ 4b. Lecture Layer (edds_decoder.py)                 │  │
│   ├─────────────────────────────────────────────────────┤  │
│   │ pixels = decode_edds_layer("Terrain_N_layer.edds") │  │
│   │ # (512, 512) uint32                                │  │
│   │                                                      │  │
│   │ weights = extract_all_weights(pixels)              │  │
│   │ # (512, 512, 7) float32 (w0..w6 normalisés)        │  │
│   └─────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│   ┌─────────────────────────────────────────────────────┐  │
│   │ 4c. Chargement textures (satmap_v2_textured.py)    │  │
│   ├─────────────────────────────────────────────────────┤  │
│   │ Pour chaque mat_id unique dans LRS2 :              │  │
│   │   middle_bcr = catalog[mat_name]["middle_bcr"]     │  │
│   │   texture = cv2.imread(middle_bcr)                 │  │
│   │   texture_tiled = tile_texture(texture, scale)     │  │
│   │   textures_cache[mat_id] = texture_tiled           │  │
│   └─────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│   ┌─────────────────────────────────────────────────────┐  │
│   │ 4d. Rendu pixel par pixel (pipeline_v3.py)         │  │
│   ├─────────────────────────────────────────────────────┤  │
│   │ tile_rgb = np.zeros((512, 512, 3), dtype=uint8)    │  │
│   │                                                      │  │
│   │ Pour chaque pixel (y, x) :                         │  │
│   │   bx, by = x // 128, y // 128                      │  │
│   │   mat_ids = lrs2[(bx, by)]                         │  │
│   │   w = weights[y, x, :len(mat_ids)]                 │  │
│   │                                                      │  │
│   │   color = np.zeros(3)                              │  │
│   │   Pour chaque (mat_id, weight) :                   │  │
│   │     texture = textures_cache[mat_id]               │  │
│   │     color += texture[y, x, :] * weight             │  │
│   │                                                      │  │
│   │   tile_rgb[y, x, :] = color                        │  │
│   └─────────────────────────────────────────────────────┘  │
│                            ↓                                 │
│   ┌─────────────────────────────────────────────────────┐  │
│   │ 4e. Écrire tuile (cv2.imwrite)                      │  │
│   ├─────────────────────────────────────────────────────┤  │
│   │ cv2.imwrite(f"tile_{tx}_{ty}.png", tile_rgb)       │  │
│   └─────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. ASSEMBLAGE GRILLE (pipeline_v3.py)                      │
├─────────────────────────────────────────────────────────────┤
│ satmap_16k = np.zeros((16384, 16384, 3), dtype=uint8)      │
│                                                              │
│ Pour chaque tuile (tx, ty) :                                │
│   tile_img = cv2.imread(f"tile_{tx}_{ty}.png")             │
│   satmap_16k[ty*512:(ty+1)*512, tx*512:(tx+1)*512] = tile  │
│                                                              │
│ cv2.imwrite("satmap_16k.png", satmap_16k)                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. DOWNSCALE (cv2.resize)                                   │
├─────────────────────────────────────────────────────────────┤
│ satmap_4k = cv2.resize(satmap_16k, (4097, 4097),           │
│                        interpolation=cv2.INTER_LANCZOS4)    │
│                                                              │
│ cv2.imwrite("satmap_4k.png", satmap_4k)                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. AFFICHAGE UI (app.py)                                    │
├─────────────────────────────────────────────────────────────┤
│ • Charger satmap_4k.png                                     │
│ • Resize vers 800×800 (aperçu)                              │
│ • Afficher dans Canvas Tkinter                              │
│ • Logs : "Satmap générée : 4097×4097"                       │
└─────────────────────────────────────────────────────────────┘
```

---

### Format des données inter-modules

#### LRS2 (dict Python)

```python
{
    (bx, by): (mat_ids, orig_index),
    # bx, by : coordonnées locales 0-3 (bloc dans la tuile)
    # mat_ids : [3, 15, 42, ...] (IDs surfaces, 1-7 matériaux)
    # orig_index : index LRS2 global (utilisé pour ré-écriture)
}
```

**Exemple** :
```python
{
    (0, 0): ([3, 15], 0x0000),           # Bloc (0,0) : Grass_03 + Dirt_01
    (1, 0): ([3, 15, 42], 0x0001),       # Bloc (1,0) : 3 matériaux
    (2, 0): ([3], 0x0002),               # Bloc (2,0) : 1 seul matériau
    ...
}
```

---

#### Layer pixels (np.ndarray uint32)

```python
shape: (512, 512)
dtype: uint32

Encodage par pixel :
  bits  0- 4 : w1
  bits  5- 9 : w2
  bits 10-14 : w3
  bits 15-19 : w4
  bits 20-24 : w5
  bits 25-29 : w6
  w0 = 31 − Σ(w1..w6)  # implicite
```

---

#### Weights (np.ndarray float32)

```python
shape: (512, 512, 7)
dtype: float32
valeurs: [0.0, 1.0] (normalisés)

weights[y, x, 0] = w0 (premier matériau)
weights[y, x, 1] = w1 (deuxième matériau)
...
weights[y, x, 6] = w6 (septième matériau)
```

---

## Outils de diagnostic

### Vérification santé pipeline

#### 1. Diagnostic fichiers `.edds`

```bash
python edds_decoder.py --scan-health "I:/Reforger.../Terrain/.Data"
```

**Sortie** :
```
Map détectée : résolution 512×512, table_offset=148, format=LZ4 
Scan de 1024 fichiers .edds

✓ OK              : 1020 fichiers
✗ Corrompus       : 2 fichiers
⚠ Hors format     : 1 fichiers
⚠ Ttile manquant  : 1 fichiers

FICHIERS CORROMPUS :
  Terrain_938_layer.edds — mip principal size=0

Tile IDs à vérifier : 938
```

---

#### 2. Validation cohérence LRS2 ↔ Layer

```bash
python clean_weights.py --validate 2,12
```

**Sortie** :
```
[TTILE] Terrain_76.ttile
  ✅ FORM size: 12345 OK
  ✅ LRS2 size: 256
  ✅ 16 blocs LRS2
    (0,0) index=0x0000 mats=[Grass_03, Dirt_01]

[LAYER] Terrain_76_layer.edds
  ✅ Magic DDS OK
  ✅ 0 pixels invalides

[COHÉRENCE LRS2 / LAYER]
  (0,0): Grass_03=87%, Dirt_01=13%

✅ Aucune erreur détectée
```

---

#### 3. Inspection visuelle tuile

```bash
python clean_weights.py --inspect 2,11
```

**Sortie** : `tile_2_11_cleanup.png` (800×800 avec textures)

---

#### 4. Vérification satmap finale

```bash
python -c "
from satmap_verifiers import verify_satmap_coverage
from pathlib import Path

stats = verify_satmap_coverage(Path('satmap_4k.png'))
print(f'Coverage: {stats[\"coverage_pct\"]:.2f}%')
print(f'Pixels noirs: {stats[\"black_pixels\"]}')
"
```

---

## Schéma global

### Architecture fichiers projet

```
Map Generator/
├── app.py                        # Interface UI principale
├── pipeline_v3.py                # Pipeline satmap v3
├── satmap_v2_textured.py         # Rendu texturé
│
├── edds_decoder.py               # Lecture/écriture .edds
├── lrs2_parser.py                # Lecture LRS2 (.ttile)
├── terrain_terr_reader.py        # Lecture terrain.terr
├── mask_utils.py                 # Utilitaires masques
├── hypsometric_colormap.py       # Colormaps terrain
│
├── clean_weights.py              # Outil nettoyage blocs
├── satmap_verifiers.py           # Vérification satmap
├── pipeline_validation.py        # Debug pipeline
│
├── data/
│   ├── Textures_ArmaReforger/
│   │   ├── catalog.json          # Métadonnées textures
│   │   └── texture_Middle/       # BCR 256×256
│   │       ├── Grass_03_Middle_BCR.png
│   │       └── ...
│   │
│   └── projects/
│       └── Zimnitrita/
│           ├── satmap_16k.png    # Sortie 16k
│           └── satmap_4k.png     # Sortie 4k
│
└── Docs/
    └── technical/
        ├── PIPELINE_V3_DEPENDENCIES.md  # Ce fichier
        ├── FORMAT_LAYER_EDDS.md
        ├── SCRIPTS_REFERENCE.md
        └── PIPELINE_LOGIQUE.md
```

---

### Dépendances entre modules

```
app.py
  ├─→ pipeline_v3.py (génération masques)
  │     ├─→ numpy, cv2, scipy
  │     └─→ Aucune dépendance interne
  │
  ├─→ satmap_v2_textured.py (rendu satmap)
  │     ├─→ edds_decoder.py
  │     │     └─→ lz4 (externe)
  │     ├─→ lrs2_parser.py
  │     ├─→ terrain_terr_reader.py
  │     └─→ cv2, numpy
  │
  └─→ clean_weights.py (diagnostic terrain)
        ├─→ edds_decoder.py
        ├─→ lrs2_parser.py
        └─→ terrain_terr_reader.py
```

---

## Optimisations futures

### Phase 1 — Performance (court terme)

| Optimisation | Gain estimé | Complexité |
|--------------|-------------|------------|
| **Cache textures par projet** | 30-40% | Basse |
| **Multiprocessing (par tuile)** | 300-400% (4 cores) | Moyenne |
| **Downscale incrémental** | 15-20% | Basse |
| **Format intermédiaire compressé** | 50% I/O | Moyenne |

---

### Phase 2 — Fonctionnalités (moyen terme)

- **Masques personnalisés** : Zones exclusion, surcharges locales
- **Biome blending** : Transitions douces entre biomes
- **Export multi-résolution** : 2k, 4k, 8k, 16k simultanés
- **Normalmap génération** : Normal map depuis heightmap

---

### Phase 3 — Généralisation (long terme)

- **Support multi-maps** : Eden, Everon, Arland, etc.
- **Format universel** : Abstraction layer pour autres moteurs
- **Cloud processing** : Génération serveur pour maps >32km
- **Real-time preview** : Aperçu temps réel pendant génération

---

## Références

- [FORMAT_LAYER_EDDS.md](FORMAT_LAYER_EDDS.md) — Format binaire `.edds` détaillé
- [SCRIPTS_REFERENCE.md](SCRIPTS_REFERENCE.md) — Référence tous les scripts
- [PIPELINE_LOGIQUE.md](PIPELINE_LOGIQUE.md) — Pipeline texture (legacy v1/v2)
- [Enfusion Engine Docs](https://community.bistudio.com/wiki/Enfusion_Engine)
- [LZ4 Specification](https://github.com/lz4/lz4)

---

**Dernière mise à jour** : 2026-08-01  
**Projet** : Map Generator Pro — Pipeline Satmap V3  
**Auteur** : Documentation technique collaborative
