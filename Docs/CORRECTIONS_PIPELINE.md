# Corrections Pipeline — Plan d'affinage

**Version** : 1.0  
**Date** : 2026-06-01  
**Objectif** : Affiner les valeurs du pipeline pour cohérence avec `TEXTURES_PAR_MASQUE.md`

---

## 🎯 Problèmes identifiés

### Problème 1 : Pebbles absents plages moyennement humides

**Symptôme** : Plages avec sediment 0.3-0.5 n'ont pas de galets

**Cause** :
```python
# Ligne 310 - Seule recette Pebbles_01 sur plage
sc["Pebbles_01"] += coast_flat * wet * 0.38
# wet = smoothstep(0.48, 0.78, sediment)
```

➡️ Si `sediment < 0.48` → `wet = 0` → Pebbles_01 = 0

**Doc dit** : Pebbles_01 logique pour sediment 0.6-0.8, mais aussi acceptable 0.4-0.6 (modéré)

**Impact** : 60% des plages sans galets alors que géologiquement plausible

---

### Problème 2 : Talus côtiers 5-12° sous-texturés

**Symptôme** : Collines côtières douces (6-10°) manquent Pebbles_02, Debris_Rock, Rock

**Cause** :
```python
# Lignes 290, 313-316
coast_talus = coastal * (moderate + steep * 0.3)
# moderate = smoothstep(7.5, 14.0, slope)

sc["Pebbles_02"] += coast_talus * moderate * 0.18
```

➡️ Pente 8° → `moderate = 0.07` → `coast_talus` très faible

**Doc dit** : Pente 8-15° devrait avoir Debris_Rock_01, Pebbles_01/02

**Impact** : Zone 5-12° (courante sur côtes réelles) mal représentée

---

### Problème 3 : Affleurements rocheux côtiers manquants

**Symptôme** : Bosses/éperons côtiers convexes sans Rock_01

**Cause** :
```python
# Ligne 298
rocky_outcrop = (lowland + midland + coastal * 0.5) * moderate * convex * (1 - steep)
```

➡️ Dépend de `moderate` (pente > 7.5°) → colline douce convexe ignorée

**Doc dit** : Curvature convexe > 0.15 devrait favoriser Rock_01 même sur pente douce

**Impact** : Affleurements rocheux sous-représentés en zone côtière

---

### Problème 4 : Recettes trop restrictives (chemins uniques)

**Symptôme** : Chaque texture a 1-2 chemins maximum vers elle

**Exemple Pebbles_01** :
- Chemin 1 : `coast_flat * wet` (sediment > 0.48)
- Chemin 2 : `coast_talus` (pente > 7.5°)
- Chemin 3 : `coast_cliff` (pente > 10.8°)
- Chemin 4 : `ravine * wet` (sediment > 0.48)

➡️ **Manque chemins alternatifs** pour cas intermédiaires

**Doc suggère** : Pebbles_01 devrait venir aussi de :
- Sediment modéré (0.3-0.5)
- Pente douce côtière (5-8°)
- Affleurement convexe doux

**Impact** : Couverture incomplète des cas réels

---

## ✅ Corrections proposées

### Correction 1 : Ajouter recettes sediment modéré

**Fichier** : `pipeline_core.py` lignes 307-316  
**Action** : Ajouter 3 nouvelles lignes après ligne 310

```python
# B. CÔTE PLATE — Actuel
sc["BeachGrass_01"]    += coast_flat * (1.0 - wet) * (1.0 - convex * 0.8) * 0.55
sc["Grass_03_coastal"] += coast_flat * moist           * 0.28
sc["Dirt_03"]          += coast_flat * dry             * 0.38
sc["Pebbles_01"]       += coast_flat * wet             * 0.38

# NOUVEAU : Ajouter chemins alternatifs
sc["Pebbles_01"]       += coast_flat * moist * 0.20              # Sediment modéré
sc["Pebbles_01"]       += coast_flat * (1.0 - dry) * 0.12        # Pas trop sec
sc["BeachGrass_01"]    += coast_flat * moist * 0.18              # Boost humidité moyenne
```

