#!/usr/bin/env python3
"""
Détection du workflow de placement des textures de terrain
Analyse l'ordre des layers pour détecter si c'est procédural ou manuel
"""

import sys
import numpy as np
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).parent))
from edds_decoder import decode_edds_layer, extract_all_weights
from material_colors_loader import MaterialColorDB


def identify_dominant_material_per_layer(weights: np.ndarray, threshold: float = 0.3):
    """
    Pour chaque layer, identifie quel est le matériau dominant dans cette tuile

    Args:
        weights: (H, W, 7) - poids des 7 layers
        threshold: Seuil pour considérer un layer comme "présent"

    Returns:
        dict: {layer_idx: coverage_percentage}
    """
    h, w, n_layers = weights.shape
    total_pixels = h * w

    layer_info = {}
    for layer_idx in range(n_layers):
        layer_weights = weights[:, :, layer_idx]

        # Pourcentage de pixels où ce layer est présent (weight > threshold)
        present_pixels = (layer_weights > threshold).sum()
        coverage = (present_pixels / total_pixels) * 100

        # Poids moyen du layer
        mean_weight = layer_weights.mean()

        layer_info[layer_idx] = {
            'coverage': coverage,
            'mean_weight': mean_weight,
            'is_significant': coverage > 1.0  # Plus de 1% de la tuile
        }

    return layer_info


def analyze_tile(tile_path: Path):
    """Analyse une tuile et retourne les infos de layers"""
    layer_img = decode_edds_layer(tile_path)
    if layer_img is None:
        return None

    weights = extract_all_weights(layer_img)
    layer_info = identify_dominant_material_per_layer(weights)

    return layer_info


def compare_layer_orders(tiles_data: dict):
    """
    Compare l'ordre des layers entre plusieurs tuiles

    Si toutes les tuiles ont le même ordre → Procédural
    Si l'ordre varie → Manuel
    """
    print("\n" + "="*80)
    print("ANALYSE DE L'ORDRE DES LAYERS")
    print("="*80)

    # Pour chaque layer (0-6), voir quelles tuiles l'utilisent significativement
    layer_usage = {i: [] for i in range(7)}

    for tile_name, layer_info in tiles_data.items():
        if layer_info is None:
            continue

        for layer_idx, info in layer_info.items():
            if info['is_significant']:
                layer_usage[layer_idx].append({
                    'tile': tile_name,
                    'coverage': info['coverage'],
                    'mean_weight': info['mean_weight']
                })

    # Analyser les patterns
    print("\n--- Usage des layers par tuile ---\n")

    for layer_idx in range(7):
        tiles_using = layer_usage[layer_idx]
        n_tiles = len(tiles_using)
        total_tiles = len([t for t in tiles_data.values() if t is not None])

        usage_pct = (n_tiles / total_tiles * 100) if total_tiles > 0 else 0

        print(f"Layer {layer_idx}: utilisé par {n_tiles}/{total_tiles} tuiles ({usage_pct:.1f}%)")

        if n_tiles > 0:
            # Moyenne de coverage
            avg_coverage = np.mean([t['coverage'] for t in tiles_using])
            avg_weight = np.mean([t['mean_weight'] for t in tiles_using])

            print(f"  → Coverage moyen: {avg_coverage:.1f}%, Poids moyen: {avg_weight:.3f}")

    # Identifier les patterns
    print("\n" + "="*80)
    print("DÉTECTION DU PATTERN")
    print("="*80)

    # Compter combien de layers sont utilisés par tuile (en moyenne)
    layers_per_tile = []
    for tile_name, layer_info in tiles_data.items():
        if layer_info is None:
            continue

        n_significant = sum(1 for info in layer_info.values() if info['is_significant'])
        layers_per_tile.append(n_significant)

    if layers_per_tile:
        avg_layers = np.mean(layers_per_tile)
        std_layers = np.std(layers_per_tile)

        print(f"\nNombre moyen de layers par tuile: {avg_layers:.1f} ± {std_layers:.1f}")

        # Si écart-type faible → Cohérence → Procédural
        if std_layers < 1.0:
            print("→ Écart-type FAIBLE: Cohérence élevée → Probablement PROCÉDURAL")
        else:
            print("→ Écart-type ÉLEVÉ: Variabilité importante → Probablement MANUEL")

    # Analyser la distribution des layers
    print("\n--- Analyse de distribution ---\n")

    # Layer 0 (dernier peint) devrait être le plus utilisé si workflow cohérent
    l0_usage = len(layer_usage[0])
    l6_usage = len(layer_usage[6])

    print(f"Layer 0 (dernier peint): {l0_usage} tuiles")
    print(f"Layer 6 (premier peint): {l6_usage} tuiles")

    if l0_usage > l6_usage * 1.5:
        print("→ Layer 0 dominant: Workflow cohérent → PROCÉDURAL probable")
    elif l6_usage > l0_usage * 1.5:
        print("→ Layer 6 dominant: Pattern inversé → VÉRIFIER l'interprétation")
    else:
        print("→ Distribution équilibrée: Pas de pattern clair → MANUEL possible")

    return layer_usage


def main():
    base_path = Path(r"h:\mod_enfusion\Arma Reforger_copie\addons\data\worlds\worlds")

    # Analyser plusieurs tuiles de Cain (tiles différentes pour voir la variabilité)
    cain_tiles = [
        "Terrain_1018_layer.edds",
        "Terrain_1019_layer.edds",
        "Terrain_1020_layer.edds",
        "Terrain_1050_layer.edds",
        "Terrain_1100_layer.edds",
        "Terrain_1200_layer.edds",
    ]

    print("="*80)
    print("DÉTECTION DU WORKFLOW DE PLACEMENT DES TEXTURES")
    print("="*80)
    print("\nCarte: CAIN")
    print(f"Tuiles analysées: {len(cain_tiles)}")

    tiles_data = {}

    for tile_name in cain_tiles:
        tile_path = base_path / "Cain" / "Terrain" / ".Data" / tile_name

        if not tile_path.exists():
            print(f"  [SKIP] {tile_name} - non trouvé")
            continue

        print(f"  [OK] Analyse de {tile_name}...", end="")
        layer_info = analyze_tile(tile_path)

        if layer_info:
            tiles_data[tile_name] = layer_info
            print(" ✓")
        else:
            print(" ✗ (échec décodage)")
            tiles_data[tile_name] = None

    # Comparer les patterns
    if tiles_data:
        layer_usage = compare_layer_orders(tiles_data)

        # Conclusion
        print("\n" + "="*80)
        print("CONCLUSION")
        print("="*80)
        print("""
Si TOUTES les tuiles ont un pattern similaire:
  → Les masques procéduraux ont été appliqués dans un ordre FIXE
  → Workflow: Masques automatiques → Import → Retouches manuelles

Si les tuiles ont des patterns VARIABLES:
  → Chaque zone a été peinte dans un ordre différent
  → Workflow: Peinture manuelle pure

Votre hypothèse: "Les masques sont appliqués dans un ordre fixe,
puis retouches manuelles pour les détails"
        """)


if __name__ == "__main__":
    main()
