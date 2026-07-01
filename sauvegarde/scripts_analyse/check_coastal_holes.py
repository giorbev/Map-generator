"""
Vérifie s'il y a des TROUS dans les masques BeachGrass et Pebbles
sur la zone côtière (0-30m altitude)
"""

import cv2
import numpy as np

# Charger heightmap
hm = np.loadtxt(r"h:\logiciel perso\Map generator\data\projects\Zbk_island\sources\temp_ZBK_terrain_modified7.asc", skiprows=6).astype(np.float32)

min_alt = hm.min()
max_alt = hm.max()
alt_range = max_alt - min_alt

print("=" * 80)
print("VERIFICATION TROUS MASQUES COTIERS")
print("=" * 80)

# Zone côtière 0-30m
coastal_mask = (hm >= 0.0) & (hm <= 30.0)
water_mask = hm < 0.0

print(f"\nZONES :")
print(f"  Eau (< 0m)     : {np.sum(water_mask):,} pixels ({np.sum(water_mask)/hm.size*100:.1f}%)")
print(f"  Cote (0-30m)   : {np.sum(coastal_mask):,} pixels ({np.sum(coastal_mask)/hm.size*100:.1f}%)")

# Charger masques
base_path = r"h:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks"

def load_mask(name_pattern):
    import os
    files = [f for f in os.listdir(base_path) if name_pattern in f and f.endswith('.png')]
    if not files:
        return None
    path = os.path.join(base_path, files[0])
    mask = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if mask.shape != hm.shape:
        mask = cv2.resize(mask, (hm.shape[1], hm.shape[0]), interpolation=cv2.INTER_LINEAR)
    return mask

seabed = load_mask('SeaBed')
beachgrass = load_mask('BeachGrass')
pebbles = load_mask('Pebbles')
grass1 = load_mask('Grass_01')
grass2 = load_mask('Grass_02')

# ============================================================================
# 1. VÉRIFIER SEABED DANS L'EAU
# ============================================================================

print("\n" + "=" * 80)
print("1. SEABED DANS L'EAU (altitude < 0m)")
print("=" * 80)

if seabed is not None:
    seabed_water = seabed[water_mask]
    active_pct = (seabed_water > 1000).sum() / len(seabed_water) * 100
    mean_val = seabed_water.mean()

    print(f"\nSeaBed :")
    print(f"  Moyenne : {mean_val:.0f} ({mean_val/65535*100:.1f}%)")
    print(f"  Actif   : {active_pct:.1f}% pixels (>1000)")

    # Trous = pixels d'eau avec SeaBed < 1000
    holes = (seabed_water < 1000).sum()
    holes_pct = holes / len(seabed_water) * 100

    print(f"\n  TROUS (SeaBed < 1000) : {holes:,} pixels ({holes_pct:.1f}% de l'eau)")

    if holes_pct > 50:
        print(f"  >>> PROBLEME : SeaBed ne couvre que {100-holes_pct:.1f}% de l'eau !")
else:
    print("\n  SeaBed NON TROUVE")

# ============================================================================
# 2. VÉRIFIER BEACHGRASS ET PEBBLES SUR COTE
# ============================================================================

print("\n" + "=" * 80)
print("2. BEACHGRASS ET PEBBLES SUR COTE (0-30m altitude)")
print("=" * 80)

if beachgrass is not None:
    bg_coastal = beachgrass[coastal_mask]
    bg_active_pct = (bg_coastal > 1000).sum() / len(bg_coastal) * 100
    bg_mean = bg_coastal.mean()

    print(f"\nBeachGrass :")
    print(f"  Moyenne : {bg_mean:.0f} ({bg_mean/65535*100:.1f}%)")
    print(f"  Actif   : {bg_active_pct:.1f}% pixels cote (>1000)")

    bg_holes = (bg_coastal < 1000).sum()
    bg_holes_pct = bg_holes / len(bg_coastal) * 100
    print(f"  TROUS   : {bg_holes:,} pixels ({bg_holes_pct:.1f}% de la cote)")
else:
    print("\n  BeachGrass NON TROUVE")
    bg_coastal = np.zeros(np.sum(coastal_mask), dtype=np.uint16)

