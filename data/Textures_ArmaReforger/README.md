# Textures_ArmaReforger

Données de textures utilisées par Map Generator Pro pour la **satmap** (couleurs et middles) et pour les
**presets de biomes** de l'onglet Generation.

Règle : le `.emat` est la seule source du catalog ; la table des matériaux d'un projet vient de son `.terr`
(jamais de ce dossier).

## Structure

```
Textures_ArmaReforger/
├── README.md
├── Textures/                    ← dossier de travail, lu par l'app
│   ├── catalog.json             catalog actif (72 entrées) — suivi par Git
│   ├── catalog_generated.json   sortie du bouton « Scan .emat » — ignoré par Git
│   ├── biomes_presets.json      presets de l'onglet Generation (7 biomes) — suivi par Git
│   ├── emat/                    .emat vanilla + custom (ZI_*, zi_*) — suivis par Git
│   ├── texture_Middle/          middles extraits des .edds (*_Middle_BCR.png) — suivis par Git
│   └── .initialized             marqueur de premier lancement — ignoré par Git
└── vanilla_base/                base vanilla copiée au premier lancement de l'exe (voir plus bas)
    ├── catalog.json             60 entrées (Textures/catalog.json sans zi_)
    ├── biomes_presets.json
    ├── emat/                    60 .emat
    └── texture_Middle/          26 middles
```

## Emplacement lu par l'app

Défini dans `catalog_config.py` (`TEXTURES_USER_DIR`) :

| Mode | Dossier `Textures/` utilisé |
|---|---|
| Développement (`python main.py`) | `<dépôt>/data/Textures_ArmaReforger/Textures/` |
| Exe | `Documents/MapGeneratorPro/data/Textures_ArmaReforger/Textures/` |

## Rôle de chaque élément

| Élément | Écrit par | Lu par |
|---|---|---|
| `catalog.json` | bascule manuelle depuis `catalog_generated.json` | satmap (`satmap_v2_textured_v2.py`), page Terrain |
| `catalog_generated.json` | bouton « Scan .emat » (`generate_catalog.py`) | comparaison avec `catalog.json` (page Satmap, alerte page Terrain) |
| `RAPPORT_CATALOG_GENERATION.md` | bouton « Scan .emat », à côté du catalog | lecture humaine |
| `emat/` | copie manuelle depuis l'addon | `generate_catalog.py` (héritage parent, couleurs) et satmap (teinte MiddleColor) |
| `texture_Middle/` | extraction manuelle des middles (.edds → PNG) | satmap, via la clé `middle_bcr` du catalog |
| `biomes_presets.json` | édition manuelle | onglet Generation (`apply_biome_preset`) |

Clés d'une entrée du catalog : `provenance` (vanilla/custom), `parent`, `middle_bcr`, `tiling_scale`,
`avg_color`, `tint`, `tint_srgb`, `tint_source`, `color_raw`, `middle_color_raw`, `source`, `role`,
`resolved`, `resolved_date`.

## Ajouter une texture

1. Copier le `.emat` dans `Textures/emat/` (avec son parent s'il n'y est pas déjà).
2. Copier son middle dans `Textures/texture_Middle/`, nommé comme la texture `BCRMiddleMap` du `.emat`
   (extension `.png` ou `.jpg` : le scan retient l'extension trouvée).
3. Bouton « Scan .emat » → `catalog_generated.json` + rapport ; vérifier les différences annoncées et la
   liste des middles manquants du rapport.
4. Bascule manuelle : remplacer `catalog.json` par `catalog_generated.json`.
5. Régénérer la satmap et vérifier qu'aucune ligne `[MISS]` n'apparaît dans le log
   (un middle manquant est remplacé par un aplat de couleur).

## Points connus (vérifiés le 30/10/2026)

- **Middles absents du dossier** pour 2 entrées : `zi_MountainGrass_02.emat` (`MountainGrass_Middle_02_BCR.jpg`),
  `zi_Heather_01.emat` (`Heather_01_Middle_BCR.jpg`). Aucun de ces matériaux n'est utilisé par les .terr de
  Zimnitrita ni de ZBK.
- `Rock_03` retiré le 30/10/2026 (texture qui n'existe plus) : .emat et entrée du catalog archivés dans
  `_archives/code/2026-10-30_rock_03/`.
- **Entrées sans .emat** : `zi_Heather_01.emat`, `zi_MountainGrass_02.emat` (entrées `custom` ajoutées à la main).
- `default.emat` (texture par défaut de Workbench, `system/terrain/terrain_BCR.edds`, utilisée par ZBK) n'a pas
  de `BCRMiddleMap` : un « Scan .emat » produit l'entrée `default` **sans middle**, alors que `catalog.json`
  utilise `terrain_BCR.jpg` (entrée manuelle de juillet). Le rapport la signale comme modifiée : garder
  l'entrée actuelle lors de la bascule. Remis dans `emat/` le 30/10/2026 (il manquait).
- **Middles non référencés** par le catalog : `ForestClearing_Middle_01_BCR.png`,
  `Grass_01_Middle_NHO.png`, `default_black_BCR.jpg`.
- Les textures ZI_* / zi_* (10 .emat) sont propres à Zimnitrita et volontairement absentes de la release.
- `RAPPORT_CATALOG_GENERATION.md` est ignoré par Git (depuis l'étape 9a).

## vanilla_base

Au premier lancement de l'exe, `_init_first_launch()` (`main.py`) copie une base vanilla vers le dossier
`Textures/` de l'utilisateur, puis écrit `.initialized`.

`vanilla_base/` est **généré** depuis `Textures/` par `tools/build_vanilla_base.py` (textures `zi_*` exclues,
casse ignorée) : ne pas le modifier à la main, relancer le script avant chaque release.

```
.venv\Scripts\python.exe tools/build_vanilla_base.py            simulation
.venv\Scripts\python.exe tools/build_vanilla_base.py --ecrire   écriture (ancien dossier archivé)
```

Reconstruit le 30/10/2026 (l'ancien contenu — `catalog_vanilla.json` de 53 entrées et middles JPG de
juillet — est dans `_archives/code/2026-10-30_vanilla_base/`).

**Reste à faire (étape 9c)** : le code cherche encore `vanilla_base_sauv/` (`main.py`, `MapGeneratorPro.spec`)
et ne copie pas `biomes_presets.json`.
