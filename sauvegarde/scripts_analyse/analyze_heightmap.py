import numpy as np

# Charger le heightmap (skip 6 lignes header)
hmap = np.loadtxt(r"data\projects\Zimnitrita\sources\temp_Terrain_modified3.asc", skiprows=6)
print(f"Dimensions: {hmap.shape}")
print(f"Min: {hmap.min():.2f} m")
print(f"Max: {hmap.max():.2f} m")
print("")

# Statistiques altitudes
print("=== DISTRIBUTION ALTITUDES ===")
percentiles = [0, 1, 2, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 99, 100]
for p in percentiles:
    val = np.percentile(hmap, p)
    count = (hmap <= val).sum()
    pct = count / hmap.size * 100
    print(f"P{p:3d}: {val:7.2f} m  ({pct:5.1f}% de la carte sous cette altitude)")
print("")

# Identifier zones côtières candidates
print("=== ZONES COTIERES CANDIDATES ===")
sea_level = 0.0
coastal_candidates = [5, 10, 20, 30, 50, 80, 100, 150, 200, 300]
for limit in coastal_candidates:
    count = ((hmap >= sea_level) & (hmap <= limit)).sum()
    pct = count / hmap.size * 100
    area_km2 = pct / 100 * 256
    print(f"Zone {sea_level:.0f}-{limit:3d}m: {pct:5.2f}% ({area_km2:6.2f} km²)")
print("")

# Zones plates côtières (celles que tu as mentionnées)
print("=== VERIFICATION ZONES PLATES ===")
print(f"Zone 0-36m (EST plates):  {((hmap >= 0) & (hmap <= 36)).sum() / hmap.size * 100:.2f}% ({((hmap >= 0) & (hmap <= 36)).sum() / hmap.size * 2.56:.2f} km²)")
print(f"Zone 0-51m (OUEST plates): {((hmap >= 0) & (hmap <= 51)).sum() / hmap.size * 100:.2f}% ({((hmap >= 0) & (hmap <= 51)).sum() / hmap.size * 2.56:.2f} km²)")
print("")

# Zone actuellement détectée comme coastal par le pipeline
print("=== ZONE ACTUELLE PIPELINE ===")
print(f"Zone 5-50m (coastal actuel): {((hmap >= 5) & (hmap <= 50)).sum() / hmap.size * 100:.2f}% ({((hmap >= 5) & (hmap <= 50)).sum() / hmap.size * 2.56:.2f} km²)")
print(f"Zone 0-5m (NON détectée):    {((hmap >= 0) & (hmap <= 5)).sum() / hmap.size * 100:.2f}% ({((hmap >= 0) & (hmap <= 5)).sum() / hmap.size * 2.56:.2f} km²)")
