# Corrections Prioritaires Pipeline

## Modifications à appliquer dans `pipeline_phases.py`

### 1. Dans `generate_continuous_masks()` — APRÈS ligne 253

```python
# ══════════════════════════════════════════════════════════════════════════
# CORRECTION 2: DÉFINIR ZONES GÉOGRAPHIQUES STRICTES
# ══════════════════════════════════════════════════════════════════════════
print("  [ZONES] Definition zones geographiques...")

# Distance mer
sea_mask_bool = heightmap < 0
distance_px = distance_transform_edt(~sea_mask_bool)
distance_m = distance_px * cellsize

coastal_distance_max = 60.0  # FIXE à 60m

# Zone 1: Mer (altitude < 0)
zone_sea = heightmap < 0

# Zone 2: Côtière (altitude >= 0 ET distance < 60m)
zone_coastal = (heightmap >= 0) & (distance_m < coastal_distance_max)

# Zone 3: Terre (tout le reste)
zone_land = (heightmap >= 0) & (distance_m >= coastal_distance_max)

num_sea = np.sum(zone_sea)
num_coastal = np.sum(zone_coastal)
num_land = np.sum(zone_land)
total = zone_sea.size

print(f"    Zone mer      : {num_sea:8} px ({num_sea/total*100:5.2f}%)")
print(f"    Zone cotiere  : {num_coastal:8} px ({num_coastal/total*100:5.2f}%)")
print(f"    Zone terre    : {num_land:8} px ({num_land/total*100:5.2f}%)")
```

### 2. Ligne ~256-264 — REMPLACER seabed par :

```python
# ══════════════════════════════════════════════════════════════════════════
# 01_SEABED (strictement altitude < 0)
# ══════════════════════════════════════════════════════════════════════════
print("  [01] seabed (strict altitude < 0)...")

# Mask binaire strict
masks['01_seabed'] = zone_sea.astype(np.float32)
```

### 3. Ligne ~395-413 — REMPLACER érosion (INVERSION CURVATURE) :

```python
# ══════════════════════════════════════════════════════════════════════════
# CORRECTION 3: ÉROSION PAR CURVATURE (INVERSÉ)
# dirt_erosion  = pente modérée ET concave (talwegs/creux)
# debris_rock   = pente modérée ET convexe (accumulation)
# ══════════════════════════════════════════════════════════════════════════
print("  [09-10] dirt erosion (concave) + debris rock (convexe)...")

debris_min = params['debris_min_deg']
rock_min = params['rock_min_deg']
falloff_slope = 5.0

# Mask pente modérée (debris_min -> rock_min)
erosion_bottom = np.clip(
    (slope - debris_min) / falloff_slope,
    0.0, 1.0
)
erosion_top = np.clip(
    1.0 - (slope - rock_min) / falloff_slope,
    0.0, 1.0
)
moderate_slope_mask = (erosion_bottom * erosion_top).astype(np.float32)

if curvature is not None:
    concave_thresh = params['concave_threshold']
    falloff_curv = 2.0

    curv_factor = np.clip(
        (curvature - concave_thresh) / falloff_curv,
        -1.0, 1.0
    ).astype(np.float32)

    # dirt_erosion = pente modérée × CONCAVE (talwegs)
    masks['09_dirt_erosion'] = moderate_slope_mask * np.clip(-curv_factor, 0.0, 1.0)

    # debris_rock = pente modérée × CONVEXE (accumulation)
    masks['10_debris_rock'] = moderate_slope_mask * np.clip(curv_factor, 0.0, 1.0)
else:
    # Sans curvature : tout dans dirt_erosion
    masks['09_dirt_erosion'] = moderate_slope_mask
    masks['10_debris_rock'] = np.zeros_like(moderate_slope_mask)
```

### 4. APRÈS feathering (ligne ~466) — AJOUTER exclusions strictes :

```python
# ══════════════════════════════════════════════════════════════════════════
# CORRECTION 2: APPLIQUER EXCLUSIONS ZONES STRICTES
# ══════════════════════════════════════════════════════════════════════════
print("  [EXCLUSIONS] Application zones strictes...")

# Zone MER : seul seabed actif
for name in masks.keys():
    if name != '01_seabed':
        masks[name][zone_sea] = 0.0

# Zone CÔTIÈRE : seuls coastal_pebbles + coastal_grass actifs
coastal_only = ['02_coastal_pebbles', '03_coastal_grass']
for name in masks.keys():
    if name not in coastal_only and name != '01_seabed':
        masks[name][zone_coastal] = 0.0

# Zone TERRE : pas de seabed ni coastal
land_excluded = ['01_seabed', '02_coastal_pebbles', '03_coastal_grass']
for name in land_excluded:
    masks[name][zone_land] = 0.0

print(f"    [OK] Exclusions appliquees (sea/coastal/land)")

# ══════════════════════════════════════════════════════════════════════════
# CORRECTION 1: NORMALISATION pixel par pixel
# ══════════════════════════════════════════════════════════════════════════
print("  [NORMALISATION] Somme masks <= 1.0...")

# Exclure seabed de la normalisation
terrain_masks = [name for name in masks.keys() if name != '01_seabed']

# Calculer somme des masks terrain
sum_terrain = np.zeros(shape, dtype=np.float32)
for name in terrain_masks:
    sum_terrain += masks[name]

# Pixels où somme > 1.0
overflow_mask = sum_terrain > 1.0
num_overflow = np.sum(overflow_mask)

if num_overflow > 0:
    print(f"    {num_overflow} pixels avec somme > 1.0 ({num_overflow/sum_terrain.size*100:.2f}%)")
    
    # Normaliser uniquement les pixels overflow
    for name in terrain_masks:
        masks[name][overflow_mask] /= sum_terrain[overflow_mask]
    
    # Vérifier après normalisation
    sum_after = np.zeros(shape, dtype=np.float32)
    for name in terrain_masks:
        sum_after += masks[name]
    
    max_sum = np.max(sum_after)
    print(f"    Somme max apres normalisation: {max_sum:.6f}")
    
    # ASSERT somme <= 1.0
    assert max_sum <= 1.0001, f"ERREUR: somme max = {max_sum} > 1.0"
else:
    print(f"    [OK] Aucun overflow detecte (somme max={np.max(sum_terrain):.6f})")
```

