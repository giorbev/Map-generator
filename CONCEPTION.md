# Map Generator Pro — Conception

> Document de référence du projet. Il décrit **ce qu'est l'application, comment elle est construite, d'où viennent ses données et quelles règles on suit**.
> Le **journal** (Carnet de Bord IA) garde le fil des sessions ; ce document garde l'état stable. Mise à jour : une fois par étape validée.
> Version : 15/10/2026 (v4, fin de l'étape 4a du nettoyage). Sources : journal, audits du 12-13/10, anciens documents `FORMATS_BINAIRES.md` (01/08), `FORMAT_LAYER_EDDS.md` (août), `ARCHITECTURE_GLOBALE.md` (14/08, époque Streamlit).
> Convention : **[À vérifier]** = information issue d'un ancien document, non revalidée ou contredite ailleurs.

---

## 1. Ce qu'est l'application

Outil desktop de génération et de diagnostic de terrain pour **Arma Reforger** (moteur Enfusion).

- **Utilisateurs** : moddeurs terrain.
- **Distribution** : application installable, publiée via les **releases GitHub**. Le plugin Workbench (Ctrl+Shift+M) a été **abandonné** : Bohemia n'autorise pas l'exécution d'un exe depuis un mod.
- **Ce qu'elle fait** :
  - lire et diagnostiquer un terrain Enfusion existant (tuiles, blocs, matériaux, budget de textures) ;
  - générer des masques de textures à partir d'une heightmap (pipeline v5) ;
  - générer une satmap texturée fidèle au rendu en jeu ;
  - outils annexes : carte hypsométrique, analyse de heightmap.
- **Ce qu'elle ne fait pas (ou plus)** : écrire dans les fichiers terrain (`.ttile`, `.dds`, `.edds`). Voir §4.6.
- **Projets de référence** (servent aussi aux tests de non-régression) :

| Projet | Grille | Pixels par tuile (surface) | Résolution | Préfixe des tuiles | Budget |
|---|---|---|---|---|---|
| Zimnitrita | 32×32 tuiles, 4×4 blocs par tuile | 512 | 1 m/px | `Terrain_` | 7 |
| ZBK_island | 64×64 tuiles, 4×4 blocs par tuile | voir `project.json` | 0,25 m/px | `ZBK_terrain_` | 7 |

Les valeurs exactes de chaque projet sont dans son `project.json` (texte « General Info » de Workbench collé dans la page Terrain).

---

## 2. Architecture

```
web/ (HTML/CSS/JS)  ──window.pywebview.api.xxx()──►  main.py (classe Api)
                                                        │
          ┌─────────────────────┬───────────────────────┼──────────────────────┬────────────────────┐
          ▼                     ▼                       ▼                      ▼                    ▼
   project_reader.py     satmap_v2_textured_v2.py   pipeline_v5.py      clean_weights.py     terrain_analysis.py
   (lecture projet)      (satmap)                   (masques)           (scan, inspect)      hypsometric_colormap.py
                               │                                              │
                 lecteurs de formats Enfusion :                       tile_inspector.py
                 lrs2_parser, layer_dds_reader, edds_decoder,         (scan global Inspection)
                 terrain_terr_reader, reforger_emat_parser
```

- **Interface** : PyWebView (fenêtre native), HTML/CSS/JS pur dans `web/`, i18n FR/EN (`i18n.js`, langue par défaut EN, choix mémorisé dans le navigateur).
- **Backend** : Python 3.13 (`.venv`), numpy, OpenCV, Pillow, lz4.
- **Exe** : PyInstaller (`MapGeneratorPro.spec`), publié en release GitHub.
- **Code** : `H:\logiciel perso\Map generator`. Dépôt GitHub `Map-generator`.

### Fichiers de l'application (après nettoyage de l'étape 2)

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée, classe `Api` exposée à l'interface |
| `project_reader.py` | **Seule** lecture des données d'un projet (voir §3) |
| `catalog_config.py` | Chemins du catalog global |
| `generate_catalog.py` | Génération du catalog depuis les .emat (bouton « Scan .emat ») |
| `satmap_v2_textured_v2.py`, `satmap_verifiers.py`, `reforger_emat_parser.py` | Satmap |
| `lrs2_parser.py`, `layer_dds_reader.py`, `edds_decoder.py`, `terrain_terr_reader.py` | Lecture des formats Enfusion |
| `tile_inspector.py`, `clean_weights.py` | Scan global, inspect tuile, scans de Corrections |
| `pipeline_v5.py` | Pipeline de masques |
| `terrain_analysis.py`, `terrain_algorithms.py`, `hypsometric_colormap.py` | Page Terrain |
| `app_config.py` | Ancien résolveur — **sortira à l'étape 6** |
| `satmap_classifier.py` | K-means — **sortira à l'étape 7** |

### Outils hors application

| Fichier | Rôle |
|---|---|
| `tools/check_regression.py` + `tools/check_regression_masks_worker.py` + `tools/check_regression_corrections_worker.py` | Non-régression (voir §8) |
| `tools/check_hardcoded.py` + `tools/hardcoded_exceptions.json` | Garde-fou des valeurs en dur (voir §8) |

### Organisation du dépôt (14/10)

```
Map generator/
├── main.py, *.py            application (à plat ; iront dans app/ à l'étape 10)
├── app/                     vide pour l'instant
├── web/                     interface
├── data/                    projets et textures (les données, pas le code)
├── tools/                   outils hors app : non-régression, garde-fou
├── docs/technical/          doc technique versionnée : formats Enfusion uniquement
├── CONCEPTION.md            la référence (ce fichier)
├── LICENSE                  MIT, [otea] Giorbev
├── requirements.txt, MapGeneratorPro.spec, .gitignore
│
│   — locaux, ignorés par Git —
├── _archives/               tout ce qui est retiré ou historique
│   ├── code/                code retiré, un sous-dossier daté par étape + NOTE.md
│   ├── backups/  genese/  sauvegarde/  .streamlit/
│   ├── docs/                anciens documents (époque Streamlit, pipelines précédents)
│   └── data/                copie d'anciennes données
├── _analyses/               rapports d'audit (rejoindra _archives/ après le nettoyage)
├── .venv/, build/, dist/, __pycache__/
├── logs/                    logs globaux (quand aucun projet n'est ouvert), ignoré
└── inputs/, Output/          restes égarés à supprimer (étape 6)
```

Règle : **rien ne sort du dossier du projet**. Ce qui ne sert plus va dans `_archives/`, jamais à la racine.

---

## 3. Données : où vit chaque information

### Classement des valeurs (décision du 13/10)

| Sorte | Exemples | Où elle vit | Ce qui est interdit |
|---|---|---|---|
| **1. Donnée d'un projet** | chemins, grille, préfixe, budget, .terr, m/px, heightmap, **ID de matériaux** | `project.json` du projet (ou .terr / fichiers Workbench), lue **uniquement** via `project_reader.py` | toute valeur de projet écrite dans le code, même comme valeur par défaut |
| **2. Constante de l'app** | en-tête DDS, noms de chunks, config par défaut des masques (par **nom** de texture), palettes, version du pipeline | dans le code, nommée et regroupée (tête de fichier ou module de constantes) ; un projet peut remplacer certains défauts dans ses propres fichiers | constante anonyme noyée dans le code |
| **3. Réglage de la machine** | chemin d'un outil externe, dernier projet ouvert | `settings.json` (local, non lié à un projet) | chemin de disque en dur dans le code |

### ID de matériaux (précisions du 13/10)

- Dans Workbench, chaque projet numérote ses matériaux (vanilla compris) dans **l'ordre où le mappeur les insère**. L'ID est la **position du matériau dans la liste du .terr** (en partant de 0). Sur un projet neuf, le premier de la liste, donc l'**ID 0**, est la texture par défaut (confirmé ; Zimnitrita : ID 0 = `Grass_03_default`). Après une réorganisation, l'ID 0 est simplement le matériau placé en tête de liste.
- Le mappeur peut **réordonner** les matériaux à tout moment : les ID sont alors renumérotés, et le résultat est enregistré dans le **.terr**.
- Dans le mod, **le .terr est le seul fichier** qui associe ID et matériaux.

Conséquences pour l'app :
- **aucun ID de matériau** ne doit être stocké ailleurs que dans le .terr : ni dans le code, ni dans les configurations (`project_mask_config.json`, presets de biomes…). On y stocke le **nom** de la texture ;
- l'ID est retrouvé à partir du nom en lisant le .terr **au moment où on en a besoin** (le mappeur a pu réordonner depuis l'ouverture du projet) ;
- `surfaces.json` n'est qu'un instantané, jamais une source ;
- ne pas confondre l'**ID 0** (texture par défaut du .terr) et le **slot 0** d'un bloc dans LRS2 (dernier matériau appliqué sur ce bloc, §4.2).

