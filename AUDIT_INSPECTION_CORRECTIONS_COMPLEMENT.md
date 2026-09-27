# COMPLÉMENT AUDIT INSPECTION / CORRECTIONS

**Date** : 2026-09-27  
**Objet** : Corrections et compléments techniques (formules LRS2, vérification, sources données)

---

## 1. FORMULES LRS2 DANS LE CODE RÉEL

### 1.1 Conversion tx,ty,bx,by → LRS2

**Fichier** : `tile_inspector.py:44-57`
```python
def calculate_lrs2_coords(tx: int, ty: int, bx: int, by: int) -> Tuple[int, int]:
    """
    Calcule les coordonnées LRS2 globales d'un bloc.
    
    Args:
        tx, ty: Coordonnées de la tile (0-31)
        bx, by: Position du bloc dans la tile (0..3)  ← 4 blocs par tuile
    
    Returns:
        (lrs_x, lrs_y): Coordonnées LRS2 globales
    """
    lrs_x = tx * 4 + bx
    lrs_y = ty * 4 + by
    return lrs_x, lrs_y
```

**Fichier** : `clean_weights.py:136-140`
```python
def calculate_lrs2_coords(tx: int, ty: int, bx: int, by: int) -> Tuple[int, int]:
    """Calcule les coordonnées LRS2 globales d'un bloc."""
    lrs_x = tx * 4 + bx
    lrs_y = ty * 4 + by
    return lrs_x, lrs_y
```

**⚠️ CORRECTION AUDIT PRINCIPAL** :
- **Audit initial FAUX** : `lrs2_x = tx * 16 + bx` (16 blocs par tuile)
- **Code réel** : `lrs2_x = tx * 4 + bx` (**4 blocs par tuile**)

---

### 1.2 Conversion tuile → Tile ID

**Fichiers multiples** :
- `clean_weights.py:385` : `tile_id = ty * 32 + tx`
- `clean_weights.py:702` : `tile_id = ty * 32 + tx`
- `clean_weights.py:882` : `tile_id = ty * 32 + tx`
- `clean_weights.py:996` : `tile_id = ty * 32 + tx`
- `clean_weights.py:1272` : `tile_id = ty * 32 + tx`
- `clean_weights.py:1448` : `tile_id = ty * 32 + tx`
- `tile_inspector.py:126` : `tile_id_n = (ty - 1) * 32 + tx`
- `tile_inspector.py:134` : `tile_id_s = (ty + 1) * 32 + tx`
- `tile_inspector.py:142` : `tile_id_e = ty * 32 + (tx + 1)`
- `tile_inspector.py:150` : `tile_id_o = ty * 32 + (tx - 1)`

**Formule** : `tid = ty * 32 + tx` (**32 tuiles par côté**)

---

### 1.3 Constantes hardcodées ou lues depuis project.json ?

**Analyse du code** :

#### Constante `4` (blocs par tuile)
- **Hardcodée** dans `tile_inspector.py:55` et `clean_weights.py:138`
- ❌ **Non lue** depuis `project.json`

#### Constante `32` (tuiles par côté)
- **Hardcodée** dans tous les fichiers (voir liste ci-dessus)
- ❌ **Non lue** depuis `project.json`

**⚠️ CONSÉQUENCE** :
- Les scripts `tile_inspector.py` et `clean_weights.py` fonctionnent **uniquement** pour :
  - Grille **32×32 tuiles** (Zimnitrita, ZBK)
  - **4 blocs par tuile** (convention Reforger `num_blk=4`)
- **Incompatible** avec projets custom ayant :
  - Grille différente (ex: 16×16, 64×64)
  - Blocs différents (ex: 8×8, 16×16)

**Valeurs dans project.json Zimnitrita** :
```json
{
  "reforger_grid": {
    "tiles": [32, 32],     ← grid_w = 32
    "blocks_per_tile": [4, 4],  ← num_blk = 4
    "planar_resolution": 4
  }
}
```

**RECOMMANDATION** : Lire `grid_w` et `num_blk` depuis `project.json` au lieu de hardcoder

---

### 1.4 Zimnitrita vs ZBK

