"""
Tile Inspector - Visualiseur de debug pour analyser une tile Reforger

Charge une tile .ttile + .edds et génère une image debug montrant:
- Le rendu texturé avec middle tuilé × poids
- Le quadrillage des 16 blocs LRS2
- Le matériau dominant par bloc affiché en texte
"""

import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Ajouter le répertoire parent au path pour imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import modules existants
from terrain_terr_reader import read_mats_from_terr
from lrs2_parser import load_lrs2_from_ttile
from scripts.edds_decoder import decode_edds_layer, extract_all_weights


def load_catalog(catalog_path: Path) -> Dict:
    """Charge le catalogue de textures enrichi."""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_material_middle(
    mat_id: int,
    catalog: Dict,
    surfaces: List[str],
    middles_dir: Path,
    middles_cache: Dict[int, np.ndarray],
    tile_size: int = 512
) -> np.ndarray:
    """
    Retourne une image tuilée (tile_size × tile_size) RGB pour un matériau.
    Si middle non disponible, retourne un aplat avg_color/tint.
    """
    # Vérifier cache
    if mat_id in middles_cache:
        return middles_cache[mat_id]

    # Fallback couleur plate
    if mat_id >= len(surfaces):
        color_flat = np.array([255, 0, 255], dtype=np.float32)  # magenta
    else:
        surface_name = surfaces[mat_id]
        entry = catalog.get(surface_name) or catalog.get(surface_name + ".emat")

        if entry is None:
            color_flat = np.array([75, 110, 48], dtype=np.float32)  # fallback grass
        else:
            # Priorité: avg_color > tint > tint_srgb
            avg = entry.get("avg_color")
            tint = entry.get("tint")
            tint_srgb = entry.get("tint_srgb")

            if tint and max(tint[:3]) < 200:
                color_flat = np.array(tint[:3], dtype=np.float32)
            elif avg and avg != [0, 0, 0]:
                color_flat = np.array(avg[:3], dtype=np.float32)
            elif tint_srgb:
                color_flat = np.array(tint_srgb[:3], dtype=np.float32)
            else:
                color_flat = np.array([75, 110, 48], dtype=np.float32)

    fallback = np.full((tile_size, tile_size, 3), color_flat, dtype=np.float32)

    if mat_id >= len(surfaces):
        middles_cache[mat_id] = fallback
        return fallback

    surface_name = surfaces[mat_id]
    entry = catalog.get(surface_name) or catalog.get(surface_name + ".emat")

    if entry is None:
        middles_cache[mat_id] = fallback
        return fallback

    # Récupérer middle_bcr et tiling_scale
    middle_bcr = entry.get("middle_bcr")
    tiling_scale = entry.get("tiling_scale", 1.0)

    if not middle_bcr or not middles_dir:
        middles_cache[mat_id] = fallback
        return fallback

    # Charger PNG middle
    middle_path = middles_dir / middle_bcr
    if not middle_path.exists():
        middles_cache[mat_id] = fallback
        return fallback

    try:
        # Charger image (BGR -> RGB)
        middle_img = cv2.imread(str(middle_path))
        if middle_img is None:
            middles_cache[mat_id] = fallback
            return fallback

        middle_img = cv2.cvtColor(middle_img, cv2.COLOR_BGR2RGB).astype(np.float32)

        # Calculer nombre de répétitions
        world_size_m = 2048.0
        repeat = max(1, round(world_size_m / tiling_scale))

        # Tuiler l'image
        h, w = middle_img.shape[:2]
        tiled = np.tile(middle_img, (repeat, repeat, 1))

        # Redimensionner pour obtenir exactement tile_size × tile_size
        tiled_resized = cv2.resize(tiled, (tile_size, tile_size), interpolation=cv2.INTER_LINEAR)

        # Clipper et mettre en cache
        result = np.clip(tiled_resized, 0, 255)
        middles_cache[mat_id] = result
        return result

    except Exception:
        middles_cache[mat_id] = fallback
        return fallback


