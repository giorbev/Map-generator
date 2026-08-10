# Format Layer.edds — Masques de splatting GPU

## Vue d'ensemble

Pour chaque tuile de terrain `Terrain_N`, Reforger génère 4 fichiers :

| Fichier | Format | Taille | Rôle |
|---------|--------|--------|------|
| `Terrain_N.ttile` | IFF TERR | Variable | **Source éditeur** : heightmap, QTRE, végétation, LRS2 |
| `Terrain_N_layer.edds` | R32_UINT | 512×512 | **Masques GPU** : poids des matériaux par texel (0-7 mats) |
| `Terrain_N_supertexture.edds` | BC7 sRGB | 512×512 | **Satmap baked** : couleur finale du sol |
| `Terrain_N_normal.edds` | BC7 | 256×256 | **Normal map** : relief pour éclairage LOD |

**Pipeline de données** :
```
World Editor → QTRE (.ttile) → Baking → layer.edds (poids) + supertexture (couleurs)
                                              ↓
                                        Shader terrain (runtime)
```

---

## 🎯 Pourquoi utiliser `layer.edds` ?

### ✅ Avantages vs QTRE
- **Tous les matériaux** : supporte 1-7 textures sans trous (vs QTRE qui manque 6-7)
- **Poids continus** : valeurs 0-31 par matériau (vs QTRE avec zones "pure" ou "blend")
- **Simple** : 1 uint32 par texel (vs quadtree avec cas particuliers)
- **Exact** : c'est ce que le moteur utilise réellement à l'écran

### ❌ Inconvénients
- Nécessite le baking Workbench (génération des `.edds`)
- Fichiers binaires (pas éditables à la main)

---

## 🔧 Format EDDS (conteneur)

### Structure générale
```
[Header DDS standard 128 bytes]  ← DDS + DX10, marqueur "ENF1"
[Table mips]                     ← mipcount × (fourcc + u32 taille)
[Blobs données]                  ← du PLUS PETIT au PLUS GRAND mip
```

### Ordre des mips
**⚠️ INVERSION** : EDDS stocke du **petit → grand** (inverse de DDS standard)

| Mip | Taille | Ordre EDDS | Ordre DDS standard |
|-----|--------|------------|-------------------|
| 0 | 512×512 | #9 (dernier) | #0 (premier) |
| 1 | 256×256 | #8 | #1 |
| ... | ... | ... | ... |
| 9 | 1×1 | #0 (premier) | #9 (dernier) |

### Compression des blobs
Deux types par mip :
- **COPY** : données brutes (non compressé)
- **LZ4** : compression par tranches de 64 Ko chaînées
  ```
  [u32 taille_décompressée_totale]
  [u32 taille_compressée | flag_bit31][données LZ4] ← 64 Ko max
  [u32 taille_compressée][données LZ4]              ← 64 Ko max
  ...
  ```

**Décodage LZ4** : chaque tranche utilise les 64 Ko précédents comme dictionnaire

---

## 🔍 Format .edds natif Workbench — Analyse détaillée

### Structure générale
```
[Header DDS 128 bytes]
[Table mips : mipcount × 8 bytes (4 FourCC + 4 taille)]
[Blobs données : du plus petit au plus grand mip]
```

### Spécifications observées

**Marqueur ENF1** : Présent dans le header DDS (bytes 32-52)

**Table offset** : Dépend de la résolution de la tuile, pas du nom de la map
- **Table offset = 128** : Maps avec tuiles layer 128×128 pixels
  - Format mips : COPY (données brutes, pas de LZ4)
  - Exemple : Eden
- **Table offset = 148** : Maps avec tuiles layer 512×512 pixels
  - Format mips : LZ4 chaîné (compression avec dictionnaire)
  - Exemple : Zimnitrita

**Détection automatique** : Fonction `_detect_table_offset()` dans `edds_decoder.py`
- Teste 148 EN PREMIER (priorité maps modernes)
- Vérifie TOUS les mips (pas seulement 3)
- Vérifie que chaque size ≤ len(data)
- Fallback = 148 (Zimnitrita par défaut)

### Table des mips

**Pour maps 512×512 (table_offset=148, Zimnitrita)** :

