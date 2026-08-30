# Diagrammes Architecture — Map Generator Pro v7.0

**Représentations visuelles** de l'architecture et des flux de données

---

## 📐 Architecture globale

```
┌─────────────────────────────────────────────────────────────────┐
│                         APP.PY (Streamlit)                      │
│                     Hub central navigation                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
                ▼               ▼               ▼
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │   Onglets    │ │   Données    │ │   Projets    │
        │     UI       │ │   Terrain    │ │   Config     │
        └──────────────┘ └──────────────┘ └──────────────┘
                │               │               │
    ┌───────────┴───────┐       │       ┌───────┴────────┐
    │                   │       │       │                │
    ▼                   ▼       ▼       ▼                ▼
┌──────────┐    ┌──────────────────────────┐    ┌──────────────┐
│ Heightmap│    │   terrain_analysis.py    │    │project.json  │
│ Satmap   │    │  (compute_terrain_data)  │    │surfaces.json │
│ Pipeline │    └──────────────────────────┘    └──────────────┘
│ Terrain  │                │
│ Validation│              ▼
└──────────┘    ┌──────────────────────┐
                │  CACHE NPZ + JSON    │
                │ terrain_data.npz     │
                │ terrain_meta.json    │
                └──────────────────────┘
```

---

## 🏗️ Modules métier — Couches logiques

```
┌─────────────────────────────────────────────────────────────────┐
│                        COUCHE PRÉSENTATION                       │
│  app.py + tab_*.py (Streamlit UI)                               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        COUCHE MÉTIER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ pipeline_v5  │  │  satmap_v2   │  │  validation  │          │
│  │  (terrain)   │  │  (textures)  │  │   (checks)   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        COUCHE DONNÉES                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  base_map    │  │   terrain_   │  │   edds_      │          │
│  │  (heightmap) │  │   analysis   │  │   decoder    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        COUCHE PERSISTANCE                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   .ttile     │  │    .terr     │  │   .edds      │          │
│  │  (blocs)     │  │  (config)    │  │  (textures)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │ project.json │  │  cache.npz   │                             │
│  └──────────────┘  └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Pipeline V5 — Flux complet

```
ENTRÉE                    PIPELINE V5                    SORTIE
════════                  ═══════════                    ══════

┌──────────┐
│Heightmap │
│  .asc    │
└────┬─────┘
     │
     ▼
┌──────────────────┐
│ MODULE 1         │────┐
│ Lecture .asc     │    │
│ • load_asc()     │    │
└──────────────────┘    │
                        │
                        ▼
                   ┌─────────────────┐
                   │ heightmap (H×W) │
                   │ meta (cellsize) │
                   └────────┬────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │ MODULE 2         │
                   │ Calcul terrain   │
                   │ • slope          │
                   │ • curvature      │
                   │ • TPI            │
                   │ • flow           │
                   │ • coastal        │
                   └────────┬─────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ MODULE 3     │   │ MODULE 4     │   │ Gaea inputs  │
│ Masques base │   │ Végétation   │   │ (optionnel)  │
│ • seabed     │   │ • prairie    │   │ • flow       │
│ • coastal    │   │ • maquis     │   │ • deposit    │
│ • rock       │   │ • alpages    │   └──────┬───────┘
│ • landes     │   │ • forêts     │          │
└──────┬───────┘   └──────┬───────┘          │
       │                   │                  │
       └───────────────────┴──────────────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ 13 MASQUES       │
                  │ uint16 (0-65535) │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ MODULE 5         │
                  │ Exclusion mask   │◄───── exclusion.png
                  │ Zone B preservée │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ MODULE 6         │
                  │ Normalisation    │
                  │ exclusive        │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ MODULE 7         │
                  │ Arbitrage budget │
                  │ par bloc         │
                  │ (6 slots max)    │
                  └────────┬─────────┘
                           │
               ┌───────────┴───────────┐
               │                       │
               ▼                       ▼
      ┌──────────────┐        ┌──────────────┐
      │ MODULE 8     │        │ MODULE 9     │
      │ Preview PNG  │        │ Export       │
      │ (colorisé)   │        │ • PNG        │
      └──────┬───────┘        │ • .ttile     │
             │                └──────┬───────┘
             │                       │
             ▼                       ▼
    ┌────────────────┐      ┌────────────────┐
    │ preview.png    │      │ 01_seabed.png  │
    │ (satmap-like)  │      │ 02_coastal.png │
    │                │      │ ...            │
    │                │      │ 13_foret.png   │
    └────────────────┘      └────────────────┘
                                     │
                                     ▼
                            ┌────────────────┐
                            │ Terrain/.Data/ │
                            │ xxxx_yyyy.ttile│
                            │ (binaire IFF)  │
                            └────────────────┘
