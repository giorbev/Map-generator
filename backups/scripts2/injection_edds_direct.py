"""
Injection directe dans fichier .edds (runtime)
Contourne le bug de régénération .edds en modifiant directement le fichier runtime

✅ ENCODEUR LZ4 IMPLÉMENTÉ
"""

import numpy as np
import sys
from pathlib import Path
import shutil

# Import des modules de décodage/encodage
sys.path.append(str(Path(__file__).parent))
from edds_decoder import decode_edds_layer, encode_edds_layer

# --- CONFIGURATION ---
TERRAIN_PATH = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
TILE_ID = 449
BLOCK_GLOBAL_X, BLOCK_GLOBAL_Y = 7, 57

# Calcul des coordonnées locales dans la tuile (0-3)
BLOCKS_PER_TILE = 4
BLOCK_LOCAL_X = BLOCK_GLOBAL_X % BLOCKS_PER_TILE
BLOCK_LOCAL_Y = BLOCK_GLOBAL_Y % BLOCKS_PER_TILE

# Calcul de la position pixel du bloc (128×128)
BLOCK_SIZE = 128
X_START = BLOCK_LOCAL_X * BLOCK_SIZE
Y_START = BLOCK_LOCAL_Y * BLOCK_SIZE

# Chemins des fichiers
dds_editor_path = TERRAIN_PATH / ".EditorData" / f"Terrain_{TILE_ID}_layer.dds"
edds_runtime_path = TERRAIN_PATH / ".Data" / f"Terrain_{TILE_ID}_layer.edds"

print("================================================================")
print(f"INJECTION .EDDS DIRECTE : BLOC GLOBAL [{BLOCK_GLOBAL_X},{BLOCK_GLOBAL_Y}]")
print("================================================================")
print(f"Fichier source  : {dds_editor_path}")
print(f"Fichier cible   : {edds_runtime_path}")
print(f"Bloc local dans tuile : [{BLOCK_LOCAL_X},{BLOCK_LOCAL_Y}]")
print(f"Position pixel : X={X_START}, Y={Y_START} (bloc {BLOCK_SIZE}x{BLOCK_SIZE})")
print(f"Action : Forcer w0 = 31 (100% texture de base L0)")
print("================================================================")

if not dds_editor_path.exists():
    print(f"ERREUR : Fichier .dds editeur introuvable : {dds_editor_path}")
    sys.exit(1)

if not edds_runtime_path.exists():
    print(f"ERREUR : Fichier .edds runtime introuvable : {edds_runtime_path}")
    sys.exit(1)

# 1. LIRE LE FICHIER .DDS ÉDITEUR (R32_UINT NON COMPRESSÉ)
print("\nLecture du fichier .dds editeur (R32_UINT)...")
try:
    with open(dds_editor_path, 'rb') as f:
        data = f.read()

    # Vérifier magic
    if data[:4] != b'DDS ':
        print("ERREUR : Pas un fichier DDS valide")
        sys.exit(1)

    # Lire dimensions (offset 12 = height, 16 = width)
    import struct
    height = struct.unpack_from('<I', data, 12)[0]
    width = struct.unpack_from('<I', data, 16)[0]

    if width != 512 or height != 512:
        print(f"ERREUR : Taille inattendue {width}x{height}, attendu 512x512")
        sys.exit(1)

    # Lire les pixels du mipmap principal (après header de 148 octets)
    HEADER_SIZE = 148
    MIPMAP0_SIZE = width * height * 4  # 512*512*4 = 1 048 576 octets

    pixel_data = data[HEADER_SIZE:HEADER_SIZE + MIPMAP0_SIZE]
    layer_img = np.frombuffer(pixel_data, dtype=np.uint32).copy()
    layer_img = layer_img.reshape((height, width))

    print(f"   OK Lecture reussie : {layer_img.shape} (hauteur x largeur)")

except Exception as e:
    print(f"ERREUR lors de la lecture : {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 2. CRÉER UN BACKUP DU FICHIER .EDDS RUNTIME
backup_path = edds_runtime_path.with_suffix('.edds.backup')
if not backup_path.exists():
    shutil.copy2(edds_runtime_path, backup_path)
    print(f"Backup cree : {backup_path.name}")
else:
    print(f"Backup existant : {backup_path.name}")

# 3. MODIFIER LES PIXELS DU BLOC CIBLÉ
print(f"\nModification du bloc [{BLOCK_LOCAL_X},{BLOCK_LOCAL_Y}]...")

# Forcer w0 = 31 en mettant tous les poids explicites à 0
VALEUR_RESET = 0

# Modifier la zone du bloc (hauteur, largeur)
layer_img[Y_START:Y_START + BLOCK_SIZE, X_START:X_START + BLOCK_SIZE] = VALEUR_RESET

print(f"   OK Pixels modifies : Y={Y_START}-{Y_START+BLOCK_SIZE}, X={X_START}-{X_START+BLOCK_SIZE}")

# 4. RÉ-ENCODER ET ÉCRIRE LE FICHIER .EDDS RUNTIME
print(f"\nRe-encodage et sauvegarde (LZ4)...")

try:
    success = encode_edds_layer(layer_img, edds_runtime_path, mipcount=10)

    if success:
        print(f"   OK Fichier .edds re-encode avec succes !")
        print(f"   Compression LZ4 appliquee (10 mipmaps)")
        print(f"\nPROCHAINES ETAPES :")
        print(f"   1. Ouvre le Workbench")
        print(f"   2. Charge la tuile {TILE_ID}")
        print(f"   3. Verifie que le bloc [{BLOCK_GLOBAL_X},{BLOCK_GLOBAL_Y}] affiche 100% de la texture L0")
        print(f"   4. Les blocs adjacents NE DOIVENT PAS etre modifies (contournement du bug)")
    else:
        print(f"ERREUR : Echec du re-encodage")
        sys.exit(1)

except Exception as e:
    print(f"ERREUR lors du re-encodage : {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n================================================================")
print("INJECTION .EDDS DIRECTE TERMINEE")
print("================================================================")
