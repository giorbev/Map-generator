"""
check_terrain_health.py — Diagnostic et réparation des fichiers terrain manquants

Usage:
    python check_terrain_health.py --scan
    python check_terrain_health.py --scan --fix --default-mat Grass_03_default
    python check_terrain_health.py --scan --fix --template-tile 0
"""

import argparse
import sys
from pathlib import Path

from app_config import resolve_paths
from edds_decoder import create_default_layer_dds


def scan_terrain(data_dir: Path, editor_dir: Path) -> dict:
    """
    Scanne les dossiers terrain et retourne un rapport des fichiers manquants.
    """
    results = {
        "total_tiles": 0,
        "missing_layer_dds": [],
        "missing_bterr": [],
        "missing_ttile": [],
        "ok": [],
    }

    # Lister toutes les tuiles depuis les ttile dans .Data
    ttile_files = sorted(data_dir.glob("Terrain_*.ttile"))
    tile_ids = []
    for f in ttile_files:
        stem = f.stem  # Terrain_18
        parts = stem.split("_")
        if len(parts) == 2 and parts[1].isdigit():
            tile_ids.append(int(parts[1]))

    results["total_tiles"] = len(tile_ids)

    for tile_id in sorted(tile_ids):
        tx = tile_id % 32
        ty = tile_id // 32

        layer_path = editor_dir / f"Terrain_{tile_id}_layer.dds"
        bterr_path = editor_dir / f"Terrain_{tile_id}.bterr"
        ttile_path = data_dir / f"Terrain_{tile_id}.ttile"

        issues = []
        if not layer_path.exists():
            results["missing_layer_dds"].append((tile_id, tx, ty))
            issues.append("layer.dds")
        if not bterr_path.exists():
            results["missing_bterr"].append((tile_id, tx, ty))
            issues.append("bterr")
        edds_path = data_dir / f"Terrain_{tile_id}_layer.edds"
        if not edds_path.exists():
            if "missing_layer_edds" not in results:
                results["missing_layer_edds"] = []
            results["missing_layer_edds"].append((tile_id, tx, ty))
            issues.append("layer.edds")

        if not issues:
            results["ok"].append(tile_id)

    return results


def fix_missing_layers(
    data_dir: Path,
    editor_dir: Path,
    missing: list,
    template_tile_id: int = None,
    dry_run: bool = True
) -> int:
    """
    Crée les layer.dds manquants en utilisant un template existant.
    """
    # Choisir un template — première tuile avec layer.dds existant
    if template_tile_id is None:
        for f in sorted(editor_dir.glob("Terrain_*_layer.dds")):
            parts = f.stem.split("_")
            if len(parts) == 3 and parts[1].isdigit():
                template_tile_id = int(parts[1])
                break

    if template_tile_id is None:
        print("[ERREUR] Aucun template layer.dds trouvé dans EditorData")
        return 0

    template_path = editor_dir / f"Terrain_{template_tile_id}_layer.dds"
    print(f"[INFO] Template : {template_path}")
    print()

    fixed = 0
    for tile_id, tx, ty in missing:
        output_path = editor_dir / f"Terrain_{tile_id}_layer.dds"
        print(f"  Tuile {tile_id} ({tx},{ty}) → {output_path.name}", end="")

        if dry_run:
            print(" [DRY-RUN]")
        else:
            ok = create_default_layer_dds(output_path, template_path)
            if ok:
                print(" ✅")
                fixed += 1
            else:
                print(" ❌")

    return fixed