```

---

## 🗄️ Structure fichier .ttile (IFF)

```
.ttile (binaire IFF)
═══════════════════

┌────────────────────────────────┐
│ HEADER IFF                     │
│ ┌────────────────────────────┐ │
│ │ "FORM"  (4 bytes)          │ │
│ │ size    (4 bytes big-end)  │ │
│ │ type    (4 bytes)          │ │
│ └────────────────────────────┘ │
└────────────────────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ CHUNK "LRS2"                   │  ← Index matériaux
│ ┌────────────────────────────┐ │
│ │ tag:   "LRS2"              │ │
│ │ size:  variable            │ │
│ │ data:                      │ │
│ │   ┌────────────────────┐   │ │
│ │   │ Entry 1            │   │ │
│ │   │ ├─ index: 0x1234   │   │ │ (bx=52, by=36)
│ │   │ ├─ count: 4        │   │ │
│ │   │ └─ mats: [1,3,8,16]│   │ │
│ │   ├────────────────────┤   │ │
│ │   │ Entry 2            │   │ │
│ │   │ ...                │   │ │
│ │   └────────────────────┘   │ │
│ └────────────────────────────┘ │
└────────────────────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ CHUNK "GCTD"                   │  ← Grilles 45×45
│ ┌────────────────────────────┐ │
│ │ tag:   "GCTD"              │ │
│ │ size:  variable            │ │
│ │ data:                      │ │
│ │   ┌────────────────────┐   │ │
│ │   │ header (2 bytes)   │   │ │
│ │   ├────────────────────┤   │ │
│ │   │ Section 1          │   │ │
│ │   │ ├─ bx: 52          │   │ │
│ │   │ ├─ by: 36          │   │ │
│ │   │ └─ grid: 45×45     │   │ │
│ │   │    [2026 bytes]    │   │ │
│ │   │    ┌────────────┐  │   │ │
│ │   │    │ Encodage   │  │   │ │
│ │   │    │ 4 slots +  │  │   │ │
│ │   │    │ sub-index  │  │   │ │
│ │   │    └────────────┘  │   │ │
│ │   ├────────────────────┤   │ │
│ │   │ Section 2          │   │ │
│ │   │ ...                │   │ │
│ │   └────────────────────┘   │ │
│ └────────────────────────────┘ │
└────────────────────────────────┘
```

### Détail encodage GCTD (grille 45×45)

```
Grille 45×45 = 2025 cellules
Encodage : 4 slots + sub-index

┌────────────────────────────────────────┐
│ Cellule GCTD (1 byte)                  │
│                                        │
│  7   6   5   4   3   2   1   0  (bits)│
│ ┌───┬───┬───┬───┬───┬───┬───┬───┐    │
│ │ s │ s │ s │ s │ i │ i │ i │ i │    │
│ └───┴───┴───┴───┴───┴───┴───┴───┘    │
│   └───────┬───────┘ └───────┬─────┘  │
│         slot            sub-index     │
│        (4 bits)          (4 bits)     │
│        0-15              0-15          │
└────────────────────────────────────────┘

Exemple :
  byte = 0x23  (0010 0011)
  → slot      = 2   (bits 7-4)
  → sub-index = 3   (bits 3-0)
  → Matériau réel = LRS2[slot] avec variation sub

Si slot = 2 et LRS2 = [1, 3, 8, 16, 0, 0]
→ mat_id = 8 (3ème élément de LRS2)
→ sub-index = 3 (variation texture locale)
```

---

## 🎨 Arbitrage budget QTRE

```
ARBITRAGE PAR BLOC (6 slots max)
═════════════════════════════════

Entrée : 13 masques × priorités
                │
                ▼