**Zimnitrita** :
- Grille : 32×32 tuiles
- Blocs : 4×4 par tuile
- Total blocs : 32 * 4 = **128 blocs par côté** (LRS2 0-127)

**ZBK** (si grille 64×64 tuiles) :
- Grille : 64×64 tuiles
- Blocs : 4×4 par tuile
- Total blocs : 64 * 4 = **256 blocs par côté** (LRS2 0-255)

**⚠️ DIVERGENCE POTENTIELLE** :
Si ZBK utilise grille 64×64, les scripts actuels (hardcodés 32) sont **incompatibles**.

---

## 2. CORRECTION verify_inspect_names.py

### 2.1 Problème identifié

**Audit initial** : Le script utilise `read_mats_from_terr()` qui lit le .terr **indirectement** via :
1. Lecture `project.json` → chemin `.terr`
2. Fonction `read_mats_from_terr()` (partagée avec Inspect tuile)
3. Construction table ID→Nom

**⚠️ PROBLÈME** : La colonne de référence doit lire **DIRECTEMENT** le chunk MATS du `.terr`, **sans fonction partagée** avec Inspect tuile.

---

### 2.2 Script corrigé

**Nouvelle fonction** : `read_mats_from_terr_direct(terr_path)`

**Implémentation** :
```python
def read_mats_from_terr_direct(terr_path: Path) -> Dict[int, str]:
    """
    Lit DIRECTEMENT le chunk MATS du .terr (XML) sans fonction partagée.
    
    Returns:
        Dict {ID: Nom matériau}
    """
    import xml.etree.ElementTree as ET
    
    if not terr_path.exists():
        raise FileNotFoundError(f".terr introuvable : {terr_path}")
    
    tree = ET.parse(terr_path)
    root = tree.getroot()
    
    id_to_name = {}
    
    # Chercher section <Surfaces>
    surfaces = root.find(".//Surfaces")
    if surfaces is None:
        raise ValueError(f"Section <Surfaces> absente du .terr : {terr_path}")
    
    # Parcourir <Surface Name="..." Id="..." />
    for surface in surfaces.findall("Surface"):
        name = surface.get("Name")
        id_str = surface.get("Id")
        
        if name and id_str:
            try:
                mat_id = int(id_str)
                id_to_name[mat_id] = name
            except ValueError:
                print(f"[WARN] ID invalide ignoré : {id_str} ({name})")
    
    return id_to_name
```

**Modification du script** :
- **Ligne ~85** : Remplacer `load_terr_table()` par `read_mats_from_terr_direct()`
- **Suppression** : Fonction `read_mats_from_terr()` importée (ligne ~9)
- **Ajout** : Fonction `read_mats_from_terr_direct()` standalone

**Justification** :
- Lecture **directe** du XML .terr (chunk MATS)
- **Indépendante** de `terrain_terr_reader.py` (fonction partagée avec Inspect tuile)
- Garantit que la colonne de référence est **totalement indépendante**

---

## 3. SOURCES DONNÉES DANS clean_weights.py --inspect

### 3.1 Chaîne complète

**Fichier** : `clean_weights.py:364-513`

#### Étape 1 : Lecture IDs matériaux (LRS2 .ttile)

**Ligne 398** :
```python
lrs2_blocks = read_lrs2_from_ttile(ttile_path)
# lrs2_blocks : dict {(bx, by): ([mat_id0, mat_id1, ...], ...)}
```

**Source** : `.Data/Terrain_{tid}.ttile` (chunk LRS2)

**Fonction** : `lrs2_parser.load_lrs2_from_ttile()`

**Structure LRS2** :
```python
{
  (0, 0): ([123, 45, 0, 0, 0, 0, 0, 0], ...),  # Bloc (0,0) : 8 slots, IDs matériaux
  (0, 1): ([67, 89, 12, 0, 0, 0, 0, 0], ...),
  ...
}
```

---

#### Étape 2 : Lecture poids (_layer.dds)

**Ligne 404** :
```python
pixels = read_layer_dds(layer_path)
# pixels : np.ndarray shape (512, 512, 8) dtype float32
```

**Source** : `.EditorData/Terrain_{tid}_layer.dds` ou `.Data/Terrain_{tid}_layer.edds`

