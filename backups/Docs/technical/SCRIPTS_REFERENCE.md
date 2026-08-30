# Scripts Reference — Map Generator Pro

Référence complète des scripts utilitaires du projet et leurs fonctions.

---

## 📦 edds_decoder.py

**Rôle** : Tout ce qui touche au format binaire `.edds` (Enfusion DDS)

### Fonctions principales

#### `decode_edds_layer(path) → np.ndarray`
Lit un fichier `.edds` et retourne un array (H, W) uint32.

**Paramètres** :
- `path` : Path — chemin vers le fichier `*_layer.edds`

**Returns** :
- `np.ndarray (H, W)` dtype uint32 — pixels R32_UINT du mip principal
- `None` si erreur

**Exemple** :
```python
from pathlib import Path
from edds_decoder import decode_edds_layer

layer_path = Path("Terrain_123_layer.edds")
pixels = decode_edds_layer(layer_path)
# pixels.shape = (512, 512), dtype=uint32
```

---

#### `encode_edds_layer(pixels, path) → bool`
Patch in-place le mip principal d'un `.edds` existant.

**Paramètres** :
- `pixels` : np.ndarray (H, W) uint32 — nouvelles données du mip principal
- `path` : Path — chemin du fichier `.edds` existant

**Returns** :
- `True` si succès, `False` si erreur

**Notes** :
- ⚠️ Nécessite un fichier `.edds` existant (pas de création)
- Préserve le header DDS natif Workbench
- Utilise la compression LZ4 chaînée avec dictionnaire

**Exemple** :
```python
from edds_decoder import encode_edds_layer

# Modifier les pixels...
success = encode_edds_layer(modified_pixels, layer_path)
```

---

#### `extract_all_weights(pixels) → np.ndarray`
Décode l'array uint32 → (H, W, 7) float32 (poids w0..w6).

**Paramètres** :
- `pixels` : np.ndarray (H, W) uint32 — pixels R32_UINT

**Returns** :
- `np.ndarray (H, W, 7)` float32 — poids normalisés [0, 1]
- Axe 2 : [w0, w1, w2, w3, w4, w5, w6]

**Encodage Enfusion** :
```
bits  0- 4 : w1
bits  5- 9 : w2
bits 10-14 : w3
bits 15-19 : w4
bits 20-24 : w5
bits 25-29 : w6
w0 = 31 − Σ(w1..w6)   (implicite)
```

**Exemple** :
```python
from edds_decoder import extract_all_weights

weights = extract_all_weights(pixels)
# weights.shape = (512, 512, 7), dtype=float32
# weights[y, x, 0] = poids du premier matériau (w0)
# weights[y, x, 1] = poids du deuxième matériau (w1)
# etc.
```

---

#### `pack_weights_to_pixel(weights) → np.ndarray`
Inverse : (H, W, 7) float32 → uint32.

**Paramètres** :
- `weights` : np.ndarray (H, W, 7) float32 [0, 1]

**Returns** :
- `np.ndarray (H, W)` uint32

**Notes** :
- w0 est ignoré (implicite), seuls w1..w6 sont encodés

**Exemple** :
```python
from edds_decoder import pack_weights_to_pixel

# Modifier les poids...
weights[100:200, 100:200, 1] = 1.0  # Forcer mat1 sur une zone

# Ré-encoder
pixels = pack_weights_to_pixel(weights)
```

---

#### `decompress_lz4_chained(data) → bytes`
Décompresse un blob LZ4 chaîné (tranches de 64 Ko avec dictionnaire).

**Format** :
```
u32  taille_décompressée_totale
[u32 taille_compressée & 0x7FFFFFFF][bloc LZ4]  × N
```

**Notes** :
- Chaque chunk utilise les 64 Ko précédents comme dictionnaire
- Bas niveau — utilisé par `decode_edds_layer()`

---

#### `compress_lz4_chained(data) → bytes`
Compresse un blob en LZ4 chaîné (inverse de `decompress_lz4_chained`).

