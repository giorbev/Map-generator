"""
Test calcul distance côte pour coastal
"""
import numpy as np
from scipy.ndimage import distance_transform_edt

# Simuler heightmap
heightmap = np.random.rand(100, 100) * 200 - 50  # -50 à +150m

# Détecter ligne de côte (transition mer 0)
coastline_mask = (heightmap > 0) & (np.roll(heightmap, 1, axis=0) <= 0)
coastline_mask |= (heightmap > 0) & (np.roll(heightmap, -1, axis=0) <= 0)
coastline_mask |= (heightmap > 0) & (np.roll(heightmap, 1, axis=1) <= 0)
coastline_mask |= (heightmap > 0) & (np.roll(heightmap, -1, axis=1) <= 0)

# Distance transform (pixels)
distance_px = distance_transform_edt(~coastline_mask)

# Convertir en mètres
cellsize = 4.0
distance_m = distance_px * cellsize

print("Test OK!")
print(f"Distance max: {np.max(distance_m):.1f}m")
print(f"Pixels côte: {np.sum(coastline_mask)}")