**Fonction** : `read_layer_dds()` (ligne 104-133)

**Structure poids** :
- **Dimensions** : (512, 512, 8)
  - 512×512 pixels (33 vertices × 4 blocs = 132 vertices par tuile, interpolé 512)
  - 8 canaux (w0, w1, w2, w3, w4, w5, w6, w7)
- **Valeurs** : float32 (0.0 - 1.0)
  - 0.0 = poids nul
  - 1.0 = poids maximal (255 en uint8)

**⚠️ NOTE** : Le fichier est `_layer.dds` (DDS non compressé) ou `_layer.edds` (EDDS compressé).

**Recherche fichier** (ligne 387) :
```python
layer_path = find_layer_path(tile_id, data_dir, editor_data_dir)
# Cherche dans :
# 1. .EditorData/Terrain_{tid}_layer.dds
# 2. .Data/Terrain_{tid}_layer.edds
```

---

#### Étape 3 : Conversion ID → Nom via surfaces

**Ligne 495-511** :
```python
block_val = lrs2_blocks.get((bx, by))
mat_ids = block_val[0] if block_val else []  # IDs depuis LRS2

for i, mat_id in enumerate(mat_ids):
    if mat_id < len(surfaces):
        _s = surfaces[mat_id]
        mat_name = (_s.get("emat", _s.get("name", str(mat_id))) 
                    if isinstance(_s, dict) else str(_s))[:12]
    else:
        mat_name = f"MAT_{mat_id}"
```