def main():
    parser = argparse.ArgumentParser(
        description="Diagnostic et réparation des fichiers terrain manquants"
    )
    parser.add_argument("--addon-path", type=str, required=True,
                        help="Chemin racine de l'addon Reforger")
    parser.add_argument("--scan", action="store_true", default=True,
                        help="Scanner les fichiers manquants (défaut)")
    parser.add_argument("--fix", action="store_true",
                        help="Créer les layer.dds manquants")
    parser.add_argument("--template-tile", type=int, default=None,
                        help="ID de la tuile à utiliser comme template (défaut: auto)")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Simulation sans écriture (défaut: True)")
    parser.add_argument("--no-dry-run", action="store_false", dest="dry_run",
                        help="Appliquer réellement les corrections")

    args = parser.parse_args()

    # Résoudre les chemins
    rp = resolve_paths(args.addon_path)
    if not rp.get("valid"):
        print(f"[ERREUR] Chemin addon invalide : {rp.get('error')}")
        sys.exit(1)

    data_dir = Path(rp["data_dir"])
    editor_dir = Path(rp["editor_dir"])

    print("=" * 70)
    print("CHECK TERRAIN HEALTH")
    print("=" * 70)
    print(f"Data dir    : {data_dir}")
    print(f"Editor dir  : {editor_dir}")
    print()

    # Scan
    results = scan_terrain(data_dir, editor_dir)

    print(f"Tuiles scannées    : {results['total_tiles']}")
    print(f"OK                 : {len(results['ok'])}")
    print(f"layer.dds manquant : {len(results['missing_layer_dds'])}")
    print(f".bterr manquant    : {len(results['missing_bterr'])}")
    print()

    if results["missing_layer_dds"]:
        print("=== LAYER.DDS MANQUANTS ===")
        for tile_id, tx, ty in results["missing_layer_dds"]:
            print(f"  Terrain_{tile_id} (tx={tx}, ty={ty})")
        print()

    if results.get("missing_layer_edds"):
        print("=== LAYER.EDDS MANQUANTS (.Data) ===")
        for tile_id, tx, ty in results["missing_layer_edds"]:
            print(f"  Terrain_{tile_id} (tx={tx}, ty={ty})")
        print()

    if results["missing_bterr"]:
        print("=== .BTERR MANQUANTS ===")
        for tile_id, tx, ty in results["missing_bterr"]:
            print(f"  Terrain_{tile_id} (tx={tx}, ty={ty})")
        print()

    # Fix
    if args.fix and results["missing_layer_dds"]:
        print("=== CRÉATION LAYER.DDS MANQUANTS ===")
        if args.dry_run:
            print("[DRY-RUN] Aucune écriture — passer --no-dry-run pour appliquer")
            print()

        fixed = fix_missing_layers(
            data_dir, editor_dir,
            results["missing_layer_dds"],
            template_tile_id=args.template_tile,
            dry_run=args.dry_run
        )

        if not args.dry_run:
            print()
            print(f"[OK] {fixed}/{len(results['missing_layer_dds'])} layer.dds créés")
    elif args.fix and not results["missing_layer_dds"]:
        print("[OK] Aucun layer.dds manquant — rien à corriger")

    if args.fix and results.get("missing_layer_edds"):
        print("=== CRÉATION LAYER.EDDS MANQUANTS ===")
        if args.dry_run:
            print("[DRY-RUN] Aucune écriture — passer --no-dry-run pour appliquer")
            print()
        fixed_edds = 0
        for tile_id, tx, ty in results["missing_layer_edds"]:
            output_path = data_dir / f"Terrain_{tile_id}_layer.edds"
            template_path = next(data_dir.glob("Terrain_*_layer.edds"), None)
            print(f"  Tuile {tile_id} ({tx},{ty}) → {output_path.name}", end="")
            if args.dry_run:
                print(" [DRY-RUN]")
            else:
                from edds_decoder import create_default_layer_dds
                ok = create_default_layer_dds(output_path, template_path)
                if ok:
                    print(" ✅")
                    fixed_edds += 1
                else:
                    print(" ❌")
        if not args.dry_run:
            print(f"[OK] {fixed_edds}/{len(results['missing_layer_edds'])} layer.edds créés")

    print()
    print("=" * 70)
    if results["missing_layer_dds"] or results["missing_bterr"] or results.get("missing_layer_edds"):
        print(f"VERDICT : {len(results['missing_layer_dds'])} layer.dds manquants, "
              f"{len(results.get('missing_layer_edds', []))} layer.edds manquants, "
              f"{len(results['missing_bterr'])} .bterr manquants")
        sys.exit(1)
    else:
        print("VERDICT : Terrain complet — aucun fichier manquant")
        sys.exit(0)


if __name__ == "__main__":
    main()
