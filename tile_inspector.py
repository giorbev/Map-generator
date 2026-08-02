"""
Tile Inspector v2 - Analyseur avancé de tiles Reforger

Fonctionnalités:
- Saisie interactive coordonnées x,y
- Calcul coordonnées LRS2 globales (grille 128×128)
- Analyse pente par bloc depuis .bterr
- Détection discontinuités avec tiles adjacentes
- Image debug 800×800 avec coordonnées LRS2 + matériaux
- Rapport texte détaillé
"""

import json
import numpy as np
import cv2
import struct
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import sys
import argparse
from datetime import datetime

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


def calculate_lrs2_coords(tx: int, ty: int, bx: int, by: int) -> Tuple[int, int]:
    """
    Calcule les coordonnées LRS2 globales d'un bloc.

    Args:
        tx, ty: Coordonnées de la tile
        bx, by: Position du bloc dans la tile (0..3)

    Returns:
        (lrs_x, lrs_y): Coordonnées LRS2 globales
    """
    lrs_x = tx * 4 + bx
    lrs_y = ty * 4 + by
    return lrs_x, lrs_y


def load_bterr_heightmap(bterr_path: Path) -> Optional[np.ndarray]:
    """
    Charge la heightmap depuis un fichier .bterr.

    Returns:
        Array 129×129 float32, ou None si erreur
    """
    if not bterr_path.exists():
        return None

    try:
        data = open(bterr_path, "rb").read()
        i = data.find(b"DATA")
        if i < 0:
            return None

        sz = struct.unpack_from(">I", data, i + 4)[0]
        hm = np.frombuffer(data[i + 8:i + 8 + sz], np.float32).reshape(129, 129)
        return hm.astype(np.float64)
    except Exception:
        return None


def calculate_slope_for_block(heightmap: np.ndarray, bx: int, by: int, cellsize: float = 4.0) -> float:
    """
    Calcule la pente moyenne (en degrés) pour un bloc 32×32 de la heightmap.

    Args:
        heightmap: Heightmap 129×129
        bx, by: Position du bloc (0..3)
        cellsize: Résolution métrique (4m par défaut)

    Returns:
        Pente moyenne en degrés
    """
    # Bloc 32×32 dans la heightmap 129×129
    # Attention : 129 vertices = 128 cells, donc 4 blocs de 32 cells
    x0 = bx * 32
    y0 = by * 32
    x1 = x0 + 33  # 33 vertices pour 32 cells
    y1 = y0 + 33

    block_hm = heightmap[y0:y1, x0:x1]

    # Gradient
    gy, gx = np.gradient(block_hm, cellsize)
    slope_rad = np.arctan(np.hypot(gx, gy))
    slope_deg = np.degrees(slope_rad)

    return float(slope_deg.mean())


def load_adjacent_tiles(
    tx: int, ty: int,
    data_dir: Path
) -> Dict[str, Optional[Dict[Tuple[int, int], List[int]]]]:
    """
    Charge les LRS2 des 4 tiles adjacentes (N, S, E, O).

    Returns:
        Dict avec clés 'N', 'S', 'E', 'O' → LRS2 ou None
    """
    adjacent = {}

    # Nord (ty - 1)
    if ty > 0:
        tile_id_n = (ty - 1) * 32 + tx
        ttile_n = data_dir / f"Terrain_{tile_id_n}.ttile"
        adjacent['N'] = load_lrs2_from_ttile(ttile_n) if ttile_n.exists() else None
    else:
        adjacent['N'] = None

    # Sud (ty + 1)
    if ty < 31:
        tile_id_s = (ty + 1) * 32 + tx
        ttile_s = data_dir / f"Terrain_{tile_id_s}.ttile"
        adjacent['S'] = load_lrs2_from_ttile(ttile_s) if ttile_s.exists() else None
    else:
        adjacent['S'] = None

    # Est (tx + 1)
    if tx < 31:
        tile_id_e = ty * 32 + (tx + 1)
        ttile_e = data_dir / f"Terrain_{tile_id_e}.ttile"
        adjacent['E'] = load_lrs2_from_ttile(ttile_e) if ttile_e.exists() else None
    else:
        adjacent['E'] = None

    # Ouest (tx - 1)
    if tx > 0:
        tile_id_o = ty * 32 + (tx - 1)
        ttile_o = data_dir / f"Terrain_{tile_id_o}.ttile"
        adjacent['O'] = load_lrs2_from_ttile(ttile_o) if ttile_o.exists() else None
    else:
        adjacent['O'] = None

    return adjacent


