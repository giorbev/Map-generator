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

# Ajouter la racine projet au path pour catalog_config
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import modules existants
from terrain_terr_reader import read_mats_from_terr
from lrs2_parser import load_lrs2_from_ttile
from edds_decoder import decode_edds_layer, extract_all_weights
from catalog_config import get_catalog_path

# -------------------------------------------------------------------------------
# FONCTIONS DE CHARGEMENT CATALOGUE
# -------------------------------------------------------------------------------
def load_catalog(catalog_path: Path) -> Dict:
    """Charge le catalogue de textures enrichi."""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# -------------------------------------------------------------------------------
# FONCTIONS DE CALCUL COORDONNÉES LRS2
# -------------------------------------------------------------------------------
def calculate_lrs2_coords(tx: int, ty: int, bx: int, by: int, num_blk: int) -> Tuple[int, int]:
    """
    Calcule les coordonnées LRS2 globales d'un bloc.

    Args:
        tx, ty: Coordonnées de la tile
        bx, by: Position du bloc dans la tile (0 à num_blk-1)
        num_blk: Nombre de blocs par tile et par côté

    Returns:
        (lrs_x, lrs_y): Coordonnées LRS2 globales
    """
    lrs_x = tx * num_blk + bx
    lrs_y = ty * num_blk + by
    return lrs_x, lrs_y

# -------------------------------------------------------------------------------
# FONCTIONS DE CHARGEMENT HEIGHTMAP .BTERR
# -------------------------------------------------------------------------------
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

# -------------------------------------------------------------------------------
# FONCTIONS DE CALCUL DE PENTE POUR UN BLOC
# -------------------------------------------------------------------------------
def calculate_slope_for_block(heightmap: np.ndarray, bx: int, by: int, num_blk: int, cell_size: float) -> float:
    """
    Calcule la pente moyenne (en degrés) pour un bloc de la heightmap.

    Args:
        heightmap: Heightmap (doit être carrée)
        bx, by: Position du bloc (0 à num_blk-1)
        num_blk: Nombre de blocs par tile et par côté
        cell_size: Résolution métrique (ex: 4.0 m/cell pour Reforger)

    Returns:
        Pente moyenne en degrés

    Raises:
        ValueError: Si heightmap non carrée ou taille incompatible avec num_blk
    """
    # Vérifier que la heightmap est carrée
    if heightmap.shape[0] != heightmap.shape[1]:
        raise ValueError(f"Heightmap non carrée : {heightmap.shape}")

    hm_px = heightmap.shape[0]

    # Vérifier que (hm_px - 1) est divisible par num_blk
    if (hm_px - 1) % num_blk != 0:
        raise ValueError(f"Heightmap {hm_px}×{hm_px} incompatible avec num_blk={num_blk} : (hm_px-1) % num_blk != 0")

    # Calculer cells_per_blk depuis la forme réelle
    cells_per_blk = (hm_px - 1) // num_blk

    # Coordonnées du bloc (vertices)
    x0 = bx * cells_per_blk
    y0 = by * cells_per_blk
    x1 = x0 + cells_per_blk + 1  # +1 vertex pour cells_per_blk cells
    y1 = y0 + cells_per_blk + 1

    block_hm = heightmap[y0:y1, x0:x1]

    # Gradient
    gy, gx = np.gradient(block_hm, cell_size)
    slope_rad = np.arctan(np.hypot(gx, gy))
    slope_deg = np.degrees(slope_rad)

    return float(slope_deg.mean())

# -------------------------------------------------------------------------------
# FONCTIONS DE CHARGEMENT DES TILES ADJACENTES
# -------------------------------------------------------------------------------
def load_adjacent_tiles(
    tx: int, ty: int,
    data_dir: Path,
    grid_w: int,
    num_blk: int,
    tile_prefix: str
) -> Dict[str, Optional[Dict[Tuple[int, int], List[int]]]]:
    """
    Charge les LRS2 des 4 tiles adjacentes (N, S, E, O).

    Args:
        tx, ty: Coordonnées de la tile
        data_dir: Dossier .Data contenant les .ttile
        grid_w: Nombre de tuiles par côté
        num_blk: Nombre de blocs par tile et par côté
        tile_prefix: Préfixe des fichiers .ttile (ex: "Terrain_", "ZBK_terrain_")

    Returns:
        Dict avec clés 'N', 'S', 'E', 'O' → LRS2 ou None
    """
    adjacent = {}

    # Nord (ty - 1)
    if ty > 0:
        tile_id_n = (ty - 1) * grid_w + tx
        ttile_n = data_dir / f"{tile_prefix}{tile_id_n}.ttile"
        adjacent['N'] = load_lrs2_from_ttile(ttile_n, grid_w, num_blk) if ttile_n.exists() else None
    else:
        adjacent['N'] = None

    # Sud (ty + 1)
    if ty < grid_w - 1:
        tile_id_s = (ty + 1) * grid_w + tx
        ttile_s = data_dir / f"{tile_prefix}{tile_id_s}.ttile"
        adjacent['S'] = load_lrs2_from_ttile(ttile_s, grid_w, num_blk) if ttile_s.exists() else None
    else:
        adjacent['S'] = None

    # Est (tx + 1)
    if tx < grid_w - 1:
        tile_id_e = ty * grid_w + (tx + 1)
        ttile_e = data_dir / f"{tile_prefix}{tile_id_e}.ttile"
        adjacent['E'] = load_lrs2_from_ttile(ttile_e, grid_w, num_blk) if ttile_e.exists() else None
    else:
        adjacent['E'] = None

    # Ouest (tx - 1)
    if tx > 0:
        tile_id_o = ty * grid_w + (tx - 1)
        ttile_o = data_dir / f"{tile_prefix}{tile_id_o}.ttile"
        adjacent['O'] = load_lrs2_from_ttile(ttile_o, grid_w, num_blk) if ttile_o.exists() else None
    else:
        adjacent['O'] = None

    return adjacent

