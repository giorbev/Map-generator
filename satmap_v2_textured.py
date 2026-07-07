"""
Generateur Satmap v2.0 MODE TEXTURE

Utilise les vraies textures middle BCR + tiling + tints
pour generer une satmap photo-realiste
"""

import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm

# Import modules
from layer_dds_reader import read_layer_dds, extract_all_weights
from lrs2_parser import load_lrs2_from_ttile, get_tile_coords_from_ttile
from terrain_materials_parser import load_surfaces_list_from_world
from reforger_emat_parser import parse_emat_params, compute_tint_srgb, find_emat_file
from satmap_verifiers import verify_environment


def load_catalog(catalog_path: Path) -> Dict:
    """Charge le catalogue de textures enrichi"""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def compute_tint_from_emat(
    surface_name: str,
    emat_dir: Path,
    tint_cache: Dict[str, Tuple[int, int, int]]
) -> Optional[Tuple[int, int, int]]:
    """
    Calcule le tint RGB d'une surface en lisant son .emat à la volée (méthode TilW)

    Args:
        surface_name: Nom du .emat (ex: "Grass_03.emat")
        emat_dir: Dossier contenant les .emat
        tint_cache: Cache des tints déjà calculés

    Returns:
        (R, G, B) tuple ou None
    """
    # Vérifier cache
    if surface_name in tint_cache:
        return tint_cache[surface_name]

    # Chercher le .emat
    emat_path = find_emat_file([emat_dir], surface_name)
    if not emat_path:
        tint_cache[surface_name] = None
        return None

    # Parser .emat avec héritage
    params = parse_emat_params(emat_path, [emat_dir])

    # Calculer tint : linear_to_srgb(MiddleColor × Color)
    middle_color = params.get('MiddleColor', '1 1 1 1')
    color = params.get('Color', '1 1 1 1')

    tint_rgb = compute_tint_srgb(middle_color, color)

    # Mettre en cache
    tint_cache[surface_name] = tint_rgb

    return tint_rgb


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
    base_name = middle_bcr.rsplit(".", 1)[0] if "." in middle_bcr else middle_bcr

    # Chercher avec extensions possibles
    for ext in ['.jpg', '.png', '.jpeg']:
        # Chercher dans texture_Middle/textures (chemin correct)
        middle_path = textures_root / "texture_Middle" / "textures" / (base_name + ext)
        if middle_path.exists():
            return middle_path

        # Fallback anciens chemins (au cas où)
        vanilla_path = textures_root / "Vanilla" / "textures" / (base_name + ext)
        if vanilla_path.exists():
            return vanilla_path

        customs_path = textures_root / "Customs" / (base_name + ext)
        if customs_path.exists():
            return customs_path

    return None


