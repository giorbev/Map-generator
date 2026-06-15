# Map Generator Pro

Outil de génération et d'analyse de cartes terrain pour **Arma Reforger / Enfusion Engine**.

## Fonctionnalités

### Gestion de projets
- Projets indépendants avec `project.json` (heightmap, grille Reforger, profils, masques IT)
- Support heightmap ASC (ESRI ASCII Grid), PNG 8/16-bit
- **Masques Instant Terra** : slopes, curvature, sediment — source de vérité prioritaire du pipeline texture
- Migration automatique des anciens formats de projet
- **Bibliothèque de matériaux** vanilla + custom par projet (JSON éditables)

### 🏔️ Onglet Terrain

**Hypsométrique** — Colormap par paliers d'altitude, hillshade intégré, export PNG

**Analyse** — Statistiques d'altitude, distribution, pentes, grille Reforger

### 🎨 Onglet Génération

**Pipeline Texture Écologique** — Génération automatique basée sur 4 variables scientifiques :

#### 📊 Variables d'entrée
1. **Altitude** (heightmap.asc) — Gradient thermique, zones altitudinales adaptatives
2. **Pente** (slopes.png) — Gravité, sédimentation (0-90°)
3. **Humidité** (sediment.png + curvature.png) — Flow map, drainage/accumulation
4. **Orientation** (futur) — Exposition soleil Adret/Ubac

#### 🌍 Contextes écologiques (12 strates)
Le pipeline combine les signaux pour créer des contextes réalistes :
- **Côtier** : coast_flat, coast_gentle, coast_talus, coast_cliff, coast_outcrop
- **Inland** : prairie_low, prairie_mid, mid_slope, rocky_outcrop
- **Highland** : alpage_dry, alpage_wet, rocky_highland, crest
- **Spéciaux** : ravine, cliff_fissure

#### ✨ Caractéristiques
- **Adaptatif universel** : Hypsométrique auto-calibré selon profil terrain (plaine/montagne/plateau)
- **Seuils dynamiques** : Pentes et zones calculées selon slope_p90 et percentiles altitude
- **Transitions douces** : Smoothstep partout, pas de frontières brutales
- **Philosophie transparente** : Tous les masques générés (≥0.01%) sont exportés, même les textures localisées rares
- **Squeezing intelligent** : top-5 par pixel + ≤3 uniques par bloc 32m (contrainte Reforger)
- **16 textures vanilla** : SeaBed, BeachGrass, Pebbles, Grass, MountainGrass, Heather, Dirt, Rock, Debris

#### 🔧 Corrections récentes (2026-06-01)
- ✅ Bug masques IT corrigés : slope converti en degrés (×90), curvature remappé -1/+1
- ✅ Boost textures côtières rares : signal `very_low_coastal` (plages 0-10m)
- ✅ Recettes Phase 1 côtier : Pebbles sediment modéré, coast_gentle (5-12°), coast_outcrop
- ✅ Seuil élimination : garde tous masques sauf vraiment vides (≥0.0001%)

#### 📦 Export
- PNG 16-bit par texture, prêt pour import Workbench
- Métadonnées : map_parameters.txt (altitude, slope_p90, profil terrain)

**Végétation** — Carte 2D de végétation potentielle :
- 13 types de zones (forêt bouleaux, pins, épicéas, maquis, roseaux, saule, pierres…)
- 3 types linéaires (haies, roseaux, lisière)
- Règles écologiques : altitude, pente, exposition, flow, humidité
- Option : exclusion des zones verrouillées (champs, urbain)
- Export PNG, légende complète

### 🗂️ Onglet Calques & Export

**Calque Texture** — Masques morphologiques générés, export par rôle

**Calque TMAT** — Lecture des `.ttile` / `.terr` Workbench, visualisation RGB blendée

**Calque SatMap** — Génération SatMap tuilée par matériau BCRMiddleMap, segmentation K-means

**Carte Reconstruction** — Vue aérienne depuis masques exportés + overlay de zones

**Fusion Masques** — Zones verrouillées (villes, champs) préservées + auto-material sur zones naturelles → ZIP prêt Workbench

## Démarrage rapide

```bash
pip install streamlit pillow numpy scipy matplotlib opencv-python pandas
streamlit run app.py
```

L'interface s'ouvre sur `http://localhost:8501`.

## Format de projet

```
data/projects/<nom>/
├── project.json                    — métadonnées et configuration
├── material_library_custom.json    — matériaux custom du projet
├── sources/
│   └── import instant/             — masques Instant Terra (slopes, curvature, sediment)
├── generated/                      — sorties générées par l'outil
└── masks/                          — masques de surface exportés (PNG 16-bit)
```

Bibliothèque vanilla partagée : `data/material_library_vanilla.json`

## Masques Instant Terra

