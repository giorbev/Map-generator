import struct
from pathlib import Path
import numpy as np

TERRAIN_PATH = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
TILE_ID = 737

CELL_SIZE = 4.0
BLOCK_CELL_RES = 32
BLOCK_PIXEL_RES = 128

def load_data():
    editor_dir = TERRAIN_PATH / ".EditorData"
    bterr_path = editor_dir / f"Terrain_{TILE_ID}.bterr"
    dds_path = editor_dir / f"Terrain_{TILE_ID}_layer.dds"

    # 1. Heightmap
    hm = None
    if bterr_path.exists():
        data = bterr_path.read_bytes()
        idx = data.find(b"DATA")
        if idx >= 0:
            chunk_size = struct.unpack_from(">I", data, idx + 4)[0]
            hm = np.frombuffer(data[idx + 8 : idx + 8 + chunk_size], np.float32).reshape(129, 129)

    # 2. Poids bruts des calques
    weights = None
    if dds_path.exists():
        data = dds_path.read_bytes()
        if data[:4] == b'DDS ':
            width = struct.unpack_from('<I', data, 16)[0]
            height = struct.unpack_from('<I', data, 12)[0]
            pixel_data = data[148 : 148 + width * height * 4]
            layer_img = np.frombuffer(pixel_data, dtype=np.uint32).reshape((height, width))
            weights = np.zeros((height, width, 7), dtype=np.float32)
            for i in range(1, 7):
                weights[:, :, i] = (layer_img >> ((i-1) * 5)) & 0x1F
            weights[:, :, 0] = np.clip(31 - np.sum(weights[:, :, 1:7], axis=2), 0, 31)

    return hm, weights

hm, weights = load_data()

if hm is None:
    print("❌ Fichier .bterr introuvable.")
    exit()

print(f"=== DIAGNOSTIC DES 16 BLOCS DE LA TUILE {TILE_ID} ===")
print("Format : [Index Fichier Y, Index Fichier X] -> Altitudes | Pentes")
print("-" * 70)

for f_y in range(4):
    for f_x in range(4):
        # Découpage géométrique brute dans le fichier
        r_start, r_end = f_y * BLOCK_CELL_RES, (f_y * BLOCK_CELL_RES) + BLOCK_CELL_RES + 1
        c_start, c_end = f_x * BLOCK_CELL_RES, (f_x * BLOCK_CELL_RES) + BLOCK_CELL_RES + 1

        hm_block = hm[r_start:r_end, c_start:c_end]
        gy, gx = np.gradient(hm_block.astype(np.float64), CELL_SIZE)
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))

        # Découpage des textures brutes (Somme des canaux 0 à 6 pour voir l'activité)
        t_r_start, t_r_end = f_y * BLOCK_PIXEL_RES, (f_y * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES
        t_c_start, t_c_end = f_x * BLOCK_PIXEL_RES, (f_x * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES

        active_layers = []
        if weights is not None:
            w_block = weights[t_r_start:t_r_end, t_c_start:t_c_end]
            for layer_idx in range(7):
                mean_w = np.mean(w_block[:, :, layer_idx])
                if mean_w > 0.5:
                    active_layers.append(f"L{layer_idx}:{mean_w/31*100:.1f}%")

        layers_str = " | ".join(active_layers) if active_layers else "Aucun calque majeur"

        print(f"Bloc Fichier [{f_y}x{f_x}] : Alt: {hm_block.min():.1f}m à {hm_block.max():.1f}m (Moy: {hm_block.mean():.1f}m) | Pente Max: {slope.max():.1f}°")
        print(f"               └─ Poids Bruts : {layers_str}")
print("-" * 70)
