# Mapping Final — Catalogue Textures Reforger

**Date** : 2026-07-03  
**Statut** : ✅ 60/60 surfaces résolues (100%)

---

## 📊 Statistiques

```
Total surfaces:        60
Fallback magenta:      0

RÉSOLUTION COULEURS:
  Auto PNG middle:     42 (calcul automatique)
  Couleurs manuelles:  18 (override hex)
  Héritages zi_:       3  (copie parent vanilla)

SOURCES PNG:
  Vanilla/textures/:   59
  Customs/Textures/:   1
```

---

## 🎨 Couleurs manuelles (18)

### Dirt (3)

| .emat | Hex | RGB | Raison |
|-------|-----|-----|--------|
| `Dirt_01.emat` | `#2d2318` | [45, 35, 24] | Sol terre sombre |
| `Dirt_02.emat` | `#2d1f12` | [45, 31, 18] | Sol terre brun |
| `Dirt_03.emat` | `#433b31` | [67, 59, 49] | Sol érosion gris |

### Forest Clearing (4)

| .emat | Hex | RGB | Raison |
|-------|-----|-----|--------|
| `ForestClearing_Coniferous_01.emat` | `#291e15` | [41, 30, 21] | Clairière conifères |
| `ForestClearing_Coniferous_01_aut.emat` | `#291e15` | [41, 30, 21] | Clairière automne |
| `ForestClearing_Deciduous_01.emat` | `#20160e` | [32, 22, 14] | Clairière feuillus |
| `ForestClearing_Deciduous_01_aut.emat` | `#241810` | [36, 24, 16] | Clairière automne |

### Forest Coniferous (4)

| .emat | Hex | RGB | Raison |
|-------|-----|-----|--------|
| `ForestConiferous_01_Base.emat` | `#251a12` | [37, 26, 18] | Sol pins dense |
| `ForestConiferous_01_Base_aut.emat` | `#251a12` | [37, 26, 18] | Sol pins automne |
| `ForestConiferous_02.emat` | `#251a12` | [37, 26, 18] | Sol pins var. 2 |
| `ForestConiferous_02_aut.emat` | `#251a12` | [37, 26, 18] | Sol pins aut. 2 |

### Forest Deciduous (4)

| .emat | Hex | RGB | Raison |
|-------|-----|-----|--------|
| `ForestDeciduous_01_Base.emat` | `#301e16` | [48, 30, 22] | Sol feuillus base |
| `ForestDeciduous_01_Base_aut.emat` | `#281a0c` | [40, 26, 12] | Sol feuillus automne |
| `ForestDeciduous_02.emat` | `#301e16` | [48, 30, 22] | Sol feuillus var. 2 |
| `ForestDeciduous_02_aut.emat` | `#241d0d` | [36, 29, 13] | Sol feuillus aut. 2 |

### Forest Pine (2)

| .emat | Hex | RGB | Raison |
|-------|-----|-----|--------|
| `ForestPine_01_Base.emat` | `#1d140c` | [29, 20, 12] | Sol sapins base |
| `ForestPine_01_Base_aut.emat` | `#1d180c` | [29, 24, 12] | Sol sapins automne |

### Autres (1)

| .emat | Hex | RGB | Raison |
|-------|-----|-----|--------|
| `SulfurStream_01_bed.emat` | `#a47012` | [164, 112, 18] | Lit rivière sulfureuse (orange) |

---

## 🗺️ Mappings PNG (61 entrées)

### Vanilla → Vanilla (56)

**Grass variantes** :
- `Grass_02.emat` → `Grass_01_Middle_BCR.jpg` (même texture)
- `Grass_02_aut.emat` → `Grass_02_Middle_aut_BCR.jpg`
- `Grass_03_coastal.emat` → `Grass_03_Middle_BCR.jpg`

**Concrete variantes** :
- `Concrete_02.emat` → `Concrete_01_Middle_BCR.jpg`

**Cobblestone renommage** :
- `Cobblestone_01_Wave.emat` → `WaveCobblestone_01_Middle_BCR.jpg`
- `Cobblestone_01_Wave_V2.emat` → `WaveCobblestone_01_Middle_BCR.jpg`

**Forest → Dirt** (14 textures) :
- Toutes les `Forest*` → `Dirt_01_Middle_BCR.jpg`
- Raison : Sol de forêt = terre/humus sombre

**Rock** :
- `Rock_01.emat` → `Debris_Rock_01_Middle_BCR.jpg`

**MountainGrass renommage** :
- `MountainGrass_01.emat` → `Grass_Mountain_01_Middle_BCR.jpg`
- `MountainGrass_02.emat` → `MountainGrass_Middle_02_BCR.jpg`
- `MountainGrass_03.emat` → `MountainGrass_Middle_03_BCR.jpg`

