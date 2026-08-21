"""
Generateur Satmap v2.0 — Rendu couleurs depuis catalogue avg_color
Utilise les couleurs moyennes calculées des vraies textures BCR
"""

import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Optional
from tqdm import tqdm

# Import modules
from layer_dds_reader import read_layer_dds, extract_all_weights
from lrs2_parser import load_lrs2_from_ttile, get_tile_coords_from_ttile
from terrain_terr_reader import read_mats_from_terr
from satmap_verifiers import verify_environment


# Aliases : texture_name → nom_canonique dans le catalog
# Ajouter ici les textures "b" qui partagent le même middle qu'une texture existante
TEXTURE_ALIASES: dict[str, str] = {
    # Exemples — à compléter selon les besoins
    # "Grass_03b": "Grass_03",
    # "Rock_01b": "Rock_01",
}


def resolve_catalog_entry(surface_name: str, catalog: dict) -> dict | None:
    """Cherche surface_name dans catalog, avec fallback sur TEXTURE_ALIASES."""
    entry = catalog.get(surface_name) or catalog.get(surface_name + ".emat")
    if entry:
        return entry
    canonical = TEXTURE_ALIASES.get(surface_name)
    if canonical:
        return catalog.get(canonical) or catalog.get(canonical + ".emat")
    return None


