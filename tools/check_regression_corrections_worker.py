#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_regression_corrections_worker.py — Worker de génération des tests Corrections

Appelé en sous-processus par check_regression.py.
Génère les résultats des méthodes Inspection et Corrections via la vraie API de main.py.
"""

import sys
import json
import shutil
import argparse
from pathlib import Path


def main():
    # Reconfiguration encodage AVANT tout affichage (fix UnicodeEncodeError avec redirection stdout)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Worker de génération des tests Corrections")
    parser.add_argument("--project-path", required=True, help="Chemin du dossier du projet")
    parser.add_argument("--out-dir", required=True, help="Dossier de sortie temporaire")
    args = parser.parse_args()

    project_path = Path(args.project_path)
    out_dir = Path(args.out_dir)

    try:
        # Ajouter app/ à sys.path pour importer main
        app_dir = Path(__file__).resolve().parent.parent / "app"
        if str(app_dir) not in sys.path:
            sys.path.insert(0, str(app_dir))

        # Importer Api depuis main (la fenêtre n'est créée que sous if __name__ == "__main__")
        from main import Api

        # Créer l'instance API
        api = Api()

        # Charger le projet
        load_result = api.load_project(str(project_path))
        if not load_result.get("ok"):
            error_msg = f"Erreur load_project : {load_result.get('error', 'inconnue')}"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "result.json").write_text(
                json.dumps({"ok": False, "error": error_msg}, indent=2),
                encoding="utf-8"
            )
            return 1

        # Créer dossier de sortie
        out_dir.mkdir(parents=True, exist_ok=True)

        # Lire les tuiles de référence sélectionnées
        tiles_json = project_path / "test" / "corrections" / "tiles.json"
        if not tiles_json.exists():
            error_msg = f"tiles.json introuvable : {tiles_json}"
            (out_dir / "result.json").write_text(
                json.dumps({"ok": False, "error": error_msg}, indent=2),
                encoding="utf-8"
            )
            return 1

        tiles_data = json.loads(tiles_json.read_text(encoding="utf-8"))
        selected = tiles_data["selected"]

        # Liste des tuiles à tester (sans odd_gctd si absent)
        test_tiles = []
        for key in ["ordinary", "high_count", "edge"]:
            if key in selected:
                test_tiles.append((key, selected[key]["tx"], selected[key]["ty"]))
        if "odd_gctd" in selected:
            test_tiles.append(("odd_gctd", selected["odd_gctd"]["tx"], selected["odd_gctd"]["ty"]))

        # === INSPECTION : scan_tiles (bouton Global Scan, réécrit outputs/cache/qtre_scan.json) ===
        result = api.scan_tiles()
        (out_dir / "inspection_scan_tiles.json").write_text(
            json.dumps({k: result.get(k) for k in ("ok", "n_tiles", "error")}, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # === DIAGNOSTIC (11d) : inspect unique (3 modes, images en base64) ===
        diag_inspect = {}
        for key, tx, ty in test_tiles:
            diag_inspect[key] = {mode: {"tx": tx, "ty": ty, **api.diagnostic_inspect_tile(tx, ty, mode)}
                                 for mode in ["inspect", "weights", "validate"]}
        grid_w = api._get_tile_grid().get("grid_w", 0)
        diag_inspect["hors_grille"] = api.diagnostic_inspect_tile(grid_w, 0, "inspect")
        (out_dir / "diagnostic_inspect_tile.json").write_text(
            json.dumps(diag_inspect, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # === DIAGNOSTIC (11d) : carte globale (seuil 1 %), textures, recherche des 2 plus frequentes, CSV ===
        (out_dir / "diagnostic_map.json").write_text(
            json.dumps(api.diagnostic_map(0.01), ensure_ascii=False),
            encoding="utf-8"
        )
        mats = api.diagnostic_materials()
        top2 = [m["id"] for m in sorted(mats.get("materials", []), key=lambda m: (-m["n_blocks"], m["id"]))[:2]]
        search = api.diagnostic_search_blocks(top2)
        csv_res = api.diagnostic_export_csv(0.01, top2)
        if csv_res.get("ok"):
            csv_res["csv"] = Path(csv_res.pop("path")).read_text(encoding="utf-8-sig")
        (out_dir / "diagnostic_search.json").write_text(
            json.dumps({"materials": mats, "search_ids": top2, "search": search, "export_csv": csv_res},
                       indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # === DIAGNOSTIC : diagnostic_scan_zone (JSON garde son nom de l'etape 4a) ===
        zone_mask = project_path / "test" / "corrections" / "zone_mask.png"
        if zone_mask.exists():
            result = api.diagnostic_scan_zone(str(zone_mask))
            (out_dir / "corrections_scan_zone.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        else:
            (out_dir / "corrections_scan_zone.json").write_text(
                json.dumps({"ok": False, "error": "zone_mask.png absent"}, indent=2),
                encoding="utf-8"
            )

        # === DIAGNOSTIC : diagnostic_terrain_health ===
        result = api.diagnostic_terrain_health()
        (out_dir / "corrections_terrain_health.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # === DIAGNOSTIC : diagnostic_file_inventory ===
        result = api.diagnostic_file_inventory()
        (out_dir / "corrections_file_inventory.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # Copier UNIQUEMENT les images générées pour les tuiles de référence
        # Les noms attendus sont basés sur les coordonnées tx,ty des tuiles testées
        tiles_dir = project_path / "outputs" / "generated" / "tiles"
        if tiles_dir.exists():
            # Construire liste des noms de fichiers attendus
            expected_files = set()
            for key, tx, ty in test_tiles:
                # Noms possibles générés par les méthodes Corrections
                # diagnostic_inspect_tile : tile_{tx}_{ty}_cleanup.png (inspect), tile_{tx}_{ty}_weights.png (weights)
                # Patterns de base : tile_<tx>_<ty>*.png
                prefix = f"tile_{tx}_{ty}"
                for png in tiles_dir.glob(f"{prefix}*.png"):
                    expected_files.add(png.name)

            # Copier uniquement les fichiers attendus
            for filename in expected_files:
                src = tiles_dir / filename
                if src.exists():
                    shutil.copy2(src, out_dir / filename)

        # Écrire result.json
        result = {
            "ok": True,
            "error": None
        }
        (out_dir / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        return 0

    except Exception as e:
        # En cas d'erreur non catchée
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(
            json.dumps({"ok": False, "error": str(e)}, indent=2),
            encoding="utf-8"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
