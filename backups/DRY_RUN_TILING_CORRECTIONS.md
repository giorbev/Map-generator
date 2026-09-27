# 🔧 DRY-RUN — Corrections tiling satmap_v2_textured_v2.py

**Date :** 2026-09-25  
**Statut :** ⏸️ EN ATTENTE VALIDATION

---

## 📊 PROBLÈMES IDENTIFIÉS

### 1. world_size_m hardcodé (ligne 174)
```python
world_size_m = 2048.0  # ❌ Fixe, inadapté aux grandes cartes
```

**Conséquence** : Répétitions calculées pour 2048m, mais Zimnitrita = 16km → motif 8× trop petit

### 2. Cache incomplet (ligne 103-104)
```python
if mat_id in middles_cache:
    return middles_cache[mat_id]
```

**Conséquence** : Cache indexé par `mat_id` seul, mais appels avec tile_size=512 (SeaBed) ET tile_size=128 (blocs) → retourne mauvaise taille

### 3. Tiling avec np.tile + resize (lignes 178-181)
```python
tiled = np.tile(middle_img, (repeat, repeat, 1))
tiled_resized = cv2.resize(tiled, (tile_size, tile_size), interpolation=cv2.INTER_CUBIC)
```

**Conséquence** : 
- Plafond 32 répétitions (ligne 175)
- Chaque appel recommence motif à l'origine → quadrillage visible entre blocs
- Pas d'échantillonnage en coordonnées globales

### 4. NameError ligne 228
```python
mid = get_material_middle(seabed_id, catalog, surfaces_list, ...)
#                                            ^^^^^^^^^^^^^^ ❌ surfaces_list n'existe pas dans ce scope
```

**Variable correcte** : `surfaces`

---

## 🔧 CORRECTIONS PROPOSÉES

### Modification 1 — Ajouter paramètre world_size_m + calcul m_per_px

**Signature fonction generate_satmap_v2_textured_complete (ligne 302)** :

```diff
def generate_satmap_v2_textured_complete(
    terrain_dir: Path,
    catalog_path: Path,
    output_path: Path,
    terr_file: Path = None,
    mode: str = "colors",
    target_resolution: Optional[int] = 4097,
    verbose: bool = False,
    middles_dir: Path = None,
-   emat_dir: Optional[Path] = None
+   emat_dir: Optional[Path] = None,
+   world_size_m: float = None  # Taille monde en mètres (auto si None)
):
```

**Calcul m_per_px après création canvas (après ligne 415)** :

```diff
    log(f"   Grille : {grid_width}x{grid_height} (depuis coordonnées LRS2)")
    log(f"   Canvas : {grid_width * 512}x{grid_height * 512} pixels")
+
+   # Calculer mètres par pixel
+   canvas_width_px = grid_width * 512
+   if world_size_m is None:
+       # Heuristique : 1 px ≈ 1 m (valide pour Reforger vanilla)
+       world_size_m = float(canvas_width_px)
+   m_per_px = world_size_m / canvas_width_px
+   log(f"   Monde : {world_size_m:.0f}m × {world_size_m:.0f}m")
+   log(f"   Échelle : {m_per_px:.3f} m/px")
    log()
```

---

### Modification 2 — Refonte get_material_middle (lignes 78-190)

**Nouvelle signature avec m_per_px** :

```diff
def get_material_middle(
    mat_id: int,
    catalog: Dict,
    surfaces: List[str],
    middles_dir: Path,
    middles_cache: Dict[int, np.ndarray],
-   tile_size: int = 512,
-   emat_dir: Optional[Path] = None
+   m_per_px: float = 1.0,
+   emat_dir: Optional[Path] = None
) -> np.ndarray:
```

**Documentation** :

```diff
    """
-   Retourne une image tuilée (tile_size × tile_size) RGB pour un matériau.
+   Retourne le middle redimensionné pour échelle correcte, prêt à échantillonner.
    Si middle non disponible, retourne un aplat avg_color/tint.

    Args:
        mat_id: ID du matériau
        catalog: Catalogue de textures
        surfaces: Liste des surfaces
        middles_dir: Dossier contenant les PNG middle
-       middles_cache: Cache des textures déjà chargées {mat_id: np.ndarray}
-       tile_size: Taille de la tuile en pixels (défaut 512)
+       middles_cache: Cache {mat_id: middle redimensionné}
+       m_per_px: Mètres par pixel du canvas global (défaut 1.0)

    Returns:
-       Image RGB (tile_size, tile_size, 3) en float32 [0-255]
+       Middle redimensionné RGB (H, W, 3) en float32 [0-255]
+       Taille : une répétition fait tiling_scale / m_per_px pixels
    """
```