def load_catalog(catalog_path: Path) -> Dict:
    """Charge le catalogue de textures enrichi"""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_material_color(mat_id: int, catalog: Dict, surfaces: List[str]) -> np.ndarray:
    """Retourne la couleur RGB — avg_color avec assombrissement global."""
    if mat_id >= len(surfaces):
        return np.array([255, 0, 255], dtype=np.uint8)

    surface_name = surfaces[mat_id]
    if isinstance(surface_name, dict):
        surface_name = surface_name.get("emat", surface_name.get("name", ""))
    entry = resolve_catalog_entry(surface_name, catalog)

    if entry is None:
        print(f"  [NO CATALOG] mat_id={mat_id} name='{surface_name}'")
        return np.array([75, 110, 48], dtype=np.uint8)

    avg = entry.get("avg_color")
    if not avg or avg == [0, 0, 0]:
        # Essayer tint_srgb comme fallback
        tint = entry.get("tint_srgb") or entry.get("tint")
        if tint and tint != [0, 0, 0]:
            return np.array(tint[:3], dtype=np.uint8)
        return np.array([75, 110, 48], dtype=np.uint8)  # vert neutre

    return np.array(avg[:3], dtype=np.uint8)


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

    Args:
        mat_id: ID du matériau
        catalog: Catalogue de textures
        surfaces: Liste des surfaces
        middles_dir: Dossier contenant les PNG middle
        middles_cache: Cache des textures déjà chargées {mat_id: np.ndarray}
        tile_size: Taille de la tuile en pixels (défaut 512)

    Returns:
        Image RGB (tile_size, tile_size, 3) en float32 [0-255]
    """
    # Vérifier cache
    if mat_id in middles_cache:
        return middles_cache[mat_id]

    # Fallback couleur plate
    color_flat = get_material_color(mat_id, catalog, surfaces).astype(np.float32)
    fallback = np.full((tile_size, tile_size, 3), color_flat, dtype=np.float32)

    if mat_id >= len(surfaces):
        middles_cache[mat_id] = fallback
        return fallback

    surface_name = surfaces[mat_id]
    entry = resolve_catalog_entry(surface_name, catalog)

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
        print(f"[MISS] {surface_name} → {middle_path}")
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
        # tile_size = 512px = 2048m dans le monde Reforger
        world_size_m = 2048.0
        repeat = max(1, min(32, round(world_size_m / tiling_scale)))

        # Tuiler l'image
        h, w = middle_img.shape[:2]

        # Créer une grille de répétitions
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


def generate_tile_satmap_textured(
    tile_id: int,
    editor_data_dir: Path,
    data_dir: Path,
    catalog: Dict,
    surfaces: List[str],
    middles_dir: Path = None,
    middles_cache: Dict[int, np.ndarray] = None
) -> Optional[np.ndarray]:
    """Genere la satmap d'une tuile (utilise avg_color du catalogue ou textures middle)."""
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
    if not lrs2_blocks:
        # ttile absent ou LRS2 corrompu — rendu SeaBed direct depuis middle
        seabed_id = next((i for i, s in enumerate(surfaces) if 'seabed' in (s if isinstance(s, str) else s.get('emat', s.get('name', ''))).lower()), 0)
        if middles_dir and middles_cache is not None:
            mid = get_material_middle(seabed_id, catalog, surfaces_list, middles_dir, middles_cache, tile_size=512)
            return np.clip(mid, 0, 255).astype(np.uint8)
        else:
            color = get_material_color(seabed_id, catalog, surfaces_list)
            return np.full((512, 512, 3), color, dtype=np.uint8)

    # Extraire poids (512, 512, 7)
    weights = extract_all_weights(layer_img)

    # Image resultat
    result = np.zeros((512, 512, 3), dtype=np.float32)

    # Pour chaque bloc (4x4 = 16 blocs)
    for by in range(4):
        for bx in range(4):
            mat_ids = lrs2_blocks.get((bx, by), [])
            if len(mat_ids) == 0:
                # Fallback : chercher SeaBed dans surfaces_list
                seabed_id = next((i for i, s in enumerate(surfaces) if 'seabed' in (s if isinstance(s, str) else s.get('emat', s.get('name', ''))).lower()), 0)
                mat_ids = [seabed_id]
            if len(mat_ids) == 0:
                continue

            x0 = bx * 128
            y0 = by * 128
            x1 = x0 + 128
            y1 = y0 + 128

            raw = weights[y0:y1, x0:x1, :]

            # w0 implicite
            if raw.shape[2] == 6:
                w0 = np.clip(1.0 - raw.sum(axis=-1), 0, 1.0)
            else:
                w0 = raw[:, :, 0]

            block_canvas = np.zeros((128, 128, 3), dtype=np.float32)
            total_w = np.zeros((128, 128), dtype=np.float32)

            # Matériau 0 (w0)
            if middles_dir is not None and middles_cache is not None:
                mid0 = get_material_middle(mat_ids[0], catalog, surfaces, middles_dir, middles_cache, tile_size=128)
            else:
                mid0 = np.full((128, 128, 3), get_material_color(mat_ids[0], catalog, surfaces).astype(np.float32))
            block_canvas += w0[:, :, None] * mid0
            total_w += w0

            # Matériaux explicites
            for k in range(1, min(len(mat_ids), 7)):
                if raw.shape[2] == 6:
                    w = raw[:, :, k-1]
                else:
                    w = raw[:, :, k]
                if np.max(w) < 0.001:
                    continue
                mat_id = mat_ids[k]
                if middles_dir is not None and middles_cache is not None:
                    mid = get_material_middle(mat_id, catalog, surfaces, middles_dir, middles_cache, tile_size=128)
                else:
                    mid = np.full((128, 128, 3), get_material_color(mat_id, catalog, surfaces).astype(np.float32))
                block_canvas += w[:, :, None] * mid
                total_w += w

            # Normaliser
            total_w = np.where(total_w < 0.001, 1.0, total_w)
            block_canvas = block_canvas / total_w[:, :, None]
            result[y0:y1, x0:x1] = block_canvas

    # Convertir en uint8
    result = np.clip(result, 0, 255).astype(np.uint8)

    return result


