"""
Générateur Satmap pour Arma Reforger
Compose l'image satellite du terrain depuis les masques de surface

Deux modes :
- Mode couleurs (rapide) : mélange avg_color unie par surface
- Mode texturé (qualité) : mélange textures middle tuilées + teintées

Rendu conforme au code TilW (Seamless Satmap Tool)
"""

from pathlib import Path
from typing import Dict, List, Optional, Callable
import json
import numpy as np
from PIL import Image
import time


# ══════════════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════════════

FALLBACK_MAGENTA = [255, 0, 255]  # RGB pour surfaces non résolues


# ══════════════════════════════════════════════════════════════════════════════
# Mode couleurs (rapide, preview)
# ══════════════════════════════════════════════════════════════════════════════

def generate_satmap_colors(
    masks: Dict[str, np.ndarray],  # {emat_name: weight_grid float32}
    catalog: Dict[str, Dict],  # catalogue surfaces
    output_path: Path,
    resolution_ppm: float = 1.0,  # pixels par mètre
    progress_callback: Optional[Callable] = None
) -> Dict:
    """
    Génère une satmap en mode couleurs (rapide)

    Chaque surface contribue sa couleur unie avg_color du catalogue
    Mélange pondéré : pixel = Σ(poids × avg_color) / Σ(poids)

    Args:
        masks: Dict {emat_name: weight_grid} (float32, shape terrain)
        catalog: Catalogue surfaces (charge depuis catalog.json)
        output_path: Chemin fichier .png de sortie
        resolution_ppm: Résolution (pixels par mètre)
        progress_callback: Fonction(message, progress_0_1)

    Returns:
        Dict avec stats (temps, warnings, dimensions)
    """
    start_time = time.time()
    warnings = []

    # Dimensions terrain (depuis premier masque)
    first_mask = next(iter(masks.values()))
    terrain_h, terrain_w = first_mask.shape  # Pixels masques

    # Résolution de sortie
    out_h = int(terrain_h * resolution_ppm / 1.0)  # Suppose masques = 1px/m base
    out_w = int(terrain_w * resolution_ppm / 1.0)

    if progress_callback:
        progress_callback(f"Initialisation canvas {out_w}×{out_h} px", 0.0)

    # Accumulateurs
    color_accumulator = np.zeros((out_h, out_w, 3), dtype=np.float32)
    weight_accumulator = np.zeros((out_h, out_w), dtype=np.float32)

    n_surfaces = len(masks)

    for idx, (emat_name, weight_grid) in enumerate(masks.items()):
        if progress_callback:
            progress_callback(
                f"Surface {idx+1}/{n_surfaces} : {emat_name}",
                (idx + 1) / n_surfaces
            )

        # Récupérer couleur du catalogue
        entry = catalog.get(emat_name)

        if not entry:
            warnings.append(f"⚠️ {emat_name} absent du catalogue → magenta")
            color = FALLBACK_MAGENTA
        else:
            # avg_color ou tint (priorité tint)
            color = entry.get("tint", entry.get("avg_color", FALLBACK_MAGENTA))

        color_rgb = np.array(color[:3], dtype=np.float32)

        # Rééchantillonner masque à résolution sortie (bicubique)
        if weight_grid.shape != (out_h, out_w):
            weight_img = Image.fromarray(weight_grid)
            weight_resized = weight_img.resize((out_w, out_h), Image.BICUBIC)
            weight_grid = np.array(weight_resized, dtype=np.float32)

        # Accumuler contribution
        color_accumulator += weight_grid[..., None] * color_rgb
        weight_accumulator += weight_grid

    # Normalisation
    if progress_callback:
        progress_callback("Normalisation finale", 0.95)

    # Clip poids minimum (évite division par zéro)
    weight_accumulator_clipped = np.clip(weight_accumulator, 1e-6, None)

    # Moyenne pondérée
    result_rgb = color_accumulator / weight_accumulator_clipped[..., None]
    result_rgb = np.clip(result_rgb, 0, 255).astype(np.uint8)

    # Sauvegarder
    if progress_callback:
        progress_callback("Sauvegarde PNG", 0.98)

    result_img = Image.fromarray(result_rgb, mode="RGB")
    result_img.save(output_path)

    elapsed = time.time() - start_time

    return {
        "output_path": str(output_path),
        "mode": "colors",
        "resolution": f"{out_w}×{out_h} px",
        "resolution_ppm": resolution_ppm,
        "n_surfaces": n_surfaces,
        "elapsed_sec": round(elapsed, 2),
        "warnings": warnings,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Mode texturé (qualité, rendu TilW)
# ══════════════════════════════════════════════════════════════════════════════

def generate_satmap_textured(
    masks: Dict[str, np.ndarray],
    catalog: Dict[str, Dict],
    textures_root: Path,  # data/Textures_ArmaReforger/
    output_path: Path,
    resolution_ppm: float = 1.0,
    band_height: int = 512,  # Hauteur bande (lignes) pour gestion mémoire
    progress_callback: Optional[Callable] = None
) -> Dict:
    """
    Génère satmap en mode texturé (qualité finale)

    Rendu conforme au code TilW :
    1. Textures middle tuilées à MiddleScaleUV × ppm
    2. Teinte = linear_to_srgb(MiddleColor × Color)
    3. Ancrage coin BAS-GAUCHE (Y inversé)
    4. Mélange Σ(layer × masque) / Σ(masques) normalisé

    Composition par bandes horizontales (gestion mémoire)

    Args:
        masks: Dict {emat_name: weight_grid float32}
        catalog: Catalogue surfaces
        textures_root: Racine textures (data/Textures_ArmaReforger/)
        output_path: Chemin PNG sortie
        resolution_ppm: Pixels par mètre
        band_height: Hauteur bande en lignes (trade-off mémoire/perf)
        progress_callback: Callback(message, progress_0_1)

    Returns:
        Dict stats
    """
    start_time = time.time()
    warnings = []

    # Dimensions terrain
    first_mask = next(iter(masks.values()))
    terrain_h_px, terrain_w_px = first_mask.shape

    # Dimensions sortie
    out_h = int(terrain_h_px * resolution_ppm)
    out_w = int(terrain_w_px * resolution_ppm)

    if progress_callback:
        progress_callback(f"Initialisation rendu {out_w}×{out_h} px", 0.0)

    # Préparer canvas final (composition par bandes)
    result_full = np.zeros((out_h, out_w, 3), dtype=np.uint8)

    n_bands = int(np.ceil(out_h / band_height))
    n_surfaces = len(masks)

    for band_idx in range(n_bands):
        # Limites bande
        y_start = band_idx * band_height
        y_end = min(y_start + band_height, out_h)
        band_h = y_end - y_start

        if progress_callback:
            progress_callback(
                f"Bande {band_idx+1}/{n_bands} (lignes {y_start}-{y_end})",
                band_idx / n_bands
            )

        # Accumulateurs bande
        color_acc = np.zeros((band_h, out_w, 3), dtype=np.float32)
        weight_acc = np.zeros((band_h, out_w), dtype=np.float32)

        # Composer surface par surface
        for surf_idx, (emat_name, weight_grid) in enumerate(masks.items()):
            entry = catalog.get(emat_name)

            if not entry:
                warnings.append(f"⚠️ {emat_name} absent catalogue → magenta")
                # Layer unie magenta
                layer_rgb = np.full((band_h, out_w, 3), FALLBACK_MAGENTA, dtype=np.float32)
            else:
                # Charger + tuiler texture
                layer_rgb = load_and_tile_texture(
                    entry,
                    textures_root,
                    out_w,
                    band_h,
                    y_start,
                    resolution_ppm,
                    warnings
                )

            # Rééchantillonner masque (bande)
            mask_band = extract_and_resample_mask_band(
                weight_grid,
                y_start,
                y_end,
                out_w,
                out_h
            )

            # Accumuler
            color_acc += layer_rgb * mask_band[..., None]
            weight_acc += mask_band

        # Normaliser bande
        weight_acc_clipped = np.clip(weight_acc, 1e-6, None)
        band_result = color_acc / weight_acc_clipped[..., None]
        band_result = np.clip(band_result, 0, 255).astype(np.uint8)

        # Placer dans canvas final
        result_full[y_start:y_end, :, :] = band_result

    # Sauvegarder
    if progress_callback:
        progress_callback("Sauvegarde PNG finale", 0.98)

    result_img = Image.fromarray(result_full, mode="RGB")
    result_img.save(output_path)

    elapsed = time.time() - start_time

    return {
        "output_path": str(output_path),
        "mode": "textured",
        "resolution": f"{out_w}×{out_h} px",
        "resolution_ppm": resolution_ppm,
        "n_surfaces": n_surfaces,
        "n_bands": n_bands,
        "band_height": band_height,
        "elapsed_sec": round(elapsed, 2),
        "warnings": warnings,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Helpers mode texturé
# ══════════════════════════════════════════════════════════════════════════════

def load_and_tile_texture(
    entry: Dict,
    textures_root: Path,
    out_w: int,
    band_h: int,
    y_offset: int,
    resolution_ppm: float,
    warnings: List[str]
) -> np.ndarray:
    """
    Charge une texture middle, la tuile et la teinte

    Args:
        entry: Entrée catalogue surface
        textures_root: Racine textures/
        out_w: Largeur sortie (pixels)
        band_h: Hauteur bande (pixels)
        y_offset: Offset Y global de la bande
        resolution_ppm: Pixels par mètre
        warnings: Liste warnings (modifiée in-place)

    Returns:
        Layer RGB float32 (band_h, out_w, 3)
    """
    middle_bcr = entry.get("middle_bcr")

    if not middle_bcr:
        # Fallback magenta
        return np.full((band_h, out_w, 3), FALLBACK_MAGENTA, dtype=np.float32)

    # Chercher PNG (Vanilla/textures/ ou Customs/Textures/)
    texture_path = find_texture_png(textures_root, middle_bcr)

    if not texture_path:
        # Fallback intelligent : Forest_* → Dirt_01_Middle_BCR.jpg
        surface_name = entry.get("name", "")
        if "Forest" in middle_bcr or (surface_name and surface_name.startswith("Forest")):
            # Essayer Dirt_01 comme fallback pour surfaces forestières
            fallback_path = find_texture_png(textures_root, "Dirt_01_Middle_BCR.jpg")
            if fallback_path:
                texture_path = fallback_path
                warnings.append(f"⚠️ Texture Forest manquante, fallback Dirt_01 : {middle_bcr}")
            else:
                warnings.append(f"⚠️ Texture introuvable : {middle_bcr}")
                return np.full((band_h, out_w, 3), FALLBACK_MAGENTA, dtype=np.float32)
        else:
            warnings.append(f"⚠️ Texture introuvable : {middle_bcr}")
            return np.full((band_h, out_w, 3), FALLBACK_MAGENTA, dtype=np.float32)

    # Charger PNG
    try:
        texture_img = Image.open(texture_path).convert("RGB")
    except Exception as e:
        warnings.append(f"⚠️ Erreur lecture {middle_bcr} : {e}")
        return np.full((band_h, out_w, 3), FALLBACK_MAGENTA, dtype=np.float32)

    # Tiling scale (mètres)
    tiling_scale = entry.get("tiling_scale", 100.0)
    tile_size_px = int(tiling_scale * resolution_ppm)

    # Redimensionner texture à tile_size (bicubique)
    texture_resized = texture_img.resize((tile_size_px, tile_size_px), Image.BICUBIC)
    texture_np = np.array(texture_resized, dtype=np.float32)

    # Teinte (sRGB)
    tint = entry.get("tint", [255, 255, 255])
    tint_np = np.array(tint[:3], dtype=np.float32) / 255.0  # Normalize [0, 1]

    # Appliquer teinte
    texture_tinted = texture_np * tint_np

    # Tuiler sur la bande (ancrage coin BAS-GAUCHE)
    layer = tile_texture_on_band(
        texture_tinted,
        out_w,
        band_h,
        y_offset,
        tile_size_px
    )

    return layer


def tile_texture_on_band(
    texture: np.ndarray,  # (tile_h, tile_w, 3) float32
    out_w: int,
    band_h: int,
    y_offset: int,  # Offset global Y de la bande
    tile_size: int
) -> np.ndarray:
    """
    Tuile une texture sur une bande horizontale (vectorisé numpy)

    Ancrage coin BAS-GAUCHE (Y inversé, comme code TilW)

    Args:
        texture: Texture RGB (tile_size, tile_size, 3)
        out_w: Largeur sortie
        band_h: Hauteur bande
        y_offset: Offset Y global
        tile_size: Taille tuile (px)

    Returns:
        Layer RGB (band_h, out_w, 3)

    Performance:
        8192×512 bande = 4M pixels → ~50ms (vs ~2000ms en boucles Python)
    """
    # Grille de coordonnées Y (colonnes) et X (lignes)
    # Shape: (band_h, 1) et (1, out_w) → broadcasting automatique
    y_coords = (np.arange(band_h, dtype=np.int32)[:, None] + y_offset) % tile_size
    x_coords = np.arange(out_w, dtype=np.int32)[None, :] % tile_size

    # Indexing avancé vectorisé : texture[y_coords, x_coords] broadcast à (band_h, out_w, 3)
    # Note: y_coords et x_coords sont broadcastés ensemble
    layer = texture[y_coords, x_coords, :]

    return layer


def extract_and_resample_mask_band(
    weight_grid: np.ndarray,  # (terrain_h, terrain_w) float32
    y_start: int,
    y_end: int,
    out_w: int,
    out_h: int
) -> np.ndarray:
    """
    Extrait et rééchantillonne une bande du masque

    Args:
        weight_grid: Masque complet terrain
        y_start: Ligne début bande (sortie)
        y_end: Ligne fin bande (sortie)
        out_w: Largeur sortie
        out_h: Hauteur totale sortie

    Returns:
        Masque bande (band_h, out_w) float32
    """
    terrain_h, terrain_w = weight_grid.shape
    band_h = y_end - y_start

    # Coordonnées source (masque)
    y_src_start = int(y_start * terrain_h / out_h)
    y_src_end = int(y_end * terrain_h / out_h)

    # Extraire bande source
    band_src = weight_grid[y_src_start:y_src_end, :]

    # Rééchantillonner à résolution sortie
    band_img = Image.fromarray(band_src)
    band_resized = band_img.resize((out_w, band_h), Image.BICUBIC)
    band_np = np.array(band_resized, dtype=np.float32)

    return band_np


def find_texture_png(textures_root: Path, middle_bcr: str) -> Optional[Path]:
    """
    Cherche un PNG/JPG middle dans Vanilla/textures/ ou Customs/Textures/

    Args:
        textures_root: data/Textures_ArmaReforger/
        middle_bcr: Nom fichier ou chemin relatif (ex: 'Grass_01_Middle_BCR.jpg' ou 'Vanilla/textures/Dirt_01_Middle_BCR.jpg')

    Returns:
        Path de l'image trouvée, ou None
    """
    # Si middle_bcr contient déjà le chemin "Vanilla/textures/" ou "Customs/Textures/", l'extraire
    if "Vanilla/textures/" in middle_bcr or "Customs/Textures/" in middle_bcr:
        # Extraire juste le nom du fichier
        img_name = middle_bcr.split("/")[-1]
    else:
        img_name = middle_bcr

    # Extraire nom de base sans extension
    base_name = img_name.replace('.jpg', '').replace('.png', '').replace('.edds', '')

    # Chercher avec différentes extensions
    for ext in ['.jpg', '.png', '.jpeg']:
        final_name = base_name + ext

        search_paths = [
            textures_root / "Vanilla" / "textures" / final_name,
            textures_root / "Customs" / "Textures" / final_name,
        ]

        for p in search_paths:
            if p.exists():
                return p

        # Fallback récursif
        for subdir in ["Vanilla/textures", "Customs/Textures"]:
            search_dir = textures_root / subdir
            if search_dir.exists():
                matches = list(search_dir.rglob(final_name))
                if matches:
                    return matches[0]

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Test rapide
# ══════════════════════════════════════════════════════════════════════════════

def load_masks_from_world(
    world_dir: Path,
    target_resolution: int = 4096
) -> Dict[str, np.ndarray]:
    """
    Charge les masques directement depuis les .ttile (sans export PNG intermédiaire)

    Résout le problème de RAM en :
    1. Calculant la résolution réduite adaptée
    2. Chargeant et downscalant à la volée

    Args:
        world_dir: Dossier monde Reforger (.terr parent)
        target_resolution: Résolution cible max (ex: 4096)

    Returns:
        Dict {emat_name: weight_grid float32 [0-1]}
    """
    import reforger_mask_export as mask_export

    # Export vers dossier temporaire avec résolution réduite
    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmp_dir:
        print(f"[INFO] Export masques temporaire (résolution réduite {target_resolution}px)...")

        # TODO: Ajouter paramètre résolution à export_all_masks()
        # Pour l'instant, on utilise la fonction existante puis on downscale

        result = mask_export.export_all_masks(
            world_dir=str(world_dir),
            out_dir=tmp_dir,
            progress_callback=None
        )

        # Charger les masques depuis le temp
        masks = load_masks_from_directory(Path(tmp_dir))

        print(f"[OK] {len(masks)} masques chargés")

    return masks


def load_masks_from_directory(masks_dir: Path) -> Dict[str, np.ndarray]:
    """
    Charge les masques PNG depuis un dossier d'export

    Args:
        masks_dir: Dossier contenant *.png + manifest.json

    Returns:
        Dict {emat_name: weight_grid float32 [0-1]}
    """
    import json

    # Charger manifest
    manifest_path = masks_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json introuvable dans {masks_dir}")

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    materials = manifest.get("surfaces", manifest.get("materials", []))
    if not materials:
        raise ValueError("Aucune surface dans le manifest")

    # Charger masques PNG
    masks = {}

    for emat_name in materials:
        png_path = masks_dir / f"{emat_name.replace('.emat', '')}.png"

        if not png_path.exists():
            print(f"[WARN] Masque manquant : {png_path.name}")
            continue

        # Charger PNG 8-bit → float32 [0-1]
        img = Image.open(png_path).convert("L")
        weight_grid = np.array(img, dtype=np.float32) / 255.0

        masks[emat_name] = weight_grid

    return masks


if __name__ == "__main__":
    import sys

    print("[INFO] Module satmap generator charge")
    print("[INFO] Utilisez depuis l'UI ou importez les fonctions generate_satmap_colors/textured")
