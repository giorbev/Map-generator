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

**Auteur** : Analyse collaborative (juillet 2026)  
**Projet** : Map Generator Pro — Pipeline Satmap v2.0
