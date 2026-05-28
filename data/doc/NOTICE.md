# MAP GENERATOR PRO — Notice complète

**Version 5.2**  
Application web locale (Streamlit) de génération et d'analyse de cartes terrain pour **Arma Reforger / Enfusion Engine**.

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Installation et démarrage](#2-installation-et-démarrage)
3. [Architecture du projet](#3-architecture-du-projet)
4. [Gestion de projets](#4-gestion-de-projets)
5. [Interface — Barre latérale](#5-interface--barre-latérale)
6. [Onglet Terrain](#6-onglet-terrain)
7. [Onglet Génération](#7-onglet-génération)
8. [Onglet Calques & Export](#8-onglet-calques--export)
9. [Bibliothèque de matériaux](#9-bibliothèque-de-matériaux)
10. [Modules Python](#10-modules-python)
11. [Formats supportés](#11-formats-supportés)
12. [Workflows](#12-workflows)
13. [Dépannage](#13-dépannage)

---

## 1. Vue d'ensemble

Map Generator Pro prend en entrée une **heightmap** et des **masques Instant Terra** optionnels, et produit un pipeline complet pour la création de terrain Reforger :

| Sortie | Utilité |
|--------|---------|
| Colormap hypsométrique | Visualisation altitude + relief |
| NatureMap biomes | Carte d'occupation des sols |
| Aperçu texture terrain | Prévisualisation morphologique des textures |
| Masques de surface (QTRE) | Priority Mask Reforger, max 5 ou 7 tex/bloc (configurable) |
| Carte végétation potentielle | Carte 2D des types de végétation par zone |
| Lecture TMAT | Visualisation grille texture réelle depuis Workbench |
| SatMap réaliste | SatMap cohérente tuilée par matériau |
| Carte Reconstruction | Vue aérienne depuis masques exportés + overlay zones |
| Fusion Masques | Masques finaux = zones spéciales préservées + auto-material |

---

## 2. Installation et démarrage

### Prérequis

```
Python 3.10+
```

### Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install streamlit pillow numpy scipy matplotlib pandas opencv-python
streamlit run app.py
```

L'application s'ouvre sur `http://localhost:8501`.

---

## 3. Architecture du projet

```
Map generator/
│
├── app.py                          # Interface Streamlit — point d'entrée unique
├── pipeline_core.py                # TexturePipeline — cœur algorithmique (sans UI)
├── biomes.json                     # Biomes climatiques (palettes de stems + pondérations)
├── material_library_vanilla.json   # Bibliothèque matériaux Reforger vanilla (globale)
├── base_map.py                     # BaseMap : heightmap + pentes + biomes + distance eau
├── naturemap_biomes_generator.py   # NatureMapBiomesGenerator : carte biomes complète
├── reforger_texture_budget.py      # Budget QTRE, masques morpho, lecture TMAT, SatMap
├── vegetation_generator.py         # VegetationGenerator : carte végétation potentielle
│
└── data/
    └── projects/
        └── <nom>/
            ├── project.json
            ├── sources/                    # Fichiers sources obligatoires
            │   ├── heightmap.png           # Heightmap importée (PNG 16-bit)
            │   ├── slope.png               # Masque Instant Terra — pentes
            │   ├── curvature.png           # Masque Instant Terra — courbure
            │   ├── sediment.png            # Masque Instant Terra — sédiments
            │   └── reforger/               # Données Reforger liées au projet
            │       ├── terrain.tern
            │       ├── terrain.tmat
            │       └── export_masks/       # Masques exportés depuis Workbench
            ├── generated/                  # Sorties générées par l'outil
            │   ├── terrain_masks/          # Masques PNG 16-bit prêts pour Reforger
            │   └── previews/               # Aperçus PNG basse résolution
            ├── pipeline_temp/              # NPY intermédiaires (auto-supprimés après run)
            │   ├── 01_Raw_Matrices/
            │   └── 02_Masks_NPY/
            ├── reports/                    # Logs horodatés par run
            │   └── run_YYYYMMDD_HHMMSS/
            │       └── map_parameters.txt
            └── snapshots/
```

---

## 4. Gestion de projets

Chaque projet est un dossier dans `data/projects/<nom>/` contenant un fichier `project.json`.

### Structure de project.json

```json
{
  "project": { "name": "...", "author": "..." },
  "assets": {
    "heightmap": { "filename": "...", "format": "asc", "cellsize": 1.0,
                   "width": 8193, "height": 8193,
                   "alt_min": -32.25, "alt_max": 399.81 },
    "it_masks": {
      "slopes":    "sources/import instant/slopes.png",
      "curvature": "sources/import instant/mask_curv.png",
      "sediment":  "sources/import instant/mask_sediment.png"
    }
  },
  "reforger_grid": {
    "tiles": [64, 64],
    "blocks_per_tile": [4, 4],
    "tile_size_m": [128, 128],
    "block_size_m": [32, 32],
    "surface_total_px": [16257, 16257]
  },
  "terr_project_path": "I:\\..."
}
```

> **Migration automatique :** Les anciens projets sont convertis automatiquement au chargement.

---

## 5. Interface — Barre latérale

- **Sélectionner ou créer un projet**
- **Charger la heightmap** (ASC / PNG 8 ou 16-bit)
- Métriques du projet : dimensions, altitudes, taille terrain
- Chemin du projet Workbench `.terr`
- Export heightmap (PNG 8-bit, PNG 16-bit, ASC)
- **🗺️ Masques Instant Terra** — chemins vers les 3 masques IT (voir section ci-dessous)
- **📚 Bibliothèque de matériaux** — éditeur vanilla + custom (voir section 9)

### Masques Instant Terra

Trois champs de chemin permettent d'associer des masques exportés depuis **Instant Terra** :

| Champ | Fichier attendu | Encodage |
|-------|-----------------|----------|
| Slope 0–90° (continu) | `slopes.png` | 0 = 0°, 1 = 90°, valeurs continues |
| Curvature (crêtes/creux) | `mask_curv.png` | 0.5 = neutre, sombre = concave, clair = convexe |
| Sediment (dépôts) | `mask_sediment.png` | 0 = aucun, 1 = accumulation maximale |

**Résolution requise :** même résolution que la heightmap (ex. 8193×8193 pour une carte 8 km à 1 m/px).

Ces masques sont la **source de vérité prioritaire** du pipeline texture. Si un masque est absent, le pipeline repasse en mode fallback (calcul approché depuis la heightmap).

---

## 6. Onglet Terrain

### 🎨 Hypsométrique

Colormap basée uniquement sur l'altitude, avec hillshade optionnel (ombrage directionnel, intensité réglable).

**Sortie :** PNG horodaté dans `output/`

---

### 📈 Analyse

Statistiques complètes : dimensions, altitudes min/max, distribution (histogramme), distribution des pentes, paramètres grille Reforger.

---

## 7. Onglet Génération

### 🖼️ Aperçu Texture

Pipeline morphologique complet de génération de textures terrain, en **2 passes**.

**Profils climatiques :** Tempéré, Aride, Continental, Tropical, Subarctique, Alpin

---

#### Architecture 2 passes

**Passe 1 — Textures de base**

Textures de fond qui couvrent 100 % du terrain :

| Rôle | Texture type | Signaux principaux |
|------|--------------|--------------------|
| fond_marin | SeaBed | Zone sous l'eau |
| cotier | Grass coastal | Distance à la mer |
| galets | Pebbles | Zone côtière basse |
| prairie | Grass | Altitude basse, humide |
| herbe_dense | Grass dense | Altitude basse–moy. |
| lande | MountainGrass | Altitude élevée |
| heather | Heather | Altitude élevée + convexité |

**Passe 2 — Textures d'érosion (surcharge proportionnelle la passe 1)**

Textures "événementielles" pilotées par les masques Instant Terra :

| Rôle | Texture type | Signal IT principal |
|------|--------------|---------------------|
| roche | Rock | `slopes` > 30° + `curvature` convexe (crêtes) |
| debris_rock | Debris Rock | Frange du seuil roche + `curvature` concave (crevasses) + flancs de talweg |
| erosion | Dirt | Fond de talweg (`curvature` concave × `sediment`) |

**Pipeline passe 2 (masques IT présents) :**
```
slopes.png    → roche (pentes raides) + debris (frange + crevasses)
mask_curv.png → roche convexe (crêtes/éperons)
              → erosion concave (fond de ravine)
              → debris flancs (talweg)
mask_sediment → renforce erosion au fond des talwegs
rough_n       → jitter organique (micro-détail, évite les fronts rectilignes)
```

**Propagation de transition :** les zones rocheuses/debris se propagent sur les plateaux adjacents (~40 m) avec un jitter organique pour éviter les frontières géométriques aux bords de falaise.

**Budget QTRE :** max 5 textures par bloc 32 m (configurable à 7 pour Zimnitrita). Zeroing des textures non retenues, renormalisation pixel par pixel.

**Sortie :** aperçu RGB en session + masques PNG dans `generated/terrain_masks/`

---

### 🌱 Végétation

Génère une carte 2D des types de végétation potentielle basée sur les signaux morphologiques.

**Prérequis :** L'Aperçu Texture doit avoir été généré (charge les signaux terrain).

**Types de zones (splines fermées dans Reforger) :**

| Type | Prefabs correspondants | Signaux principaux |
|------|------------------------|-------------------|
| Forêt de bouleaux | FG_Forest_Birch, Pioneer_Birch | Altitude basse–moyenne |
| Forêt de pins | FG_Forest_Pine 1/2/3 | Altitude basse–moy., exposition sud |
| Forêt d'épicéas | FG_Forest_Spruce 1/2/3 | Altitude moy.–haute, exposition nord |
| Forêt mixte | FG_Forest_MixedBirchPine | Transition, pente douce |
| Forêt de charmes | FG_Forest_Hornbeam | Altitude basse, humide, nord |
| Clairière | FG_Forest_Clearing | Tout terrain, quasi plat |
| Maquis dense | FG_Brushland_Dense, Sorbus_Dense | Altitude moy., pente modérée |
| Maquis sparse | FG_Brushland_Sparse | Altitude moy.–haute, pentes raides |
| Épicéa montagne | FG_Brushland_Picea_Mountain | Haute altitude |
| Saule / zone humide | FG_Brushland_Salix | Altitude basse, flow élevé |
| Roseaux | FG_Brushland_Phragmites | Bord d'eau direct (< 80 m) |
| Genévrier | FG_Brushland_JuniperusPinus | Pentes raides, exposition sud, sec |
| Pierres | FG_BeachStone_Dense/Sparse | Côtier, lit de rivière, pied de roche |

**Types linéaires (splines ouvertes dans Reforger) :**

| Type | Prefabs | Condition |
|------|---------|-----------|
| Haie noisetier | PG_Bushline_Corylus | Bordure zones agricoles |
| Roseaux linéaires | PG_Bushline_Phragmites | Axe de flow élevé |
| Lisière | PG_Treeline_Birch | Transition forêt/clairière |

**Options :**
- Dégradé aux frontières (blend) ou couleur franche
- Score minimum d'apparition (0.05 – 0.50)
- Exclusion des zones verrouillées (champs, urbain) depuis masques exportés
- Résolution de sortie : 512 / 1024 / 2048 / 4096 px

**Sortie :** PNG horodaté + légende complète + export téléchargeable

---

## 8. Onglet Calques & Export

### 🖼️ Calque Texture

Affichage et export des masques morphologiques générés par l'Aperçu Texture.  
Export PNG 16-bit par rôle, nommé `{numéro}_{rôle}_{emat}.png`.

---

### 🎨 Calque TMAT

Lit les fichiers binaires `.ttile` / `.terr` générés par l'Enfusion Workbench.

- Scan du dossier `.terr`, lecture structure TMAT binaire
- Auto-détection grille (bx/by réels)
- Affichage RGB blendé par matériau
- Diagnostic résiduel : détection des blocs avec matériau < seuil

---

### 🛰️ Calque SatMap

Génère une SatMap cohérente en tuilant les textures BCRMiddleMap de chaque matériau.

Pipeline : BCRMiddleMap → colorisation par MiddleColor → blend par masque de surface → segmentation K-means → masques SatMap PNG.

---

### 🗺️ Carte Reconstruction

Reconstruit une vue aérienne colorée depuis les masques exportés de Workbench.

**Algorithme :** `couleur_px = Σ(masque_i × couleur_i) / Σ(masque_i)`

**Overlay de zones :** détection automatique (urbain, agriculture, forêt, roche, eau…) superposée en semi-transparent.

---

### 🔀 Fusion Masques

Combine masques exportés (zones spéciales peintes manuellement dans Workbench) et auto-material (zones naturelles générées).

```
lock_mask = union des masques verrouillés (urbain, champs…) > seuil
free_mask = ~lock_mask

Verrouillé → masque exporté Workbench conservé
Naturel    → masque généré × free_mask
```

**Sortie :** ZIP de tous les masques PNG, prêts pour import Workbench.

---

## 9. Bibliothèque de matériaux

La bibliothèque remplace le mapping hardcodé `stem → rôle`. Elle est en deux parties :

**`data/material_library_vanilla.json`** — Matériaux Reforger vanilla, partagés entre tous les projets. Éditables via la sidebar (ajout, suppression de rôles et matériaux).

**`data/projects/<nom>/material_library_custom.json`** — Matériaux spécifiques au projet. Complète vanilla ; même stem → custom remplace vanilla.

**Fusion au chargement du projet :**
- Rôles : union vanilla + custom (pas de doublon sur `id`)
- Matériaux : custom en tête, stems custom écrasent vanilla

**`mat_to_role()`** — Matching case-insensitive par préfixe (ordre spécifique → générique).

---

## 10. Modules Python

### base_map.py — BaseMap

Source unique de vérité. Charge la heightmap une fois, précalcule toutes les données dérivées (pentes Sobel, flow accumulation multi-échelle, masques biomes, distance eau, rugosité locale `rough_n`).

### naturemap_biomes_generator.py — NatureMapBiomesGenerator

Génère la carte biomes RGB. Stocké en `session_state.nat_gen` après génération de l'Aperçu Texture — réutilisé par l'onglet Végétation.

### reforger_texture_budget.py

Module central du pipeline texture. Budget QTRE, lecture TMAT, rendu SatMap, mapping matériaux → rôles.

Fonctions clés : `compute_texture_scores()`, `_score_base_textures()`, `_score_erosion_textures()`, `_combine_passes()`, `apply_block_budget()`, `read_tmat_grid()`, `render_tmat_rgb_blended()`, `mat_to_role()`, `set_runtime_library()`.

### vegetation_generator.py — VegetationGenerator

Génère les scores de végétation potentielle par pixel depuis les signaux morphologiques.

```python
vgen = VegetationGenerator(nat_gen, cell_m)
scores = vgen.compute(mask_water, lock_masks=None)
rgb    = vgen.render_rgb(scores, mask_water=mask_water, min_score=0.15, blend=True)
```

---

## 11. Formats supportés

### Heightmap (entrée)

| Format | Extension | Notes |
|--------|-----------|-------|
| ESRI ASCII Grid | `.asc` | **Recommandé** — altitudes réelles + cellsize |
| PNG 16-bit | `.png` | 0–65535 → bonne précision |
| PNG 8-bit | `.png` | 0–255 → faible précision |

### Masques Instant Terra (entrée)

| Masque | Format | Encodage |
|--------|--------|----------|
| slopes.png | PNG 16-bit grayscale | 0 = plat (0°), 65535 = vertical (90°) |
| mask_curv.png | PNG 16-bit grayscale | 32767 = neutre, bas = concave, haut = convexe |
| mask_sediment.png | PNG 16-bit grayscale | 0 = aucun dépôt, 65535 = accumulation max |

### Masques surface (sortie)

| Format | Usage |
|--------|-------|
| PNG 16-bit grayscale | Masques haute précision pour Workbench |
| PNG 8-bit grayscale | Masques légers |

### Fichiers Workbench (lecture seule)

| Format | Description |
|--------|-------------|
| `.ttile` | Tuile TMAT binaire |
| `.terr` | Projet terrain Enfusion |
| `.emat` | Matériau terrain |

---

## 12. Workflows

### Workflow 1 — Pipeline Texture automatique (nouveau pipeline)

```
1. Créer/ouvrir un projet
2. Onglet Texture Pipeline → si heightmap absente : importer le fichier source
   (ASC, PNG) via le bouton "Convertir et importer" → sauvegardé en sources/heightmap.png
3. Vérifier le statut des sources (✅/⚠️ pour chaque signal)
4. Choisir un biome climatique (default, temperate_volcanic, arctic…)
5. Cliquer "Lancer le Pipeline Complet"
   → Masques PNG 16-bit générés dans generated/terrain_masks/
   → Logs dans reports/run_YYYYMMDD_HHMMSS/
6. Importer les masques dans Workbench
```

---

### Workflow 2 — Génération avec masques Instant Terra (qualité maximale)

```
1. Créer/ouvrir un projet → charger la heightmap
2. Dans Instant Terra, exporter 3 masques à la résolution exacte de la heightmap :
   - Slope map (0–90°, normalisé 0–1) → slopes.png
   - Curvature map (centré 0.5) → mask_curv.png
   - Sediment / flow accumulation → mask_sediment.png
3. Sidebar → section "Masques Instant Terra" : renseigner les 3 chemins
4. Sauvegarder le projet (les chemins sont persistés dans project.json)
5. Onglet Génération → Aperçu Texture : générer
   → Le pipeline utilise automatiquement les masques IT comme source primaire
6. Onglet Calques & Export → Calque Texture : exporter les masques PNG
7. Importer dans Workbench
```

---

### Workflow 3 — Carte de végétation

```
1. Générer l'Aperçu Texture (charge les signaux terrain)
2. Onglet Génération → Végétation :
   - Optionnel : activer l'exclusion des zones verrouillées
   - Ajuster score minimum et résolution
   - Générer la carte
3. Utiliser la carte comme référence visuelle pour placer
   les splines WEGenerators dans Reforger Workbench
```

---

### Workflow 4 — Fusion masques Workbench + auto-material

```
1. Exporter les masques depuis Workbench
   → placer dans sources/export mask text/
2. Onglet Calques & Export → Carte Reconstruction :
   - Générer la carte de reconstruction
   - Générer l'overlay de zones
3. Onglet Génération → Aperçu Texture : générer l'auto-material
4. Onglet Calques & Export → Fusion Masques :
   - Vérifier la classification verrouillé / naturel
   - Générer et télécharger le ZIP
5. Importer les masques fusionnés dans Workbench
```

---

## 13. Dépannage

**`DecompressionBombError` (PIL)**  
Les masques Workbench peuvent dépasser 179 Mpx. `Image.MAX_IMAGE_PIXELS = None` est appliqué automatiquement.

**Végétation : "Générez d'abord l'Aperçu Texture"**  
L'onglet Végétation nécessite `nat_gen` en session. Générer l'Aperçu Texture d'abord.

**`ValueError: shapes cannot be broadcast`**  
Les masques exportés (16257²) sont automatiquement redimensionnés à la résolution de la heightmap avant usage.

**Masques IT ignorés (pipeline en mode fallback)**  
Vérifier que les chemins sont corrects dans la sidebar et que les fichiers font exactement la même résolution que la heightmap. Sauvegarder le projet après avoir renseigné les chemins.

**Migration ancien format projet**  
Automatique au chargement. Utiliser "Sauvegarder le projet" pour persister les valeurs recalculées.

**App Streamlit ne démarre pas**  
```powershell
.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

---

*Map Generator Pro v5.2 — Développé par [otea] Giorbev with Claude AI*