# -------------------------------------------------------------------------------
# FONCTIONS DE DÉTECTION DES DISCONTINUITÉS AUX FRONTIÈRES
# -------------------------------------------------------------------------------
def detect_border_discontinuities(
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    adjacent_tiles: Dict[str, Optional[Dict[Tuple[int, int], List[int]]]],
    num_blk: int
) -> List[Tuple[int, int, str]]:
    """
    Détecte les discontinuités matériaux aux frontières.

    Args:
        lrs2_blocks: LRS2 de la tile courante
        adjacent_tiles: LRS2 des tiles adjacentes
        num_blk: Nombre de blocs par tile et par côté

    Returns:
        Liste de (bx, by, direction) pour les blocs avec discontinuité
    """
    discontinuities = []
    last_blk = num_blk - 1

    # Bord Nord (by = 0)
    if adjacent_tiles['N'] is not None:
        for bx in range(num_blk):
            mats_current = set(lrs2_blocks.get((bx, 0), []))
            mats_north = set(adjacent_tiles['N'].get((bx, last_blk), []))  # Bord sud de la tile nord
            if mats_current and mats_north and mats_current != mats_north:
                discontinuities.append((bx, 0, 'N'))

    # Bord Sud (by = last_blk)
    if adjacent_tiles['S'] is not None:
        for bx in range(num_blk):
            mats_current = set(lrs2_blocks.get((bx, last_blk), []))
            mats_south = set(adjacent_tiles['S'].get((bx, 0), []))  # Bord nord de la tile sud
            if mats_current and mats_south and mats_current != mats_south:
                discontinuities.append((bx, last_blk, 'S'))

    # Bord Est (bx = last_blk)
    if adjacent_tiles['E'] is not None:
        for by in range(num_blk):
            mats_current = set(lrs2_blocks.get((last_blk, by), []))
            mats_east = set(adjacent_tiles['E'].get((0, by), []))  # Bord ouest de la tile est
            if mats_current and mats_east and mats_current != mats_east:
                discontinuities.append((last_blk, by, 'E'))

    # Bord Ouest (bx = 0)
    if adjacent_tiles['O'] is not None:
        for by in range(num_blk):
            mats_current = set(lrs2_blocks.get((0, by), []))
            mats_west = set(adjacent_tiles['O'].get((last_blk, by), []))  # Bord est de la tile ouest
            if mats_current and mats_west and mats_current != mats_west:
                discontinuities.append((0, by, 'O'))

    return discontinuities

# -------------------------------------------------------------------------------
# FONCTIONS DE CHARGEMENT DES IMAGES MIDDLE DES MATÉRIAUX
# -------------------------------------------------------------------------------
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

