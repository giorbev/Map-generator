# ✅ RAPPORT APPLICATION — Corrections tiling satmap_v2_textured_v2.py

**Date :** 2026-09-25  
**Statut :** ✅ APPLIQUÉ

---

## 📊 MODIFICATIONS EFFECTUÉES

### 1. get_material_middle — Refonte complète (lignes 78-193)

**Signature modifiée** :
```python
# AVANT
def get_material_middle(..., tile_size: int = 512, ...)

# APRÈS  
def get_material_middle(..., m_per_px: float = 1.0, ...)
```

**Changements clés** :
- ✅ Suppression hardcoding `world_size_m = 2048.0`
- ✅ Calcul `repeat_size_px = max(1, int(round(tiling_scale / m_per_px)))`
- ✅ Redimensionnement direct : `cv2.resize(middle_img, (repeat_size_px, repeat_size_px), INTER_AREA)`
- ✅ Suppression `np.tile()` et plafond 32
- ✅ Cache cohérent (mat_id seul, taille unique par matériau)
- ✅ Fallback 1×1 au lieu de tile_size×tile_size

---

### 2. sample_middle_tiled — Nouvelle fonction vectorisée (lignes 196-229)

```python
def sample_middle_tiled(middle, x_global, y_global, width, height):
    """Échantillonnage avec répétition par modulo (vectorisé numpy)."""
    repeat_h, repeat_w = middle.shape[:2]
    
    # Grilles coordonnées + modulo
    xs_global = x_global + np.arange(width)
    ys_global = y_global + np.arange(height)
    xs = xs_global % repeat_w
    ys = ys_global % repeat_h
    
    # Échantillonnage vectorisé avec np.ix_
    return middle[np.ix_(ys, xs)]
```

**Avantages** :
- ✅ VECTORISÉE numpy (pas de boucles Python)
- ✅ Continuité motif entre blocs/tuiles
- ✅ Coordonnées globales → pas de quadrillage

---

### 3. generate_tile_satmap_textured — Coordonnées globales (lignes 230-350)

**Signature modifiée** :
```python
# AJOUTS
tile_x_global: int = 0,
tile_y_global: int = 0,
m_per_px: float = 1.0
```

**Modifications** :
- ✅ **Ligne 265-268** : NameError corrigé `surfaces_list` → `surfaces`
- ✅ **Ligne 265-269** : SeaBed avec coordonnées globales
  ```python
  mid_full = get_material_middle(..., m_per_px=m_per_px, ...)
  mid = sample_middle_tiled(mid_full, tile_x_global, tile_y_global, 512, 512)
  ```
- ✅ **Ligne 294-296** : Calcul coordonnées globales blocs
  ```python
  x0_global = tile_x_global + bx * 128
  y0_global = tile_y_global + by * 128
  ```
- ✅ **Lignes 306-310, 322-329** : Échantillonnage blocs
  ```python
  mid_full = get_material_middle(..., m_per_px=m_per_px, ...)
  mid = sample_middle_tiled(mid_full, x0_global, y0_global, 128, 128)
  ```

---

### 4. generate_satmap_v2_textured_complete — m_per_px (lignes 345-520)

**Signature modifiée** :
```python
# AJOUT
world_size_m: Optional[float] = None
```

**Calcul m_per_px (après ligne 464)** :
```python
canvas_width = grid_width * 512

if world_size_m is None:
    # Défaut : 1 px ≈ 1 m (mesuré Workbench)
    m_per_px = 1.0
    log(f"   Échelle : {m_per_px:.3f} m/px (défaut Workbench)")
else:
    m_per_px = world_size_m / canvas_width
    log(f"   Monde : {world_size_m:.0f}m × {world_size_m:.0f}m")
    log(f"   Échelle : {m_per_px:.3f} m/px (calculé depuis world_size_m)")
```

**Propagation m_per_px (ligne 503-513)** :
```python
# Coordonnées globales calculées AVANT appel
y0 = ty * 512
x0 = tx * 512

tile_img = generate_tile_satmap_textured(
    tile_id, editor_data_dir, data_dir, catalog, surfaces_list,
    middles_dir, middles_cache, emat_dir,
    tile_x_global=x0, tile_y_global=y0, m_per_px=m_per_px  # ← NOUVEAU
)
```

---

## 📋 RÉSUMÉ TECHNIQUE

| Aspect | Avant | Après |
|--------|-------|-------|
| **world_size_m** | Hardcodé 2048.0 | Paramètre, défaut m_per_px=1.0 |
| **Calcul répétition** | `min(32, world/tiling)` | `tiling / m_per_px` (pas de plafond) |
| **Tiling** | `np.tile()` + resize | Resize direct INTER_AREA |
| **Échantillonnage** | Origine locale (quadrillage) | Coordonnées globales + modulo |
| **Cache** | mat_id + tile_size | mat_id seul (cohérent) |
| **Vectorisation** | Boucles Python implicites | `np.ix_()` explicite |

---

## 🎯 COMPORTEMENT ATTENDU

### Zimnitrita 16km (m_per_px = 1.0 défaut)

**Forêt (tiling 75m)** :
- repeat_size_px = 75 / 1.0 = **75 px** par répétition
- AVANT : 2048 / 75 = 27 répétitions → 27× motif source
- APRÈS : 75 px direct → résolution native préservée

**Champs (tiling 150m)** :
- repeat_size_px = 150 / 1.0 = **150 px** par répétition
- AVANT : 2048 / 150 = 14 répétitions → 14× motif source
- APRÈS : 150 px direct → résolution native préservée

**Motif continu** :
- Bloc 0 (0, 0) échantillonne middle[0:128, 0:128]
- Bloc 1 (128, 0) échantillonne middle[0:128, 128:256] (si repeat_size_px > 128)
- → PAS de raccord visible, continuité parfaite

---

## ✅ VALIDATION

```bash
python -m py_compile satmap_v2_textured_v2.py
```

**Résultat** : ✅ Aucune erreur syntaxe

---

## 🧪 TEST REQUIS

### Commande
```python
# Test sur 1 tuile forêt + 1 tuile champs
# Logger :
# - m_per_px utilisé
# - repeat_size_px pour tiling 75 et 150
# - Temps génération par tuile
```

### Vérification visuelle
- [ ] Absence raccords entre blocs 128×128
- [ ] Absence quadrillage entre tuiles 512×512
- [ ] Résolution texture cohérente (pas de pixelisation excessive)

---

## 🚫 NON TOUCHÉ (conforme demande)

- ✅ generate_catalog.py
- ✅ catalog_config.py
- ✅ main.py
- ✅ Lecture poids/LRS2
- ✅ Normalisation poids
- ✅ satmap_fond_512 (déjà corrigé précédemment)
- ✅ Flip vertical
- ✅ Downscale final
- ✅ Chemins/noms sortie

---

## 📊 STATISTIQUES

| Métrique | Valeur |
|----------|--------|
| **Fichiers modifiés** | 1 (satmap_v2_textured_v2.py) |
| **Fonctions refondues** | 1 (get_material_middle) |
| **Fonctions créées** | 1 (sample_middle_tiled) |
| **Signatures modifiées** | 2 (+ params coordonnées/m_per_px) |
| **NameError corrigés** | 2 (surfaces_list → surfaces) |
| **Lignes modifiées** | ~60 |

---

**✅ CORRECTIONS APPLIQUÉES — En attente test utilisateur**
