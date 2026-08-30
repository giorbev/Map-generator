# Textures par Masque — Référence théorique

**Version** : 1.0  
**Date** : 2026-06-01  
**Objectif** : Documenter quelles textures sont logiquement associées à chaque masque indépendamment

---

## 📋 Principe

Ce document décompose la logique du pipeline **masque par masque** pour comprendre quelles textures devraient apparaître selon les valeurs de chaque masque **pris isolément**.

**Utilité** :
- Diagnostiquer pourquoi une texture est absente
- Comprendre le rôle de chaque masque
- Référence pour ajuster les recettes

---

## 🗻 MASQUE 1 : SLOPE (Pente en degrés)

**Rôle** : Déterminer la **stabilité du terrain** et la capacité à retenir sol/végétation

### Plages de valeurs et textures associées

| Pente (°) | Catégorie | Textures logiques | Raison physique |
|-----------|-----------|-------------------|-----------------|
| **0-3°** | Très plat | `Grass_02`, `Grass_03`, `Dirt_01`, `BeachGrass_01` | Sol stable → végétation dense, terre meuble |
| **3-8°** | Plat | `Grass_01`, `Grass_02`, `MountainGrass_02`, `Dirt_01`, `Dirt_02` | Stable → herbe standard, début drainage |
| **8-15°** | Pente douce | `Grass_01`, `MountainGrass_01/02`, `Dirt_02`, `Heather_01` | Légère érosion → herbes résistantes, terre sèche |
| **15-25°** | Pente moyenne | `Dirt_03`, `Debris_Rock_01`, `Pebbles_01/02`, `MountainGrass_01` | Érosion active → débris, cailloux, herbe alpine rase |
| **25-35°** | Pente forte | `Rock_01`, `Debris_Rock_01`, `Pebbles_02` | Sol instable → roche affleure, éboulis |
| **35-45°** | Très forte | `Rock_01`, `Debris_Rock_01` | Paroi raide → roche dominante, quelques débris |
| **45°+** | Falaise/Paroi | `Rock_01` (quasi exclusif) | Vertical → roche nue seulement |

### Seuils critiques actuels (avec slope_p90 = 15°)

```
flat     : 0 - 5.4°
gentle   : 2.1 - 15.0°
moderate : 7.5 - 26.9°
steep    : 10.8°+
```

### Textures JAMAIS présentes selon pente

| Pente | Textures exclues | Raison |
|-------|------------------|--------|
| **> 25°** | Grass_02, Grass_03, Dirt_01, BeachGrass_01 | Trop raide pour végétation dense |
| **> 35°** | Toutes herbes sauf traces dans fissures | Sol ne tient pas |
| **< 5°** | Rock_01 en dominance (sauf affleurement) | Pas assez raide pour exposer roche |

---

## 🌊 MASQUE 2 : CURVATURE (Courbure -1 à +1)

**Rôle** : Déterminer **forme 3D**, **exposition** et **drainage**

### Plages de valeurs et textures associées

| Curvature | Catégorie | Textures logiques | Raison physique |
|-----------|-----------|-------------------|-----------------|
| **< -0.3** | Vallée profonde | `Debris_Rock_01`, `Dirt_03`, `Pebbles_01/02` | Accumulation débris + eau, talweg |
| **-0.3 à -0.15** | Vallée moyenne | `Grass_03`, `Dirt_01`, `Dirt_03` | Creux humide → herbe dense, terre meuble |
| **-0.15 à -0.08** | Concave légère | `Grass_02`, `Grass_03`, `MountainGrass_03` | Légère dépression → humidité modérée |
| **-0.08 à +0.08** | Plat (neutre) | Toutes textures standards | Pas d'influence forme → neutre |
| **+0.08 à +0.15** | Convexe légère | `Grass_01`, `Heather_01`, `Dirt_02` | Légère bosse → drainage, herbe rase |
| **+0.15 à +0.3** | Bosse/Éperon | `Rock_01`, `Heather_01`, `MountainGrass_01`, `Dirt_02` | Exposé → affleurement, végétation résistante |
| **> +0.3** | Crête marquée | `Rock_01`, `Debris_Rock_01`, `Dirt_02` | Très exposé → roche affleure, terre sèche |