### Sources de vérité

| Information | Source unique | Lue par |
|---|---|---|
| Dossier du projet Reforger | `paths.addon_reforger` dans `project.json` | `project_reader` |
| Grille | clés à la racine de `project.json` : `grid_w`, `num_blk`, `tile_size_m`, `surface_tile_px` | `project_reader.get_grid()` |
| m/px | **calculé** : `tile_size_m / surface_tile_px` | `project_reader` |
| Texte Workbench « General Info » | enregistré en entier dans `project.json` (`workbench_info_raw`, `workbench_info_updated`) | page Terrain |
| Budget de textures par bloc | `pipeline.reforger_block_limit` (5 ou 7), choisi dans la page Terrain | `project_reader.get_block_budget()` |
| **Budget du pipeline** | **budget du projet − 1** (un slot laissé libre au mappeur) : 5 → 4, 7 → 6 | à brancher (étape 5) |
| Préfixe des tuiles | détecté dans `.Data/` (vérification d'unicité) | `project_reader.get_tile_prefix()` |
| Table ID → matériau | le **.terr** | `terrain_terr_reader` ; `surfaces.json` n'est qu'un instantané |
| Catalog des textures (satmap) | `data/Textures_ArmaReforger/Textures/catalog.json`, généré depuis les **.emat** | `catalog_config` |

Anciennes clés de `project.json` qui ne sont plus lues : `project_path`, `reforger_grid`, `reforger.grid_data`, `terrain_info`, `cell_size`, `terr_project_path`, `world_terrain_path`.
**Aucune valeur par défaut** pour un projet neuf (grille, budget) : champs vides et message d'aide.

### Arborescence des données

```
data/
├── projects/<projet>/
│   ├── project.json              (versionné)
│   ├── project_mask_config.json  (versionné)
│   ├── surfaces.json             (instantané de la table matériaux)
│   ├── inputs/                   (heightmap, masques Gaea, exclusion…)
│   ├── outputs/                  (générés : satmap, aperçus, caches, logs — ignorés par Git)
│   └── test/                     (références de non-régression — ignoré par Git)
└── Textures_ArmaReforger/
    ├── Textures/   catalog.json, catalog_generated.json, emat/, texture_Middle/, biomes_presets.json
    ├── vanilla_base/   (base copiée au premier lancement — à reconstruire avant l'exe)
    └── README.md       (à réécrire)
```

---

## 4. Formats Enfusion

Formats décodés entre juin et août 2026 sur des fichiers réels, puis complétés le 12/10 (ZBK).

### 4.1 Conteneur IFF

```
FORM  u32 BE taille  TYPE
  CHUNK  u32 BE taille  [données]
  …
```

- En-têtes IFF (FORM, identifiants, tailles) en **big-endian** ; données internes (u32, u16, f32) en **little-endian**.
- **Pas de padding** entre les chunks (contrairement à l'IFF standard). Un chunk peut avoir une taille impaire : un lecteur qui ajoute un octet de padding décale tout (bug corrigé le 12/10 dans `lrs2_parser.parse_iff_chunks()`).

### 4.2 `.Data/<préfixe><id>.ttile` — une tuile

```
FORM TERR
  VERS   4 o        version (u32 LE) = 9
  HGHT   33 282 o   heightmap runtime — jamais modifié par Workbench lors d'une modif de texture
  BERR   576 o      erreur de bordure — jamais modifié
  GCTD   variable   index de matériau par cellule (voir plus bas)
  LRS2   variable   liste des matériaux par bloc
  TMAT   variable   sous-chunks BMAT, métadonnées matériaux (régénéré par Workbench)
```

Lors d'une modification de texture dans Workbench, seuls **GCTD, LRS2 et TMAT** changent. Tailles relevées : GCTD ~30 452 o et TMAT ~20 404 o sur Zimnitrita ; GCTD de 449 ou 1 939 o sur ZBK.

**LRS2** — une entrée par bloc actif :

```
index    u32 LE   = bx | (by << shift)   coordonnées du bloc
count    u16 LE   nombre de matériaux (1 à 7)
mat_ids  u16 LE × count                  ID globaux (table du .terr)
```

- `shift` = **7** pour Zimnitrita, **8** pour ZBK (dépend du projet, détecté sur les fichiers).
- La position dans la liste = **slot** du matériau. Le slot 0 est le matériau le plus récemment appliqué dans Workbench ; c'est aussi le matériau implicite (w0) des poids.
- L'ordre des slots dans LRS2 est l'ordre des poids dans le `_layer` (w0, w1, …). **Toujours décoder les poids avec LRS2**, pas avec BMAT (qui peut différer).
- Le slot [0] compte dans le budget (comme Info & Diags de Workbench).

**GCTD** — un en-tête de 2 octets, puis une section par bloc actif, dans l'ordre de LRS2 :

```
bx       u16 LE
by       u16 LE
payload  N octets   une valeur par cellule + 1 octet de bourrage
```

- Résolution : **45×45** cellules par bloc sur Zimnitrita (2 025 + 1 o), **12×12** sur ZBK (144 + 1 o).
- **[À vérifier]** Codage des cellules. Deux descriptions coexistent dans les anciens documents :
  - (a) valeur = index local du slot (0, 1, 2…) ;
  - (b) valeur = `slot × 4 + sub`, avec `sub` 0 = présence faible, 1 = présence forte, et le slot 0 jamais codé (fond implicite).
  La (b) est la plus récente. Sans objet tant que l'app n'écrit pas les `.ttile`.
- **[À vérifier]** Valeur de l'en-tête : `EA 07` ou `91 00` selon les documents.

### 4.3 Poids des textures : `_layer.edds` et `_layer.dds`

**Encodage d'un pixel** (u32, format R32_UINT) :

```
bits 31-30 : 00
bits 29-25 : w6   bits 24-20 : w5   bits 19-15 : w4
bits 14-10 : w3   bits  9- 5 : w2   bits  4- 0 : w1
w0 = 31 − (w1 + … + w6)      (implicite, slot 0 de LRS2)
```

Somme toujours égale à 31. Une tuile fait 512×512 pixels, un bloc 128×128.

| Fichier | Structure |
|---|---|
| `_layer.edds` (format Enfusion) | en-tête DDS 128 o + extension DX10 20 o (dxgiFormat 42 = R32_UINT) ; à l'**offset 148** : tag `"LZ4 "`, taille compressée (u32 LE), taille décompressée (u32 LE, = 1 048 576), puis données. Un seul mip. LZ4 **chaîné** : 16 blocs de 64 Ko, chaque bloc (sauf le premier) compressé avec le bloc précédent décompressé comme dictionnaire. |
| `_layer.dds` (éditeur) | en-tête DDS 128 o + DX10 20 o, puis mip0 brut à l'offset 148 (1 048 576 o). Taille totale 1 048 724 o. Pas de LZ4. |
| Anciennes cartes (Eden, 128×128) | table de mips à l'offset 128, données `COPY` (non compressées) |

**Rôle des fichiers [À vérifier]** : les anciens documents se contredisent. Le test du diff avant/après dans Workbench (tuile 896) montre que `.ttile`, `_layer.dds` et `_layer.edds` sont **tous modifiés** au Save, et que Workbench recalcule les coutures sur les blocs voisins. Un autre passage affirme que Workbench ne modifie pas le `.edds` et que le `.ttile` est la seule source de vérité au runtime. L'emplacement exact du `_layer.edds` (`.Data/` ou `.EditorData/`) varie aussi selon les documents. Point de lecture actuel de l'app : `.Data/…_layer.edds`, puis `.EditorData/…_layer.edds`, puis `.EditorData/…_layer.dds`.

### 4.4 Autres fichiers

| Fichier | Contenu |
|---|---|
| `_supertexture.edds` / `.dds` | couleur du sol précalculée par Workbench (BC7 512×512 / RGBA8) — produit par Workbench, à ne pas écrire |
| `_normal.edds` / `.dds` | normal map 256×256 ; le canal alpha encode la couverture d'herbe |
| `.bterr` (par tuile, `.EditorData/`) | IFF EDTR : VERS + DATA = 129×129 float32 (heightmap d'édition) |
| `Terrain.bterr` (global) | IFF EDTR : VERS + HEAD 28 o (largeur, hauteur, résolution en f32) — ancien format, plus utilisé par l'app |
| `.terr` | table des matériaux du terrain (ID → nom, GUID) |
| `.emat` | matériau : BCRMiddleMap, MiddleColor, Color, MiddleScaleUV, héritage |
| `HeightMap.desc`, `NormTex.desc`, `SatTex.desc` | réglages texte d'import Workbench (altitudes min/max, normal map, satmap) |

### 4.5 Coordonnées

Orientation : nord en haut, X vers la droite (est), Y vers le haut (nord).

```
tile_id         = ty × grid_w + tx                (grid_w lu dans le projet : 32, 64…)
bloc global     = (tx × num_blk + bx_local, ty × num_blk + by_local)
tuile d'un bloc = (bx_global // num_blk, by_global // num_blk)
bloc d'un pixel = (x // 128, y // 128)            dans une tuile de 512 px
```

### 4.6 Écriture des fichiers terrain — historique

- Août 2026 : écriture directe du `.ttile` (LRS2 + GCTD) validée en jeu sur la tuile 616 (`write_ttile_block.py`), puis intégrée au pipeline et aux modes de `clean_weights.py`.
- Ensuite : résultats **non probants** (blocs voisins corrompus, liés au LZ4 chaîné et aux coutures), écriture **suspendue**, puis **retirée** de l'app pendant le nettoyage d'octobre.
- Pistes conservées dans l'archive pour une éventuelle reprise : pas de padding IFF (GCTD impair), en-tête DDS de 148 o (et non 128), dictionnaire LZ4 chaîné, recalcul des coutures par Workbench.
- Observation : après fusion de deux matériaux sur deux blocs voisins, un faible pourcentage de l'ancien réapparaît sur le second bloc (mélange de bordure probable).

---

## 5. Fonctions par onglet

| Onglet | Ce qu'il fait | Backend |
|---|---|---|
| Projets | créer, ouvrir, supprimer un projet | `main.py` |
| Terrain | chemins et fichiers du projet, collage du texte Workbench (grille), budget 5/7, analyse de heightmap, carte hypsométrique | `project_reader`, `terrain_analysis`, `hypsometric_colormap` |
| Inspection | grille QTRE (scan global), inspect tuile | `tile_inspector`, `clean_weights.mode_inspect` |
| Generation | presets de biomes, mapping masque → texture, paramètres du pipeline, aperçu des masques, export PNG | `pipeline_v5` |
| Satmap | scan .emat (→ `catalog_generated.json`), génération de la satmap, K-means (à retirer) | `generate_catalog`, `satmap_v2_textured_v2` |
| Corrections | scan global, scan de zone, inspect tuile, santé du terrain, inventaire des fichiers | `clean_weights`, `main.py` |

Inspection et Corrections font en partie double emploi (deux scans globaux avec deux codes différents, deux méthodes d'inspect tuile) : **fusion prévue** (§9).

---

## 6. Pipeline de masques (v5)

**Principe : normalisation par soustraction.** Chaque masque prend les pixels pas encore attribués par les masques précédents ; le premier a priorité absolue, le dernier prend ce qui reste. Le budget de slots du pipeline est ainsi garanti par construction.

**Budget du pipeline = budget du projet − 1** : un slot reste toujours libre pour le mappeur (retouches à la main dans Workbench). Budget 5 → le pipeline vise 4 ; budget 7 → 6. Aujourd'hui codé en dur à 6 (`BUDGET_MAX`), à brancher sur le projet à l'étape 5.

**Règle de placement en 3 niveaux** :
1. éléments distinctifs (forêts, drainages/flow, rochers) — posés en premier ;
2. textures de transition (landes rocheuses, maquis) ;
3. fond (landes de plateau, prairies).

**Ordre validé Zimnitrita (24/08)** : seabed → coastal → alpages → landes_rocheuses → maquis_landes → foret_coniferes → foret_feuillue → flow → landes_plateau → rock → deposit → prairie_seche → prairie_humide.

**Étapes du pipeline** : lecture heightmap → calcul terrain (pente, fBm, distance à la côte) → masques de base (seabed, coastal, rock, landes, flow, deposit) → végétation (prairies, maquis, alpages, forêts) → masque d'exclusion (Zone B préservée) → normalisation exclusive → arbitrage du budget par bloc → aperçu colorisé → export PNG.

**Rendu en jeu** : clutter et plantes 3D visibles au-delà de ~50-60 % du poids normalisé ; en dessous de 30-40 %, texture au sol seulement. Reforger normalise les poids **par pixel**.
**Réglages validés Zimnitrita** : pentes Gentle 10°, Landes 16°, Rock 28°, Cliff 35° ; flow_cut_low 0,55, flow_gamma 0,80 ; maquis : fenêtre de pente 5°→30°, transition d'altitude 30 m, boost (seuil 0,15, minimum 0,75).
**Problème connu** : un masque placé trop tard n'a plus de pixels libres → le remonter dans l'ordre ou booster son signal.

**Données associées** : 7 presets de biomes (`biomes_presets.json`) ; masques Gaea optionnels (flow, deposit) ; masque d'exclusion (blanc = Zone A générée, noir = Zone B préservée). Cache des dérivés du terrain : `outputs/cache/terrain_data.npz`, invalidé si la version du pipeline (`TERRAIN_PIPELINE_VERSION`) ou la heightmap change.

---

## 7. Satmap

- Le **.emat est la seule source** du catalog : héritage résolu ; middle = nom exact de `BCRMiddleMap` en .png ; teinte = MiddleColor × Color (linéaire → sRGB) ; tiling = MiddleScaleUV, ou 100 par défaut.
- `generate_catalog.py` produit `catalog_generated.json` ; la bascule vers `catalog.json` est **manuelle**.
- Poids lus dans les `_layer` + LRS2 (tous les blocs, jusqu'à 7 matériaux), et non plus dans le QTRE (qui manquait les blocs à 6-7 textures).
- Middles réels extraits des .edds ; échelle 1 m/px en coordonnées monde.
- Un seul PNG par génération (`satmap_v2_textured_native.png`, sinon `_4097` / `_8193`), pas d'agrandissement si la résolution demandée dépasse la native.
- Validée en jeu sur Zimnitrita (luminosité ~27 %, aucun MISS) et fonctionnelle sur ZBK (4096/4096 tuiles).
- Cas particuliers : ZI_Ground_Sport_01 garde la teinte calculée depuis le .emat ([211, 137, 39]) ; Rock_03 exclu volontairement (middle Granite_05 absent).
- Import dans Workbench : Terrain Tool → Satellite Texture → Import (`SatTex.desc`).

---

## 8. Règles de développement

### Règles du projet
- Ne **jamais écrire** les fichiers terrain (.edds, .dds, .ttile) : écriture retirée de l'app (§4.6). Workbench fermé avant toute manipulation de ces fichiers.
- Le code qui ne sert pas est **retiré** de l'application et archivé dans `_archives/code/<date>_<étape>/` (hors Git) avec un `NOTE.md` : origine, raison, ce qu'il faisait.
- Tout passe par l'application : pas de mode ligne de commande dans les modules de l'app ; un seul chemin d'exécution (dev = exe).
- Standalone d'abord, intégration ensuite.

### Méthode de travail
- Jordi conçoit et teste, Claude Code écrit le code, la conversation prépare les prompts **une fois le problème tranché**.
- Chaque prompt liste les fichiers et fonctions à **ne pas toucher**, interdit les modifications non demandées, exige `ast.parse()` + pyflakes après chaque modification, dry-run + confirmation avant toute écriture en lot, et des chemins loggés.
- Lecture seule d'abord (inventaire), puis modification fichier par fichier.
- Au début de chaque prompt : « lis d'abord CONCEPTION.md ».

### Git
- Commiter **uniquement** les fichiers de la tâche (jamais `git add -A`).
- **Toujours** lancer `git status --short` avant `git commit` pour vérifier que tous les fichiers de la tâche sont préparés (`project_reader.py` et le code de l'étape 2a avaient été oubliés les 11-12/10).
- Ignorés : logs, caches, `outputs/`, `test/`, `_archives/`, `_analyses/`, `catalog_generated.json`, `satmap_fond_512.png` (à ajouter : `.initialized`).
- Déplacer un fichier suivi vers `_archives/` le fait apparaître en `D` : l'enregistrer avec `git add -u <chemins>` (jamais `git add -A`).
- Tag `avant-nettoyage` sur `a897f12` (point de retour du nettoyage).

### Non-régression (`tools/check_regression.py`)
- Commandes : `enregistrer | comparer --projet <nom|tous> [--masques-seulement | --corrections-seulement]`.
- `tous` = `REFERENCE_PROJECTS` (Zimnitrita, Zbk_island), défini en tête du script. Un autre projet : `--projet <nom>`. Normandie et bornholm sont d'anciens projets non fonctionnels, hors tests.
- Couvre, par projet : satmap Native, scan global (Inspection), aperçu des masques (vraie méthode `Api.run_pipeline_preview()`), Corrections (vraies méthodes `inspect_tile`, `corrections_inspect_tile` ×3 modes, `corrections_scan_global`, `corrections_scan_zone`, `corrections_terrain_health`, `corrections_file_inventory`). Masques et Corrections tournent dans un sous-processus par projet.
- Corrections : tuiles de référence choisies automatiquement dans les `.ttile` (ordinaire au centre, bloc à 6-7 matériaux, bord, GCTD impair pour ZBK), dans `test/corrections/tiles.json` ; masque de zone carré au centre ; liste blanche stricte des fichiers comparés.
- Protège et restaure à l'octet près `config.json`, `settings.json`, et par projet `project.json`, `project_mask_config.json`, `surfaces.json` (restauration de tous les fichiers avant tout affichage).
- **Surveillance terrain** : relevé taille + date de tous les fichiers `.Data`, `.EditorData` et du `.terr` avant/après ; toute création/suppression/modification → KO.
- Durées indicatives : complet ~10 min ; `--corrections-seulement` ~3 min ; `--masques-seulement` ~2 min.
- **Protocole par étape** (plusieurs mappeurs modifient les cartes, une référence durable serait toujours périmée) :
  1. `enregistrer --projet tous` (ou partie ciblée) **juste avant** de toucher au code ;
  2. modification du code ;
  3. `comparer` sur la partie touchée par l'étape : `--corrections-seulement` (4b, 4c), `--masques-seulement` (5), complet (6, et avant toute release).
  Un `comparer` rouge sans modification du code = le terrain a changé (cas du 14/10).
- Lancer depuis PowerShell **sans** `| Tee-Object` (casse l'encodage). Les tests longs sont lancés par Jordi, pas par Claude Code.

### Garde-fou des valeurs en dur (`tools/check_hardcoded.py`)
- Cherche dans le code de l'app (`.py` de la racine, `web/`) : noms de projets (Zimnitrita, ZBK), lettres de disque, « Terrain_ », préfixes de textures custom (ZI_, zi_).
- `tools/hardcoded_exceptions.json` : occurrences encore tolérées, chacune rattachée à l'étape qui la supprimera (aucune exception permanente). 31 exceptions au 14/10.
- À lancer à chaque étape : il doit rester vert, et les exceptions traitées par l'étape sont retirées du fichier.
- Limite : ne voit pas les nombres (grille 32, budget 6) ; ceux-là sont suivis par `_analyses/audit_2026-10-12/rapport_etape3b.md`.

### Travailler avec Claude Code
- `/clear` avant chaque prompt ; prompts découpés ; « ne lire que les parties nécessaires » des gros fichiers (`check_regression.py` ~2 900 lignes).
- Claude Code s'arrête après `ast.parse()` + pyflakes + garde-fou ; Jordi lance les tests longs et envoie seulement les bilans.
- Ne jamais laisser Claude Code réécrire à côté ce que l'app sait déjà faire (cas du 14/10 : lecture LRS2 maison au lieu de `lrs2_parser`).

---

## 9. État et feuille de route

### Nettoyage (en cours depuis le 13/10)

| Étape | Contenu | État |
|---|---|---|
| 0 | Tag `avant-nettoyage`, dossier d'archive, non-régression des masques | Fait |
| 1 | Vérifications en lecture seule (`rapport_etape1.md`) | Fait |
| — | Réorganisation du dépôt : `_archives/`, `docs/technical/`, `LICENSE`, `CONCEPTION.md` | Fait (14/10) |
| 2 | Archiver les 11 fichiers morts de la racine (`_archives/code/2026-10-14_etape2_racine/`) | Fait (14/10) |
| 3 | Code mort dans les fichiers vivants ; libellé « PARTIEL » ; outils dans `tools/` ; `cache/` racine archivé (`logs/` conservé) | Fait (14/10) |
| 3b | **Inventaire des valeurs en dur** (sortes 1 / 2 / 3, avec destination) + garde-fou automatique ; **tous les ID de matériaux stockés** hors du .terr (code, `DEFAULT_MASK_CONFIG`, champ `ID` de `project_mask_config.json`, presets de biomes) et les endroits où la table ID → nom est lue une seule fois à l'ouverture | Fait (14/10) |
| 4a | `check_regression` étendu à Inspection et Corrections, surveillance terrain, projets de référence, encodage robuste | Fait (15/10) |
| 4b | `main.py` : appels directs aux `mode_*` en dev comme dans l'exe ; grille et préfixe transmis à `corrections_inspect_tile` ; échelle du masque de `mode_scan_zone` calculée depuis la grille du projet | **Prochaine** |
| 4c | `clean_weights.py` : retrait de l'écriture et de la ligne de commande (~1 150 lignes) | À faire |
| 5 | `pipeline_v5.py` : suppression du code Zimnitrita exécuté au chargement, retrait de l'écriture et de la ligne de commande (~540 lignes), branchement sur `project_reader` (budget pipeline = budget projet − 1) | À faire |
| 6 | Satmap sur `project_reader` ; archivage de `app_config.py` et `config.json` ; correction du chemin de `satmap_fond_512.png` ; `RAPPORT_CATALOG_GENERATION.md` écrit à côté du catalog (et non à la racine) ; suppression de `inputs/` et `Output/` à la racine | À faire |
| 7 | Retrait du K-means | À faire |
| 8 | Données et config (anciennes clés des `project.json`, README de Textures, `.initialized` dans `.gitignore`, sortir `config.json` / `settings.json` / `surfaces.json` du suivi Git) | À faire |
| 9 | Préparation de la release (`vanilla_base`, `.spec`, `requirements.txt`, recompilation, test sur un dossier vierge) | À faire |
| 10 | Code de l'application dans `app/` (imports, chemins de `main.py`, spec, outils de test) ; `_analyses/` rejoint `_archives/` | À faire |

### Problèmes connus (traités dans le nettoyage)
- `pipeline_v5.py` lit le .terr de Zimnitrita sur `I:` dès son import : sans ce disque, l'onglet Generation plante (étape 5).
- `vanilla_base_sauv` n'existe pas (`main.py:47`, `.spec:23`) : un nouvel exe ne copierait pas le catalog (étape 9).
- `config.json` est écrit à chaque ouverture de Satmap mais jamais lu (étape 6).
- `satmap_fond_512.png` est écrit trois niveaux trop haut (hors du projet) (étape 6).
- `load_project` réécrit `settings.json` et `surfaces.json` à chaque ouverture ; `run_pipeline_preview` enregistre `project.json` et `project_mask_config.json` à chaque aperçu.
- Grille 32×32 et préfixe `Terrain_` en dur dans la page Inspection (fusion).
- **`corrections_inspect_tile`** (`main.py` ~1991-1996) n'envoie ni `grid_w`, ni `num_blk`, ni `tile_prefix` à `mode_inspect`, `mode_weights`, `mode_validate` : les défauts 32 / 4 / `Terrain_` s'appliquent sur ZBK (aucune image « poids » produite sur ZBK). Étape 4b ; différence attendue dans `comparer` sur ZBK uniquement.
- **`mode_scan_zone`** (`clean_weights.py` ~1659-1661) : `px_per_tile = 508 if w > 8000 else 128`, calibré pour 32 tuiles, faux sur ZBK. Étape 4b.
- Logs de l'app : emojis et accents qui provoquent des erreurs selon l'encodage de la console (nettoyage des logs).
- À trancher à l'étape 5 : usage réel des ID issus de `surfaces.json` dans `run_pipeline_preview` (calcul ou légende).

### Ensuite, dans cet ordre
1. **Fusion Inspection + Corrections → « Tile Diagnostic »** :
   - carte quadrillée d'analyse globale : budget, slots négligeables, recherche des blocs contenant **toutes** les textures choisies parmi celles du .terr, export 4k (aperçu satmap dans Workbench) et CSV ;
   - inspect tuile relié à la carte ;
   - onglet Validation des fichiers (santé du terrain + inventaire).
2. **Corrections fonctionnelles** : confirmations manquantes (« Apply Reforger grid », suppression d'un chemin), sliders de Generation (3 crans pour descendre de 1), import de heightmap (le remplacement ne s'enregistre pas), clés i18n brutes, accents dans les logs.
3. **Nouveautés** :
   - carte hillshade (relief ombré) à la place du K-means ;
   - **splines forêt** à partir des masques forêt, **en écrivant directement des fichiers `.layer`** depuis Python (pas besoin de plugin) : masque → contours simplifiés → coordonnées monde (grille et m/px du projet) → entités forêt (forme fermée + générateur) dans un `.layer`. Même méthode que les routes de la carte Normandie (données QGIS → splines → `.layer`) : retrouver ce script et le format exact des entités. À regarder aussi : `_archives/genese/vegetation_polyline_exporter.py`. Vérifier sur un exemple réel quelle entité Workbench sert aux forêts et ses réglages.

### Python et Workbench (décision du 14/10)

| Besoin | Outil |
|---|---|
| Calcul lourd sur grilles, analyse, interface riche | Python (Map Generator) |
| Créer des objets dans le monde (forêts, routes…) | Fichiers `.layer` écrits par Python |
| Agir en direct dans l'éditeur (confort, régénération) | Plugin Workbench en Enforce Script — optionnel, plus tard |

Un mod ne peut contenir que du script, pas d'exe ni de code natif : le calcul reste dans l'app, l'échange se fait par fichiers.

### Idées pour plus tard
**Placement de villes et villages** aux emplacements favorables (zones plates, abritées, proches de l'eau, non inondables), à partir de l'analyse de terrain déjà calculée (pente, courbure, TPI, distance à la côte, ruissellement) — c'était l'idée de départ du projet ; bathymétrie de la carte Normandie (voir `merge_bathymetry.py` archivé à l'étape 2) ; éditeur de catalog dans l'app ; génération d'un middle depuis la texture de détail ; carte de rasterisation type carte 2D en jeu ; masques ↔ routes/bâtiments/forêts ; génération de `.layer` depuis OSM (bâtiments) ; éditeur de heightmap (île, érosion, aplanissement) ; lien tuile → Workbench au bon bloc ; drag-and-drop de l'ordre des masques ; tooltips des sliders ; analyse des ClutterConfig (avertissement « 32 clutter models » sur certains blocs).

---

## 10. Jalons

| Période | Réalisations |
|---|---|
| Juin 2026 | Décodage du chunk LRS2 ; premiers changelogs |
| Juillet–août 2026 | Formats Enfusion décodés (.ttile, _layer, .bterr, .emat, .terr, résolution du GCTD) ; écriture directe `.ttile` testée ; outils terrain ; pipeline de masques v5 ; Zone B de Zimnitrita validée en jeu ; app Streamlit v7 puis passage à PyWebView ; multi-projets ; v1 distribuée |
| Septembre 2026 | Catalog unique généré depuis les .emat ; vrais middles ; satmap validée en jeu |
| 27/09 → 02/10 | Un seul PNG satmap ; échelle depuis Workbench ; Inspect validé face à Workbench ; table matériaux lue dans le .terr ; grille dynamique ; budget 5/7 ; `check_regression.py` |
| 11 → 14/10 | `project_reader.py` ; correction de la lecture IFF (ZBK complet) ; ménage de Textures ; audit complet ; rattrapage Git ; non-régression des masques ; ce document ; réorganisation du dépôt (`_archives/`, `docs/technical/`, `LICENSE`) ; étape 2 du nettoyage |
| 14 → 15/10 | Étapes 3 (code mort, `tools/`), 3b (inventaire des valeurs en dur, garde-fou) et 4a (non-régression d'Inspection/Corrections, surveillance des fichiers terrain) |

---

## 11. Questions ouvertes

- Codage exact des cellules GCTD et rôle respectif de `_layer.edds` / `_layer.dds` / `.ttile` au chargement (§4.2, §4.3) — sans objet tant que l'écriture est retirée.
- ZBK : nombre de masques (13 contre 17 pour Zimnitrita) — à confirmer.
---

## 12. Documentation

- **`CONCEPTION.md`** (ce fichier) : référence à jour, versionnée.
- **`docs/technical/`** (versionné) : uniquement les formats Enfusion — `FORMATS_BINAIRES.md`, `FORMAT_LAYER_EDDS.md`, `ANALYSE_LOGIQUE_BOHEMIA_LAYER_EDDS.md`. En cas de contradiction, §4 de ce document fait foi.
- **`_archives/docs/`** : anciens documents (architecture Streamlit, pipelines de juin, références de fonctions) — historiques, à ne pas utiliser comme référence.
- **`_analyses/`** : rapports d'audit (non versionnés).
- **`_archives/code/*/NOTE.md`** : ce que faisait chaque fichier retiré.
