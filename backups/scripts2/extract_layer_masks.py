#!/usr/bin/env python3
"""
Extraction des masques de texture (layer maps) en images PNG
Permet de visualiser comment les layers sont organisés
"""

import sys
import numpy as np
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
try:
    from edds_decoder import decode_edds_layer, extract_all_weights
except:
    # Fallback pour format 256×256
    from decode_layer_256 import decode_layer_256 as decode_edds_layer, extract_all_weights


def save_layer_as_grayscale(layer_weights: np.ndarray, output_path: Path, layer_idx: int):
    """
    Sauvegarde un layer individuel en PNG niveau de gris

    Args:
        layer_weights: (H, W) array de poids [0, 1]
        output_path: Chemin de sortie
        layer_idx: Index du layer (0-6)
    """
    # Convertir [0, 1] → [0, 255]
    gray_img = (layer_weights * 255).astype(np.uint8)

    # Sauvegarder en PNG
    img = Image.fromarray(gray_img, mode='L')
    img.save(output_path)

    print(f"  Layer {layer_idx} sauvegarde: {output_path.name}")


def create_composite_visualization(weights: np.ndarray, output_path: Path):
    """
    Crée une visualisation composite de tous les layers

    Layout:
    L0  L1  L2  L3
    L4  L5  L6  ALL
    """
    h, w, n_layers = weights.shape

    # Créer une grille 2×4
    grid_h = h * 2
    grid_w = w * 4
    composite = np.zeros((grid_h, grid_w), dtype=np.uint8)

    # Placer chaque layer
    positions = [
        (0, 0), (0, 1), (0, 2), (0, 3),  # Ligne 1
        (1, 0), (1, 1), (1, 2),          # Ligne 2
    ]

    for layer_idx in range(7):
        row, col = positions[layer_idx]
        y_start = row * h
        y_end = (row + 1) * h
        x_start = col * w
        x_end = (col + 1) * w

        # Convertir en niveaux de gris
        gray = (weights[:, :, layer_idx] * 255).astype(np.uint8)
        composite[y_start:y_end, x_start:x_end] = gray

    # Position (1, 3) : Visualisation "ALL" (layer dominant par pixel)
    all_viz = np.zeros((h, w), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            # Trouver le layer dominant à ce pixel
            dominant_layer = np.argmax(weights[y, x, :])
            # Couleur = index du layer * 36 (pour répartir sur 0-255)
            all_viz[y, x] = dominant_layer * 36

    composite[h:h*2, w*3:w*4] = all_viz

    # Sauvegarder
    img = Image.fromarray(composite, mode='L')
    img.save(output_path)

    print(f"\nComposite sauvegarde: {output_path.name}")


def create_rgb_visualization(weights: np.ndarray, output_path: Path):
    """
    Crée une visualisation RGB des 3 premiers layers
    R = Layer 0, G = Layer 1, B = Layer 2
    """
    h, w, _ = weights.shape

    rgb_img = np.zeros((h, w, 3), dtype=np.uint8)
    rgb_img[:, :, 0] = (weights[:, :, 0] * 255).astype(np.uint8)  # R = L0
    rgb_img[:, :, 1] = (weights[:, :, 1] * 255).astype(np.uint8)  # G = L1
    rgb_img[:, :, 2] = (weights[:, :, 2] * 255).astype(np.uint8)  # B = L2

    img = Image.fromarray(rgb_img, mode='RGB')
    img.save(output_path)

    print(f"RGB visualisation sauvegardee: {output_path.name}")


def extract_masks_from_tile(tile_path: Path, output_dir: Path, tile_name: str):
    """
    Extrait tous les masques d'une tuile et les sauvegarde
    """
    print(f"\n{'='*60}")
    print(f"Extraction: {tile_name}")
    print(f"{'='*60}")

    # Décoder (essayer avec le décodeur 256×256 si nécessaire)
    layer_img = None
    try:
        from edds_decoder import decode_edds_layer as decode_512
        layer_img = decode_512(tile_path)
    except:
        pass

    if layer_img is None:
        try:
            from decode_layer_256 import decode_layer_256
            layer_img = decode_layer_256(tile_path)
        except Exception as e:
            print(f"ERREUR: Echec decodage - {e}")
            return False

    if layer_img is None:
        print("ERREUR: Echec decodage")
        return False

    # Extraire les poids
    weights = extract_all_weights(layer_img)
    h, w, n_layers = weights.shape

    print(f"Dimensions: {h}×{w}, {n_layers} layers")

    # Créer le dossier de sortie pour cette tuile
    tile_output_dir = output_dir / tile_name.replace('.edds', '')
    tile_output_dir.mkdir(parents=True, exist_ok=True)

    # Sauvegarder chaque layer individuellement
    print("\nExtraction des layers individuels:")
    for layer_idx in range(n_layers):
        output_path = tile_output_dir / f"layer_{layer_idx}.png"
        save_layer_as_grayscale(weights[:, :, layer_idx], output_path, layer_idx)

    # Créer la visualisation composite
    composite_path = tile_output_dir / "composite_all_layers.png"
    create_composite_visualization(weights, composite_path)

    # Créer la visualisation RGB
    rgb_path = tile_output_dir / "rgb_L0_L1_L2.png"
    create_rgb_visualization(weights, rgb_path)

    # Statistiques
    print("\n--- Statistiques ---")
    for layer_idx in range(n_layers):
        layer_weights = weights[:, :, layer_idx]
        coverage = (layer_weights > 0.1).sum() / (h * w) * 100
        mean_weight = layer_weights.mean()
        max_weight = layer_weights.max()

        print(f"Layer {layer_idx}: coverage={coverage:5.1f}% mean={mean_weight:.3f} max={max_weight:.3f}")

    return True


def main():
    base_path = Path(r"h:\mod_enfusion\Arma Reforger_copie\addons\data\worlds\worlds")
    output_base = Path(r"H:\mod_enfusion\Travail_Analyse\Terrain")

    # Créer le dossier de sortie
    output_base.mkdir(parents=True, exist_ok=True)

    print("="*80)
    print("EXTRACTION DES MASQUES DE TEXTURE")
    print("="*80)
    print("\nCarte: EDEN")
    print("Format: PNG niveaux de gris (0=noir, 255=blanc)")
    print("Blanc = layer présent/dominant, Noir = layer absent")

    # Extraire plusieurs tuiles d'Eden pour comparaison
    eden_tiles = [
        "Eden_0_layer.edds",      # Tuile 0
        "Eden_1000_layer.edds",   # Tuile 1000
        "Eden_1500_layer.edds",   # Tuile 1500 (milieu)
        "Eden_2000_layer.edds",   # Tuile 2000
    ]

    success_count = 0

    for tile_name in eden_tiles:
        tile_path = base_path / "Eden" / "Eden" / ".Data" / tile_name

        if not tile_path.exists():
            print(f"\n[SKIP] {tile_name} - non trouve")
            continue

        if extract_masks_from_tile(tile_path, output_base / "Eden_masks", tile_name):
            success_count += 1

    # Résumé
    print("\n" + "="*80)
    print("RÉSUMÉ")
    print("="*80)
    print(f"\nTuiles traitees: {success_count}/{len(eden_tiles)}")
    print(f"\nFichiers sauvegardes dans: {output_base / 'Eden_masks'}")
    print("\nPour chaque tuile:")
    print("  - layer_0.png à layer_6.png : Masques individuels (niveaux de gris)")
    print("  - composite_all_layers.png : Tous les layers en grille 2×4")
    print("  - rgb_L0_L1_L2.png : RGB des 3 premiers layers")
    print("\nAnalyse visuelle:")
    print("  - Transitions LISSES = Peinture manuelle ou blending artistique")
    print("  - Transitions NETTES = Masques procéduraux avec seuils")
    print("  - Patterns GÉOMÉTRIQUES = Règles automatiques (slope, altitude)")
    print("  - Patterns ORGANIQUES = Travail manuel")


if __name__ == "__main__":
    main()
