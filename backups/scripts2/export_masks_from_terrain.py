"""
Export des masques de textures depuis un terrain Reforger
Reconstruit un masque PNG pour chaque matériau utilisé
"""

import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm

# Import modules existants
from layer_dds_reader import read_layer_dds, extract_all_weights
from lrs2_parser import load_lrs2_from_ttile, get_tile_coords_from_ttile
from terrain_terr_reader import read_mats_from_terr


def export_material_masks(
    terrain_dir: Path,
    terr_file: Path,
    output_dir: Path,
    resolution: int = 4097
):
    """
    Exporte un masque PNG pour chaque matériau utilisé dans le terrain

    Args:
        terrain_dir: Dossier Terrain/
        terr_file: Chemin vers Terrain.terr
        output_dir: Dossier de sortie pour les masques
        resolution: Résolution finale des masques (défaut 4097)
    """
    print("="*80)
    print("EXPORT MASQUES DEPUIS TERRAIN REFORGER")
    print("="*80)

    editor_data_dir = terrain_dir / ".EditorData"
    data_dir = terrain_dir / ".Data"

    # 1. Charger liste des matériaux depuis Terrain.terr
    print("\n1. Chargement liste matériaux...")
    mats = read_mats_from_terr(terr_file)
    surfaces = [e["emat"] for e in mats]
    print(f"   {len(surfaces)} matériaux définis")

    # 2. Scanner toutes les tuiles pour détecter matériaux utilisés
    print("\n2. Scan des tuiles...")
    ttile_files = sorted(data_dir.glob("Terrain_*.ttile"))
    print(f"   {len(ttile_files)} fichiers .ttile détectés")

    # Détecter coordonnées et matériaux utilisés
    tile_data = {}  # {tile_id: (tile_x, tile_y)}
    material_usage = {}  # {mat_id: set(tile_ids)}

    for ttile in tqdm(ttile_files, desc="   Analyse LRS2"):
        # Extraire tile_id
        parts = ttile.stem.split('_')
        if len(parts) < 2:
            continue
        try:
            tile_id = int(parts[1])
        except ValueError:
            continue

        # Lire coordonnées
        coords = get_tile_coords_from_ttile(ttile)
        if coords is None:
            continue

        tile_data[tile_id] = coords

        # Lire LRS2
        lrs2_blocks = load_lrs2_from_ttile(ttile)
        if lrs2_blocks is None:
            continue

        # Collecter matériaux utilisés dans cette tuile
        for mat_ids in lrs2_blocks.values():
            for mat_id in mat_ids:
                if mat_id not in material_usage:
                    material_usage[mat_id] = set()
                material_usage[mat_id].add(tile_id)

    print(f"   {len(material_usage)} matériaux utilisés sur {len(surfaces)} définis")

    # 3. Déterminer grille
    all_coords = list(tile_data.values())
    max_x = max(x for x, y in all_coords)
    max_y = max(y for x, y in all_coords)
    grid_width = max_x + 1
    grid_height = max_y + 1

    canvas_width = grid_width * 512
    canvas_height = grid_height * 512

    print(f"\n3. Grille terrain: {grid_width}×{grid_height} tuiles")
    print(f"   Canvas natif: {canvas_width}×{canvas_height} px")
    print(f"   Résolution cible: {resolution}×{resolution} px")

    # 4. Créer dossier de sortie
    output_dir.mkdir(parents=True, exist_ok=True)

    # 5. Exporter chaque matériau
    print(f"\n4. Export des masques...")

    for mat_id in sorted(material_usage.keys()):
        if mat_id >= len(surfaces):
            continue

        mat_name = surfaces[mat_id]
        tile_ids = material_usage[mat_id]

        print(f"\n   [{mat_id:2d}] {mat_name} ({len(tile_ids)} tuiles)")

        # Canvas pour ce matériau (initialisé à 0 = noir)
        canvas = np.zeros((canvas_height, canvas_width), dtype=np.float32)

        # Parcourir les tuiles utilisant ce matériau
        for tile_id in tqdm(tile_ids, desc=f"      Tuiles", leave=False):
            # Coordonnées tuile
            if tile_id not in tile_data:
                continue
            tx, ty = tile_data[tile_id]

            # Lire layer.dds
            layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.dds"
            if not layer_path.exists():
                continue

            layer_img = read_layer_dds(layer_path)
            if layer_img is None:
                continue

            # Lire LRS2
            ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
            lrs2_blocks = load_lrs2_from_ttile(ttile_path)
            if lrs2_blocks is None:
                continue

            # Extraire poids
            weights = extract_all_weights(layer_img)  # (512, 512, 6) ou (512, 512, 7)

            # Canvas tuile
            tile_canvas = np.zeros((512, 512), dtype=np.float32)

            # Pour chaque bloc (4×4)
            for by in range(4):
                for bx in range(4):
                    mat_ids = lrs2_blocks.get((bx, by), [])

                    if mat_id not in mat_ids:
                        continue

                    # Position du matériau dans la liste du bloc
                    mat_idx = mat_ids.index(mat_id)

                    # Zone du bloc (128×128)
                    x0 = bx * 128
                    y0 = by * 128
                    x1 = x0 + 128
                    y1 = y0 + 128

                    raw = weights[y0:y1, x0:x1, :]

                    # Extraire poids selon position
                    if mat_idx == 0:
                        # Matériau de base (w0)
                        if raw.shape[2] == 6:
                            # w0 implicite = 1 - sum(w1..w6)
                            w = np.clip(1.0 - raw.sum(axis=-1), 0, 1.0)
                        else:
                            # w0 explicite dans canal 0
                            w = raw[:, :, 0]
                    else:
                        # Matériaux explicites (w1..w6)
                        if raw.shape[2] == 6:
                            # w1=canal 0, w2=canal 1...
                            w = raw[:, :, mat_idx - 1]
                        else:
                            # w1=canal 1, w2=canal 2...
                            w = raw[:, :, mat_idx]

                    # Placer dans canvas tuile
                    tile_canvas[y0:y1, x0:x1] = w

            # Placer tuile dans canvas global
            y0 = ty * 512
            x0 = tx * 512

            if y0 >= 0 and y0 + 512 <= canvas.shape[0] and x0 + 512 <= canvas.shape[1]:
                canvas[y0:y0+512, x0:x0+512] = tile_canvas

        # Flip vertical
        canvas = np.flip(canvas, axis=0)

        # Convertir en 0-255
        mask = (canvas * 255).astype(np.uint8)

        # Downscale si nécessaire
        if canvas_width != resolution or canvas_height != resolution:
            mask = cv2.resize(mask, (resolution, resolution), interpolation=cv2.INTER_AREA)

        # Sauvegarder
        output_name = f"mask_{mat_name.replace('.emat', '')}.png"
        output_path = output_dir / output_name
        cv2.imwrite(str(output_path), mask)

    print("\n" + "="*80)
    print(f"EXPORT TERMINE: {len(material_usage)} masques exportés")
    print(f"Dossier: {output_dir}")
    print("="*80)


if __name__ == "__main__":
    # Configuration pour Zimnitrita
    terrain_dir = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
    terr_file = terrain_dir / "Terrain.terr"
    output_dir = Path(r"h:\logiciel perso\Map generator\data\projects\Zimnitrita\exported_masks")

    export_material_masks(
        terrain_dir=terrain_dir,
        terr_file=terr_file,
        output_dir=output_dir,
        resolution=4097
    )
