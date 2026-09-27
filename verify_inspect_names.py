#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCRIPT STANDALONE — Vérification des noms de matériaux affichés dans "Inspect tuile"

Objectif : Pour une liste de blocs en coordonnées LRS2 globales, afficher côte à côte :
- Noms selon Inspect tuile (surfaces.json du projet)
- Noms selon LRS2 .ttile + table .terr du projet
- % de couverture (concordance)

Usage :
    python verify_inspect_names.py [--project PROJECT_PATH] [--blocks BLOCKS_JSON]

Exemple :
    python verify_inspect_names.py --project "H:/logiciel perso/Map generator/data/projects/Zimnitrita" --blocks "[(256,256),(271,271)]"
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import argparse
import xml.etree.ElementTree as ET

# Import modules existants
try:
    from lrs2_parser import load_lrs2_from_ttile
except ImportError as e:
    print(f"[ERREUR] Impossible d'importer les modules : {e}")
    print("[INFO] Assurez-vous d'exécuter le script depuis le dossier du projet")
    sys.exit(1)


def lrs2_to_tile_block(lrs2_x: int, lrs2_y: int) -> Tuple[int, int, int, int]:
    """
    Convertit coordonnées LRS2 globales → (tx, ty, bx, by).

    Args:
        lrs2_x, lrs2_y : Coordonnées bloc LRS2 global (0-511 pour grille 32×32)

    Returns:
        (tx, ty, bx, by) : Tuile (0-31) + Bloc (0-15)
    """
    tx = lrs2_x // 16
    ty = lrs2_y // 16
    bx = lrs2_x % 16
    by = lrs2_y % 16
    return tx, ty, bx, by


def load_surfaces_json(project_path: Path) -> Dict[int, str]:
    """
    Charge surfaces.json et retourne dict {ID: Nom}.

    Args:
        project_path : Chemin racine projet

    Returns:
        Dict {ID: Nom matériau}
    """
    surfaces_json = project_path / "surfaces.json"
    if not surfaces_json.exists():
        raise FileNotFoundError(f"surfaces.json introuvable : {surfaces_json}")

    data = json.loads(surfaces_json.read_text(encoding="utf-8"))
    materials = data.get("materials", {})

    # Inversion : Nom → ID vers ID → Nom
    id_to_name = {v: k for k, v in materials.items()}
    return id_to_name


# FONCTIONS SUPPRIMÉES (FAUSSES) - Le .terr est BINAIRE (chunk MATS), pas XML
# Implémentation correcte : terrain_terr_reader.py:read_mats_from_terr()



def get_block_materials_from_ttile(
    data_dir: Path,
    lrs2_x: int,
    lrs2_y: int,
    id_to_name: Dict[int, str]
) -> List[str]:
    """
    Lit les IDs matériaux d'un bloc depuis .ttile et convertit en noms.

    Args:
        data_dir : Dossier .Data contenant Terrain_*.ttile
        lrs2_x, lrs2_y : Coordonnées bloc LRS2
        id_to_name : Table ID → Nom

    Returns:
        Liste noms matériaux (slots w0-w7)
    """
    tx, ty, bx, by = lrs2_to_tile_block(lrs2_x, lrs2_y)
    tid = ty * 32 + tx

    ttile_path = data_dir / f"Terrain_{tid}.ttile"
    if not ttile_path.exists():
        raise FileNotFoundError(f".ttile introuvable : {ttile_path}")

    # Charger LRS2
    lrs2_data = load_lrs2_from_ttile(ttile_path)

    # Récupérer IDs du bloc
    block_key = (lrs2_x, lrs2_y)
    material_ids = lrs2_data.get(block_key, [])

    # Convertir IDs → Noms
    material_names = []
    for mat_id in material_ids:
        if mat_id == 0:
            material_names.append("(vide)")
        else:
            mat_name = id_to_name.get(mat_id, f"ID_{mat_id}")
            material_names.append(mat_name)

    return material_names


