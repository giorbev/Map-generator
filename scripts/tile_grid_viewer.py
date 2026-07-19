"""
tile_grid_viewer.py - Visualisation du quadrillage des tuiles de Zimnitrita
Génère une image PNG avec le numéro de chaque tile affiché sur un quadrillage 32x32
"""

import numpy as np
import cv2
from pathlib import Path
import struct

# ============================================================================
# CONFIG
# ============================================================================
DATA_DIR = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
EDITOR_DATA_DIR = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData")
OUTPUT_PATH = Path(r"H:\logiciel perso\Map generator\tile_grid.png")

# Taille de chaque cellule dans l'image de sortie (pixels)
CELL_SIZE = 60

# ============================================================================

def get_tile_coords_from_ttile(ttile_path: Path):
    """Extrait les coordonnées (tx, ty) depuis le chunk LRS2 d'un .ttile"""
    try:
        with open(ttile_path, 'rb') as f:
            data = f.read()
        i = data.find(b'LRS2')
        if i < 0:
            return None
        lrs2_data = data[i+8:i+8+struct.unpack_from('>I', data, i+4)[0]]
        if len(lrs2_data) < 4:
            return None
        index = struct.unpack_from('<I', lrs2_data, 0)[0]
        bx_global = index & 0x7F
        by_global = (index >> 7) & 0x7F
        return (bx_global // 4, by_global // 4)
    except:
        return None

def main():
    print("Lecture des tuiles...")

    # Collecter toutes les tiles et leurs coordonnées
    tile_map = {}  # {(tx, ty): tile_id}
    ttile_files = list(DATA_DIR.glob("Terrain_*.ttile"))
    ttile_files = [f for f in ttile_files if not any(x in f.name for x in ["_layer", "_normal", "_supertexture"])]

    for ttile in ttile_files:
        try:
            tile_id = int(ttile.stem.split('_')[1])
        except:
            continue
        coords = get_tile_coords_from_ttile(ttile)
        if coords:
            tile_map[coords] = tile_id

    if not tile_map:
        print("Aucune tile trouvée !")
        return

    max_x = max(x for x, y in tile_map)
    max_y = max(y for x, y in tile_map)
    grid_w = max_x + 1
    grid_h = max_y + 1

    print(f"Grille détectée : {grid_w}x{grid_h} ({len(tile_map)} tiles)")

    # Créer l'image
    img_w = grid_w * CELL_SIZE
    img_h = grid_h * CELL_SIZE
    img = np.full((img_h, img_w, 3), 240, dtype=np.uint8)  # fond gris clair

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = CELL_SIZE / 120.0
    thickness = max(1, int(CELL_SIZE / 50))

    for (tx, ty), tile_id in tile_map.items():
        # Flip Y pour affichage (ty=0 en bas → en haut dans l'image)
        display_ty = max_y - ty

        x0 = tx * CELL_SIZE
        y0 = display_ty * CELL_SIZE
        x1 = x0 + CELL_SIZE
        y1 = y0 + CELL_SIZE

        # Couleur alternée pour lisibilité
        color_bg = (200, 220, 200) if (tx + ty) % 2 == 0 else (180, 200, 220)
        cv2.rectangle(img, (x0, y0), (x1-1, y1-1), color_bg, -1)

        # Bordure
        cv2.rectangle(img, (x0, y0), (x1-1, y1-1), (100, 100, 100), 1)

        # Coordonnées tx,ty en petit en haut
        coord_text = f"{tx},{ty}"
        cv2.putText(img, coord_text, (x0+2, y0+12),
                    font, font_scale * 0.7, (80, 80, 80), 1, cv2.LINE_AA)

        # ID de tile en grand au centre
        id_text = str(tile_id)
        text_size = cv2.getTextSize(id_text, font, font_scale, thickness)[0]
        cx = x0 + (CELL_SIZE - text_size[0]) // 2
        cy = y0 + (CELL_SIZE + text_size[1]) // 2
        cv2.putText(img, id_text, (cx, cy),
                    font, font_scale, (20, 20, 20), thickness, cv2.LINE_AA)

    # Axes
    # Légende X en bas
    for tx in range(0, grid_w, 4):
        x = tx * CELL_SIZE + CELL_SIZE // 2
        cv2.putText(img, str(tx), (x-5, img_h - 2),
                    font, font_scale * 0.6, (0, 0, 150), 1, cv2.LINE_AA)

    # Sauvegarder
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUTPUT_PATH), img)
    print(f"[OK] Image sauvegardée : {OUTPUT_PATH}")
    print(f"     Taille : {img_w}x{img_h} px")

if __name__ == '__main__':
    main()