| Mip | FourCC | Résolution | Size (bytes) | Format |
|-----|--------|------------|--------------|--------|
| 0 | COPY | 1×1 | 4 | Zéro brut |
| 1 | COPY | 2×2 | 16 | Zéros bruts |
| 2 | LZ4 | 4×4 | 19 | Zéros compressés LZ4 |
| 3 | LZ4 | 8×8 | 19 | Zéros compressés LZ4 |
| 4 | LZ4 | 16×16 | 22 | Zéros compressés LZ4 |
| 5 | LZ4 | 32×32 | 34 | Zéros compressés LZ4 |
| 6 | LZ4 | 64×64 | 83 | Zéros compressés LZ4 |
| 7 | LZ4 | 128×128 | 275 | Zéros compressés LZ4 |
| 8 | LZ4 | 256×256 | 1085 | Zéros compressés LZ4 |
| 9 | LZ4 | 512×512 | Variable | **Données réelles** LZ4 chaîné |

**Pour maps 128×128 (table_offset=128, Eden)** :

| Mip | FourCC | Résolution | Size (bytes) | Format |
|-----|--------|------------|--------------|--------|
| 0..N | COPY | 1×1 → 128×128 | Variable | Données brutes (pas de LZ4) |
| Principal | COPY | 128×128 | 65536 | 128×128×4 bytes bruts |

### Compression LZ4 chaînée

**Paramètres** :
- **Chunk size** : 65536 bytes (64 Ko)
- **Format blob** : `[u32 total_size][u32 comp_size][data]×N`

**Algorithme de chaînage** :
- `chunk[0]` : compressé **sans dictionnaire**
- `chunk[1..N]` : compressé **avec dictionnaire** = les 65536 bytes décompressés du chunk précédent

**Preuve expérimentale** :
- ✅ `chunk[0]` décompresse sans dict (OK)
- ❌ `chunk[1]` échoue sans dict (error code 5)
- ✅ `chunk[1]` décompresse UNIQUEMENT avec dict=chunk[0] décompressé

**Source de validation** : Analyse de `ZBK_terrain_3560_layer.edds` (map native Workbench)

**Conséquence critique** :
> **Tous les fichiers .edds natifs Workbench utilisent le dictionnaire chaîné LZ4.**  
> **Tout fichier écrit sans dict sera rejeté par Reforger.**

### 🔍 Algorithme de détection format

**Implémentation** : `_detect_table_offset()` dans `edds_decoder.py`

```python
def _detect_table_offset(data: bytes, mipcount: int) -> int:
    # 1. Tester 148 EN PREMIER (maps modernes 512×512)
    # 2. Tester 128 en second (maps legacy 128×128)
    # 3. Autres offsets (136, 140, 144, 152)
    
    for candidate in [148, 128, 136, 140, 144, 152]:
        # Vérifier longueur suffisante
        if len(data) < candidate + mipcount * 8:
            continue
        
        valid = True
        # Vérifier TOUS les mips (pas seulement 3)
        for i in range(mipcount):
            off = candidate + i * 8
            fourcc = data[off:off+4]
            
            # FourCC valide ?
            if fourcc not in {b'COPY', b'LZ4 ', b'LZB4', b'LZ4B'}:
                valid = False
                break
            
            # Taille cohérente ?
            sz = struct.unpack_from('<I', data, off + 4)[0]
            if sz > len(data):  # Taille absurde
                valid = False
                break
        
        if valid:
            return candidate
    
    return 148  # Fallback Zimnitrita (pas 128)
```

**Raisons de la priorité 148** :
1. Maps modernes (Zimnitrita, Arland) utilisent 512×512
2. Évite faux positifs sur maps avec header non-standard
3. Fallback cohérent avec format le plus courant

---

### ⚠️ Règle absolue pour l'encodage

**Conséquences pour l'encodage** :
```python
# ❌ FAUX — Rejeté par Reforger
for chunk in chunks:
    compressed = lz4.compress(chunk)

# ✅ CORRECT — Accepté par Reforger
prev_chunk = None
for chunk in chunks:
    if prev_chunk is None:
        compressed = lz4.compress(chunk)
    else:
        compressed = lz4.compress(chunk, dict=prev_chunk)
    prev_chunk = chunk  # Sauvegarder pour le suivant
```

---

## 🎨 Format `layer.edds` (masques)

### Spécifications
```
Format  : R32_UINT (32 bits par pixel)
Taille  : 512×512 pixels
Mips    : 10 niveaux (512→1)
Couverture : 512 px / tuile ≈ 1 texel par mètre de terrain
```

### Encodage d'un texel (uint32)

**6 champs de 5 bits** encodant les poids w1 à w6 :
```
Bits    : 31-30 | 29-25 | 24-20 | 19-15 | 14-10 | 9-5  | 4-0
Valeur  : 00    | w6    | w5    | w4    | w3    | w2   | w1
```

**Poids w0** (premier matériau) **IMPLICITE** :
```python
w0 = 31 - (w1 + w2 + w3 + w4 + w5 + w6)
```