┌───────────────────────────────────┐
│ Pour chaque bloc 128×128 px       │
│ (découpage heightmap 16k / 128)   │
└───────────────────────┬───────────┘
                        │
                        ▼
        ┌───────────────────────────┐
        │ Extraire région 128×128   │
        │ pour les 13 masques       │
        └───────────┬───────────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │ Comptage matériaux actifs │
        │ (poids > 0 dans masque)   │
        └───────────┬───────────────┘
                    │
                    ▼
              ╔═════════════╗
              ║ > 6 slots ? ║
              ╚═════╤═══════╝
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼ OUI                   ▼ NON
┌──────────────────┐    ┌──────────────────┐
│ ARBITRAGE        │    │ GARDER TOUS      │
│ ┌──────────────┐ │    │ (≤6 matériaux)   │
│ │1. Tri prio   │ │    └──────────────────┘
│ │   descendante│ │
│ ├──────────────┤ │
│ │2. Garder top │ │
│ │   6 matériaux│ │
│ ├──────────────┤ │
│ │3. Per-pixel: │ │
│ │   mat winner │ │
│ │   = max poids│ │
│ │   parmi top6 │ │
│ └──────────────┘ │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│ Grille 128×128   │
│ mat_id par pixel │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Downsampling     │
│ 128×128 → 45×45  │
│ (nearest)        │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Encodage GCTD    │
│ 4 slots + sub    │
└────────┬─────────┘
         │
         ▼
   [2026 bytes]
   → Section GCTD
```

---

## 🗺️ Organisation terrain Reforger

```
GRILLE GLOBALE (32×32 tuiles)
══════════════════════════════

┌─────────────────────────────────────────┐
│  0   1   2   3  ...              31    │ tx
│ ┌───┬───┬───┬───┬─ ─ ─ ─ ─ ─ ─┬───┐   │
│0│   │   │   │   │               │   │   │
│ ├───┼───┼───┼───┼─ ─ ─ ─ ─ ─ ─┼───┤   │
│1│   │   │   │   │               │   │   │
│ ├───┼───┼───┼───┼─ ─ ─ ─ ─ ─ ─┼───┤   │
│2│   │   │   │   │               │   │   │
│ ├───┼───┼───┼───┼─ ─ ─ ─ ─ ─ ─┼───┤   │
│.│   │   │   │   │               │   │   │
│.│   │   │   │   │               │   │   │
│.│   │   │   │   │               │   │   │
│ ├───┼───┼───┼───┼─ ─ ─ ─ ─ ─ ─┼───┤   │
│31  │   │   │   │               │   │   │
│ └───┴───┴───┴───┴─ ─ ─ ─ ─ ─ ─┴───┘   │
└─────────────────────────────────────────┘
              ty

TUILE (4×4 blocs)
═════════════════

Tuile (tx, ty)
┌─────────────────┐
│  0   1   2   3  │ local_bx
│ ┌───┬───┬───┬───┐
│0│ 0 │ 1 │ 2 │ 3 │
│ ├───┼───┼───┼───┤
│1│ 4 │ 5 │ 6 │ 7 │
│ ├───┼───┼───┼───┤
│2│ 8 │ 9 │10 │11 │
│ ├───┼───┼───┼───┤
│3│12 │13 │14 │15 │
│ └───┴───┴───┴───┘
  local_by

COORDONNÉES GLOBALES
════════════════════

bx = tx × 4 + local_bx
by = ty × 4 + local_by

Exemple : tuile (4, 27), bloc local (2, 3)
→ bx = 4×4 + 2 = 18
→ by = 27×4 + 3 = 111

Fichier : .Data/0012_006f.ttile
          (18 en hex = 0x12)
          (111 en hex = 0x6F)
```

---

## 🔄 Flux Satmap V2

```
GÉNÉRATION SATMAP V2 (photoréaliste)
════════════════════════════════════

ENTRÉE                PROCESS                    SORTIE
──────                ───────                    ──────

┌──────────┐
│ layer_0  │  ← Poids GPU
│  .edds   │     (H×W×7)
└────┬─────┘
     │
     ▼
┌────────────────┐
│ edds_decoder   │
│ extract_all_   │
│   weights()    │
└────────┬───────┘
         │
         ▼
    ┌─────────────┐
    │ Poids float │
    │ (H×W×7)     │
    │ normalisé   │
    └─────┬───────┘
          │
          ▼
    ┌──────────────┐
    │ Pour chaque  │
    │ bloc (128×128)│
    └──────┬───────┘
           │
   ┌───────┴────────┐
   │                │
   ▼                ▼
┌────────┐    ┌──────────┐
│ .ttile │    │ catalog  │
│ LRS2   │    │ .json    │
└───┬────┘    └────┬─────┘
    │              │
    └──────┬───────┘
           │
           ▼
    ┌──────────────────┐
    │ Mat IDs actifs   │
    │ [1, 3, 8, 16]    │
    └────────┬─────────┘
             │
             ▼
    ┌─────────────────────┐
    │ MODE ?              │
    └─────┬───────────────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
COLORED     TEXTURED
    │           │
    ▼           ▼
