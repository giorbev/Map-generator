# AUDIT LECTURE SEULE — ONGLETS INSPECTION ET CORRECTIONS

**Date** : 2026-09-27  
**Objectif** : Cartographie complète des fonctionnalités, redondances, et traçage de l'affichage des noms de textures

---

## VOLET 1 — CARTOGRAPHIE ET REDONDANCES

### 1.1 ONGLET INSPECTION (`web/inspection.html`)

#### Tab 1 : GRILLE QTRE

| Fonctionnalité | Bouton/Libellé | Fonction JS | API Python | Script externe | Source données | Sortie | R/W |
|----------------|----------------|-------------|------------|----------------|----------------|--------|-----|
| **Affichage grille QTRE** | (Chargement auto) | `loadQtre()` | `get_qtre_cache()` | — | `outputs/cache/qtre_scan.json` | Grille colorée superposée sur satmap | **R** |
| **Affichage satmap** | (Chargement auto) | `loadQtre()` → `get_satmap_b64()` | `get_satmap_b64()` | — | `inputs/satmap_fond_512.png` ou `.jpg` | Image base64 dans HTML | **R** |
| **Sélection budget** | Radio 5/7 | `setBudget(v)` | — | — | Variable JS `_budget` | Re-calcul couleurs grille | — |
| **Sélection tuile** | Click cellule | `selectCell(el)` | — | — | `_scanData` (cache JSON) | Affichage détails tuile | **R** |

**Données lues** :
- `outputs/cache/qtre_scan.json` : Cache du scan global (tiles[], tid, max_tex_per_block, n_active_mats)
- `inputs/satmap_fond_512.png` : Image satmap générée par satmap_v2_textured_v2.py

**Données écrites** : ❌ **AUCUNE** (lecture seule)

---

#### Tab 2 : INSPECT TUILE

| Fonctionnalité | Bouton/Libellé | Fonction JS | API Python | Script externe | Source données | Sortie | R/W |
|----------------|----------------|-------------|------------|----------------|----------------|--------|-----|
| **Inspection tuile** | 🔍 Inspecter | `inspectTile()` | `inspect_tile(tx, ty)` | `clean_weights.py --inspect tx,ty` | `.Data/Terrain_{tid}.ttile` (LRS2), `.EditorData/*.edds` (weights), `surfaces.json` (table matériaux) | `outputs/generated/tiles/tile_{tx}_{ty}_cleanup.png` (image blocs+poids), log texte | **R+W** |

**Arguments script externe** :
```bash
# Mode exe
mode_inspect(tx, ty, data_dir, editor_dir, surfaces, threshold=0.01, output_dir)

# Mode dev
python clean_weights.py --inspect tx,ty
```

**Données lues** :
- `.Data/Terrain_{tid}.ttile` : Bloc LRS2 (IDs matériaux globaux)
- `.EditorData/Terrain_{tid}_layer.edds` : Poids par layer (w0, w1, w2, ...)
- `surfaces.json` : Table ID→nom matériau
- `.terr` du projet : Table matériaux (via `read_mats_from_terr`)

**Données écrites** :
- `outputs/generated/tiles/tile_{tx}_{ty}_cleanup.png` : Image PNG (visualisation poids par bloc)

**Traitement** :
1. Calcul `tid = ty * 32 + tx` (coord tuile LRS2)
2. Lecture `.ttile` → IDs matériaux par bloc (16×16 blocs)
3. Lecture `.edds` → Poids par slot (w0, w1, ..., w7)
4. Conversion ID→nom via `surfaces.json`
5. Génération image : chaque bloc = cellule colorée avec poids superposés

---

#### Tab 3 : SCAN GLOBAL