**Pebbles partagé** :
- `Pebbles_01.emat` → `Pebbles_02_Middle_BCR.jpg`

**Debris partagés** :
- `Debris_Coal_01.emat` → `Debris_Coal_02_Middle_BCR.jpg`
- `Debris_Coal_03.emat` → `Debris_Coal_02_Middle_BCR.jpg`

**Autres** :
- `Dirt_02.emat` → `Dirt_01_Middle_BCR.jpg`
- `SulfurStream_01_bed.emat` → `Dirt_01_Middle_BCR.jpg` (+ couleur manuelle)
- `default.emat` → `Grass_01_Middle_BCR.jpg`

### Customs → Vanilla (4)

| .emat custom | PNG vanilla | Raison |
|--------------|-------------|--------|
| `ZI_Crop_Field_03.emat` | `Crop_Field_01_Middle_BCR.jpg` | Même champ var. 3 |
| `ZI_Crop_Field_04.emat` | `Crop_Field_02_Middle_BCR.jpg` | Même champ var. 4 |
| `ZI_Crop_Field_Cut_01.emat` | `Crop_Field_01_Middle_BCR.jpg` | Champ coupé var. 1 |
| `ZI_Crop_Field_Cut_02.emat` | `Crop_Field_02_Middle_BCR.jpg` | Champ coupé var. 2 |

### Customs → Customs (1)

| .emat custom | PNG custom | Raison |
|--------------|------------|--------|
| `ZI_Ground_Sport_01.emat` | `zi_ground_sport_midle.jpg` | Terrain de sport custom |

---

## 🔗 Héritages zi_ automatiques (3)

| .emat custom | Parent vanilla | Résolution |
|--------------|----------------|------------|
| `ZI_Crop_Field_01.emat` | `Crop_Field_01.emat` | Convention zi_ → héritage auto |
| `ZI_Crop_Field_02.emat` | `Crop_Field_02.emat` | Convention zi_ → héritage auto |
| `ZI_Rock_01.emat` | `Rock_01.emat` | Convention zi_ → héritage auto |

---

## 📁 Fichiers sources

### Structure

```
data/Textures_ArmaReforger/
├── texture_mapping.json       # 61 mappings + 18 couleurs
├── catalog.json               # Catalogue généré (60 entrées)
├── Vanilla/
│   ├── *.emat (52)
│   └── textures/
│       └── *_Middle_BCR.jpg (27 PNG uniques)
└── Customs/
    ├── *.emat (8)
    └── Textures/
        └── zi_ground_sport_midle.jpg
```

### PNG middle uniques utilisés

**Vanilla** : ~27 PNG partagés entre 52 .emat
- `Grass_01_Middle_BCR.jpg` → utilisé par Grass_01, Grass_02, default
- `Dirt_01_Middle_BCR.jpg` → utilisé par Dirt_01, Dirt_02, toutes Forest, SulfurStream
- `Concrete_01_Middle_BCR.jpg` → utilisé par Concrete_01, Concrete_02
- etc.

**Customs** : 1 PNG
- `zi_ground_sport_midle.jpg` → utilisé par ZI_Ground_Sport_01

---

## 🎯 Raisons des couleurs manuelles

### Pourquoi 18 couleurs manuelles ?

Les textures **Forest** et **Dirt** ont des PNG middle BCR qui représentent la **texture de surface** (terre, humus), mais dans Reforger ces textures ont des **teintes spécifiques** pour différencier :

- **Type de forêt** : Conifères (vert foncé), Feuillus (brun), Pins (très sombre)
- **Saison** : Base (normal), Automne (plus orangé)
- **Type de sol** : Dirt_01 (sombre), Dirt_02 (brun), Dirt_03 (gris érosion)

Les couleurs manuelles représentent les **teintes finales** telles qu'elles apparaissent dans le jeu, après application des **tints** et **color grading** du moteur Enfusion.

---

## ✅ Validation

### Tests effectués

```bash
# Scan complet
python test_satmap_catalog.py
✅ 60/60 surfaces, 0 fallback

# Vérification couleurs manuelles
python verify_manual_colors.py
✅ 18/18 couleurs correctes (match hex exact)

# Vérification PNG sources
✅ Tous les PNG référencés existent
✅ Tous les mappings cross-folder résolus
```

### Prochaine étape

**Vérification .terr** dans l'UI :
```
I:/reforger_travail/Zimnitrita_map/World/Zimnitrita/Terrain/Terrain.terr
```

Toutes les surfaces du .terr devraient être trouvées dans le catalogue ✅

---

## 📚 Références

- [texture_mapping.json](texture_mapping.json) — Fichier mapping source
- [catalog.json](catalog.json) — Catalogue généré
- [SATMAP_CORRECTIONS_SESSION2.md](../../Docs/SATMAP_CORRECTIONS_SESSION2.md) — Historique corrections
