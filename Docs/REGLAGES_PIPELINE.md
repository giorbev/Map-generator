# RÉCAPITULATIF COMPLET DES RÉGLAGES PIPELINE V2

Guide de référence pour tous les paramètres du pipeline de génération de textures terrain.

---

## 🎯 1. CURVATURE (Détection creux/ravins)

### Paramètres

| Paramètre | Valeur actuelle | Plage | Effet | Où ajuster |
|-----------|----------------|-------|-------|------------|
| **deep (debris)** | P58 | P5-P70 | Creux profonds → debris_rock | Onglet Debug → Slider "deep" |
| **concave (dirt)** | P25 | P5-P40 | Creux légers → dirt_erosion | Onglet Debug → Slider "concave" |

### Logique

- **P58** = 58% zones les plus concaves
- **Plus haut** = plus permissif (plus de zones détectées)
- **Plus bas** = plus restrictif (seulement creux profonds)

### Relation

- **Debris** : `curvature < P58` (creux profonds)
- **Dirt** : `P58 ≤ curvature < P25` (creux légers, exclut debris)

### Sauvegarde

Bouton **"⚙️ Sauvegarder pour Pipeline"** → Enregistre dans `project.json`

```json
{
  "pipeline_v2": {
    "curvature_percentiles": {
      "debris_deep": 58,
      "dirt_concave": 25
    }
  }
}
```

---

## 📐 2. TPI (Position topographique)

### Paramètres

| Paramètre | Valeur | Plage | Effet | Où ajuster |
|-----------|--------|-------|-------|------------|
| **TPI Local Radius** | 100m | 50-300m | Détecte ravins/creux locaux | Onglet Génération (slider) |
| **TPI Macro Radius** | 500m | 200-1000m | Détecte contexte vallée/montagne | Onglet Génération (slider) |

### Utilisation actuelle

- ✅ **Mud river** : TPI < P40 (fonds de ravins)
- ❌ **Debris/dirt** : TPI retiré (trop restrictif)

### Impact

- **Radius plus petit** (50-75m) → Détecte relief fin
- **Radius plus grand** (150-200m) → Détecte relief général

### Note importante

⚠️ Nécessite **"Forcer recalcul terrain"** pour prendre effet (supprime cache `terrain_data.npz`)

---

## 🌊 3. FEATHERING (Transitions textures)

### Paramètres par texture

| Texture | Paramètre | Valeur défaut | Plage | Effet |
|---------|-----------|---------------|-------|-------|
| **Coastal** (pebbles/grass) | `feather_coastal_m` | 20m | 10-50m | Transition eau → terre |
| **Grass** (herbes) | `feather_grass_m` | 20m | 10-50m | Transitions entre herbes |
| **Rock** (falaises) | `feather_rock_m` | 20m | 10-60m | Transition rock → autres |
| **Debris** (débris) | `feather_debris_m` | 25m | 5-50m | Transition debris → herbe |
| **Forest** (forêt) | `feather_forest_m` | 40m | 20-80m | Lisière de forêt |
| **River/Mud** | `feather_river_m` | 15m | 5-30m | Bords rivières/mud |

### Où ajuster

**Onglet Génération** → Section **"Paramètres Feathering"**

### Règles d'ajustement

- **10-20m** : Transitions nettes/marquées → Grande zone pure
- **30-50m** : Transitions douces/étalées → Petite zone pure
- **60-80m** : Transitions très douces (forêts)

### Exemple visuel

```
Feather 10m :  ████████░  (zone pure large, transition courte)
Feather 40m :  ████░░░░░  (zone pure courte, transition large)
```

---

## 🎨 4. GRADIENT DEBRIS (Érosion directionnelle)

### Paramètre

| Paramètre | Valeur | Plage | Effet | Où |
|-----------|--------|-------|-------|-----|
| `debris_gradient_distance_m` | 100m | 50-200m | Distance max gradient depuis rock | `project.json` |

### Fonction

Gradient directionnel d'intensité basé sur la distance depuis rock_walls :

```
Rock walls ═══════════════════
    ↓ 0m
Debris 100% ████████  ← Pied de roche (débris concentrés)
    ↓ 50m
Debris 50%  ████░░░░  ← Gradient de dispersion
    ↓ 100m
Debris 0%   ░░░░░░░░  ← Débris dispersés/intégrés
    ↓
Herbe ═══════════════════════
```

### Ajustement manuel

Modifier `project.json` :

```json
{
  "pipeline_v2": {
    "params": {
      "debris_gradient_distance_m": 100.0
    }
  }
}
```

### Effet des valeurs

- **50m** : Gradient serré (transitions rapides)
- **100m** : Gradient moyen (défaut, équilibré)
- **150-200m** : Gradient doux (étalé, dispersion longue)

### Note

Le gradient s'applique **AVANT** le feathering :
1. Gradient directionnel (intensité selon distance)
2. PUIS feathering standard (blur transitions)

Les deux se combinent pour un résultat naturel !

---

## 📊 5. AUTRES PARAMÈTRES IMPORTANTS

### Seuils de pente (auto-calibrés)