| Fonctionnalité | Bouton/Libellé | Fonction JS | API Python | Script externe | Source données | Sortie | R/W |
|----------------|----------------|-------------|------------|----------------|----------------|--------|-----|
| **Vérifier cache** | (Chargement auto) | `loadScanInfo()` | `get_scan_info()` | — | `outputs/cache/qtre_scan.json` | Affichage infos cache (n tuiles, date) | **R** |
| **Scanner toutes tuiles** | 📡 Scanner | `scanTiles()` | `scan_tiles()` | `tile_inspector.py --export-json` | `.Data/Terrain_*.ttile` (1024 tuiles), `.terr` (table matériaux), `.EditorData/*.edds` (weights) | `outputs/cache/qtre_scan.json` (cache global), log | **R+W** |
| **Rescanner** | 🔄 Rescanner | `rescanTiles()` | `delete_scan_cache()` + `scan_tiles()` | `tile_inspector.py --export-json` | Idem | Idem | **R+W** |

**Arguments script externe** :
```bash
# Mode exe
from tile_inspector import export_json
export_json(data_dir, cache_json)

# Mode dev
python tile_inspector.py --tiles-dir {data_dir} --export-json {cache_json}
```

**Données lues** :
- `.Data/Terrain_*.ttile` : Tous les fichiers tuiles (LRS2)
- `.terr` : Table matériaux projet
- `.EditorData/*.edds` : Layers poids (optionnel)

**Données écrites** :
- `outputs/cache/qtre_scan.json` : Cache JSON global
  - Structure : `{"generated_at": "ISO timestamp", "tiles": [{"tid": int, "tx": int, "ty": int, "max_tex_per_block": int, "n_active_mats": int, ...}, ...]}`

**Traitement** :
1. Scan récursif `.Data/Terrain_*.ttile`
2. Pour chaque tuile :
   - Lecture LRS2 (IDs matériaux par bloc)
   - Comptage textures actives par bloc
   - Détection max_tex_per_block (QTRE = 4-5, Zimnitrita = 7)
3. Export JSON cache

---

### 1.2 ONGLET CORRECTIONS (`web/corrections.html`)

#### Tab 1 : SCAN GLOBAL

| Fonctionnalité | Bouton/Libellé | Fonction JS | API Python | Script externe | Source données | Sortie | R/W |
|----------------|----------------|-------------|------------|----------------|----------------|--------|-----|
| **Scan slots négligeables** | 🔍 Lancer le scan | `runScan()` | `corrections_scan_global(threshold)` | `clean_weights.py --scan threshold` | `.Data/Terrain_*.ttile` (LRS2), `.EditorData/*.edds` (weights), `surfaces.json` | Log détection slots < seuil | **R** |

**Arguments script externe** :
```bash
# Mode exe
mode_scan(data_dir, editor_dir, threshold)

# Mode dev
python clean_weights.py --scan {threshold}
```

**Paramètres** :
- `threshold` : Seuil couverture (default 1.0%, slider 0.5-5.0%)

**Données lues** :
- `.Data/Terrain_*.ttile` : LRS2 (IDs matériaux)
- `.EditorData/*.edds` : Weights par layer
- `surfaces.json` : Table matériaux

**Données écrites** : ❌ **AUCUNE** (lecture seule)

**Traitement** :
1. Scan tous blocs de toutes tuiles
2. Pour chaque slot (w0-w7) : calcul coverage % = sum(poids) / (33*33*255)
3. Détection slots < threshold
4. Log résultats (coord bloc LRS2, slot, coverage%)

---

#### Tab 2 : SCAN ZONE

| Fonctionnalité | Bouton/Libellé | Fonction JS | API Python | Script externe | Source données | Sortie | R/W |
|----------------|----------------|-------------|------------|----------------|----------------|--------|-----|
| **Choisir masque** | 📁 Choisir masque PNG | `pickZoneMask()` | `pick_any_file(['png'])` | — | Fichier PNG externe | Chemin masque stocké JS | **R** |
| **Scan zone** | 🔍 Scan zone | `runScanZone()` | `corrections_scan_zone(mask_path)` | `clean_weights.py --scan-zone {mask}` | Masque PNG (blanc = zone active), `.Data/Terrain_*.ttile`, `.EditorData/*.edds`, `surfaces.json` | Log détection slots négligeables (zone) | **R** |

