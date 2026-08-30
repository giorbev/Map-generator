#!/usr/bin/env python3
"""
Extraction des masques de texture complets pour toute une carte
Assemble toutes les tuiles et crée 7 masques globaux (un par layer)
Export en PNG 16-bit pour précision maximale
"""

import sys
import numpy as np
from pathlib import Path
from PIL import Image
from collections import defaultdict
import re

sys.path.insert(0, str(Path(__file__).parent))
from decode_layer_256 import decode_layer_256, extract_all_weights


def parse_tile_coords(filename: str):
    """
    Extrait les coordonnées de tuile depuis le nom de fichier

    Ex: "Eden_1234_layer.edds" → 1234
        "Terrain_5678_layer.edds" → 5678

    Returns:
        int: index de tuile, ou None si pas trouvé
    """
    match = re.search(r'_(\d+)_layer\.edds', filename)
    if match:
        return int(match.group(1))
    return None


def find_all_tiles(map_path: Path, pattern: str = "*_layer.edds"):
    """
    Trouve toutes les tuiles layer d'une carte

    Returns:
        dict: {tile_index: file_path}
    """
    tiles = {}

    for file_path in map_path.glob(pattern):
        tile_idx = parse_tile_coords(file_path.name)
        if tile_idx is not None:
            tiles[tile_idx] = file_path

    return tiles


def estimate_grid_size(tile_indices: list, tile_size: int = 256):
    """
    Estime la taille de la grille de tuiles

    Pour Eden: indices de 0 à ~2500
    Suppose que c'est une grille carrée ou rectangulaire

    Returns:
        (grid_width, grid_height, total_width, total_height)
    """
    max_idx = max(tile_indices)
    min_idx = min(tile_indices)
    n_tiles = len(tile_indices)

    # Essayer de deviner la structure de la grille
    # Hypothèse : grille carrée ou proche
    import math
    grid_size = int(math.ceil(math.sqrt(max_idx + 1)))

    # Vérifier si c'est une grille rectangulaire
    # (parfois les maps sont des rectangles, pas des carrés)

    print(f"\nAnalyse de la grille:")
    print(f"  Tuiles trouvées: {n_tiles}")
    print(f"  Index min: {min_idx}, max: {max_idx}")
    print(f"  Grille estimée: {grid_size}×{grid_size}")

    total_width = grid_size * tile_size
    total_height = grid_size * tile_size

    return grid_size, grid_size, total_width, total_height


