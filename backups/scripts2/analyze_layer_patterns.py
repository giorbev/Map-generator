#!/usr/bin/env python3
"""
Analyse des patterns de placement de layers de terrain
Détecte si le placement est manuel ou procédural
"""

import sys
import numpy as np
from pathlib import Path
from edds_decoder import decode_edds_layer, extract_all_weights


def calculate_slope_map(layer_img: np.ndarray, pixel_size: float = 1.0) -> np.ndarray:
    """
    Calcule une carte de pente approximative depuis les poids de layer

    Note: Ceci est une approximation car on n'a pas la vraie heightmap
    On suppose que certains layers (rock) = haute altitude
    """
    # Supposer que layer avec rock = altitude élevée (très approximatif)
    # On utilise le gradient des poids comme proxy
    dy, dx = np.gradient(layer_img.astype(float))
    slope_approx = np.sqrt(dx**2 + dy**2)
    return slope_approx


def analyze_layer_distribution(layer_path: Path, sample_name: str = "Unknown"):
    """
    Analyse la distribution des poids d'un layer map
    """
    print(f"\n{'='*60}")
    print(f"Analyse: {sample_name}")
    print(f"Fichier: {layer_path.name}")
    print(f"{'='*60}")

    # Décoder
    layer_img = decode_edds_layer(layer_path)
    if layer_img is None:
        print("ERREUR: Échec décodage")
        return None

    # Extraire tous les poids
    weights = extract_all_weights(layer_img)
    h, w, n_layers = weights.shape

    print(f"\nDimensions: {h}×{w}, {n_layers} layers")

    # Statistiques par layer
    print(f"\n--- Distribution des layers ---")
    for i in range(n_layers):
        layer_weights = weights[:, :, i]

        # Pixels où ce layer est dominant (weight > 0.5)
        dominant = (layer_weights > 0.5).sum()

        # Pixels où ce layer est présent (weight > 0.1)
        present = (layer_weights > 0.1).sum()

        # Stats
        mean_weight = layer_weights.mean()
        std_weight = layer_weights.std()
        max_weight = layer_weights.max()

        print(f"Layer {i}: mean={mean_weight:.3f} std={std_weight:.3f} "
              f"dominant={dominant:6d} ({dominant/(h*w)*100:5.1f}%) "
              f"present={present:6d} ({present/(h*w)*100:5.1f}%)")

    # Analyser les transitions
    print(f"\n--- Analyse des transitions ---")

    # Calculer la variation spatiale (lissé ou abrupt ?)
    for i in range(n_layers):
        layer_weights = weights[:, :, i]

        # Gradient (changement spatial)
        dy, dx = np.gradient(layer_weights)
        gradient_magnitude = np.sqrt(dx**2 + dy**2)

        mean_gradient = gradient_magnitude.mean()
        max_gradient = gradient_magnitude.max()

        # Si mean_gradient faible = transitions lisses (manuel)
        # Si mean_gradient élevé = transitions abruptes (procédural)
        transition_type = "Lisses (manuel?)" if mean_gradient < 0.02 else "Abruptes (auto?)"

        print(f"Layer {i}: gradient moyen={mean_gradient:.4f} max={max_gradient:.4f} → {transition_type}")

    # Détecter des patterns réguliers
    print(f"\n--- Détection de patterns ---")

    # Vérifier si certains layers ont une distribution uniforme (procédural)
    # ou organique (manuel)
    for i in range(n_layers):
        layer_weights = weights[:, :, i]

        # Histogramme des poids
        hist, bins = np.histogram(layer_weights, bins=10, range=(0, 1))

        # Si distribution uniforme = probablement procédural
        # Si pic à 0 ou 1 = probablement manuel (tout ou rien)
        entropy = -np.sum((hist / hist.sum()) * np.log2((hist / hist.sum()) + 1e-10))

        # Entropy max = log2(10) = 3.32 (uniforme)
        # Entropy min = 0 (un seul bin)
        uniformity = entropy / 3.32

        pattern_type = "Uniforme (auto?)" if uniformity > 0.7 else "Concentré (manuel?)"

        print(f"Layer {i}: entropy={entropy:.2f} uniformité={uniformity:.2f} → {pattern_type}")

    return weights


def compare_maps(cain_path: Path, eden_path: Path):
    """
    Compare les patterns entre Cain et Eden
    """
    print("\n" + "="*60)
    print("COMPARAISON CAIN vs EDEN")
    print("="*60)

    print("\n>>> CAIN <<<")
    cain_weights = analyze_layer_distribution(cain_path, "Cain Tile 0")

    print("\n>>> EDEN <<<")
    eden_weights = analyze_layer_distribution(eden_path, "Eden Tile 0")

    if cain_weights is not None and eden_weights is not None:
        print("\n" + "="*60)
        print("COMPARAISON DES PATTERNS")
        print("="*60)

        # Comparer les distributions
        for i in range(7):
            cain_mean = cain_weights[:, :, i].mean()
            eden_mean = eden_weights[:, :, i].mean()

            diff = abs(cain_mean - eden_mean)

            print(f"Layer {i}: Cain={cain_mean:.3f} Eden={eden_mean:.3f} diff={diff:.3f}")

        print("\nSi les patterns sont TRÈS similaires entre les cartes,")
        print("cela suggère un système automatique commun.")
        print("\nSi les patterns sont DIFFÉRENTS,")
        print("cela suggère un placement manuel adapté à chaque carte.")


if __name__ == "__main__":
    base_path = Path(r"h:\mod_enfusion\Arma Reforger_copie\addons\data\worlds\worlds")

    # Fichiers à analyser (utiliser les premières tuiles disponibles)
    cain_tile = base_path / "Cain" / "Terrain" / ".Data" / "Terrain_1008_layer.edds"
    eden_tile = base_path / "Eden" / "Eden" / ".Data" / "Eden_0_layer.edds"

    if not cain_tile.exists():
        print(f"ERREUR: Fichier Cain non trouve: {cain_tile}")
        sys.exit(1)

    if not eden_tile.exists():
        print(f"ERREUR: Fichier Eden non trouve: {eden_tile}")
        sys.exit(1)

    # Comparaison
    compare_maps(cain_tile, eden_tile)

    print("\n" + "="*60)
    print("CONCLUSION")
    print("="*60)
    print("""
Si on observe :
- Transitions LISSES + distributions CONCENTRÉES → Placement MANUEL
- Transitions ABRUPTES + distributions UNIFORMES → Placement AUTOMATIQUE
- Patterns SIMILAIRES entre Cain/Eden → Système COMMUN (auto)
- Patterns DIFFÉRENTS entre Cain/Eden → Travail ARTISTIQUE (manuel)
    """)