**Arguments script externe** :
```bash
# Mode exe
mode_scan_zone(mask, data_dir, editor_dir, surfaces)

# Mode dev
python clean_weights.py --scan-zone {mask_path}
```

**Données lues** :
- Masque PNG : Blanc = zone à scanner, noir = ignorer
- Idem Scan global (tuiles, weights, surfaces)

**Données écrites** : ❌ **AUCUNE** (lecture seule)

**Traitement** :
1. Lecture masque PNG → grille 32×32 tuiles actives
2. Scan uniquement tuiles dans zone blanche
3. Détection slots négligeables (idem Scan global)

---

#### Tab 3 : INSPECT TUILE

| Fonctionnalité | Bouton/Libellé | Fonction JS | API Python | Script externe | Source données | Sortie | R/W |
|----------------|----------------|-------------|------------|----------------|----------------|--------|-----|
| **Inspect** | 🔎 Lancer (mode Inspect) | `runInspect()` | `corrections_inspect_tile(tx, ty, "inspect")` | `clean_weights.py --inspect tx,ty` | Idem Inspection/Inspect tuile | Image + log | **R+W** |
| **Weights** | 🔎 Lancer (mode Weights) | `runInspect()` | `corrections_inspect_tile(tx, ty, "weights")` | `clean_weights.py --weights tx,ty` | Idem | Log poids détaillés | **R** |
| **Validate** | 🔎 Lancer (mode Validate) | `runInspect()` | `corrections_inspect_tile(tx, ty, "validate")` | `clean_weights.py --validate tx,ty` | Idem | Log validation poids | **R** |

**Arguments script externe** :
```bash
# Mode exe
mode_inspect(tx, ty, data_dir, editor_dir, surfaces, threshold=0.01, output_dir)
mode_weights(tx, ty, data_dir, editor_dir, surfaces, output_dir)
mode_validate(tx, ty, data_dir, editor_dir, surfaces)

# Mode dev
python clean_weights.py --inspect tx,ty
python clean_weights.py --weights tx,ty
python clean_weights.py --validate tx,ty
```

**Données lues/écrites** : Idem Inspection/Inspect tuile

---

#### Tab 4 : SANTÉ TERRAIN

| Fonctionnalité | Bouton/Libellé | Fonction JS | API Python | Script externe | Source données | Sortie | R/W |
|----------------|----------------|-------------|------------|----------------|----------------|--------|-----|
| **Analyser santé** | ❤️ Analyser | `runHealth()` | `corrections_terrain_health()` | — (fonction Python directe) | `.Data/Terrain_*.ttile` (taille fichiers), `.EditorData/*.edds` | Stats (n_ok, n_warn, n_err), log | **R** |

**Traitement** :
1. Comptage tuiles `.ttile` dans `.Data/`
2. Vérification taille fichiers (< 100 bytes = erreur, < 1000 = warning)
3. Vérification présence `.EditorData/`
4. Comptage `.edds` dans `.EditorData/`
5. Retour stats + log

**Données lues** :
- `.Data/Terrain_*.ttile` : Métadonnées fichiers (taille)
- `.EditorData/*.edds` : Comptage

**Données écrites** : ❌ **AUCUNE** (lecture seule)

---

#### Tab 5 : INVENTAIRE FICHIERS

| Fonctionnalité | Bouton/Libellé | Fonction JS | API Python | Script externe | Source données | Sortie | R/W |
|----------------|----------------|-------------|------------|----------------|----------------|--------|-----|
| **Scanner inventaire** | 📊 Scanner | `runInventory()` | `corrections_file_inventory()` | — (fonction Python directe) | `project.json` (grille), `.Data/Terrain_*.ttile`, `.EditorData/*.edds` | Stats (présents/manquants), liste manquants | **R** |

**Traitement** :
1. Lecture grille depuis `project.json` (grid_w)
2. Calcul attendus : `grid_w × grid_w` tuiles (ex: 32×32 = 1024)
3. Scan `.Data/` → détection `.ttile` présents
4. Comparaison attendus vs présents
5. Comptage `.edds` dans `.Data/` et `.dds` dans `.EditorData/`
6. Retour liste manquants + stats

