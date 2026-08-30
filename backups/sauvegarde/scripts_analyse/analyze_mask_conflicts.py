"""
Analyse conflits masques Workbench
Compare masques générés pour détecter superpositions
"""
import numpy as np
from PIL import Image
from pathlib import Path

# Chemin masques
mask_dir = Path(r"H:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks")

# Charger masques générés (ceux importés dans Workbench)
masks_to_check = {
    '02a_coastal_pebbles': None,
    '02b_coastal_grass': None,
    '03_grass_dry': None,
    '04_grass_standard': None,
    '05_grass_dense_zones': None,
    '06a_highland_dense': None,
    '06b_highland_crest': None,
    '07_dirt_erosion': None,
    '08_dirt_talwegs': None,
    '09_debris_rock_zones': None,
    '10_rock_walls': None
}

print("Chargement masques...")
for name in masks_to_check.keys():
    path = mask_dir / f"{name}.png"
    if path.exists():
        img = Image.open(path)
        # Convertir en boolean (blanc = True)
        arr = np.array(img)
        masks_to_check[name] = (arr > 32768).astype(bool)
        print(f"  {name}: {arr.shape}, pixels actifs: {np.sum(arr > 32768)}")

print("\nAnalyse superpositions...")
conflicts = {}

# Comparer chaque paire de masques
mask_list = [(k, v) for k, v in masks_to_check.items() if v is not None]

for i, (name1, mask1) in enumerate(mask_list):
    for name2, mask2 in mask_list[i+1:]:
        overlap = mask1 & mask2
        overlap_count = np.sum(overlap)

        if overlap_count > 0:
            conflicts[(name1, name2)] = overlap_count
            print(f"  ⚠️ {name1} ∩ {name2}: {overlap_count} pixels")

            # Trouver coordonnées des conflits
            coords = np.argwhere(overlap)
            if len(coords) > 0:
                print(f"     Exemple coords: {coords[:5].tolist()}")

# Vérifier couverture totale vs superposition
print("\n═══════════════════════════════════════════")
print("STATISTIQUES GLOBALES")
print("═══════════════════════════════════════════")

total_pixels = mask_list[0][1].size if mask_list else 0
print(f"Total pixels terrain: {total_pixels}")

# Somme de tous les masques
sum_all = np.zeros_like(mask_list[0][1], dtype=int)
for name, mask in mask_list:
    sum_all += mask.astype(int)

# Pixels avec plusieurs textures
multi_texture = np.sum(sum_all > 1)
print(f"Pixels avec >1 texture: {multi_texture} ({multi_texture/total_pixels*100:.2%})")

# Distribution
unique, counts = np.unique(sum_all, return_counts=True)
print("\nDistribution textures/pixel:")
for val, count in zip(unique, counts):
    print(f"  {val} texture(s): {count} pixels ({count/total_pixels*100:.2%})")

# Sauvegarder carte des conflits
conflict_map = (sum_all > 1).astype(np.uint8) * 255
Image.fromarray(conflict_map).save(mask_dir / "CONFLICT_MAP.png")
print(f"\n✅ Carte conflits sauvegardée: CONFLICT_MAP.png")

# Sauvegarder carte de densité
density_map = np.clip(sum_all * 50, 0, 255).astype(np.uint8)
Image.fromarray(density_map).save(mask_dir / "DENSITY_MAP.png")
print(f"✅ Carte densité sauvegardée: DENSITY_MAP.png")
