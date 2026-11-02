# Textures_ArmaReforger

Textures **vanilla** de Map Generator Pro : le **modèle** copié dans chaque projet pour la **satmap**
(couleurs et middles), et les **presets de biomes** de l'onglet Generation.

Depuis l'étape 12 (02/11/2026), chaque projet a ses propres textures dans `<projet>/textures/`
(`emat/`, `texture_Middle/`, `catalog.json`). Ce dossier n'est plus lu par la satmap : il n'est que
copié à la création d'un projet (ou à la première ouverture d'un projet qui n'a pas encore de `textures/`).
Les textures custom (ex. `ZI_*` de Zimnitrita) ne vont **jamais** ici : elles viennent de l'addon du projet
(onglet Satmap > Textures, bouton Synchroniser).

Règle : le `.emat` est la seule source du catalog ; la table des matériaux d'un projet vient de son `.terr`.

## Structure

```
Textures_ArmaReforger/
├── README.md
├── Textures/                    ← dossier modèle (vanilla seul), identique à vanilla_base/
│   ├── catalog.json             60 entrées — suivi par Git
│   ├── biomes_presets.json      presets de l'onglet Generation (7 biomes), global — suivi par Git
│   ├── emat/                    59 .emat vanilla — suivis par Git
│   ├── texture_Middle/          26 middles extraits des .edds (*_Middle_BCR.png) — suivis par Git
│   └── .initialized             marqueur de premier lancement — ignoré par Git
└── vanilla_base/                base vanilla livrée avec l'exe (voir plus bas)
```

## Emplacements

Définis dans `catalog_config.py` :

| Élément | Développement | Exe |
|---|---|---|
| Dossier modèle (`TEXTURES_USER_DIR`) | `<dépôt>/data/Textures_ArmaReforger/Textures/` | `Documents/MapGeneratorPro/data/Textures_ArmaReforger/Textures/` |
| Textures d'un projet (`get_project_textures_dir`) | `<dépôt>/data/projects/<projet>/textures/` | `Documents/MapGeneratorPro/data/projects/<projet>/textures/` |

`vanilla_base/` sert aussi de **référence vanilla** à la synchronisation : un `.emat` de l'addon qui porte
le nom d'un `.emat` vanilla est une surcharge (Workbench n'y enregistre que les propriétés modifiées) et
est fusionné avec la version de `vanilla_base/`.

## Rôle de chaque élément

| Élément | Écrit par | Lu par |
|---|---|---|
| `catalog.json`, `emat/`, `texture_Middle/` | `tools/build_vanilla_base.py` (modèle aligné sur `vanilla_base/`) | copie vers `<projet>/textures/` (`ensure_project_textures`) |
| `biomes_presets.json` | édition manuelle | onglet Generation (`apply_biome_preset`) |

Dans un projet, `catalog.json` est écrit par la synchronisation (`textures_sync.py`). Clés d'une entrée :
`provenance` (vanilla / custom / override / system), `parent`, `middle_bcr`, `middle_source`
(vanilla / projet / addon_image / addon_edds / manual), `manual`, `tiling_scale`, `avg_color`, `tint`,
`tint_srgb`, `color_raw`, `middle_color_raw`, `source`, `role`, `resolved`, `resolved_date`.

## Ajouter une texture

- **Texture custom d'un projet** : la peindre dans Workbench, puis onglet Satmap > Textures > Synchroniser.
  Le `.emat` et son middle (image source à côté du `.edds` dans l'addon, sinon `.edds` décodé) sont copiés
  dans le projet. Si le middle est introuvable (texture du jeu de base hors de l'addon), « Choisir… ».
- **Texture vanilla manquante dans le modèle** (nouvelle version de Reforger) : copier le `.emat` dans
  `Textures/emat/` et son middle dans `Textures/texture_Middle/`, ajouter l'entrée au `catalog.json`, puis
  régénérer `vanilla_base/` avec `tools/build_vanilla_base.py --ecrire`. Les projets existants gardent leur
  copie : la nouvelle texture n'arrive que dans les nouveaux projets.

## Points connus

- Le 02/11/2026 (étape 12e), les textures `ZI_*` / `zi_*` (10 .emat, 2 middles, 12 entrées du catalog),
  3 middles non référencés (`ForestClearing_Middle_01_BCR.png`, `Grass_01_Middle_NHO.png`,
  `default_black_BCR.jpg`), `catalog_generated.json` et `RAPPORT_CATALOG_GENERATION.md` ont été retirés du
  modèle et archivés dans `_archives/code/2026-11-02_etape12e/`. Zimnitrita et Zbk_island ont leur propre copie.
- `Rock_03` retiré le 30/10/2026 (texture qui n'existe plus) : archivé dans `_archives/code/2026-10-30_rock_03/`.
- **Entrée sans .emat** : `default.emat` (texture par défaut de Workbench, utilisée par ZBK, middle
  `terrain_BCR.jpg`). Ne pas ajouter `default.emat` dans `emat/` : il n'a pas de `BCRMiddleMap`.

## vanilla_base

Au premier lancement de l'exe, `_init_first_launch()` (`main.py`) copie `vanilla_base/` vers le dossier
modèle de l'utilisateur, puis écrit `.initialized`.

`vanilla_base/` est **généré** depuis `Textures/` par `tools/build_vanilla_base.py` (textures `zi_*` exclues,
casse ignorée) : ne pas le modifier à la main.

```
.venv\Scripts\python.exe tools/build_vanilla_base.py            simulation
.venv\Scripts\python.exe tools/build_vanilla_base.py --ecrire   écriture (ancien dossier archivé)
```