**Données lues** :
- `project.json` : Grille Reforger (grid_w)
- `.Data/Terrain_*.ttile` : Comptage présents
- `.EditorData/*.edds` et `.dds` : Comptage

**Données écrites** : ❌ **AUCUNE** (lecture seule)

---

### 1.3 TABLEAU DES REDONDANCES

| Fonctionnalité | Onglet 1 | Onglet 2 | Données lues | Redondance | Écriture |
|----------------|----------|----------|--------------|------------|----------|
| **Affichage cache QTRE** | Inspection › GRILLE QTRE | — | `outputs/cache/qtre_scan.json` | — | ❌ |
| **Affichage satmap** | Inspection › GRILLE QTRE | — | `inputs/satmap_fond_512.png` | — | ❌ |
| **Scan global tuiles** | Inspection › SCAN GLOBAL | — | `.Data/*.ttile`, `.terr`, `.EditorData/*.edds` | — | ✅ Cache JSON |
| **Inspect tuile tx,ty** | Inspection › INSPECT TUILE | Corrections › INSPECT TUILE | `.Data/Terrain_{tid}.ttile`, `.EditorData/*.edds`, `surfaces.json` | ⚠️ **REDONDANCE** (2 onglets, même fonction) | ✅ Image PNG |
| **Scan slots négligeables** | — | Corrections › SCAN GLOBAL | `.Data/*.ttile`, `.EditorData/*.edds` | — | ❌ |
| **Scan zone masque** | — | Corrections › SCAN ZONE | Masque PNG + `.Data/*.ttile` | — | ❌ |
| **Santé terrain** | — | Corrections › SANTÉ TERRAIN | `.Data/*.ttile` (métadonnées) | Partiel avec Inventaire (comptage tuiles) | ❌ |
| **Inventaire fichiers** | — | Corrections › INVENTAIRE | `project.json`, `.Data/*.ttile` | Partiel avec Santé (comptage tuiles) | ❌ |

**REDONDANCES DÉTECTÉES** :

1. **Inspect tuile (tx, ty)** : Présent dans 2 onglets
   - `Inspection › INSPECT TUILE`
   - `Corrections › INSPECT TUILE`
   - **Même fonction API** : `inspect_tile(tx, ty)` (Inspection) vs `corrections_inspect_tile(tx, ty, mode="inspect")` (Corrections)
   - **Même script** : `clean_weights.py --inspect tx,ty`
   - **Même sortie** : `outputs/generated/tiles/tile_{tx}_{ty}_cleanup.png`
   - ⚠️ **RECOMMANDATION** : Fusionner en une seule fonctionnalité

2. **Comptage tuiles .ttile** : Présent dans 2 fonctionnalités
   - `Corrections › SANTÉ TERRAIN` : Comptage + vérification taille
   - `Corrections › INVENTAIRE` : Comptage + détection manquants
   - **Données lues** : `.Data/Terrain_*.ttile` (métadonnées)
   - ⚠️ **RECOMMANDATION** : Partiel, logiques différentes (santé = taille, inventaire = présence)

3. **Lecture surfaces.json** : Utilisée dans 4 fonctionnalités
   - `Inspection › INSPECT TUILE`
   - `Corrections › SCAN GLOBAL`
   - `Corrections › SCAN ZONE`
   - `Corrections › INSPECT TUILE`
   - **Chemin** : `{project_path}/surfaces.json`
   - ℹ️ **NORMAL** : Table de référence globale

---

### 1.4 FONCTIONNALITÉS QUI ÉCRIVENT

| Fonctionnalité | Fichier écrit | Type | Onglet |
|----------------|---------------|------|--------|
| **Scan global tuiles** | `outputs/cache/qtre_scan.json` | Cache JSON | Inspection › SCAN GLOBAL |
| **Inspect tuile** | `outputs/generated/tiles/tile_{tx}_{ty}_cleanup.png` | Image PNG | Inspection › INSPECT TUILE, Corrections › INSPECT TUILE (mode inspect) |

