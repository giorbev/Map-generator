"""
Sonde le raster layer.dds pour trouver quel quadrant correspond à quel bloc LRS2.
Pour chaque quadrant 128x128, calcule la coverage de chaque canal w1-w6.
"""
import struct
import numpy as np
from pathlib import Path

layer_path = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData\Terrain_737_layer.dds")

with open(layer_path, 'rb') as f:
    data = f.read()

mip0 = np.frombuffer(data[148:148+512*512*4], dtype=np.uint32).reshape(512, 512)

print("Coverage par quadrant (128x128), canaux w1-w6")
print("Format: w1% w2% w3% w4% w5% w6%")
print()

for qy in range(4):
    for qx in range(4):
        y0, x0 = qy*128, qx*128
        block = mip0[y0:y0+128, x0:x0+128]
        covs = []
        for slot in range(1, 7):
            vals = (block >> ((slot-1)*5)) & 0x1F
            cov = (vals > 0).sum() / (128*128) * 100
            covs.append(f"{cov:4.0f}%")
        print(f"  raster[{qy},{qx}] (y={y0}-{y0+127}, x={x0}-{x0+127}): {' '.join(covs)}")
    print()
