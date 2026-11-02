"""
Tile Inspector - scan global des tuiles .ttile d'un projet (bouton Global Scan d'Inspection)

export_json : pour chaque tuile, matériaux de chaque bloc (LRS2 du .ttile) et nombre de pixels
couverts par chaque slot (poids > 0 dans le _layer), écrits en JSON (format version 2, étape 11c).
source_signature : nombre et date la plus récente des fichiers lus, pour détecter un cache périmé.
Appelé directement par main.py, en dev comme en exe (ligne de commande retirée à l'étape 11b).
"""

import io
import json
import re
import contextlib
from pathlib import Path
from typing import Optional
from datetime import datetime

from lrs2_parser import load_lrs2_from_ttile
from clean_weights import find_layer_path, read_layer_dds

SCAN_FORMAT_VERSION = 2


# -------------------------------------------------------------------------------
# SIGNATURE DES FICHIERS SOURCES (détection d'un cache périmé)
# -------------------------------------------------------------------------------
def source_signature(tiles_dir: Path, editor_dir: Path, tile_prefix: str) -> dict:
    """
    Nombre de .ttile et de _layer du projet et date de modification la plus récente.

    Returns:
        {"n_files": int, "max_mtime": float}
    """
    files = list(tiles_dir.glob(f"{tile_prefix}*.ttile"))
    for d in (tiles_dir, editor_dir):
        files += [f for f in d.glob(f"{tile_prefix}*_layer.*") if f.suffix in (".dds", ".edds")]
    mtimes = [f.stat().st_mtime for f in files]
    return {"n_files": len(files), "max_mtime": round(max(mtimes), 3) if mtimes else 0.0}


# -------------------------------------------------------------------------------
# FONCTION D'EXPORT JSON DE TOUTES LES TILES D'UN PROJET
# -------------------------------------------------------------------------------
def export_json(tiles_dir: Path, editor_dir: Path, output_path: Path, grid_w: int, num_blk: int, tile_prefix: str, block_budget: Optional[int] = None) -> int:
    """
    Export JSON de toutes les tiles d'un projet.

    Args:
        tiles_dir: Dossier contenant les .ttile (.Data)
        editor_dir: Dossier .EditorData (_layer de repli, voir find_layer_path)
        output_path: Chemin du fichier JSON de sortie
        grid_w: Nombre de tuiles par côté
        num_blk: Nombre de blocs par tile et par côté
        tile_prefix: Préfixe des fichiers .ttile (addon_reforger du projet)
        block_budget: Budget QTRE textures/bloc (5 ou 7), optionnel

    Returns:
        0 si succès, 1 si erreur
    """
    print("=" * 80)
    print("TILE INSPECTOR - Export JSON (blocs et couverture des slots)")
    print("=" * 80)
    print()
    budget_str = f", block_budget={block_budget}" if block_budget else ""
    print(f"[TILE_INSPECTOR] Dossier={tiles_dir}, préfixe={tile_prefix}, grid_w={grid_w}, num_blk={num_blk}{budget_str}")
    print()

    if not tiles_dir.exists():
        print(f"❌ Dossier introuvable: {tiles_dir}")
        return 1

    # Lister tous les .ttile avec le bon préfixe via regex
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
    block_px = None
    n_no_layer = 0
    t_start = datetime.now()

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

        # Charger les poids (_layer), sans le log [LAYER] de chaque tuile
        with contextlib.redirect_stdout(io.StringIO()):
            layer_path = find_layer_path(tid, tiles_dir, editor_dir, tile_prefix)
        pixels = read_layer_dds(layer_path) if layer_path else None
        if pixels is None:
            n_no_layer += 1
            print(f"⚠️  _layer introuvable ou illisible, couverture absente : {ttile_path.name}")

        # Calculer max_tex_per_block, et la couverture de chaque slot par bloc
        max_tex_per_block = 0
        all_mat_ids = set()
        blocks = []

        for (bx, by), mat_ids in sorted(lrs2_blocks.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            n_tex = len(mat_ids)
            max_tex_per_block = max(max_tex_per_block, n_tex)
            all_mat_ids.update(mat_ids)

            coverage_px = None
            if pixels is not None:
                bs = pixels.shape[0] // num_blk
                block_px = bs * bs
                blk = pixels[by * bs:(by + 1) * bs, bx * bs:(bx + 1) * bs, :]
                coverage_px = [int((blk[:, :, slot] > 0).sum()) for slot in range(min(n_tex, blk.shape[2]))]
            blocks.append({"bx": bx, "by": by, "mat_ids": list(mat_ids), "coverage_px": coverage_px})

        # Construire entrée JSON
        tile_entry = {
            "tid": tid,
            "tx": tx,
            "ty": ty,
            "max_tex_per_block": max_tex_per_block,
            "n_active_mats": len(all_mat_ids),
            "active_mat_ids": sorted(list(all_mat_ids)),
            "blocks": blocks
        }

        tiles_data.append(tile_entry)

        # Afficher progression tous les 50 tiles
        if len(tiles_data) % 50 == 0:
            print(f"   ✅ {len(tiles_data)} tuiles traitées...")

    print()
    duration = (datetime.now() - t_start).total_seconds()
    print(f"✅ {len(tiles_data)} tuile(s) analysée(s) en {duration:.1f} s")
    if n_no_layer:
        print(f"⚠️  {n_no_layer} tuile(s) sans _layer lisible (coverage_px = null)")
    print()

    # Écrire JSON (compact : un enregistrement par bloc)
    output_json = {
        "version": SCAN_FORMAT_VERSION,
        "generated_at": datetime.now().isoformat(),
        "project": str(tiles_dir),
        "grid_w": grid_w,
        "num_blk": num_blk,
        "block_budget": block_budget,
        "tile_prefix": tile_prefix,
        "block_px": block_px,
        "source": source_signature(tiles_dir, editor_dir, tile_prefix),
        "tiles": tiles_data
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_json, f, ensure_ascii=False, separators=(",", ":"))

        print(f"📝 JSON exporté: {output_path}")
        print(f"   {len(tiles_data)} tuiles, {sum(t['n_active_mats'] for t in tiles_data)} matériaux distincts (total)")
        print()
        print("=" * 80)

        return 0
    except Exception as e:
        print(f"❌ Erreur écriture JSON: {e}")
        return 1
