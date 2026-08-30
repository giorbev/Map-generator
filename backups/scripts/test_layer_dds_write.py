"""
test_layer_dds_write.py
-----------------------
Modifie le bloc local (2,3) de la tuile 616 dans le _layer.dds
pour y mettre w1=31 (100%), w2..w6=0 sur tous les 128×128 pixels.

C'est un test de validation : ouvre ensuite Workbench et vérifie
si le bloc a changé de texture dominante.

Usage :
    python test_layer_dds_write.py --dds "I:/.../_layer.dds" [--restore]

Sans --restore : applique la modification de test
Avec --restore : restaure depuis le backup .bak
"""
import argparse
import struct
import shutil
from pathlib import Path

BX_LOCAL = 2   # bloc local dans la tuile (34 - 8*4)
BY_LOCAL = 3   # bloc local dans la tuile (79 - 19*4)
BLOC_PX  = 128 # pixels par bloc

# Valeur de test : w1=31 (100%), tout le reste à 0
# Dans la liste LRS2 du bloc (34,79) : [Dirt_01, Grass_03, ForestConiferous]
# w1=100% → matériau local 1 = Grass_03 dominant
TEST_VALUE = 0x0000001F  # w1=31


def read_layer(path: Path):
    data = bytearray(path.read_bytes())
    return data


def get_pixel_offset(x: int, y: int, width: int = 512) -> int:
    """Offset en bytes dans les pixel data (mip0)."""
    return (y * width + x) * 4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dds', required=True, help='Chemin vers Terrain_616_layer.dds')
    parser.add_argument('--restore', action='store_true', help='Restaurer depuis backup')
    args = parser.parse_args()

    dds_path = Path(args.dds)
    bak_path = dds_path.with_suffix('.dds.bak')

    if args.restore:
        if bak_path.exists():
            shutil.copy2(bak_path, dds_path)
            print(f"[OK] Restauré depuis {bak_path}")
        else:
            print(f"[ERREUR] Backup introuvable : {bak_path}")
        return

    # Backup
    if not bak_path.exists():
        shutil.copy2(dds_path, bak_path)
        print(f"[OK] Backup créé : {bak_path}")
    else:
        print(f"[INFO] Backup déjà existant : {bak_path}")

    data = read_layer(dds_path)
    HEADER = 148  # DDS header + DX10 header

    # Coordonnées pixels du bloc local
    row = 3 - BY_LOCAL  # inversion Y : by=3 → row=0 (haut)
    col = BX_LOCAL
    px_x0 = col * BLOC_PX
    px_y0 = row * BLOC_PX

    print(f"Bloc local ({BX_LOCAL},{BY_LOCAL}) → pixels x={px_x0}:{px_x0+BLOC_PX}, y={px_y0}:{px_y0+BLOC_PX}")
    print(f"Valeur test : 0x{TEST_VALUE:08X} (w1=100%)")

    # Lire 3 pixels avant pour vérification
    print("\nAvant modification (3 premiers pixels) :")
    for i in range(3):
        off = HEADER + get_pixel_offset(px_x0 + i, px_y0)
        v = struct.unpack_from('<I', data, off)[0]
        w = [(v >> (k*5)) & 0x1F for k in range(6)]
        print(f"  px ({px_x0+i},{px_y0}): 0x{v:08X} w={w}")

    # Modifier tous les 128×128 pixels du bloc
    count = 0
    for dy in range(BLOC_PX):
        for dx in range(BLOC_PX):
            off = HEADER + get_pixel_offset(px_x0 + dx, px_y0 + dy)
            struct.pack_into('<I', data, off, TEST_VALUE)
            count += 1

    # Vérification après
    print(f"\nAprès modification ({count} pixels) :")
    for i in range(3):
        off = HEADER + get_pixel_offset(px_x0 + i, px_y0)
        v = struct.unpack_from('<I', data, off)[0]
        w = [(v >> (k*5)) & 0x1F for k in range(6)]
        print(f"  px ({px_x0+i},{px_y0}): 0x{v:08X} w={w}")

    # Écriture
    dds_path.write_bytes(bytes(data))
    print(f"\n[OK] Fichier écrit : {dds_path}")
    print("\nOuvre Workbench, charge la tuile 616, vérifie le bloc (34,79).")
    print("Pour restaurer : python test_layer_dds_write.py --dds <chemin> --restore")


if __name__ == '__main__':
    main()
