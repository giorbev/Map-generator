# Satmap Export — Phase 1 : Catalogue de textures

**Date** : 2026-07-03  
**Statut** : ✅ Implémenté et testé

## Vue d'ensemble

Nouvelle fonctionnalité dans l'onglet **"🛰️ Satmap Export"** permettant de construire un catalogue unifié des surfaces .emat Reforger (vanilla + custom) pour préparer l'export des masques depuis les fichiers du monde.

## Architecture

### Fichiers créés

```
h:\logiciel perso\Map generator\
├── reforger_satmap_export.py          # Module core (catalogue + scan)
├── test_satmap_catalog.py             # Tests unitaires
├── texturesArmaReforger/              # Données
│   ├── README.md                      # Documentation structure
│   ├── catalog.json                   # Catalogue généré (gitignored)
│   ├── vanilla/
│   │   ├── textures/                  # PNG middle BCR vanilla
│   │   └── emat/                      # .emat vanilla
│   └── customs/
│       ├── textures/                  # PNG middle BCR custom
│       └── emat/                      # .emat custom
└── Docs/
    └── SATMAP_EXPORT_PHASE1.md        # Ce fichier
```

### Modifications dans app.py

**Ligne 2055** : Ajout du 4e onglet principal `tab_satmap`

```python
tab_terrain, tab_satmap, tab_gen, tab_validation = st.tabs([
    "🏔 Terrain",
    "🛰️ Satmap Export",
    "🎨 Génération",
    "[INFO] Validation Masks",
])
```

**Lignes 2586-2828** : Code de l'onglet Satmap (4 sections)

## Fonctionnalités implémentées

### 1. Construction du catalogue

**Bouton** : "🔨 Scanner"

**Actions** :
- Parse `texturesArmaReforger/vanilla/emat/` → entrées vanilla
- Parse `texturesArmaReforger/customs/emat/` → entrées custom
- Résout chaque .emat :
  - Cherche PNG middle BCR correspondant
  - Calcule couleur moyenne RGB
  - Déduit le rôle écologique via `_MAT_STEM_TO_ROLE`
- Préserve les entrées `resolved: "manual"` et les champs `tint` non nuls
- Sauvegarde dans `texturesArmaReforger/catalog.json`

**Affichage** :
- Métriques : Total / Vanilla / Custom / Fallback
- Expander "🔗 Résolutions zi_" : liste des héritages détectés
- Expander "⚠️ Fallback magenta" : surfaces sans PNG trouvé
- Rapport texte dans `<projet>/reports/catalog_scan.txt`

### 2. Convention zi_

**Règle d'héritage** : `zi_X.emat`
- Si `X.emat` existe dans vanilla → **héritage**
  - `middle_bcr` et `avg_color` copiés du parent
  - `resolved: "convention"`
  - `parent: "X.emat"`
- Si `X.emat` absent → **création custom**
  - Cherche PNG dans `customs/textures/`
  - Calcule `avg_color` si PNG trouvé
  - `resolved: "convention"` ou `"fallback"`

**Matching** : insensible à la casse (stems normalisés en minuscules)

### 3. Croisement avec .terr

**Input** : chemin vers le fichier `.terr` du monde Reforger

**Bouton** : "✓ Vérifier"

**Actions** :
- Appelle `parse_terr_materials(terr_path)` (réutilise fonction existante)
- Croise avec le catalogue → détecte surfaces manquantes
- Affiche :
  - Couverture % (surfaces présentes / total)
  - Expander "⚠️ Surfaces manquantes" (avec noms)
  - Expander "📋 Toutes les surfaces" (avec pastilles couleur + rôle)
- Rapport dans `<projet>/reports/catalog_terr_verify.txt`

### 4. État du catalogue

**Affichage tableau** :
- Filtres : Provenance / Résolution / Rôle
- Colonnes : Surface / Prov. / Résolu / Rôle / Couleur
- Limite 100 entrées pour performance

**Pastille couleur** : rendu HTML inline avec couleur moyenne

## Format catalog.json