### Combinaisons typiques

| Curvature | + Pente douce | + Pente forte |
|-----------|---------------|---------------|
| **Concave** | Grass_03, Dirt_01 (vallon herbeux) | Debris_Rock_01, Pebbles_02 (ravin/éboulis) |
| **Neutre** | Grass_02, Dirt_01 (prairie) | Rock_01, Debris_Rock_01 (pente rocheuse) |
| **Convexe** | Heather_01, Grass_01 (crête herbeuse) | Rock_01 (affleurement rocheux) |

### Textures favorisées par courbure

| Curvature | Textures boostées | Textures réduites |
|-----------|-------------------|-------------------|
| **Concave forte** | Debris_Rock_01, Pebbles_01, Dirt_03 | Rock_01, Heather_01, Dirt_02 |
| **Convexe forte** | Rock_01, Heather_01, Dirt_02 | Grass_03, Dirt_01 |

---

## 💧 MASQUE 3 : SEDIMENT (Accumulation 0-1)

**Rôle** : Déterminer **activité érosive**, **transport de matière**, **humidité relative**

⚠️ **Important** : Sediment = **flow accumulation** (où l'eau s'accumule), PAS directement l'humidité du sol

### Plages de valeurs et textures associées

| Sediment | Catégorie | Textures logiques | Raison physique |
|----------|-----------|-------------------|-----------------|
| **0.0-0.15** | Très faible | `Rock_01`, `Dirt_02`, `Heather_01` | Crête drainée → roche/terre sèche, lande |
| **0.15-0.35** | Faible | `Grass_01`, `MountainGrass_01/02`, `Dirt_01`, `Dirt_02` | Drainage normal → herbe standard, terre |
| **0.35-0.50** | Moyen | `Grass_02`, `Grass_03`, `Dirt_01`, `BeachGrass_01` | Humidité modérée → herbe mixte |
| **0.50-0.70** | Élevé | `Debris_Rock_01`, `Dirt_03`, `Pebbles_01`, `Grass_03` | Érosion active → débris transportés, herbe dense humide |
| **0.70-0.85** | Très élevé | `Debris_Rock_01`, `Pebbles_01`, `Pebbles_02`, `Dirt_03` | Flow fort → débris/galets, lits de rivière |
| **0.85-1.0** | Extrême | `Debris_Rock_01`, `Pebbles_02` | Talweg/ravine → débris grossiers dominants |

### Interprétation écologique

**Sediment BAS (< 0.3)** :
- Zone **drainée** (crête, sommet, pente convexe)
- Pas d'accumulation d'eau
- Sol sec, végétation résistante sécheresse
- Roche peut affleurer (altération lente)

**Sediment MOYEN (0.3-0.6)** :
- Zone **normale** (plaine, pente douce)
- Humidité équilibrée
- Végétation standard
- Sol meuble stable

**Sediment ÉLEVÉ (> 0.6)** :
- Zone **d'accumulation** (vallée, talweg, ravin)
- Flow actif → transport de matière
- Érosion + dépôt de débris
- Végétation dense (si pente douce) OU débris (si pente forte)

### ⚠️ Problèmes connus avec sediment

| Problème | Cause | Impact |
|----------|-------|--------|
| **Pebbles absents plages sèches** | Recette nécessite sediment > 0.48 | Plage sediment=0.2 → pas de galets |
| **Prairies trop humides** | Seuil "wet" à 0.48 trop bas | Prairie sediment=0.5 → Dirt_03 au lieu de Grass |
| **Côte mal différenciée** | Sediment pas adapté zone côtière | Même sediment → même texture côte/inland |

### Textures par niveau sediment

