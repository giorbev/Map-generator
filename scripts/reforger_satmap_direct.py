"""
Générateur Satmap Direct - Lecture QTRE depuis monde Reforger
Sans export PNG intermédiaire, résolution 4k standard
"""

from pathlib import Path
from typing import Dict, Optional, Callable
import numpy as np
from PIL import Image
import json
import time


def generate_satmap_from_world(
    world_terr_path: str,
    output_path: Path,
    mode: str = "colors",  # "colors" ou "textured"
    resolution: int = 4097,  # 4k standard Reforger
    catalog_path: Path = None,
    textures_root: Path = None,
    progress_callback: Optional[Callable] = None
) -> Dict:
    """
    Génère une satmap directement depuis le monde Reforger (lecture QTRE)

    Workflow :
    1. Lit .ttile (QTRE) du monde
    2. Calcule masques à la volée (résolution 4k)
    3. Génère satmap (couleurs ou texturé)

    Args:
        world_terr_path: Chemin vers Terrain.terr
        output_path: Chemin PNG de sortie
        mode: "colors" (rapide) ou "textured" (qualité)
        resolution: Résolution cible (défaut 4097 = 4k Reforger)
        catalog_path: Chemin catalog.json (auto si None)
        textures_root: Racine textures (auto si None)
        progress_callback: Callback(message, progress_0_1)

    Returns:
        Dict avec stats (temps, résolution, warnings)
    """
    import reforger_mask_export as mask_export
    import reforger_satmap_generator as satmap_gen

    start_time = time.time()

    if progress_callback:
        progress_callback("Initialisation", 0.0)

    # ── Charger catalogue ──────────────────────────────────────────────────

    if catalog_path is None:
        catalog_path = Path("data/Textures_ArmaReforger/catalog.json")

    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalogue introuvable : {catalog_path}")

    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    if textures_root is None:
        textures_root = Path("data/Textures_ArmaReforger")

    # ── Export masques temporaires (résolution 4k) ─────────────────────────

    if progress_callback:
        progress_callback("Lecture terrain QTRE", 0.1)

    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Export masques vers temp (downscale auto 4k)
        export_result = mask_export.export_all_masks(
            world_dir=str(Path(world_terr_path).parent),
            out_dir=tmp_dir,
            progress_callback=lambda msg, pct: progress_callback(
                f"Export masques : {msg}",
                0.1 + pct * 0.4
            ) if progress_callback else None,
            target_resolution=resolution
        )

        masks_dir = Path(export_result['output_dir'])

        # Charger masques depuis temp
        if progress_callback:
            progress_callback("Chargement masques", 0.5)

        masks = satmap_gen.load_masks_from_directory(masks_dir)

        # ── Générer satmap ──────────────────────────────────────────────────

        if mode == "colors":
            # Mode couleurs (rapide)
            if progress_callback:
                progress_callback("Génération satmap couleurs", 0.6)

            result = satmap_gen.generate_satmap_colors(
                masks=masks,
                catalog=catalog,
                output_path=output_path,
                resolution_ppm=1.0,  # Déjà en résolution cible
                progress_callback=lambda msg, pct: progress_callback(
                    f"Satmap couleurs : {msg}",
                    0.6 + pct * 0.4
                ) if progress_callback else None
            )

        else:  # mode == "textured"
            # Mode texturé (qualité)
            if progress_callback:
                progress_callback("Génération satmap texturée", 0.6)

            result = satmap_gen.generate_satmap_textured(
                masks=masks,
                catalog=catalog,
                textures_root=textures_root,
                output_path=output_path,
                resolution_ppm=1.0,  # Déjà en résolution cible
                band_height=512,
                progress_callback=lambda msg, pct: progress_callback(
                    f"Satmap texturée : {msg}",
                    0.6 + pct * 0.4
                ) if progress_callback else None
            )

    elapsed = time.time() - start_time

    if progress_callback:
        progress_callback("Terminé", 1.0)

    return {
        "output_path": str(output_path),
        "mode": mode,
        "resolution": f"{resolution}×{resolution} px",
        "n_surfaces": len(masks),
        "elapsed_sec": round(elapsed, 2),
        "warnings": result.get('warnings', []),
    }


if __name__ == "__main__":
    print("[INFO] Module satmap direct chargé")
    print("[INFO] Utilisez generate_satmap_from_world() pour générer depuis un monde Reforger")