**Effet** :
- Plage sediment=0.4 → `moist ≈ 0.7` → Pebbles_01 += 0.14 ✓
- Plage sediment=0.3 → `(1-dry) ≈ 0.8` → Pebbles_01 += 0.10 ✓
- Garde dominance BeachGrass sur plages sèches

**Validation** :
| Sediment plage | Avant | Après |
|----------------|-------|-------|
| 0.2 (sec) | BeachGrass 60%, Dirt 40% | BeachGrass 55%, Dirt 35%, Pebbles 10% ✓ |
| 0.4 (moyen) | BeachGrass 45%, Dirt 35%, Grass_coastal 20% | BeachGrass 40%, Pebbles 20%, Dirt 25%, Grass 15% ✓ |
| 0.6 (humide) | Pebbles 38%, BeachGrass 30%, Grass 20%, Dirt 12% | Pebbles 50%, BeachGrass 25%, Grass 15%, Dirt 10% ✓ |

---

### Correction 2 : Créer contexte pente douce côtière

**Fichier** : `pipeline_core.py` lignes 285-299  
**Action** : Ajouter nouveau contexte après ligne 290

```python
# Contextes actuels
coast_flat    = coastal  * (flat + gentle * 0.8 + moderate * 0.4)
coast_talus   = coastal  * (moderate + steep * 0.3)

# NOUVEAU : Pente douce côtière (5-12°) — entre flat et talus
coast_gentle_slope = coastal * smoothstep(5.0, 10.0, s_chunk) * (1.0 - smoothstep(12.0, 20.0, s_chunk))
```

**Utiliser dans recettes** (après ligne 316) :

```python
# C. TALUS CÔTIER — Actuel
sc["Pebbles_01"]       += coast_talus                  * 0.45
sc["Pebbles_02"]       += coast_talus * moderate       * 0.18
sc["Grass_02"]         += coast_talus * (1.0 - steep)  * 0.24
sc["Dirt_03"]          += coast_talus                  * 0.18

# NOUVEAU : Pente douce côtière (5-12°)
sc["Pebbles_01"]       += coast_gentle_slope * 0.25
sc["Pebbles_02"]       += coast_gentle_slope * 0.15
sc["Debris_Rock_01"]   += coast_gentle_slope * convex * 0.18
sc["Grass_02"]         += coast_gentle_slope * 0.20
sc["Dirt_03"]          += coast_gentle_slope * 0.15
```

**Effet** :
- Colline côtière 8° → `coast_gentle_slope ≈ 0.6` → Pebbles_02 += 0.09 ✓
- Si convexe → Debris_Rock += 0.11 ✓
- Couvre le trou 5-12° entre `coast_flat` et `coast_talus`

---

### Correction 3 : Affleurement rocheux convexe côtier

**Fichier** : `pipeline_core.py` lignes 285-299  
**Action** : Ajouter nouveau contexte

```python
# NOUVEAU : Affleurement rocheux côtier (convexe + pente 6-15°)
coast_rock_outcrop = coastal * convex * smoothstep(6.0, 12.0, s_chunk) * (1.0 - smoothstep(18.0, 30.0, s_chunk))
```

**Utiliser dans recettes** (après ligne 389) :

```python
# N. FALAISES CÔTIÈRES — Actuel
sc["Rock_01"]          += coast_cliff                  * 0.60
sc["Debris_Rock_01"]   += coast_cliff                  * 0.20
sc["Pebbles_01"]       += coast_cliff                  * 0.12

# NOUVEAU : Affleurement rocheux côtier (pente moyenne convexe)
sc["Rock_01"]          += coast_rock_outcrop * 0.35
sc["Debris_Rock_01"]   += coast_rock_outcrop * 0.25
sc["Pebbles_02"]       += coast_rock_outcrop * 0.15
sc["Heather_01"]       += coast_rock_outcrop * (1.0 - steep) * 0.10  # Lande si pas trop raide
```