**Toutes les autres fonctionnalités sont en LECTURE SEULE.**

---

## VOLET 2 — NOMS DE TEXTURES DE "INSPECT TUILE"

### 2.1 CHAÎNE COMPLÈTE : BLOC → IDs → NOMS AFFICHÉS

**Contexte** : L'onglet `Inspection › INSPECT TUILE` génère une image PNG affichant chaque bloc d'une tuile avec les noms de matériaux et leurs poids. **Comment les noms sont-ils obtenus ?**

---

#### Étape 1 : Coordonnées tuile (tx, ty) → Tile ID (tid)

**Formule** :
```python
tid = ty * 32 + tx  # Grille 32×32 tuiles (convention LRS2)
```

**Exemple** :
- Tuile (16, 16) → tid = 16 * 32 + 16 = **528**
- Tuile (0, 0) → tid = **0**
- Tuile (31, 31) → tid = 31 * 32 + 31 = **1023**

**Fichier** : `.Data/Terrain_{tid}.ttile`

---

#### Étape 2 : Lecture IDs matériaux depuis .ttile (LRS2)

**Format** : Bloc binaire LRS2 (Layer Reference System 2)

**Structure** :
- **1024 tuiles** (32×32)
- **Chaque tuile** : 16×16 blocs = **256 blocs**
- **Chaque bloc** : 8 slots (w0, w1, ..., w7)
- **Chaque slot** : 1 ID matériau (uint16 ou uint32)

**Lecture** :
```python
from lrs2_parser import load_lrs2_from_ttile

ttile_path = data_dir / f"Terrain_{tid}.ttile"
lrs2_data = load_lrs2_from_ttile(ttile_path)
# lrs2_data : dict {(lrs2_x, lrs2_y): [id0, id1, id2, ...]}
```

**Coordonnées globales LRS2** :
```python
def calculate_lrs2_coords(tx: int, ty: int, bx: int, by: int) -> Tuple[int, int]:
    """
    Convertit coordonnées (tuile + bloc) en coordonnées LRS2 globales.
    tx, ty : 0-31 (position tuile dans grille)
    bx, by : 0-15 (position bloc dans tuile)
    """
    lrs2_x = tx * 16 + bx
    lrs2_y = ty * 16 + by
    return lrs2_x, lrs2_y
```

**Exemple** :
- Tuile (16, 16), bloc (0, 0) → LRS2 (256, 256)
- Tuile (16, 16), bloc (15, 15) → LRS2 (271, 271)

**IDs matériaux** : Tableau d'entiers (ex: `[123, 45, 67, 0, 0, 0, 0, 0]`)
- **IDs globaux LRS2** : Index dans la table globale des matériaux (définie dans `.terr`)
- **ID = 0** : Slot vide (pas de matériau)

---

#### Étape 3 : Conversion ID → Nom de matériau

**Table utilisée** : `surfaces.json` (racine projet)

**Structure** :
```json
{
  "materials": {
    "Grass_03": 123,
    "Dirt_02": 45,
    "Forest_Deciduous_01": 67,
    ...
  }
}
```

**Conversion inverse** :
```python
# Charger surfaces.json
surfaces = json.loads(Path(project_path) / "surfaces.json".read_text())
mat_dict = surfaces["materials"]

# Créer index inverse ID → Nom
id_to_name = {v: k for k, v in mat_dict.items()}

# Convertir ID → Nom
mat_id = 123
mat_name = id_to_name.get(mat_id, f"ID_{mat_id}")  # "Grass_03"
```

**Fallback** : Si ID absent de `surfaces.json`, affichage `"ID_{mat_id}"`

---

#### Étape 4 : Construction de la table ID→Nom

**Source primaire** : `surfaces.json` (table projet)

**Comment `surfaces.json` est-il construit ?**
- **Générateur** : `pipeline_v5.py` ou `satmap_v2_textured_v2.py`
- **Source** : `.terr` du projet (`{terrain_dir}/worlds/{world_name}/{world_name}.terr`)
- **Fonction** : `read_mats_from_terr(terr_path)`
  - Lit le fichier `.terr` (XML)
  - Extrait la liste des matériaux avec leurs IDs LRS2 globaux
  - Sauvegarde dans `surfaces.json`