def compare_block_names(
    project_path: Path,
    blocks: List[Tuple[int, int]]
) -> List[Dict]:
    """
    Compare noms matériaux pour une liste de blocs LRS2.

    Args:
        project_path : Chemin racine projet
        blocks : Liste [(lrs2_x, lrs2_y), ...]

    Returns:
        Liste de dicts avec comparaison par bloc
    """
    print(f"[INFO] Projet : {project_path}")
    print(f"[INFO] Nombre de blocs à vérifier : {len(blocks)}")
    print()

    # Charger tables
    print("[1/4] Chargement surfaces.json...")
    surfaces_table = load_surfaces_json(project_path)
    print(f"      → {len(surfaces_table)} matériaux chargés")

    print("[2/4] Chargement table .terr...")
    terr_table = load_terr_table(project_path)
    print(f"      → {len(terr_table)} matériaux chargés")

    # Charger chemin .Data
    project_json = project_path / "project.json"
    pdata = json.loads(project_json.read_text(encoding="utf-8"))
    paths = pdata.get("paths", {})
    data_dir = Path(paths.get("data_dir", ""))

    if not data_dir.exists():
        raise FileNotFoundError(f".Data introuvable : {data_dir}")

    print(f"[3/4] Dossier .Data : {data_dir}")
    print()

    # Comparer chaque bloc
    print("[4/4] Analyse des blocs...")
    print()

    results = []
    for lrs2_x, lrs2_y in blocks:
        tx, ty, bx, by = lrs2_to_tile_block(lrs2_x, lrs2_y)
        tid = ty * 32 + tx

        print(f"  Bloc LRS2 ({lrs2_x:3d}, {lrs2_y:3d}) → Tuile T{tid:4d} (tx={tx:2d}, ty={ty:2d}) Bloc (bx={bx:2d}, by={by:2d})")

        try:
            # Noms selon surfaces.json (Inspect tuile)
            names_surfaces = get_block_materials_from_ttile(data_dir, lrs2_x, lrs2_y, surfaces_table)

            # Noms selon .terr
            names_terr = get_block_materials_from_ttile(data_dir, lrs2_x, lrs2_y, terr_table)

            # Calculer concordance
            matches = sum(1 for a, b in zip(names_surfaces, names_terr) if a == b)
            total = len(names_surfaces)
            coverage = (matches / total * 100) if total > 0 else 0

            results.append({
                "lrs2": (lrs2_x, lrs2_y),
                "tile": (tx, ty),
                "block": (bx, by),
                "tid": tid,
                "names_surfaces": names_surfaces,
                "names_terr": names_terr,
                "coverage": coverage,
                "matches": matches,
                "total": total
            })

            print(f"    Surfaces.json : {', '.join(names_surfaces[:4])}{'...' if len(names_surfaces) > 4 else ''}")
            print(f"    .terr         : {', '.join(names_terr[:4])}{'...' if len(names_terr) > 4 else ''}")
            print(f"    Concordance   : {matches}/{total} ({coverage:.1f}%)")
            print()

        except Exception as e:
            print(f"    [ERREUR] {e}")
            print()
            results.append({
                "lrs2": (lrs2_x, lrs2_y),
                "error": str(e)
            })

    return results


