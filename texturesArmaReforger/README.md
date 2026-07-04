# Catalogue de textures Reforger

⚠️ **ANCIEN EMPLACEMENT** — Déplacé vers `data/Textures_ArmaReforger/`

Structure de données pour l'export des masques Satmap depuis les fichiers du monde Reforger.

## Structure

```
data/Textures_ArmaReforger/
├── catalog.json          # Catalogue unifié (généré par le scanner)
├── vanilla/
│   ├── textures/         # PNG middle BCR des surfaces vanilla
│   └── emat/             # Copies des .emat vanilla
└── customs/
    ├── textures/         # PNG middle BCR des surfaces custom
    └── emat/             # .emat custom du mod
```

## Convention zi_

Les surfaces custom préfixées `zi_` suivent une convention d'héritage :

- **`zi_X.emat`** + `X.emat` existe dans vanilla → **héritage** du parent vanilla
  - Middle BCR et couleur moyenne hérités automatiquement
  - Exemple : `zi_Grass_01.emat` → hérite de `Grass_01.emat`

- **`zi_X.emat`** + `X.emat` absent → **création** custom
  - Doit avoir son propre PNG dans `customs/textures/`
  - Exemple : `zi_CropField_Custom.emat` → cherche `zi_CropField_Custom.png`

## Workflow

1. **Scan** : `app.py` → onglet "Satmap Export" → bouton "Scanner"
   - Parse `vanilla/emat/` et `customs/emat/`
   - Résout chaque .emat → PNG middle + couleur moyenne
   - Génère `catalog.json`

2. **Vérification** : croiser avec le `.terr` du monde
   - Détecte les surfaces manquantes dans le catalogue
   - Rapport dans `reports/catalog_terr_verify.txt`

3. **Export masques** (Phase 2 — à venir)
   - Lit les `.ttile` du monde
   - Exporte un PNG 8-bit par surface (0-255 = couverture %)

## catalog.json — Format

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

- **provenance** : `vanilla` | `custom`
- **parent** : nom du .emat vanilla hérité (convention zi_), ou `null`
- **middle_bcr** : chemin relatif vers le PNG middle, ou `null` si hérité
- **avg_color** : `[R, G, B]` couleur moyenne du PNG, ou `null` si hérité
- **tint** : tinte custom (édition manuelle), ou `null`
- **role** : rôle écologique déduit de `_MAT_STEM_TO_ROLE`
- **resolved** : `manual` | `auto` | `convention` | `fallback`
- **resolved_date** : date de dernière résolution

### Résolution

- **manual** : saisi manuellement, **jamais écrasé** par un re-scan
- **auto** : parsé automatiquement depuis les dossiers
- **convention** : déduit du nommage `zi_` (héritage ou création)
- **fallback** : PNG introuvable → couleur magenta `[255, 0, 255]`

Le re-scan met à jour `auto`, `convention` et `fallback`, mais **préserve** :
- Les entrées `resolved: "manual"`
- Les champs `tint` non nuls (édition manuelle)

## Rapports

Générés dans `<projet>/reports/` :

- **catalog_scan.txt** : résumé du scan (total, vanilla, custom, zi_ résolus, fallback)
- **catalog_terr_verify.txt** : croisement avec le .terr du monde (surfaces manquantes)