def render_tile_with_blocks(
    tile_id: int,
    data_dir: Path,
    editor_data_dir: Path,
    terr_path: Path,
    catalog_path: Path,
    middles_dir: Path,
    output_path: Path
) -> bool:
    """
    Génère une image debug d'une tile avec:
    - Rendu texturé middle × poids
    - Quadrillage blocs LRS2
    - Nom matériau dominant par bloc
    """
    print(f"🔍 Tile Inspector — Tile {tile_id}")
    print("="*80)

    # 1. Charger données terrain
    print("📂 Chargement catalogue et surfaces...")
    catalog = load_catalog(catalog_path)
    surfaces = [e["name"] for e in read_mats_from_terr(terr_path)]
    print(f"   ✅ {len(catalog)} matériaux dans catalogue, {len(surfaces)} surfaces")

    # 2. Charger LRS2 (blocs 4×4)
    ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
    if not ttile_path.exists():
        print(f"   ❌ Fichier non trouvé: {ttile_path}")
        return False

    print(f"📦 Chargement LRS2 depuis {ttile_path.name}...")
    lrs2_blocks = load_lrs2_from_ttile(ttile_path)
    if lrs2_blocks is None:
        print("   ❌ Échec parsing LRS2")
        return False
    print(f"   ✅ {len(lrs2_blocks)} blocs chargés")

    # 3. Charger layer EDDS/DDS (poids)
    # Tester .edds puis .dds
    layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.edds"
    if not layer_path.exists():
        layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.dds"

    if not layer_path.exists():
        print(f"   ❌ Fichier non trouvé: {layer_path}")
        return False

    print(f"🖼️  Chargement layer depuis {layer_path.name}...")
    layer_img = decode_edds_layer(layer_path)
    if layer_img is None:
        print("   ❌ Échec décodage EDDS")
        return False
    print(f"   ✅ Image {layer_img.shape} décodée")

    # 4. Extraire poids
    print("⚖️  Extraction poids...")
    weights = extract_all_weights(layer_img)  # (512, 512, 7)
    print(f"   ✅ Poids extraits: {weights.shape}")

    # 5. Générer rendu texturé
    print("🎨 Génération rendu texturé...")
    img = np.zeros((512, 512, 3), dtype=np.float32)
    middles_cache = {}

    # Parcourir tous les pixels
    for y in range(512):
        for x in range(512):
            # Identifier bloc
            bx = x // 128
            by = y // 128

            mat_ids = lrs2_blocks.get((bx, by), [])
            if len(mat_ids) == 0:
                # Bloc vide → noir
                continue

            # Obtenir poids pour ce pixel
            w = weights[y, x, :len(mat_ids)]

            # Accumuler contribution de chaque matériau
            pixel_color = np.zeros(3, dtype=np.float32)

            for i, mat_id in enumerate(mat_ids):
                if i >= 7:
                    break

                weight = w[i]
                if weight < 0.001:
                    continue

                # Obtenir texture tuilée pour ce matériau
                middle = get_material_middle(
                    mat_id, catalog, surfaces, middles_dir, middles_cache
                )

                # Contribution pondérée
                pixel_color += middle[y, x, :] * weight

            img[y, x, :] = pixel_color

    # Clipper
    img = np.clip(img, 0, 255).astype(np.uint8)
    print("   ✅ Rendu généré")

    # 6. Superposer quadrillage et labels
    print("🖍️  Ajout quadrillage et labels...")

    # Quadrillage blanc semi-transparent
    overlay = img.copy()

    # Lignes verticales
    for bx in range(1, 4):
        x = bx * 128
        cv2.line(overlay, (x, 0), (x, 512), (255, 255, 255), 2)

    # Lignes horizontales
    for by in range(1, 4):
        y = by * 128
        cv2.line(overlay, (0, y), (512, y), (255, 255, 255), 2)

    # Blend
    alpha = 0.7
    img = cv2.addWeighted(img, alpha, overlay, 1 - alpha, 0)

    # Labels matériaux dominants
    for by in range(4):
        for bx in range(4):
            mat_ids = lrs2_blocks.get((bx, by), [])

            if len(mat_ids) == 0:
                label = "VIDE"
            else:
                # Calculer matériau dominant dans ce bloc
                block_x0 = bx * 128
                block_y0 = by * 128
                block_x1 = block_x0 + 128
                block_y1 = block_y0 + 128

                # Moyenner poids dans le bloc
                block_weights = weights[block_y0:block_y1, block_x0:block_x1, :len(mat_ids)]
                avg_weights = block_weights.mean(axis=(0, 1))

                dominant_idx = avg_weights.argmax()
                dominant_id = mat_ids[dominant_idx]

                # Nom du matériau
                if dominant_id < len(surfaces):
                    label = surfaces[dominant_id]
                else:
                    label = f"MAT_{dominant_id}"

            # Position texte (centre du bloc)
            text_x = bx * 128 + 10
            text_y = by * 128 + 30

            # Ombre portée
            cv2.putText(
                img, label,
                (text_x + 1, text_y + 1),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 0, 0),
                2,
                cv2.LINE_AA
            )

            # Texte blanc
            cv2.putText(
                img, label,
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )

    print("   ✅ Quadrillage et labels ajoutés")

    # 7. Sauvegarder
    print(f"💾 Sauvegarde vers {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convertir RGB -> BGR pour OpenCV
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(output_path), img_bgr)

    print(f"   ✅ Image sauvegardée: {output_path}")
    print("="*80)
    print("✅ Terminé!")

    return True


def main():
    """Point d'entrée principal."""
    # Saisie interactive coordonnées
    coords = input("Entrez les coordonnées de la tile (ex: 1,13) : ")
    x, y = map(int, coords.strip().split(','))
    tile_id = y * 32 + x
    print(f"Tile ({x},{y}) → ID {tile_id}")

    # Chemins projet
    PROJECT_ROOT = Path(__file__).parent.parent

    # Chemins données Zimnitrita (disque I:)
    TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
    DATA_DIR = TERRAIN_ROOT / ".Data"
    EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
    TERR_PATH = TERRAIN_ROOT / "terrain.terr"

    # Chemins catalogue local (projet H:)
    CATALOG_PATH = PROJECT_ROOT / "data" / "Textures_ArmaReforger" / "catalog.json"
    MIDDLES_DIR = PROJECT_ROOT / "data" / "Textures_ArmaReforger" / "middle_png"

    # Sortie locale
    OUTPUT_PATH = PROJECT_ROOT / f"tile_{x}_{y}_debug.png"

    # Vérifications
    if not DATA_DIR.exists():
        print(f"❌ Dossier .Data introuvable: {DATA_DIR}")
        return 1

    if not EDITOR_DATA_DIR.exists():
        print(f"❌ Dossier .EditorData introuvable: {EDITOR_DATA_DIR}")
        return 1

    if not TERR_PATH.exists():
        print(f"❌ Fichier terrain.terr introuvable: {TERR_PATH}")
        return 1

    if not CATALOG_PATH.exists():
        print(f"❌ Catalogue introuvable: {CATALOG_PATH}")
        return 1

    # Générer image debug
    success = render_tile_with_blocks(
        tile_id=tile_id,
        data_dir=DATA_DIR,
        editor_data_dir=EDITOR_DATA_DIR,
        terr_path=TERR_PATH,
        catalog_path=CATALOG_PATH,
        middles_dir=MIDDLES_DIR,
        output_path=OUTPUT_PATH
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