def detect_border_discontinuities(
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    adjacent_tiles: Dict[str, Optional[Dict[Tuple[int, int], List[int]]]]
) -> List[Tuple[int, int, str]]:
    """
    Détecte les discontinuités matériaux aux frontières.

    Returns:
        Liste de (bx, by, direction) pour les blocs avec discontinuité
    """
    discontinuities = []

    # Bord Nord (by = 0)
    if adjacent_tiles['N'] is not None:
        for bx in range(4):
            mats_current = set(lrs2_blocks.get((bx, 0), []))
            mats_north = set(adjacent_tiles['N'].get((bx, 3), []))  # Bord sud de la tile nord
            if mats_current and mats_north and mats_current != mats_north:
                discontinuities.append((bx, 0, 'N'))

    # Bord Sud (by = 3)
    if adjacent_tiles['S'] is not None:
        for bx in range(4):
            mats_current = set(lrs2_blocks.get((bx, 3), []))
            mats_south = set(adjacent_tiles['S'].get((bx, 0), []))  # Bord nord de la tile sud
            if mats_current and mats_south and mats_current != mats_south:
                discontinuities.append((bx, 3, 'S'))

    # Bord Est (bx = 3)
    if adjacent_tiles['E'] is not None:
        for by in range(4):
            mats_current = set(lrs2_blocks.get((3, by), []))
            mats_east = set(adjacent_tiles['E'].get((0, by), []))  # Bord ouest de la tile est
            if mats_current and mats_east and mats_current != mats_east:
                discontinuities.append((3, by, 'E'))

    # Bord Ouest (bx = 0)
    if adjacent_tiles['O'] is not None:
        for by in range(4):
            mats_current = set(lrs2_blocks.get((0, by), []))
            mats_west = set(adjacent_tiles['O'].get((3, by), []))  # Bord est de la tile ouest
            if mats_current and mats_west and mats_current != mats_west:
                discontinuities.append((0, by, 'O'))

    return discontinuities


def get_material_middle(
    mat_id: int,
    catalog: Dict,
    surfaces: List[str],
    middles_dir: Path,
    middles_cache: Dict[int, np.ndarray],
    tile_size: int = 512
) -> np.ndarray:
    """Retourne une image tuilée RGB pour un matériau (identique à v1)."""
    if mat_id in middles_cache:
        return middles_cache[mat_id]

    # Fallback couleur plate
    if mat_id >= len(surfaces):
        color_flat = np.array([255, 0, 255], dtype=np.float32)
    else:
        surface_name = surfaces[mat_id]
        entry = catalog.get(surface_name) or catalog.get(surface_name + ".emat")

        if entry is None:
            color_flat = np.array([75, 110, 48], dtype=np.float32)
        else:
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

    middle_bcr = entry.get("middle_bcr")
    tiling_scale = entry.get("tiling_scale", 1.0)

    if not middle_bcr or not middles_dir:
        middles_cache[mat_id] = fallback
        return fallback

    middle_path = middles_dir / middle_bcr
    if not middle_path.exists():
        middles_cache[mat_id] = fallback
        return fallback

    try:
        middle_img = cv2.imread(str(middle_path))
        if middle_img is None:
            middles_cache[mat_id] = fallback
            return fallback

        middle_img = cv2.cvtColor(middle_img, cv2.COLOR_BGR2RGB).astype(np.float32)

        world_size_m = 2048.0
        repeat = max(1, round(world_size_m / tiling_scale))

        h, w = middle_img.shape[:2]
        tiled = np.tile(middle_img, (repeat, repeat, 1))
        tiled_resized = cv2.resize(tiled, (tile_size, tile_size), interpolation=cv2.INTER_LINEAR)

        result = np.clip(tiled_resized, 0, 255)
        middles_cache[mat_id] = result
        return result
    except Exception:
        middles_cache[mat_id] = fallback
        return fallback