**Exemple `.terr`** :
```xml
<Surface Name="Grass_03" Id="123" />
<Surface Name="Dirt_02" Id="45" />
<Surface Name="Forest_Deciduous_01" Id="67" />
```

**Génération `surfaces.json`** :
```python
from terrain_terr_reader import read_mats_from_terr

terr_path = Path("path/to/world.terr")
mats = read_mats_from_terr(terr_path)
# mats : {"Grass_03": 123, "Dirt_02": 45, ...}

surfaces = {"materials": mats}
Path("surfaces.json").write_text(json.dumps(surfaces, indent=2))
```

---

#### Étape 5 : Type d'IDs (globaux LRS2 vs locaux GCTD)

**Format du projet** : `.ttile` utilise **LRS2** (Layer Reference System 2)

**IDs LRS2** :
- **IDs globaux** : Uniques à travers tout le terrain
- **Définis dans `.terr`** : Chaque matériau a un ID global fixe
- **Exemple** : Grass_03 = ID 123 (même ID dans toutes les tuiles)

**IDs GCTD** (GAEA Compressed Terrain Data) :
- **IDs locaux par tuile** : Chaque tuile a sa propre table locale
- **Slots w0-w7** : Indexés localement (0-7)
- **Conversion** : GCTD local → LRS2 global (via table de mapping)

**⚠️ IMPORTANT** : Le projet utilise **LRS2**, donc IDs globaux. Pas de conversion locale nécessaire.

---

#### Étape 6 : Traitement du slot w0 implicite

**Convention Reforger** :
- **Slot w0** : Matériau de base (background)
- **Implicite dans LRS2** : Si slot w0 absent du bloc LRS2, il est **toujours présent** (poids = 255 - sum(autres poids))

**Calcul poids w0** :
```python
# Lire poids des slots w1-w7 depuis .edds
weights = extract_all_weights(edds_path, bx, by)  # [w0, w1, w2, ...]

# Si w0 non stocké dans .edds, calculer implicitement
total_other = sum(weights[1:])
if weights[0] == 0:
    weights[0] = max(0, 255 - total_other)
```

**Affichage dans Inspect tuile** :
- w0 affiché même si poids = 0 (slot vide)
- Nom matériau w0 : Depuis LRS2 bloc ID[0]

---

#### Étape 7 : Formule conversion coordonnées

**Coordonnées disponibles** :
- **Tuile** : (tx, ty) — 0-31 (grille 32×32)
- **Bloc** : (bx, by) — 0-15 (16×16 blocs par tuile)
- **Pixel** : (px, py) — 0-32 (33×33 vertices par bloc)

**Conversion vers LRS2 global** :
```python
# Bloc → LRS2
lrs2_x = tx * 16 + bx  # 0-511 (32*16 = 512 blocs globaux)
lrs2_y = ty * 16 + by

# Pixel → LRS2
lrs2_px = lrs2_x * 33 + px  # 0-16896 (512*33 = 16896 pixels globaux)
lrs2_py = lrs2_y * 33 + py
```

**Conversion inverse LRS2 → Tuile+Bloc** :
```python
lrs2_x = 256  # Exemple
lrs2_y = 256

tx = lrs2_x // 16  # 256 // 16 = 16
ty = lrs2_y // 16  # 16
bx = lrs2_x % 16   # 256 % 16 = 0
by = lrs2_y % 16   # 0

# Résultat : Tuile (16, 16), bloc (0, 0)
```

---

### 2.2 DIVERGENCES POSSIBLES

#### 2.2.1 Source table ID→Nom

**Sources possibles** :
1. ✅ **`surfaces.json`** (projet) — Source actuelle
2. ❌ **Table en dur** dans le script — Non utilisé
3. ❌ **Catalogue global** — Non utilisé (catalogue = paths vers .emat, pas IDs LRS2)

