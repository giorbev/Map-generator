# Auto-Calibration Biome — Guide Technique

**Version** : 3.0 (2026-06-06)  
**Système** : `temperate_auto.json` — Universel, altitude en mètres absolus

---

## 🎯 PRINCIPE

**Auto-calibration** analyse la carte et **adapte automatiquement** les seuils de textures :

- ✅ **Altitude en mètres absolus** (0m = niveau mer sur TOUTES cartes)
- ✅ **Slope en degrés** (universel, pas de conversion)
- ✅ **Fonctionne sur île, montagne, plaine** sans modification

---

## 📊 ANALYSE DE LA CARTE

### **Étape 1 : Statistiques Terrain**

Analyse automatique de la heightmap :

```python
Altitude :
  - min_alt : altitude minimale carte (ex: -32.25m ZBK)
  - max_alt : altitude maximale carte (ex: 399.81m ZBK)
  - range   : max - min (ex: 432.06m ZBK)
  - P50     : médiane → détecte niveau mer

Slope :
  - P75 : seuil pentes modérées
  - P90 : seuil pentes raides
```

---

### **Étape 2 : Détection Niveau Mer**

```python
niveau_mer = P50 altitude

Exemples :
  - ZBK (île)      : -9.97m (50% carte = eau)
  - Montagne       : +150m (pas d'eau)
  - Plaine côtière : 0m
```

---

### **Étape 3 : Stratification Terre Émergée**

Terre au-dessus du niveau mer divisée en **3 strates** (percentiles) :

```python
Terre émergée (altitude > niveau_mer) :

Lowland  : P0  → P33  (1/3 inférieur)
Midland  : P33 → P66  (1/3 milieu)
Highland : P66 → max  (1/3 supérieur)
```

**Exemple ZBK** :
```
Terre émergée : -9.94m → 399.81m

Lowland  : 0-41m    (plaines basses)
Midland  : 41-88m   (collines)
Highland : 88-400m  (montagnes)
```

---

## 🗺️ SEUILS CALIBRÉS

### **Zone Côtière** (fixe universel)

```
Coastal : 0-20m absolu
  → Bord de mer, plages, marais côtiers
  → FIXE sur toutes cartes (écologique)
```

---

### **Zones Herbeuses** (adaptatif)

```
Lowland  : 0 → P33 terre  (plaines basses)
Midland  : P33 → P66      (collines)
Highland : P66 → max      (montagnes)

→ S'ADAPTE selon la carte !
```

**Carte île** (ZBK) :
- Lowland : 0-41m (beaucoup de plaines)
- Midland : 41-88m
- Highland : 88-400m

**Carte montagne** (Alpes) :
- Lowland : 500-1200m (compressé)
- Midland : 1200-2000m
- Highland : 2000-3500m

---

## 🎨 RÉPARTITION DES TEXTURES

### **Critères de Sélection**

Chaque texture a des **conditions min/max** :

1. **Altitude** (mètres absolus) → converti auto selon carte
2. **Slope** (degrés) → universel
3. **Priority** → résout conflits si >3 textures
4. **Intensity** → force du masque

---

### **📋 TABLEAU RÉCAPITULATIF**

| Texture | Altitude (m) | Slope (°) | Priority | Rôle Écologique |
|---------|-------------|-----------|----------|-----------------|
| **SeaBed_01** | < 0 | - | 11 | Fond marin (sous niveau mer) |
| **Pebbles_01** | 0-20 | < 20 | 9 | Galets plage (bord immédiat eau) |
| **BeachGrass_01** | 0-20 | < 20 | 7 | Herbe plage (arrière-plage) |
| **Debris_Rock_01** | - | 20-35 | 8 | Débris rocheux (pentes modérées) |
| **Rock_01** | - | ≥ 35 | 10 | Roches (pentes raides/falaises) |

**Textures Phase 3** (herbes, pas encore implémentées) :
| Texture | Altitude (m) | Slope (°) | Priority | Rôle Écologique |
|---------|-------------|-----------|----------|-----------------|
| **Grass_01** | 20-200 | < 25 | 5 | Herbe lowland (plaines basses) |
| **MountainGrass_01** | 50-400 | < 25 | 6 | Herbe midland/highland (collines/montagnes) |
| **Heather_01** | > 100 | < 30 | 4 | Bruyère highland (hautes altitudes) |
| **Dirt_03** | 20-200 | < 15 | 3 | Terre nue (zones plates) |

