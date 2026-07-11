import struct
from pathlib import Path
import numpy as np

TERRAIN_PATH = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
TILE_ID = 737
BX, BY = 2, 2  # Ton bloc d'érosion
BLOCK_PIXEL_RES = 128

def extract_raw_channels():
    dds_path = TERRAIN_PATH / ".EditorData" / f"Terrain_{TILE_ID}_layer.dds"
    if not dds_path.exists():
        print("❌ Fichier de textures introuvable.")
        return

    data = dds_path.read_bytes()
    if data[:4] != b'DDS ':
        print("❌ Format DDS invalide.")
        return

    width = struct.unpack_from('<I', data, 16)[0]
    height = struct.unpack_from('<I', data, 12)[0]

    # Lecture des pixels en BGRA / RGBA standard (4 octets par pixel)
    pixel_data = data[148 : 148 + width * height * 4]
    img = np.frombuffer(pixel_data, dtype=np.uint8).reshape((height, width, 4))

    # Slicing du bloc local [2x2]
    r_start, r_end = BY * BLOCK_PIXEL_RES, (BY * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES
    c_start, c_end = BX * BLOCK_PIXEL_RES, (BX * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES
    block_pixels = img[r_start:r_end, c_start:c_end]

    print(f"=== ANALYSE DES VALEURS DU BLOC DE RÉFÉRENCE [{BX}x{BY}] ===")
    print("Voici les valeurs brutes (0-255) extraites du fichier DDS pour ton érosion :\n")

    channels = ["Canal Bleu (B)", "Canal Vert (V)", "Canal Rouge (R)", "Canal Alpha (A)"]
    for i, name in enumerate(channels):
        ch_data = block_pixels[:, :, i]
        print(f"🔹 {name} :")
        print(f"   ├─ Valeur Min  : {ch_data.min()}")
        print(f"   ├─ Valeur Max  : {ch_data.max()}")
        print(f"   └─ Valeur Moy  : {ch_data.mean():.1f}")

        # Si tu veux voir la répartition pour ton script :
        vals, counts = np.unique(ch_data, return_counts=True)
        top_vals = sorted(zip(vals, counts), key=lambda x: x[1], reverse=True)[:3]
        print(f"   └─ Valeurs les plus fréquentes : " + ", ".join([f"{v} ({c}px)" for v, c in top_vals]))
        print("-" * 50)

extract_raw_channels()