┌─────────┐ ┌─────────────┐
│ Tint    │ │ Texture BCR │
│ sRGB    │ │ middle.edds │
└───┬─────┘ └──────┬──────┘
    │              │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Blending GPU │
    │ per-pixel    │
    │              │
    │ color =      │
    │ Σ(tex×weight)│
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Assembly     │
    │ blocs →      │
    │ image finale │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ satmap_v2    │
    │ 4097×4097.png│
    └──────────────┘
```

---

## 💾 Gestion cache terrain_data

```
CHARGEMENT PROJET
═════════════════

┌──────────────┐
│ load_project │
│   (app.py)   │
└──────┬───────┘
       │
       ▼
  ╔═══════════╗
  ║ Cache     ║
  ║ existe ?  ║
  ╚═══╤═══════╝
      │
  ┌───┴───┐
  │       │
  ▼ OUI   ▼ NON
┌────────────┐    ┌────────────────┐
│ Load cache │    │ compute_       │
│            │    │ terrain_data() │
│ ┌────────┐ │    │                │
│ │terrain_│ │    │ ~30-60s        │
│ │data.npz│ │    └────────┬───────┘
│ └────────┘ │             │
│ ┌────────┐ │             ▼
│ │terrain_│ │    ┌────────────────┐
│ │meta.   │ │    │ save_terrain_  │
│ │json    │ │    │ data_cache()   │
│ └────────┘ │    └────────┬───────┘
│            │             │
│ ~0.1s      │             ▼
└─────┬──────┘    ┌────────────────┐
      │           │ Cache créé     │
      │           │ • .npz (arrays)│
      │           │ • .json (meta) │
      │           └────────┬───────┘
      │                    │
      └────────┬───────────┘
               │
               ▼
      ╔════════════════╗
      ║ Validation     ║
      ║ • version ok ? ║
      ║ • mtime ok ?   ║
      ╚════════╤═══════╝
               │
          ┌────┴────┐
          │         │
          ▼ OK      ▼ INVALIDE
   ┌──────────┐   ┌──────────────┐
   │ Utiliser │   │ Supprimer    │
   │ cache    │   │ + recalculer │
   └──────────┘   └──────────────┘
```

### Invalidation cache

```
CONDITIONS INVALIDATION
═══════════════════════

1. Version pipeline changée
   ────────────────────────
   terrain_meta.json:
     "pipeline_version": "2.2.0"
   
   Code actuel:
     TERRAIN_PIPELINE_VERSION = "2.3.0"
   
   → MISMATCH → Supprimer cache

2. Heightmap modifiée
   ──────────────────
   mtime(heightmap.asc) > mtime(terrain_data.npz)
   
   → Cache obsolète → Supprimer cache

3. Cache corrompu
   ──────────────
   Erreur lecture .npz ou .json
   
   → Supprimer + recalculer
```

---

## 🔧 Outils CLI — Workflows

### Workflow 1 : Diagnostic complet

```
┌──────────────────────┐
│ check_terrain_health │
│   --addon-path       │
└──────────┬───────────┘
           │
           ▼
    ┌──────────────┐
    │ Scan .Data/  │
    │ tous .ttile  │
    └──────┬───────┘
           │
           ▼
    ┌──────────────────┐
    │ Pour chaque bloc │
    │ ┌──────────────┐ │
    │ │ Corrupted ?  │ │
    │ │ Empty ?      │ │
    │ │ Overbudget ? │ │
    │ │ LRS2≠GCTD ?  │ │
    │ └──────────────┘ │
    └──────┬───────────┘
           │
           ▼
    ┌──────────────┐
    │ Rapport HTML │
    │ health.json  │
    └──────────────┘
```

### Workflow 2 : Correction matériau global

```
┌──────────────────────┐
│ ttile_manager        │
│ --mode replace       │
│ --all                │
│ --old-mat 0          │
│ --new-mat 3          │
└──────────┬───────────┘
           │
           ▼
    ┌──────────────┐
    │ Scan Zone A  │
    │ (excl.mask)  │
    └──────┬───────┘
           │
           ▼
    ┌──────────────────┐
    │ Pour chaque bloc │
    │ ┌──────────────┐ │
    │ │ Backup .bak  │ │
    │ │ Parse LRS2   │ │
    │ │ Parse GCTD   │ │
    │ │ Replace mat  │ │
    │ │ Rebuild IFF  │ │
    │ │ Write .ttile │ │
    │ └──────────────┘ │
    └──────┬───────────┘
           │
           ▼
    ┌──────────────┐
    │ Rapport      │
    │ • blocs OK   │
    │ • blocs skip │
    │ • erreurs    │
    └──────────────┘