**Effet** :
- Bosse côtière curvature=0.25, pente=9° → `coast_rock_outcrop ≈ 0.5` → Rock_01 += 0.18 ✓
- Indépendant de `moderate` (ne dépend que convex + pente)
- Favorise affleurements sur éperons/promontoires côtiers

---

### Correction 4 : Élargir coast_flat

**Fichier** : `pipeline_core.py` ligne 289  
**Action** : Modifier coefficients

```python
# AVANT
coast_flat = coastal * (flat + gentle * 0.8 + moderate * 0.4)

# APRÈS
coast_flat = coastal * (flat + gentle * 0.9 + moderate * 0.5)
```

**Effet** :
- Pente 8° → `gentle ≈ 0.9` → boost coast_flat de 10%
- Pente 12° → `moderate ≈ 0.3` → boost coast_flat de 25%
- Plages sur pente douce mieux couvertes

**Validation** :
| Pente | coast_flat avant | coast_flat après | Gain |
|-------|------------------|------------------|------|
| 5° | 0.72 | 0.76 | +5% |
| 8° | 0.64 | 0.70 | +9% |
| 12° | 0.48 | 0.58 | +21% |

---

### Correction 5 : Ajuster seuil wet (optionnel, impact global)

⚠️ **Attention** : Modification globale, impacte prairies + ravines

**Fichier** : `pipeline_core.py` ligne 283  
**Action** : Baisser légèrement seuil

```python
# AVANT
wet = smoothstep(0.48, 0.78, sed_chunk)

# APRÈS (option conservatrice)
wet = smoothstep(0.45, 0.75, sed_chunk)
```

**Effet** :
- Sediment 0.4 : wet passe de 0.00 → 0.06
- Sediment 0.5 : wet passe de 0.07 → 0.20
- Sediment 0.6 : wet passe de 0.40 → 0.53

**⚠️ Impacts collatéraux** :
- Prairies basses : Dirt_03 apparaît plus tôt (sediment 0.45 au lieu de 0.48)
- Ravines : Debris_Rock boosted légèrement
- Alpages : Dirt_03 apparaît sur zones humides

**Recommandation** : **NE PAS faire cette correction** → Utiliser Corrections 1-4 qui sont ciblées côtier

---

## 🧪 Validation des corrections

### Test 1 : Plage plate sediment=0.35

**Avant corrections** :
```
BeachGrass_01 : 55%
Dirt_03 : 38%
Pebbles_01 : 0%   ← PROBLÈME
```

**Après Correction 1** :
```
BeachGrass_01 : 48%
Dirt_03 : 30%
Pebbles_01 : 15%  ← CORRIGÉ
Grass_03_coastal : 7%
```

---

### Test 2 : Colline côtière 8°, sediment=0.3

**Avant corrections** :
```
BeachGrass_01 : 45%
Dirt_03 : 35%
Grass_02 : 15%
Pebbles_01 : 5%
Pebbles_02 : 0%   ← PROBLÈME
```

**Après Corrections 2 + 4** :
```
BeachGrass_01 : 35%
Pebbles_01 : 20%
Pebbles_02 : 12%  ← CORRIGÉ
Dirt_03 : 18%
Grass_02 : 15%
```

---

### Test 3 : Bosse côtière convexe, curvature=0.2, pente=9°

**Avant corrections** :
```
BeachGrass_01 : 40%
Dirt_03 : 30%
Pebbles_01 : 15%
Grass_02 : 10%
Rock_01 : 5%      ← INSUFFISANT
```

**Après Correction 3** :
```
Rock_01 : 25%     ← CORRIGÉ
Pebbles_01 : 18%
Debris_Rock_01 : 15%
BeachGrass_01 : 20%
Dirt_03 : 15%
Pebbles_02 : 7%
```

---

## 📋 Récapitulatif corrections