| Paramètre | Valeur auto | Effet |
|-----------|-------------|-------|
| `debris_min_deg` | P65 ≈ 10.4° | Pente minimum pour debris/dirt |
| `rock_min_deg` | P85 ≈ 19.9° | Pente minimum pour rock walls |

### Coastal (zone côtière)

| Paramètre | Valeur | Effet |
|-----------|--------|-------|
| `coastal_alt_max_m` | Auto P10 ≈ 11.5m | Altitude max pebbles/grass |
| `coastal_distance_max_m` | 60m | Distance max depuis mer |
| **Altitude min pebbles** | **-0.5m** | Pebbles descend jusqu'à l'eau |

### Roughness (rugosité)

| Paramètre | Valeur | Effet |
|-----------|--------|-------|
| `rock_roughness_min` | P70 ≈ 0.10 | Seuil rugosité rock vs grass alpine |

---

## 🎯 WORKFLOW COMPLET

### Étape 1 : Calibration Debug (Curvature)

1. **Onglet Aperçu Terrain** → **Masques Debug**
2. Ajuster sliders en temps réel :
   - **Deep (debris)** : 58
   - **Concave (dirt)** : 25
3. Vérifier visuellement les masques générés
4. Clic **"⚙️ Sauvegarder pour Pipeline"**

### Étape 2 : Réglages Génération

1. **Onglet Textures Terrain**
2. Ajuster **Feathering** :
   - Coastal : 20m
   - Grass : 20m
   - Rock : 20m
   - **Debris : 15m** (pour zone pure plus large)
   - Forest : 40m
   - River : 15m
3. **TPI** : Laisser par défaut (100m/500m) sauf besoin spécifique

### Étape 3 : Génération

1. Clic **"Générer Masks Terrain"**
2. Pipeline applique automatiquement :
   - Curvature P58/P25
   - **Gradient debris 100m**
   - Feathering
   - Exclusions
3. Import dans Reforger
4. **Retouches manuelles** pour creux de pentes

---

## 📝 VALEURS ACTUELLES RECOMMANDÉES

### Configuration optimale Zimnitrita

```yaml
CURVATURE:
  deep (debris)     : P58    # Ravins + montagnes
  concave (dirt)    : P25    # Talus légers

TPI:
  local             : 100m   # Détection ravins locaux
  macro             : 500m   # Contexte vallée/montagne

FEATHERING:
  coastal           : 20m    # Pebbles/grass
  grass             : 20m    # Entre herbes
  rock              : 20m    # Falaises
  debris            : 15m    # Zone pure debris large
  forest            : 40m    # Lisière douce
  river/mud         : 15m    # Bords nets

GRADIENT:
  debris distance   : 100m   # Érosion depuis rock

COASTAL:
  altitude min      : -0.5m  # Touche l'eau
  altitude max      : auto   # P10 ≈ 11.5m
  distance max      : 60m
```

---

## 🔧 DÉPANNAGE

### Problème : Debris trop étalé

**Solutions** :
- ↓ Diminuer `feather_debris_m` (25m → 15m)
- ↓ Diminuer `debris_gradient_distance_m` (100m → 75m)
- ↓ Diminuer curvature `deep` (P58 → P45)

### Problème : Debris pas assez visible

**Solutions** :
- ↑ Augmenter curvature `deep` (P58 → P65)
- ↑ Augmenter `debris_gradient_distance_m` (100m → 150m)

### Problème : Transitions trop brutales

**Solutions** :
- ↑ Augmenter feathering global (20m → 30-40m)

### Problème : Pebbles ne touche pas l'eau

**Solutions** :
- Vérifier `heightmap >= -0.5` dans code (déjà corrigé)
- Augmenter `coastal_distance_max_m` (60m → 80m)

### Problème : TPI ne fait rien

**Solutions** :
- ✅ Cocher **"Forcer recalcul terrain"**
- ❌ Supprimer `terrain_data.npz` manuellement

---

## 📚 RÉFÉRENCES

### Fichiers concernés

- **Pipeline** : `pipeline_v2.py`
- **Interface** : `app.py`
- **Config projet** : `data/projects/[NOM]/project.json`
- **Cache terrain** : `data/projects/[NOM]/terrain_data.npz`

### Mémoire auto

Voir `C:\Users\jordi\.claude\projects\h--logiciel-perso-Map-generator\memory\` pour :
- Contraintes QTRE
- Architecture pipeline
- Solutions crashs Workbench

---

## 📌 NOTES IMPORTANTES

1. **Curvature P58** = Calibré via analyse masque manuel (90% zones peintes)
2. **Gradient debris** = Nouveau système d'érosion directionnelle (Option B validée)
3. **TPI retiré debris/dirt** = Trop restrictif, curvature suffit
4. **Feathering + Gradient** = Se combinent (gradient PUIS feathering)
5. **Pebbles -0.5m** = Descend dans l'eau pour coller au bord visible

---

**Document mis à jour le : 2026-06-17**  
**Version pipeline : V2 (MODE 2 - 15 masks)**  
**Terrain de référence : Zimnitrita 16km²**
