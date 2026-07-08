# Philosophie du Pipeline — Génération Universelle

**Date** : 2026-06-01  
**Auteur** : [otea] Giorbev

---

## 🎯 Principe directeur

> **Le pipeline génère TOUT ce qui est écologiquement cohérent, quelle que soit la carte.**

---

## 🌍 Approche universelle

### 1. Analyse d'abord

**Avant de générer**, le pipeline analyse la carte complète :

```python
# Profil hypsométrique
altitude_p10, altitude_p50, altitude_p90
relief_score = (p90 - p50) / (p90 - p10)

# Classification
if relief_score < 0.35:
    profil = "flat"  # Plaine
elif relief_score < 0.55:
    profil = "balanced"  # Équilibré
elif relief_score < 0.70:
    profil = "plateau"  # Plateau avec sommets
else:
    profil = "mountain"  # Montagne

# Pentes
slope_p90 = percentile(slope, 90)
```

---

### 2. Adaptation ensuite

**Zones altitudinales calculées dynamiquement** :

**Pas de seuils fixes** :
```python
# ❌ MAUVAIS (sur-fitting)
coastal = 0-50m
lowland = 50-400m
highland = >1200m
```

**Seuils adaptatifs** :
```python
# ✅ BON (universel)
coastal = sea → percentile_20
lowland = percentile_20 → percentile_50
midland = percentile_50 → percentile_75
highland = percentile_75 → max
```

**Résultat** :
- **Carte plaine** (0-200m) : coastal 0-40m, lowland 40-100m, highland 150-200m
- **Carte montagne** (0-3500m) : coastal 0-700m, lowland 700-1750m, highland 2600-3500m
- **Zimnitrita** (0-1843m) : coastal 0-17m, lowland 209-621m, highland 603-929m

➡️ **S'adapte automatiquement à CHAQUE carte**

---

### 3. Génération honnête

**Le pipeline génère ce qu'il détecte, point final.**

**Pas de filtrage arbitraire** :
```python
# ❌ MAUVAIS
if texture_coverage < 1.0%:
    skip()  # "Trop rare, on ignore"

# ✅ BON
generate_all_textures()
export_if_not_empty()  # Garde même 0.01%
```

**Pourquoi ?**

**Scénario A** : Zimnitrita (plages rares)
```
BeachGrass : 0.01% (260 000 m²)
→ Exporté ✅
→ Peut être éliminé par squeezing Reforger (normal)
→ Utilisateur peut voir où il s'applique (PNG)
```

**Scénario B** : Île tropicale (plages nombreuses)
```
BeachGrass : 8.5% (21 km²)
→ Exporté ✅
→ Survit au squeezing (dominant)
→ Mêmes recettes, résultat différent selon géographie
```

➡️ **Le pipeline est honnête : il ne cache rien, il génère ce qui existe**

---

## 🔧 Contraintes acceptées

### Squeezing top-5 par pixel

**Réalité** : 16 textures générées, seulement 5 gardées par pixel après normalisation.

**Acceptation** :
```python
# Sur un pixel prairie
Grass_01 : 35%  ✅ Gardé
Grass_03 : 30%  ✅ Gardé
Dirt_01 : 20%   ✅ Gardé
MountainGrass : 10%  ✅ Gardé
Dirt_02 : 4%    ✅ Gardé
BeachGrass : 1%  ❌ Éliminé (6e position)
```

➡️ **Normal, pas un bug** : BeachGrass ne devrait PAS être sur une prairie inland

---

### Enforce ≤3 uniques par bloc 32m

**Réalité moteur Enfusion** : Maximum 3 textures différentes par bloc de 32m × 32m.

**Exemple** : Petite plage 64m × 64m (4 blocs) entourée de prairies

**Bloc côte** :
```
Grass_01 : présent sur 900 pixels (dominant environnant)
Dirt_01 : présent sur 800 pixels (dominant environnant)
BeachGrass : présent sur 200 pixels (locale plage)
Pebbles : présent sur 100 pixels (locale plage)
```

**Après enforce** :
```
Grass_01 ✅ Gardé (dominant)
Dirt_01 ✅ Gardé (dominant)
BeachGrass ✅ Gardé (3e texture)
Pebbles ❌ Éliminé (4e texture interdite)
```

**Acceptation** :
- La plage aura BeachGrass + Grass + Dirt (visuellement correct)
- Pebbles absent (limitation moteur, pas du pipeline)

➡️ **Pas idéal, mais inévitable** : C'est Reforger, pas notre choix

---

## 🎨 Textures rares ≠ Erreur

### Mentalité à éviter

```
"BeachGrass = 0.01%, c'est rien, on supprime"
→ ❌ Sur-optimisation prématurée
```

### Mentalité correcte

```
"BeachGrass = 0.01% = 260 000 m² = carré de 510m × 510m"
→ ✅ C'est significatif sur petites plages localisées
→ ✅ Exportons et laissons l'utilisateur décider
```

**Argument 1** : Transparence
- L'utilisateur peut ouvrir le PNG et voir **exactement** où BeachGrass s'applique
- Pas de magie cachée, pas de "le pipeline a décidé de l'ignorer"

