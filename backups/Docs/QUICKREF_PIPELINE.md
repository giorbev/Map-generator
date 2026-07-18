# Pipeline Texture — Référence Rapide

## 🎯 Principe

**Pipeline écologique universel** : Génère automatiquement 16 textures terrain à partir de 4 variables scientifiques.

---

## 📊 Variables d'entrée

| Variable | Source | Format | Rôle |
|----------|--------|--------|------|
| **Altitude** | heightmap.asc | Mètres réels | Zones thermiques (coastal/lowland/midland/highland) |
| **Pente** | slope.png | 0-1 → ×90 = degrés | Gravité, sédimentation (flat/gentle/moderate/steep) |
| **Humidité** | sediment.png | 0-1 (0=sec, 1=humide) | Flow map, drainage/accumulation (dry/moist/wet) |
| **Curvature** | curvature.png | 0-1 → remappé -1/+1 | Crêtes convexes, vallées concaves |

---

## 🌍 12 Contextes écologiques

**Croisements** : Altitude × Pente × Humidité × Curvature

### Côtier (coastal)
- `coast_flat` : plages plates (<9°)
- `coast_gentle` : pentes douces 5-12°
- `coast_talus` : talus 12-25°
- `coast_cliff` : falaises >25°
- `coast_outcrop` : affleurements convexes 6-12°

### Inland
- `prairie_low` : plaines basses plates
- `prairie_mid` : collines moyennes plates
- `mid_slope` : pentes moyennes 12-25° (non raides)

### Highland
- `alpage_dry` : alpages secs plats
- `alpage_wet` : alpages humides plats
- `rocky_highland` : pentes hautes rocheuses
- `crest` : crêtes convexes hautes

### Spéciaux
- `ravine` : vallées concaves humides
- `cliff_fissure` : falaises concaves

---

## 🎨 16 Textures générées

| Stem | Contexte principal | Altitude | Pente |
|------|-------------------|----------|-------|
| **SeaBed_01** | Sous niveau mer | <0m | Toute |
| **BeachGrass_01** | coast_flat | 0-50m | <9° |
| **Grass_03_coastal** | coast_flat | 0-50m | <12° |
| **Pebbles_01** | coast_flat, coast_gentle | 0-50m | <12° |
| **Pebbles_02** | coast_talus, coast_outcrop | 0-50m | 12-25° |
| **Grass_01** | prairie_low, prairie_mid | 50-700m | <12° |
| **Grass_03** | prairie_low | 50-400m | <9° |
| **MountainGrass_01** | alpage_dry, mid_slope | 400-1200m | <25° |
| **MountainGrass_02** | alpage_wet | 600-1200m | <12° |
| **MountainGrass_03** | alpage_wet | 600-1200m | <9° |
| **Heather_01** | highland (rare) | >600m | <9° |
| **Dirt_01** | prairie_low | 50-700m | <12° |
| **Dirt_02** | mid_slope, crest | 400-1200m | 12-25° |
| **Dirt_03** | coast_flat | 0-50m | <9° |
| **Debris_Rock_01** | ravine, rocky_highland, coast_outcrop | Toute | Modéré |
| **Rock_01** | steep, crest, coast_cliff | Toute | >25° |

---

## ⚙️ Calibration automatique

### Altitude (hypsométrique adaptatif)

**Profil détecté** : flat / balanced / plateau / mountain

**Zones calculées par percentiles** :
```
coastal : sea-2m → P20 (ex: -2→17m sur Zimnitrita)
lowland : P20 → P50 (ex: 17→621m)
midland : P50 → P75
highland : P75 → max
```

### Pente (seuils dynamiques)

**Basé sur slope_p90** (90e percentile des pentes) :

```python
flat     : 0 → slope_p90 × 0.36
gentle   : slope_p90 × 0.14 → slope_p90 × 1.00
moderate : slope_p90 × 0.50 → slope_p90 × 1.79
steep    : slope_p90 × 0.72 → 90°
```

**Exemple Zimnitrita** (slope_p90 = 25.8°) :
```
flat     : 0-9.3°
gentle   : 3.6-25.8°
moderate : 12.9-46.1°
steep    : 18.6-90°
```

### Humidité (seuils fixes)

```python
dry   : sediment 0.0-0.35
moist : sediment 0.12-0.82 (pic 0.3-0.6)
wet   : sediment 0.48-1.0
```

### Curvature (seuils fixes)

```python
convex  : curvature +0.08 à +1.0
concave : curvature -0.08 à -1.0
```

---

## 🔧 Squeezing Reforger

### Top-5 par pixel
16 textures générées → 5 dominantes gardées par pixel

### Enforce ≤3 uniques par bloc 32m
Si un bloc contient >3 textures différentes, les moins présentes sont supprimées

**Impact** : Petites zones (<100m) peuvent être éliminées si entourées de textures dominantes

---

## 📦 Export

```
data/projects/<nom>/generated/terrain_masks/
  mask_01_SeaBed_01.png
  mask_02_BeachGrass_01.png
  ...
  mask_16_Rock_01.png
  map_parameters.txt
```

**Format** : PNG 16-bit (0-65535)  
**Seuil élimination** : 0.0001% (garde tout sauf vraiment vide)

---

## 🐛 Bugs courants

### Slope_p90 très bas (<5°)
```
Cause : slope.png non converti en degrés
Fix : pipeline_core.py ligne 629 (× 90)
```

### Crêtes/vallées non détectées
```
Cause : curvature.png non remappé -1/+1
Fix : pipeline_core.py ligne 632 ((x-0.5)×2)
```

### Textures côtières absentes
```
Causes possibles :
1. Plages <5m altitude (avant coastal commençait à 5m)
2. Sediment trop sec (<0.3) pour recettes wet
3. Petites plages (<100m) éliminées par squeezing

Fix : boost very_low_coastal (ligne 310-312)
```

---

## 📝 Phases de développement

### ✅ Phase 0 : Bugs masques IT (2026-06-01)
- Slope converti degrés
- Curvature remappé -1/+1
- Sediment validé OK

### ✅ Phase 1 : Côtier (2026-06-01)
- Boost very_low_coastal
- Contextes coast_gentle, coast_outcrop
- Recettes Pebbles sediment modéré

### ⏳ Phase 2 : Dirt/Grass (à venir)
- Réduire Dirt_02 sur pentes/crêtes
- Booster Grass en compensation

### ⏳ Phase 3 : Érosion (à venir)
- Ajuster Debris_Rock_01 distribution

---

**Dernière mise à jour** : 2026-06-01  
**Version pipeline** : 5.2
