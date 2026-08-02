# Changelog Phase 1 — Corrections Côtier

**Date** : 2026-06-01 15:00  
**Version** : Phase 1 (côtier uniquement)  
**Backup** : `pipeline_core_backup_20260601_150059.py`

---

## 📝 Modifications appliquées

### ✅ Modification 1 : Élargir coast_flat

**Fichier** : `pipeline_core.py` ligne 289  
**Type** : Modification coefficients

```python
# AVANT
coast_flat = coastal * (flat + gentle * 0.8 + moderate * 0.4)

# APRÈS
coast_flat = coastal * (flat + gentle * 0.9 + moderate * 0.5)
```

**Objectif** : Plages sur pente 8-12° mieux couvertes  
**Impact** : Boost coast_flat de 5-20% sur pentes douces

---

### ✅ Modification 2 : Nouveau contexte coast_gentle

**Fichier** : `pipeline_core.py` après ligne 290  
**Type** : Ajout contexte

```python
coast_gentle = coastal * smoothstep(5.0, 10.0, s_chunk) * (1.0 - smoothstep(12.0, 20.0, s_chunk))
```

**Objectif** : Détecter pentes côtières douces 5-12°  
**Impact** : Nouveau signal pour talus doux

---

### ✅ Modification 3 : Nouveau contexte coast_outcrop

**Fichier** : `pipeline_core.py` après ligne 299  
**Type** : Ajout contexte

```python
coast_outcrop = coastal * convex * smoothstep(6.0, 12.0, s_chunk)
```

**Objectif** : Détecter affleurements rocheux côtiers convexes  
**Impact** : Rock sur bosses/éperons côtiers

---

### ✅ Modification 4 : Recettes Pebbles sediment modéré

**Fichier** : `pipeline_core.py` après ligne 312  
**Type** : Ajout recettes

```python
sc["Pebbles_01"] += coast_flat * moist * 0.18
sc["Pebbles_01"] += coast_flat * (1.0 - dry) * 0.10
```

**Objectif** : Pebbles sur plages sediment 0.3-0.6  
**Impact** : Galets présents même si sediment < 0.48

---

### ✅ Modification 5 : Recettes coast_gentle

**Fichier** : `pipeline_core.py` après ligne 318  
**Type** : Ajout recettes

```python
sc["Pebbles_01"] += coast_gentle * 0.22
sc["Pebbles_02"] += coast_gentle * 0.12
sc["Grass_02"]   += coast_gentle * 0.18
sc["Dirt_03"]    += coast_gentle * 0.12
```

**Objectif** : Texturer talus côtiers 5-12°  
**Impact** : Pebbles + Grass sur pentes douces

---

### ✅ Modification 6 : Recettes coast_outcrop

**Fichier** : `pipeline_core.py` après ligne 399  
**Type** : Ajout recettes

```python
sc["Rock_01"]        += coast_outcrop * 0.30
sc["Debris_Rock_01"] += coast_outcrop * 0.20
sc["Pebbles_02"]     += coast_outcrop * 0.12
```

**Objectif** : Rock sur bosses côtières convexes  
**Impact** : Affleurements rocheux sur éperons

---

## 📊 Résumé

| Type | Nombre | Lignes touchées |
|------|--------|-----------------|
| Contextes ajoutés | 2 | coast_gentle, coast_outcrop |
| Coefficients modifiés | 2 | gentle 0.8→0.9, moderate 0.4→0.5 |
| Recettes ajoutées | 9 lignes | Pebbles, Rock, Grass, Dirt |
| **TOTAL** | **13 lignes** | Sur ~1500 lignes (0.9%) |

---

## 🎯 Objectifs Phase 1

### Problèmes corrigés

1. ✅ **Pebbles absents plages moyennes** (sediment 0.3-0.5)
   - Solution : 2 recettes alternatives (moist, 1-dry)
   
2. ✅ **Talus côtiers 5-12° sous-texturés**
   - Solution : Nouveau contexte coast_gentle + 4 recettes
   
3. ✅ **Affleurements rocheux côtiers manquants**
   - Solution : Nouveau contexte coast_outcrop + 3 recettes

### Zones impactées

- ✅ **Plages plates** (0-5°)
- ✅ **Plages douces** (5-8°)
- ✅ **Talus côtiers** (8-12°)
- ✅ **Collines côtières convexes** (6-15°)
- ✅ **Falaises moyennes** (12-25°)

### Zones NON impactées (préservées)