**Cache et fallback modifié** :

```diff
    # Vérifier cache
    if mat_id in middles_cache:
        return middles_cache[mat_id]

    # Fallback couleur plate
    color_flat = get_material_color(mat_id, catalog, surfaces).astype(np.float32)
-   fallback = np.full((tile_size, tile_size, 3), color_flat, dtype=np.float32)
+   # Fallback = motif 1×1 (couleur plate)
+   fallback = np.full((1, 1, 3), color_flat, dtype=np.float32)

    if mat_id >= len(surfaces):
        middles_cache[mat_id] = fallback
        return fallback
```

**Calcul taille répétition (remplace lignes 173-181)** :

```diff
-   # Calculer répétitions
-   world_size_m = 2048.0
-   repeat = max(1, min(32, round(world_size_m / tiling_scale)))
-
-   # Tuiler
-   tiled = np.tile(middle_img, (repeat, repeat, 1))
-
-   # Resize avec INTER_CUBIC pour plus de détail
-   tiled_resized = cv2.resize(tiled, (tile_size, tile_size), interpolation=cv2.INTER_CUBIC)
-
-   result = np.clip(tiled_resized, 0, 255)
+   # Calculer taille d'une répétition en pixels
+   # tiling_scale (m) / m_per_px (m/px) = pixels par répétition
+   repeat_size_px = max(1, int(round(tiling_scale / m_per_px)))
+
+   # Redimensionner middle pour qu'une répétition fasse repeat_size_px
+   middle_resized = cv2.resize(
+       middle_img,
+       (repeat_size_px, repeat_size_px),
+       interpolation=cv2.INTER_CUBIC
+   )
+
+   result = np.clip(middle_resized, 0, 255)
    middles_cache[mat_id] = result
    return result
```

---

### Modification 3 — Échantillonnage par coordonnées globales

**Nouvelle fonction d'échantillonnage** (insérer après get_material_middle) :

```python
def sample_middle_tiled(
    middle: np.ndarray,
    x_global: int,
    y_global: int,
    width: int,
    height: int
) -> np.ndarray:
    """
    Échantillonne le middle avec répétition par modulo.
    
    Args:
        middle: Middle redimensionné (repeat_size_px × repeat_size_px × 3)
        x_global, y_global: Coordonnées globales du coin supérieur gauche
        width, height: Taille de la zone à extraire
    
    Returns:
        Zone extraite (height, width, 3) en float32
    """
    repeat_h, repeat_w = middle.shape[:2]
    
    # Créer grille de coordonnées
    result = np.zeros((height, width, 3), dtype=np.float32)
    
    for dy in range(height):
        for dx in range(width):
            # Coordonnées globales
            gx = x_global + dx
            gy = y_global + dy
            
            # Modulo pour répétition
            mx = gx % repeat_w
            my = gy % repeat_h
            
            result[dy, dx] = middle[my, mx]
    
    return result
```

**Remplacement dans render_textured_block (lignes 267-290)** :

```diff
    # Matériau 0 (w0)
    if middles_dir is not None and middles_cache is not None:
-       mid0 = get_material_middle(mat_ids[0], catalog, surfaces, middles_dir, middles_cache, tile_size=128, emat_dir=emat_dir)
+       mid0_full = get_material_middle(mat_ids[0], catalog, surfaces, middles_dir, middles_cache, m_per_px=m_per_px, emat_dir=emat_dir)
+       # Échantillonner avec coordonnées globales
+       mid0 = sample_middle_tiled(mid0_full, x0_global, y0_global, 128, 128)
    else:
        mid0 = np.full((128, 128, 3), get_material_color(mat_ids[0], catalog, surfaces).astype(np.float32))
    block_canvas += w0[:, :, None] * mid0
    total_w += w0

    # Matériaux explicites
    for k in range(1, min(len(mat_ids), 7)):
        # ... (poids) ...
        mat_id = mat_ids[k]
        if middles_dir is not None and middles_cache is not None:
-           mid = get_material_middle(mat_id, catalog, surfaces, middles_dir, middles_cache, tile_size=128, emat_dir=emat_dir)
+           mid_full = get_material_middle(mat_id, catalog, surfaces, middles_dir, middles_cache, m_per_px=m_per_px, emat_dir=emat_dir)
+           mid = sample_middle_tiled(mid_full, x0_global, y0_global, 128, 128)
        else:
            mid = np.full((128, 128, 3), get_material_color(mat_id, catalog, surfaces).astype(np.float32))
        block_canvas += w[:, :, None] * mid
        total_w += w
```

