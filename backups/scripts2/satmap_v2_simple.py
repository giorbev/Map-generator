"""
Generateur Satmap v2.0 SIMPLIFIE

Lit les layer.dds depuis .EditorData (pas de LZ4 !)
+ LRS2 depuis .Data/.ttile
= Satmap complete avec 100% couverture (1-7 textures)
"""

import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Optional
from tqdm import tqdm

# Import modules
from layer_dds_reader import read_layer_dds, extract_all_weights
from lrs2_parser import load_lrs2_from_ttile


def load_catalog(catalog_path: Path) -> Dict:
    """Charge le catalogue de textures enrichi"""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_material_color(mat_id: int, catalog: Dict, surfaces: List[str]) -> np.ndarray:
    """
    Retourne la couleur RGB d'un materiau

    Args:
        mat_id: ID global du materiau
        catalog: Catalogue enrichi
        surfaces: Liste globale des surfaces

    Returns:
        np.array([R, G, B], dtype=uint8)
    """
    # mat_id indexe la liste globale des surfaces
    if mat_id >= len(surfaces):
        return np.array([255, 0, 255], dtype=np.uint8)  # Magenta = erreur

    surface_name = surfaces[mat_id]

    # Chercher dans le catalogue
    if surface_name not in catalog:
        return np.array([255, 0, 255], dtype=np.uint8)

    entry = catalog[surface_name]

    # Utiliser le tint sRGB si disponible
    if 'tint_srgb' in entry and entry['tint_srgb']:
        r, g, b = entry['tint_srgb']
        return np.array([r, g, b], dtype=np.uint8)

    # Sinon couleur par defaut
    return np.array([128, 128, 128], dtype=np.uint8)


def generate_tile_satmap_v2(
    tile_id: int,
    editor_data_dir: Path,
    data_dir: Path,
    catalog: Dict,
    surfaces: List[str]
) -> Optional[np.ndarray]:
    """
    Genere la satmap d'une tuile (mode couleurs)

    Args:
        tile_id: Numero tuile
        editor_data_dir: Dossier .EditorData
        data_dir: Dossier .Data
        catalog: Catalogue enrichi
        surfaces: Liste globale surfaces

    Returns:
        np.array (512, 512, 3) uint8 RGB
    """
    # Fichiers necessaires
    layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.dds"
    ttile_path = data_dir / f"Terrain_{tile_id}.ttile"

    if not layer_path.exists() or not ttile_path.exists():
        return None

    # Charger layer.dds
    layer_img = read_layer_dds(layer_path)
    if layer_img is None:
        return None

    # Charger LRS2
    lrs2_blocks = load_lrs2_from_ttile(ttile_path)
    if lrs2_blocks is None:
        return None

    # Extraire poids (512, 512, 7)
    weights = extract_all_weights(layer_img)

    # Image resultat
    result = np.zeros((512, 512, 3), dtype=np.float32)

    # Pour chaque bloc (4x4 = 16 blocs)
    for by in range(4):
        for bx in range(4):
            mat_ids = lrs2_blocks.get((bx, by), [])

            if len(mat_ids) == 0:
                continue

            # Zone du bloc (128x128)
            x0 = bx * 128
            y0 = by * 128
            x1 = x0 + 128
            y1 = y0 + 128

            # Pour chaque materiau du bloc
            for i, mat_id in enumerate(mat_ids):
                if i >= 7:
                    break

                # Couleur du materiau
                color = get_material_color(mat_id, catalog, surfaces)

                # Poids du materiau pour cette zone
                w = weights[y0:y1, x0:x1, i]

                # Accumuler couleur ponderee
                result[y0:y1, x0:x1] += w[:, :, None] * color[None, None, :]

    # Convertir en uint8
    result = np.clip(result, 0, 255).astype(np.uint8)

    return result


