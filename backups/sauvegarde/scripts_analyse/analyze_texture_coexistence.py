"""
Analyse coexistence textures
- Quelles textures ne se superposent JAMAIS
- Quelles textures coexistent dans blocs +5
"""
import numpy as np
from PIL import Image
from pathlib import Path
from collections import Counter

mask_dir = Path(r"H:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks")

# Parametres
terrain_size_m = 8192
mask_resolution = 4096
meters_per_pixel = terrain_size_m / mask_resolution
block_size_m = 32
block_size_px = int(block_size_m / meters_per_pixel)

# Charger masques importes
masks_imported = [
    '02a_coastal_pebbles',
    '02b_coastal_grass',
    '03_grass_dry',
    '04_grass_standard',
    '05_grass_dense_zones',
    '06a_highland_dense',
    '06b_highland_crest',
    '07_dirt_erosion',
    '08_dirt_talwegs',
    '09_debris_rock_zones',
    '10_rock_walls'
]

masks = {}
for name in masks_imported:
    path = mask_dir / f"{name}.png"
    if path.exists():
        img = Image.open(path)
        masks[name] = (np.array(img) > 32768).astype(bool)

print("="*70)
print("ANALYSE SUPERPOSITION PIXEL-A-PIXEL")
print("="*70)

# Matrice de superposition pixel
mask_list = list(masks.items())
overlap_matrix = {}

for i, (name1, mask1) in enumerate(mask_list):
    for j, (name2, mask2) in enumerate(mask_list):
        if i < j:
            overlap = np.sum(mask1 & mask2)
            overlap_matrix[(name1, name2)] = overlap

# Trier par superposition
sorted_overlaps = sorted(overlap_matrix.items(), key=lambda x: x[1], reverse=True)

print("\nPAIRES AVEC SUPERPOSITION (pixels):")
for (name1, name2), count in sorted_overlaps:
    if count > 0:
        print(f"  {name1:25s} & {name2:25s}: {count:8d} px")

print("\nPAIRES SANS SUPERPOSITION (mutuellement exclusives):")
for (name1, name2), count in sorted_overlaps:
    if count == 0:
        print(f"  {name1:25s} & {name2:25s}: jamais ensemble")

print("\n" + "="*70)
print("ANALYSE BLOCS 32x32m")
print("="*70)

# Analyser blocs
num_blocks_x = mask_resolution // block_size_px
num_blocks_y = mask_resolution // block_size_px

blocks_by_texture_count = {i: [] for i in range(12)}
texture_combinations = Counter()

for by in range(num_blocks_y):
    for bx in range(num_blocks_x):
        y_start = by * block_size_px
        y_end = (by + 1) * block_size_px
        x_start = bx * block_size_px
        x_end = (bx + 1) * block_size_px

        textures_in_block = []
        for name, mask in masks.items():
            block_region = mask[y_start:y_end, x_start:x_end]
            if np.any(block_region):
                textures_in_block.append(name)

        num_textures = len(textures_in_block)
        blocks_by_texture_count[num_textures].append((bx, by, textures_in_block))

        if num_textures > 0:
            # Enregistrer combinaison (triee)
            combo = tuple(sorted(textures_in_block))
            texture_combinations[combo] += 1

print(f"\nDistribution blocs par nombre de textures:")
for count in range(12):
    num_blocks = len(blocks_by_texture_count[count])
    if num_blocks > 0:
        status = "OK" if count <= 5 else "CRASH"
        print(f"  {count} textures: {num_blocks:5d} blocs [{status}]")

print("\n" + "="*70)
print("BLOCS PROBLEMATIQUES (6+ textures)")
print("="*70)

for count in range(6, 12):
    blocks = blocks_by_texture_count[count]
    if blocks:
        print(f"\n--- BLOCS AVEC {count} TEXTURES ({len(blocks)} blocs) ---")

        # Compter combinaisons pour ce nombre de textures
        combos_this_count = {}
        for bx, by, textures in blocks:
            combo = tuple(sorted(textures))
            if combo not in combos_this_count:
                combos_this_count[combo] = 0
            combos_this_count[combo] += 1

        # Trier par frequence
        sorted_combos = sorted(combos_this_count.items(), key=lambda x: x[1], reverse=True)

        print(f"\nCombinaisons de textures (top 10):")
        for combo, freq in sorted_combos[:10]:
            print(f"  [{freq:3d} blocs] Combinaison:")
            for tex in combo:
                print(f"    - {tex}")
            print()

print("="*70)
print("ANALYSE TEXTURES FREQUENTES DANS BLOCS +5")
print("="*70)

# Compter presence de chaque texture dans blocs +5
texture_presence_in_problem_blocks = Counter()
total_problem_blocks = 0

for count in range(6, 12):
    for bx, by, textures in blocks_by_texture_count[count]:
        total_problem_blocks += 1
        for tex in textures:
            texture_presence_in_problem_blocks[tex] += 1

print(f"\nTextures presentes dans blocs +5 ({total_problem_blocks} blocs):")
for tex, freq in texture_presence_in_problem_blocks.most_common():
    pct = freq / total_problem_blocks * 100
    print(f"  {tex:30s}: {freq:4d} / {total_problem_blocks} blocs ({pct:5.1f}%)")

print("\n" + "="*70)
print("GROUPES MUTUELLEMENT EXCLUSIFS")
print("="*70)

# Identifier groupes qui ne se superposent jamais
exclusive_groups = []

# Groupe 1: Altitudes (ne se superposent pas entre elles)
altitude_group = []
for name in masks_imported:
    if any(x in name for x in ['coastal', 'grass', 'highland']):
        altitude_group.append(name)

print("\nGroupe ALTITUDE (mutuellement exclusifs):")
for tex in altitude_group:
    print(f"  - {tex}")

# Groupe 2: Erosion (peuvent se superposer ?)
erosion_group = []
for name in masks_imported:
    if any(x in name for x in ['dirt', 'debris', 'rock']):
        erosion_group.append(name)

print("\nGroupe EROSION:")
for tex in erosion_group:
    print(f"  - {tex}")

# Verifier superposition ENTRE groupes
print("\n" + "="*70)
print("SUPERPOSITION ENTRE GROUPES")
print("="*70)

print("\nAltitude vs Erosion (devrait etre 0 si cascade correcte):")
for alt_tex in altitude_group:
    if alt_tex in masks:
        for ero_tex in erosion_group:
            if ero_tex in masks:
                overlap = np.sum(masks[alt_tex] & masks[ero_tex])
                if overlap > 0:
                    print(f"  {alt_tex:25s} & {ero_tex:25s}: {overlap} px OVERLAP!")
