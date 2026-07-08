# Correspondance Types Végétation → Prefabs Reforger

**Date** : 2026-06-29  
**Version** : Map Generator Pro v5.1  
**Module** : `vegetation_map.py`

---

## Table des Matières

1. [Correspondance Complète](#correspondance-complète)
2. [Résumé par Zone Terrain](#résumé-par-zone-terrain)
3. [Notes d'Utilisation](#notes-dutilisation)

---

## Correspondance Complète

### FORÊTS (5 types)

| Type végétation | Fichier masque | Prefabs Reforger | Description |
|---|---|---|---|
| `foret_feuillue` | mask_foret_feuillue.png | Arbres feuillus + deciduous_01/02 | Forêt de feuillus (chênes, bouleaux) - basse altitude, versants nord humides |
| `foret_mixte` | mask_foret_mixte.png | Mix arbres feuillus/conifères + clearing | Forêt mixte - basse/moyenne altitude |
| `foret_mixte_plateau` | mask_foret_mixte_plateau.png | Mix arbres + deciduous_01 + mountain_grass1 | Forêt clairsemée de plateau - moyenne altitude, plateaux |
| `foret_pins` | mask_foret_pins.png | Pins + coniferous_01 + grass3 | Forêt de pins - moyenne altitude, versants sud secs |
| `foret_coniferes` | mask_foret_coniferes.png | Sapins/épicéas + coniferous_01/02 | Forêt de conifères - haute altitude, versants nord |

### PRAIRIES / LANDES (7 types)

| Type végétation | Fichier masque | Prefabs Reforger | Description |
|---|---|---|---|
| `prairie_humide` | mask_prairie_humide.png | Grass2 + fleurs humides | Prairie humide - basse altitude, zones plates humides |
| `prairie_seche` | mask_prairie_seche.png | Grass1 + Grass2 | Prairie sèche - basse/moyenne altitude, zones sèches |
| `prairie_plateau` ⭐ | mask_prairie_plateau.png | **Grass1 + Grass2** (herbe rase) | Prairie de plateau (jaune-vert) - plateaux plats moyens/hauts |
| `landes_plateau` ⭐ | mask_landes_plateau.png | **Heather** (bruyère) | Landes/bruyère de plateau (brun-olive) - plateaux secs |
| `alpages` | mask_alpages.png | Mountain_grass1 (herbe rase montagne) | Alpages - haute altitude, plateaux |
| `maquis_landes` | mask_maquis_landes.png | Heather (version générique) | Maquis/landes - moyenne altitude, versants sud secs |
| `haies_lisieres` | mask_haies_lisieres.png | Haies + buissons transition | Haies et lisières forêt/prairie - zones de transition |

### ZONES HUMIDES (2 types)

| Type végétation | Fichier masque | Prefabs Reforger | Description |
|---|---|---|---|
| `ripisylve` | mask_ripisylve.png | Saules + roseaux + végétation dense | Végétation de bord de rivière/ruisseau (vert eau) - suit les cours d'eau |
| `roseaux_marais` | mask_roseaux_marais.png | Roseaux (reeds) + marais | Roseaux zones marécageuses - très basse altitude, très humide |

### ZONES ROCHEUSES (2 types)

| Type végétation | Fichier masque | Prefabs Reforger | Description |
|---|---|---|---|
| `landes_rocheuses` | mask_landes_rocheuses.png | Mountain_grass3 clairsemé + buissons bas | Végétation clairsemée sur pentes - toutes pentes raides |
| `veg_rupestre` | mask_veg_rupestre.png | Très clairsemé, lichens, rochers | Végétation haute montagne/falaises - zones rocheuses extrêmes |

---

## Résumé par Zone Terrain

### Plateaux Ouest (zones plates moyennes/hautes)

| Zone | Types végétation dominants | Prefabs clés | Répartition |
|---|---|---|---|
| **Plateaux très plats** | prairie_plateau, landes_plateau, foret_mixte_plateau | Grass1/2, Heather, arbres clairsemés | 50% prairie, 30% landes, 20% forêt |

**Détails plateaux :**
- **Prairie plateau** (jaune-vert) : herbe rase dominante (Grass1/Grass2)
- **Landes plateau** (brun-olive) : bruyère (Heather) en patches 20-30%
- **Forêt mixte plateau** (vert moyen) : arbres clairsemés + mountain_grass1

### Pentes et Vallées

| Zone | Types végétation dominants | Prefabs clés |
|---|---|---|
| **Toutes pentes** | landes_rocheuses | Mountain_grass3 clairsemé + buissons bas |
| **Vallées humides** | ripisylve | Saules + roseaux |
| **Pentes hautes** | veg_rupestre | Très clairsemé, rochers |

### Basses Altitudes (0-40m)

| Zone | Types végétation dominants | Prefabs clés |
|---|---|---|
| **Zones humides plates** | prairie_humide | Grass2 + fleurs humides |
| **Forêts basses** | foret_feuillue | Arbres feuillus + deciduous_01/02 |
| **Zones marécageuses** | roseaux_marais | Roseaux (reeds) |

### Hautes Altitudes (>170m)

| Zone | Types végétation dominants | Prefabs clés |
|---|---|---|
| **Plateaux hauts** | alpages | Mountain_grass1 (herbe rase montagne) |
| **Forêts hautes** | foret_coniferes | Sapins/épicéas + coniferous_01/02 |
| **Zones rocheuses** | veg_rupestre | Très clairsemé, rochers |

### Cours d'Eau et Zones Humides

| Zone | Types végétation dominants | Prefabs clés |
|---|---|---|
| **Berges rivières** | ripisylve | Saules + roseaux |
| **Marais** | roseaux_marais | Roseaux (reeds) |

---

## Notes d'Utilisation

### Format des Masques

- **Format** : PNG 16-bit
- **Valeurs** : 0 (noir) ou 65535 (blanc) - masques binaires
- **Méthode** : Zones exclusives (winner-takes-all) - chaque pixel appartient à UN SEUL type
- **Seuil** : score > 0.1 pour inclusion

### Pas de Superposition

Les masques sont **exclusifs** : un pixel ne peut être blanc que dans UN SEUL masque. Cela correspond exactement aux zones de couleur de la carte végétation RGB.

### Cohérence avec Masques Terrain

Les masques végétation sont **complémentaires** aux 7 masques terrain (QTRE) :
- **Masques terrain** = texture sol + ground cover dense (tapis)
- **Masques végétation** = prefabs ponctuels (arbres, buissons, variété)
- Même système de seuils altitudinaux auto-calibrés

### Glossaire

- **Rupestre** : végétation qui pousse sur les rochers, falaises
- **Ripisylve** : végétation des bords de rivières (du latin *ripa* = rive)
- **Heather** : bruyère (buissons bas denses brun-violet/mauve)
- **Clearing** : clairière (sous-bois forêt mixte)
- **Deciduous** : feuillus (arbres à feuilles caduques)
- **Coniferous** : conifères (arbres à aiguilles)

---

## Workflow Reforger Workbench

1. **Export** : Cliquer "🎯 Exporter Masques 16-bit" dans l'onglet Végétation
2. **Import Workbench** : Importer les 16 masques PNG dans votre projet Reforger
3. **Placement** : Utiliser chaque masque pour placer les prefabs correspondants
4. **Densité** : Ajuster la densité de spawn selon la zone (plateaux = dense, pentes = clairsemé)

---

**Généré par Map Generator Pro v5.1**  
**Module** : `vegetation_map.py` — 16 types de végétation basés sur signaux terrain  
**Documentation complète** : voir `project_vegetation_plan.md` dans mémoire projet