| Sediment | Végétation | Sol nu | Débris/Roche |
|----------|------------|--------|--------------|
| **< 0.2** | Heather_01, Grass_01 | Dirt_02 | Rock_01 |
| **0.2-0.4** | Grass_01, Grass_02 | Dirt_01, Dirt_02 | - |
| **0.4-0.6** | Grass_02, Grass_03 | Dirt_01 | - |
| **0.6-0.8** | Grass_03 | Dirt_03 | Debris_Rock_01, Pebbles_01 |
| **> 0.8** | - | Dirt_03 | Debris_Rock_01, Pebbles_02 |

---

## 📏 MASQUE 4 : ALTITUDE (Heightmap en mètres)

**Rôle** : Déterminer **zone climatique/écologique** et **étagement de végétation**

⚠️ **Important** : Seuils adaptatifs selon analyse hypsométrique (profil terrain)

### Zones altitudinales et textures associées

#### Zone SUBMERGÉE (< 0m)

| Altitude | Textures | Rôle |
|----------|----------|------|
| **< -12m** | `SeaBed_01` (exclusif) | Fond marin profond |
| **-12m à -2m** | `SeaBed_01` (dominant) | Fond marin peu profond |
| **-2m à 0m** | `SeaBed_01` (transition vers côte) | Zone intertidale |

#### Zone CÔTIÈRE (0-50m)

| Altitude | Textures principales | Textures secondaires |
|----------|---------------------|---------------------|
| **0-5m** | `BeachGrass_01`, `Pebbles_01`, `Dirt_03` | `Grass_03_coastal` |
| **5-15m** | `BeachGrass_01`, `Grass_03_coastal`, `Pebbles_01/02` | `Dirt_03`, `Rock_01` (si pente) |
| **15-50m** | `Grass_03_coastal`, `Grass_02`, `Dirt_01` | Transition vers lowland |

**Caractéristiques côtières** :
- Influence marine (sel, vent)
- BeachGrass adapté conditions côtières
- Pebbles fréquents (galets roulés par vagues)
- Dirt_03 = sable côtier
- Rock_01 = falaises côtières

#### Zone LOWLAND (50-250m) — Basses terres

| Altitude | Textures principales | Textures secondaires |
|----------|---------------------|---------------------|
| **50-150m** | `Grass_02`, `Grass_03`, `Dirt_01` | `ForestDeciduous_01` (si forêt) |
| **150-250m** | `Grass_01`, `Grass_02`, `Dirt_01`, `Dirt_02` | Transition vers midland |

**Caractéristiques** :
- Prairie tempérée standard
- Forêts feuillus possibles
- Terre meuble (Dirt_01)
- Climat doux

#### Zone MIDLAND (250-400m) — Collines

| Altitude | Textures principales | Textures secondaires |
|----------|---------------------|---------------------|
| **250-350m** | `Grass_01`, `MountainGrass_02`, `Dirt_02` | `Heather_01` (début) |
| **350-400m** | `MountainGrass_02`, `Heather_01`, `Dirt_02` | Transition vers highland |

**Caractéristiques** :
- Herbes de transition prairie → montagne
- Début végétation alpine (MountainGrass)
- Bruyère/lande apparaît
- Terre plus sèche (Dirt_02)

#### Zone HIGHLAND (> 400m) — Montagne

| Altitude | Textures principales | Textures secondaires |
|----------|---------------------|---------------------|
| **400-600m** | `MountainGrass_01/02/03`, `Heather_01`, `Rock_01` | `Debris_Rock_01` |
| **> 600m** | `Rock_01`, `MountainGrass_01`, `Debris_Rock_01` | Végétation rare |

**Caractéristiques** :
- Alpages (MountainGrass)
- Lande/bruyère dominante
- Roche affleure fréquemment
- Climat rude (vent, froid)
- Au-dessus limite végétation → Rock_01 dominant

### ⚠️ Seuils adaptatifs selon profil terrain

Les seuils ci-dessus sont **indicatifs**. Le pipeline adapte selon le profil hypsométrique :

