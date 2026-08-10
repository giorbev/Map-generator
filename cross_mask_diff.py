#!/usr/bin/env python3
"""
cross_mask_diff.py
------------------
Croise diff.csv avec new_exclusion4.png pour identifier les blocs
de la Zone B (pixels noirs du masque) dont la texture dominante a changé.

Grille : 32x32 tuiles (1024 tuiles, IDs 0–1023)
  - Tuile 0    : coin bas-gauche
  - Tuile 32   : au-dessus de la tuile 0 (même colonne, ligne +1)
  - Tuile 1023 : coin haut-droit
  - tx = tile_id % 32
  - ty = tile_id // 32  (0 = bas, 31 = haut)

Masque PNG : 4096×4096 pixels
  - Pixel (0,0) en haut-à-gauche dans PIL → correspond à tuile ty=31 (haut)
  - Zone B = pixels noirs (R<128, G<128, B<128)

Usage :
    python cross_mask_diff.py --diff diff.csv --mask new_exclusion4.png [--out zone_b_changes.csv]
"""

import argparse
import csv
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERREUR : Pillow manquant. Lance : pip install Pillow")
    sys.exit(1)


GRID_W = 32          # colonnes
GRID_H = 32          # lignes
MASK_SIZE = 4096     # pixels par côté
TILE_PX = MASK_SIZE // GRID_W   # 128 px par tuile


def tile_id_to_tx_ty(tile_id: int):
    tx = tile_id % GRID_W
    ty = tile_id // GRID_W
    return tx, ty


def tx_ty_to_pixel_region(tx: int, ty: int):
    """
    Retourne (px_left, px_top, px_right, px_bottom) dans l'image PIL.
    PIL a (0,0) en haut-à-gauche, ty=0 est en bas → inverser ty.
    """
    py_top_row = (GRID_H - 1 - ty)   # ligne PIL (0 = haut)
    px_left  = tx * TILE_PX
    px_top   = py_top_row * TILE_PX
    px_right  = px_left + TILE_PX
    px_bottom = px_top  + TILE_PX
    return px_left, px_top, px_right, px_bottom


def is_zone_b(img_pixels, px_left, px_top, px_right, px_bottom, threshold=128):
    """
    Retourne True si la majorité des pixels de la région sont noirs (Zone B).
    On échantillonne les 4 coins + centre pour rapidité.
    """
    sample_points = [
        (px_left,                    px_top),
        (px_right - 1,               px_top),
        (px_left,                    px_bottom - 1),
        (px_right - 1,               px_bottom - 1),
        ((px_left + px_right) // 2,  (px_top + px_bottom) // 2),
    ]
    black_count = 0
    for px, py in sample_points:
        r, g, b = img_pixels[px, py][:3]
        if r < threshold and g < threshold and b < threshold:
            black_count += 1
    return black_count >= 3   # majorité


def load_diff_csv(path: Path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Croise diff.csv × masque Zone B")
    parser.add_argument("--diff",  required=True, help="Chemin vers diff.csv")
    parser.add_argument("--mask",  required=True, help="Chemin vers new_exclusion4.png")
    parser.add_argument("--out",   default="zone_b_changes.csv", help="Fichier de sortie")
    parser.add_argument("--threshold", type=int, default=128,
                        help="Seuil de noirceur (défaut: 128)")
    args = parser.parse_args()

    diff_path = Path(args.diff)
    mask_path = Path(args.mask)
    out_path  = Path(args.out)

    # --- Chargement masque ---
    print(f"[1/4] Chargement masque : {mask_path}")
    img = Image.open(mask_path).convert("RGB")
    w, h = img.size
    print(f"      Résolution : {w}×{h} px")
    if w != MASK_SIZE or h != MASK_SIZE:
        print(f"AVERTISSEMENT : résolution inattendue ({w}×{h}), attendu {MASK_SIZE}×{MASK_SIZE}")
    px = img.load()

    # --- Construction carte Zone B par tile_id ---
    print(f"[2/4] Calcul Zone B pour {GRID_W * GRID_H} tuiles…")
    zone_b_set = set()
    for tile_id in range(GRID_W * GRID_H):
        tx, ty = tile_id_to_tx_ty(tile_id)
        region = tx_ty_to_pixel_region(tx, ty)
        if is_zone_b(px, *region, threshold=args.threshold):
            zone_b_set.add(tile_id)
    print(f"      Tuiles Zone B détectées : {len(zone_b_set)}")

    # --- Chargement diff.csv ---
    print(f"[3/4] Chargement diff : {diff_path}")
    rows = load_diff_csv(diff_path)
    print(f"      Lignes dans diff.csv : {len(rows)}")

    # Détection automatique du nom de colonne tile_id
    if not rows:
        print("ERREUR : diff.csv vide.")
        sys.exit(1)

    sample = rows[0]
    # Colonnes attendues (insensible à la casse)
    col_map = {k.strip().lower(): k for k in sample.keys()}

    def get_col(*candidates):
        for c in candidates:
            if c in col_map:
                return col_map[c]
        return None

    col_tile     = get_col("tile_id", "tile id", "tileid", "id")
    col_bx       = get_col("bx_global", "b global", "bx", "block_x")
    col_by       = get_col("by_global", "by global", "by", "block_y")
    col_tx       = get_col("tx")
    col_ty_col   = get_col("ty")
    col_status   = get_col("status")
    col_dom_main = get_col("dominant_main", "dominant main", "dom_main", "main_dominant")
    col_dom_test = get_col("dominant_test", "dominant test", "dom_test", "test_dominant")
    col_changes  = get_col("changes")

    if not col_tile:
        print("ERREUR : colonne 'tile id' introuvable dans diff.csv.")
        print(f"  Colonnes disponibles : {list(sample.keys())}")
        sys.exit(1)

    # --- Filtrage et export ---
    print(f"[4/4] Croisement et export → {out_path}")
    out_fieldnames = list(sample.keys()) + ["zone_b"]
    zone_b_changed = []

    for row in rows:
        try:
            tile_id = int(row[col_tile])
        except (ValueError, TypeError):
            continue
        if tile_id in zone_b_set:
            row["zone_b"] = "1"
            zone_b_changed.append(row)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        writer.writerows(zone_b_changed)

    # --- Résumé console ---
    print()
    print("=" * 50)
    print(f"  Tuiles Zone B totales       : {len(zone_b_set)}")
    print(f"  Blocs diff dans Zone B      : {len(zone_b_changed)}")

    if zone_b_changed and col_dom_main and col_dom_test:
        # Comptage des changements de texture dominante
        texture_changes = {}
        for row in zone_b_changed:
            key = (row.get(col_dom_main, "?"), row.get(col_dom_test, "?"))
            texture_changes[key] = texture_changes.get(key, 0) + 1
        print()
        print("  Changements de texture dominante (main → test) :")
        for (before, after), count in sorted(texture_changes.items(), key=lambda x: -x[1]):
            if before != after:
                print(f"    {before:30s} → {after:30s}  ({count} blocs)")
        same = sum(c for (b, a), c in texture_changes.items() if b == a)
        diff_count = sum(c for (b, a), c in texture_changes.items() if b != a)
        print()
        print(f"  Dominante inchangée         : {same}")
        print(f"  Dominante changée           : {diff_count}")

    print("=" * 50)
    print(f"  Fichier exporté : {out_path}")


if __name__ == "__main__":
    main()
