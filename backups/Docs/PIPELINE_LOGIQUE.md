# Pipeline Texture Reforger — Logique complète

**Version** : 1.0  
**Date** : 2026-06-01  
**Auteur** : Documentation technique Map Generator Pro

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Les 5 signaux terrain](#les-5-signaux-terrain)
3. [Étapes du pipeline](#étapes-du-pipeline)
4. [Zones altitudinales](#zones-altitudinales)
5. [Catégories de pente](#catégories-de-pente)
6. [Signaux de forme et humidité](#signaux-de-forme-et-humidité)
7. [Contextes écologiques](#contextes-écologiques)
8. [Recettes par texture](#recettes-par-texture)
9. [Normalisation finale](#normalisation-finale)
10. [Exemples concrets](#exemples-concrets)
11. [Diagnostiquer un problème](#diagnostiquer-un-problème)

---

## Vue d'ensemble

Le pipeline transforme **4 masques terrain** en **16 masques de textures Reforger** via un système de **règles écologiques**.

### Schéma général

```
┌──────────────────────────────────────────────────────────────┐
│ INPUTS (4 masques)                                           │
├──────────────────────────────────────────────────────────────┤
│ 1. heightmap.asc     → Altitudes (mètres)                    │
│ 2. slope.png         → Pentes (degrés)                       │
│ 3. curvature.png     → Courbure (-1 à +1)                    │
│ 4. sediment.png      → Accumulation (0-1)                    │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ TRAITEMENT (pipeline_core.py)                                │
├──────────────────────────────────────────────────────────────┤
│ 1. Normalisation → h, s, c, sed normalisés                   │
│ 2. Analyse hypsométrique → adaptation seuils                 │
│ 3. Calcul signaux → coastal, flat, convex, wet, etc.         │
│ 4. Combinaison → 12 contextes écologiques                    │
│ 5. Application recettes → poids par texture                  │
│ 6. Normalisation → somme = 1.0 par pixel                     │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ OUTPUTS (16 masques PNG 16-bit)                              │
├──────────────────────────────────────────────────────────────┤
│ Rock_01.png, Debris_Rock_01.png, Pebbles_01.png, ...         │
│ → Importables directement dans Reforger                      │
└──────────────────────────────────────────────────────────────┘
```

---

## Les 5 signaux terrain

Le pipeline utilise **5 signaux indépendants** qui se combinent pour former des contextes écologiques.

### 1. **Altitude** (depuis heightmap)

| Signal | Calcul | Rôle |
|--------|--------|------|
| `coastal` | `smoothstep(-2m, 5m, alt) * (1 - smoothstep(15m, 50m, alt))` | Zone côtière (0-50m) |
| `lowland` | `smoothstep(a_l1, a_l2, alt) * (1 - smoothstep(a_l3, a_l4, alt))` | Basses terres |
| `midland` | `smoothstep(a_m1, a_m2, alt) * (1 - smoothstep(a_m3, a_m4, alt))` | Collines |
| `highland` | `smoothstep(a_h1, a_h2, alt)` | Haute montagne |

**Points clés** :
- La heightmap est convertie de 0-1 normalisé → mètres absolus : `alt_m = alt_min + h * (alt_max - alt_min)`
- Les seuils `a_l1`, `a_h1`, etc. sont **adaptés** selon le profil hypsométrique
- Une zone peut avoir plusieurs signaux actifs simultanément (ex: `lowland=0.3` + `midland=0.7`)

### 2. **Pente** (depuis slope.png)

| Signal | Seuil | Rôle |
|--------|-------|------|
| `flat` | `1 - smoothstep(0°, sl_flat, pente)` | Terrain plat |
| `gentle` | `smoothstep(sl_g1, sl_g2, pente) * (1 - smoothstep(sl_g3, sl_g4, pente))` | Pente douce |
| `moderate` | `smoothstep(sl_mo1, sl_mo2, pente) * (1 - smoothstep(sl_mo3, sl_mo4, pente))` | Pente moyenne |
| `steep` | `smoothstep(sl_st1, sl_st2, pente)` | Pente raide/falaise |

**Seuils par défaut** (avec `slope_p90 = 15°`) :
- `flat` : 0-5.4°
- `gentle` : 2.1-15°
- `moderate` : 7.5-27°
- `steep` : 10.8°+

### 3. **Courbure** (depuis curvature.png)

| Signal | Seuil | Rôle |
|--------|-------|------|
| `convex` | `smoothstep(0.08, 0.45, curvature)` | Crêtes, bosses, éperons |
| `concave` | `smoothstep(0.08, 0.45, -curvature)` | Vallées, creux, ravines |

**Points clés** :
- Valeurs curvature normalisées -1 à +1
- Indépendant de l'altitude et de la pente
- Une crête peut être plate (`convex=1, flat=1`) ou raide (`convex=1, steep=1`)

### 4. **Humidité** (depuis sediment.png)

| Signal | Seuil | Rôle |
|--------|-------|------|
| `dry` | `1 - smoothstep(0.10, 0.35, sediment)` | Sec |
| `moist` | `smoothstep(0.12, 0.40, sed) * (1 - smoothstep(0.58, 0.82, sed))` | Humide |
| `wet` | `smoothstep(0.48, 0.78, sediment)` | Très humide |

**Points clés** :
- Sediment = proxy pour accumulation d'eau/matière
- Valeurs 0-1 (0 = sec, 1 = très humide)
- **IMPORTANT** : `wet` nécessite `sediment > 0.48` → impact sur Pebbles côtiers

### 5. **Calibration hypsométrique**

Le pipeline analyse la **courbe hypsométrique** (distribution altitude) pour adapter les seuils :

| Profil détecté | Critères | Adaptation seuils |
|----------------|----------|-------------------|
| **flat** | `mean < 0.32` et `spread < 0.45` | Highland tardif (p75), coastal élargi |
| **balanced** | Distribution équilibrée | Seuils standards (ZBK) |
| **plateau** | `mean > 0.48` et `spread < 0.42` | Highland anticipé (p50) |
| **mountain** | `mean > 0.55` ou `spread > 0.65` | Highland très tôt (p45), coastal réduit |

**Exemple** :
- Terrain **flat** (plaine côtière) → `highland_start = p75` → alpages rares
- Terrain **mountain** (Everest) → `highland_start = p45` → alpages précoces

---

## Étapes du pipeline

### Étape 1 : Ingestion et normalisation

**Fichier** : `pipeline_core.py` → `ingest_all()`

```python
# Heightmap .asc → normalisation 0-1
raw_h = np.loadtxt("heightmap.asc", skiprows=6)
h_norm = (raw_h - alt_min) / (alt_max - alt_min)

# Slope.png → degrés (0-90)
slope_img = cv2.imread("slope.png")
s = (slope_img / 255.0) * 90.0  # Approximatif

# Curvature.png → -1 à +1
curv_img = cv2.imread("curvature.png")
c = (curv_img / 255.0) * 2.0 - 1.0

# Sediment.png → 0-1
sed_img = cv2.imread("sediment.png")
sed = sed_img / 255.0
```

**Fallbacks** :
- Si `slope.png` absent ET heightmap ≤ 12000px → calcul auto via Sobel
- Si `curvature.png` absent ET heightmap ≤ 12000px → calcul auto via Laplacien
- Si `sediment.png` absent → matrice de zéros

### Étape 2 : Analyse hypsométrique

**Fichier** : `pipeline_core.py` → `calibrate_zones()`

```python
# Extraire pixels terrestres (altitude > niveau mer)
h_land = h_norm[h_norm > sea_threshold]

# Calculer percentiles
p15 = np.percentile(h_land, 15)
p85 = np.percentile(h_land, 85)
mean = np.mean(h_land)
spread = p85 - p15

# Détecter profil terrain
if mean < 0.32 and spread < 0.45:
    terrain_type = 'flat'
    highland_start_pct = 75  # Alpine tardif
elif mean > 0.55 or spread > 0.65:
    terrain_type = 'mountain'
    highland_start_pct = 45  # Alpine précoce
else:
    terrain_type = 'balanced'
    highland_start_pct = 58  # Standard ZBK

# Calculer seuils adaptatifs
a_h1 = np.percentile(h_land, highland_start_pct)
# ... etc pour tous les seuils
```

### Étape 3 : Calcul des signaux

**Fichier** : `pipeline_core.py` → `compute_chunk_blends()`

Pour chaque pixel :

```python
# 1. Convertir heightmap → altitude mètres
alt_m = alt_min + h_chunk * (alt_max - alt_min)

# 2. Calculer zones altitude
coastal = smoothstep(-2.0, 5.0, alt_m) * (1 - smoothstep(15.0, 50.0, alt_m))
lowland = smoothstep(zones['a_l1'], zones['a_l2'], alt_m) * ...
highland = smoothstep(zones['a_h1'], zones['a_h2'], alt_m)

# 3. Calculer catégories pente
flat = 1.0 - smoothstep(0.0, zones['sl_flat'], s_chunk)
moderate = smoothstep(zones['sl_mo1'], zones['sl_mo2'], s_chunk) * ...
steep = smoothstep(zones['sl_st1'], zones['sl_st2'], s_chunk)

# 4. Calculer forme
convex = smoothstep(0.08, 0.45, c_chunk)
concave = smoothstep(0.08, 0.45, -c_chunk)

# 5. Calculer humidité
dry = 1.0 - smoothstep(0.10, 0.35, sed_chunk)
wet = smoothstep(0.48, 0.78, sed_chunk)
```

### Étape 4 : Combinaison en contextes

**Fichier** : `pipeline_core.py` → lignes 285-299

Les signaux se **multiplient** pour former des contextes :

```python
# Contextes côtiers
coast_flat = coastal * (flat + gentle * 0.8 + moderate * 0.4)
coast_talus = coastal * (moderate + steep * 0.3)
coast_cliff = coastal * steep

# Contextes prairies
prairie_low = lowland * (flat + gentle) * (1.0 - steep) * (1.0 - ravine)
prairie_mid = midland * (flat + gentle) * (1.0 - steep)

# Contextes montagne
alpage_dry = highland * (flat + gentle) * dry
alpage_wet = highland * (flat + gentle) * (moist + wet * 0.4)

# Contextes rocheux
rocky_highland = highland * smoothstep(zones['sl_rh1'], zones['sl_rh2'], s_chunk)
rocky_outcrop = (lowland + midland + coastal * 0.5) * moderate * convex * (1.0 - steep)

# Contextes spéciaux
ravine = concave * wet
cliff_fissure = steep * concave
crest = highland * convex
```

**Points clés** :
- Un pixel peut appartenir à **plusieurs contextes** simultanément
- Les contextes ne sont **pas exclusifs** (ex: `coast_flat=0.7` + `prairie_low=0.3`)
- La **multiplication** garantit que tous les critères sont satisfaits

### Étape 5 : Application des recettes

**Fichier** : `pipeline_core.py` → lignes 301-390

Chaque texture accumule des **poids depuis plusieurs contextes** :

```python
# Exemple: Pebbles_01 reçoit du poids depuis 4 sources
sc["Pebbles_01"] = 0.0
sc["Pebbles_01"] += coast_flat * wet * 0.38           # Plage humide
sc["Pebbles_01"] += coast_talus * 0.45                # Talus côtier
sc["Pebbles_01"] += coast_cliff * 0.12                # Falaise
sc["Pebbles_01"] += ravine * wet * 0.12               # Lit de rivière

# Exemple: Rock_01 reçoit du poids depuis 6 sources
sc["Rock_01"] = 0.0
sc["Rock_01"] += steep * (1.0 - cliff_fissure * 0.15) * 0.90  # Parois raides
sc["Rock_01"] += crest * dry * (0.38 + steep * 0.08)          # Crêtes highland
sc["Rock_01"] += rocky_highland * 0.52                        # Pentes highland
sc["Rock_01"] += rocky_outcrop * 0.38                         # Affleurements
sc["Rock_01"] += coast_cliff * 0.60                           # Falaises côtières
```

**Les coefficients** (0.38, 0.52, etc.) représentent :
- La **proportion de la texture** dans ce contexte
- Exemple : `coast_cliff * 0.60` = falaise côtière = 60% Rock_01

### Étape 6 : Normalisation

**Fichier** : `pipeline_core.py` → lignes 788-796

```python
# Pour chaque pixel
for pixel in all_pixels:
    # Somme de tous les scores
    total = sum(scores[stem][pixel] for stem in PIPELINE_STEMS)
    
    # Éviter division par zéro
    if total == 0:
        total = 1.0
    
    # Normaliser (garantit somme = 1.0)
    for stem in PIPELINE_STEMS:
        scores[stem][pixel] /= total
```

**Résultat** :
- Chaque pixel : `Rock_01 + Pebbles_01 + Grass_02 + ... = 1.0`
- Compatible format QTRE Reforger (4-5 textures pondérées par pixel)

---

## Zones altitudinales

### Définition des zones

| Zone | Seuil altitude (mètres) | Rôle écologique |
|------|-------------------------|-----------------|
| **Submergé** | < 0m | Fond marin |
| **Coastal** | -2m → +50m | Plage, côte, falaises côtières |
| **Lowland** | `a_l1` → `a_l4` | Prairies basses, forêts |
| **Midland** | `a_m1` → `a_m4` | Collines, prairies intermédiaires |
| **Highland** | `a_h1` → `a_h2` | Alpages, landes, crêtes rocheuses |

### Seuils adaptatifs

Les valeurs `a_l1`, `a_h1`, etc. sont **calculées depuis les percentiles** de la heightmap :

**Exemple terrain "balanced" (Zimnitrita)** :

```
alt_min = -204m, alt_max = 499m
Percentiles pixels terrestres :
  p5  = 12m
  p30 = 85m
  p50 = 156m
  p58 = 189m (highland start)
  p85 = 387m

Seuils calculés :
  a_l1 = 1m       (début lowland)
  a_l2 = 85m      (poids max lowland)
  a_l3 = 156m     (début transition lowland→midland)
  a_l4 = 210m     (fin lowland)
  
  a_h1 = 189m     (début highland)
  a_h2 = 387m     (poids max highland)
```

**Comparaison profils** :

| Profil | Highland démarre | Effet |
|--------|------------------|-------|
| **flat** (plaine) | p75 = 320m | Alpages très rares |
| **balanced** (ZBK) | p58 = 189m | Équilibre prairie/alpine |
| **mountain** (Everest) | p45 = 2800m | Alpages dès 2800m |

### Chevauchement des zones

**Les zones ne sont PAS exclusives** — utilisation de `smoothstep` pour transitions douces :

```
Exemple pixel altitude = 180m (Zimnitrita balanced) :

lowland  = smoothstep(1, 85, 180) * (1 - smoothstep(156, 210, 180))
         = 1.0                     * (1 - 0.44)
         = 0.56

midland  = smoothstep(67, 156, 180) * (1 - smoothstep(256, 373, 180))
         = 1.0                      * 1.0
         = 1.0

highland = smoothstep(189, 387, 180)
         = 0.0  (pas encore highland)

→ Ce pixel est 56% lowland + 100% midland (zone de transition)
```

---

## Catégories de pente

### Calcul des seuils

Les seuils de pente sont **dérivés de `slope_p90`** (90e percentile des pentes terrestres) :

```python
slope_p90 = np.percentile(slope_map[slope_map > 0.01], 90)

# Par défaut (Zimnitrita slope_p90 ≈ 15°) :
sl_flat  = 15 * 0.36 = 5.4°
sl_g1    = 15 * 0.14 = 2.1°
sl_g2    = 15 * 0.50 = 7.5°
sl_g3    = 15 * 0.72 = 10.8°
sl_g4    = 15 * 1.00 = 15.0°
sl_mo1   = 15 * 0.50 = 7.5°
sl_mo2   = 15 * 0.93 = 14.0°
sl_mo3   = 15 * 1.25 = 18.8°
sl_mo4   = 15 * 1.79 = 26.9°
sl_st1   = 15 * 0.72 = 10.8°
sl_st2   = 15 * 1.38 = 20.7°
```

### Plages par catégorie

| Catégorie | Plage (slope_p90=15°) | Rôle |
|-----------|-----------------------|------|
| `flat` | 0 - 5.4° | Prairies, plages, plats |
| `gentle` | 2.1 - 15° | Collines douces, pentes herbeuses |
| `moderate` | 7.5 - 27° | Pentes moyennes, érosion légère |
| `steep` | 10.8°+ | Falaises, parois, affleurements rocheux |

**Remarques importantes** :
- **Chevauchement intentionnel** : gentle et moderate se superposent (7.5-15°)
- **Impact global** : `steep` exclut les prairies (`prairie_low = ... * (1.0 - steep)`)
- **Seuil critique côtier** : `moderate` démarre à **7.5°** → talus côtier inactif avant cette pente

---

## Signaux de forme et humidité

### Courbure (curvature)

**Source** : Masque `curvature.png` normalisé -1 à +1

| Type | Seuil | Valeur curvature | Interprétation |
|------|-------|------------------|----------------|
| **Convex** | `> 0.08` | +0.2 à +1.0 | Crêtes, bosses, éperons rocheux |
| **Plat** | `-0.08 à +0.08` | ≈ 0 | Terrain uniforme |
| **Concave** | `< -0.08` | -0.2 à -1.0 | Vallées, creux, ravines, talwegs |

**Utilisation** :
- `convex` → favorise Rock_01, Heather_01 (crêtes exposées)
- `concave * wet` → détecte ravines (vallées + humides)
- Indépendant de la pente (une crête peut être plate)

### Humidité (sediment)

**Source** : Masque `sediment.png` normalisé 0-1

| Signal | Seuil | Rôle écologique |
|--------|-------|-----------------|
| `dry` | `sediment < 0.35` | Zones drainées, crêtes, alpages secs |
| `moist` | `0.12 < sediment < 0.82` | Humidité modérée, prairies |
| `wet` | `sediment > 0.48` | Accumulation forte, ravines, plages humides |

**⚠️ Point critique côtier** :
```python
sc["Pebbles_01"] += coast_flat * wet * 0.38
```
- Plage **sèche** (`sediment = 0.1`) → `wet = 0` → **Pebbles_01 = 0** !
- **Explication** : Recette suppose plage humide = galets, plage sèche = BeachGrass + Dirt
- **Problème** : Trop restrictif pour côtes réelles (galets attendus même si sec)

---

## Contextes écologiques

Les **12 contextes principaux** combinant les 5 signaux :

### Contextes côtiers

| Contexte | Formule | Zone typique |
|----------|---------|--------------|
| `coast_flat` | `coastal * (flat + gentle*0.8 + moderate*0.4)` | Plages plates, dunes |
| `coast_talus` | `coastal * (moderate + steep*0.3)` | Pentes côtières, dunes raides |
| `coast_cliff` | `coastal * steep` | Falaises côtières |

**⚠️ Problème détecté** :
- `coast_talus` nécessite `moderate` (pente > 7.5°) → **inactif sur collines douces 5-7°**
- `coast_cliff` nécessite `steep` (pente > 10.8°) → **inactif sur petites falaises 8-10°**

### Contextes prairies

| Contexte | Formule | Zone typique |
|----------|---------|--------------|
| `prairie_low` | `lowland * (flat+gentle) * (1-steep) * (1-ravine)` | Prairies basses terres |
| `prairie_mid` | `midland * (flat+gentle) * (1-steep)` | Prairies collines |

**Points clés** :
- `(1-steep)` = exclusion si pente raide → garantit herbe seulement sur pentes douces
- `(1-ravine)` = exclusion si vallée humide → évite herbe dans ravines

### Contextes montagne

| Contexte | Formule | Zone typique |
|----------|---------|--------------|
| `alpage_dry` | `highland * (flat+gentle) * dry` | Alpages secs, bruyère |
| `alpage_wet` | `highland * (flat+gentle) * (moist+wet*0.4)` | Alpages humides |
| `rocky_highland` | `highland * smoothstep(sl_rh1, sl_rh2, slope)` | Pentes raides haute altitude |
| `crest` | `highland * convex` | Crêtes sommitales |

### Contextes pentes

| Contexte | Formule | Zone typique |
|----------|---------|--------------|
| `mid_slope` | `(lowland+midland) * moderate * (1-steep) * (1-ravine)` | Pentes moyennes herbeuses |
| `rocky_outcrop` | `(lowland+midland+coastal*0.5) * moderate * convex * (1-steep)` | Affleurements rocheux |

### Contextes spéciaux

| Contexte | Formule | Zone typique |
|----------|---------|--------------|
| `ravine` | `concave * wet` | Vallées, talwegs, lits de rivière |
| `cliff_fissure` | `steep * concave` | Fissures dans parois |

---

## Recettes par texture

Voici comment chaque texture reçoit ses poids depuis les contextes :

### SeaBed_01 (Fond marin)

```python
sc["SeaBed_01"] += sub  # sub = smoothstep(-2m, -12m, altitude)
```

**Contexte** : Submergé uniquement  
**Poids** : 100% sous -12m

---

### BeachGrass_01 (Herbe de plage)

```python
sc["BeachGrass_01"] += coast_flat * (1.0 - wet) * (1.0 - convex * 0.8) * 0.55
```

**Contextes** : Plages plates, pas trop humides, pas sur bosses  
**Poids max** : 55% du contexte `coast_flat`  
**⚠️ Note** : Réduit si `wet` élevé (favorise Pebbles) ou si `convex` (favorise Rock)

---

### Grass_03_coastal (Herbe côtière dense)

```python
sc["Grass_03_coastal"] += coast_flat * moist * 0.28
```

**Contextes** : Plages plates humides  
**Poids max** : 28%

---

### Pebbles_01 (Galets fins)

```python
sc["Pebbles_01"] += coast_flat * wet * 0.38           # Plage humide
sc["Pebbles_01"] += coast_talus * 0.45                # Talus côtier
sc["Pebbles_01"] += coast_cliff * 0.12                # Falaise
sc["Pebbles_01"] += ravine * wet * 0.12               # Lit de rivière
```

**Contextes** : Côtier humide, lits de rivière  
**⚠️ Problème** : Ligne 1 nécessite `wet` (sediment > 0.48) → absent sur plages sèches

---

### Pebbles_02 (Galets grossiers)

```python
sc["Pebbles_02"] += coast_talus * moderate * 0.18
```

**Contextes** : Talus côtier avec pente moyenne  
**⚠️ Problème** : Nécessite `moderate` (pente > 7.5°) → inactif sur pentes douces

---

### Dirt_01 (Terre franche)

```python
sc["Dirt_01"] += prairie_low * dry * 0.20             # Prairie sèche
sc["Dirt_01"] += prairie_low * moist * 0.16           # Prairie humide
sc["Dirt_01"] += prairie_mid * dry * 0.18             # Colline sèche
sc["Dirt_01"] += rocky_outcrop * 0.10                 # Affleurement
```

**Contextes** : Prairies, affleurements rocheux  
**Poids** : Variable selon humidité

---

### Dirt_02 (Limon / terre sèche)

```python
sc["Dirt_02"] += prairie_low * dry * 0.10
sc["Dirt_02"] += prairie_mid * dry * 0.10
sc["Dirt_02"] += alpage_dry * 0.14
sc["Dirt_02"] += crest * (1.0 - wet) * 0.22
sc["Dirt_02"] += mid_slope * dry * 0.22
sc["Dirt_02"] += rocky_highland * 0.08
```

**Contextes** : Zones sèches, crêtes, alpages  
**Rôle** : Sol drainé, limon

---

### Dirt_03 (Terre érodée / sableuse)

```python
sc["Dirt_03"] += coast_flat * dry * 0.38              # Plage sèche
sc["Dirt_03"] += coast_talus * 0.18                   # Talus côtier
sc["Dirt_03"] += ravine * (0.70 - wet * 0.22)         # Ravine (liant)
sc["Dirt_03"] += prairie_low * wet * 0.18             # Prairie humide
sc["Dirt_03"] += mid_slope * moist * 0.22             # Pente moyenne
sc["Dirt_03"] += alpage_wet * wet * 0.15              # Alpage humide
```

**Contextes** : Érosion légère, zones humides, liant dans ravines  
**Rôle** : Terre + cailloux, sable côtier

---

### Debris_Rock_01 (Débris rocheux / éboulis)

```python
sc["Debris_Rock_01"] += ravine * (0.30 + wet * 0.22)  # Ravine (débris)
sc["Debris_Rock_01"] += cliff_fissure * 0.18          # Fissures parois
sc["Debris_Rock_01"] += (lowland+midland) * steep * 0.14  # Pentes raides basses
sc["Debris_Rock_01"] += crest * 0.14                  # Crêtes
sc["Debris_Rock_01"] += mid_slope * dry * 0.18        # Pentes moyennes sèches
sc["Debris_Rock_01"] += mid_slope * dry * convex * 0.10  # Pentes convexes
sc["Debris_Rock_01"] += rocky_highland * 0.24         # Pentes highland
sc["Debris_Rock_01"] += rocky_outcrop * 0.28          # Affleurements
sc["Debris_Rock_01"] += coast_cliff * 0.20            # Falaises côtières
```

**Contextes** : Érosion forte, éboulis, pentes raides  
**Poids** : Très présent, rôle de transition vers roche nue

---

### Rock_01 (Roche nue)

```python
sc["Rock_01"] += steep * (1.0 - cliff_fissure * 0.15) * 0.90  # Parois
sc["Rock_01"] += crest * dry * (0.38 + steep * 0.08)          # Crêtes
sc["Rock_01"] += rocky_highland * 0.52                        # Highland raide
sc["Rock_01"] += rocky_outcrop * 0.38                         # Affleurements
sc["Rock_01"] += coast_cliff * 0.60                           # Falaises côtières
```

**Contextes** : Pentes raides, crêtes, affleurements, falaises  
**Poids** : Dominant sur terrain > 10.8°  
**⚠️ Problème côtier** : `coast_cliff` nécessite `steep` (>10.8°) → inactif sur falaises douces

---

### Grass_01, Grass_02, Grass_03 (Herbes prairies)

```python
# Grass_01 (herbe rase)
sc["Grass_01"] += cliff_fissure * 0.04                # Fissures
sc["Grass_01"] += crest * (1-steep) * (1-wet) * 0.18  # Crêtes plates
sc["Grass_01"] += alpage_dry * 0.16                   # Alpages secs
sc["Grass_01"] += prairie_low * dry * 0.28            # Prairies sèches
sc["Grass_01"] += mid_slope * dry * 0.20              # Pentes moyennes

# Grass_02 (herbe standard)
sc["Grass_02"] += coast_talus * (1-steep) * 0.24      # Talus doux
sc["Grass_02"] += prairie_low * dry * 0.38            # Prairie sèche
sc["Grass_02"] += prairie_low * moist * 0.34          # Prairie humide
sc["Grass_02"] += prairie_mid * dry * 0.20            # Colline

# Grass_03 (herbe dense)
sc["Grass_03"] += prairie_low * moist * 0.32          # Prairie humide
sc["Grass_03"] += prairie_mid * moist * 0.20          # Colline humide
sc["Grass_03"] += alpage_wet * moist * 0.14           # Alpage humide
```

**Contextes** : Prairies basses, collines, pentes douces  
**Répartition** : Grass_01 (sec), Grass_02 (polyvalent), Grass_03 (humide)

---

### MountainGrass_01/02/03 (Herbes alpines)

```python
# MountainGrass_01 (rase alpine)
sc["MountainGrass_01"] += crest * dry * 0.10
sc["MountainGrass_01"] += alpage_dry * 0.28
sc["MountainGrass_01"] += mid_slope * (1-moist) * 0.26
sc["MountainGrass_01"] += rocky_highland * (1-steep) * 0.08

# MountainGrass_02 (standard alpine)
sc["MountainGrass_02"] += alpage_wet * 0.28
sc["MountainGrass_02"] += prairie_mid * dry * 0.32

# MountainGrass_03 (dense alpine)
sc["MountainGrass_03"] += alpage_wet * moist * 0.44
sc["MountainGrass_03"] += prairie_mid * moist * 0.32
```

**Contextes** : Highland, alpages, prairies haute altitude  
**Activation** : Selon profil hypsométrique (p45 à p75)

---

### Heather_01 (Bruyère / lande)

```python
sc["Heather_01"] += alpage_dry * 0.34
sc["Heather_01"] += prairie_mid * convex * dry * 0.14
```

**Contextes** : Alpages secs, crêtes exposées  
**Rôle** : Végétation résistante zones sèches

---

## Normalisation finale

### Pourquoi normaliser ?

Après application des recettes, chaque pixel a des poids **bruts** pour chaque texture :

```
Pixel exemple :
  Rock_01 = 0.52
  Debris_Rock_01 = 0.28
  Dirt_02 = 0.18
  MountainGrass_01 = 0.12
  TOTAL = 1.10  ← Somme > 1.0 !
```

**Problème** : Format QTRE Reforger nécessite `somme = 1.0` (pondération normalisée).

### Algorithme

**Fichier** : `pipeline_core.py` lignes 788-796

```python
# Pour chaque chunk de 256 lignes
for row_start in range(0, rows, 256):
    row_end = min(row_start + 256, rows)
    
    # Calculer scores pour ce chunk
    scores = compute_chunk_blends(h_chunk, s_chunk, c_chunk, sed_chunk, ...)
    
    # Normaliser
    total = np.zeros(h_chunk.shape, dtype=np.float32)
    for stem in biome_stems:
        total += scores.get(stem, 0.0)
    
    # Éviter division par zéro
    total = np.where(total == 0.0, 1.0, total)
    
    # Diviser chaque score par le total
    for stem in biome_stems:
        out_maps[stem][row_start:row_end] = scores[stem] / total
```

### Résultat après normalisation

```
Pixel exemple APRÈS normalisation :
  Rock_01 = 0.52 / 1.10 = 0.473  (47.3%)
  Debris_Rock_01 = 0.28 / 1.10 = 0.255  (25.5%)
  Dirt_02 = 0.18 / 1.10 = 0.164  (16.4%)
  MountainGrass_01 = 0.12 / 1.10 = 0.109  (10.9%)
  TOTAL = 1.000  ✓
```

**Export PNG 16-bit** : `valeur_uint16 = int(poids_normalisé * 65535)`

---

## Exemples concrets

### Exemple 1 : Plage plate sèche

**Input masques** :
- Heightmap : 3m
- Slope : 2°
- Curvature : 0.0
- Sediment : 0.1 (sec)

**Signaux calculés** :
```
coastal = 0.80  (pleine zone côtière)
flat = 0.60
gentle = 0.40
dry = 1.0
wet = 0.0  ← CRITIQUE
```

**Contextes actifs** :
```
coast_flat = 0.80 * (0.60 + 0.40*0.8) = 0.74
coast_talus = 0.0  (pas de moderate)
coast_cliff = 0.0  (pas de steep)
```

**Textures résultantes** (poids bruts) :
```
BeachGrass_01 = 0.74 * 1.0 * 1.0 * 0.55 = 0.407
Dirt_03 = 0.74 * 1.0 * 0.38 = 0.281
Pebbles_01 = 0.74 * 0.0 * 0.38 = 0.000  ← ABSENT (wet=0)
```

**Après normalisation** (total = 0.688) :
```
BeachGrass_01 : 59.2%
Dirt_03 : 40.8%
Pebbles_01 : 0%  ← PROBLÈME IDENTIFIÉ
```

**Analyse** :
- ✅ BeachGrass présent (logique)
- ✅ Dirt_03 présent (sable/terre côtière)
- ❌ **Pebbles_01 absent** alors qu'attendu sur plage

**Cause** : Recette `coast_flat * wet * 0.38` nécessite `wet > 0` (sediment > 0.48)

---

### Exemple 2 : Colline côtière 12°

**Input masques** :
- Heightmap : 15m
- Slope : 12°
- Curvature : 0.2 (convexe)
- Sediment : 0.3

**Signaux calculés** :
```
coastal = 1.0
moderate = 0.35  (12° début moderate)
steep = 0.08
convex = 0.38
moist = 0.80
```

**Contextes actifs** :
```
coast_flat = 1.0 * (0 + 0 + 0.35*0.4) = 0.14
coast_talus = 1.0 * (0.35 + 0.08*0.3) = 0.374
coast_cliff = 1.0 * 0.08 = 0.08
rocky_outcrop = 1.0 * 0.35 * 0.38 * 0.92 = 0.122
```

**Textures résultantes** (poids bruts) :
```
BeachGrass_01 = 0.14 * 0.80 * 0.55 = 0.062
Pebbles_01 (talus) = 0.374 * 0.45 = 0.168
Pebbles_02 = 0.374 * 0.35 * 0.18 = 0.024
Rock_01 (cliff) = 0.08 * 0.60 = 0.048
Rock_01 (outcrop) = 0.122 * 0.38 = 0.046
Debris_Rock_01 = 0.08 * 0.20 = 0.016
Grass_02 = 0.374 * 0.92 * 0.24 = 0.083
Dirt_03 = 0.374 * 0.18 = 0.067
```

**Après normalisation** (total ≈ 0.514) :
```
Pebbles_01 : 32.7%
Grass_02 : 16.1%
Dirt_03 : 13.0%
Rock_01 : 18.3%
BeachGrass_01 : 12.1%
Pebbles_02 : 4.7%
Debris_Rock_01 : 3.1%
```

**Analyse** :
- ✅ Mélange réaliste Pebbles + Rock + Herbe
- ✅ Convexité favorise Rock (affleurement)
- ✅ Pente 12° active `moderate` → Pebbles_02 apparaît

---

### Exemple 3 : Prairie intérieure 120m

**Input masques** :
- Heightmap : 120m
- Slope : 4°
- Curvature : -0.1 (concave)
- Sediment : 0.5 (humide)

**Signaux calculés** :
```
coastal = 0.0
lowland = 0.85
gentle = 0.80
concave = 0.15
moist = 0.70
wet = 0.30
```

**Contextes actifs** :
```
prairie_low = 0.85 * (0.2+0.8) * 1.0 * (1-0.15*0.3) = 0.812
ravine = 0.15 * 0.30 = 0.045
```

**Textures résultantes** (poids bruts) :
```
Grass_02 (dry) = 0.812 * 0.0 * 0.34 = 0.0
Grass_02 (moist) = 0.812 * 0.70 * 0.34 = 0.193
Grass_03 (moist) = 0.812 * 0.70 * 0.32 = 0.182
Dirt_01 (moist) = 0.812 * 0.70 * 0.16 = 0.091
Dirt_03 (wet) = 0.812 * 0.30 * 0.18 = 0.044
Dirt_03 (ravine) = 0.045 * 0.70 = 0.032
```

**Après normalisation** (total ≈ 0.542) :
```
Grass_02 : 35.6%
Grass_03 : 33.6%
Dirt_01 : 16.8%
Dirt_03 : 14.0%
```

**Analyse** :
- ✅ Prairie humide réaliste (Grass_02 + Grass_03)
- ✅ Trace de Dirt (terre visible)
- ✅ Concavité légère → pas assez pour ravine marquée

---

## Diagnostiquer un problème

### Méthodologie

Quand une texture est **absente** ou **trop présente**, suivre cette checklist :

#### 1. Identifier la texture problématique

Exemple : "Pebbles_01 manquant sur plages"

#### 2. Lire les recettes dans le code

**Fichier** : `pipeline_core.py` lignes 301-390

```python
# Chercher toutes les lignes avec "Pebbles_01"
sc["Pebbles_01"] += coast_flat * wet * 0.38           # Ligne 310
sc["Pebbles_01"] += coast_talus * 0.45                # Ligne 313
sc["Pebbles_01"] += coast_cliff * 0.12                # Ligne 389
sc["Pebbles_01"] += ravine * wet * 0.12               # Ligne 320
```

#### 3. Vérifier chaque contexte

Pour chaque recette, décomposer le contexte :

**Exemple ligne 310** : `coast_flat * wet * 0.38`

- **Contexte** : `coast_flat`
  - Formule : `coastal * (flat + gentle*0.8 + moderate*0.4)` (ligne 289)
  - Nécessite : `coastal > 0` ET `(flat OU gentle OU moderate)`
  
- **Signal** : `wet`
  - Formule : `smoothstep(0.48, 0.78, sediment)` (ligne 283)
  - Nécessite : `sediment > 0.48`

#### 4. Tester avec des valeurs réelles

Simuler le pixel problématique :

```python
# Plage altitude=3m, pente=2°, sediment=0.1
coastal = 0.80  ✓
flat = 0.60     ✓
wet = 0.0       ✗ CAUSE TROUVÉE (sediment 0.1 < 0.48)

coast_flat = 0.80 * 0.60 = 0.48  ✓
Pebbles_01 = 0.48 * 0.0 * 0.38 = 0.0  ✗
```

#### 5. Identifier la cause racine

| Cause possible | Vérification |
|----------------|--------------|
| **Masque input incorrect** | Vérifier `sediment.png` : valeurs 0-1 correctes ? |
| **Seuil trop restrictif** | `wet` nécessite `sediment > 0.48` trop élevé pour plages |
| **Contexte inactif** | `coast_talus` nécessite `moderate` (pente > 7.5°) |
| **Recette manquante** | Pas de recette pour contexte "plage sèche + galets" |

#### 6. Solutions possibles

| Solution | Avantages | Inconvénients |
|----------|-----------|---------------|
| **Ajuster masque sediment** | Pas de code à modifier | Impacte aussi prairies/ravines |
| **Ajouter recette spécifique** | Ciblé, pas d'effet de bord | Nécessite modification code |
| **Baisser seuil wet** | Simple | Impacte TOUT le terrain (ravines, prairies) |

---

### Cas fréquents

#### Problème : "Pas assez de Rock sur falaises côtières"

**Recette concernée** : `sc["Rock_01"] += coast_cliff * 0.60` (ligne 387)

**Contexte** : `coast_cliff = coastal * steep` (ligne 299)

**Vérification** :
- `coastal` actif ? (altitude 0-50m) → ✓
- `steep` actif ? (pente > 10.8°) → ✗ Falaise 8° trop douce

**Cause** : Seuil `steep` trop élevé (10.8° avec slope_p90=15°)

**Solution** : Ajouter recette intermédiaire
```python
coast_moderate_cliff = coastal * smoothstep(6.0, 12.0, s_chunk)
sc["Rock_01"] += coast_moderate_cliff * 0.40
```

---

#### Problème : "Trop de Debris_Rock partout"

**Recettes concernées** : 9 sources différentes (lignes 319-389)

**Vérification** :
```python
# Compter les contributions
Debris_Rock_01 total = ravine + cliff_fissure + steep_low + crest + 
                       mid_slope_dry + mid_slope_convex + rocky_highland + 
                       rocky_outcrop + coast_cliff
```

**Cause probable** : Cumul de toutes les sources → poids > autres textures

**Solution** : Réduire coefficients (0.28 → 0.18) ou exclure certains contextes

---

#### Problème : "BeachGrass remplacé par Grass_02"

**Recettes concernées** :
- `BeachGrass_01` : `coast_flat * (1-wet) * (1-convex*0.8) * 0.55` (ligne 307)
- `Grass_02` : `coast_talus * (1-steep) * 0.24` (ligne 315)

**Vérification** :
- Si pente = 8° → `coast_talus` actif, `coast_flat` réduit
- `Grass_02` prend le dessus car coefficient plus favorable

**Cause** : Transition `coast_flat` → `coast_talus` trop agressive

**Solution** : Ajuster ligne 289 (élargir `coast_flat`)
```python
coast_flat = coastal * (flat + gentle * 0.9 + moderate * 0.6)  # Au lieu de 0.8 et 0.4
```

---

### Outils de diagnostic

#### Logs pipeline

Le pipeline affiche les seuils calculés :

```
[CALIBRATION] alt_max=499m  slope_p90=15.000
[CALIBRATION] Profil terrain : balanced  (mean=0.42  spread=0.38)
[CALIBRATION] coastal 5→50m  |  lowland 1→210m  |  highland 189→387m
```

**À vérifier** :
- `slope_p90` cohérent avec le terrain ?
- Profil détecté correct ? (flat vs mountain)
- Seuils highland trop tôt/tard ?

#### Validation masques

Vérifier les masques inputs avant de lancer le pipeline :

```python
import cv2
import numpy as np

# Slope.png
slope = cv2.imread("slope.png", cv2.IMREAD_UNCHANGED)
print(f"Slope min={slope.min()}, max={slope.max()}, mean={slope.mean():.1f}")
# Attendu : min=0, max=255, mean=20-50 (terrain moyen)

# Sediment.png
sed = cv2.imread("sediment.png", cv2.IMREAD_UNCHANGED)
sed_norm = sed / 255.0
print(f"Sediment zones: dry={np.sum(sed_norm<0.35)/sed.size*100:.1f}%, wet={np.sum(sed_norm>0.48)/sed.size*100:.1f}%")
# Attendu : 30-50% dry, 10-30% wet
```

---

## Conclusion

### Points clés à retenir

1. **5 signaux indépendants** : altitude, pente, courbure, humidité, calibration
2. **Multiplication** des signaux → contextes écologiques
3. **Contextes non-exclusifs** : un pixel peut être 60% lowland + 40% midland
4. **Recettes additives** : chaque texture cumule des poids depuis plusieurs contextes
5. **Normalisation finale** : garantit somme = 1.0 par pixel (format QTRE)

### Limitations connues

| Limitation | Impact | Workaround |
|------------|--------|------------|
| Seuil `wet > 0.48` trop restrictif | Pebbles absents plages sèches | Ajuster masque sediment OU ajouter recette |
| `moderate` démarre à 7.5° | Talus côtiers inactifs 5-7° | Ajouter recette `coast_gentle` |
| `steep` démarre à 10.8° | Falaises douces sans Rock | Baisser `sl_st1` OU ajouter recette |
| Signaux globaux partagés | Impossible modifier côtier seul | Créer signaux locaux (ex: `coast_moderate`) |

### Évolutions futures

**Phase 1 — Corrections côtières** (priorité haute) :
- Ajouter recette `Pebbles_01` sans dépendance `wet`
- Créer contexte `coast_gentle` (pente 3-8°)
- Ajouter recette `Rock_01` pour petites falaises (7-10°)

**Phase 2 — Bibliothèque matériaux** :
- Externaliser recettes dans `material_library_vanilla.json`
- Permettre surcharge par projet
- Interface UI pour ajuster coefficients

**Phase 3 — Végétation** :
- Intégrer masques végétation (forêts, clairières)
- Recettes `ForestDeciduous_01`, `ForestConiferous_01`
- Transitions lisières

---

**Document généré automatiquement**  
Source : `pipeline_core.py` (commit 421ccdb)  
Dernière mise à jour : 2026-06-01
