# Biomes Texture System

**Date** : 2026-06-02  
**Auteur** : Giorbev

---

## 📋 Principe

Le système de tableaux biomes permet de **définir quelles textures sont utilisées selon le biome climatique**, indépendamment du code Python.

---

## 🎨 Biomes disponibles

| Biome | Fichier | Statut | Description |
|-------|---------|--------|-------------|
| **Tempéré** | `temperate.json` | ✅ Actif | Prairies, forêts tempérées, montagnes herbacées (Zimnitrita, ZBK) |
| **Méditerranéen** | `mediterranean.json` | ⏳ Futur | Scrubland, herbes sèches, maquis |
| **Tropical** | `tropical.json` | ⏳ Futur | Jungle, savane, plages tropicales |
| **Volcanique** | `volcanic.json` | ⏳ Futur | Cendres, lave, herbes volcaniques |
| **Arctique** | `arctic.json` | ⏳ Futur | Neige, glace, toundra |

---

## 📂 Structure fichier JSON

```json
{
  "biome": "nom_biome",
  "version": "1.0",
  "description": "Description du biome",
  "textures": {
    "altitude": {
      "coastal": {"Texture_01": 0.35, "Texture_02": 0.30, ...},
      "lowland": {...},
      "midland": {...},
      "highland": {...}
    },
    "slope": {
      "flat": {...},
      "gentle": {...},
      "moderate": {...},
      "steep": {...}
    },
    "sediment": {
      "dry": {...},
      "moist": {...},
      "wet": {...}
    },
    "curvature": {
      "concave": {...},
      "neutral": {...},
      "convex": {...}
    }
  },
  "thresholds": {...},
  "notes": {...}
}
```

---

## 🔧 Comment ça marche

### **1. Chaque masque vote pour 2-4 textures**

**Exemple pixel** :
```
Altitude : 200m → lowland
Slope : 12° → gentle
Sediment : 0.40 → moist
Curvature : -0.05 → neutral
```

**Votes** :
- **ALTITUDE (lowland)** : Grass_01 (0.45), Grass_03 (0.30), Dirt_01 (0.20)
- **SLOPE (gentle)** : Grass_01 (0.40), MountainGrass (0.30), Dirt_01 (0.20)
- **SEDIMENT (moist)** : Grass_01 (0.40), Grass_03 (0.30), Dirt_01 (0.20)
- **CURVATURE (neutral)** : Grass_01 (0.50), Dirt_01 (0.30), MountainGrass (0.15)

---

### **2. Addition des scores**

```
Grass_01 : 0.45 + 0.40 + 0.40 + 0.50 = 1.75
Dirt_01 : 0.20 + 0.20 + 0.20 + 0.30 = 0.90
Grass_03 : 0.30 + 0.30 = 0.60
MountainGrass : 0.30 + 0.15 = 0.45
```

---

### **3. Normalisation (somme = 1.0)**

```
Total : 3.70

Grass_01 : 1.75 / 3.70 = 0.47 (47%)
Dirt_01 : 0.90 / 3.70 = 0.24 (24%)
Grass_03 : 0.60 / 3.70 = 0.16 (16%)
MountainGrass : 0.45 / 3.70 = 0.12 (12%)
```

---

### **4. Squeezing top-5 (Reforger)**

Les 5 textures dominantes sont gardées, les autres éliminées.

---

## ➕ Ajouter une nouvelle texture

### **Texture vanilla Reforger**

Si Bohemia ajoute une nouvelle texture vanilla (ex: `Grass_04`), il suffit de l'ajouter dans les tableaux :

```json
"altitude": {
  "lowland": {
    "Grass_01": 0.40,
    "Grass_03": 0.25,
    "Grass_04": 0.20,  ← NOUVELLE texture
    "Dirt_01": 0.15
  }
}
```

**Pas besoin de modifier le code Python** ✅

---

### **Texture custom**

Si tu crées une texture custom (ex: `MyCustomGrass`), même principe :

```json
"altitude": {
  "coastal": {
    "BeachGrass_01": 0.30,
    "MyCustomGrass": 0.35,  ← Custom
    "Pebbles_01": 0.25,
    "Dirt_03": 0.10
  }
}
```

Il faut juste que la texture existe dans Reforger (vanilla ou addon).

---

## 🌍 Créer un nouveau biome

### **Exemple : Biome Méditerranéen**

1. **Copier** `temperate.json` → `mediterranean.json`

2. **Modifier** les textures :

```json
{
  "biome": "mediterranean",
  "version": "1.0",
  "description": "Biome méditerranéen - Scrubland, herbes sèches, maquis",
  "textures": {
    "altitude": {
      "coastal": {
        "BeachGrass_dry": 0.30,
        "Sand_01": 0.35,
        "Scrubland": 0.25,
        "Pebbles_01": 0.10
      },
      "lowland": {
        "Grass_dry": 0.40,
        "Scrubland": 0.35,
        "Dirt_dry": 0.20,
        "Sand_01": 0.05
      },
      ...
    },
    ...
  }
}
```

3. **Tester** sur une carte méditerranéenne

---

## 🎨 Biome custom

Tu peux créer un biome complètement custom :

```json
{
  "biome": "my_fantasy_biome",
  "version": "1.0",
  "description": "Mon biome fantasy avec textures customs",
  "textures": {
    "altitude": {
      "lowland": {
        "MyCustomGrass_Green": 0.40,
        "MyCustomGrass_Blue": 0.30,
        "MyCustomDirt_Purple": 0.20,
        "MyCustomRock_Crystal": 0.10
      },
      ...
    }
  }
}
```

**Seule condition** : Les textures doivent exister dans ton addon Reforger.

---

## 🔧 Utilisation dans projet

### **Config projet** (`project.json`)

```json
{
  "name": "Zimnitrita",
  "biome": "temperate",  ← Sélection biome
  "heightmap": "...",
  "masks": {...}
}
```

```json
{
  "name": "Mediterranean_Island",
  "biome": "mediterranean",  ← Autre biome
  "heightmap": "...",
  "masks": {...}
}
```

---

## 📊 Poids recommandés

### **Textures dominantes** (positions 1-2)
```
Poids : 0.40 - 0.70
Exemples : Grass_01 (prairie), Rock_01 (falaise), MountainGrass (alpage)
```

### **Textures secondaires** (positions 3-4)
```
Poids : 0.20 - 0.35
Exemples : Dirt_01, Grass_03, Debris_Rock
```

### **Textures détails** (positions 5+, peuvent être éliminées)
```
Poids : 0.05 - 0.15
Exemples : Heather, Grass_02, variantes
```

---

## ✅ Avantages système

1. **Extensibilité** : Ajouter texture sans coder ✅
2. **Modularité** : Ajuster un tableau sans casser les autres ✅
3. **Partage** : Partager fichiers biomes entre utilisateurs ✅
4. **Versioning** : Versioning JSON indépendant du code Python ✅
5. **Clarté** : Voir directement quelles textures sont utilisées ✅

---

## 📝 Notes

- Les **seuils** (flat/gentle, coastal/lowland) sont calculés **dynamiquement** selon la carte (slope_p90, percentiles altitude)
- Les **poids** dans les tableaux sont **fixes** (universels)
- Le **filtrage** est automatique (BeachGrass seulement en coastal, MountainGrass seulement en mid/highland)
- La **compétition** est réduite (textures filtrées par altitude avant croisement)

---

**Dernière mise à jour** : 2026-06-02  
**Version système** : 1.0