# -------------------------------------------------------------------------------
# FONCTION DE RENDU D'UNE TILE (VERSION 2)
# -------------------------------------------------------------------------------
def render_tile_v2(
    tx: int, ty: int, tile_id: int,
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    weights: np.ndarray,
    slopes: Dict[Tuple[int, int], float],
    discontinuities: List[Tuple[int, int, str]],
    catalog: Dict,
    surfaces: List[str],
    middles_dir: Path,
    output_path: Path,
    num_blk: int
) -> bool:
    """
    Génère l'image debug 800×800 avec coordonnées LRS2, matériaux, discontinuités.

    Args:
        tx, ty, tile_id: Coordonnées et ID de la tile
        lrs2_blocks, weights, slopes, discontinuities: Données analysées
        catalog, surfaces, middles_dir: Catalogue textures
        output_path: Chemin sortie
        num_blk: Nombre de blocs par tile et par côté
    """
    print("🎨 Génération image debug v2 (800×800)...")

    # Vérifier divisibilité
    if 512 % num_blk != 0:
        raise ValueError(f"num_blk={num_blk} ne divise pas 512 : image 512×512 impossible")
    if 800 % num_blk != 0:
        raise ValueError(f"num_blk={num_blk} ne divise pas 800 : image 800×800 impossible")

    block_px_512 = 512 // num_blk
    block_px_800 = 800 // num_blk

    # 1. Rendu texturé 512×512
    img_512 = np.zeros((512, 512, 3), dtype=np.float32)
    middles_cache = {}

    for y in range(512):
        for x in range(512):
            bx = x // block_px_512
            by = y // block_px_512

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

    # 3. Quadrillage blanc (blocs dans l'image 800×800)
    overlay = img.copy()

    for bx in range(1, num_blk):
        x = bx * block_px_800
        cv2.line(overlay, (x, 0), (x, 800), (255, 255, 255), 2)

    for by in range(1, num_blk):
        y = by * block_px_800
        cv2.line(overlay, (0, y), (800, y), (255, 255, 255), 2)

    alpha = 0.7
    img = cv2.addWeighted(img, alpha, overlay, 1 - alpha, 0)

    # 4. Marquage discontinuités en rouge
    discontinuity_set = {(bx, by) for bx, by, _ in discontinuities}
    for bx, by in discontinuity_set:
        x0 = bx * block_px_800
        y0 = by * block_px_800
        x1 = x0 + block_px_800
        y1 = y0 + block_px_800
        cv2.rectangle(img, (x0, y0), (x1, y1), (255, 0, 0), 4)

    # 5. Labels coordonnées LRS2 + matériau
    for by in range(num_blk):
        for bx in range(num_blk):
            lrs_x, lrs_y = calculate_lrs2_coords(tx, ty, bx, by, num_blk)

            # Coordonnées LRS2 en grand
            text_lrs = f"{lrs_x},{lrs_y}"
            text_x = bx * block_px_800 + 20
            text_y = by * block_px_800 + 60

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
                block_x0 = bx * block_px_512
                block_y0 = by * block_px_512
                block_weights = weights[block_y0:block_y0 + block_px_512, block_x0:block_x0 + block_px_512, :len(mat_ids)]
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

# -------------------------------------------------------------------------------
# FONCTION DE GÉNÉRATION DU RAPPORT TEXTE DÉTAILLÉ
# -------------------------------------------------------------------------------
def generate_report(
    tx: int, ty: int, tile_id: int,
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    weights: np.ndarray,
    slopes: Dict[Tuple[int, int], float],
    discontinuities: List[Tuple[int, int, str]],
    surfaces: List[str],
    report_path: Path,
    num_blk: int
) -> bool:
    """
    Génère le rapport texte détaillé.

    Args:
        tx, ty, tile_id: Coordonnées et ID de la tile
        lrs2_blocks, weights, slopes, discontinuities: Données analysées
        surfaces: Liste surfaces
        report_path: Chemin sortie
        num_blk: Nombre de blocs par tile et par côté
    """
    print(f"📝 Génération rapport texte: {report_path}...")

    block_px_512 = 512 // num_blk

    lines = []
    lines.append("=" * 80)
    lines.append(f"TILE INSPECTOR V2 - RAPPORT")
    lines.append(f"Tile ({tx},{ty}) → ID {tile_id}")
    lines.append("=" * 80)
    lines.append("")

    # Section blocs
    lines.append(f"BLOCS ({num_blk}×{num_blk})")
    lines.append("-" * 80)

    for by in range(num_blk):
        for bx in range(num_blk):
            lrs_x, lrs_y = calculate_lrs2_coords(tx, ty, bx, by, num_blk)
            mat_ids = lrs2_blocks.get((bx, by), [])
            slope = slopes.get((bx, by), 0.0)

            lines.append(f"\nBloc ({bx},{by}) → LRS2 ({lrs_x},{lrs_y})")
            lines.append(f"  Pente moyenne: {slope:.2f}°")

            if len(mat_ids) == 0:
                lines.append(f"  Matériaux: VIDE")
            else:
                # Calculer poids moyens
                block_x0 = bx * block_px_512
                block_y0 = by * block_px_512
                block_weights = weights[block_y0:block_y0 + block_px_512, block_x0:block_x0 + block_px_512, :len(mat_ids)]
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
            lrs_x, lrs_y = calculate_lrs2_coords(tx, ty, bx, by, num_blk)
            lines.append(f"Bloc ({bx},{by}) → LRS2 ({lrs_x},{lrs_y}) - Bord {direction}")

    lines.append("")
    lines.append("=" * 80)

    # Sauvegarder
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding='utf-8')

    print(f"   ✅ Rapport sauvegardé: {report_path}")
    return True

