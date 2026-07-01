# Pipeline 11 Masks Continus — Zimnitrita

**Date génération** : 2026-06-11 17:33:26  
**Dossier export** : `h:\logiciel perso\Map generator\data\projects\Zimnitrita\pipeline_11masks_20260611_173326`

---

## 📊 Résultats Pipeline

### Terrain Source
- **Heightmap** : `temp_Terrain_modified3.asc`
- **Résolution** : 4097×4097 pixels
- **Cellsize** : 4m/px
- **Taille terrain** : 16.4 km × 16.4 km
- **Altitude** : -204.8m → 499.6m
- **Pente** : 0.0° → 88.0° (médiane 6.7°)

### Curvature
- **Source** : `curvature.png`
- **Range** : -17.0 → +17.0

---

## ⚙️ Paramètres Auto-Calibrés

| Paramètre | Valeur | Source |
|-----------|--------|--------|
| **coastal_alt_max_m** | 11.5m | P10 heightmap |
| **grass_low_max_m** | 38.4m | P30 heightmap |
| **grass_mid_max_m** | 102.6m | P66 heightmap |
| **grass_high_max_m** | 166.9m | P80 heightmap |
| **debris_min_deg** | 10.4° | P65 slope |
| **rock_min_deg** | 19.9° | P85 slope |
| **concave_threshold** | -3.81 | P25 curvature |
| **curvature_radius_m** | 20.0m | cellsize × 5 |

### Feathering (fixe)
- **coastal** : 20m
- **grass** : 40m
- **rock** : 10m

### Coastal (fixe)
- **distance_max** : 100m

---

## 🗺️ 11 Masks Générés

| # | Nom Mask | Couverture | Min | Max | Valeurs Uniques | Transitions | Type |
|---|----------|------------|-----|-----|-----------------|-------------|------|
| 01 | **seabed** | 15.40% | 0 | 65535 | 641 | 4.24% | ✅ CONTINU |
| 02 | **coastal_pebbles** | 18.92% | 0 | 65535 | 65536 | 18.18% | ✅ CONTINU |
| 03 | **coastal_grass** | 4.23% | 0 | 52576 | 46029 | 14.04% | ✅ CONTINU |
| 04 | **grass_low** | 18.03% | 0 | 45828 | 45829 | 38.99% | ✅ CONTINU |
| 05 | **grass_mid** | 19.18% | 0 | 65535 | 65536 | 30.90% | ✅ CONTINU |
| 06 | **grass_high** | 11.15% | 0 | 65535 | 65536 | 14.26% | ✅ CONTINU |
| 07 | **mountain_grass_low** | 3.68% | 0 | 45177 | 39628 | 13.26% | ✅ CONTINU |
| 08 | **mountain_grass_high** | 8.25% | 0 | 65533 | 65533 | 14.96% | ✅ CONTINU |
| 09 | **dirt_erosion** | 16.05% | 0 | 65535 | 65536 | 30.11% | ✅ CONTINU |
| 10 | **debris_rock** | 5.02% | 0 | 63994 | 62890 | 13.83% | ✅ CONTINU |
| 11 | **rock_walls** | 7.05% | 0 | 65535 | 65536 | 10.92% | ✅ CONTINU |

**Résultat** : **11/11 masks continus** (0 binaire) ✅

---

## 🎯 Texture de Base Recommandée

**`05_grass_mid`** (couverture 19.18%)

### Comparaison grass :
- `04_grass_low` : 18.03%
- **`05_grass_mid` : 19.18%** ← dominante
- `06_grass_high` : 11.15%

---

## 📈 Observations

### ✅ Points forts
1. **Tous les masks sont continus** — pas de binarisation détectée
2. **Transitions douces** : entre 4% et 39% du terrain en transition progressive
3. **Distribution équilibrée** : pas de mask mono-dominant (max 19.18%)
4. **Valeurs uniques** : jusqu'à 65536 valeurs distinctes (gradient complet)
5. **Feathering efficace** : gaussian_filter appliqué avec succès

### 🔍 Zones critiques
- **grass_low** : 38.99% en transition (très progressif)
- **dirt_erosion** : 30.11% en transition (zones pentes modérées)
- **grass_mid** : 30.90% en transition (texture base avec dégradés)

### 📊 Couverture globale
- **Zones côtières** (seabed + coastal) : ~38%
- **Herbes basses/moyennes** (grass_low + grass_mid) : ~37%
- **Érosion/roche** (dirt + debris + rock) : ~28%
- **Zones montagnes** (mountain_grass) : ~12%

---

## 🚀 Prochaines Étapes

1. **Importer dans Reforger Workbench** les 11 masks
2. **Tester le QTRE** (4-5 textures/bloc max)
3. **Vérifier les transitions** in-game (pas de lignes dures)
4. **Ajuster les seuils** si nécessaire (re-run avec params custom)
5. **Comparer avec anciens masks** Zimnitrita (avant pipeline continu)

---

## 📝 Commande Utilisée

```bash
python pipeline_phases.py \
  "data/projects/Zimnitrita/sources/temp_Terrain_modified3.asc" \
  "data/projects/Zimnitrita/sources/curvature.png" \
  -17 17 \
  "data/projects/Zimnitrita/pipeline_11masks_20260611_173326"
```

**Durée** : ~3 secondes  
**Mémoire** : ~2 GB (4097² × 11 masks float32)

---

## 🔗 Fichiers Générés

Tous les masks sont au format **PNG 16-bit** avec valeurs continues [0-65535].

```
pipeline_11masks_20260611_173326/
├── 01_seabed.png (1.0 MB)
├── 02_coastal_pebbles.png (6.8 MB)
├── 03_coastal_grass.png (6.5 MB)
├── 04_grass_low.png (11.7 MB)
├── 05_grass_mid.png (11.3 MB)
├── 06_grass_high.png (6.6 MB)
├── 07_mountain_grass_low.png (5.0 MB)
├── 08_mountain_grass_high.png (5.1 MB)
├── 09_dirt_erosion.png (17.6 MB)
├── 10_debris_rock.png (10.3 MB)
└── 11_rock_walls.png (8.1 MB)

Total: 90.0 MB
```
