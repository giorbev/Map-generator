# Formats Binaires Enfusion — Terrain Zimnitrita

**Version** : 1.0  
**Date** : 2026-08-01  
**Source** : Analyse fichiers réels Zimnitrita (16 km²)

---

## 📋 Table des matières

1. [Format IFF Enfusion](#format-iff-enfusion)
2. [Terrain_N.ttile](#terrain_nttile)
3. [Terrain_N_layer.edds](#terrain_n_layeredds)
4. [Terrain.bterr](#terrainbterr)
5. [HeightMap.desc](#heightmapdesc)
6. [NormTex.desc](#normtexdesc)
7. [SatTex.desc](#sattexdesc)
8. [Résumé par localisation](#résumé-des-fichiers-par-localisation)
9. [Correspondances coordonnées](#correspondances-coordonnées)

---

## Format IFF Enfusion

Tous les fichiers terrain Enfusion utilisent le format **IFF** (Interchange File Format).

### Structure générale

```
FORM  u32_be size  FOURCC_type
  CHUNK_ID  u32_be size  [data]
  CHUNK_ID  u32_be size  [data]
  ...
```

### Règles d'encodage

| Partie | Encodage |
|--------|----------|
| **Headers IFF** | Big-endian (FORM, chunk IDs, sizes) |
| **Données internes** | Little-endian (u32, f32, etc.) |

### Exemple

```
Offset  Bytes               Interprétation
0x00    46 4F 52 4D        FORM (big-endian)
0x04    00 00 30 A4        size = 12452 bytes (big-endian)
0x08    54 45 52 52        TERR (type fichier)
0x0C    56 45 52 53        VERS (premier chunk)
0x10    00 00 00 04        chunk size = 4 bytes (big-endian)
0x14    09 00 00 00        version = 9 (little-endian)
```

**⚠️ Attention** : Confusion fréquente entre big/little endian lors du parsing.

---

## Terrain_N.ttile

**Rôle** : Un fichier par tuile terrain (32×32 tuiles max = 1024 fichiers).

**Contenu** :
- Heightmap locale de la tuile
- Matériaux par bloc (LRS2)
- Métadonnées de rendu

### Structure globale

```
FORM  size  TERR
  VERS  4 bytes     → version (u32 LE) = 9
  HGHT  33282 bytes → heightmap locale
  BERR  576 bytes   → données d'erreur/blend heightmap
  GCTD  2032 bytes  → données grille (timestamps, etc.)
  LRS2  N bytes     → matériaux par bloc (variable)
  TMAT  828 bytes   → table matériaux (sous-chunks BMAT)
```

**Taille typique** : ~40-50 Ko par fichier

---

### Chunk VERS — Version

```
Offset  Type     Valeur
0x00    u32 LE   9  (version Enfusion terrain)
```

**Zimnitrita** : Toujours version 9

---

### Chunk HGHT — Heightmap locale

**Taille** : 33282 bytes

**Contenu** :
- Header (82 bytes ?)
- Array de floats représentant la heightmap locale de la tuile

**Résolution estimée** :
```
(33282 - header) / 4 = environ 8300 floats
→ 91×91 ou 182×182 selon version
```

**Format** :
- Type : `float32` little-endian
- Valeurs : Altitudes en mètres
- Ordre : Ligne par ligne (row-major)

**Exemple (Zimnitrita T0)** :
```
Offset 0x52 (début données) :
  C2 C7 FF FF → float = -127.984375 m (mer)
  C2 C7 FF FF → float = -127.984375 m
  ...
```

---

### Chunk BERR — Blend/Error

**Taille** : 576 bytes

**Rôle** : Données d'erreur ou blend pour transitions entre tuiles

**Format** : Non documenté, binaire propriétaire

---

### Chunk GCTD — Grid/Cell Data

**Taille** : 2032 bytes

**Rôle** : Métadonnées grille (timestamps édition, flags, etc.)

**Format** : Non documenté

---

### Chunk LRS2 — Matériaux par bloc

**Rôle** : Liste des matériaux utilisés par chaque bloc de la tuile

**Structure** : 16 entrées (une par bloc dans la grille 4×4)

#### Format d'une entrée

```
Offset  Type      Description
0x00    u32 LE    index — identifiant du bloc
0x04    u16 LE    n — nombre de matériaux (1-7)
0x06    u16[n]    ids — IDs des matériaux
```

**Taille entrée** : 6 + n×2 bytes

#### Calcul coordonnées depuis index

```python
bx_local = index & 0x7F           # bits 0-6
by_local = (index >> 7) & 0x7F    # bits 7-13
```

**Coordonnées locales** : `(bx, by)` ∈ [0, 3] × [0, 3]

#### Exemple analysé (Terrain_0.ttile, bloc 3,3)

```
Offset  Bytes               Interprétation
0x...   83 01 00 00        index = 0x00000183
                            bx = 0x183 & 0x7F = 3
                            by = (0x183 >> 7) & 0x7F = 3
                            → Bloc local (3, 3)

0x...   04 00              n = 4 matériaux

0x...   00 00              mat_ids[0] = 0  → Grass_03_default.emat
        01 00              mat_ids[1] = 1  → SeaBed_01.emat
        03 00              mat_ids[2] = 3  → Grass_03.emat
        10 00              mat_ids[3] = 16 → (mat_16)
```

**Résultat** : Bloc (3,3) contient 4 matériaux : Grass_03_default, SeaBed_01, Grass_03, et mat_16

#### Vérification cohérence

**LRS2 vs LAYER** :
- LRS2 liste les matériaux présents
- `_layer.edds` stocke les poids de ces matériaux par pixel
- **Important** : Ordre dans LRS2 = ordre dans layer (w0, w1, w2, ...)

**Outil de vérification** :
```bash
python clean_weights.py --validate tx,ty
# Vérifie cohérence LRS2 ↔ layer.edds
```

---

### Chunk TMAT — Table matériaux

**Taille** : 828 bytes

**Rôle** : Liste consolidée des matériaux de la tuile

**Format** : Séquence de sous-chunks BMAT

#### Structure sous-chunk BMAT

```
BMAT  size=8  [u32 index] [u16 n] [u16 id]
```

**Exemple** :
```
42 4D 41 54    BMAT (fourcc)
08 00 00 00    size = 8 bytes (big-endian)
83 01 00 00    index = 0x183 (little-endian)
01 00          n = 1
00 00          id = 0
```

**Utilisation** : Index rapide des matériaux sans parser tout le LRS2

---

## Terrain_N_layer.edds

**Voir** : [FORMAT_LAYER_EDDS.md](FORMAT_LAYER_EDDS.md) pour la documentation complète.

### Résumé

**Rôle** : Poids des matériaux par pixel (masques de splatting GPU)

**Format** :
- DDS avec extension Enfusion (marqueur ENF1)
- Résolution : 512×512 pixels pour Zimnitrita
- Format pixel : R32_UINT (32 bits par pixel)
- Compression : LZ4 chaînée avec dictionnaire

**Encodage pixel** :
```
bits  0- 4 : w1
bits  5- 9 : w2
bits 10-14 : w3
bits 15-19 : w4
bits 20-24 : w5
bits 25-29 : w6
w0 = 31 − Σ(w1..w6)  # implicite
```

**Table offset** :
- **148** pour Zimnitrita (512×512, LZ4 chaîné)
- **128** pour Eden (128×128, COPY brut)

**Outils** :
```bash
# Lire layer.edds
python edds_decoder.py Terrain_123_layer.edds

# Diagnostic santé
python edds_decoder.py --scan-health "chemin/.Data"
```

---

## Terrain.bterr

**Rôle** : Configuration heightmap global de la map (un seul fichier à la racine)

**Localisation** : `World/Zimnitrita/Terrain/Terrain.bterr`

### Structure

```
FORM  size  EDTR
  VERS  4 bytes   → version (u32 LE) = 9
  HEAD  28 bytes  → paramètres globaux heightmap
```

---

### Chunk VERS — Version

```
u32 LE = 9
```

---

### Chunk HEAD — Paramètres globaux (28 bytes)

**Format** (little-endian) :

| Offset | Type | Valeur Zimnitrita | Description |
|--------|------|-------------------|-------------|
| 0 | u32 | 4097 | Largeur heightmap (pixels) |
| 4 | u32 | 4097 | Hauteur heightmap (pixels) |
| 8 | u32 | 0 | Réservé |
| 12 | u32 | 0 | Réservé |
| 16 | f32 | 4.0 | Résolution (mètres/pixel) |
| 20 | u32 | 0 | Réservé |
| 24 | u32 | 0 | Réservé |

**Calcul taille map** :
```
Largeur = 4097 pixels × 4 m/pixel = 16388 m ≈ 16.4 km
Hauteur = 4097 pixels × 4 m/pixel = 16388 m ≈ 16.4 km

Aire = 16388 × 16388 ≈ 268 km²
```

**⚠️ Note** : Zimnitrita annoncé "16 km²" utilise en réalité ~16.4 km de côté

---

### Exemple binaire (Zimnitrita)

```
Offset  Bytes               Interprétation
0x00    46 4F 52 4D        FORM
0x04    00 00 00 24        size = 36 bytes
0x08    45 44 54 52        EDTR

0x0C    56 45 52 53        VERS
0x10    00 00 00 04        size = 4
0x14    09 00 00 00        version = 9 (LE)

0x18    48 45 41 44        HEAD
0x1C    00 00 00 1C        size = 28
0x20    01 10 00 00        width = 4097 (LE)
0x24    01 10 00 00        height = 4097 (LE)
0x28    00 00 00 00        reserved
0x2C    00 00 00 00        reserved
0x30    00 00 80 40        resolution = 4.0 (float LE)
0x34    00 00 00 00        reserved
0x38    00 00 00 00        reserved
```

---

## HeightMap.desc

**Rôle** : Configuration import heightmap dans Workbench (format texte)

**Localisation** : `World/Zimnitrita/Terrain/.EditorData/HeightMap.desc`

### Format

```
HeightMapImportDescClass {
  FileName "chemin/vers/heightmap.png"
  Flags 1
  MinHeight -1000000
  ResampleMinHeight -200    // Altitude minimale en mètres
  ResampleMaxHeight 140     // Altitude maximale en mètres
}
```

### Zimnitrita

```
ResampleMinHeight -200  → Fond mer le plus profond
ResampleMaxHeight 140   → Sommet le plus haut
```

**Plage altitudes** : -200m à +140m = 340m de dénivelé

---

## NormTex.desc

**Rôle** : Configuration génération normal maps (format texte)

**Localisation** : `World/Zimnitrita/Terrain/.EditorData/NormTex.desc`

### Format

```
NormGenDescClass {
  Interpolation automatic
  MinDegAngle 30       // Angle minimum pour les normales
  MaxDegAngle 45       // Angle maximum
  Intensity 1
  TexSize 256          // Résolution normal map par tuile (256×256)
}
```

### Zimnitrita

```
MinDegAngle 30
MaxDegAngle 45
TexSize 256  → 256×256 pixels par tuile
```

**Résolution totale** : 32×32 tuiles × 256×256 = 8192×8192 pixels

**Génération** :
```
Terrain Tool → Manage → Generate Normal Map
```

**⚠️ Important** : Depuis patch Reforger, le canal alpha de la normal map encode la couverture herbe (obligatoire après import masques).

---

## SatTex.desc

**Rôle** : Configuration satmap importée dans Workbench (format texte)

**Localisation** : `World/Zimnitrita/Terrain/.EditorData/SatTex.desc`

### Format

```
SatGenDescClass {
  FileName "chemin/vers/satmap.png"
  sRGBOutput 0
  RenderRoads 1
  Interpolation nearest
  RoadsAA "8x"
}
```

### Zimnitrita

```
FileName "data/projects/Zimnitrita/satmap_4k.png"
sRGBOutput 0
RenderRoads 1        → Dessine les routes sur la satmap
Interpolation nearest
RoadsAA "8x"         → Anti-aliasing routes
```

**Résolution satmap** : 4097×4097 pixels (format Reforger)

**Import** :
```
Terrain Tool → Satellite Texture → Import
```

---

## Résumé des fichiers par localisation

### Racine terrain (`.EditorData/`)

| Fichier | Format | Rôle |
|---------|--------|------|
| `Terrain.bterr` | IFF EDTR | Config heightmap global |
| `HeightMap.desc` | Texte | Paramètres import heightmap |
| `NormTex.desc` | Texte | Paramètres normal map |
| `SatTex.desc` | Texte | Paramètres satmap |
| `Terrain_N_layer.dds` | DDS R32_UINT | Poids textures (format standard) |

**Caractéristiques `.EditorData`** :
- Format DDS standard (pas ENF1)
- Offset table = 128
- Pas de compression LZ4
- Utilisé par l'éditeur Workbench

---

### `.Data/`

| Fichier | Format | Rôle |
|---------|--------|------|
| `Terrain_N.ttile` | IFF TERR | Matériaux + heightmap locale |
| `Terrain_N_layer.edds` | DDS+ENF1 | Poids textures (format Enfusion LZ4) |

**Caractéristiques `.Data`** :
- Format Enfusion natif (ENF1)
- Offset table = 148
- Compression LZ4 chaînée avec dictionnaire
- Utilisé par le runtime Reforger

---

### Règle `.dds` vs `.edds`

```
.EditorData → .dds  : Format DDS standard R32_UINT, offset 128
.Data       → .edds : Format Enfusion LZ4 chaîné, offset 148
```

**Priorité lecture** (clean_weights.py, edds_decoder.py) :
1. `.Data/Terrain_N_layer.edds` (priorité)
2. `.EditorData/Terrain_N_layer.edds` (fallback Eden)
3. `.EditorData/Terrain_N_layer.dds` (fallback legacy)

---

## Correspondances coordonnées

### Tuile → tile_id

```python
tile_id = ty * 32 + tx

# Axes
ty=0  → bas (sud)
ty=31 → haut (nord)
tx=0  → gauche (ouest)
tx=31 → droite (est)
```

**Exemple** :
```
Tuile (11, 3) → tile_id = 3 × 32 + 11 = 107
Terrain_107.ttile
```

---

### Bloc LRS2 local → global

```python
bx_global = tx * 4 + bx_local  # 0-127
by_global = ty * 4 + by_local  # 0-127
```

**Exemple** :
```
Tuile (11, 3), bloc local (2, 1)
→ bx_global = 11 × 4 + 2 = 46
→ by_global = 3 × 4 + 1 = 13
→ Bloc global (46, 13)
```

---

### Index LRS2 → bloc local

```python
bx = index & 0x7F           # bits 0-6
by = (index >> 7) & 0x7F    # bits 7-13
```

**Exemple** :
```
index = 0x00000183
bx = 0x183 & 0x7F = 0x03 = 3
by = (0x183 >> 7) & 0x7F = 0x03 = 3
→ Bloc local (3, 3)
```

---

### Pixel → bloc local dans tuile

**Résolution tuile** : 512×512 pixels  
**Résolution bloc** : 128×128 pixels  
**Grille** : 4×4 blocs

```python
bx_local = x_pixel // 128  # 0-3
by_local = y_pixel // 128  # 0-3
```

**Exemple** :
```
Pixel (200, 350)
→ bx = 200 // 128 = 1
→ by = 350 // 128 = 2
→ Bloc local (1, 2)
```

---

### Bloc global → tuile

```python
tx = bx_global // 4  # 0-31
ty = by_global // 4  # 0-31
```

**Exemple** :
```
Bloc global (46, 13)
→ tx = 46 // 4 = 11
→ ty = 13 // 4 = 3
→ Tuile (11, 3)
```

---

### Pixel global → tuile

**Résolution map** : 16384×16384 pixels (32×32 tuiles × 512 px)

```python
tx = x_global // 512  # 0-31
ty = y_global // 512  # 0-31
```

**Exemple** :
```
Pixel global (5800, 1900)
→ tx = 5800 // 512 = 11
→ ty = 1900 // 512 = 3
→ Tuile (11, 3)
```

---

## Outils d'analyse binaire

### Lecture fichiers IFF

**Python** :
```python
import struct

def read_iff_chunk(data, offset):
    fourcc = data[offset:offset+4]
    size = struct.unpack_from('>I', data, offset+4)[0]  # big-endian
    chunk_data = data[offset+8:offset+8+size]
    return fourcc, size, chunk_data
```

**PowerShell** (hex dump) :
```powershell
Format-Hex -Path "Terrain_0.ttile" -Count 256
```

---

### Validation LRS2

```bash
python clean_weights.py --validate tx,ty
```

**Vérifications** :
- Cohérence index LRS2 → coordonnées
- Matériaux valides (< nombre total surfaces)
- Poids layer cohérents avec LRS2

---

### Diagnostic fichiers

```bash
# Santé tous les .edds
python edds_decoder.py --scan-health "chemin/.Data"

# Détails tuile
python clean_weights.py --inspect tx,ty

# Poids réels
python clean_weights.py --weights tx,ty
```

---

## Références

- [FORMAT_LAYER_EDDS.md](FORMAT_LAYER_EDDS.md) — Format `.edds` détaillé
- [SCRIPTS_REFERENCE.md](SCRIPTS_REFERENCE.md) — Outils d'analyse
- [WORKFLOW_GLOBAL.md](../WORKFLOW_GLOBAL.md) — Workflow complet

---

**Dernière mise à jour** : 2026-08-01  
**Projet** : Map Generator Pro — Zimnitrita 16 km²  
**Source** : Analyse fichiers binaires réels  
**Auteur** : Documentation technique collaborative