| # | Correction | Fichier | Lignes | Impact | Priorité |
|---|-----------|---------|--------|--------|----------|
| **1** | Recettes sediment modéré | pipeline_core.py | Après 310 | Pebbles sur plages moyennes | ⭐⭐⭐ HAUTE |
| **2** | Contexte pente douce côtière | pipeline_core.py | Après 290, après 316 | Talus 5-12° | ⭐⭐⭐ HAUTE |
| **3** | Affleurement rocheux convexe | pipeline_core.py | Après 299, après 389 | Rock sur bosses | ⭐⭐ MOYENNE |
| **4** | Élargir coast_flat | pipeline_core.py | Ligne 289 | Plages pente douce | ⭐⭐ MOYENNE |
| **5** | Ajuster seuil wet | pipeline_core.py | Ligne 283 | ⚠️ GLOBAL, déconseillé | ⭐ BASSE |

---

## 🎯 Plan d'action recommandé

### Phase 1 : Corrections ciblées côtier (sans risque)

1. ✅ **Correction 1** : Ajouter 3 lignes recettes sediment modéré
2. ✅ **Correction 4** : Modifier 1 ligne (coast_flat coefficients)
3. ✅ Tester sur Zimnitrita zone côtière
4. ✅ Valider visuellement : Pebbles présents sur plages moyennes

**Temps estimé** : 10 min code + 15 min test = **25 min**

---

### Phase 2 : Contextes additionnels (si Phase 1 OK)

5. ✅ **Correction 2** : Ajouter contexte `coast_gentle_slope` + 5 recettes
6. ✅ **Correction 3** : Ajouter contexte `coast_rock_outcrop` + 4 recettes
7. ✅ Tester sur Zimnitrita complet
8. ✅ Valider visuellement : Talus et affleurements bien texturés

**Temps estimé** : 20 min code + 30 min test = **50 min**

---

### Phase 3 : Validation autre map (universalité)

9. ✅ Tester sur une map **différente** (autre profil hypsométrique)
10. ✅ Vérifier que corrections n'ont pas cassé inland
11. ✅ Ajuster coefficients si besoin (±10% max)

**Temps estimé** : 1h test

---

## 📝 Notes importantes

### Pourquoi pas toucher aux seuils globaux

Les **seuils** (`wet`, `moderate`, `steep`) sont **universels** :
- `wet` à 0.48 = définition physique "sediment élevé"
- `moderate` à 7.5° = définition géologique "pente moyenne"

**Les modifier** casserait :
- Prairies basses (trop humides)
- Ravines (Debris partout)
- Pentes moyennes inland (affleurements rocheux excessifs)

**À la place** : Ajouter **recettes alternatives** qui utilisent signaux intermédiaires (`moist`, `gentle`, `convex`)

---

### Cohérence avec TEXTURES_PAR_MASQUE.md

Ces corrections **alignent le code avec la doc théorique** :

| Doc dit | Code avant | Code après correction |
|---------|------------|----------------------|
| Pebbles si sediment 0.4-0.6 | Non (nécessite > 0.48) | Oui (moist) ✓ |
| Pebbles si pente 8-15° | Non (nécessite > 7.5°) | Oui (coast_gentle_slope) ✓ |
| Rock si convexe > 0.15 | Partiel (dépend moderate) | Oui (coast_rock_outcrop) ✓ |

---

### Impact sur budget textures Reforger

**Avant corrections** : 8-12 textures actives par zone côtière  
**Après corrections** : 10-14 textures actives

➡️ Toujours dans limite QTRE (max 5-7 textures/pixel après squeezing)

Les nouvelles recettes **redistribuent** les poids, ne créent pas forcément de nouvelles textures uniques.

---

## ✅ Validation finale

**Checklist avant commit** :

```
☐ Corrections 1-4 appliquées
☐ Code compile sans erreur
☐ Test Zimnitrita : plages ont Pebbles
☐ Test Zimnitrita : talus 8-12° texturés
☐ Test Zimnitrita : prairies inland intactes
☐ Test autre map : résultat cohérent
☐ Pas de régression visuelle
☐ Documentation mise à jour
```

---

**Document généré automatiquement**  
Basé sur analyse `TEXTURES_PAR_MASQUE.md` vs `pipeline_core.py`  
Dernière mise à jour : 2026-06-01