**Contraintes vérifiées** :
- Bits 30-31 toujours `00`
- Σ(w0..w6) = 31 (vérifié 100% des texels)
- Chaque poids ∈ [0, 31]

### Exemples
```python
# Texel = 0x00000000 (tous bits à 0)
w1=0, w2=0, w3=0, w4=0, w5=0, w6=0
→ w0 = 31 - 0 = 31
→ 100% du premier matériau

# Texel = 0x0000000A (w1=10, reste=0)
w1=10, w2=0, w3=0, w4=0, w5=0, w6=0
→ w0 = 31 - 10 = 21
→ 67.7% mat0, 32.3% mat1

# Texel = 0x02108421 (tous non-nuls)
w1 = (0x02108421 >> 0) & 0x1F = 1
w2 = (0x02108421 >> 5) & 0x1F = 2
w3 = (0x02108421 >> 10) & 0x1F = 4
w4 = (0x02108421 >> 15) & 0x1F = 8
w5 = (0x02108421 >> 20) & 0x1F = 16
w6 = (0x02108421 >> 25) & 0x1F = 0
→ w0 = 31 - (1+2+4+8+16) = 0
→ 0% mat0, 3.2% mat1, 6.5% mat2, 12.9% mat3, 25.8% mat4, 51.6% mat5
```

---

## 🗺️ Chunk LRS2 (liste matériaux par bloc)

### Localisation
**Fichier** : `Terrain_N.ttile` (IFF TERR)  
**Chunk** : `LRS2` (Layer Resources v2)

### Structure
```python
# Pour une tuile 4×4 blocs = 16 enregistrements
for i in range(16):
    u32 index       # (by << 7) | bx → identifie le bloc
    u16 n           # Nombre de matériaux (1-7)
    u16[n] ids      # IDs globaux des surfaces
```

**Exemple bloc (2, 1)** :
```
index = (1 << 7) | 2 = 130
n = 7
ids = [1, 2, 8, 9, 16, 55, 57]
```

### ⚠️ Différence avec QTRE

**LRS2 ≠ BMAT** (vérifié !) :
- **LRS2** : liste réelle utilisée par le GPU (`layer.edds`)
- **BMAT** : liste source éditeur (peut différer après optimisation)

**→ Toujours utiliser LRS2 pour décoder `layer.edds` !**

---

## 🚀 Pipeline de décodage complet

### Étape 1 : Charger les tuiles
```python
data_dir = Path("World/Zimnitrita/Terrain/.Data")

for tuile_id in range(1024):  # 32×32 tuiles
    ttile = data_dir / f"Terrain_{tuile_id}.ttile"
    layer = data_dir / f"Terrain_{tuile_id}_layer.edds"
```

### Étape 2 : Parser LRS2
```python
# Extraire chunk LRS2 du .ttile
lrs2_data = extract_chunk(ttile, "LRS2")

# Parser 16 enregistrements
lrs2_blocks = {}
for i in range(16):
    index = read_u32(lrs2_data, pos)
    bx = index & 0x7F
    by = (index >> 7) & 0x7F
    n = read_u16(lrs2_data, pos+4)
    ids = [read_u16(lrs2_data, pos+6+j*2) for j in range(n)]
    lrs2_blocks[(bx, by)] = ids
    pos += 6 + n*2
```

### Étape 3 : Décoder layer.edds
```python
# Charger la texture 512×512 R32_UINT
layer_data = decode_edds(layer)  # Mip 0 = 512×512

# Pour chaque pixel (x, y)
pixel_value = layer_data[y, x]  # uint32

# Extraire les 6 poids
weights = []
for i in range(6):
    w = (pixel_value >> (5 * i)) & 0x1F
    weights.append(w)

# Calculer w0 implicite
w0 = 31 - sum(weights)
weights.insert(0, w0)

# Identifier le bloc (4×4 grille de 128×128 px)
bx = x // 128
by = y // 128
mat_ids = lrs2_blocks[(bx, by)]

# Normaliser poids → [0, 1]
weights_norm = [w / 31.0 for w in weights[:len(mat_ids)]]
```

### Étape 4 : Composer couleur
```python
# Couleur unie (preview rapide)
color = sum(w * COLOR_MAP[mat_id] for w, mat_id in zip(weights_norm, mat_ids))

# OU texture réaliste
color = sum(w * sample_texture(mat_id, uv) for w, mat_id in zip(weights_norm, mat_ids))
```