**Ajout coordonnées globales dans render_textured_block (signature ligne 193)** :

```diff
def render_textured_block(
    bx: int, by: int,
    mat_ids: List[int],
    weights: np.ndarray,
    catalog: Dict,
    surfaces: List[str],
    middles_dir: Path = None,
    middles_cache: Dict[int, np.ndarray] = None,
-   emat_dir: Optional[Path] = None
+   emat_dir: Optional[Path] = None,
+   tile_x_global: int = 0,
+   tile_y_global: int = 0,
+   m_per_px: float = 1.0
) -> np.ndarray:
```

**Calcul coordonnées globales (après ligne 250)** :

```diff
    x0 = bx * 128
    y0 = by * 128
    x1 = x0 + 128
    y1 = y0 + 128
+
+   # Coordonnées globales dans le canvas complet
+   x0_global = tile_x_global + x0
+   y0_global = tile_y_global + y0
```

---

### Modification 4 — Correction NameError ligne 228

```diff
-   mid = get_material_middle(seabed_id, catalog, surfaces_list, middles_dir, middles_cache, tile_size=512, emat_dir=emat_dir)
+   mid_full = get_material_middle(seabed_id, catalog, surfaces, middles_dir, middles_cache, m_per_px=m_per_px, emat_dir=emat_dir)
+   # Échantillonner fond marin (coordonnées tuile globales)
+   mid = sample_middle_tiled(mid_full, x0, y0, 512, 512)
```

---

### Modification 5 — Propagation m_per_px aux appels

**Appel render_textured_block (ligne ~437 dans boucle de tuiles)** :

```diff
-   result = render_textured_block(bx, by, mat_ids, weights, catalog, surfaces_list, middles_dir, middles_cache, emat_dir)
+   result = render_textured_block(
+       bx, by, mat_ids, weights, catalog, surfaces_list, 
+       middles_dir, middles_cache, emat_dir,
+       tile_x_global=x0, tile_y_global=y0, m_per_px=m_per_px
+   )
```

**Variables x0, y0 existent déjà** (coordonnées tuile dans canvas, ligne ~455) :
```python
x0 = tx * 512
y0 = ty * 512
```

---

## 📋 RÉSUMÉ DES CHANGEMENTS

| Fichier | Lignes | Type | Description |
|---------|--------|------|-------------|
| satmap_v2_textured_v2.py | 78-190 | Refonte | get_material_middle : cache cohérent, taille correcte |
| satmap_v2_textured_v2.py | 191+ | Ajout | sample_middle_tiled : échantillonnage coordonnées globales |
| satmap_v2_textured_v2.py | 193-299 | Modif | render_textured_block : coordonnées globales, m_per_px |
| satmap_v2_textured_v2.py | 228 | Fix | surfaces_list → surfaces (NameError) |
| satmap_v2_textured_v2.py | 302 | Param | world_size_m optionnel |
| satmap_v2_textured_v2.py | 415+ | Ajout | Calcul m_per_px, logs |
| satmap_v2_textured_v2.py | ~437 | Modif | Propagation m_per_px aux appels |

---

## ✅ VALIDATIONS REQUISES

- [ ] **Diff approuvé** par l'utilisateur
- [ ] **ast.parse()** après modifications
- [ ] **Test 1 tuile forêt** (tiling 75) — log repeat_size_px
- [ ] **Test 1 tuile champs** (tiling 150) — log repeat_size_px
- [ ] **Vérification visuelle** — Absence raccords entre blocs

---

## 🎯 ATTENDU APRÈS CORRECTION

### Zimnitrita (16km, canvas 16384px)
- m_per_px ≈ 0.976 m/px
- Forêt tiling 75m : repeat_size_px = 75 / 0.976 ≈ **77 px**
- Champs tiling 150m : repeat_size_px = 150 / 0.976 ≈ **154 px**
- **Motif continu** entre blocs (échantillonnage global + modulo)

### Vanilla Everon (2km, canvas 2048px)
- m_per_px = 2000 / 2048 ≈ 0.976 m/px
- Même calcul, échelle adaptée

---

**⏸️ EN ATTENTE VALIDATION UTILISATEUR AVANT APPLICATION**
