"""
compare_texture_blocks.py — Comparaison de deux lectures bloc par bloc

Compare deux CSV générés par read_texture_blocks.py (version main vs version test)
et génère un rapport des différences bloc par bloc.

Usage:
    python compare_texture_blocks.py --main main.csv --test test.csv --output diff.csv
    python compare_texture_blocks.py --main main.csv --test test.csv --output diff.csv --min-change 5.0
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional


def load_csv(path: Path) -> Dict[tuple, Dict]:
    """Charge un CSV et indexe par (bx_global, by_global)."""
    rows = {}
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (int(row["bx_global"]), int(row["by_global"]))
            rows[key] = row
    return rows


def get_textures(row: Dict) -> Dict[str, float]:
    """Extrait le dict {texture: pct} depuis une ligne CSV."""
    textures = {}
    i = 1
    while f"tex_{i}" in row and row[f"tex_{i}"]:
        name = row[f"tex_{i}"]
        try:
            pct = float(row.get(f"pct_{i}", 0))
        except (ValueError, TypeError):
            pct = 0.0
        if name and pct > 0:
            textures[name] = pct
        i += 1
    return textures


def compare(
    main_rows: Dict[tuple, Dict],
    test_rows: Dict[tuple, Dict],
    min_change: float = 1.0
) -> List[Dict]:
    """
    Compare les deux versions bloc par bloc.

    Args:
        min_change: % minimum de changement pour signaler une différence

    Returns:
        Liste de diffs
    """
    diffs = []

    all_keys = set(main_rows.keys()) | set(test_rows.keys())

    for key in sorted(all_keys):
        bx, by = key
        main_row = main_rows.get(key)
        test_row = test_rows.get(key)

        if main_row is None:
            # Bloc absent dans main, présent dans test
            diffs.append({
                "bx_global": bx, "by_global": by,
                "tx": test_row.get("tx", ""),
                "ty": test_row.get("ty", ""),
                "tile_id": test_row.get("tile_id", ""),
                "status": "NOUVEAU",
                "dominant_main": "",
                "dominant_test": test_row.get("dominant_texture", ""),
                "changes": "bloc absent dans main",
            })
            continue

        if test_row is None:
            # Bloc absent dans test
            diffs.append({
                "bx_global": bx, "by_global": by,
                "tx": main_row.get("tx", ""),
                "ty": main_row.get("ty", ""),
                "tile_id": main_row.get("tile_id", ""),
                "status": "SUPPRIMÉ",
                "dominant_main": main_row.get("dominant_texture", ""),
                "dominant_test": "",
                "changes": "bloc absent dans test",
            })
            continue

        main_tex = get_textures(main_row)
        test_tex = get_textures(test_row)

        all_textures = set(main_tex.keys()) | set(test_tex.keys())
        changes = []

        for tex in sorted(all_textures):
            pct_main = main_tex.get(tex, 0.0)
            pct_test = test_tex.get(tex, 0.0)
            delta = pct_test - pct_main

            if abs(delta) >= min_change:
                sign = "+" if delta > 0 else ""
                changes.append(f"{tex}: {pct_main:.1f}% → {pct_test:.1f}% ({sign}{delta:.1f}%)")

        if not changes:
            continue  # Bloc identique — skip

        dom_main = main_row.get("dominant_texture", "")
        dom_test = test_row.get("dominant_texture", "")
        status = "MODIFIÉ" if dom_main == dom_test else "DOM_CHANGÉ"

        diffs.append({
            "bx_global": bx,
            "by_global": by,
            "tx": main_row.get("tx", ""),
            "ty": main_row.get("ty", ""),
            "tile_id": main_row.get("tile_id", ""),
            "status": status,
            "dominant_main": dom_main,
            "dominant_test": dom_test,
            "changes": " | ".join(changes),
        })

    return diffs


def write_diff_csv(diffs: List[Dict], output_path: Path):
    """Écrit le CSV de diff."""
    fieldnames = [
        "bx_global", "by_global", "tx", "ty", "tile_id",
        "status", "dominant_main", "dominant_test", "changes"
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(diffs)
    print(f"[OK] Diff CSV écrit : {output_path} ({len(diffs)} blocs différents)")


def main():
    parser = argparse.ArgumentParser(
        description="Comparaison de deux lectures bloc par bloc (main vs test)"
    )
    parser.add_argument("--main", type=str, required=True,
                        help="CSV version main (référence)")
    parser.add_argument("--test", type=str, required=True,
                        help="CSV version test (à comparer)")
    parser.add_argument("--output", type=str, required=True,
                        help="CSV de sortie avec les différences")
    parser.add_argument("--min-change", type=float, default=1.0,
                        help="% minimum de changement pour signaler (défaut: 1.0)")

    args = parser.parse_args()

    main_path = Path(args.main)
    test_path = Path(args.test)
    out_path  = Path(args.output)

    if not main_path.exists():
        print(f"[ERREUR] Fichier main introuvable : {main_path}")
        sys.exit(1)
    if not test_path.exists():
        print(f"[ERREUR] Fichier test introuvable : {test_path}")
        sys.exit(1)

    print(f"[INFO] Chargement main : {main_path}")
    main_rows = load_csv(main_path)
    print(f"  {len(main_rows)} blocs")

    print(f"[INFO] Chargement test : {test_path}")
    test_rows = load_csv(test_path)
    print(f"  {len(test_rows)} blocs")

    print(f"[INFO] Comparaison (seuil: {args.min_change}%)...")
    diffs = compare(main_rows, test_rows, min_change=args.min_change)

    write_diff_csv(diffs, out_path)

    # Résumé
    from collections import Counter
    status_count = Counter(d["status"] for d in diffs)
    print()
    print("=== RÉSUMÉ ===")
    print(f"  Total blocs différents : {len(diffs)}")
    for status, count in status_count.most_common():
        print(f"  {status:15s} : {count} blocs")

    # Top tuiles affectées
    from collections import defaultdict
    tile_diffs = defaultdict(int)
    for d in diffs:
        tile_diffs[(d["tx"], d["ty"])] += 1
    print()
    print("Top 10 tuiles avec le plus de changements :")
    for (tx, ty), count in sorted(tile_diffs.items(), key=lambda x: -x[1])[:10]:
        tile_id = int(ty) * 32 + int(tx) if tx and ty else "?"
        print(f"  Tuile ({tx},{ty}) T{tile_id} : {count} blocs modifiés")


if __name__ == "__main__":
    main()