### 5. REMPLACER `verify_masks()` par :

```python
def verify_masks(masks, heightmap, zones=None):
    """
    CORRECTION 4: Vérification détaillée par zone
    
    Args:
        masks: dict {name: float32_array}
        heightmap: array 2D altitudes
        zones: dict optionnel {zone_name: mask_bool}
    """
    print("[7/8] Verification finale POST-CORRECTIONS...")

    valid_mask = ~np.isnan(heightmap)

    print(f"\n  Couverture GLOBALE par mask:")
    for name, mask in masks.items():
        coverage_pct = np.mean(mask[valid_mask]) * 100
        mask_valid = mask[valid_mask]
        min_val = np.min(mask_valid)
        max_val = np.max(mask_valid)
        mean_val = np.mean(mask_valid)

        print(f"    {name:30s}: couv={coverage_pct:5.2f}%, min={min_val:.3f}, max={max_val:.3f}, moy={mean_val:.3f}")

    # ── VÉRIFICATION PAR ZONE ──
    if zones is not None:
        print(f"\n  Couverture PAR ZONE:")
        
        for zone_name, zone_mask in zones.items():
            print(f"\n  [{zone_name.upper()}]")
            
            for name, mask in masks.items():
                coverage_zone = np.mean(mask[zone_mask]) * 100
                if coverage_zone > 0.01:  # Afficher seulement si > 0.01%
                    print(f"    {name:30s}: {coverage_zone:5.2f}%")

    # ── VÉRIFICATION EXCLUSIONS ──
    print(f"\n  [CHECK] Exclusions zones:")
    
    if zones is not None:
        # Check 1: Seabed = 0 sur zone côtière
        seabed_coastal = np.sum(masks['01_seabed'][zones['coastal']])
        print(f"    Seabed zone cotiere : {seabed_coastal:.6f} (doit etre 0)")
        
        # Check 2: Grass = 0 sur zone côtière
        grass_coastal = np.sum(
            masks['04_grass_low'][zones['coastal']] + 
            masks['05_grass_mid'][zones['coastal']] + 
            masks['06_grass_high'][zones['coastal']]
        )
        print(f"    Grass zone cotiere  : {grass_coastal:.6f} (doit etre 0)")
        
        # Check 3: Coastal = 0 sur zone terre
        coastal_land = np.sum(
            masks['02_coastal_pebbles'][zones['land']] + 
            masks['03_coastal_grass'][zones['land']]
        )
        print(f"    Coastal zone terre  : {coastal_land:.6f} (doit etre 0)")

    # ── VÉRIFICATION SOMME ──
    print(f"\n  [CHECK] Somme masks <= 1.0:")
    
    terrain_masks = [name for name in masks.keys() if name != '01_seabed']
    sum_terrain = np.zeros(heightmap.shape, dtype=np.float32)
    for name in terrain_masks:
        sum_terrain += masks[name]
    
    max_sum = np.max(sum_terrain)
    overflow_pixels = np.sum(sum_terrain > 1.0001)
    
    print(f"    Somme max: {max_sum:.6f}")
    print(f"    Pixels >1.0: {overflow_pixels}")
    
    if overflow_pixels == 0:
        print(f"    [OK] Somme <= 1.0 partout")
    else:
        print(f"    [WARNING] {overflow_pixels} pixels somme >1.0 !")

    print(f"\n  [OK] Verification terminee")
```

### 6. Modifier appel dans `run_pipeline_continuous()` :

```python
# 7. Vérifier (passer zones)
zones_dict = {
    'sea': zone_sea,
    'coastal': zone_coastal,
    'land': zone_land
}
verify_masks(masks, heightmap, zones=zones_dict)
```

## IMPORTANT

Ces corrections doivent être appliquées dans l'ordre :
1. Définir zones (début)
2. Modifier seabed (strict)
3. Inverser érosion curvature
4. Exclusions zones (après feathering)
5. Normalisation (après exclusions)
6. Vérification détaillée

Après application, relancer :
```bash
python pipeline_phases.py ... output_corrected
python run_qtre_... output_corrected
```
