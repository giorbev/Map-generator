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
│   ├── catalog.json             catalog actif (73 entrées) — suivi par Git
│   ├── catalog_generated.json   sortie du bouton « Scan .emat » — ignoré par Git
│   ├── biomes_presets.json      presets de l'onglet Generation (7 biomes) — suivi par Git
│   ├── emat/                    .emat vanilla + custom (ZI_*, zi_*) — suivis par Git
│   ├── texture_Middle/          middles extraits des .edds (*_Middle_BCR.png) — suivis par Git
│   └── .initialized             marqueur de premier lancement — ignoré par Git
└── vanilla_base/                base vanilla pour le premier lancement de l'exe (à reconstruire, voir plus bas)
    ├── catalog_vanilla.json
    ├── emat/
    └── texture_Middle/
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

- **Middles absents du dossier** pour 3 entrées : `Rock_03.emat` (`Granite_05_BCR.png`),
  `zi_MountainGrass_02.emat` (`MountainGrass_Middle_02_BCR.jpg`), `zi_Heather_01.emat`
  (`Heather_01_Middle_BCR.jpg`). Aucun de ces matériaux n'est utilisé par les .terr de Zimnitrita ni de ZBK.
- **Entrées sans .emat** : `default.emat`, `zi_Heather_01.emat`, `zi_MountainGrass_02.emat`
  (entrées `custom` ajoutées à la main).
- **Middles non référencés** par le catalog : `ForestClearing_Middle_01_BCR.png`,
  `Grass_01_Middle_NHO.png`, `default_black_BCR.jpg`.
- Les textures ZI_* / zi_* (10 .emat) sont propres à Zimnitrita et volontairement absentes de la release.
- `RAPPORT_CATALOG_GENERATION.md` n'est pas dans le `.gitignore` : il apparaît comme non suivi après un scan.

## vanilla_base (à reconstruire — étape 9)

Au premier lancement de l'exe, `_init_first_launch()` (`main.py`) copie une base vanilla vers le dossier
`Textures/` de l'utilisateur, puis écrit `.initialized`. **En l'état, cette copie ne fonctionne pas** :

- le code cherche `vanilla_base_sauv/` (`main.py`, `MapGeneratorPro.spec`), le dossier s'appelle `vanilla_base/` ;
- le code copie `catalog.json`, le dossier contient `catalog_vanilla.json` (53 entrées) ;
- les middles de `vanilla_base/texture_Middle/` sont d'anciens JPG basse résolution (juillet), pas les
  vrais middles PNG de `Textures/texture_Middle/` (septembre).

À faire avant la recompilation : reconstruire `vanilla_base/` depuis `Textures/` (vanilla uniquement,
sans ZI_*/zi_*) et aligner le nom du dossier et du catalog avec le code.
