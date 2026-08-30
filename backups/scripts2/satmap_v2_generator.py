"""
Générateur Satmap v2.0 - Pipeline layer.edds + LRS2

Lit les vrais poids GPU depuis layer.edds (supporte 1-7 textures)
Plus de trous comme avec QTRE !
"""

import sys
import io
import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm

# Imports modules custom
from edds_decoder import decode_edds_layer, extract_all_weights
from lrs2_parser import load_lrs2_from_ttile

# Désactivé pour compatibilité Streamlit
# sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def load_catalog(catalog_path: Path) -> Dict:
    """Charge le catalogue de textures enrichi"""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_material_color(mat_id: int, catalog: Dict, surfaces: List[str]) -> np.ndarray:
    """
    Retourne la couleur RGB d'un matériau

    Args:
        mat_id: ID global du matériau
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

    # Sinon couleur par défaut
    return np.array([128, 128, 128], dtype=np.uint8)


def load_material_texture(
    mat_id: int,
    catalog: Dict,
    surfaces: List[str],
    textures_root: Path
) -> Optional[np.ndarray]:
    """
    Charge la texture middle BCR d'un matériau

    Returns:
        np.array (H, W, 3) uint8 RGB, ou None
    """
    if mat_id >= len(surfaces):
        return None

    surface_name = surfaces[mat_id]

    if surface_name not in catalog:
        return None

    entry = catalog[surface_name]

    if 'middle_bcr' not in entry:
        return None

    middle_bcr = entry['middle_bcr']

    # Chercher le fichier texture
    texture_path = find_texture_file(textures_root, middle_bcr)

    if texture_path is None:
        return None

    # Charger image
    try:
        img = cv2.imread(str(texture_path))
        if img is None:
            return None
        # Convertir BGR → RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return img
    except:
        return None


def find_texture_file(textures_root: Path, middle_bcr: str) -> Optional[Path]:
    """
    Cherche un fichier texture

    Args:
        textures_root: Racine des textures
        middle_bcr: Nom fichier (ex: "Dirt_01_Middle_BCR.jpg")

    Returns:
        Path complet ou None
    """
    # Extraire nom base si path relatif
    if "/" in middle_bcr or "\\" in middle_bcr:
        middle_bcr = middle_bcr.split("/")[-1].split("\\")[-1]

    # Retirer extension
    base_name = middle_bcr.rsplit(".", 1)[0]

    # Chercher avec extensions possibles
    for ext in ['.jpg', '.png', '.jpeg']:
        # Chercher dans Vanilla
        vanilla_path = textures_root / "Vanilla" / "textures" / (base_name + ext)
        if vanilla_path.exists():
            return vanilla_path

        # Chercher dans Customs
        customs_path = textures_root / "Customs" / (base_name + ext)
        if customs_path.exists():
            return customs_path

    return None


def apply_tint_to_texture(texture: np.ndarray, tint_rgb: Tuple[int, int, int]) -> np.ndarray:
    """
    Applique un tint à une texture

    Args:
        texture: (H, W, 3) uint8
        tint_rgb: (R, G, B) uint8

    Returns:
        Texture tintée (H, W, 3) uint8
    """
    tint = np.array(tint_rgb, dtype=np.float32) / 255.0
    texture_f = texture.astype(np.float32) / 255.0

    # Multiplier
    result = texture_f * tint[None, None, :]

    # Reconvertir
    result = np.clip(result * 255, 0, 255).astype(np.uint8)

    return result


def generate_tile_satmap_colors(
    tile_id: int,
    data_dir: Path,
    catalog: Dict,
    surfaces: List[str],
    target_size: int = 512
) -> Optional[np.ndarray]:
    """
    Génère la satmap d'une tuile en mode couleurs unies (rapide)

    Args:
        tile_id: Numéro tuile
        data_dir: Dossier .Data
        catalog: Catalogue enrichi
        surfaces: Liste globale surfaces
        target_size: Taille sortie (512 par défaut)

    Returns:
        np.array (target_size, target_size, 3) uint8
    """
    ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
    layer_path = data_dir / f"Terrain_{tile_id}_layer.edds"

    if not ttile_path.exists() or not layer_path.exists():
        return None

    # Charger LRS2
    lrs2_blocks = load_lrs2_from_ttile(ttile_path)
    if lrs2_blocks is None:
        return None

    # Charger layer.edds
    layer_img = decode_edds_layer(layer_path)
    if layer_img is None:
        return None

    # Extraire poids (512, 512, 7)
    weights = extract_all_weights(layer_img)

    # Image résultat
    result = np.zeros((512, 512, 3), dtype=np.float32)

    # Pour chaque bloc
    for by in range(4):
        for bx in range(4):
            mat_ids = lrs2_blocks.get((bx, by), [])

            if len(mat_ids) == 0:
                continue

            # Zone du bloc (128×128)
            x0 = bx * 128
            y0 = by * 128
            x1 = x0 + 128
            y1 = y0 + 128

            # Pour chaque matériau du bloc
            for i, mat_id in enumerate(mat_ids):
                if i >= 7:
                    break

                # Couleur du matériau
                color = get_material_color(mat_id, catalog, surfaces)

                # Poids du matériau pour cette zone
                w = weights[y0:y1, x0:x1, i]

                # Accumuler couleur pondérée
                result[y0:y1, x0:x1] += w[:, :, None] * color[None, None, :]

    # Convertir en uint8
    result = np.clip(result, 0, 255).astype(np.uint8)

    # Resize si besoin
    if target_size != 512:
        result = cv2.resize(result, (target_size, target_size), interpolation=cv2.INTER_LINEAR)

    return result


def generate_satmap_v2(
    terrain_dir: Path,
    catalog_path: Path,
    surfaces_list: List[str],
    output_path: Path,
    mode: str = "colors",
    target_resolution: int = 4097
):
    """
    Génère la satmap complète avec le pipeline v2.0

    Args:
        terrain_dir: Dossier Terrain/
        catalog_path: Chemin vers catalog.json
        surfaces_list: Liste globale des surfaces
        output_path: Chemin sortie satmap.png
        mode: "colors" (rapide) ou "textured" (qualité)
        target_resolution: Résolution finale (4097 = 4k)
    """
    print("="*80)
    print("GÉNÉRATION SATMAP v2.0 - Pipeline layer.edds + LRS2")
    print("="*80)
    print(f"Mode : {mode}")
    print(f"Résolution cible : {target_resolution}×{target_resolution}")
    print()

    data_dir = terrain_dir / ".Data"

    # Charger catalogue
    print("📂 Chargement catalogue...")
    catalog = load_catalog(catalog_path)
    print(f"   ✅ {len(catalog)} surfaces\n")

    # Détecter nombre de tuiles
    ttile_files = list(data_dir.glob("Terrain_*.ttile"))
    # Exclure les fichiers layer/normal/supertexture
    ttile_files = [f for f in ttile_files if not any(x in f.name for x in ["_layer", "_normal", "_supertexture"])]

    num_tiles = len(ttile_files)
    print(f"📂 Détection tuiles : {num_tiles} fichiers .ttile")

    # Déterminer grille
    grid_size = int(np.sqrt(num_tiles))
    if grid_size * grid_size != num_tiles:
        print(f"⚠️ Nombre de tuiles non carré : {num_tiles}")
        grid_size = int(np.ceil(np.sqrt(num_tiles)))

    print(f"   Grille : {grid_size}×{grid_size}")
    print()

    # Canvas natif 512 px/tuile
    native_size = grid_size * 512
    print(f"📐 Résolution native : {native_size}×{native_size}")
    print(f"   Downscale → {target_resolution}×{target_resolution}")
    print()

    # Canvas
    canvas = np.zeros((native_size, native_size, 3), dtype=np.uint8)

    # Préparation mode textured
    texture_cache = {}
    tint_cache = {}
    if mode == "textured":
        from satmap_v2_textured import generate_tile_satmap_textured
        editor_data_dir = terrain_dir / ".EditorData"
        textures_root = catalog_path.parent  # data/Textures_ArmaReforger/
        emat_dir = textures_root / "emat"
        print(f"📐 Mode textured : textures depuis {textures_root}")

    # Générer tuiles
    print("🎨 Génération tuiles...")
    for tile_id in tqdm(range(num_tiles)):
        # Position dans la grille
        tx = tile_id % grid_size
        ty = tile_id // grid_size

        # Générer tuile selon le mode
        if mode == "textured":
            tile_img = generate_tile_satmap_textured(
                tile_id, editor_data_dir, data_dir, catalog, surfaces_list,
                textures_root, texture_cache, tint_cache, emat_dir, mode="textured"
            )
        else:
            tile_img = generate_tile_satmap_colors(
                tile_id, data_dir, catalog, surfaces_list, target_size=512
            )

        if tile_img is None:
            continue

        # Placer dans canvas
        y0 = ty * 512
        x0 = tx * 512
        canvas[y0:y0+512, x0:x0+512] = tile_img

    print()

    # Downscale
    print(f"🔽 Downscale {native_size}×{native_size} → {target_resolution}×{target_resolution}...")
    satmap = cv2.resize(canvas, (target_resolution, target_resolution), interpolation=cv2.INTER_AREA)

    # Sauvegarder
    print(f"💾 Sauvegarde : {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR))

    print()
    print("="*80)
    print("✅ SATMAP v2.0 GÉNÉRÉE !")
    print("="*80)
    print(f"Fichier : {output_path}")
    print(f"Taille : {satmap.shape[1]}×{satmap.shape[0]}")


# Test
if __name__ == "__main__":
    # Configuration test
    terrain_dir = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain")
    catalog_path = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")
    output_path = Path(r"h:\logiciel perso\Map generator\output\satmap_v2_test.png")

    # Liste globale surfaces (exemple Zimnitrita - à adapter)
    # Cette liste doit venir de la config du monde
    # Pour le test, on utilise les surfaces du catalogue
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    surfaces_list = list(catalog.keys())

    # Tester sur 1 tuile d'abord
    print("🧪 TEST 1 TUILE\n")
    data_dir = terrain_dir / ".Data"

    tile_img = generate_tile_satmap_colors(
        0, data_dir, catalog, surfaces_list, target_size=512
    )

    if tile_img is not None:
        cv2.imwrite("test_tile_0.png", cv2.cvtColor(tile_img, cv2.COLOR_RGB2BGR))
        print(f"✅ Tuile 0 générée : test_tile_0.png\n")
    else:
        print("❌ Échec génération tuile 0\n")

    # Générer satmap complète
    # generate_satmap_v2(
    #     terrain_dir,
    #     catalog_path,
    #     surfaces_list,
    #     output_path,
    #     mode="colors",
    #     target_resolution=4097
    # )