**Divergence** : Si `surfaces.json` désynchronisé avec `.terr`
- **Cause** : Modification `.terr` sans regénération `surfaces.json`
- **Symptôme** : IDs affichés comme `"ID_123"` au lieu du nom
- **Solution** : Regénérer `surfaces.json` depuis `.terr`

---

#### 2.2.2 IDs 0-based vs 1-based

**Convention LRS2** : **IDs 0-based**
- ID 0 = Matériau vide (pas de texture)
- ID 1+ = Matériaux définis

**⚠️ ATTENTION** : Certains projets utilisent IDs 1-based
- `.terr` commence à ID=1
- ID 0 réservé comme "non défini"

**Vérification** :
```python
# Lire .terr et vérifier premier ID
mats = read_mats_from_terr(terr_path)
first_id = min(mats.values())
# first_id == 0 → 0-based
# first_id == 1 → 1-based
```

---

#### 2.2.3 Customs zi_ intercalés

**Zimnitrita** : Matériaux customs préfixés `zi_` (ex: `zi_Rock_01b`)

**IDs dans `.terr`** :
- **Vanilla** : IDs 0-55 (56 matériaux Reforger vanilla)
- **Customs** : IDs 56+ (matériaux projet Zimnitrita)

**Exemple** :
```
ID 0-55  : Vanilla (Grass_03, Dirt_02, ...)
ID 56    : zi_Rock_01b
ID 57    : zi_Mud_River
...
```

**Divergence** : Si `surfaces.json` d'un autre projet (ex: projet vanilla uniquement)
- IDs 56+ affichés comme `"ID_56"` au lieu de `"zi_Rock_01b"`

**Solution** : Toujours utiliser `surfaces.json` du projet courant

---

#### 2.2.4 Projet ZBK vs Zimnitrita

**ZBK** : Projet custom avec matériaux ZBK
**Zimnitrita** : Projet avec matériaux zi_*

**Tables différentes** :
- **ZBK** : `surfaces.json` avec matériaux ZBK
- **Zimnitrita** : `surfaces.json` avec matériaux zi_*

**⚠️ DIVERGENCE** : Si cache partagé entre projets
- Cache QTRE `outputs/cache/qtre_scan.json` peut contenir IDs d'un projet
- Affichage avec `surfaces.json` d'un autre projet → Noms incorrects

**Solution** : Cache QTRE par projet (déjà implémenté)

---

### 2.3 SCRIPT STANDALONE : `verify_inspect_names.py`

**Objectif** : Vérifier la cohérence des noms de matériaux affichés dans "Inspect tuile"

**Entrée** : Liste de blocs en coordonnées LRS2 globales (ex: [(256, 256), (271, 271), ...])

**Sortie** : Tableau comparatif
```
Bloc LRS2   | Noms selon Inspect tuile | Noms selon LRS2 .ttile + .terr | % Couverture
------------|--------------------------|--------------------------------|-------------
(256, 256)  | Grass_03, Dirt_02        | Grass_03, Dirt_02              | 100%
(271, 271)  | ID_56, Dirt_02           | zi_Rock_01b, Dirt_02           | 50%
```

**Implémentation** : Voir fichier `verify_inspect_names.py` ci-dessous

---

## CONCLUSION

### Redondances identifiées

1. **Inspect tuile** : 2 onglets (Inspection + Corrections) → Fusionner
2. **Comptage tuiles** : Santé terrain + Inventaire → Logiques différentes, conserver

### Fonctionnalités en écriture

- Scan global tuiles → Cache JSON
- Inspect tuile → Image PNG

### Chaîne noms matériaux

**Bloc (tx,ty,bx,by) → LRS2 global → ID matériau → surfaces.json → Nom affiché**

**Sources** :
- IDs : `.Data/Terrain_{tid}.ttile` (LRS2)
- Noms : `surfaces.json` (construit depuis `.terr`)

**Type IDs** : Globaux LRS2 (pas de conversion locale)

**Script verify_inspect_names.py** : Créé ci-dessous