if pebbles is not None:
    pb_coastal = pebbles[coastal_mask]
    pb_active_pct = (pb_coastal > 1000).sum() / len(pb_coastal) * 100
    pb_mean = pb_coastal.mean()

    print(f"\nPebbles :")
    print(f"  Moyenne : {pb_mean:.0f} ({pb_mean/65535*100:.1f}%)")
    print(f"  Actif   : {pb_active_pct:.1f}% pixels cote (>1000)")

    pb_holes = (pb_coastal < 1000).sum()
    pb_holes_pct = pb_holes / len(pb_coastal) * 100
    print(f"  TROUS   : {pb_holes:,} pixels ({pb_holes_pct:.1f}% de la cote)")
else:
    print("\n  Pebbles NON TROUVE")
    pb_coastal = np.zeros(np.sum(coastal_mask), dtype=np.uint16)

# ============================================================================
# 3. VÉRIFIER COUVERTURE COMBINÉE (BeachGrass OU Pebbles)
# ============================================================================

print("\n" + "=" * 80)
print("3. COUVERTURE COMBINEE (BeachGrass OU Pebbles)")
print("=" * 80)

if beachgrass is not None and pebbles is not None:
    # Pixels avec BeachGrass OU Pebbles actif
    combined_active = ((bg_coastal > 1000) | (pb_coastal > 1000)).sum()
    combined_pct = combined_active / len(bg_coastal) * 100

    # Trous = pixels sans BeachGrass ET sans Pebbles
    combined_holes = ((bg_coastal < 1000) & (pb_coastal < 1000)).sum()
    combined_holes_pct = combined_holes / len(bg_coastal) * 100

    print(f"\nCouverture :")
    print(f"  Actif (BG ou PB) : {combined_pct:.1f}% de la cote")
    print(f"  TROUS (ni BG ni PB) : {combined_holes_pct:.1f}% de la cote")

    if combined_holes_pct > 50:
        print(f"\n  >>> PROBLEME : {combined_holes_pct:.1f}% de la cote n'a NI BeachGrass NI Pebbles !")
        print(f"      -> Grass_01/Grass_02 vont remplir ces trous")

# ============================================================================
# 4. VÉRIFIER SOMME TOTALE SUR COTE
# ============================================================================

print("\n" + "=" * 80)
print("4. SOMME TOTALE SUR COTE (devrait = 65535 = 100%)")
print("=" * 80)

# Charger TOUS les masques
all_masks = []
mask_names = []

for pattern in ['SeaBed', 'BeachGrass', 'Pebbles', 'Grass_01', 'Grass_02', 'Rock', 'Debris', 'MountainGrass', 'Heather', 'Dirt']:
    m = load_mask(pattern)
    if m is not None:
        all_masks.append(m[coastal_mask])
        mask_names.append(pattern)

if all_masks:
    total = np.sum(all_masks, axis=0)
    total_mean = total.mean()
    total_min = total.min()

    # Pixels avec somme < 90%
    low_pixels = (total < 58982).sum()  # 90% de 65535
    low_pct = low_pixels / len(total) * 100

    print(f"\nSomme totale sur cote :")
    print(f"  Moyenne : {total_mean:.0f} ({total_mean/65535*100:.1f}%)")
    print(f"  Min     : {total_min} ({total_min/65535*100:.1f}%)")
    print(f"  Pixels < 90% : {low_pixels:,} ({low_pct:.1f}%)")

    if low_pct > 1:
        print(f"\n  >>> PROBLEME : {low_pct:.1f}% des pixels cote ont somme < 90% !")
        print(f"      -> Grass_02 base visible dans ces zones")

# ============================================================================
# 5. GRASS_02 SUR COTE
# ============================================================================

print("\n" + "=" * 80)
print("5. GRASS_02 SUR COTE")
print("=" * 80)

if grass2 is not None:
    g2_coastal = grass2[coastal_mask]
    g2_active_pct = (g2_coastal > 1000).sum() / len(g2_coastal) * 100
    g2_mean = g2_coastal.mean()

    print(f"\nGrass_02 :")
    print(f"  Moyenne : {g2_mean:.0f} ({g2_mean/65535*100:.1f}%)")
    print(f"  Actif   : {g2_active_pct:.1f}% pixels cote (>1000)")

    if g2_active_pct > 10:
        print(f"\n  >>> INFO : Grass_02 actif sur {g2_active_pct:.1f}% de la cote (NORMAL si c'est le masque)")
else:
    print("\n  Grass_02 NON TROUVE (ou pas de masque)")

print("\n" + "=" * 80)