| Fichier | Encodage source | Conversion pipeline | Rôle |
|---------|----------------|---------------------|------|
| `slopes.png` | 0-1 (0-90° normalisé) | × 90 → degrés | Détection pentes plates/raides, seuils adaptatifs |
| `curvature.png` | 0-1 (0=concave, 0.5=neutre, 1=convex) | (x-0.5)×2 → -1/+1 | Crêtes convexes (roche), vallées concaves (debris/ravine) |
| `sediment.png` | 0-1 (0=sec/drainé, 1=humide/accumulation) | Direct 0-1 | Flow map, humidité sol, drainage crêtes vs accumulation vallées |

**Résolution requise** : Identique à la heightmap (ex. 4097×4097 pour 16 km)

**Calibration automatique** : Le pipeline détecte automatiquement les plages de valeurs et s'adapte à chaque carte (slope_p90, altitude percentiles, profil hypsométrique).

---

## Philosophie du pipeline

### Approche universelle
Le pipeline est conçu pour fonctionner sur **toute carte** sans ajustement manuel :
- **Analyse d'abord** : Détection du profil terrain (plat/balanced/plateau/mountain)
- **Adaptation ensuite** : Zones altitudinales calculées par percentiles (coastal = 0-P20, lowland = P20-P50, etc.)
- **Génération honnête** : Toutes les textures écologiquement cohérentes sont générées

### Gestion des textures rares
**Principe** : On garde tout sauf les masques vraiment vides (0.00%)

**Pourquoi ?**
- Une texture à 0.01% (ex: BeachGrass sur petites plages) est **réelle**, pas une erreur
- Elle peut être éliminée par le squeezing Reforger (contrainte moteur : ≤3 textures/bloc 32m)
- L'utilisateur peut **voir visuellement** où elle s'applique (PNG exporté)
- Une future carte avec plus de plages bénéficiera des mêmes recettes sans modification

**Résultat** : Transparence totale, pas de sur-fitting sur une carte particulière

### Contraintes Reforger acceptées
- **Top-5 par pixel** : Les 5 textures dominantes sont gardées, les autres éliminées
- **≤3 uniques par bloc 32m** : Si un bloc contient >3 textures différentes, les moins présentes sont supprimées
- **Petites zones (<100m)** : Peuvent être texturées différemment si isolées, sinon écrasées par les textures environnantes

➡️ **Ces limites sont inhérentes au moteur Enfusion, pas au pipeline**

---

## Changelog

### 2026-06-01 — Pipeline Texture v5.2 (Corrections universalité)

#### 🐛 Bugs critiques corrigés
- **Slope** : Masque IT (0-1 normalisé) maintenant converti en degrés (×90). Correction slope_p90 : 0.294° → 25.774°
- **Curvature** : Masque IT (0-1) maintenant remappé en -1/+1 pour détection crêtes/vallées
- **Sediment** : Confirmé OK (0-1 direct, 0=sec, 1=humide)

#### ✨ Améliorations côtier (Phase 1)
- Nouveau signal `very_low_coastal` : boost BeachGrass et Pebbles sur plages 0-10m
- Nouveau contexte `coast_gentle` : pentes douces côtières 5-12° (Pebbles, Grass)
- Nouveau contexte `coast_outcrop` : affleurements rocheux convexes côtiers (Rock, Debris)
- Recettes Pebbles adaptées : fonctionnent maintenant sur sediment modéré (0.3-0.6) au lieu de seulement wet (>0.6)

#### 🔧 Ajustements système
- **Seuil élimination** : 0.25% → 0.0001% (garde tous masques sauf vraiment vides)
- **Philosophie** : Approche universelle adoptée — le pipeline génère ce qui est écologiquement cohérent, accepte les contraintes Reforger

#### 📊 Validation scientifique
- Pipeline conforme aux 4 variables terrain : Altitude ✅, Pente ✅, Humidité ✅, Orientation (futur)
- 12 contextes écologiques implémentés avec croisements adaptatifs
- Seuils dynamiques basés sur slope_p90 et percentiles altitude

#### 📝 Documentation
- README mis à jour avec architecture pipeline, philosophie universelle
- `data/doc/PIPELINE_LOGIQUE.md` (39 pages) : logique complète des 12 contextes
- `data/doc/TEXTURES_PAR_MASQUE.md` : décomposition par masque source
- `data/doc/CORRECTIONS_PIPELINE.md` : plan Phase 1 côtier détaillé
- `data/doc/CHANGELOG_PHASE1.md` : 13 lignes modifiées, tests de validation

### Phases futures
- **Phase 2** : Ajustement Dirt/Grass (réduire Dirt_02 sur pentes moyennes/crêtes)
- **Phase 3** : Ajustement érosion (Debris_Rock_01 distribution)
- **Orientation** : Masque aspect (Adret/Ubac) pour végétation

---

Développé par **[otea] Giorbev** with Claude AI
