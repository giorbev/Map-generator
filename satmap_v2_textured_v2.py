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
from reforger_emat_parser import parse_emat_params, compute_tint_srgb, find_emat_file


def linear_to_srgb(c: np.ndarray) -> np.ndarray:
    """Convertit un array float32 [0-1] de linéaire vers sRGB."""
    out = np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.clip(c, 0, None), 1/2.4) - 0.055)
    return np.clip(out, 0, 1)


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
    m_per_px: float = 1.0,
    emat_dir: Optional[Path] = None
) -> np.ndarray:
    """
    Retourne le middle redimensionné pour échelle correcte, prêt à échantillonner.
    Si middle non disponible, retourne un aplat couleur 1×1.

    Args:
        mat_id: ID du matériau
        catalog: Catalogue de textures
        surfaces: Liste des surfaces
        middles_dir: Dossier contenant les PNG middle
        middles_cache: Cache {mat_id: middle redimensionné}
        m_per_px: Mètres par pixel du canvas global (défaut 1.0)
        emat_dir: Dossier des .emat pour lecture tint

    Returns:
        Middle redimensionné RGB (H, W, 3) en float32 [0-255]
        Taille : une répétition fait tiling_scale / m_per_px pixels
    """
    # Vérifier cache
    if mat_id in middles_cache:
        return middles_cache[mat_id]

    # Fallback couleur plate (motif 1×1)
    color_flat = get_material_color(mat_id, catalog, surfaces).astype(np.float32)
    fallback = np.full((1, 1, 3), color_flat, dtype=np.float32)

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
        # Charger image (BGR -> RGB) en float32 [0-1]
        middle_img = cv2.imread(str(middle_path))
        if middle_img is None:
            middles_cache[mat_id] = fallback
            return fallback

        middle_img = cv2.cvtColor(middle_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

        # Appliquer tint depuis .emat (MiddleColor × Color) comme TilW
        tint_rgb = None
        if emat_dir is not None:
            emat_path = emat_dir / surface_name
            if emat_path.exists():
                params = parse_emat_params(emat_path, [emat_dir])
                middle_color = params.get("MiddleColor", "1 1 1 1")
                color = params.get("Color", "1 1 1 1")
                tint_rgb = compute_tint_srgb(middle_color, color)

        # Fallback sur tint_srgb du catalog si pas de .emat
        if tint_rgb is None:
            tint_srgb = entry.get("tint_srgb")
            if tint_srgb and tint_srgb != [0, 0, 0]:
                tint_rgb = tint_srgb[:3]

        if tint_rgb is not None:
            tint = np.array(tint_rgb, dtype=np.float32) / 255.0
            # N'appliquer le tint que s'il n'est pas blanc (1,1,1)
            if not np.allclose(tint, [1.0, 1.0, 1.0], atol=0.02):
                middle_img = middle_img * tint[None, None, :]
                middle_img = np.clip(middle_img, 0, 1)

        # Pas de gamma — utiliser les middles BCR bruts comme TilW

        # Reconvertir en [0-255]
        middle_img = (middle_img * 255.0).astype(np.float32)

        # Calculer taille d'une répétition en pixels
        # tiling_scale (m) / m_per_px (m/px) = pixels par répétition
        repeat_size_px = max(1, int(round(tiling_scale / m_per_px)))

        # Redimensionner middle pour qu'une répétition fasse repeat_size_px
        middle_resized = cv2.resize(
            middle_img,
            (repeat_size_px, repeat_size_px),
            interpolation=cv2.INTER_AREA
        )

        result = np.clip(middle_resized, 0, 255)
        middles_cache[mat_id] = result
        return result

    except Exception as e:
        print(f"[ERR] {surface_name} : {e}")
        middles_cache[mat_id] = fallback
        return fallback


def sample_middle_tiled(
    middle: np.ndarray,
    x_global: int,
    y_global: int,
    width: int,
    height: int
) -> np.ndarray:
    """
    Échantillonne le middle avec répétition par modulo (vectorisé numpy).

    Args:
        middle: Middle redimensionné (repeat_size_px × repeat_size_px × 3)
        x_global, y_global: Coordonnées globales du coin supérieur gauche
        width, height: Taille de la zone à extraire

    Returns:
        Zone extraite (height, width, 3) en float32
    """
    repeat_h, repeat_w = middle.shape[:2]

    # Grilles de coordonnées globales
    xs_global = x_global + np.arange(width)
    ys_global = y_global + np.arange(height)

    # Modulo pour répétition
    xs = xs_global % repeat_w
    ys = ys_global % repeat_h

    # Échantillonner avec np.ix_
    result = middle[np.ix_(ys, xs)]

    return result


def generate_tile_satmap_textured(
    tile_id: int,
    editor_data_dir: Path,
    data_dir: Path,
    catalog: Dict,
    surfaces: List[str],
    middles_dir: Path = None,
    middles_cache: Dict[int, np.ndarray] = None,
    emat_dir: Optional[Path] = None,
    tile_x_global: int = 0,
    tile_y_global: int = 0,
    m_per_px: float = 1.0
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
            mid_full = get_material_middle(seabed_id, catalog, surfaces, middles_dir, middles_cache, m_per_px=m_per_px, emat_dir=emat_dir)
            # Échantillonner avec coordonnées globales de la tuile
            mid = sample_middle_tiled(mid_full, tile_x_global, tile_y_global, 512, 512)
            return np.clip(mid, 0, 255).astype(np.uint8)
        else:
            color = get_material_color(seabed_id, catalog, surfaces)
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

            # Coordonnées globales dans le canvas complet
            x0_global = tile_x_global + x0
            y0_global = tile_y_global + y0

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
                mid0_full = get_material_middle(mat_ids[0], catalog, surfaces, middles_dir, middles_cache, m_per_px=m_per_px, emat_dir=emat_dir)
                mid0 = sample_middle_tiled(mid0_full, x0_global, y0_global, 128, 128)
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
                    mid_full = get_material_middle(mat_id, catalog, surfaces, middles_dir, middles_cache, m_per_px=m_per_px, emat_dir=emat_dir)
                    mid = sample_middle_tiled(mid_full, x0_global, y0_global, 128, 128)
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
    target_resolution: Optional[int] = 4097,
    verbose: bool = False,
    middles_dir: Path = None,
    emat_dir: Optional[Path] = None,
    world_size_m: Optional[float] = None,
    echelle_m_per_px: Optional[float] = None
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
    res_str = "native" if target_resolution is None else f"{target_resolution}x{target_resolution}"
    log(f"Resolution cible : {res_str}")
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

    # Calculer mètres par pixel
    canvas_width = grid_width * 512
    canvas_height = grid_height * 512

    # Calcul échelle (priorité : Workbench > world_size_m > défaut 1.0)
    if echelle_m_per_px is not None:
        # Priorité 1 : Valeurs Workbench
        m_per_px = echelle_m_per_px
        log(f"   Échelle : {m_per_px:.3f} m/px (Workbench)")
    elif world_size_m is not None:
        # Priorité 2 : world_size_m (si jamais passé)
        m_per_px = world_size_m / canvas_width
        log(f"   Monde : {world_size_m:.0f}m × {world_size_m:.0f}m")
        log(f"   Échelle : {m_per_px:.3f} m/px (calculé depuis world_size_m)")
    else:
        # Priorité 3 : Défaut 1.0 + WARNING
        m_per_px = 1.0
        log(f"⚠️ WARNING: Valeurs Workbench absentes, échelle par défaut 1.000 m/px")
    log()

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

        # Coordonnées globales dans le canvas
        y0 = ty * 512
        x0 = tx * 512

        # Generer tuile
        tile_img = generate_tile_satmap_textured(
            tile_id, editor_data_dir, data_dir, catalog, surfaces_list,
            middles_dir, middles_cache, emat_dir,
            tile_x_global=x0, tile_y_global=y0, m_per_px=m_per_px
        )

        # Placer dans canvas
        # Les coordonnées LRS2 sont utilisées telles quelles
        # Le flip vertical final inverse tout le canvas pour corriger l'orientation

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
    canvas_width = canvas.shape[1]
    canvas_height = canvas.shape[0]

    if target_resolution is None or target_resolution == 0:
        # Mode native explicite
        log(f"Résolution native : {canvas_width}×{canvas_height}")
        satmap = canvas
        final_resolution = 0  # Marqueur "native"
    elif target_resolution >= canvas_width:
        # Pas d'upscale : utiliser native
        log(f"⚠️ WARNING: Résolution demandée {target_resolution} ≥ native {canvas_width}, satmap native utilisée")
        satmap = canvas
        final_resolution = 0  # Marqueur "native"
    else:
        # Downscale
        log(f"Downscale {canvas_width}×{canvas_height} -> {target_resolution}×{target_resolution}...")
        satmap = cv2.resize(canvas, (target_resolution, target_resolution), interpolation=cv2.INTER_AREA)
        final_resolution = target_resolution

    # Nommage selon règle
    if final_resolution == 0:
        # Native
        filename = "satmap_v2_textured_native.png"
    else:
        # Downscale
        filename = f"satmap_v2_textured_{final_resolution}.png"

    final_path = output_path.parent / filename
    log(f"Sauvegarde : {final_path} ({satmap.shape[1]}×{satmap.shape[0]})")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(final_path), cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR))

    # Générer automatiquement satmap_fond_512.png (version réduite de la satmap finale)
    try:
        # Convertir RGB → BGR pour cv2.imwrite
        satmap_bgr_fond = cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR)

        # Réduire à 512×512 sans flou
        fond_512 = cv2.resize(satmap_bgr_fond, (512, 512), interpolation=cv2.INTER_AREA)

        # Sauvegarder
        fond_path = final_path.parent.parent.parent / "inputs" / "satmap_fond_512.png"
        fond_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(fond_path), fond_512)
        log(f"✅ satmap_fond_512.png générée → {fond_path.absolute()}")
    except Exception as e:
        log(f"⚠️ satmap_fond_512 non générée : {e}")

    # Post-processing : corriger les pixels noirs isolés
    # (tuiles avec LRS2 compressé non décodable → pixels [0,0,0])
    satmap_bgr = cv2.imread(str(final_path))
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
            cv2.imwrite(str(final_path), satmap_bgr)
            log(f"✅ Pixels noirs corrigés → {final_path}")

    log()
    log("="*80)
    log("OK SATMAP v2.0 GENEREE !")
    log("="*80)
    log(f"Fichier : {final_path.absolute()}")
    log(f"Taille : {satmap.shape[1]}x{satmap.shape[0]}")

    # Retourner stats pour affichage dans Streamlit
    return {
        "tiles": len(tile_data),
        "missing_layers": len(missing_layers) if missing_layers else 0,
        "material_issues": len(material_issues) if material_issues else 0,
        "output_path": str(final_path),
        "size": f"{satmap.shape[1]}×{satmap.shape[0]}"
    }