def create_full_map_masks(map_name: str, tiles_path: Path, output_dir: Path,
                          use_16bit: bool = True, max_tiles: int = None):
    """
    Crée les masques complets de toute la carte

    Args:
        map_name: Nom de la carte (ex: "Eden", "Cain")
        tiles_path: Chemin vers le dossier .Data contenant les tuiles
        output_dir: Dossier de sortie
        use_16bit: True = PNG 16-bit, False = PNG 8-bit
        max_tiles: Limite le nombre de tuiles (pour tests), None = tout
    """
    print("="*80)
    print(f"EXTRACTION DES MASQUES COMPLETS - {map_name.upper()}")
    print("="*80)

    # Trouver toutes les tuiles
    print(f"\nRecherche des tuiles dans: {tiles_path}")
    tiles = find_all_tiles(tiles_path)

    if not tiles:
        print("ERREUR: Aucune tuile trouvée!")
        return False

    print(f"Tuiles trouvées: {len(tiles)}")

    # Limiter pour tests
    if max_tiles and len(tiles) > max_tiles:
        print(f"LIMITE: Traitement de {max_tiles} tuiles seulement")
        tiles = dict(list(tiles.items())[:max_tiles])

    # Estimer la taille de la grille
    tile_indices = list(tiles.keys())
    grid_w, grid_h, total_w, total_h = estimate_grid_size(tile_indices)

    tile_size = 256  # Taille d'une tuile

    print(f"\nTaille finale estimée: {total_w}×{total_h} pixels")
    print(f"Mémoire requise: ~{(total_w * total_h * 7 * 2) / (1024**2):.1f} MB (16-bit)")

    # Créer les 7 masques globaux
    dtype = np.uint16 if use_16bit else np.uint8
    max_value = 65535 if use_16bit else 255

    print(f"\nCréation des masques globaux ({dtype})...")

    # Utiliser un dict pour stocker seulement les tuiles non-vides
    # (économie de mémoire pour les grandes cartes avec beaucoup d'océan)
    layer_masks = {i: {} for i in range(7)}  # {layer: {tile_idx: data}}

    # Traiter chaque tuile
    print(f"\nTraitement des tuiles:")
    processed = 0
    errors = 0

    for tile_idx, tile_path in sorted(tiles.items()):
        processed += 1

        # Barre de progression
        if processed % 10 == 0 or processed == len(tiles):
            progress = processed / len(tiles) * 100
            print(f"  [{processed}/{len(tiles)}] {progress:.1f}% - {tile_path.name}",
                  end='\r' if processed < len(tiles) else '\n')

        # Décoder la tuile
        layer_img = decode_layer_256(tile_path)
        if layer_img is None:
            errors += 1
            continue

        # Extraire les poids
        weights = extract_all_weights(layer_img)  # (256, 256, 7)

        # Stocker chaque layer (si non vide)
        for layer_idx in range(7):
            layer_data = weights[:, :, layer_idx]

            # Seulement stocker si le layer est utilisé (optimisation mémoire)
            if layer_data.max() > 0.01:  # Seuil minimal
                # Convertir en uint8 ou uint16
                layer_masks[layer_idx][tile_idx] = (layer_data * max_value).astype(dtype)

    print(f"\nTuiles traitées: {processed}, erreurs: {errors}")

    # Assembler et sauvegarder chaque layer
    print(f"\nAssemblage et export des masques:")
    output_dir.mkdir(parents=True, exist_ok=True)

    for layer_idx in range(7):
        print(f"  Layer {layer_idx}...", end='')

        # Créer l'image finale
        final_mask = np.zeros((total_h, total_w), dtype=dtype)

        # Placer chaque tuile
        tiles_in_layer = layer_masks[layer_idx]

        if not tiles_in_layer:
            print(f" (vide, skippé)")
            continue

        for tile_idx, tile_data in tiles_in_layer.items():
            # Calculer la position de la tuile dans la grille
            # Hypothèse: grille de gauche à droite, haut en bas
            row = tile_idx // grid_w
            col = tile_idx % grid_w

            y_start = row * tile_size
            x_start = col * tile_size

            # Vérifier les limites
            if y_start + tile_size <= total_h and x_start + tile_size <= total_w:
                final_mask[y_start:y_start+tile_size, x_start:x_start+tile_size] = tile_data

        # Crop au contenu réel (enlever les bordures vides)
        # Trouver les limites du contenu non-nul
        rows_with_data = np.any(final_mask > 0, axis=1)
        cols_with_data = np.any(final_mask > 0, axis=0)

        if rows_with_data.any() and cols_with_data.any():
            y_min = np.argmax(rows_with_data)
            y_max = len(rows_with_data) - np.argmax(rows_with_data[::-1])
            x_min = np.argmax(cols_with_data)
            x_max = len(cols_with_data) - np.argmax(cols_with_data[::-1])

            cropped_mask = final_mask[y_min:y_max, x_min:x_max]
        else:
            cropped_mask = final_mask

        # Sauvegarder en PNG
        output_path = output_dir / f"{map_name}_layer_{layer_idx}.png"

        # PIL supporte 16-bit en mode 'I;16'
        if use_16bit:
            img = Image.fromarray(cropped_mask, mode='I;16')
        else:
            img = Image.fromarray(cropped_mask, mode='L')

        img.save(output_path)

        # Stats
        coverage = (cropped_mask > max_value * 0.1).sum() / cropped_mask.size * 100
        size_mb = cropped_mask.nbytes / (1024**2)

        print(f" OK {cropped_mask.shape[1]}×{cropped_mask.shape[0]} px, "
              f"coverage={coverage:.1f}%, {size_mb:.1f} MB")

    # Créer une visualisation composite RGB
    print(f"\nCréation de la visualisation RGB...")

    # Charger les 3 premiers layers
    rgb_img = np.zeros((total_h, total_w, 3), dtype=np.uint8)

    for channel, layer_idx in enumerate([0, 1, 2]):
        if layer_idx in layer_masks and layer_masks[layer_idx]:
            channel_data = np.zeros((total_h, total_w), dtype=np.uint8)

            for tile_idx, tile_data in layer_masks[layer_idx].items():
                row = tile_idx // grid_w
                col = tile_idx % grid_w
                y_start = row * tile_size
                x_start = col * tile_size

                if y_start + tile_size <= total_h and x_start + tile_size <= total_w:
                    # Convertir 16-bit → 8-bit pour RGB
                    tile_8bit = (tile_data.astype(np.float32) / max_value * 255).astype(np.uint8)
                    channel_data[y_start:y_start+tile_size, x_start:x_start+tile_size] = tile_8bit

            rgb_img[:, :, channel] = channel_data

    # Crop
    if rows_with_data.any() and cols_with_data.any():
        rgb_cropped = rgb_img[y_min:y_max, x_min:x_max, :]
    else:
        rgb_cropped = rgb_img

    rgb_path = output_dir / f"{map_name}_RGB_preview.png"
    rgb_pil = Image.fromarray(rgb_cropped, mode='RGB')
    rgb_pil.save(rgb_path)

    print(f"OK RGB preview: {rgb_cropped.shape[1]}×{rgb_cropped.shape[0]} px")

    # Résumé final
    print("\n" + "="*80)
    print("TERMINÉ")
    print("="*80)
    print(f"\nFichiers créés dans: {output_dir}")
    print(f"Format: PNG {'16-bit' if use_16bit else '8-bit'}")
    print(f"\nMasques globaux:")
    for i in range(7):
        path = output_dir / f"{map_name}_layer_{i}.png"
        if path.exists():
            size = path.stat().st_size / (1024**2)
            print(f"  - {path.name} ({size:.2f} MB)")

    print(f"  - {map_name}_RGB_preview.png (aperçu)")

    return True


def main():
    base_path = Path(r"h:\mod_enfusion\Arma Reforger_copie\addons\data\worlds\worlds")
    output_base = Path(r"H:\mod_enfusion\Travail_Analyse\Terrain")

    # Configuration
    MAP_NAME = "Eden"  # Changer pour "Cain" si besoin
    TILES_PATH = base_path / "Eden" / "Eden" / ".Data"
    OUTPUT_DIR = output_base / f"{MAP_NAME}_full_masks"
    USE_16BIT = True  # True = PNG 16-bit, False = PNG 8-bit
    MAX_TILES = None  # MODE COMPLET: toutes les tuiles

    print(f"Configuration:")
    print(f"  Carte: {MAP_NAME}")
    print(f"  Source: {TILES_PATH}")
    print(f"  Sortie: {OUTPUT_DIR}")
    print(f"  Format: {'16-bit' if USE_16BIT else '8-bit'} PNG")
    if MAX_TILES:
        print(f"  LIMITE TEST: {MAX_TILES} tuiles seulement")

    print("\nMode COMPLET: toutes les tuiles (~20-30 min)")

    create_full_map_masks(MAP_NAME, TILES_PATH, OUTPUT_DIR, USE_16BIT, MAX_TILES)


if __name__ == "__main__":
    main()