```

### Workflow 3 : Merge conditionnel

```
┌──────────────────────┐
│ merge_mat.py         │
│ --src 0,mat:9        │  ← "Remplacer 0 par 3
│ --dst 3              │     SEULEMENT où 9 présent"
│ --all                │
└──────────┬───────────┘
           │
           ▼
    ┌──────────────────┐
    │ Pour chaque bloc │
    │ ┌──────────────┐ │
    │ │ Parse GCTD   │ │
    │ │ Chercher mat │ │
    │ │ 9 dans grille│ │
    │ └──────┬───────┘ │
    │        │         │
    │   ╔════════════╗ │
    │   ║ Mat 9 ?    ║ │
    │   ╚════╤═══════╝ │
    │        │         │
    │   ┌────┴────┐   │
    │   │         │   │
    │   ▼ OUI     ▼ NON
    │ ┌─────┐  ┌─────┐│
    │ │Merge│  │Skip ││
    │ │0→3  │  │     ││
    │ └─────┘  └─────┘│
    └──────────────────┘
           │
           ▼
    ┌──────────────┐
    │ Rapport      │
    │ • merged: 45 │
    │ • skipped:983│
    └──────────────┘
```

---

## 🎯 Nomenclature coordonnées

```
COORDONNÉES MULTIPLES SYSTÈMES
═══════════════════════════════

┌────────────────────────────────────────┐
│ SYSTÈME 1 : Global blocs (bx, by)     │
│                                        │
│ Range: 0 ≤ bx,by < 128                │
│ (pour map 32×32 tuiles × 4×4 blocs)   │
│                                        │
│ Exemple : bx=18, by=111                │
│                                        │
└────────────────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────┐
│ SYSTÈME 2 : Tuile + local             │
│                                        │
│ tx = bx // 4                           │
│ ty = by // 4                           │
│ local_bx = bx % 4                      │
│ local_by = by % 4                      │
│                                        │
│ Exemple :                              │
│   bx=18 → tx=4, local_bx=2             │
│   by=111 → ty=27, local_by=3           │
│                                        │
└────────────────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────┐
│ SYSTÈME 3 : Nom fichier .ttile        │
│                                        │
│ Format: {bx:04x}_{by:04x}.ttile       │
│                                        │
│ Exemple :                              │
│   bx=18 (0x12) by=111 (0x6F)           │
│   → 0012_006f.ttile                    │
│                                        │
└────────────────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────┐
│ SYSTÈME 4 : Index LRS2 (packed)       │
│                                        │
│ index = bx | (by << 7)                 │
│                                        │
│ Exemple :                              │
│   bx=18, by=111                        │
│   index = 18 | (111 << 7)              │
│       = 18 | 14208                     │
│       = 14226 (0x3792)                 │
│                                        │
│ Extraction inverse:                    │
│   bx = index & 0x7F                    │
│   by = (index >> 7) & 0x7F             │
│                                        │
└────────────────────────────────────────┘
```

---

## 📊 Distribution matériaux — Analyse

```
ANALYSE DISTRIBUTION BLOC
═════════════════════════

Grille GCTD 45×45 = 2025 cellules
                │
                ▼
        ┌───────────────┐
        │ Comptage      │
        │ per-matériau  │
        └───────┬───────┘
                │
                ▼
┌───────────────────────────────────┐
│ Distribution                      │
│                                   │
│ mat_id  count   pct    slot      │
│ ──────────────────────────────────│
│   1     892    44.0%    0  ████  │
│   3     654    32.3%    1  ███   │
│   8     321    15.9%    2  ██    │
│  16     158     7.8%    3  █     │
│  ──────────────────────────────── │
│ Total: 2025   100.0%             │
│ Slots: 4 / 6                      │
│                                   │
└───────────────────────────────────┘
                │
                ▼
        ╔═══════════════╗
        ║ Budget OK ?   ║
        ║ (≤6 slots)    ║
        ╚═══╤═══════════╝
            │
       ┌────┴────┐
       │         │
       ▼ OUI     ▼ NON
   ┌────────┐ ┌──────────┐
   │ Garder │ │ Arbitrer │
   │ tous   │ │ top 6    │
   └────────┘ └──────────┘
```

---

**Document généré le** : 2026-08-14  
**Auteur** : Claude Code  
**Usage** : Référence visuelle architecture