| Profil terrain | Highland démarre | Coastal étendu | Exemple map |
|----------------|------------------|----------------|-------------|
| **flat** (plaine côtière) | p75 (tard) → ~320m | Oui (+30%) | Delta, plaine littorale |
| **balanced** (équilibré) | p58 (normal) → ~190m | Standard | ZBK Island, Zimnitrita |
| **plateau** (plateau élevé) | p50 (tôt) → ~160m | Réduit | Plateau d'Aubrac |
| **mountain** (montagne) | p45 (très tôt) → ~2800m | Réduit (-40%) | Everest, Alpes |

**Exemple Zimnitrita** (profil balanced) :
```
alt_min = -204m
alt_max = 499m
Seuils calculés :
  coastal : -2m → 50m
  lowland : 1m → 210m
  midland : 67m → 373m
  highland : 189m → 387m
```

### Textures par étage altitudinal (synthèse)

| Étage | Herbes | Sols | Débris/Roche | Spécial |
|-------|--------|------|--------------|---------|
| **Submergé** | - | - | - | SeaBed_01 |
| **Côtier** | BeachGrass_01, Grass_03_coastal | Dirt_03 (sable) | Pebbles_01/02, Rock_01 (falaise) | - |
| **Lowland** | Grass_02, Grass_03 | Dirt_01 | - | ForestDeciduous |
| **Midland** | Grass_01, MountainGrass_02 | Dirt_02 | - | Heather_01 |
| **Highland** | MountainGrass_01/02/03 | - | Rock_01, Debris_Rock_01 | Heather_01 |

---

## 🔄 COMBINAISONS MASQUES (Exemples types)

### Exemple 1 : Plage plate sèche

| Masque | Valeur | Contribution |
|--------|--------|--------------|
| **Altitude** | 3m | Côtier → BeachGrass_01, Pebbles_01, Dirt_03 |
| **Slope** | 2° | Plat → Grass_02, BeachGrass_01, Dirt_01 |
| **Curvature** | 0.0 | Neutre → pas d'influence |
| **Sediment** | 0.2 | Faible → Grass_01, Dirt_02 (drainage) |

**Résultat attendu** : BeachGrass_01 (dominant) + Dirt_03 (sable) + traces Pebbles_01

**⚠️ Problème actuel** : Pebbles_01 absent car recette nécessite sediment > 0.48

---

### Exemple 2 : Colline côtière 12°

| Masque | Valeur | Contribution |
|--------|--------|--------------|
| **Altitude** | 15m | Côtier → BeachGrass, Pebbles, Rock (si pente) |
| **Slope** | 12° | Pente douce → Debris_Rock_01, Dirt_03, herbes résistantes |
| **Curvature** | +0.2 | Convexe → Rock_01, Heather_01, Dirt_02 |
| **Sediment** | 0.3 | Faible/moyen → Grass_01, Dirt_01 |

**Résultat attendu** : Pebbles_01/02 (talus) + Rock_01 (affleurement convexe) + Debris_Rock_01

**✓ Fonctionne** : Pente active `coast_talus`, convexité favorise Rock

---

### Exemple 3 : Ravine montagne

| Masque | Valeur | Contribution |
|--------|--------|--------------|
| **Altitude** | 350m | Midland/highland → MountainGrass, Heather, Rock |
| **Slope** | 18° | Pente moyenne → Debris_Rock_01, Dirt_03 |
| **Curvature** | -0.3 | Concave forte → Debris_Rock_01, Pebbles_01/02, Dirt_03 |
| **Sediment** | 0.8 | Très élevé → Debris_Rock_01, Pebbles_02 (talweg) |

**Résultat attendu** : Debris_Rock_01 (dominant) + Pebbles_02 + Dirt_03 (liant)

**✓ Fonctionne** : Contexte `ravine` actif (concave × sediment élevé)

---

### Exemple 4 : Prairie basse humide

| Masque | Valeur | Contribution |
|--------|--------|--------------|
| **Altitude** | 120m | Lowland → Grass_02, Grass_03, Dirt_01 |
| **Slope** | 4° | Plat → Grass_02/03, Dirt_01 |
| **Curvature** | -0.1 | Concave légère → Grass_03 (dense), Dirt_01 |
| **Sediment** | 0.5 | Moyen → Grass_02, Grass_03 |