**Source noms** : Paramètre `surfaces` (passé par l'appelant)

**Provenance** :
- **Mode exe** : `surfaces.json` chargé dans `main.py` → passé à `mode_inspect()`
- **Mode dev** : `surfaces.json` chargé par CLI argument

**Fallback** : Si ID absent de `surfaces`, affichage `"MAT_{mat_id}"`

---

### 3.2 Deux sources distinctes

| Donnée | Source fichier | Format | Fonction lecture |
|--------|----------------|--------|------------------|
| **IDs matériaux** | `.Data/Terrain_{tid}.ttile` | Chunk LRS2 (binaire) | `load_lrs2_from_ttile()` |
| **Poids par slot** | `.EditorData/Terrain_{tid}_layer.dds` | DDS 512×512×8 (float32) | `read_layer_dds()` |
| **Noms matériaux** | `surfaces.json` (paramètre) | JSON | Passé par appelant |

**⚠️ INCOHÉRENCE POSSIBLE** : Nombre de slots

**Scénario** :
1. LRS2 dit : Bloc (0,0) a **6 slots actifs** (IDs : [123, 45, 67, 89, 12, 34, 0, 0])
2. _layer.dds dit : **8 canaux** (w0-w7), dont w6 et w7 = 0.0

**Vérification dans le script** :
```python
# Ligne 501 : Lecture poids pour len(mat_ids) slots
block_pixels = pixels[y0:y0+128, x0:x0+128, :len(mat_ids)]
```

**Comportement** :
- Si LRS2 dit 6 slots → lecture w0-w5 seulement
- Si _layer.dds a w6 et w7 non nuls → **ignorés silencieusement**

**RECOMMANDATION verify_inspect_names.py** :
Ajouter colonne "Nombre slots" :
```
Bloc LRS2 | Noms surfaces.json | Noms .terr | Slots LRS2 | Slots _layer | Incohérence
(256,256) | Grass_03, Dirt_02  | Idem       | 6          | 8            | ⚠️ +2 slots DDS
```

---

## 4. TABLEAU SCRIPTS EXTERNES COMPLET

### 4.1 Modes clean_weights.py

| Mode | Lecture/Écriture | Appelé par UI | Arguments | Fichiers modifiés |
|------|------------------|---------------|-----------|-------------------|
| `--scan` | **R** | Corrections › SCAN GLOBAL | `--scan {threshold}` | ❌ Aucun |
| `--scan-zone` | **R** | Corrections › SCAN ZONE | `--scan-zone {mask_path}` | ❌ Aucun |
| `--inspect` | **R+W** | Inspection › INSPECT TUILE, Corrections › INSPECT TUILE | `--inspect {tx},{ty}` | ✅ `outputs/generated/tiles/tile_{tx}_{ty}_cleanup.png` |
| `--weights` | **R** | Corrections › INSPECT TUILE | `--weights {tx},{ty}` | ❌ Aucun (log uniquement) |
| `--validate` | **R** | Corrections › INSPECT TUILE | `--validate {tx},{ty}` | ❌ Aucun (log uniquement) |
| `--clean` | **R+W** | ❌ Non exposé UI | `--clean {lrs2_coords}` | ✅ `.EditorData/Terrain_{tid}_layer.dds` |
| `--clean-all` | **R+W** | ❌ Non exposé UI | `--clean-all {threshold} [--pass N]` | ✅ `.EditorData/Terrain_*_layer.dds` (tous) |
| `--clean-zone` | **R+W** | ❌ Non exposé UI | `--clean-zone {mask_path}` | ✅ `.EditorData/Terrain_*_layer.dds` (zone) |
| `--force-mat` | **R+W** | ❌ Non exposé UI | `--force-mat {lrs2_coords} {mat_id}` | ✅ `.Data/Terrain_*.ttile` (LRS2) + `.EditorData/*_layer.dds` |
| `--reset-zone` | **R+W** | ❌ Non exposé UI | `--reset-zone {mask_path}` | ✅ `.EditorData/Terrain_*_layer.dds` (zone → w0=1.0, w1-w7=0.0) |

---

### 4.2 Modes tile_inspector.py

| Mode | Lecture/Écriture | Appelé par UI | Arguments | Fichiers modifiés |
|------|------------------|---------------|-----------|-------------------|
| `--export-json` | **R+W** | Inspection › SCAN GLOBAL | `--tiles-dir {data_dir} --export-json {cache_json}` | ✅ `outputs/cache/qtre_scan.json` |
| Mode direct (import) | **R** | Inspection › SCAN GLOBAL (mode exe) | `export_json(data_dir, cache_json)` | ✅ `outputs/cache/qtre_scan.json` |

---

### 4.3 Autres scripts

**Recherche dans le projet** :
- ❌ `merge_mat.py` : **Introuvable**
- ❌ `ttile_manager.py` : **Introuvable**
- ❌ `scan_ttile.py` : **Introuvable**

**Conclusion** : Ces scripts n'existent pas dans le projet actuel (ou renommés/fusionnés).

---

### 4.4 Modes en écriture NON exposés dans l'UI

**⚠️ IMPORTANT** : Les modes suivants existent dans `clean_weights.py` mais **aucun bouton** dans `corrections.html` ou `inspection.html` :

1. `--clean` : Nettoie slots négligeables (blocs spécifiques)
2. `--clean-all` : Nettoie slots négligeables (tous blocs, multi-pass)
3. `--clean-zone` : Nettoie slots négligeables (zone masque)
4. `--force-mat` : Force un matériau sur blocs spécifiques
5. `--reset-zone` : Reset zone masque (w0=100%, w1-w7=0%)

**Utilisation** : CLI uniquement (pas d'UI)

**Exemple** :
```bash
python clean_weights.py --clean-all 0.01 --pass 3
python clean_weights.py --force-mat "64,64 65,65" 123
python clean_weights.py --reset-zone "H:/mask.png"
```

---

## 5. TRAITEMENT DU w0 IMPLICITE DANS INSPECT TUILE

### 5.1 Convention Reforger w0

**w0** : Matériau de base (background)
- **Toujours présent** dans LRS2 (premier slot)
- **Poids implicite** : `w0 = 1.0 - sum(w1..w7)`

**Exemple** :
```
Bloc (0,0) LRS2 : IDs = [123, 45, 67, 0, 0, 0, 0, 0]
Poids _layer.dds : w0=0.0, w1=0.4, w2=0.3, w3=0.3, w4-w7=0.0

Calcul implicite :
  w0_implicite = 1.0 - (0.4 + 0.3 + 0.3) = 0.0

Affichage :
  Grass_03 (ID 123) : 0.0%    ← w0 implicite = 0%
  Dirt_02 (ID 45)   : 40%     ← w1
  Forest_01 (ID 67) : 30%     ← w2
```

---

### 5.2 Code Inspect tuile (clean_weights.py)

**Ligne 495-497** :
```python
block_val = lrs2_blocks.get((bx, by))
mat_ids = block_val[0] if block_val else []
```

**Ligne 507-511** :
```python
for i, mat_id in enumerate(mat_ids):
    if mat_id < len(surfaces):
        _s = surfaces[mat_id]
        mat_name = (_s.get("emat", _s.get("name", str(mat_id))) 
                    if isinstance(_s, dict) else str(_s))[:12]
    else:
        mat_name = f"MAT_{mat_id}"
```

**Comportement** :
- **i=0** : Slot w0, `mat_id` = premier ID LRS2 (ex: 123)
- **Nom affiché** : `surfaces[123]` → `"Grass_03"`

---

### 5.3 Quel nom affiché pour w0 ?

**Réponse** : **Nom du premier ID LRS2** (mat_ids[0])

**Exemple concret** :
```
Bloc (0,0) :
  LRS2 IDs : [123, 45, 67, 0, 0, 0, 0, 0]
  surfaces[123] = "Grass_03"
  surfaces[45] = "Dirt_02"
  surfaces[67] = "Forest_Deciduous_01"

Affichage Inspect tuile :
  Grass_03 (w0) : 0%
  Dirt_02 (w1) : 40%
  Forest_Deciduous_01 (w2) : 30%
```

**⚠️ CAS w0 = 0 dans LRS2** :
Si `mat_ids[0] = 0` (ID vide) :
- **Nom affiché** : `"MAT_0"` (fallback ligne 511)

**⚠️ CAS w0 absent de surfaces.json** :
Si `mat_ids[0] = 999` et `999 >= len(surfaces)` :
- **Nom affiché** : `"MAT_999"` (fallback ligne 511)

---

### 5.4 Poids w0 implicite

**Calcul** : Ligne 513-522
```python
# Coverage : % de pixels où weight > 0
if i < block_pixels.shape[2]:
    weights = block_pixels[:, :, i]
    coverage = (weights > 0.001).sum() / pixel_count * 100
else:
    coverage = 0
```

**Pour w0** :
- **i=0** → lecture `block_pixels[:, :, 0]` (canal w0 de _layer.dds)
- **Pas de calcul implicite** : Lecture directe du fichier DDS

**⚠️ DIVERGENCE POSSIBLE** :
Si _layer.dds stocke w0=0.0 (fichier corrompu ou reset), l'affichage sera :
```
Grass_03 (w0) : 0%   ← Devrait être 100% - sum(autres)
```

**RECOMMANDATION** :
Ajouter vérification somme poids :
```python
total_weight = sum(coverage for all slots)
if abs(total_weight - 100.0) > 1.0:
    print(f"⚠️ WARNING: Somme poids bloc ({bx},{by}) = {total_weight:.1f}% (attendu 100%)")
```

---

## CONCLUSION COMPLÉMENTS

### Corrections principales

1. **Formule LRS2** : `tx * 4 + bx` (pas 16) — **4 blocs par tuile hardcodé**
2. **Constantes** : 32 tuiles/côté et 4 blocs/tuile **hardcodées**, pas lues depuis project.json
3. **verify_inspect_names.py** : Doit lire `.terr` **directement** (XML chunk MATS), pas via fonction partagée
4. **Sources clean_weights --inspect** :
   - IDs : `.ttile` LRS2
   - Poids : `_layer.dds` (pas .edds)
   - Noms : `surfaces.json` (paramètre)
5. **Modes en écriture** : 5 modes CLI non exposés UI (--clean, --clean-all, --clean-zone, --force-mat, --reset-zone)
6. **Traitement w0** : Nom = surfaces[mat_ids[0]], poids lu directement (pas calculé implicite)

### Recommandations

1. Lire `grid_w` et `num_blk` depuis `project.json` au lieu de hardcoder
2. verify_inspect_names.py : Implémenter `read_mats_from_terr_direct()` (XML standalone)
3. Ajouter vérification somme poids (doit = 100%)
4. Ajouter colonne "Nombre slots LRS2 vs DDS" dans script vérification

