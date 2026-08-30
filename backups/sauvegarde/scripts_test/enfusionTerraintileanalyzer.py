"""
Enfusion Terrain Tile & Block Analyzer - Version Corrigée de Production
Calculs géométriques et découpages de pixels alignés à 100% sur le moteur de jeu.
"""

import struct
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np

CELL_SIZE = 4.0
TILE_PIXEL_RES = 512
BLOCKS_PER_AXIS = 4
BLOCK_PIXEL_RES = 128
BLOCK_CELL_RES = 32


class EnfusionRawTileAnalyzer:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.editor_dir = self.base_dir / ".EditorData"

    def load_raw_heightmap(self, tile_id: int) -> Optional[np.ndarray]:
        bterr_path = self.editor_dir / f"Terrain_{tile_id}.bterr"
        if not bterr_path.exists():
            return None
        data = bterr_path.read_bytes()
        idx = data.find(b"DATA")
        if idx < 0:
            return None
        chunk_size = struct.unpack_from(">I", data, idx + 4)[0]
        return np.frombuffer(data[idx + 8 : idx + 8 + chunk_size], np.float32).reshape(129, 129)

    def decode_raw_layer_weights(self, tile_id: int) -> Optional[np.ndarray]:
        dds_path = self.editor_dir / f"Terrain_{tile_id}_layer.dds"
        if not dds_path.exists():
            dds_path = self.editor_dir / f"Terrain_{tile_id}_layer.edds"
            if not dds_path.exists():
                return None

        with open(dds_path, 'rb') as f:
            data = f.read()

        if data[:4] != b'DDS ':
            return None

        header_size = 148
        width = struct.unpack_from('<I', data, 16)[0]
        height = struct.unpack_from('<I', data, 12)[0]

        pixel_data = data[header_size : header_size + width * height * 4]
        if len(pixel_data) != width * height * 4:
            return None

        layer_img = np.frombuffer(pixel_data, dtype=np.uint32).reshape((height, width))
        weights = np.zeros((height, width, 7), dtype=np.float32)

        # Dépaquetage 5-bits Enfusion
        w1 = (layer_img >> 0) & 0x1F
        w2 = (layer_img >> 5) & 0x1F
        w3 = (layer_img >> 10) & 0x1F
        w4 = (layer_img >> 15) & 0x1F
        w5 = (layer_img >> 20) & 0x1F
        w6 = (layer_img >> 25) & 0x1F
        w0 = 31 - (w1 + w2 + w3 + w4 + w5 + w6)

        weights[:, :, 0] = np.clip(w0, 0, 31)
        weights[:, :, 1] = w1
        weights[:, :, 2] = w2
        weights[:, :, 3] = w3
        weights[:, :, 4] = w4
        weights[:, :, 5] = w5
        weights[:, :, 6] = w6
        return weights


if __name__ == "__main__":
    TERRAIN_PATH = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")

    print("\n--- ANALYSEUR DE BLOC REFORGER (ALCHÉMIE VALIDE) ---")
    analyzer = EnfusionRawTileAnalyzer(TERRAIN_PATH)

    try:
        global_bx = int(input("Entrez la valeur X du bloc (ex: 6) : ").strip())
        global_by = int(input("Entrez la valeur Y du bloc (ex: 94) : ").strip())

        val_x = global_bx // 4
        val_y = global_by // 4

        bx = global_bx % 4
        by = global_by % 4

        TILE_ID = val_x + (val_y * 32)

    except ValueError:
        print("❌ Saisie invalide.")
        exit(1)

    print(f"\n===============================================================================")
    print(f" COORDONNÉES ET DOCUMENTS :")
    print(f"  ├─ Bloc In-Game             : [{global_bx}, {global_by}]")
    print(f"  ├─ Grille Tuile             : [{val_x}x{val_y}] (Tuile ID: {TILE_ID})")
    print(f"  ├─ Bloc Local de la Tuile   : Idx [{bx}x{by}]")
    print(f"  └─ Fichier Ciblé            : Terrain_{TILE_ID}")
    print(f"===============================================================================")

    hm = analyzer.load_raw_heightmap(TILE_ID)
    weights_global = analyzer.decode_raw_layer_weights(TILE_ID)

    # --- GÉOMÉTRIE (Slicing Direct Validé) ---
    if hm is not None:
        row_start, row_end = by * BLOCK_CELL_RES, (by * BLOCK_CELL_RES) + BLOCK_CELL_RES + 1
        col_start, col_end = bx * BLOCK_CELL_RES, (bx * BLOCK_CELL_RES) + BLOCK_CELL_RES + 1

        hm_block = hm[row_start:row_end, col_start:col_end]
        gy_b, gx_b = np.gradient(hm_block.astype(np.float64), CELL_SIZE)
        slope_b = np.degrees(np.arctan(np.hypot(gx_b, gy_b)))

        print(f"\n GÉOMÉTRIE DU BLOC CIBLÉ :")
        print(f"  └─ Altitude : Min: {hm_block.min():.1f}m | Max: {hm_block.max():.1f}m | Moy: {hm_block.mean():.1f}m")
        print(f"  └─ Pente    : Max: {slope_b.max():.1f}°  | Moy: {slope_b.mean():.1f}°")
    else:
        print(f"❌ Fichier Terrain_{TILE_ID}.bterr introuvable.")
        exit(1)

    # --- TEXTURES (Slicing Direct Validé) ---
    if weights_global is not None:
        t_row_start, t_row_end = by * BLOCK_PIXEL_RES, (by * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES
        t_col_start, t_col_end = bx * BLOCK_PIXEL_RES, (bx * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES

        weights_block = weights_global[t_row_start:t_row_end, t_col_start:t_col_end]

        print(f"\n TEXTURES DU BLOC CIBLÉ (Canaux Bruts Enfusion) :")
        for i in range(7):
            mean_val = np.mean(weights_block[:, :, i])
            if mean_val > 0.1:
                pct_real = (mean_val / 31.0) * 100
                bar = "█" * int(pct_real / 2)
                print(f"  └─ Canal_L{i}                             : Poids: {mean_val:4.1f}/31 ... Taux: {pct_real:5.1f}% {bar}")
    else:
        print(f"❌ Fichier de textures Terrain_{TILE_ID}_layer.dds/.edds introuvable.")

    print(f"===============================================================================\n")