def print_summary_table(results: List[Dict]):
    """Affiche tableau récapitulatif."""
    print()
    print("=" * 120)
    print("TABLEAU RÉCAPITULATIF")
    print("=" * 120)
    print()
    print(f"{'Bloc LRS2':<15} | {'Tuile':<10} | {'Bloc':<10} | {'Noms surfaces.json':<30} | {'Noms .terr':<30} | {'Couverture':<12}")
    print("-" * 120)

    for r in results:
        if "error" in r:
            lrs2_str = f"({r['lrs2'][0]},{r['lrs2'][1]})"
            print(f"{lrs2_str:<15} | {'ERREUR':<10} | {'':<10} | {r['error']:<30} | {'':<30} | {'':<12}")
        else:
            lrs2_str = f"({r['lrs2'][0]},{r['lrs2'][1]})"
            tile_str = f"T{r['tid']} ({r['tile'][0]},{r['tile'][1]})"
            block_str = f"({r['block'][0]},{r['block'][1]})"
            surf_str = ', '.join(r['names_surfaces'][:2]) + ('...' if len(r['names_surfaces']) > 2 else '')
            terr_str = ', '.join(r['names_terr'][:2]) + ('...' if len(r['names_terr']) > 2 else '')
            cov_str = f"{r['coverage']:.1f}%"

            print(f"{lrs2_str:<15} | {tile_str:<10} | {block_str:<10} | {surf_str:<30} | {terr_str:<30} | {cov_str:<12}")

    print()

    # Stats globales
    valid_results = [r for r in results if "error" not in r]
    if valid_results:
        avg_coverage = sum(r["coverage"] for r in valid_results) / len(valid_results)
        print(f"Couverture moyenne : {avg_coverage:.1f}%")
        print(f"Blocs avec 100% concordance : {sum(1 for r in valid_results if r['coverage'] == 100.0)} / {len(valid_results)}")
        print(f"Blocs avec divergences : {sum(1 for r in valid_results if r['coverage'] < 100.0)} / {len(valid_results)}")

    print()


def main():
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser(
        description="Vérifier les noms de matériaux affichés dans Inspect tuile"
    )
    parser.add_argument(
        "--project",
        type=str,
        required=True,
        help="Chemin racine du projet (contenant project.json et surfaces.json)"
    )
    parser.add_argument(
        "--blocks",
        type=str,
        required=True,
        help="Liste de blocs LRS2 au format JSON : [(x1,y1),(x2,y2),...]"
    )

    args = parser.parse_args()

    # Parser blocs
    try:
        blocks = eval(args.blocks)  # [(256,256), (271,271), ...]
        if not isinstance(blocks, list):
            raise ValueError("--blocks doit être une liste")
    except Exception as e:
        print(f"[ERREUR] Format --blocks invalide : {e}")
        print("[INFO] Exemple : --blocks \"[(256,256),(271,271)]\"")
        sys.exit(1)

    project_path = Path(args.project)
    if not project_path.exists():
        print(f"[ERREUR] Projet introuvable : {project_path}")
        sys.exit(1)

    # Lancer comparaison
    try:
        results = compare_block_names(project_path, blocks)
        print_summary_table(results)

        # Log des chemins de fichiers lus
        print()
        print("=" * 120)
        print("FICHIERS LUS")
        print("=" * 120)
        print(f"  surfaces.json : {project_path / 'surfaces.json'}")
        print(f"  project.json  : {project_path / 'project.json'}")

        pdata = json.loads((project_path / "project.json").read_text(encoding="utf-8"))
        terr_file = pdata.get("paths", {}).get("terr_file")
        data_dir = pdata.get("paths", {}).get("data_dir")
        print(f"  .terr         : {terr_file}")
        print(f"  .Data/        : {data_dir}")

        for r in results:
            if "error" not in r:
                lrs2_x, lrs2_y = r["lrs2"]
                tx, ty, _, _ = lrs2_to_tile_block(lrs2_x, lrs2_y)
                tid = ty * 32 + tx
                print(f"  .ttile        : {data_dir}/Terrain_{tid}.ttile")

        print()

    except Exception as e:
        print(f"[ERREUR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Si lancé sans arguments, exemple avec Zimnitrita
    if len(sys.argv) == 1:
        print("[INFO] Aucun argument fourni, utilisation de l'exemple Zimnitrita")
        print()

        project_path = Path("H:/logiciel perso/Map generator/data/projects/Zimnitrita")
        blocks = [
            (256, 256),  # Tuile (16,16), bloc (0,0)
            (271, 271),  # Tuile (16,16), bloc (15,15)
            (0, 0),      # Tuile (0,0), bloc (0,0)
            (511, 511),  # Tuile (31,31), bloc (15,15)
        ]

        results = compare_block_names(project_path, blocks)
        print_summary_table(results)
    else:
        main()