---

## 🔧 CONVERSION ALTITUDE

### **Mètres Absolus → Normalisé**

Le pipeline travaille en **normalisé 0-1** :

```python
# Conversion automatique
alt_norm = (altitude_meters - min_alt) / alt_range

Exemple ZBK :
  - min_alt   = -32.25m
  - alt_range = 432.06m

  0m absolu   → (0 - (-32.25)) / 432.06 = 0.075 norm
  20m absolu  → (20 - (-32.25)) / 432.06 = 0.121 norm
```

**→ Transparent pour l'utilisateur !** ✅

---

## 🌍 UNIVERSALITÉ

### **Pourquoi ça fonctionne partout ?**

**Altitude** :
- Mètres absolus (0m = niveau mer)
- Conversion auto selon min/max carte
- **→ 0-20m côte = pareil ZBK ou Alpes** ✅

**Slope** :
- Degrés absolus (20° = 20° partout)
- Pas de conversion
- **→ Pente raide = pareil ZBK ou Alpes** ✅

---

## 📐 EXEMPLE CONCRET : ZBK

### **Stats Carte**
```
Altitude : -32.25m → 399.81m (range 432.06m)
Niveau mer : -9.97m (P50)
Terre émergée : -9.94m → 399.81m
```

### **Seuils Calibrés**
```
Coastal  : 0-20m     (0.075-0.121 norm)
Lowland  : 0-41m     (0.075-0.170 norm)
Midland  : 41-88m    (0.170-0.278 norm)
Highland : 88-400m   (0.278-1.000 norm)
```

### **Répartition Textures**

**Zone Côtière (0-20m)** :
```
Slope 0-20°   → Pebbles + BeachGrass (mélange 67/33%)
Slope 20-35°  → Debris_Rock (pentes modérées)
Slope ≥35°    → Rock (falaises côtières)
```

**Zone Lowland (0-41m)** :
```
Slope < 25°   → Grass_01 (plaines)
Slope 20-35°  → Debris_Rock
Slope ≥35°    → Rock
```

**Zone Midland (41-88m)** :
```
Slope < 25°   → MountainGrass_01 (collines)
Slope 20-35°  → Debris_Rock
Slope ≥35°    → Rock
```

**Zone Highland (88-400m)** :
```
Slope < 30°   → MountainGrass_01 + Heather_01 (montagnes)
Slope 20-35°  → Debris_Rock
Slope ≥35°    → Rock
```

---

## 🔄 WORKFLOW

### **1. Analyse**
```
Charger heightmap → Calculer stats → Détecter niveau mer
```

### **2. Calibration**
```
Stratifier terre émergée (P33, P66)
Définir seuils coastal/lowland/midland/highland
```

### **3. Génération**
```
Pour chaque pixel :
  - Convertir altitude mètres → normalisé
  - Tester conditions textures (altitude + slope)
  - Appliquer priority si conflit
  - Normaliser somme = 100%
```

### **4. Export**
```
Masques 16-bit PNG → Reforger Workbench
```

---

## ⚙️ PARAMÈTRES AJUSTABLES

### **Zone Côtière**
```python
coastal_max_meters = 20  # Hauteur max zone côtière (défaut 20m)
```

### **Stratification Herbes**
```python
lowland_percentile = 33   # Seuil lowland/midland (défaut 33%)
midland_percentile = 66   # Seuil midland/highland (défaut 66%)
```

### **Intensity Textures**
```json
"Pebbles_01": {
  "intensity": 2.0  // Augmente dominance Pebbles vs BeachGrass
}
```

---

## 🎯 AVANTAGES

✅ **Universel** : fonctionne île, montagne, plaine  
✅ **Lisible** : altitude en mètres (pas 0.075 normalisé)  
✅ **Écologique** : répartition réaliste selon terrain  
✅ **Adaptatif** : seuils herbes auto selon carte  
✅ **Rétrocompatible** : ancien format fonctionne encore  

---

## 📁 FICHIERS

- **Biome** : `data/biomes/temperate_auto.json`
- **Calibration** : `biome_calibration.py`
- **Pipeline** : `pipeline_core.py`
- **Config** : `biomes.json` (pointe vers temperate_auto)

---

**Dernière mise à jour** : 2026-06-06  
**Auteur** : Claude Code + Giorbev
