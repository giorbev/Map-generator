"""
Tile Inspector - scan global des tuiles .ttile d'un projet (bouton Global Scan d'Inspection)

export_json : matériaux par bloc et budget QTRE de chaque tuile, écrits en JSON.
Le reste de l'ancien Tile Inspector v2 (mode interactif, rendu, pente, tuiles voisines)
est archivé dans _archives/code/2026-11-02_etape11a/ (étape 11a).
"""

import json
from pathlib import Path
from typing import Optional
import sys
import argparse
from datetime import datetime

# Import modules existants
from lrs2_parser import load_lrs2_from_ttile


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