def generate_satmap_v2_textured_complete(
    terrain_dir: Path,
    catalog_path: Path,
    output_path: Path,
    terr_file: Path = None,
    mode: str = "colors",
    target_resolution: int = 4097,
    verbose: bool = False,
    middles_dir: Path = None
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
        middles_dir: Dossier contenant les PNG middle (None = mode couleurs plates)
    """
    # Fonction wrapper pour print conditionnel
    def log(msg=""):
        if verbose:
            print(msg)

    log("="*80)
    log(f"GENERATION SATMAP v2.0 - Mode {mode.upper()}")
    log("="*80)
    log(f"Resolution cible : {target_resolution}x{target_resolution}")
    log(f"   middles_dir : {middles_dir}")
    log()

    editor_data_dir = terrain_dir / ".EditorData"
    data_dir = terrain_dir / ".Data"

    # Charger catalogue
    log("Chargement catalogue...")
    catalog = load_catalog(catalog_path)
    log(f"   OK {len(catalog)} surfaces")
    log(f"   Exemple clé : {list(catalog.keys())[0] if catalog else 'VIDE'}")
    log()

    # Charger liste surfaces depuis Terrain.terr (source de vérité Enfusion)
    log("Chargement liste surfaces...")
    surfaces_list = None

    if terr_file:
        try:
            mats = read_mats_from_terr(terr_file)
            surfaces_list = [e["emat"] for e in mats]
            log(f"   OK {len(surfaces_list)} surfaces depuis {Path(terr_file).name}")
        except Exception as e:
            log(f"   ERREUR {e}")
            surfaces_list = None

    if surfaces_list is None:
        log("   Fallback : utilisation catalogue complet")
        surfaces_list = list(catalog.keys())

    log(f"   Surfaces finales : {len(surfaces_list)}\n")

    # Vérifier environnement (layers manquants, matériaux sans couleur)
    missing_layers, material_issues = verify_environment(
        editor_data_dir, data_dir, surfaces_list, catalog
    )
    if missing_layers:
        log(f"⚠️ {len(missing_layers)} layers manquants traités automatiquement")
    if material_issues:
        log(f"⚠️ {len(material_issues)} matériaux sans couleur → fallback Grass_03")
        for _mi in material_issues:
            log(f"   [NO COLOR] {_mi}")

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

    # Cache des textures middle
    middles_cache = {} if middles_dir else None
    log(f"   middles_cache initialisé : {middles_cache is not None}")

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
            middles_dir, middles_cache
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

    # Générer automatiquement satmap_fond_512.png (terre/eau depuis heightmap)
    try:
        import cv2 as _cv2
        dem_norm = dem  # dem déjà chargé en mémoire
        water_thresh = float(np.percentile(dem_norm[dem_norm > dem_norm.min()], 10))
        fond = np.where(
            dem_norm < water_thresh,
            np.array([45, 30, 20], dtype=np.uint8),   # eau — BGR bleu foncé
            np.array([35, 55, 40], dtype=np.uint8)    # terre — BGR vert foncé
        ).astype(np.uint8)
        fond_512 = _cv2.resize(fond, (512, 512), interpolation=_cv2.INTER_AREA)
        fond_path = output_path.parent.parent.parent / "inputs" / "satmap_fond_512.png"
        fond_path.parent.mkdir(parents=True, exist_ok=True)
        _cv2.imwrite(str(fond_path), fond_512)
        log(f"✅ satmap_fond_512.png générée → {fond_path}")
    except Exception as e:
        log(f"⚠️ satmap_fond_512 non générée : {e}")

    # Post-processing : corriger les pixels noirs isolés
    # (tuiles avec LRS2 compressé non décodable → pixels [0,0,0])
    satmap_bgr = cv2.imread(str(output_path))
    if satmap_bgr is not None:
        black_mask = (satmap_bgr[:,:,0] < 10) & (satmap_bgr[:,:,1] < 10) & (satmap_bgr[:,:,2] < 10)
        n_black = int(black_mask.sum())
        if n_black > 0:
            log(f"⚠️ {n_black} pixels noirs détectés — correction par interpolation voisins...")
            from scipy.ndimage import generic_filter
            for c in range(3):
                channel = satmap_bgr[:,:,c].astype(np.float32)
                def fill_black(values):
                    center = values[len(values)//2]
                    if center < 10:
                        neighbors = values[values >= 10]
                        return neighbors.mean() if len(neighbors) > 0 else center
                    return center
                channel_fixed = generic_filter(channel, fill_black, size=5)
                satmap_bgr[:,:,c] = np.where(black_mask, channel_fixed.astype(np.uint8), satmap_bgr[:,:,c])
            cv2.imwrite(str(output_path), satmap_bgr)
            log(f"✅ Pixels noirs corrigés → {output_path}")

    log()
    log("="*80)
    log("OK SATMAP v2.0 GENEREE !")
    log("="*80)
    log(f"Fichier : {output_path}")
    log(f"Taille : {satmap.shape[1]}x{satmap.shape[0]}")

    # Retourner stats pour affichage dans Streamlit
    return {
        "tiles": len(tile_data),
        "missing_layers": len(missing_layers) if missing_layers else 0,
        "material_issues": len(material_issues) if material_issues else 0,
        "output": str(output_path),
        "size": f"{satmap.shape[1]}×{satmap.shape[0]}"
    }