**Résultat attendu** : Grass_02 + Grass_03 (prairie humide) + traces Dirt_01

**✓ Fonctionne** : Contexte `prairie_low` actif, sediment moyen favorise Grass_03

---

## 🎯 USAGE DE CE DOCUMENT

### Pour diagnostiquer un problème

**Exemple** : "Pebbles_01 manquant sur plages"

1. **Vérifier chaque masque individuellement** :
   - Altitude 3m → Côtier ✓ (devrait contribuer Pebbles_01)
   - Slope 2° → Plat ✓ (compatible Pebbles_01)
   - Curvature 0.0 → Neutre (pas d'exclusion)
   - Sediment 0.2 → **PROBLÈME** (table indique sediment > 0.6 pour Pebbles via flow)

2. **Identifier la cause** :
   - Recette côtière nécessite sediment > 0.48 (seuil "wet")
   - Plage sèche (sediment 0.2) exclue de la recette

3. **Solution** :
   - Option A : Ajuster masque sediment (monter à 0.6 sur plages)
   - Option B : Ajouter recette alternative Pebbles_01 sans dépendance sediment élevé
   - Option C : Baisser seuil "wet" (⚠️ impact global)

---

### Pour vérifier cohérence map

**Checklist validation masques** :

```
☐ Sediment plages côtières = 0.4-0.7 (humidité modérée)
☐ Sediment ravines/talwegs > 0.7 (flow actif)
☐ Sediment crêtes < 0.3 (drainées)
☐ Slope falaises > 25° (roche)
☐ Slope plaines < 8° (herbe)
☐ Curvature vallées < -0.1 (concave)
☐ Curvature crêtes > 0.1 (convexe)
☐ Altitude côte < 50m (zone côtière)
```

Si masques respectent ces plages → pipeline devrait donner résultats cohérents.

---

### Pour calibrer nouvelle map

**Workflow recommandé** :

1. **Analyser les masques** :
   ```
   Slope : min, max, p90
   Sediment : distribution (% < 0.3, % 0.3-0.6, % > 0.6)
   Curvature : distribution (% concave, % convexe)
   Altitude : profil hypsométrique
   ```

2. **Comparer aux tables** :
   - Sediment plages = 0.2 → Table dit "faible" → Pebbles_01 absent attendu
   - Ajuster masque OU accepter résultat

3. **Tester zones clés** :
   - Plage plate
   - Colline côtière
   - Prairie basse
   - Crête montagne
   - Ravine

4. **Affiner via biomes** si global correct mais besoin ajustements régionaux

---

## 📌 NOTES IMPORTANTES

### Limitations des masques IT

**Ce que les masques ne disent PAS** :
- Type de végétation (forêt vs prairie)
- Type de sol géologique (granit vs calcaire)
- Climat local (méditerranéen vs tropical)
- Exposition soleil (nord vs sud)

➡️ Le pipeline fait des **suppositions** basées uniquement sur forme terrain + flow

### Différenciation côtier problématique

**Problème connu** : Les masques IT ne différencient pas suffisamment :
- Plage de galets vs plage de sable (même altitude + slope)
- BeachGrass vs Grass_03_coastal (même conditions)

**Raison** : Pas de masque "type de substrat" ou "végétation"

**Workaround** : Utiliser sediment comme proxy (arbitraire mais fonctionnel)

### Universalité vs Spécificité

Ce document décrit **textures théoriques** selon valeurs masques.

En pratique :
- Pipeline génère des **mélanges** (pas 100% d'une texture)
- Biomes affinent **régionalement**
- Utilisateur retouche **localement** dans Reforger

➡️ **Pas de "bonne réponse unique"**, juste des tendances logiques.

---

**Document généré automatiquement**  
Basé sur analyse `pipeline_core.py` et `material_library_vanilla.json`  
Dernière mise à jour : 2026-06-01