**Notes** :
- Chaque chunk utilise les 64 Ko précédents comme dictionnaire
- Bas niveau — utilisé par `encode_edds_layer()`

---

### Mode CLI : --scan-health

**Usage** :
```bash
python edds_decoder.py --scan-health "chemin/vers/.Data"
```

**Diagnostic** : Scanner tous les `.edds` d'un dossier et vérifier leur intégrité.

**Vérifications** :
1. Auto-détection résolution de référence depuis le premier fichier valide
2. Pour chaque fichier :
   - Résolution conforme (width × height)
   - Table offset conforme
   - Mip principal : FourCC, size, total_size
   - Décompression chunk[0] (si LZ4)
   - Fichier `.ttile` correspondant existe

**Affichage** :
```
Map détectée : résolution 512×512, table_offset=148, format=LZ4 
Scan de 1024 fichiers .edds

✓ OK              : 1020 fichiers
✗ Corrompus       : 2 fichiers
⚠ Hors format     : 1 fichiers
⚠ Ttile manquant  : 1 fichiers

FICHIERS CORROMPUS :
  Terrain_938_layer.edds — mip principal size=0

FICHIERS HORS FORMAT :
  Terrain_200_layer.edds — 128×128 (attendu 512×512)

Tile IDs à vérifier : 200 938
```

---

## 🧹 clean_weights.py

**Rôle** : Tout ce qui touche aux tuiles terrain (nettoyage, modification, diagnostic)

### Modes disponibles

#### `--scan`
Scan rapide de toutes les tuiles, liste celles avec slots négligeables.

**Usage** :
```bash
python clean_weights.py --scan [--threshold 0.01]
```

**Affichage** :
```
Tiles avec slots négligeables (seuil 0.01/31) :

  (2,11) : 3 slots négligeables
  (25,0) : 5 slots négligeables

Total : 2 tiles, 8 slots à nettoyer
```

---

#### `--inspect tx,ty`
Génère une image PNG 800×800 de la tuile avec rendu texturé.

**Usage** :
```bash
python clean_weights.py --inspect 2,11
```

**Fonctionnalités** :
- Fond : rendu texturé des matériaux (ou noir si catalogue absent)
- Quadrillage blanc 4×4 blocs
- Labels par bloc :
  - Coordonnées LRS2 globales
  - Liste matériaux avec coverage %
  - Couleur : rouge (négligeable), blanc (normal), vert (dominant >50%)

**Sortie** : `tile_2_11_cleanup.png`

---

#### `--clean tx,ty`
Supprime les slots négligeables d'une tuile (dry-run + confirmation + backup).

**Usage** :
```bash
python clean_weights.py --clean 25,0 [--threshold 0.02]
```

**Workflow** :
1. Analyse des slots négligeables
2. Affichage dry-run avec détails
3. Confirmation utilisateur
4. Backup automatique (`.ttile.bak`, `.dds.bak`)
5. Nettoyage + renormalisation des poids
6. Mise à jour LRS2

**Affichage** :
```
[DRY-RUN] 5 slots à supprimer dans 3 blocs:

  Bloc (0,1) LRS2=(100,5):
    slot[2]: Dirt_01 (coverage: 0.3%)

Nettoyer 5 slots dans cette tile ? (oui/non) :
```

---

#### `--clean-all`
Nettoyage global de toutes les tiles (confirmation unique, passes itératives).

**Usage** :
```bash
python clean_weights.py --clean-all [--threshold 0.01]
```

**Fonctionnalités** :
- Scan de toutes les tiles
- Confirmation unique au départ
- Backup par tile
- Passes itératives jusqu'à convergence
- Résumé final