```json
{
  "Grass_01.emat": {
    "provenance": "vanilla",
    "parent": null,
    "middle_bcr": "vanilla/textures/Grass_01.png",
    "avg_color": [58, 62, 39],
    "tint": null,
    "role": "prairie",
    "resolved": "manual",
    "resolved_date": "2026-07-03"
  },
  "ZI_CropField_01.emat": {
    "provenance": "custom",
    "parent": "CropField_01.emat",
    "middle_bcr": null,
    "avg_color": null,
    "tint": null,
    "role": "champ",
    "resolved": "convention",
    "resolved_date": "2026-07-03"
  }
}
```

### Champs

| Champ           | Type          | Description                                              |
|-----------------|---------------|----------------------------------------------------------|
| `provenance`    | str           | `"vanilla"` \| `"custom"`                                |
| `parent`        | str \| null   | .emat parent vanilla (héritage zi_)                      |
| `middle_bcr`    | str \| null   | Chemin relatif vers PNG middle, ou null si hérité        |
| `avg_color`     | [int] \| null | `[R, G, B]` couleur moyenne, ou null si hérité           |
| `tint`          | ? \| null     | Tinte custom (édition manuelle future)                   |
| `role`          | str \| null   | Rôle écologique déduit de `_MAT_STEM_TO_ROLE`            |
| `resolved`      | str           | `"manual"` \| `"auto"` \| `"convention"` \| `"fallback"` |
| `resolved_date` | str           | Date ISO de dernière résolution (YYYY-MM-DD)             |

### Statuts de résolution

- **manual** : saisi manuellement → **jamais écrasé** par un re-scan
- **auto** : parsé automatiquement depuis les dossiers → mis à jour à chaque scan
- **convention** : déduit du nommage `zi_` → mis à jour à chaque scan
- **fallback** : PNG introuvable → couleur magenta `[255, 0, 255]` → mis à jour à chaque scan

## Réutilisation du code existant

### Depuis reforger_texture_budget.py

✅ **`parse_terr_materials(terr_path)`** ([ligne 45](../reforger_texture_budget.py#L45))
- Extrait la liste ordonnée des matériaux depuis le .terr binaire
- Utilisé dans `verify_catalog_against_terr()`

✅ **`_MAT_STEM_TO_ROLE`** ([ligne 428](../reforger_texture_budget.py#L428))
- Dictionnaire stem → rôle écologique
- Utilisé dans `scan_vanilla_textures()` et `scan_custom_textures()` pour déduire le rôle

✅ **`_MAT_STEM_ORDER`** ([ligne 472](../reforger_texture_budget.py#L472))
- Ordre de priorité (spécifique → générique)
- Garantit matching correct (ex: "Grass_03_coastal" avant "Grass")

## Tests

**Script** : `test_satmap_catalog.py`

**Résultat** : ✅ TOUS LES TESTS PASSÉS

1. ✅ Import du module
2. ✅ Structure de dossiers
3. ✅ Créer un catalogue vide
4. ✅ Scanner les dossiers (même vides)
5. ✅ Sauvegarde du catalogue
6. ✅ Rechargement du catalogue

## Contraintes respectées

✅ **Lecture seule** : aucun fichier Reforger modifié  
✅ **Réutilisation** : `parse_terr_materials()`, `_MAT_STEM_TO_ROLE`  
✅ **Robustesse** : fallback magenta si PNG introuvable + warning  
✅ **Rejeu** : `preserve_manual=True` → n'écrase jamais les entrées manuelles  

## Phase 2 (à venir)

**Fonctionnalité** : Export masques globaux PNG 8-bit par surface

**Source** : fichiers `.ttile` du monde Reforger

**Workflow** :
1. Utilisateur sélectionne le dossier `.bterr` du monde
2. Lecture de tous les `.ttile` → décodage QTRE (réutiliser décodeurs existants)
3. Reconstruction masque global par matériau (H×W, 0-255 = couverture %)
4. Export PNG dans dossier de sortie choisi

**Adaptations requises** :
- Créer variantes des décodeurs QTRE pour retourner **poids complets** au lieu de `argmax`
- Agréger les blocs → grille globale par matériau
- Normaliser 0.0-1.0 → 0-255 uint8

## Références

- [PIPELINE_V2_FLOW_FIX.md](PIPELINE_V2_FLOW_FIX.md) — Pipeline textures v2.0.0
- [reforger_texture_budget.py](../reforger_texture_budget.py) — Module core QTRE
- [texturesArmaReforger/README.md](../texturesArmaReforger/README.md) — Doc catalogue
