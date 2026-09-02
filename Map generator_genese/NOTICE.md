# MAP GENERATOR PRO — Notice complète

**Version 3.0 — Production-Ready Architecture**
Plateforme Python/Streamlit de génération de cartes topographiques pour Arma Reforger, Unreal Engine 5 et Unity.

---

## Table des matières

1. [Vue d'ensemble du logiciel](#1-vue-densemble-du-logiciel)
2. [Installation et démarrage](#2-installation-et-démarrage)
3. [Architecture du projet](#3-architecture-du-projet)
4. [Mode d'emploi — Interface](#4-mode-demploi--interface)
   - 4.1 [Colonne gauche — Chargement et Export](#41-colonne-gauche--chargement-et-export)
   - 4.2 [Onglet Hypsométrique PURE](#42-onglet-hypsométrique-pure)
   - 4.3 [Onglet NatureMap (Occupation)](#43-onglet-naturemap-occupation)
   - 4.4 [Onglet Aperçu Texture Terrain 2D](#44-onglet-aperçu-texture-terrain-2d)
   - 4.5 [Onglet Calques Textures](#45-onglet-calques-textures)
   - 4.6 [Onglet Analyse Heightmap](#46-onglet-analyse-heightmap)
   - 4.7 [Onglet Végétation Potentielle](#47-onglet-végétation-potentielle)
5. [Modules Python — Référence détaillée](#5-modules-python--référence-détaillée)
   - 5.1 [base_map.py — BaseMap](#51-base_mappy--basemap)
   - 5.2 [naturemap_biomes_generator.py — NatureMapBiomesGenerator](#52-naturemap_biomes_generatorpy--naturemapbiomesgenerator)
   - 5.3 [satellite_colormap_generator.py — SatelliteColormapGenerator](#53-satellite_colormap_generatorpy--satellitecolormapgenerator)
   - 5.4 [hypsometric_colormap.py — HypsometricColormapGenerator](#54-hypsometric_colormappy--hypsometriccolormapgenerator)
   - 5.5 [texture_layer_generator.py — TextureLayerGenerator](#55-texture_layer_generatorpy--texturelayergenerator)
   - 5.6 [reforger_mask_generator.py — ReforgerMaskGenerator](#56-reforger_mask_generatorpy--reforgermaskgenerator)
   - 5.7 [satmap_analyzer.py — SatMapAnalyzer](#57-satmap_analyzerpy--satmapanalyzer)
   - 5.8 [urban_analysis_generator.py — UrbanAnalysisGenerator](#58-urban_analysis_generatorpy--urbananalysisgenerator)
   - 5.9 [airfield_analysis_generator.py — AirfieldAnalysisGenerator](#59-airfield_analysis_generatorpy--airfieldanalysisgenerator)
   - 5.10 [asc_png_converter.py](#510-asc_png_converterpy)
   - 5.11 [mask_correction_tool.py](#511-mask_correction_toolpy)
   - 5.12 [mask_validation_analyzer.py](#512-mask_validation_analyzerpy)
6. [Package map_generator — Architecture DDD](#6-package-map_generator--architecture-ddd)
   - 6.1 [Domain](#61-domain)
   - 6.2 [Application](#62-application)
   - 6.3 [Infrastructure](#63-infrastructure)
7. [Formats de fichiers supportés](#7-formats-de-fichiers-supportés)
8. [Flux de travail complets](#8-flux-de-travail-complets)
   - 8.1 [Workflow minimal — Hypsométrique](#81-workflow-minimal--hypsométrique)
   - 8.2 [Workflow complet — Reforger](#82-workflow-complet--reforger)
   - 8.3 [Workflow SatMap + morphologie](#83-workflow-satmap--morphologie)
   - 8.4 [Workflow analyse stratégique](#84-workflow-analyse-stratégique)
9. [Fonctions utilitaires dans app.py](#9-fonctions-utilitaires-dans-apppy)
10. [Dépannage](#10-dépannage)

---

## 1. Vue d'ensemble du logiciel

Map Generator Pro est une application web locale (Streamlit) qui prend en entrée une **heightmap** (carte des altitudes) et produit une suite de sorties graphiques et analytiques :

| Sortie | Utilité |
|--------|---------|
| Colormap hypsométrique | Visualisation altitude pure |
| Colormap satellite | Visualisation réaliste type satellite |
| NatureMap biomes | Carte d'occupation des sols (8 classes) |
| Aperçu texture terrain | Prévisualisation textures rock/soil/grass |
| Masques Reforger | Masques PNG 8-bit pour surface map Arma Reforger |
| Calques textures pente | Masques par tranche d'inclinaison |
| Analyse urbaine Voronoi | Planification villes / infrastructure |
| Analyse aérienne | Détection zones aéroports/aérodromes |
| Export ASC/PNG | Réexport heightmap avec altitudes réelles |

Le logiciel est conçu pour Bornholm (4352×4064 px, résolution 10.93 m/px) mais fonctionne sur toute heightmap ASC ou PNG.

---

## 2. Installation et démarrage

### Prérequis

```
Python 3.10+
pip install streamlit pillow numpy scipy matplotlib pandas opencv-python
```

### Démarrage

```bash
cd "Map generator"
streamlit run app.py
```

L'application s'ouvre automatiquement sur `http://localhost:8501`.

### Environnement virtuel (recommandé)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install streamlit pillow numpy scipy matplotlib pandas opencv-python
streamlit run app.py
```

---

## 3. Architecture du projet

```
Map generator/
│
├── app.py                          # Interface Streamlit principale (point d'entrée)
│
├── ── Modules métier ──
├── base_map.py                     # Source unique de vérité (BaseMap)
├── naturemap_biomes_generator.py   # Carte biomes + analyse morphologique complète
├── satellite_colormap_generator.py # Colormap réaliste type satellite
├── hypsometric_colormap.py         # Colormap hypsométrique altitude pure
├── texture_layer_generator.py      # Masques pente pour Reforger
├── reforger_mask_generator.py      # Masques textures Arma Reforger
├── satmap_analyzer.py              # Façade d'analyse d'image satellite (SatMap)
├── urban_analysis_generator.py     # Analyse urbaine Voronoi
├── airfield_analysis_generator.py  # Analyse aéroports/aérodromes
│
├── ── Outils standalone ──
├── asc_png_converter.py            # Convertisseur ASC ↔ PNG sans perte
├── mask_correction_tool.py         # Outil correction de masque débordant
├── mask_validation_analyzer.py     # Validation d'application de masque
├── slope_mask_generator.py         # Générateur masques pente
├── slope_material_masks_generator.py
├── slope_zones_locator.py
├── perfect_mask_generator.py
├── topographic_mask_generator.py
│
├── ── Package DDD ──
├── map_generator/
│   ├── domain/
│   │   ├── models/
│   │   │   ├── satmap.py           # SatMapInput, SatMapIndices, AlignmentReport
│   │   │   ├── terrain.py          # TerrainPreviewRequest, TerrainPreviewResult
│   │   │   └── mask.py             # MaskGenerationRequest, MaskGenerationResult
│   │   ├── ports/
│   │   │   ├── normalization.py    # Protocol NormalizationStrategy
│   │   │   └── exporter.py         # Protocol HeightmapExporter
│   │   └── services/
│   │       ├── satmap_index_service.py   # Calcul VARI, wet, mineral, bright, crop
│   │       └── terrain_score_service.py  # Scores rock/soil/grass + CLIMATE_TABLE
│   ├── application/
│   │   ├── use_cases/
│   │   │   ├── analyze_satmap_use_case.py
│   │   │   ├── generate_terrain_preview_use_case.py
│   │   │   └── generate_masks_use_case.py
│   │   ├── factories/
│   │   │   └── satmap_factory.py
│   │   └── satmap_facade.py
│   └── infrastructure/
│       ├── adapters/
│       │   └── pillow_resizer.py
│       ├── normalization/
│       │   └── percentile.py       # Normalisation au 99e percentile
│       └── exporters/
│           ├── asc_exporter.py     # Export ESRI ASCII Grid
│           └── png_exporter.py     # Export PNG 8/16-bit + dénormalisation
│
├── ── Données ──
├── input/
│   ├── bornholm_ter.asc            # Heightmap Bornholm (terrain principal)
│   └── ZBK_terrain_modified.asc
├── output/                         # Toutes les sorties générées
│   ├── masks/
│   ├── texture_layers/
│   └── saved_meshes/
├── prompts/                        # Templates de prompts par scénario
└── assets/                         # Ressources statiques
```

---

## 4. Mode d'emploi — Interface

### 4.1 Colonne gauche — Chargement et Export

C'est le point de départ obligatoire pour toute session.

#### Charger une heightmap

1. Cliquer sur **"📂 Charger Heightmap"**
2. Sélectionner un fichier `.asc`, `.png`, `.tga` ou `.jpg`
3. L'application affiche automatiquement :
   - Dimensions en pixels
   - Altitudes min/max en mètres
   - Prévisualisation miniature

> **Format recommandé :** `.asc` (ESRI ASCII Grid) — seul format conservant les vraies altitudes.

#### Charger une SatMap (optionnel)

Une **SatMap** est une image satellite ou ortho-photo de la même zone géographique que la heightmap. Elle permet d'enrichir l'aperçu texture avec les vraies couleurs de sol.

1. Dérouler la section **"🛰️ SatMap"**
2. Charger une image RGB (PNG ou JPG) de n'importe quelle résolution
3. Le logiciel redimensionne automatiquement à la résolution de la heightmap

#### Réparation heightmap

Si la heightmap contient des artéfacts (valeurs aberrantes, creux/pics isolés) :

1. Dérouler **"🔧 Réparer Heightmap"**
2. Ajuster le seuil de détection et le rayon de correction
3. Cliquer **"🔧 Réparer"**
4. Télécharger le résultat en `.asc`

#### Export heightmap

| Bouton | Format | Usage |
|--------|--------|-------|
| 📥 Export PNG 16-bit | PNG 16-bit normalisé + metadata.json | Édition externe (GIMP, Photoshop) |
| 📥 Export PNG 8-bit | PNG 8-bit normalisé | Aperçu / moteurs légers |
| 📥 Export ASC | ASC ESRI | Reforger / analyse SIG |
| 🔄 PNG → ASC (dénorm.) | ASC avec altitudes réelles | Après édition du PNG 16-bit |

> **Important :** L'export PNG 16-bit génère un fichier `_metadata.json` contenant les altitudes min/max d'origine. Ce fichier est indispensable pour la reconversion PNG → ASC avec dénormalisation.

---

### 4.2 Onglet Hypsométrique PURE

Génère une image colorée uniquement basée sur l'altitude, sans texture ni ombrage complexe.

**Palette de couleurs :**

| Altitude (%) | Couleur |
|:---:|---------|
| 0 – 10 % | Vert profond → Vert clair |
| 10 – 30 % | Jaune |
| 30 – 50 % | Orange clair |
| 50 – 70 % | Orange vif |
| 70 – 85 % | Rouge brique |
| 85 – 95 % | Rouge sombre |
| 95 – 100 % | Brun très sombre |

**Options :**
- **Hillshading :** Ajoute un ombrage directionnel (315° NW, 45° élévation) pour le relief
- **Force ombrage :** Intensité de l'effet relief [0.0 – 1.0]

**Utilisation :**
1. Charger une heightmap
2. Cocher/décocher Hillshading selon besoin
3. Cliquer **"🚀 Générer Hypsométrique"**
4. Télécharger avec **"📥 Télécharger"**

**Sortie :** `output/color_map_hypsometric.png`

---

### 4.3 Onglet NatureMap (Occupation)

Génère une carte d'occupation des sols à 8 biomes, basée sur l'altitude et les pentes.

**Biomes détectés (ordre de priorité) :**

| Biome | Règle | Couleur |
|-------|-------|---------|
| 🌊 Eau | altitude ≤ 0 m | Bleu azure |
| ❄️ Neige | altitude > 92e percentile | Blanc cassé |
| 🪨 Roche | pente > 35° OU altitude > 80e percentile | Gris marron |
| 🏔️ Toundra | 70e – 80e percentile altitude | Vert olive |
| 🌲 Forêt dense | 15° ≤ pente ≤ 35° | Vert foncé |
| 🌱 Prairie | défaut (reste) | Vert tendre |
| 🏖️ Sable | bordure eau/plaine (+2px) | Sable beige |

**Analyse morphologique incluse :**
La génération calcule en interne (une seule fois au chargement) :
- Pentes (degrés via Sobel)
- TPI local/moyen/large (Topographic Position Index)
- Accumulation de flux (réseau hydrographique)
- Réseau de rivières et lacs
- Lithologie proxy (alluvial / altérite / roche tendre / roche dure)
- Aspect (exposition)

**Utilisation :**
1. Charger une heightmap
2. Cliquer **"🚀 Générer NatureMap Biomes"**
3. Visualiser la distribution des biomes en pourcentage
4. Télécharger le PNG résultant

**Sortie :** `output/nature_map_biomes.png`

---

### 4.4 Onglet Aperçu Texture Terrain 2D

Génère une image de prévisualisation des textures terrain (rock / soil / grass) avec transitions douces.

#### Paramètres

| Paramètre | Description |
|-----------|-------------|
| **Profil climatique** | 6 profils prédéfinis (voir ci-dessous) |
| **% neige** | Percentile d'altitude à partir duquel la neige apparaît |
| **% flow (sol)** | Percentile d'accumulation de flux pour la détection sol |
| **Mode d'aperçu** | Morphologique / Morphologique + SatMap / SatMap (indépendant) |
| **Force guidance SatMap** | Intensité du guidage satellite [0.0 – 1.0] |

#### Profils climatiques

| Profil | Neige (m) | Humidité | Herbe cible | Roche cible |
|--------|-----------|----------|-------------|-------------|
| Tempéré | 1500 | 0.65 | 50–68 % | 5–14 % |
| Aride | 2600 | 0.18 | 18–38 % | 14–32 % |
| Continental | 1700 | 0.45 | 42–58 % | 8–18 % |
| Tropical | 4200 | 0.78 | 55–72 % | 4–12 % |
| Subarctique | 700 | 0.38 | 28–46 % | 14–28 % |
| Alpin | 2000 | 0.52 | 28–46 % | 20–38 % |

#### Modes d'aperçu

**Morphologique (actuel) :** Calcul 100 % basé sur les données altimétriques (pente, courbure, TPI, lithologie, accumulation de flux). Auto-calibration roche en 2 passes pour respecter les cibles du profil.

**Morphologique + SatMap :** Les scores morphologiques sont modulés par les indices spectraux de la SatMap (VARI végétation, humidité, minéral). Affiche une comparaison avant/après.

**SatMap (indépendant) :** Classification 100 % basée sur les couleurs de la SatMap. Détecte eau, neige, herbe, sol, roche, et cultures (overlay vert-jaune sur les champs détectés).

#### Algorithme de scores (mode morphologique)

1. **Score ROCHE** = 0.50 × sigmoid(pente, seuil) + 0.15 × courbure convexe + 0.12 × litho_dure + 0.10 × rugosité − 0.08 × flow_norm + bruit
2. **Score SOL** = 0.32 × sigmoid(flow, seuil) + 0.22 × courbure concave + 0.18 × alluvial + 0.12 × (1−humidité) × sigmoid(pente, 5°) + bruit
3. **Score HERBE** = 0.38 + 0.20 × altérite + 0.12 × humidité + 0.08 × bonus_nord − 0.18 × sigmoid(pente) + bruit

Les 3 scores sont normalisés (somme = 1) puis lissés par filtre gaussien (sigma ≈ 50 m / résolution).

**Couleurs de composition :**
- Roche : RGB(160, 160, 160)
- Sol/Terre : RGB(139, 94, 60)
- Herbe : RGB(76, 170, 78)
- Eau : RGB(50, 120, 220)
- Neige : RGB(245, 245, 245)
- Cultures (overlay) : RGB(185, 195, 100)

**Sortie :** `output/terrain_texture_preview.png`

---

### 4.5 Onglet Calques Textures

Génère des masques PNG noir/blanc par tranche de pente, utilisables directement dans Reforger comme calques de texture.

**5 catégories de pente :**

| Calque | Plage | Usage terrain |
|--------|-------|---------------|
| Herbe/Prairie | 0 – 3° | Terrain plat |
| Terre/Sol | 3 – 12° | Pente modérée |
| Roche Légère | 12 – 25° | Pente forte |
| Roche Forte | 25 – 45° | Pente très forte |
| Escarpement | 45°+ | Paroi intraversable |

**Mode Morphologique + SatMap :** Fusionne les calques de pente avec les indices spectraux de la SatMap pour affiner les masques selon les couleurs réelles du terrain.

**Options :**
- Exporter chaque calque individuellement (PNG 8-bit ou 16-bit)
- Générer un rapport JSON avec les statistiques par calque

**Sortie :** `output/texture_layers/`

---

### 4.6 Onglet Analyse Heightmap

Affiche des statistiques détaillées sur la heightmap chargée :
- Distribution des altitudes (histogramme)
- Distribution des pentes
- Répartition par classe (eau, plaine, montagne…)
- Métadonnées résolution / dimensions / format

---

### 4.7 Onglet Végétation Potentielle

Génère des masques de probabilité de végétation basés sur la combinaison :
- Altitude (zone de végétation possible)
- Pente (stabilité du sol)
- Exposition (versants nord = plus humide)
- Accumulation de flux (zones humides)

---

## 5. Modules Python — Référence détaillée

### 5.1 base_map.py — BaseMap

**Rôle :** Source unique de vérité. Charge la heightmap une seule fois et précalcule les dérivées fondamentales partagées par tous les modules.

**Classe `BaseMap`**

```python
BaseMap(heightmap_path: str, vertical_exaggeration: float = 10.0)
```

| Attribut | Type | Description |
|----------|------|-------------|
| `heightmap_uint8` | ndarray H×W | Heightmap 8-bit normalisée |
| `height`, `width` | int | Dimensions en pixels |
| `altitude_min`, `altitude_max` | float | Altitudes réelles en mètres |
| `slopes` | ndarray H×W | Pentes en degrés (Sobel) |
| `water_mask` | ndarray bool | Masque zones eau |
| `biome_masks` | dict | Masques par biome |

**Formats d'entrée supportés :** PNG, TGA, JPG, ASC

---

### 5.2 naturemap_biomes_generator.py — NatureMapBiomesGenerator

**Rôle :** Génère la carte biomes ET toutes les données morphologiques utilisées par l'aperçu terrain et les masques Reforger. C'est le module central.

**Classe `NatureMapBiomesGenerator`**

```python
NatureMapBiomesGenerator(
    heightmap_path: str,
    output_dir: str = "output",
    png_alt_max: float = 1000.0,
    png_cellsize: float = None
)
```

**Attributs calculés au chargement :**

| Attribut | Type | Description |
|----------|------|-------------|
| `heightmap_original` | ndarray H×W float32 | Altitudes réelles en mètres |
| `heightmap_norm` | ndarray H×W float32 | Altitudes normalisées [0,1] |
| `slopes` | ndarray H×W float32 | Pentes en degrés |
| `aspect` | ndarray H×W float32 | Aspect/exposition (degrés) |
| `tpi` | ndarray H×W float32 | TPI composite |
| `tpi_local` | ndarray H×W float32 | TPI fenêtre locale |
| `flow_accumulation` | ndarray H×W float32 | Accumulation de flux |
| `stream_network` | ndarray H×W bool | Réseau de rivières |
| `lake_mask` | ndarray H×W bool | Masque lacs |
| `water_mask` | ndarray H×W bool | Masque eau (total) |
| `lithology_proxy` | ndarray H×W int | 0=alluvial 1=altérite 2=tendre 3=dur |
| `lithology_distribution` | dict | % surface par classe lithologique |
| `nodata_mask` | ndarray bool | Pixels sans données (océan ASC) |
| `cellsize` | float | Résolution m/px (lue dans header ASC) |
| `tpi_windows_m` | dict | Tailles fenêtres TPI en mètres |
| `height`, `width` | int | Dimensions |
| `h_min`, `h_max` | float | Altitudes min/max réelles |

**Méthodes principales :**

`generate_biomes_map() -> np.ndarray`
Génère et retourne la carte biomes RGB H×W×3.

`save_biomes_map(output_path) -> str`
Sauvegarde la carte biomes en PNG.

---

### 5.3 satellite_colormap_generator.py — SatelliteColormapGenerator

**Rôle :** Génère une image réaliste "vue satellite" à partir de la heightmap seule, sans image satellite source.

**Classe `SatelliteColormapGenerator`**

```python
SatelliteColormapGenerator(
    heightmap_path: str,
    output_dir: str = "output",
    vertical_exaggeration: float = 10.0
)
```

**Pipeline de génération :**

1. `compute_slopes()` — Calcul des pentes via gradient Sobel
2. `apply_analytical_hillshading(azimuth=315, elevation=45)` — Ombrage directionnel
3. `create_biome_masks()` — Détection eau, roche, forêt, plaine par percentiles
4. `apply_texture_blending()` — Ajout bruit Perlin 2 échelles (fine + large)
5. `apply_hillshade_overlay(strength=0.35)` — Fusion ombrage sur colormap

**Palette biomes (RGB) :**

| Biome | Couleur RGB | Condition |
|-------|-------------|-----------|
| Eau | (40, 65, 90) | altitude < 10e percentile |
| Roche | (110, 105, 95) | pente > 85e percentile |
| Forêt | (45, 85, 40) | pente > 60e percentile |
| Plaine | (205, 195, 160) | reste |

**Sortie :** `output/satellite_colormap.png`

---

### 5.4 hypsometric_colormap.py — HypsometricColormapGenerator

**Rôle :** Colormap basée uniquement sur l'altitude, avec interpolation douce entre 8 points d'ancrage.

**Classe `HypsometricColormapGenerator`**

```python
HypsometricColormapGenerator(heightmap_path: str)
gen.save(output_path: str, add_hillshade: bool = True)
```

**Algorithme :**
1. Chargement heightmap (PNG/TGA/ASC)
2. Normalisation altitude [0, 1]
3. Lookup table 256 niveaux interpolés linéairement entre 8 ancres
4. Lissage bilinéaire (upsampling 2× + downsampling)
5. Hillshading optionnel (force 0.2 par défaut)

**Sortie :** `output/color_map_hypsometric.png`

---

### 5.5 texture_layer_generator.py — TextureLayerGenerator

**Rôle :** Génère 5 masques binaires PNG par tranche de pente pour usage direct dans les logiciels de terrain (Reforger, UE5).

**Classe `TextureLayerGenerator`**

```python
TextureLayerGenerator(heightmap_path: str, output_dir: str = "output")
```

**Catégories de pente :**

| Clé | Plage | Description |
|-----|-------|-------------|
| `herbe` | 0 – 3° | Herbe/Prairie |
| `terre` | 3 – 12° | Terre/Sol |
| `roche_legere` | 12 – 25° | Roche légère |
| `roche_forte` | 25 – 45° | Roche forte |
| `escarpement` | 45 – 90° | Escarpement |

**Méthodes :**

`generate_slope_masks() -> dict`
Retourne un dictionnaire `{clé: ndarray uint8}` pour chaque catégorie.

`export_masks(masks, bit_depth=8) -> list`
Exporte chaque masque en PNG. Retourne la liste des chemins.

`generate_report(masks) -> dict`
Génère un rapport JSON avec pourcentage de couverture par calque.

**Sorties :** `output/texture_layers/{herbe,terre,...}_mask.png`

---

### 5.6 reforger_mask_generator.py — ReforgerMaskGenerator

**Rôle :** Génère les masques de texture de surface (surface map) pour Arma Reforger, en respectant la contrainte des 5 textures maximum par bloc de 128 m.

**Classe `ReforgerMaskGenerator`**

```python
ReforgerMaskGenerator(nat_gen: NatureMapBiomesGenerator, output_dir: str = "output")
```

**4 profils biogéographiques :**

| Profil | Ambiance | Textures incluses |
|--------|----------|-------------------|
| `europe_temperee` | Europe tempérée | Grass_02, Grass_03, ForestDeciduous, Dirt_03, Pebbles, Rock, SeaBed |
| `boreal` | Boréal / Scandinave | Grass_01, ForestConiferous, Dirt_02, Heather, Pebbles, Rock, SeaBed |
| `mediterraneen` | Méditerranéen | Grass_03, Dirt_01, ForestDeciduous, MountainGrass, Pebbles_02, Rock, SeaBed |
| `arctique` | Arctique / Toundra | MountainGrass, Grass_01, Dirt_02, Pebbles, Debris_Rock, Rock, SeaBed |

**Méthodes principales :**

`generate_masks(profile, enforce_blocks, dynamic_budget, sat_indices, sat_strength) -> dict`
Génère tous les masques pour le profil donné. Si `sat_indices` est fourni, applique un guidage spectral.

`export_masks(masks, profile, output_dir) -> dict`
Sauvegarde chaque masque en PNG 8-bit. Retourne `{clé: chemin}`.

`enforce_block_limit(masks, profile, max_tex=5, dynamic_budget=True) -> dict`
Arbitre les blocs de 128 px pour respecter la limite Reforger de 5 textures/bloc.

`_apply_sat_guidance(masks, sat_indices, strength=0.35) -> dict`
Fusionne les masques morphologiques avec les indices spectraux SatMap.

**Sortie :** `output/texture_masks/{profil}/`

---

### 5.7 satmap_analyzer.py — SatMapAnalyzer

**Rôle :** Façade de compatibilité API. Analyse une image satellite RGB et calcule 5 indices spectraux normalisés.

**Classe `SatMapAnalyzer`**

```python
SatMapAnalyzer(sat_array: np.ndarray, target_shape: tuple = None)
```

**Méthodes :**

`align() -> np.ndarray`
Redimensionne le tableau satellite à `target_shape`. Retourne le tableau float32 normalisé [0,1].

`compute() -> dict`
Aligne puis calcule tous les indices. Retourne :

| Clé | Description | Formule |
|-----|-------------|---------|
| `veg_index` | Végétation (VARI) | `(G − R) / (G + R − B + ε)` normalisé [0,1] |
| `wet_index` | Humidité | `(B + 0.5×G) − R`, normalisé au 99e percentile |
| `mineral_index` | Minéral/Sol nu | `R − 0.5×G − 0.3×B`, normalisé au 99e percentile |
| `bright_index` | Brillance | `0.299×R + 0.587×G + 0.114×B` |
| `crop_index` | Cultures/Champs | `(R×0.55 + G×0.45) / (B + 0.08) − 1.2`, normalisé |
| `status` | `"ok"` ou code erreur | |
| `message` | Message descriptif | |

`to_preview_image(index_arr, colormap='viridis') -> PIL.Image`
Méthode statique. Convertit un index numpy en image colorée via matplotlib colormaps.

---

### 5.8 urban_analysis_generator.py — UrbanAnalysisGenerator

**Rôle :** Génère un maillage Voronoi représentant la planification urbaine. Place les seeds en priorité sur les zones de Prairie.

**Classe `UrbanAnalysisGenerator`**

```python
UrbanAnalysisGenerator(heightmap_path: str, biomes_map_path: str)
```

**Méthode principale :**

`generate_urban_analysis(num_seeds: int = 20) -> dict`
- Filtre les zones viables (Prairie, pas eau/roche)
- Place `num_seeds` seeds avec distribution spatiale équilibrée
- Classe les seeds : Alpha (2 plus grandes = métropoles), Beta/Gamma (reste)
- Génère maillage Voronoi et overlay visuel

**Sorties :**

| Sortie | Description |
|--------|-------------|
| `output/urban_planning_overlay.png` | Carte colorée avec Voronoi |
| `seeds` dans résultat | Liste `[(x, y), ...]` des seeds |

**Hiérarchie urbaine :**

| Classe | Nombre | Représentation |
|--------|--------|----------------|
| Alpha | 2 seeds | Métropoles (grande surface) |
| Beta | ~5 seeds | Villes secondaires |
| Gamma | Reste | Villages / bourgs |

---

### 5.9 airfield_analysis_generator.py — AirfieldAnalysisGenerator

**Rôle :** Détecte les zones géographiquement viables pour la construction d'aéroports et d'aérodromes.

**Classe `AirfieldAnalysisGenerator`**

```python
AirfieldAnalysisGenerator(heightmap_path: str, biomes_map_path: str, meters_per_pixel: float = 10.0)
```

**Gabarits :**

| Type | Dimensions | Pente max | Biomes viables |
|------|-----------|-----------|----------------|
| Alpha (Aéroport) | 2500 × 400 m | 2 % | Prairie, Plaine |
| Beta (Aérodrome) | 800 × 150 m | 5 % | Prairie, Plaine, Sable |

**Méthodes :**

`scan_for_airports() -> dict`
Mode Libre : balaye toute la carte. Retourne tous les sites viables (top 5 aéroports + 15 aérodromes par défaut).

`scan_for_airports_on_voronoi_seeds(voronoi_seeds_list: list) -> dict`
Mode Voronoi : évalue uniquement les seeds Voronoi situés en Prairie. Chaque seed est testé pour les deux gabarits.

**Rapport par site :**

```json
{
  "x": 1426, "y": 3279,
  "gabarit": "A",
  "altitude_mean": 45.3,
  "altitude_min": 42.1,
  "altitude_max": 48.7,
  "mean_slope": 1.2,
  "requires_earthwork": false,
  "feasibility_score": 100.0
}
```

**Sortie :** `output/site_diagnostic.png`

---

### 5.10 asc_png_converter.py

**Rôle :** Script autonome de conversion ASC ↔ PNG 16-bit sans perte d'altitude.

**Usage en ligne de commande :**

```bash
# ASC → PNG 16-bit
python asc_png_converter.py --asc-to-png input.asc output.png

# PNG 16-bit → ASC (dénormalisé)
python asc_png_converter.py --png-to-asc output.png result.asc

# Avec métadonnées personnalisées
python asc_png_converter.py --png-to-asc output.png result.asc --metadata custom_meta.json
```

**Workflow complet :**

```
heightmap.asc  →  heightmap.png (16-bit, 0–65535)
                + heightmap_metadata.json  (alt_min, alt_max)
                    ↓ [édition dans GIMP/Photoshop]
                heightmap_modified.png
                    ↓
                heightmap_result.asc  (altitudes réelles restaurées)
```

**Fichier metadata.json :**

```json
{
  "ncols": 4352, "nrows": 4064,
  "cellsize": 10.93,
  "nodata_value": -9999,
  "alt_min": -39.6,
  "alt_max": 163.7
}
```

---

### 5.11 mask_correction_tool.py

**Rôle :** Corrige une heightmap corrompue par un masque qui a débordé au-delà de la frontière rivière.

**Usage :**

```bash
python mask_correction_tool.py original.asc corrupted.asc --output fixed.asc
python mask_correction_tool.py original.asc corrupted.asc --output fixed.asc --river-col 2048
```

**Algorithme de correction :**

1. Détecte la rivière (colonne avec altitudes les plus basses)
2. Zone OUEST (< rivière) → conserve les modifications
3. Zone EST (≥ rivière) → restaure l'original pixel par pixel
4. Transition (±50 px) → blend progressif pour éviter les sauts

---

### 5.12 mask_validation_analyzer.py

**Rôle :** Valide qu'un masque a été correctement appliqué (modifications à l'ouest, aucun changement à l'est).

**Usage :**

```bash
python mask_validation_analyzer.py avant.png apres.png
python mask_validation_analyzer.py avant.asc apres.asc --output rapport.json
```

**Résultats :**
- `mask_validation_report.json` — rapport JSON détaillé
- `mask_differences_heatmap.png` — heatmap rouge/bleu des changements

**Critères de validation :**

| Zone | Critère | Résultat |
|------|---------|---------|
| OUEST | % changements > seuil | ✅ PASS si suffisamment modifié |
| EST | % changements < 2 % | ✅ PASS si quasi-inchangé |

---

## 6. Package map_generator — Architecture DDD

Le package `map_generator/` implémente une architecture Domain-Driven Design (DDD) séparant logique métier, orchestration et infrastructure.

### 6.1 Domain

#### `domain/models/satmap.py`

- **`SatMapInput`** : dataclass — `rgb: ndarray`, `target_shape: Optional[tuple]`
- **`SatMapIndices`** : dataclass frozen — les 5 indices + rapport + méthode `to_legacy_dict()`
- **`AlignmentReport`** : dataclass frozen — `status`, `message`, `source_shape`, `target_shape`

#### `domain/models/terrain.py`

- **`TerrainPreviewRequest`** : tous les paramètres nécessaires à la génération (chemin, profil climatique, mode, sat_array…)
- **`TerrainPreviewResult`** : image RGB + stats + comparison_payload + sat_preview_images

#### `domain/models/mask.py`

- **`MaskGenerationRequest`** : paramètres génération masques Reforger
- **`MaskGenerationResult`** : masques dict + chemins export + rapport JSON

#### `domain/ports/normalization.py`

- **`NormalizationStrategy`** : Protocol — méthode `normalize(arr) -> ndarray`

#### `domain/ports/exporter.py`

- **`HeightmapExporter`** : Protocol — méthode `export(array, output_path, **kwargs) -> str`

#### `domain/services/satmap_index_service.py`

Calcul pur des 5 indices spectraux sans état. Injecte une `NormalizationStrategy`.

#### `domain/services/terrain_score_service.py`

Contient toute la logique de calcul des scores texture :

| Méthode | Description |
|---------|-------------|
| `compute_morpho_scores(nat_gen, climate, snow_pct, flow_pct)` | Scores bruts + masques + auto-calibration |
| `normalize_scores(s_rock, s_soil, s_grass, blur_sigma)` | Normalisation + flou gaussien |
| `compose_texture(...)` | Composition RGB finale |
| `coverage_from_scores(...)` | Stats couverture % par matériau |
| `apply_sat_guidance(...)` | Fusion morpho + spectral |
| `compute_sat_only_scores(...)` | Classification 100 % SatMap |
| `apply_crop_overlay(...)` | Overlay cultures (vert-jaune) |

La table `CLIMATE_TABLE` définit les 6 profils climatiques avec leurs paramètres.

---

### 6.2 Application

#### `application/use_cases/analyze_satmap_use_case.py`

Orchestre align + compute. Méthode `execute(SatMapInput) -> SatMapIndices`.

#### `application/use_cases/generate_terrain_preview_use_case.py`

`GenerateTerrainPreviewUseCase.execute(TerrainPreviewRequest) -> TerrainPreviewResult`

Pipeline complet :
1. Instancie `NatureMapBiomesGenerator`
2. Calcule les scores morphologiques via `TerrainScoreService`
3. Optionnel : charge SatMap et calcule les indices
4. Applique la guidance / classification SatMap selon le mode
5. Compose la texture RGB
6. Applique l'overlay cultures si mode sat_only
7. Calcule les statistiques de couverture
8. Retourne `TerrainPreviewResult`

#### `application/use_cases/generate_masks_use_case.py`

`GenerateMasksUseCase.execute(MaskGenerationRequest) -> MaskGenerationResult`

Délègue à `ReforgerMaskGenerator`, exporte les masques, retourne rapport JSON.

#### `application/factories/satmap_factory.py`

`SatMapFactory.create_use_case()` — assemble `PillowResizer` + `PercentileNormalization` + `SatMapIndexService` + `AnalyzeSatMapUseCase`.

#### `application/satmap_facade.py`

API haut niveau simplifiée `SatMapFacade.analyze(rgb_array, target_shape) -> SatMapIndices`.

---

### 6.3 Infrastructure

#### `infrastructure/adapters/pillow_resizer.py`

Implémente le redimensionnement d'images via PIL BILINEAR. Satisfait l'interface `ImageResizer`.

#### `infrastructure/normalization/percentile.py`

`PercentileNormalization` : normalise un tableau au 99e percentile. Implémente `NormalizationStrategy`.

#### `infrastructure/exporters/asc_exporter.py`

`AscExporter.export(array, output_path, cellsize, nodata_value) -> str`

Écrit un ESRI ASCII Grid. Aucune dépendance Streamlit — toutes exceptions propagées.

#### `infrastructure/exporters/png_exporter.py`

`PngExporter.export(array, output_path, bit_depth) -> str`

Exporte en PNG 8-bit ou 16-bit normalisé + `_metadata.json`.

`PngExporter.export_from_png_with_denormalization(png_array, metadata_path, output_path) -> str`

Dénormalise un PNG 16-bit en altitudes réelles puis délègue à `AscExporter`.

---

## 7. Formats de fichiers supportés

### Entrée

| Format | Extension | Notes |
|--------|-----------|-------|
| ESRI ASCII Grid | `.asc` | **Format recommandé** — conserve altitudes réelles + résolution cellsize |
| PNG 8-bit | `.png` | Nécessite `png_alt_max` pour altitudes réelles |
| PNG 16-bit | `.png` | Plus précis que 8-bit |
| TGA | `.tga` | Support via PIL |
| JPEG | `.jpg`, `.jpeg` | Déconseillé (perte) |

### Sortie

| Format | Usage |
|--------|-------|
| PNG 24-bit | Colormaps, NatureMap, Aperçu terrain, cartes visuelles |
| PNG 8-bit grayscale | Masques Reforger, calques textures |
| PNG 16-bit grayscale | Export heightmap haute précision |
| ASC ESRI | Réexport heightmap avec altitudes réelles |
| JSON | Rapports, metadata, statistiques |

### Format ASC — Structure

```
ncols         4352
nrows         4064
xllcorner     0.0
yllcorner     0.0
cellsize      10.93
NODATA_value  -9999
-39.60 -38.10 ...
```

---

## 8. Flux de travail complets

### 8.1 Workflow minimal — Hypsométrique

```
1. Charger bornholm_ter.asc
2. Onglet "📐 Hypsométrique PURE"
3. Cliquer "🚀 Générer Hypsométrique"
4. Télécharger color_map_hypsometric.png
```

Durée estimée : < 10 secondes sur Bornholm (4352×4064).

---

### 8.2 Workflow complet — Reforger

```
1. Charger bornholm_ter.asc
   ↓
2. Onglet "🌿 NatureMap"
   → Cliquer "🚀 Générer NatureMap Biomes"
   → Vérifier distribution biomes
   ↓
3. Onglet "🧱 Aperçu Texture Terrain 2D"
   → Choisir profil climatique (ex: Tempéré)
   → Mode: Morphologique (actuel)
   → Cliquer "🚀 Générer Aperçu Terrain 2D"
   → Vérifier calibration (tableau cibles vs obtenu)
   ↓
4. Onglet "📐 Calques Textures"
   → Profil: europe_temperee
   → Cliquer "🚀 Générer Masques Reforger"
   → Télécharger les masques PNG individuels
   ↓
5. Colonne gauche → Export ASC
   → Télécharger heightmap pour Reforger
```

---

### 8.3 Workflow SatMap + morphologie

```
1. Charger heightmap (.asc)
2. Charger SatMap (ortho-photo PNG/JPG de la même zone)
   ↓
3. Onglet "🧱 Aperçu Texture Terrain 2D"
   → Mode: "SatMap (indépendant)"
   → Force guidance: 0.60–0.80
   → Cliquer "🚀 Générer Aperçu"
   → Inspecter les zones détectées (cultures en jaune-vert)
   ↓
   OU
   → Mode: "Morphologique + SatMap"
   → Comparer avant/après dans la section résultats
   → Ajuster la force si nécessaire
   ↓
4. Valider avec les indices SatMap affichés :
   - Vert (veg_index) : zones végétalisées
   - Bleu (wet_index) : zones humides
   - Cuivre (mineral_index) : sol nu / minéral
```

---

### 8.4 Workflow analyse stratégique

```
1. Charger heightmap (.asc)
   ↓
2. Onglet "🌿 NatureMap" → Générer NatureMap
   (nécessaire pour la détection biomes)
   ↓
3. Onglet "📊 Analyse Stratégique"
   Section "Analyse Urbaine Voronoi" :
   → Régler num_seeds (20 recommandé)
   → Cliquer "🚀 Générer Analyse Urbaine"
   → Les 20 seeds sont sauvegardés en session
   ↓
4. Section "Analyse Aérienne" :
   
   Mode Libre :
   → Cliquer "✈️ Analyser Emplacements (Libre)"
   → Top 5 aéroports + 15 aérodromes affichés

   Mode Voronoi (après étape 3) :
   → Cliquer "✈️ Analyser sur Seeds Voronoi"
   → Aéroports/aérodromes placés dans les cellules urbaines
   ↓
5. Télécharger site_diagnostic.png
   Récupérer le rapport JSON des sites viables
```

---

## 9. Fonctions utilitaires dans app.py

Ces fonctions sont définies dans `app.py` et utilisées par plusieurs onglets.

| Fonction | Rôle |
|----------|------|
| `export_heightmap_to_png(array, path, bit_depth)` | Export PNG (délègue à `PngExporter`) |
| `export_heightmap_to_asc(array, path, cellsize, nodata)` | Export ASC (délègue à `AscExporter`) |
| `export_png_to_asc_with_denormalization(png_array, meta_path, out_path)` | Reconversion PNG→ASC avec dénormalisation |
| `generate_basemap_and_maps(heightmap_path)` | Crée BaseMap + SatelliteColormap + NatureMap en une fois |
| `analyze_real_stats(heightmap_array)` | Statistiques altitudes + pentes (distribution complète) |
| `load_bg_image_base64()` | Charge le fond d'écran en base64 (cache Streamlit) |

---

## 10. Dépannage

### "FAIL: Trop de changements à l'EST" (mask validation)
→ Le masque a débordé au-delà de la rivière. Utiliser `mask_correction_tool.py` pour corriger.

### "FAIL: Pas assez de changements à l'OUEST"
→ Le masque ne s'est pas appliqué correctement. Vérifier le format du fichier masque.

### Métadonnées PNG non trouvées (dénormalisation)
→ S'assurer que le fichier `*_metadata.json` est dans le même répertoire que le PNG 16-bit.

### Aperçu terrain très sombre ou très clair
→ Ajuster le profil climatique. Un profil Aride favorise roche et sol ; un profil Tropical favorise herbe.

### SatMap non reconnue
→ La SatMap doit être une image RGB (3 canaux). Les images en niveaux de gris sont refusées.

### Erreur import cv2
→ `pip install opencv-python`. cv2 est optionnel pour plusieurs modules mais requis pour NatureMapBiomesGenerator.

### Masques Reforger vides (tous à 0)
→ Vérifier que NatureMap a bien été générée avant les masques. Les masques dépendent des données morphologiques de `NatureMapBiomesGenerator`.

### App Streamlit ne démarre pas
→ Vérifier que l'environnement virtuel est activé et que streamlit est installé :
```powershell
.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

### Heightmap chargée mais altitudes aberrantes
→ Pour un fichier `.asc`, vérifier que le header contient `cellsize` et `NODATA_value`. Pour un PNG, renseigner `png_alt_max` (altitude réelle du pixel le plus blanc).

---

*Notice générée le 5 mai 2026 — Map Generator Pro v3.0*