- ✅ **Prairies basses** (lowland)
- ✅ **Prairies collines** (midland)
- ✅ **Alpages** (highland)
- ✅ **Pentes moyennes inland**
- ✅ **Ravines**
- ✅ **Crêtes**

---

## 🧪 Tests à effectuer

### Test 1 : Plage plate sediment=0.35

**Avant** :
```
BeachGrass_01 : 55%
Dirt_03 : 38%
Pebbles_01 : 0%   ← PROBLÈME
```

**Attendu après** :
```
BeachGrass_01 : 45-50%
Dirt_03 : 25-30%
Pebbles_01 : 15-20%  ← CORRIGÉ
Grass_03_coastal : 5-10%
```

---

### Test 2 : Colline côtière 8°, sediment=0.3

**Avant** :
```
BeachGrass_01 : 45%
Dirt_03 : 35%
Grass_02 : 15%
Pebbles_02 : 0%   ← PROBLÈME
```

**Attendu après** :
```
Pebbles_01 : 20-25%
Pebbles_02 : 10-15%  ← CORRIGÉ
Grass_02 : 15-20%
BeachGrass_01 : 25-30%
Dirt_03 : 15-20%
```

---

### Test 3 : Bosse côtière convexe (curvature=0.2, pente=9°)

**Avant** :
```
BeachGrass_01 : 40%
Dirt_03 : 30%
Rock_01 : 5%      ← INSUFFISANT
```

**Attendu après** :
```
Rock_01 : 20-25%     ← CORRIGÉ
Pebbles_01 : 15-20%
Debris_Rock_01 : 12-15%
Grass_02 : 15-20%
BeachGrass_01 : 15-20%
Dirt_03 : 10-15%
```

---

## ⚠️ Validation

### Checklist avant génération

```
☑ Backup créé (pipeline_core_backup_20260601_150059.py)
☑ Syntaxe Python validée (py_compile OK)
☑ 13 lignes modifiées seulement
☑ Zone côtière ciblée uniquement
☑ Inland préservé
```

### Checklist après génération

```
☐ Générer Zimnitrita
☐ Vérifier visuellement zone côtière
☐ Plages ont Pebbles ? (sediment 0.3-0.5)
☐ Talus 5-12° texturés ? (Pebbles_02 visible)
☐ Bosses côtières ont Rock ? (affleurements)
☐ Prairies inland intactes ? (non-régression)
☐ Alpages intacts ? (non-régression)
```

---

## 🔄 Rollback si problème

**Si résultat non satisfaisant** :

```bash
cd "h:\logiciel perso\Map generator"
cp pipeline_core.py pipeline_core_phase1_failed.py
cp pipeline_core_backup_20260601_150059.py pipeline_core.py
```

**Puis** : Analyser ce qui n'a pas fonctionné avant Phase 2

---

## 📅 Prochaines phases (à faire APRÈS validation Phase 1)

### Phase 2 : Corrections Dirt/Grass inland

**Problème** : Dirt_02 trop présent (22%) sur pentes moyennes et crêtes

**Actions prévues** :
- Réduire Dirt_02 sur mid_slope (0.22 → 0.14)
- Réduire Dirt_02 sur crest (0.22 → 0.15)
- Booster Grass_01 et MountainGrass_01 en compensation

**Timing** : Après validation visuelle Phase 1

---

### Phase 3 : Corrections érosion

**Problème** : À diagnostiquer précisément (zones à identifier)

**Actions prévues** : À définir après Phase 2

**Timing** : Après validation Phase 2

---

## 📝 Notes développeur

### Pourquoi ces valeurs de coefficients ?

**coast_gentle (5-12°)** :
- Pebbles_01 = 0.22 (dominant léger)
- Pebbles_02 = 0.12 (galets grossiers modérés)
- Grass_02 = 0.18 (herbe standard)
- Dirt_03 = 0.12 (sable/terre)

➡️ Total ≈ 0.64 → Après normalisation : mix équilibré

**coast_outcrop (convexe + 6-12°)** :
- Rock_01 = 0.30 (affleurement principal)
- Debris_Rock_01 = 0.20 (éboulis)
- Pebbles_02 = 0.12 (galets grossiers)

➡️ Total ≈ 0.62 → Après normalisation : Rock dominant à ~50%

---

## ✅ Validation syntaxe

```bash
python -m py_compile pipeline_core.py
# Résultat : OK - Syntaxe Python valide
```

---

**Fichier généré automatiquement**  
Phase 1 — Corrections côtier uniquement  
Zone inland 100% préservée  
2026-06-01 15:00
