#!/usr/bin/env python3
"""Visualise rapidement la colormap générée."""
import matplotlib.pyplot as plt
from PIL import Image
import numpy as np

# Charger la colormap
colormap = Image.open("output/color_map_hypsometric.png")
heightmap = Image.open("input/bornholm_ter.asc")

# Afficher side-by-side
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

ax1.imshow(heightmap, cmap='gray')
ax1.set_title("Heightmap (Bornholm)", fontsize=14)
ax1.axis('off')

ax2.imshow(colormap)
ax2.set_title("Colormap Hypsométrique", fontsize=14)
ax2.axis('off')

plt.tight_layout()
plt.savefig("output/comparison_hypsometric.png", dpi=100, bbox_inches='tight')
print("✅ Comparison sauvegardée: output/comparison_hypsometric.png")
plt.show()