### Étape 5 : Assembler satmap
```python
# Grille 32×32 tuiles × 512 px = 16384×16384
satmap = np.zeros((16384, 16384, 3), dtype=np.uint8)

for tuile_id, (tx, ty) in enumerate(tuile_positions):
    # Décoder tuile → 512×512 RGB
    tile_img = process_tile(tuile_id)
    
    # Placer dans la grille
    satmap[ty*512:(ty+1)*512, tx*512:(tx+1)*512] = tile_img

# Downscale 16k → 4k
satmap_4k = cv2.resize(satmap, (4097, 4097))
```

---

## 📊 Comparaison QTRE vs Layer

| Critère | QTRE (TMAT/BMAT) | Layer.edds |
|---------|------------------|------------|
| **Couverture** | ❌ Manque blocs 6-7 tex (6.4%) | ✅ Tous les blocs (100%) |
| **Précision** | Variable (quadtree) | Fixe (512×512) |
| **Complexité** | 🔴 Haute (3 formats) | 🟢 Basse (1 format) |
| **Rapidité** | 🟡 Moyenne | 🟢 Rapide (vectorisé) |
| **Dépendance** | ✅ Toujours présent | ⚠️ Nécessite baking |

**→ Recommandation** : Utiliser `layer.edds` + `LRS2` pour qualité maximale !

---

## 🐛 Problèmes résolus

### ❌ Problème ancien (QTRE)
- 1058 blocs (6.4%) avec 6-7 textures → **pas de données QTRE**
- Rendu : première texture 100% → **très grossier**

### ✅ Solution (Layer.edds)
- Tous les blocs décodés → **0% de perte**
- Poids exacts → **qualité Workbench**

---

## 📚 Références