# -------------------------------------------------------------------------------
# FONCTION D'EXPORT JSON DE TOUTES LES TILES D'UN PROJET
# -------------------------------------------------------------------------------
def export_json(tiles_dir: Path, output_path: Path, grid_w: int, num_blk: int, tile_prefix: str, block_budget: Optional[int] = None) -> int:
    """
    Export JSON de toutes les tiles d'un projet.

    Args:
        tiles_dir: Dossier contenant les .ttile
        output_path: Chemin du fichier JSON de sortie
        grid_w: Nombre de tuiles par côté
        num_blk: Nombre de blocs par tile et par côté
        tile_prefix: Préfixe des fichiers .ttile (ex: "Terrain_", "ZBK_terrain_")
        block_budget: Budget QTRE textures/bloc (5 ou 7), optionnel

    Returns:
        0 si succès, 1 si erreur
    """
    print("=" * 80)
    print("TILE INSPECTOR V2 - Export JSON")
    print("=" * 80)
    print()
    budget_str = f", block_budget={block_budget}" if block_budget else ""
    print(f"[TILE_INSPECTOR] Dossier={tiles_dir}, préfixe={tile_prefix}, grid_w={grid_w}, num_blk={num_blk}{budget_str}")
    print()

    if not tiles_dir.exists():
        print(f"❌ Dossier introuvable: {tiles_dir}")
        return 1

    # Lister tous les .ttile avec le bon préfixe via regex
    import re
    pattern = re.compile(rf'^{re.escape(tile_prefix)}(\d+)\.ttile$')
    ttile_files = sorted([f for f in tiles_dir.glob("*.ttile") if pattern.match(f.name)])

    if not ttile_files:
        print(f"❌ Aucun fichier .ttile trouvé dans {tiles_dir} avec préfixe '{tile_prefix}'")
        return 1

    print(f"📂 {len(ttile_files)} fichier(s) .ttile trouvés")
    print(f"📤 Export vers: {output_path}")
    print()

    # Dry-run : afficher nombre de tuiles
    print(f"🔍 Analyse de {len(ttile_files)} tuile(s)...")
    print()

    tiles_data = []

    for ttile_path in ttile_files:
        # Extraire tile_id depuis le nom de fichier via regex
        match = pattern.match(ttile_path.name)
        if not match:
            print(f"⚠️  Nom invalide, skip: {ttile_path.name}")
            continue

        try:
            tid = int(match.group(1))
        except ValueError:
            print(f"⚠️  Nom invalide, skip: {ttile_path.name}")
            continue

        # Calculer tx, ty depuis tid
        tx = tid % grid_w
        ty = tid // grid_w

        # Charger LRS2
        lrs2_blocks = load_lrs2_from_ttile(ttile_path, grid_w, num_blk, block_budget)
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

# -------------------------------------------------------------------------------
# POINT D'ENTRÉE PRINCIPAL
# -------------------------------------------------------------------------------
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
    parser.add_argument(
        "--grid-w",
        type=int,
        metavar="GRID_W",
        help="Nombre de tuiles par côté (ex: 32 pour Zimnitrita, 64 pour ZBK)"
    )
    parser.add_argument(
        "--num-blk",
        type=int,
        metavar="NUM_BLK",
        help="Nombre de blocs par tile et par côté (ex: 4)"
    )
    parser.add_argument(
        "--prefix",
        type=str,
        metavar="PREFIX",
        help="Préfixe des fichiers .ttile (ex: 'Terrain_', 'ZBK_terrain_')"
    )
    parser.add_argument(
        "--block-budget",
        type=int,
        metavar="BUDGET",
        help="Budget QTRE textures/bloc (5 ou 7), optionnel"
    )

    args = parser.parse_args()

    # Mode export JSON
    if args.export_json:
        if not args.tiles_dir:
            print("❌ --export-json nécessite --tiles-dir")
            return 1

        if not args.grid_w or args.grid_w <= 0:
            print("❌ --export-json nécessite --grid-w (entier > 0)")
            return 1

        if not args.num_blk or args.num_blk <= 0:
            print("❌ --export-json nécessite --num-blk (entier > 0)")
            return 1

        if not args.prefix:
            print("❌ --export-json nécessite --prefix (chaîne non vide)")
            return 1

        if args.block_budget is not None and args.block_budget not in (5, 7):
            print("❌ --block-budget doit être 5 ou 7")
            return 1

        return export_json(args.tiles_dir, args.export_json, args.grid_w, args.num_blk, args.prefix, args.block_budget)

    # Mode interactif NON MIGRÉ
    print("=" * 80)
    print("❌ ERREUR : Mode interactif non migré (grille dynamique)")
    print("=" * 80)
    print()
    print("Utiliser : --export-json OUTPUT_PATH --tiles-dir DIR --grid-w N --num-blk M --prefix PREFIX")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
