"""
block_grid_viewer.py - Visualisation du quadrillage global des blocs LRS2
Grille 128x128 blocs avec coordonnées LRS2 globales (bx_global, by_global)
Convention Reforger : (0,0) en bas-gauche
"""

import numpy as np
import cv2
import struct
from pathlib import Path

# ============================================================================
# CONFIG
# ============================================================================
DATA_DIR = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
OUTPUT_PATH = Path(r"H:\logiciel perso\Map generator\block_grid.png")

CELL_SIZE = 40  # pixels par bloc
GRID_SIZE = 128  # 32 tiles × 4 blocs

# Tile à mettre en évidence (None pour désactiver)
HIGHLIGHT_TILE = (1, 23)  # tx, ty

# ============================================================================

def get_tile_coords_from_ttile(ttile_path):
    try:
        with open(ttile_path, 'rb') as f:
            data = f.read()
        i = data.find(b'LRS2')
        if i < 0: return None
        lrs2 = data[i+8:i+8+struct.unpack_from('>I', data, i+4)[0]]
        if len(lrs2) < 4: return None
        index = struct.unpack_from('<I', lrs2, 0)[0]
        bx_g = index & 0x7F
        by_g = (index >> 7) & 0x7F
        return (bx_g // 4, by_g // 4)
    except:
        return None

def main():
    img_size = GRID_SIZE * CELL_SIZE
    img = np.full((img_size, img_size, 3), 50, dtype=np.uint8)

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = CELL_SIZE / 120.0
    
    # Collecter les tiles et leurs positions
    tile_positions = {}  # {(tx,ty): True}
    ttile_files = list(DATA_DIR.glob("Terrain_*.ttile"))
    ttile_files = [f for f in ttile_files if not any(x in f.name for x in ["_layer","_normal","_supertexture"])]
    
    for ttile in ttile_files:
        try:
            tile_id = int(ttile.stem.split('_')[1])
        except:
            continue
        coords = get_tile_coords_from_ttile(ttile)
        if coords:
            tile_positions[coords] = tile_id

    print(f"Tiles trouvées: {len(tile_positions)}")

    # Dessiner le quadrillage
    for by_g in range(GRID_SIZE):
        for bx_g in range(GRID_SIZE):
            # Position dans l'image (Y inversé : by_g=0 → bas = dernière ligne)
            display_y = (GRID_SIZE - 1 - by_g) * CELL_SIZE
            display_x = bx_g * CELL_SIZE

            # Tile correspondante
            tx = bx_g // 4
            ty = by_g // 4
            bx_local = bx_g % 4
            by_local = by_g % 4

            # Couleur de fond selon tile
            is_highlight = HIGHLIGHT_TILE and (tx, ty) == HIGHLIGHT_TILE
            tile_exists = (tx, ty) in tile_positions

            if is_highlight:
                bg = (0, 80, 120)  # bleu pour tile mise en évidence
            elif tile_exists:
                # Alterner couleurs par tile
                bg = (55, 65, 55) if (tx + ty) % 2 == 0 else (65, 55, 65)
            else:
                bg = (30, 30, 30)  # gris foncé = tile absente

            cv2.rectangle(img, (display_x, display_y),
                         (display_x + CELL_SIZE - 1, display_y + CELL_SIZE - 1),
                         bg, -1)

            # Bordure de tile (plus épaisse aux bords de tile)
            border_color = (150, 150, 150)
            tile_border = (220, 220, 100) if is_highlight else (100, 150, 100)

            # Bordure bloc
            cv2.rectangle(img, (display_x, display_y),
                         (display_x + CELL_SIZE - 1, display_y + CELL_SIZE - 1),
                         border_color, 1)

            # Bordure tile (bords gauche et bas de chaque tile)
            if bx_local == 0:
                cv2.line(img, (display_x, display_y),
                        (display_x, display_y + CELL_SIZE - 1), tile_border, 2)
            if by_local == 0:
                cv2.line(img, (display_x, display_y + CELL_SIZE - 1),
                        (display_x + CELL_SIZE - 1, display_y + CELL_SIZE - 1), tile_border, 2)

            # Texte coordonnées globales
            if CELL_SIZE >= 30:
                text = f"{bx_g},{by_g}"
                text_color = (220, 220, 220) if tile_exists else (100, 100, 100)
                if is_highlight:
                    text_color = (255, 255, 100)
                cv2.putText(img, text,
                           (display_x + 2, display_y + CELL_SIZE // 2 + 4),
                           font, font_scale * 0.8, text_color, 1, cv2.LINE_AA)

                # Coordonnées locales en petit en bas
                local_text = f"({bx_local},{by_local})"
                cv2.putText(img, local_text,
                           (display_x + 2, display_y + CELL_SIZE - 4),
                           font, font_scale * 0.55, (150, 150, 150), 1, cv2.LINE_AA)

    # Légende
    print(f"Tile {HIGHLIGHT_TILE} en surbrillance bleue")
    if HIGHLIGHT_TILE and HIGHLIGHT_TILE in tile_positions:
        tx, ty = HIGHLIGHT_TILE
        bx_start = tx * 4
        by_start = ty * 4
        print(f"Tile ({tx},{ty}) → blocs globaux X:[{bx_start}-{bx_start+3}] Y:[{by_start}-{by_start+3}]")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUTPUT_PATH), img)
    print(f"[OK] {OUTPUT_PATH}")
    print(f"     Taille : {img_size}x{img_size} px")

if __name__ == '__main__':
    main()