**Affichage** :
```
PASSE 1
[DRY-RUN] 15 tiles, 47 slots à nettoyer
Nettoyer 47 slots dans 15 tiles ? (oui/non) :

Passe 1 terminée : 15 tiles OK, 0 erreurs, 47 slots supprimés
→ 47 slots supprimés, nouvelle passe nécessaire...

PASSE 2
...

✅ Convergence atteinte en 2 passe(s), 47 slots supprimés au total
```

---

#### `--force-mat lrs_x,lrs_y --mat-id ID`
Force un matériau unique sur des blocs LRS2 précis.

**Usage** :
```bash
python clean_weights.py --force-mat 46,4 47,4 --mat-id 3
```

**Fonctionnalités** :
- Accepte plusieurs coordonnées LRS2 globales
- Groupe par tuile automatiquement
- Dry-run par tuile
- Force w1=1.0 (matériau cible), w2..w6=0.0
- Met à jour LRS2 pour ne contenir que `[mat_id]`

**Affichage** :
```
Blocs cibles : 2 blocs sur 1 tuile(s)
  Tile (11,1) : (46,4), (47,4)

[DRY-RUN] Tuile (11,1) T43 : 2 blocs à modifier
  LRS2=(46,4) Bloc(2,0) : [Dirt_01, Grass_03] → [Grass_03]

Forcer matériau sur 2 bloc(s) ? (oui/non) :
```

---