def render_tile_v2(
    tx: int, ty: int, tile_id: int,
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    weights: np.ndarray,
    slopes: Dict[Tuple[int, int], float],
    discontinuities: List[Tuple[int, int, str]],
    catalog: Dict,
    surfaces: List[str],
    middles_dir: Path,
    output_path: Path
) -> bool:
    """
    Génère l'image debug 800×800 avec coordonnées LRS2, matériaux, discontinuités.
    """
    print("🎨 Génération image debug v2 (800×800)...")

    # 1. Rendu texturé 512×512
    img_512 = np.zeros((512, 512, 3), dtype=np.float32)
    middles_cache = {}

    for y in range(512):
        for x in range(512):
            bx = x // 128
            by = y // 128

            mat_ids = lrs2_blocks.get((bx, by), [])
            if len(mat_ids) == 0:
                continue

            w = weights[y, x, :len(mat_ids)]
            pixel_color = np.zeros(3, dtype=np.float32)

            for i, mat_id in enumerate(mat_ids):
                if i >= 7:
                    break
                weight = w[i]
                if weight < 0.001:
                    continue

                middle = get_material_middle(mat_id, catalog, surfaces, middles_dir, middles_cache)
                pixel_color += middle[y, x, :] * weight

            img_512[y, x, :] = pixel_color

    img_512 = np.clip(img_512, 0, 255).astype(np.uint8)

    # 2. Upscale vers 800×800
    img = cv2.resize(img_512, (800, 800), interpolation=cv2.INTER_LINEAR)

    # 3. Quadrillage blanc (blocs 200×200 px dans l'image 800×800)
    overlay = img.copy()

    for bx in range(1, 4):
        x = bx * 200
        cv2.line(overlay, (x, 0), (x, 800), (255, 255, 255), 2)

    for by in range(1, 4):
        y = by * 200
        cv2.line(overlay, (0, y), (800, y), (255, 255, 255), 2)

    alpha = 0.7
    img = cv2.addWeighted(img, alpha, overlay, 1 - alpha, 0)

    # 4. Marquage discontinuités en rouge
    discontinuity_set = {(bx, by) for bx, by, _ in discontinuities}
    for bx, by in discontinuity_set:
        x0 = bx * 200
        y0 = by * 200
        x1 = x0 + 200
        y1 = y0 + 200
        cv2.rectangle(img, (x0, y0), (x1, y1), (255, 0, 0), 4)

    # 5. Labels coordonnées LRS2 + matériau
    for by in range(4):
        for bx in range(4):
            lrs_x, lrs_y = calculate_lrs2_coords(tx, ty, bx, by)

            # Coordonnées LRS2 en grand
            text_lrs = f"{lrs_x},{lrs_y}"
            text_x = bx * 200 + 20
            text_y = by * 200 + 60

            # Ombre
            cv2.putText(img, text_lrs, (text_x + 2, text_y + 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3, cv2.LINE_AA)
            # Texte blanc
            cv2.putText(img, text_lrs, (text_x, text_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)

            # Matériau dominant en petit dessous
            mat_ids = lrs2_blocks.get((bx, by), [])
            if len(mat_ids) > 0:
                # Calculer dominant
                block_x0 = bx * 128
                block_y0 = by * 128
                block_weights = weights[block_y0:block_y0 + 128, block_x0:block_x0 + 128, :len(mat_ids)]
                avg_weights = block_weights.mean(axis=(0, 1))
                dominant_idx = avg_weights.argmax()
                dominant_id = mat_ids[dominant_idx]

                if dominant_id < len(surfaces):
                    mat_name = surfaces[dominant_id]
                else:
                    mat_name = f"MAT_{dominant_id}"

                text_mat = mat_name[:15]  # Tronquer si trop long
                text_mat_y = text_y + 35

                # Ombre
                cv2.putText(img, text_mat, (text_x + 1, text_mat_y + 1),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2, cv2.LINE_AA)
                # Texte blanc
                cv2.putText(img, text_mat, (text_x, text_mat_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    # 6. Sauvegarder
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(output_path), img_bgr)

    print(f"   ✅ Image sauvegardée: {output_path}")
    return True


def generate_report(
    tx: int, ty: int, tile_id: int,
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    weights: np.ndarray,
    slopes: Dict[Tuple[int, int], float],
    discontinuities: List[Tuple[int, int, str]],
    surfaces: List[str],
    report_path: Path
) -> bool:
    """
    Génère le rapport texte détaillé.
    """
    print(f"📝 Génération rapport texte: {report_path}...")

    lines = []
    lines.append("=" * 80)
    lines.append(f"TILE INSPECTOR V2 - RAPPORT")
    lines.append(f"Tile ({tx},{ty}) → ID {tile_id}")
    lines.append("=" * 80)
    lines.append("")

    # Section blocs
    lines.append("BLOCS (4×4)")
    lines.append("-" * 80)

    for by in range(4):
        for bx in range(4):
            lrs_x, lrs_y = calculate_lrs2_coords(tx, ty, bx, by)
            mat_ids = lrs2_blocks.get((bx, by), [])
            slope = slopes.get((bx, by), 0.0)

            lines.append(f"\nBloc ({bx},{by}) → LRS2 ({lrs_x},{lrs_y})")
            lines.append(f"  Pente moyenne: {slope:.2f}°")

            if len(mat_ids) == 0:
                lines.append(f"  Matériaux: VIDE")
            else:
                # Calculer poids moyens
                block_x0 = bx * 128
                block_y0 = by * 128
                block_weights = weights[block_y0:block_y0 + 128, block_x0:block_x0 + 128, :len(mat_ids)]
                avg_weights = block_weights.mean(axis=(0, 1))

                lines.append(f"  Matériaux ({len(mat_ids)}):")
                for i, mat_id in enumerate(mat_ids):
                    mat_name = surfaces[mat_id] if mat_id < len(surfaces) else f"MAT_{mat_id}"
                    weight_pct = avg_weights[i] * 100
                    lines.append(f"    [{i}] {mat_name}: {weight_pct:.1f}%")

    lines.append("")
    lines.append("=" * 80)

    # Section discontinuités
    lines.append("DISCONTINUITÉS AUX FRONTIÈRES")
    lines.append("-" * 80)

    if len(discontinuities) == 0:
        lines.append("Aucune discontinuité détectée.")
    else:
        for bx, by, direction in discontinuities:
            lrs_x, lrs_y = calculate_lrs2_coords(tx, ty, bx, by)
            lines.append(f"Bloc ({bx},{by}) → LRS2 ({lrs_x},{lrs_y}) - Bord {direction}")

    lines.append("")
    lines.append("=" * 80)

    # Sauvegarder
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding='utf-8')

    print(f"   ✅ Rapport sauvegardé: {report_path}")
    return True


def export_json(tiles_dir: Path, output_path: Path) -> int:
    """
    Export JSON de toutes les tiles d'un projet.

    Args:
        tiles_dir: Dossier contenant les .ttile
        output_path: Chemin du fichier JSON de sortie

    Returns:
        0 si succès, 1 si erreur
    """
    print("=" * 80)
    print("TILE INSPECTOR V2 - Export JSON")
    print("=" * 80)
    print()

    if not tiles_dir.exists():
        print(f"❌ Dossier introuvable: {tiles_dir}")
        return 1

    # Lister tous les .ttile
    ttile_files = sorted(tiles_dir.glob("Terrain_*.ttile"))

    if not ttile_files:
        print(f"❌ Aucun fichier .ttile trouvé dans {tiles_dir}")
        return 1

    print(f"📂 {len(ttile_files)} fichier(s) .ttile trouvés")
    print(f"📤 Export vers: {output_path}")
    print()

    # Dry-run : afficher nombre de tuiles
    print(f"🔍 Analyse de {len(ttile_files)} tuile(s)...")
    print()

    tiles_data = []

    for ttile_path in ttile_files:
        # Extraire tile_id depuis le nom de fichier
        try:
            tid = int(ttile_path.stem.replace("Terrain_", ""))
        except ValueError:
            print(f"⚠️  Nom invalide, skip: {ttile_path.name}")
            continue

        # Calculer tx, ty depuis tid
        tx = tid % 32
        ty = tid // 32

        # Charger LRS2
        lrs2_blocks = load_lrs2_from_ttile(ttile_path)
        if lrs2_blocks is None:
            print(f"⚠️  Échec parsing LRS2, skip: {ttile_path.name}")
            continue

        # Calculer max_tex_per_block
        max_tex_per_block = 0
        all_mat_ids = set()

        for (bx, by), mat_ids in lrs2_blocks.items():
            n_tex = len(mat_ids)
            max_tex_per_block = max(max_tex_per_block, n_tex)
            all_mat_ids.update(mat_ids)

        # Construire entrée JSON
        tile_entry = {
            "tid": tid,
            "tx": tx,
            "ty": ty,
            "max_tex_per_block": max_tex_per_block,
            "n_active_mats": len(all_mat_ids),
            "active_mat_ids": sorted(list(all_mat_ids))
        }

        tiles_data.append(tile_entry)

        # Afficher progression tous les 50 tiles
        if len(tiles_data) % 50 == 0:
            print(f"   ✅ {len(tiles_data)} tuiles traitées...")

    print()
    print(f"✅ {len(tiles_data)} tuile(s) analysée(s)")
    print()

    # Écrire JSON
    output_json = {
        "tiles": tiles_data,
        "generated_at": datetime.now().isoformat(),
        "project": str(tiles_dir)
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_json, f, indent=2, ensure_ascii=False)

        print(f"📝 JSON exporté: {output_path}")
        print(f"   {len(tiles_data)} tuiles, {sum(t['n_active_mats'] for t in tiles_data)} matériaux distincts (total)")
        print()
        print("=" * 80)

        return 0
    except Exception as e:
        print(f"❌ Erreur écriture JSON: {e}")
        return 1


def main():
    """Point d'entrée principal."""
    # Parser arguments CLI
    parser = argparse.ArgumentParser(
        description="Tile Inspector v2 - Analyseur avancé de tiles Reforger"
    )
    parser.add_argument(
        "--export-json",
        type=Path,
        metavar="OUTPUT_PATH",
        help="Export JSON de toutes les tiles (nécessite --tiles-dir)"
    )
    parser.add_argument(
        "--tiles-dir",
        type=Path,
        metavar="TILES_DIR",
        help="Dossier contenant les fichiers .ttile"
    )

    args = parser.parse_args()

    # Mode export JSON
    if args.export_json:
        if not args.tiles_dir:
            print("❌ --export-json nécessite --tiles-dir")
            return 1

        return export_json(args.tiles_dir, args.export_json)

    # Mode interactif (existant)
    print("=" * 80)
    print("TILE INSPECTOR V2 - Analyseur avancé de tiles Reforger")
    print("=" * 80)
    print()

    # Saisie interactive
    coords = input("Entrez les coordonnées de la tile (ex: 1,13) : ")
    x, y = map(int, coords.strip().split(','))
    tile_id = y * 32 + x
    print(f"Tile ({x},{y}) → ID {tile_id}")
    print()

    # Chemins projet
    PROJECT_ROOT = Path(__file__).parent.parent

    # Chemins données Zimnitrita (disque I:)
    TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
    DATA_DIR = TERRAIN_ROOT / ".Data"
    EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
    TERR_PATH = TERRAIN_ROOT / "terrain.terr"

    # Chemins catalogue local
    CATALOG_PATH = PROJECT_ROOT / "data" / "Textures_ArmaReforger" / "catalog.json"
    MIDDLES_DIR = PROJECT_ROOT / "data" / "Textures_ArmaReforger" / "middle_png"

    # Sorties
    OUTPUT_IMG = PROJECT_ROOT / f"tile_{x}_{y}_v2_debug.png"
    OUTPUT_REPORT = PROJECT_ROOT / f"tile_{x}_{y}_report.txt"

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

    # 1. Charger catalogue et surfaces
    print("📂 Chargement catalogue et surfaces...")
    catalog = load_catalog(CATALOG_PATH)
    surfaces = [e["name"] for e in read_mats_from_terr(TERR_PATH)]
    print(f"   ✅ {len(catalog)} matériaux, {len(surfaces)} surfaces")

    # 2. Charger LRS2
    ttile_path = DATA_DIR / f"Terrain_{tile_id}.ttile"
    if not ttile_path.exists():
        print(f"❌ Fichier non trouvé: {ttile_path}")
        return 1

    print(f"📦 Chargement LRS2 depuis {ttile_path.name}...")
    lrs2_blocks = load_lrs2_from_ttile(ttile_path)
    if lrs2_blocks is None:
        print("❌ Échec parsing LRS2")
        return 1
    print(f"   ✅ {len(lrs2_blocks)} blocs chargés")

    # 3. Charger layer EDDS
    layer_path = EDITOR_DATA_DIR / f"Terrain_{tile_id}_layer.edds"
    if not layer_path.exists():
        layer_path = EDITOR_DATA_DIR / f"Terrain_{tile_id}_layer.dds"

    if not layer_path.exists():
        print(f"❌ Fichier non trouvé: {layer_path}")
        return 1

    print(f"🖼️  Chargement layer depuis {layer_path.name}...")
    layer_img = decode_edds_layer(layer_path)
    if layer_img is None:
        print("❌ Échec décodage EDDS")
        return 1
    print(f"   ✅ Image {layer_img.shape} décodée")

    # 4. Extraire poids
    print("⚖️  Extraction poids...")
    weights = extract_all_weights(layer_img)
    print(f"   ✅ Poids extraits: {weights.shape}")

    # 5. Charger heightmap .bterr et calculer pentes
    bterr_path = EDITOR_DATA_DIR / f"Terrain_{tile_id}.bterr"
    slopes = {}

    if bterr_path.exists():
        print(f"🏔️  Chargement heightmap depuis {bterr_path.name}...")
        heightmap = load_bterr_heightmap(bterr_path)

        if heightmap is not None:
            print("📐 Calcul pentes par bloc...")
            for by in range(4):
                for bx in range(4):
                    slope = calculate_slope_for_block(heightmap, bx, by)
                    slopes[(bx, by)] = slope
            print(f"   ✅ Pentes calculées pour 16 blocs")
        else:
            print("⚠️  Échec chargement heightmap - pentes non disponibles")
    else:
        print(f"⚠️  Fichier .bterr non trouvé - pentes non disponibles")

    # 6. Charger tiles adjacentes
    print("🧭 Chargement tiles adjacentes...")
    adjacent_tiles = load_adjacent_tiles(x, y, DATA_DIR)
    loaded_count = sum(1 for v in adjacent_tiles.values() if v is not None)
    print(f"   ✅ {loaded_count}/4 tiles adjacentes chargées")

    # 7. Détecter discontinuités
    print("🔍 Détection discontinuités aux frontières...")
    discontinuities = detect_border_discontinuities(lrs2_blocks, adjacent_tiles)
    print(f"   ✅ {len(discontinuities)} discontinuité(s) détectée(s)")

    # 8. Générer image debug
    success_img = render_tile_v2(
        x, y, tile_id,
        lrs2_blocks, weights, slopes, discontinuities,
        catalog, surfaces, MIDDLES_DIR, OUTPUT_IMG
    )

    # 9. Générer rapport
    success_report = generate_report(
        x, y, tile_id,
        lrs2_blocks, weights, slopes, discontinuities,
        surfaces, OUTPUT_REPORT
    )

    print()
    print("=" * 80)
    print("✅ TERMINÉ!")
    print(f"   Image: {OUTPUT_IMG}")
    print(f"   Rapport: {OUTPUT_REPORT}")
    print("=" * 80)

    return 0 if (success_img and success_report) else 1


if __name__ == "__main__":
    sys.exit(main())
