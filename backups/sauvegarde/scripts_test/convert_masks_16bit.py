"""
Convertit tous les masques PNG en 16-bit grayscale pour Reforger
"""
import cv2
import numpy as np
from pathlib import Path

# Dossier masques
input_dir = Path(r"H:\logiciel perso\Map generator\data\projects\Zbk_island\sources\instant\export")
output_dir = input_dir / "16bit"
output_dir.mkdir(exist_ok=True)

print(f"Conversion masques 1-bit -> 16-bit...")
print(f"Input : {input_dir}")
print(f"Output: {output_dir}\n")

for png_file in sorted(input_dir.glob("*_noconflict.png")):
    print(f"  {png_file.name}...", end=" ")

    # Charger (auto-detect format)
    img = cv2.imread(str(png_file), cv2.IMREAD_UNCHANGED)

    if img is None:
        print("ERREUR (lecture)")
        continue

    # Convertir en 16-bit
    if img.dtype == np.uint8:
        # 8-bit -> 16-bit : 0-255 -> 0-65535
        img_16 = (img.astype(np.uint16) * 257)  # 257 = 65535/255
    elif img.dtype == np.uint16:
        # Déjà 16-bit
        img_16 = img
    elif img.dtype == bool or len(np.unique(img)) == 2:
        # 1-bit -> 16-bit : 0/1 -> 0/65535
        img_16 = np.where(img > 0, 65535, 0).astype(np.uint16)
    else:
        print(f"ERREUR (format inconnu: {img.dtype})")
        continue

    # Sauvegarder 16-bit
    out_path = output_dir / png_file.name
    cv2.imwrite(str(out_path), img_16)

    print(f"OK ({img.dtype} -> uint16)")

print(f"\nTerminé ! {len(list(output_dir.glob('*.png')))} masques convertis")
print(f"Utilise les masques dans: {output_dir}")
