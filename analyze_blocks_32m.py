"""
Analyse blocs 32x32m Reforger
Detecte blocs avec +5 textures (limite QTRE)
"""
import numpy as np
from PIL import Image
from pathlib import Path

mask_dir = Path(r"H:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks")

# Parametres terrain ZBK
terrain_size_m = 8192  # 8 km
mask_resolution = 4096  # pixels (downscale 4K)
meters_per_pixel = terrain_size_m / mask_resolution  # 2 m/px
block_size_m = 32  # Taille bloc Reforger
block_size_px = int(block_size_m / meters_per_pixel)  # 32m / 2m/px = 16 px

print(f"Terrain: {terrain_size_m}m")
print(f"Masques: {mask_resolution}x{mask_resolution} px")
print(f"Resolution: {meters_per_pixel} m/px")
print(f"Bloc Reforger: {block_size_m}m = {block_size_px}x{block_size_px} px")
print()

# Charger masques (sauf sous-marins non importes)
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
        print(f"Charge: {name} ({np.sum(masks[name])} px actifs)")

print(f"\nTotal masques importes: {len(masks)}")
print(f"\nAnalyse blocs {block_size_m}x{block_size_m}m...")

# Diviser en blocs et compter textures uniques par bloc
num_blocks_x = mask_resolution // block_size_px
num_blocks_y = mask_resolution // block_size_px

print(f"Grille: {num_blocks_x}x{num_blocks_y} blocs")

# Carte nombre de textures par bloc
texture_count_map = np.zeros((num_blocks_y, num_blocks_x), dtype=int)

# Stats
blocks_exceeding_5 = []
max_textures_in_block = 0

for by in range(num_blocks_y):
    for bx in range(num_blocks_x):
        # Coordonnees bloc en pixels
        y_start = by * block_size_px
        y_end = (by + 1) * block_size_px
        x_start = bx * block_size_px
        x_end = (bx + 1) * block_size_px

        # Compter textures presentes dans ce bloc
        textures_in_block = []
        for name, mask in masks.items():
            block_region = mask[y_start:y_end, x_start:x_end]
            if np.any(block_region):
                textures_in_block.append(name)

        num_textures = len(textures_in_block)
        texture_count_map[by, bx] = num_textures

        if num_textures > max_textures_in_block:
            max_textures_in_block = num_textures

        if num_textures > 5:
            blocks_exceeding_5.append({
                'x': bx,
                'y': by,
                'x_m': bx * block_size_m,
                'y_m': by * block_size_m,
                'count': num_textures,
                'textures': textures_in_block
            })

print(f"\nMax textures dans un bloc: {max_textures_in_block}")
print(f"Blocs depassant 5 textures: {len(blocks_exceeding_5)}")

# Distribution
unique, counts = np.unique(texture_count_map, return_counts=True)
print(f"\nDistribution textures/bloc:")
for val, cnt in zip(unique, counts):
    pct = cnt / (num_blocks_x * num_blocks_y) * 100
    status = " [QTRE OK]" if val <= 5 else " ⚠️ CRASH"
    print(f"  {val} textures: {cnt} blocs ({pct:.1f}%){status}")

# Afficher premiers blocs problematiques
if blocks_exceeding_5:
    print(f"\n{'='*70}")
    print(f"BLOCS PROBLEMATIQUES (>{5} textures)")
    print(f"{'='*70}")
    for i, block in enumerate(blocks_exceeding_5[:20]):  # Max 20 premiers
        print(f"\nBloc #{i+1}: [{block['x_m']}m, {block['y_m']}m] - {block['count']} textures")
        for tex in block['textures']:
            print(f"  - {tex}")

# Sauvegarder carte heatmap
heatmap = np.clip(texture_count_map * 30, 0, 255).astype(np.uint8)
# Upscale pour visibilite (16x16 blocs -> 256x256 image)
scale = max(1, 256 // num_blocks_x)
heatmap_scaled = np.kron(heatmap, np.ones((scale, scale)))
Image.fromarray(heatmap_scaled).save(mask_dir / "BLOCK_TEXTURE_COUNT.png")
print(f"\n✅ Carte heatmap sauvegardee: BLOCK_TEXTURE_COUNT.png")

# Sauvegarder masque blocs problematiques
problem_mask = (texture_count_map > 5).astype(np.uint8) * 255
problem_mask_scaled = np.kron(problem_mask, np.ones((scale, scale)))
Image.fromarray(problem_mask_scaled).save(mask_dir / "BLOCKS_OVER_5_TEXTURES.png")
print(f"✅ Masque blocs +5 textures: BLOCKS_OVER_5_TEXTURES.png")

print(f"\n{'='*70}")
print(f"RESUME")
print(f"{'='*70}")
print(f"Blocs totaux: {num_blocks_x * num_blocks_y}")
print(f"Blocs OK (<=5 tex): {np.sum(texture_count_map <= 5)} ({np.sum(texture_count_map <= 5)/(num_blocks_x * num_blocks_y)*100:.1f}%)")
print(f"Blocs CRASH (>5 tex): {len(blocks_exceeding_5)} ({len(blocks_exceeding_5)/(num_blocks_x * num_blocks_y)*100:.1f}%)")