def load_material_texture(
    mat_id: int,
    catalog: Dict,
    surfaces: List[str],
    textures_root: Path,
    texture_cache: Dict[str, np.ndarray]
) -> Optional[np.ndarray]:
    """
    Charge la texture middle BCR d'un materiau (avec cache)

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

    # Verifier cache
    if middle_bcr in texture_cache:
        return texture_cache[middle_bcr]

    # Chercher le fichier texture
    texture_path = find_texture_file(textures_root, middle_bcr)

    if texture_path is None:
        # Fallback pour Forest textures
        if "Forest" in middle_bcr or "forest" in surface_name.lower():
            fallback_path = find_texture_file(textures_root, "Dirt_01_Middle_BCR.jpg")
            if fallback_path:
                texture_path = fallback_path

    if texture_path is None:
        texture_cache[middle_bcr] = None
        return None

    # Charger image
    try:
        img = cv2.imread(str(texture_path))
        if img is None:
            texture_cache[middle_bcr] = None
            return None
        # Convertir BGR -> RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        texture_cache[middle_bcr] = img
        return img
    except:
        texture_cache[middle_bcr] = None
        return None


def apply_tint_to_texture(texture: np.ndarray, tint_rgb: Tuple[int, int, int]) -> np.ndarray:
    """
    Applique un tint a une texture

    Args:
        texture: (H, W, 3) uint8
        tint_rgb: (R, G, B) uint8

    Returns:
        Texture tintee (H, W, 3) uint8
    """
    tint = np.array(tint_rgb, dtype=np.float32) / 255.0
    texture_f = texture.astype(np.float32) / 255.0

    # Multiplier
    result = texture_f * tint[None, None, :]

    # Reconvertir
    result = np.clip(result * 255, 0, 255).astype(np.uint8)

    return result


def tile_texture(
    texture: np.ndarray,
    width: int,
    height: int,
    tile_size_meters: float,
    pixels_per_meter: float = 1.0
) -> np.ndarray:
    """
    Tuile une texture pour couvrir une zone donnee

    Args:
        texture: (H, W, 3) texture source
        width, height: Taille zone en pixels
        tile_size_meters: Taille tuile texture en metres (MiddleScaleUV)
        pixels_per_meter: Resolution (pixels par metre)

    Returns:
        (height, width, 3) texture tuilee
    """
    # Taille d'une tuile en pixels de sortie
    tile_px = int(tile_size_meters * pixels_per_meter)

    if tile_px <= 0:
        tile_px = 1

    # Nombre de tuiles necessaires
    n_tiles_x = int(np.ceil(width / tile_px))
    n_tiles_y = int(np.ceil(height / tile_px))

    # Redimensionner texture source a tile_px
    tex_h, tex_w = texture.shape[:2]
    if tex_h != tile_px or tex_w != tile_px:
        texture_resized = cv2.resize(texture, (tile_px, tile_px), interpolation=cv2.INTER_LINEAR)
    else:
        texture_resized = texture

    # Creer canvas
    canvas = np.zeros((n_tiles_y * tile_px, n_tiles_x * tile_px, 3), dtype=np.uint8)

    # Tuiler
    for ty in range(n_tiles_y):
        for tx in range(n_tiles_x):
            y0 = ty * tile_px
            x0 = tx * tile_px
            canvas[y0:y0+tile_px, x0:x0+tile_px] = texture_resized

    # Crop a la taille exacte
    return canvas[:height, :width]


def get_material_color(mat_id: int, catalog: Dict, surfaces: List[str]) -> np.ndarray:
    """
    Retourne la couleur RGB d'un materiau (fallback si pas de texture)

    Args:
        mat_id: ID global du materiau
        catalog: Catalogue enrichi
        surfaces: Liste globale des surfaces

    Returns:
        np.array([R, G, B], dtype=uint8)
    """
    # Fallback si ID hors limites
    if mat_id >= len(surfaces):
        # Retourner gris au lieu de magenta pour ne pas polluer la satmap
        return np.array([75, 110, 48], dtype=np.uint8)  # Grass_03 par défaut

    surface_name = surfaces[mat_id]

    if surface_name not in catalog:
        return np.array([75, 110, 48], dtype=np.uint8)  # Grass_03 par défaut

    entry = catalog[surface_name]

    # STRATEGIE HYBRIDE :
    # - Surfaces custom (ZI_*, custom_*) : avg_color (couleur observée)
    # - Surfaces vanilla : tint_srgb (calculé MiddleColor × Color)
    # - Exception : ZI_Ground_Sport_01 → tint_srgb (rouge correct)
    # Raison : Les customs ont Color comme tint modificateur, pas couleur finale

    is_custom = surface_name.startswith('ZI_') or surface_name.startswith('custom_')

    # Exception pour terrains de sport (tint_srgb correct)
    if surface_name == 'ZI_Ground_Sport_01.emat':
        if 'tint_srgb' in entry and entry['tint_srgb']:
            r, g, b = entry['tint_srgb']
            return np.array([r, g, b], dtype=np.uint8)

    if is_custom:
        # Custom : priorité avg_color
        if 'avg_color' in entry and entry['avg_color']:
            r, g, b = entry['avg_color'][:3]
            return np.array([r, g, b], dtype=np.uint8)
        elif 'tint_srgb' in entry and entry['tint_srgb']:
            r, g, b = entry['tint_srgb']
            return np.array([r, g, b], dtype=np.uint8)
    else:
        # Vanilla : priorité tint_srgb (méthode TilW)
        if 'tint_srgb' in entry and entry['tint_srgb']:
            r, g, b = entry['tint_srgb']
            return np.array([r, g, b], dtype=np.uint8)
        elif 'avg_color' in entry and entry['avg_color']:
            r, g, b = entry['avg_color'][:3]
            return np.array([r, g, b], dtype=np.uint8)

    return np.array([75, 110, 48], dtype=np.uint8)  # Grass_03 par défaut


def generate_tile_satmap_textured(
    tile_id: int,
    editor_data_dir: Path,
    data_dir: Path,
    catalog: Dict,
    surfaces: List[str],
    textures_root: Path,
    texture_cache: Dict[str, np.ndarray],
    tint_cache: Dict[str, Tuple[int, int, int]],
    emat_dir: Path,
    mode: str = "colors"
) -> Optional[np.ndarray]:
    """
    Genere la satmap d'une tuile (mode colors ou textured)

    Args:
        tile_id: Numero tuile
        editor_data_dir: Dossier .EditorData
        data_dir: Dossier .Data
        catalog: Catalogue enrichi
        surfaces: Liste globale surfaces
        textures_root: Racine textures
        texture_cache: Cache textures
        mode: "colors" ou "textured"

    Returns:
        np.array (512, 512, 3) uint8 RGB
    """
    GRASS_FALLBACK = np.full((512, 512, 3), [75, 110, 48], dtype=np.uint8)

    # Fichiers necessaires
    layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.dds"
    ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
    supertexture_path = editor_data_dir / f"Terrain_{tile_id}_supertexture.dds"

    if not layer_path.exists():
        return GRASS_FALLBACK.copy()

    if not ttile_path.exists():
        return GRASS_FALLBACK.copy()

    # Charger layer.dds
    layer_img = read_layer_dds(layer_path)
    if layer_img is None:
        return GRASS_FALLBACK.copy()

    # Charger LRS2
    lrs2_blocks = load_lrs2_from_ttile(ttile_path)
    if lrs2_blocks is None:
        return GRASS_FALLBACK.copy()

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

            # Canvas pour ce bloc
            block_canvas = np.zeros((128, 128, 3), dtype=np.float32)

            raw = weights[y0:y1, x0:x1, :]  # (128,128,6) ou (128,128,7)

            # w0 implicite : matériau de base mat_ids[0]
            if raw.shape[2] == 6:
                # Cas 6 canaux : w1..w6 explicites, w0 calculé (déjà normalisé [0,1])
                w0 = np.clip(1.0 - raw.sum(axis=-1), 0, 1.0)
            else:
                # Cas 7 canaux : w0 déjà en canal 0 (déjà normalisé [0,1])
                w0 = raw[:, :, 0]

            color0 = get_material_color(mat_ids[0], catalog, surfaces)
            block_canvas += w0[:, :, None] * color0[None, None, :].astype(np.float32)

            # Matériaux explicites mat_ids[1]..mat_ids[n-1]
            for k in range(1, min(len(mat_ids), 7)):
                if raw.shape[2] == 6:
                    w = raw[:, :, k-1]  # w1=canal 0, w2=canal 1... (déjà normalisé)
                else:
                    w = raw[:, :, k]  # déjà normalisé

                if np.max(w) < 0.001:
                    continue

                mat_id = mat_ids[k]
                if mode == "textured":
                    texture = load_material_texture(mat_id, catalog, surfaces, textures_root, texture_cache)
                    if texture is not None:
                        surface_name = surfaces[mat_id] if mat_id < len(surfaces) else None
                        tile_size_meters = 4.0
                        if surface_name and surface_name in catalog:
                            entry = catalog[surface_name]
                            if 'tiling_scale' in entry and entry['tiling_scale']:
                                tile_size_meters = entry['tiling_scale']
                        textured = tile_texture(texture, 128, 128, tile_size_meters, pixels_per_meter=1.0)
                        if surface_name:
                            tint_rgb = compute_tint_from_emat(surface_name, emat_dir, tint_cache)
                            if tint_rgb:
                                textured = apply_tint_to_texture(textured, tint_rgb)
                        block_canvas += w[:, :, None] * textured.astype(np.float32)
                    else:
                        color = get_material_color(mat_id, catalog, surfaces)
                        block_canvas += w[:, :, None] * color[None, None, :].astype(np.float32)
                else:
                    color = get_material_color(mat_id, catalog, surfaces)
                    block_canvas += w[:, :, None] * color[None, None, :].astype(np.float32)

            # Placer dans resultat
            result[y0:y1, x0:x1] = block_canvas

    # Convertir en uint8
    result = np.clip(result, 0, 255).astype(np.uint8)

    return result


def generate_satmap_v2_textured_complete(
    terrain_dir: Path,
    catalog_path: Path,
    output_path: Path,
    mode: str = "colors",
    target_resolution: int = 4097,
    verbose: bool = False
):
    """
    Genere la satmap complete en mode textured

    Args:
        terrain_dir: Dossier Terrain/
        catalog_path: Chemin vers catalog.json
        output_path: Chemin sortie satmap.png
        mode: "colors" ou "textured"
        target_resolution: Resolution finale (4097 = 4k)
        verbose: Afficher messages de progression (False par defaut)
    """
    # Fonction wrapper pour print conditionnel
    def log(msg=""):
        if verbose:
            print(msg)

    log("="*80)
    log(f"GENERATION SATMAP v2.0 - Mode {mode.upper()}")
    log("="*80)
    log(f"Resolution cible : {target_resolution}x{target_resolution}")
    log()

    editor_data_dir = terrain_dir / ".EditorData"
    data_dir = terrain_dir / ".Data"
    textures_root = catalog_path.parent

    # Charger catalogue
    log("Chargement catalogue...")
    catalog = load_catalog(catalog_path)
    log(f"   OK {len(catalog)} surfaces\n")

    # Charger liste surfaces depuis terrain_materials_list.txt
    log("Chargement liste surfaces...")
    surfaces_list = load_surfaces_list_from_world(terrain_dir)

    if surfaces_list is None:
        log("ERREUR Impossible de charger terrain_materials_list.txt")
        log("Fallback : utilisation catalogue complet")
        surfaces_list = list(catalog.keys())

    log(f"   OK {len(surfaces_list)} surfaces\n")

    # Vérifier environnement (layers manquants, matériaux sans couleur)
    missing_layers, material_issues = verify_environment(
        editor_data_dir, data_dir, surfaces_list, catalog
    )
    if missing_layers:
        log(f"⚠️ {len(missing_layers)} layers manquants traités automatiquement")
    if material_issues:
        log(f"⚠️ {len(material_issues)} matériaux sans couleur → fallback Grass_03")

    # Cache textures et tints
    texture_cache = {}
    tint_cache = {}

    # Dossier .emat
    emat_dir = catalog_path.parent / "emat"

    # Detecter tuiles et extraire COORDONNÉES RÉELLES depuis LRS2
    layer_files = list(editor_data_dir.glob("Terrain_*_layer.dds"))

    # Extraire numéros et coordonnées
    tile_data = {}  # {tile_id: (tile_x, tile_y)}

    for f in layer_files:
        # Terrain_1015_layer.dds -> 1015
        parts = f.stem.split('_')
        if len(parts) >= 2:
            try:
                tile_id = int(parts[1])

                # Lire coordonnées RÉELLES depuis .ttile
                ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
                coords = get_tile_coords_from_ttile(ttile_path)

                if coords:
                    tile_data[tile_id] = coords
                else:
                    log(f"   ATTENTION: Tuile {tile_id} sans coordonnées LRS2 (ignorée)")

            except ValueError:
                continue

    num_tiles = len(tile_data)
    log(f"Detection tuiles : {num_tiles} fichiers avec coordonnées valides")

    # Déterminer grille depuis coordonnées MAX
    all_coords = list(tile_data.values())
    max_x = max(x for x, y in all_coords)
    max_y = max(y for x, y in all_coords)

    grid_width = max_x + 1
    grid_height = max_y + 1

    log(f"   Grille : {grid_width}x{grid_height} (depuis coordonnées LRS2)")
    log(f"   Canvas : {grid_width * 512}x{grid_height * 512} pixels")
    log()

    # Canvas natif 512 px/tuile
    canvas_width = grid_width * 512
    canvas_height = grid_height * 512

    log(f"Resolution native : {canvas_width}x{canvas_height}")
    log(f"   Downscale -> {target_resolution}x{target_resolution}")
    log()

    # Canvas (initialisé en vert Grass_03 pour les zones hors-grille)
    canvas = np.full((canvas_height, canvas_width, 3), [75, 110, 48], dtype=np.uint8)

    # Generer tuiles
    log("Generation tuiles...")

    # Utiliser tqdm seulement si verbose
    tile_ids_sorted = sorted(tile_data.keys())
    iterator = tqdm(tile_ids_sorted) if verbose else tile_ids_sorted

    for tile_id in iterator:
        # Coordonnées RÉELLES depuis LRS2
        tx, ty = tile_data[tile_id]

        # Generer tuile
        tile_img = generate_tile_satmap_textured(
            tile_id, editor_data_dir, data_dir, catalog, surfaces_list,
            textures_root, texture_cache, tint_cache, emat_dir, mode=mode
        )

        # Placer dans canvas
        # Les coordonnées LRS2 sont utilisées telles quelles
        # Le flip vertical final inverse tout le canvas pour corriger l'orientation
        y0 = ty * 512
        x0 = tx * 512

        if tile_img is None:
            continue  # Ne devrait plus arriver avec le fallback ci-dessus

        # Vérifier limites
        if y0 < 0 or y0 + 512 > canvas.shape[0] or x0 + 512 > canvas.shape[1]:
            log(f"ATTENTION: Tuile {tile_id} hors limites (tx={tx}, ty={ty}, canvas={canvas.shape[0]}x{canvas.shape[1]})")
            continue

        canvas[y0:y0+512, x0:x0+512] = tile_img

    log()

    # Flip vertical (l'image est a l'envers)
    log("Flip vertical...")
    canvas = np.flip(canvas, axis=0)

    # Downscale si nécessaire
    if canvas_width != target_resolution or canvas_height != target_resolution:
        log(f"Downscale {canvas_width}x{canvas_height} -> {target_resolution}x{target_resolution}...")
        satmap = cv2.resize(canvas, (target_resolution, target_resolution), interpolation=cv2.INTER_AREA)
    else:
        satmap = canvas

    # Sauvegarder
    log(f"Sauvegarde : {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR))

    log()
    log("="*80)
    log("OK SATMAP v2.0 GENEREE !")
    log("="*80)
    log(f"Fichier : {output_path}")
    log(f"Taille : {satmap.shape[1]}x{satmap.shape[0]}")
    log(f"Textures en cache : {len([k for k, v in texture_cache.items() if v is not None])}")

    # Retourner stats pour affichage dans Streamlit
    return {
        "tiles": len(tile_data),
        "missing_layers": len(missing_layers) if missing_layers else 0,
        "material_issues": len(material_issues) if material_issues else 0,
        "output": str(output_path),
        "size": f"{satmap.shape[1]}×{satmap.shape[0]}"
    }