**Argument 2** : Réutilisabilité
- Une future carte avec plus de plages utilisera les mêmes recettes
- BeachGrass passera de 0.01% à 5% automatiquement, sans modification code

**Argument 3** : Réalisme
- 260 000 m² de plages, c'est 26 hectares
- Sur une carte de 256 km², c'est cohérent avec "côte escarpée avec quelques plages rares"

---

## 🚫 Anti-patterns à éviter

### 1. Sur-fitting sur une carte

```python
# ❌ MAUVAIS
if map_name == "Zimnitrita":
    coastal_threshold = 17m
elif map_name == "ZBK":
    coastal_threshold = 50m
```

**Pourquoi mauvais** :
- Ne marche pas sur nouvelle carte
- Masque les vrais problèmes (recettes, seuils)
- Maintenance cauchemar

**Bon équivalent** :
```python
# ✅ BON
coastal_threshold = percentile(altitude, 20)
```

---

### 2. Seuils arbitraires

```python
# ❌ MAUVAIS
if texture_coverage < 1.0%:
    remove()  # "C'est trop rare"
```

**Pourquoi mauvais** :
- 1.0% sur carte 256 km² = 2.56 km² = **énorme**
- 1.0% sur carte 4 km² = 160 000 m² = petit mais significatif
- Seuil n'a pas de justification écologique

**Bon équivalent** :
```python
# ✅ BON
if texture_coverage == 0.0%:
    remove()  # Vraiment vide (0 pixel)
else:
    keep()  # Tout le reste
```

---

### 3. Boost manuel par texture

```python
# ❌ MAUVAIS
if texture == "BeachGrass":
    score *= 5.0  # "On veut vraiment du BeachGrass"
```

**Pourquoi mauvais** :
- Casse l'équilibre écologique
- Peut mettre BeachGrass sur montagnes
- Solution : corriger les contextes/recettes, pas booster aveuglément

**Bon équivalent** :
```python
# ✅ BON
very_low_coastal = (alt < 10m) * coastal * flat
sc["BeachGrass"] += very_low_coastal * 0.40
# Boost SEULEMENT sur contexte approprié (plages plates basses)
```

---

## ✅ Validation universalité

### Test 1 : Cartes extrêmes

**Plaine totale** (0-50m) :
```
coastal : 0-10m
lowland : 10-25m
highland : 40-50m

Résultat attendu :
  ✅ Pas de MountainGrass (pas d'altitude haute)
  ✅ Pas de Rock steep (pas de pente forte)
  ✅ Beaucoup Grass, Dirt
```

**Montagne pure** (800-3500m) :
```
coastal : 800-1400m
lowland : 1400-2200m
highland : 2600-3500m

Résultat attendu :
  ✅ Pas de BeachGrass (niveau mer à 800m)
  ✅ Beaucoup Rock, MountainGrass
  ✅ Debris dans ravines haute altitude
```

---

### Test 2 : Carte mixte (validation)

**Zimnitrita** (côtes plates EST + vallonnées OUEST) :

**Attendu** :
```
EST (plat) :
  ✅ BeachGrass sur plages 0-5m
  ✅ Grass sur prairies plates
  ❌ PAS de Rock (pas de pente forte)

OUEST (vallonné) :
  ❌ PAS de BeachGrass (pentes trop fortes)
  ✅ Rock sur côtes escarpées
  ✅ Grass + Dirt sur pentes moyennes
```

**Si résultat OK** → Pipeline est universel ✅

**Si BeachGrass partout (EST+OUEST)** → Contextes mal définis ❌

---

## 📊 Indicateurs de qualité

### Bon pipeline

```
[CALIBRATION] slope_p90=25.8°  (cohérent 15-35°)
[FILTRAGE] 16 masques gardés, 0 éliminés
[EXPORT] Tailles variables (1 MiB à 108 MiB)

Textures dominantes (>10%) : Grass, Rock, Dirt
Textures localisées (<1%) : BeachGrass, Heather, SeaBed
```

### Mauvais pipeline

```
[CALIBRATION] slope_p90=0.3°  ← BUG lecture masque
[FILTRAGE] 11 masques gardés, 5 éliminés  ← Seuil trop restrictif
[EXPORT] Tailles uniformes (toutes 50 MiB)  ← Textures partout
```

---

## 🎯 Résumé

**3 principes universels** :

1. **Analyse → Adaptation → Génération**
   - Pas de seuils fixes codés en dur
   - Tout calculé dynamiquement par percentiles
   
2. **Génération honnête**
   - Exporte tout sauf vraiment vide (0.00%)
   - Transparence totale (utilisateur voit tout)
   
3. **Acceptation contraintes**
   - Squeezing top-5 : normal, pas un bug
   - Enforce ≤3/bloc : limite moteur, inévitable
   - Petites zones (<100m) : peuvent être éliminées

**Test universel** : Le pipeline doit marcher sur plaine, montagne, île, sans modification code.

**Validation** : Si Zimnitrita (mixte plat/vallonné) fonctionne correctement, le pipeline est universel.

---

**Philosophie adoptée** : 2026-06-01  
**Validé sur** : Zimnitrita (16 km, tempéré, côtes mixtes)  
**À valider** : ZBK (non-régression), autres biomes