- **Format EDDS** : [Enfusion DDS](https://community.bistudio.com/wiki/Enfusion_Engine)
- **Compression LZ4** : [LZ4 spec](https://github.com/lz4/lz4)
- **Chunk LRS2** : Reverse-engineering (juin 2026)
- **Terrain splatting** : [GPU Gems 3 - Chapter 1](https://developer.nvidia.com/gpugems/GPUGems3/gpugems3_ch01.html)

---

## 🔬 Découverte format .ttile — Structure GCTD + TMAT (août 2026)

### Constat fondamental

**Workbench ne modifie pas le .edds lors d'une modification de texture dans le Terrain Editor.** Les données de texture sont entièrement dans le `.ttile`. Le problème LZ4 du `.edds` était un faux problème — tout peut s'écrire directement dans le `.ttile` (format IFF big-endian, sans compression).

### Structure du .ttile

```
FORM > TERR > VERS > HGHT (33282b) > BERR (576b) > GCTD (30452b) > LRS2 (208b) > TMAT (20404b)
```

**Chunks modifiés par Workbench lors d'une modif texture** : `GCTD` + `TMAT` + `LRS2`

**Chunks jamais touchés** : `HGHT`, `BERR`

---

### LRS2 — Table des matériaux par bloc

**Format** : liste d'entrées, une par bloc actif

```
index (uint32 LE) | count (uint16 LE) | mat_ids[count] (uint16 LE chacun)
```

- **index** = coordonnées globales encodées : `bx | (by << 7)`
- **mat_ids** = IDs globaux des matériaux présents sur le bloc (depuis `terrain.terr`)
- C'est la **liste locale du bloc** — les indices 0, 1, 2... dans cette liste correspondent aux **index locaux** utilisés dans `GCTD`

**Exemple bloc (34,79)** :
- **Before** : `[2, 3, 8]` = `[Dirt_01, Grass_03, Rock_01]`
- **After** : `[2, 3, 26]` = `[Dirt_01, Grass_03, ForestConiferous_01_Base]`

---

### GCTD — Poids de texture par pixel

**Taille** : 30452 bytes = header 6 bytes + sections de 2030 bytes par bloc actif

**Structure d'une section** :
```
[02 02 02 02] [bx uint16 LE] [by uint16 LE] [2022 bytes de données]
```

- Les 4 premiers bytes sont du padding `0x02`
- `bx`, `by` = coordonnées globales du bloc
- Les 2022 bytes = **index local du matériau**, un byte par pixel (128×128 = 16384 pixels... à confirmer, probablement RLE ou bitmap compressé)

**Valeur dans GCTD = index local dans la liste LRS2 du bloc** :
```
0x00 = matériau local 0 (ex: Dirt_01)
0x01 = matériau local 1 (ex: Grass_03)
0x02 = matériau local 2 (ex: Rock_01)
```

**Exemple** : avant modif, les 2022 bytes du bloc (34,79) contiennent `0x02` (= Rock_01). Après modif en ForestConiferous, ils contiennent `0x01` (= ForestConiferous, qui est passé à l'index 2 → après renumérotation locale il est index 1 dans la nouvelle liste `[Dirt_01, Grass_03, ForestConiferous]`).

---

### TMAT — Métadonnées de matériaux par tuile

Contient 16 sous-chunks `BMAT`. Le premier `BMAT` est la table locale complète de la tuile (toutes textures utilisées). Les autres `BMAT` contiennent des données de poids/blending supplémentaires. **Workbench le met à jour lors de chaque modification.**

---

### Workflow d'écriture directe (à implémenter)

Pour changer un matériau sur un bloc donné **sans passer par Workbench** :

1. **Modifier LRS2** : remplacer l'ancien ID global par le nouveau dans la liste du bloc cible
2. **Modifier GCTD** : dans la section du bloc cible, remplacer les bytes de l'ancien index local par le nouvel index local
3. **Mettre à jour TMAT** : régénérer ou patcher les entrées `BMAT` concernées
4. **Le .edds n'est pas à toucher**

**Fichiers concernés** :
- `.Data/Terrain_NNN.ttile` — **source de vérité pour les textures**
- `.EditorData/Terrain_NNN_layer.edds` — cache visuel uniquement, ignoré par ce workflow

---

### Supertexture et Normal — Outputs en lecture seule

#### Terrain_NNN_supertexture.edds — 512×512, BC7_UNORM (DXGI 99)

**Rôle** : Texture de surface rendue (couleur finale du sol après baking)

**Structure des pixel data** :
```
[10 × chunk COPY]  → table des offsets/tailles des mip levels
[LZ4 chunk mip0]   → payload compressé LZ4 non chaîné
[LZ4 chunk mip1]   → ...
...
```

Les **10 premiers chunks COPY** (format `COPY | size uint32`) correspondent aux 10 mip levels déclarés dans le header DDS. Les tailles sont **16, 16, 16, 64, 256, 1024, 4096, 16384, 65536, 262144 bytes** — exactement les mip levels BC7 de 512×512 à 1×1.

Puis viennent les vrais chunks **LZ4 ` `** (avec espace) qui contiennent les données compressées.

#### Terrain_NNN_normal.edds — 256×256, BC7_UNORM_SRGB (DXGI 98)

**Rôle** : Normal map du terrain (relief pour éclairage LOD distant)

**Structure** : Même structure, 9 mip levels, résolution moitié (256×256 → 1×1)

---

### ⚠️ Conclusion importante sur l'écriture directe

**Ces deux fichiers sont des textures BC7 compressées GPU, générées automatiquement par Workbench à partir des données de surface.**

- **Outputs en lecture seule** : Workbench les régénère après chaque Save
- **On n'a pas à les toucher pour l'écriture directe**
- **Seul le `.ttile` (GCTD + LRS2 + TMAT) est la source de vérité**

**Pipeline réel** :
```
[Modification GCTD/LRS2/TMAT dans .ttile]
           ↓
    [Save Workbench]
           ↓
[Workbench régénère automatiquement supertexture.edds + normal.edds]
```

**→ Pour l'écriture directe, focus sur `.ttile` uniquement !**

---

## 📁 Hiérarchie complète des fichiers terrain — Découverte EditorData (août 2026)

### Terrain_NNN.bterr — Heightmap éditeur

**Format** : IFF EDTR (même conteneur FORM que le `.ttile`)

**Chunks** :
- `VERS` : version 9
- `DATA` : 16641 float32 = grille **129×129** en mètres, little-endian
  - min=17.3m, max=151.6m — valeurs cohérentes avec la tuile
  - C'est la **heightmap haute résolution** utilisée par Workbench pour l'édition
  - 128×128 blocs + 1 point de bordure partagé avec la tuile voisine

**⚠️ Différent du chunk `HGHT` dans le `.ttile`** qui est la version runtime compressée

---

### Terrain_NNN_layer.dds — Poids de texture éditeur ⭐

**Format** : **DDS standard R32_UINT**, 512×512, 10 mips

**Caractéristiques critiques** :
- **Mip0 et mip1 uniquement** contiennent des données — mip2 à 9 sont vides (tout à zéro)
- Format déjà connu : 1 uint32 par pixel, 6 champs de 5 bits (w1..w6), w0 implicite
- Exemples :
  - `0x0000001F` → w1=100%, w2..w6=0% → matériau local 1 à 100%
  - `0x0002801A` → plusieurs canaux non nuls (bloc mixte)

**🎯 C'est la source de vérité des poids de blending** que Workbench affiche et édite directement — **c'est ce fichier qu'on avait tenté d'écrire via les .edds !**

---

### Terrain_NNN_normal.dds — Normal map éditeur

**Format** : DDS legacy RGBA8, 256×256, 9 mips

**Structure** :
- Format non compressé, 4 bytes/pixel
- Canal R=NX, G=NY, B=NZ(?), A=coverage herbe
- Exemple pixel `(0, 140, 0, 109)` :
  - NX=-1.0 (byte 0 = −128 offset)
  - NY≈+0.094
  - A=109/255≈43% coverage

**Généré automatiquement** par Workbench depuis les poids de texture + heightmap

---

### Terrain_NNN_supertexture.dds — Supertexture couleur éditeur

**Format** : DDS legacy RGBA8 non compressé, 512×512, 10 mips, pitch=1048576

**Structure** :
- Exemple pixel `(47, 72, 68, 255)` → couleur vert-kaki opaque = rendu couleur final de la surface
- C'est le **baking des textures de matériaux** selon leurs poids → aperçu couleur in-editor

**Généré automatiquement** par Workbench

---

## 🗂️ Table de hiérarchie complète — Tous les fichiers terrain

| Fichier | Format | Rôle | Éditable |
|---------|--------|------|----------|
| **`.ttile`** (Data/) | IFF FORM | **Source de vérité runtime** (LRS2, GCTD, TMAT, HGHT) | ✓ à implémenter |
| **`.bterr`** (EditorData/) | IFF EDTR | Heightmap éditeur 129×129 float32 | ✓ (déjà connu) |
| **`_layer.dds`** (EditorData/) ⭐ | **DDS R32_UINT** | **Poids de texture 512×512 — source de vérité éditeur** | ✅ **CIBLE PRIORITAIRE** |
| `_normal.dds` (EditorData/) | DDS RGBA8 | Normal map générée | ✗ output WB |
| `_supertexture.dds` (EditorData/) | DDS RGBA8 | Couleur baked générée | ✗ output WB |
| `_layer.edds` (EditorData/) | EDDS LZ4 | Cache layer pour runtime | ✗ output WB |
| `_normal.edds` (EditorData/) | EDDS BC7 | Cache normal pour runtime | ✗ output WB |
| `_supertexture.edds` (EditorData/) | EDDS BC7 | Cache supertexture pour runtime | ✗ output WB |

---

## 🚀 Stratégie d'écriture directe optimale

### ⭐ Point clé découvert

Le **`_layer.dds`** (EditorData) est un **DDS standard R32_UINT sans LZ4** — on peut l'écrire directement avec `struct.pack`. **C'est probablement plus simple que de passer par le `.ttile`.**

### Workflow recommandé

```
[1. Écrire _layer.dds (DDS standard R32_UINT)]
              ↓
[2. Ouvrir dans Workbench]
              ↓
[3. Save → Workbench régénère automatiquement]
              ↓
    ┌─────────┬─────────────┬──────────────┐
    ↓         ↓             ↓              ↓
  .ttile    .edds      normal.edds   supertexture.edds
  (GCTD)   (LZ4)        (BC7)          (BC7)
```

**Avantages** :
- ✅ Format simple (DDS standard, pas EDDS)
- ✅ Pas de compression LZ4 chaînée à gérer
- ✅ Workbench fait toute la régénération automatiquement
- ✅ Seul le mip0 512×512 est nécessaire (mip1-9 peuvent rester vides)

**Implémentation** :
```python
# Structure simple DDS R32_UINT
header = create_dds_header_r32uint(512, 512, mipcount=10)
mip0_data = encode_weights_to_uint32(weights_512x512)  # 512×512×4 bytes
mip1_9_data = b'\x00' * (mip1_to_9_total_size)  # Remplir de zéros

with open("Terrain_616_layer.dds", "wb") as f:
    f.write(header)
    f.write(mip0_data)
    f.write(mip1_9_data)
```

**→ C'est la voie la plus simple pour l'implémentation !**

---

## ⚠️ Tests d'écriture directe — Résultats (août 2026)

### Test 1 : Écriture sur `_layer.dds` — ❌ ÉCHEC

**Protocole** :
1. Workbench fermé
2. Modification d'un bloc dans `Terrain_NNN_layer.dds` (EditorData/)
3. Redémarrage de Workbench
4. Observation du bloc modifié

**Résultat** : **Aucun changement visible** dans le Terrain Editor sur le bloc modifié

**Hypothèse** : **Workbench lit le `_layer.edds` en priorité**, pas le `_layer.dds`

**Implications** :
- Le `_layer.dds` n'est probablement **pas** la source de vérité au chargement
- Workbench pourrait utiliser la hiérarchie : `.edds` (cache) → `.ttile` (source) → `.dds` (fallback ?)
- Il faudrait écrire le `_layer.edds` (LZ4 chaîné) **OU** le `.ttile` (GCTD + LRS2 + TMAT)

### Ordre de priorité probable (à valider)

```
Chargement Workbench :
1. _layer.edds existe ET valide ? → charger depuis .edds
2. Sinon → charger depuis .ttile (GCTD/LRS2/TMAT)
3. Sinon → fallback .dds (?)

Save Workbench :
→ Écriture simultanée : .ttile + .edds + .dds (tous synchronisés)
```

**Prochains tests à faire** :
- [ ] Supprimer le `_layer.edds` → est-ce que Workbench charge alors le `.dds` ?
- [ ] Modifier le `.ttile` (GCTD) directement → est-ce que WB le détecte ?
- [ ] Modifier le `_layer.edds` avec LZ4 chaîné valide → est-ce que WB l'accepte ?

**→ La stratégie d'écriture reste à confirmer par tests supplémentaires.**

---

## ✅ Format .ttile Reforger — Synthèse finale validée (août 2026)

### Découverte fondamentale

**Workbench ne modifie pas le `_layer.edds` lors d'une modification de texture dans le Terrain Editor.** Le problème LZ4 identifié précédemment était un faux problème. **La source de vérité des textures terrain est entièrement dans le `.ttile`**, format IFF big-endian **sans compression**.

---

### Fichiers EditorData — Rôles clarifiés définitifs

| Fichier | Format | Rôle | Modifiable |
|---------|--------|------|------------|
| **`.Data/Terrain_NNN.ttile`** | **IFF FORM** | **Source de vérité runtime** | ✅ **script** |
| `.EditorData/Terrain_NNN.bterr` | IFF EDTR | Heightmap éditeur 129×129 float32 | ✅ connu |
| `.EditorData/Terrain_NNN_layer.dds` | DDS R32_UINT 512×512 | Poids de texture éditeur — **ignoré par Reforger** | ✗ inutile |
| `.EditorData/Terrain_NNN_layer.edds` | EDDS LZ4 chaîné | Cache runtime — **régénéré par WB au Save** | ✗ |
| `.EditorData/Terrain_NNN_normal.dds` | DDS RGBA8 256×256 | Normal map — générée par WB | ✗ |
| `.EditorData/Terrain_NNN_supertexture.dds` | DDS RGBA8 512×512 | Couleur baked — générée par WB | ✗ |
| `.EditorData/Terrain_NNN_normal.edds` | EDDS BC7 | Cache normal — généré par WB | ✗ |
| `.EditorData/Terrain_NNN_supertexture.edds` | EDDS BC7 | Cache supertexture — généré par WB | ✗ |

---

### Structure du .ttile

```
FORM (big-endian IFF)
└── TERR
    ├── VERS  (4 bytes)      — version
    ├── HGHT  (33282 bytes)  — heightmap runtime compressée — jamais modifié
    ├── BERR  (576 bytes)    — border error — jamais modifié
    ├── GCTD  (~30452 bytes) — poids de texture par pixel/bloc ← MODIFIER
    ├── LRS2  (~208 bytes)   — liste matériaux par bloc ← MODIFIER
    └── TMAT  (~20404 bytes) — métadonnées matériaux (régénéré par WB)
```

**Chunks modifiés par Workbench lors d'une modif texture** : `GCTD` + `LRS2` + `TMAT`

---

### LRS2 — Liste des matériaux par bloc

**Format** : liste d'entrées consécutives, une par bloc actif

```
index   uint32 LE  = bx | (by << 7)   — coordonnées globales encodées
count   uint16 LE  = nombre de matériaux
mat_ids uint16 LE  × count             — IDs globaux depuis terrain.terr
```

**Les IDs dans la liste définissent les index locaux utilisés dans le GCTD** :

```
index local 0 = mat_ids[0]
index local 1 = mat_ids[1]
etc.
```

**Exemple** — bloc (34,79) : `[3, 8, 26]` = `[Grass_03, Rock_01, ForestConiferous_01_Base]`

---

### GCTD — Données de texture par cellule (résolution 45×45) ✅

#### Problème de départ

Le payload GCTD d'un bloc fait **2026 bytes**. Un bloc terrain fait 128×128 pixels dans le `_layer.dds`. **2026 ≠ 16384** → pas de correspondance 1:1. La résolution du GCTD était inconnue.

#### Méthode de décodage

Comparaison d'un bloc mixte (deux matériaux distincts) entre le payload GCTD et une visualisation en grille. Le bloc (32,76) contient `[Dirt_01, Grass_03, Rock_01]` avec deux valeurs dans le payload : `0x00` (Dirt_01) et `0x02` (Rock_01).

**En restructurant les 2026 bytes en grille 45×45 = 2025 cellules + 1 byte padding**, le résultat est une forme géographique cohérente : **une frontière diagonale naturelle** entre les deux matériaux, progressant régulièrement de haut en bas avec 1 transition par ligne.

#### ✅ Résultat — Résolution 45×45 décodée

Le GCTD encode une **grille 45×45 cellules par bloc** :

```
2026 bytes = 45 × 45 cellules + 1 byte padding
```

- **Chaque cellule** représente environ **45m × 45m** de terrain (128 × 16m / 45 ≈ 45m par cellule)
- **Chaque byte** = **index local du matériau** dans la liste LRS2 du bloc :
  ```
  0x00 = matériau local 0 (ex: Dirt_01)
  0x01 = matériau local 1 (ex: Grass_03)
  0x02 = matériau local 2 (ex: Rock_01)
  etc.
  ```
- Le **dernier byte** (index 2025) est un byte de padding, toujours `0x00`

#### Ce que ça change — Chirurgie cellule par cellule

On peut maintenant faire de la **chirurgie cellule par cellule** dans le GCTD. Pour les blocs frontière Zone A/B :

1. **Lire le masque d'exclusion** à la résolution 45×45 pour ce bloc (rééchantillonner le masque PNG 4096×4096 → cellules de 45×45)
2. **Pour chaque cellule** :
   - Si pixel masque = **noir** (Zone B) → **préserver l'index existant**
   - Si pixel masque = **blanc** (Zone A) → **appliquer le matériau pipeline**
3. **Reconstruire la LRS2** = union des matériaux Zone B + Zone A
4. **Écrire GCTD + LRS2**

#### Relation GCTD / _layer.dds

**Le GCTD et le `_layer.dds` sont indépendants** — ils ne se correspondent pas en valeurs :

- Le **`_layer.dds`** encode des **poids continus** (6 canaux × 5 bits) à **128×128 pixels**, mais **Reforger l'ignore au runtime**
- Le **GCTD** encode des **index discrets** à **45×45 cellules** et c'est **lui la source de vérité runtime** lue par Reforger

---

### Format d'une section GCTD — Spécifications complètes

**Format global** :

```
header   2 bytes   — EA 07 (valeur fixe)
sections           — une par bloc actif, ordre identique au LRS2
```

**Format d'une section** :

```
bx       uint16 LE  — coordonnée globale X du bloc
by       uint16 LE  — coordonnée globale Y du bloc
payload  2026 bytes — index local du matériau, un byte par "unité"
```

Le **payload** contient des bytes dont la valeur = **index local dans la liste LRS2 du bloc**. Exemple : `0x02` = matériau local 2 = 3ème matériau de la liste.

---

### Workflow d'écriture directe ✅

Pour modifier la texture dominante d'un bloc :

1. **LRS2** — remplacer l'ancien ID global par le nouveau dans la liste du bloc cible (ou supprimer si le nouveau est déjà présent)
2. **GCTD** — dans la section du bloc cible, remplacer les bytes de l'ancien index local par le nouvel index local
3. **TMAT** — laisser intact, Workbench le régénère au prochain Save
4. **`.edds`** — ne pas toucher

**Résultat** : **visible in-game immédiatement sans Save Workbench** ✅

---

### Script `write_ttile_block.py` — Implémentation validée

**Usage** :
```bash
python write_ttile_block.py \
  --ttile <path/Terrain_NNN.ttile> \
  --bx <int> --by <int> \
  --old-mat <ID_global> --new-mat <ID_global> \
  [--dry-run] [--no-confirm]
```

**Fonctionnalités** :
- ✅ Backup automatique `.ttile.bak` avant toute écriture
- ✅ Dry-run par défaut pour vérification
- ✅ Gère le remplacement simple et la fusion (si `new-mat` déjà dans la liste → supprime `old-mat` et redirige ses pixels)
- ✅ Coordonnées `bx`/`by` globales — le script calcule la tuile à partir de `bx//4` et `by//4`

**Validation** : ✅ **Testé in-game sur tuile 616, blocs (34,79)** :
- Remplacement `ForestConiferous` → `Rock_01`
- Fusion `zi_MountainGrass_04` → `Dirt_03`

**→ Workflow d'écriture directe CONFIRMÉ et OPÉRATIONNEL** 🎉

---

**Auteur** : Analyse collaborative (juillet-août 2026)  
**Projet** : Map Generator Pro — Pipeline Satmap v2.0