#### `--scan-zone --mask`
Identifie les blocs avec résidus dans la Zone B (masque d'exclusion).

**Usage** :
```bash
python clean_weights.py --scan-zone --mask data/zone_b_mask.png
```

**Logique** :
- Détecte les blocs 100% blancs dans le masque
- Vérifie si les matériaux sont autorisés (Grass_03, SeaBed_01)
- Liste les résidus (matériaux non autorisés)

**Affichage** :
```
RÉSUMÉ :
  Blocs 100% blancs traités : 245
  Blocs pleins propres       : 200
  Blocs pleins avec résidus  : 45 → lancer --clean-zone

BLOCS PLEINS avec résidus :
  LRS2=(46,4) Tile(11,1) : Dirt_01 Concrete_01
  ...

Tuiles à nettoyer (--clean-zone) : 11,1 12,3 ...
```

---

#### `--clean-zone --mask`
Nettoie les résidus sur les blocs 100% blancs du masque.

**Usage** :
```bash
python clean_weights.py --clean-zone --mask data/zone_b_mask.png
```

**Fonctionnalités** :
- Détecte les blocs pleins avec résidus
- Supprime uniquement les matériaux non autorisés
- Conserve Grass_03 et SeaBed_01
- Dry-run + confirmation globale
- Backup par tuile

**Affichage** :
```
Blocs 100% blancs traités : 245

[DRY-RUN] 3 tuiles, 45 blocs à nettoyer

  Tuile (11,1) T363 : 15 blocs à nettoyer
  LRS2=(46,4) Bloc(2,0) : Dirt_01 Concrete_01 → supprimés

Nettoyer 45 blocs dans 3 tuiles ? (oui/non) :

[TERMINÉ] 45 blocs nettoyés au total
```

---

#### `--reset-zone --mask`
Force Grass_03 sur tous les blocs 100% blancs du masque.

**Usage** :
```bash
python clean_weights.py --reset-zone --mask data/zone_b_mask.png
```

**Fonctionnalités** :
- Détecte tous les blocs 100% blancs
- Force Grass_03 (mat_id=3) avec w1=1.0 sur chaque bloc
- Met à jour LRS2 pour ne contenir que `[3]`
- Dry-run + confirmation globale
- Backup par tuile

**Affichage** :
```
Matériau cible : Grass_03
Blocs 100% blancs détectés : 245

[DRY-RUN] Reset Zone B : 245 blocs dans 8 tuiles

  Tuile (11,1) T363 : 30 blocs à resetter

Resetter 245 blocs dans 8 tuiles ? (oui/non) :

[TERMINÉ] 245 blocs resettés au total
```

---

#### `--validate tx,ty`
Vérifie la cohérence LRS2 ↔ pixels d'une tuile.

**Usage** :
```bash
python clean_weights.py --validate 2,12
```

**Vérifications** :
1. **TTILE** :
   - FORM size cohérent
   - Chunk LRS2 présent et parsable
   - Index globaux cohérents
   - mat_ids valides (dans le catalogue)
2. **LAYER DDS** :
   - Magic DDS + mip_count
   - base_offset dans les limites
   - Pixels valides (sum ≤ 31)
   - Cohérence LRS2 / layer (coverage par slot)

**Affichage** :
```
[TTILE] Terrain_76.ttile
  ✅ FORM size: 12345 OK
  ✅ LRS2 size: 256
  ✅ 16 blocs LRS2
    (0,0) index=0x0000 mats=[Grass_03, Dirt_01]
    ...

[LAYER] Terrain_76_layer.edds
  ✅ Magic DDS OK
  mip_count: 10
  ✅ base_offset OK
  ✅ 0 pixels invalides

[COHÉRENCE LRS2 / LAYER]
  (0,0): Grass_03=87%, Dirt_01=13%
  ...

✅ Aucune erreur détectée
```

---

#### `--weights tx,ty`
Affiche les poids réels (0-31) par matériau avec image diagnostic.

**Usage** :
```bash
python clean_weights.py --weights 1,18
```

**Fonctionnalités** :
- Log détaillé : moyenne, min, max, coverage par matériau
- Image 800×800 avec valeurs moyennes affichées
- Couleurs selon poids moyen :
  - Vert : dominant (w ≥ 20)
  - Jaune : moyen (10 ≤ w < 20)
  - Orange : faible (0 < w < 10)
  - Rouge : absent (w = 0)

**Affichage** :
```
Bloc            Mat                       Moy    Min    Max   Cover
----------------------------------------------------------------------
  (0,0) LRS=(4,72)  Grass_03                 25.3   18     31   92.5%
  (0,0) LRS=(4,72)  Dirt_01                   5.7    1     13    7.5%
  ...

[OK] Image sauvegardée: tile_1_18_weights.png
```

---

## 🎭 simulate_masks.py

**Rôle** : Outil de simulation (lecture seule) du pipeline de masques

**Usage** :
```bash
python simulate_masks.py
```

**Fonctionnalités** :
- Génère une image 4096×4096 montrant le budget de slots par bloc
- Simule l'empilement des 14 masques du pipeline
- Calcule le nombre de textures par bloc après fusion
- Identifie les blocs critiques (≥6 textures)

**Affichage** :
```
Simulation de l'empilement des 14 masques...

Blocs par nombre de textures :
  1 texture  : 4520 blocs (27.5%)
  2 textures : 6780 blocs (41.2%)
  3 textures : 3890 blocs (23.7%)
  4 textures : 980 blocs (6.0%)
  5 textures : 210 blocs (1.3%)
  6 textures : 48 blocs (0.3%) ← CRITIQUE
  7 textures : 4 blocs (0.0%) ← CRITIQUE

Image sauvegardée : mask_budget_simulation.png
```

---

## ⚠️ Scripts obsolètes (remplacés)

### scan_exclusion_zone.py
**Statut** : ❌ Obsolète — Remplacé par `--scan-zone` dans `clean_weights.py`

### validation_zone_b.py
**Statut** : ❌ Obsolète — Remplacé par `--clean-zone` dans `clean_weights.py`

---

## 📖 Références

- [FORMAT_LAYER_EDDS.md](FORMAT_LAYER_EDDS.md) — Format binaire `.edds` détaillé
- [PIPELINE_LOGIQUE.md](PIPELINE_LOGIQUE.md) — Pipeline de génération satmap
- Mémoire projet : [MEMORY.md](../../.claude/memory/MEMORY.md)

---

**Dernière mise à jour** : 2026-08-01  
**Projet** : Map Generator Pro — Pipeline Satmap v2.0