def generate_satmap_v2_complete(
    terrain_dir: Path,
    catalog_path: Path,
    surfaces_list: List[str],
    output_path: Path,
    target_resolution: int = 4097
):
    """
    Genere la satmap complete

    Args:
        terrain_dir: Dossier Terrain/
        catalog_path: Chemin vers catalog.json
        surfaces_list: Liste globale des surfaces
        output_path: Chemin sortie satmap.png
        target_resolution: Resolution finale (4097 = 4k)
    """
    print("="*80)
    print("GENERATION SATMAP v2.0 - Pipeline simplifie .EditorData + LRS2")
    print("="*80)
    print(f"Resolution cible : {target_resolution}x{target_resolution}")
    print()

    editor_data_dir = terrain_dir / ".EditorData"
    data_dir = terrain_dir / ".Data"

    # Charger catalogue
    print("Chargement catalogue...")
    catalog = load_catalog(catalog_path)
    print(f"   OK {len(catalog)} surfaces\n")

    # Detecter nombre de tuiles
    layer_files = list(editor_data_dir.glob("Terrain_*_layer.dds"))
    num_tiles = len(layer_files)

    print(f"Detection tuiles : {num_tiles} fichiers layer.dds")

    # Determiner grille
    grid_size = int(np.sqrt(num_tiles))
    if grid_size * grid_size != num_tiles:
        print(f"Attention Nombre de tuiles non carre : {num_tiles}")
        grid_size = int(np.ceil(np.sqrt(num_tiles)))

    print(f"   Grille : {grid_size}x{grid_size}")
    print()

    # Canvas natif 512 px/tuile
    native_size = grid_size * 512
    print(f"Resolution native : {native_size}x{native_size}")
    print(f"   Downscale -> {target_resolution}x{target_resolution}")
    print()

    # Canvas
    canvas = np.zeros((native_size, native_size, 3), dtype=np.uint8)

    # Generer tuiles
    print("Generation tuiles...")
    for tile_id in tqdm(range(num_tiles)):
        # Position dans la grille
        tx = tile_id % grid_size
        ty = tile_id // grid_size

        # Generer tuile
        tile_img = generate_tile_satmap_v2(
            tile_id, editor_data_dir, data_dir, catalog, surfaces_list
        )

        if tile_img is None:
            continue

        # Placer dans canvas
        y0 = ty * 512
        x0 = tx * 512
        canvas[y0:y0+512, x0:x0+512] = tile_img

    print()

    # Downscale
    print(f"Downscale {native_size}x{native_size} -> {target_resolution}x{target_resolution}...")
    satmap = cv2.resize(canvas, (target_resolution, target_resolution), interpolation=cv2.INTER_AREA)

    # Sauvegarder
    print(f"Sauvegarde : {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR))

    print()
    print("="*80)
    print("OK SATMAP v2.0 GENEREE !")
    print("="*80)
    print(f"Fichier : {output_path}")
    print(f"Taille : {satmap.shape[1]}x{satmap.shape[0]}")


# Test
if __name__ == "__main__":
    # Configuration test
    terrain_dir = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain")
    catalog_path = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")
    output_path = Path(r"h:\logiciel perso\Map generator\output\satmap_v2_final.png")

    # Liste globale surfaces (a charger depuis la config du monde)
    # Pour le test, on utilise les surfaces du catalogue
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    surfaces_list = list(catalog.keys())

    # Tester sur 1 tuile d'abord
    print("TEST 1 TUILE\n")

    editor_data_dir = terrain_dir / ".EditorData"
    data_dir = terrain_dir / ".Data"

    tile_img = generate_tile_satmap_v2(
        0, editor_data_dir, data_dir, catalog, surfaces_list
    )

    if tile_img is not None:
        cv2.imwrite("test_tile_0_v2.png", cv2.cvtColor(tile_img, cv2.COLOR_RGB2BGR))
        print(f"OK Tuile 0 generee : test_tile_0_v2.png\n")
    else:
        print("Echec generation tuile 0\n")

    # Generer satmap complete
    print("\n" + "="*80)
    print("GENERATION SATMAP COMPLETE")
    print("="*80 + "\n")

    generate_satmap_v2_complete(
        terrain_dir,
        catalog_path,
        surfaces_list,
        output_path,
        target_resolution=4097
    )
