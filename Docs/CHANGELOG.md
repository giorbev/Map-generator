# Changelog — Map Generator Pro

## v5.0 — Pipeline MODE 2 & Végétation Enrichie (2026-06-15)

### ✨ Nouveautés

#### **Pipeline MODE 2 : Terrain + Végétation**
- ✅ **15 masks enrichis biomes** : forest_floor_deciduous, forest_floor_coniferous, heather
- ✅ **Intégration carte végétation** :
  - PNG coloré → Extraction automatique 7 zones par couleur
  - Dossier masks PNG → Chargement direct
  - Dict pré-chargé → Optimisation performance
- ✅ **7 zones végétation** :
  - `foret_mixte` → forest_floor_deciduous
  - `foret_coniferes` → forest_floor_coniferous
  - `plateau_herbeux` → heather + mountain_grass
  - `prairie_seche` → grass_low/mid
  - `veg_rupestre` → grass_low
  - `non_attribue` → debris/rock selon pente
  - `eau` → mud_river

#### **Logique Terrain Révisée**
- ✅ **Debris/Dirt affiné** :
  - `debris_rock` : curvature < -0.15 (vrais creux rocheux)
  - `dirt_erosion` : curvature -0.15 à 0.1 + tpi_local < 0.0 + flow > 0.15 (ravines)
- ✅ **Crêtes convexes** → Mountain Grass / Heather (au lieu de debris)
- ✅ **Zones intouchables** : seabed, coastal_pebbles, rock_walls, mud_river

#### **Interface Utilisateur**
- ✅ **Radio MODE 1/MODE 2** :
  - MODE 1 : 13 masks terrain pur (rétrocompatible)
  - MODE 2 : 15 masks terrain + végétation
- ✅ **Source végétation** : Dossier masks PNG ou carte PNG colorée
- ✅ **Messages dynamiques** : Affichage mode et nombre de masks générés

### 🔧 Améliorations

- **pipeline_v2.py** : Paramètre `vegetation_map` pour run_pipeline()
- **Feathering adapté** : Support 15 masks MODE 2
- **Logger détaillé** : Pixels traités par zone végétation
- **Rétrocompatibilité** : MODE 1 100% inchangé

### 📚 Documentation

- Seuils curvature/slope documentés
- Guide utilisation MODE 2
- Mapping 7 zones → 15 masks

---

## v4.0 — Post-Traitement & Optimisation Cache (2026-06-15)

### ✨ Nouveautés

#### **Post-Traitement Phase 1**
- ✅ **Fusion intelligente** : Combine masks pipeline_v2 + masks mappeur Reforger
- ✅ **4 catégories** :
  - `sol_naturel` : Priorité pipeline_v2 (sauf zones urbaines)
  - `mappeur` : Priorité mappeur (routes, bâtiments)
  - `commune` : Max(pipeline_v2, mappeur)
  - `foret_custom` : Addition clampée
- ✅ **Zones urbaines automatiques** : Génération depuis masks mappeur + dilatation
- ✅ **Redimensionnement auto** : Masks 16257×16257 → 4097×4097
- ✅ **Export** : `generated/masks_fusion/` avec rapport QTRE

#### **Cache Terrain Data**
- ✅ **Sauvegarde automatique** : `cache/terrain_data.npz` (463 MB)
- ✅ **Chargement instantané** : 0.5s au lieu de 4.5 min
- ✅ **Validation date** : Recalcul auto si heightmap modifiée

#### **Corrections Système**
- ✅ **Chargement projet** : Heightmap correctement chargée depuis `sources/`
- ✅ **Structure dossiers** : `sources/` + `generated/` + `cache/`
- ✅ **Diagnostic sidebar** : État projet (heightmap, basemap, terrain_data, cache)

### 🔧 Améliorations

- **Interface** : Colonnes catégorisation rapprochées et alignées
- **Messages** : Feedback chargement cache vs calcul
- **Performance** : Terrain_data calculé UNE SEULE FOIS par projet
- **Dossiers** : `exports/` → `generated/` (structure organisée)

### ⚠️ Connu

- **Phase 2 désactivée** : Polygones manuels incompatibles avec Streamlit 1.57
  - Alternative : Créer masques manuels dans QGIS/IT → upload comme mappeur

---

## v3.0 — Architecture DDD (2026-05-23)

### Nouveautés
- Architecture 3 couches (Domain/Application/Infrastructure)
- Pipeline V2 : 13 masks terrain avec auto-calibration
- Validation QTRE intégrée
- Génération végétation potentielle

---

## v2.0 — Pipeline Textures (2026-04-15)

### Nouveautés
- Pipeline génération masques terrain
- Intégration Reforger grid
- Export PNG 16-bit

---

## v1.0 — Version initiale (2026-03-10)

### Fonctionnalités
- Chargement heightmap ASC
- Génération hypsométrique
- Aperçu terrain
