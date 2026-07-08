"""
Lecteur simple des fichiers layer.dds depuis .editordata

Format : DDS standard R32_UINT, 512x512, header 148 bytes
Pas de compression LZ4, lecture directe !
"""

import struct
import numpy as np
from pathlib import Path
from typing import Optional


def read_layer_dds(layer_path: Path) -> Optional[np.ndarray]:
    """
    Lit un fichier Terrain_N_layer.dds depuis .editordata

    Format : DDS standard, R32_UINT, 512x512
    Header : 128 bytes (DDS) + 20 bytes (DX10) = 148 bytes total

    Returns:
        np.ndarray (512, 512) uint32, ou None si erreur
    """
    with open(layer_path, 'rb') as f:
        data = f.read()

    # Verifier magic DDS
    if data[:4] != b'DDS ':
        print(f"ERREUR {layer_path.name} : pas un DDS")
        return None

    # Header DDS standard = 128 bytes + DX10 extension 20 bytes
    # Donnees commencent a offset 148
    header_size = 148

    # Lire width/height du header
    width = struct.unpack_from('<I', data, 16)[0]
    height = struct.unpack_from('<I', data, 12)[0]

    if width != 512 or height != 512:
        print(f"Attention {layer_path.name} : taille inattendue {width}x{height}")

    # Extraire pixels (uint32)
    pixel_data = data[header_size:header_size + width*height*4]

    if len(pixel_data) != width * height * 4:
        print(f"ERREUR {layer_path.name} : taille donnees incorrecte")
        return None

    # Convertir en numpy array
    pixels = np.frombuffer(pixel_data, dtype=np.uint32)
    img = pixels.reshape((height, width))

    return img


def extract_weights_from_pixel(pixel: np.uint32) -> np.ndarray:
    """
    Extrait les 7 poids (w0..w6) d'un pixel uint32

    Format :
        w1 = (v >>  0) & 0x1F
        w2 = (v >>  5) & 0x1F
        w3 = (v >> 10) & 0x1F
        w4 = (v >> 15) & 0x1F
        w5 = (v >> 20) & 0x1F
        w6 = (v >> 25) & 0x1F
        w0 = 31 - (w1+w2+w3+w4+w5+w6)

    Returns:
        np.array([w0, w1, w2, w3, w4, w5, w6], dtype=float32)
        Normalise [0, 1]
    """
    w1 = (pixel >> 0) & 0x1F
    w2 = (pixel >> 5) & 0x1F
    w3 = (pixel >> 10) & 0x1F
    w4 = (pixel >> 15) & 0x1F
    w5 = (pixel >> 20) & 0x1F
    w6 = (pixel >> 25) & 0x1F

    # w0 implicite
    w0 = 31 - (w1 + w2 + w3 + w4 + w5 + w6)

    # Normaliser [0, 31] -> [0, 1]
    weights = np.array([w0, w1, w2, w3, w4, w5, w6], dtype=np.float32) / 31.0

    return weights


def extract_all_weights(layer_img: np.ndarray) -> np.ndarray:
    """
    Extrait les poids de tous les pixels d'une image layer

    Args:
        layer_img: (512, 512) uint32

    Returns:
        (512, 512, 7) float32 - poids normalises [0, 1]
    """
    h, w = layer_img.shape
    weights = np.zeros((h, w, 7), dtype=np.float32)

    # Vectoriser l'extraction
    for i in range(7):
        if i == 0:
            # w0 = 31 - somme(w1..w6)
            w1 = (layer_img >> 0) & 0x1F
            w2 = (layer_img >> 5) & 0x1F
            w3 = (layer_img >> 10) & 0x1F
            w4 = (layer_img >> 15) & 0x1F
            w5 = (layer_img >> 20) & 0x1F
            w6 = (layer_img >> 25) & 0x1F
            weights[:, :, 0] = (31 - (w1 + w2 + w3 + w4 + w5 + w6)) / 31.0
        else:
            shift = 5 * (i - 1)
            weights[:, :, i] = ((layer_img >> shift) & 0x1F) / 31.0

    return weights


# Test
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Test sur une tuile
    test_path = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.EditorData\Terrain_0_layer.dds")

    if not test_path.exists():
        print(f"Fichier test non trouve : {test_path}")
        sys.exit(1)

    print(f"Test lecture : {test_path.name}\n")

    layer_img = read_layer_dds(test_path)

    if layer_img is not None:
        print(f"OK Decode : {layer_img.shape} {layer_img.dtype}")
        print(f"   Min pixel : 0x{layer_img.min():08X}")
        print(f"   Max pixel : 0x{layer_img.max():08X}")

        # Extraire poids d'un pixel
        test_pixel = layer_img[256, 256]
        weights = extract_weights_from_pixel(test_pixel)

        print(f"\nPixel (256, 256) = 0x{test_pixel:08X}")
        print(f"   Poids : {weights}")
        print(f"   Somme : {weights.sum():.3f} (doit etre 1.0)")

        # Statistiques globales
        all_weights = extract_all_weights(layer_img)
        print(f"\nStatistiques globales (512x512)")
        print(f"   Shape : {all_weights.shape}")
        for i in range(7):
            usage = (all_weights[:, :, i] > 0).sum()
            pct = usage / (512*512) * 100
            print(f"   w{i} utilise : {usage:6d} pixels ({pct:5.1f}%)")

    else:
        print("Echec decodage")
        sys.exit(1)
