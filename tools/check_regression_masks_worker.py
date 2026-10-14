#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_regression_masks_worker.py — Worker de génération des masques

Appelé en sous-processus par check_regression.py.
Génère les masques via la vraie API de main.py (comme le ferait le bouton de l'app).
"""

import sys
import json
import argparse
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Worker de génération des masques")
    parser.add_argument("--project-path", required=True, help="Chemin du dossier du projet")
    parser.add_argument("--out-dir", required=True, help="Dossier de sortie temporaire")
    args = parser.parse_args()

    project_path = Path(args.project_path)
    out_dir = Path(args.out_dir)

    try:
        # Ajouter la racine du projet à sys.path pour importer main
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

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
                json.dumps({"ok": False, "error": error_msg, "masks": []}, indent=2),
                encoding="utf-8"
            )
            return 1

        # Obtenir les données de génération
        gen_data = api.get_generation_data()
        if not gen_data.get("ok"):
            error_msg = f"Erreur get_generation_data : {gen_data.get('error', 'inconnue')}"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "result.json").write_text(
                json.dumps({"ok": False, "error": error_msg, "masks": []}, indent=2),
                encoding="utf-8"
            )
            return 1

        # Extraire les paramètres comme le fait generation.html
        params = gen_data.get("params", {})
        mask_config = gen_data.get("mask_config", [])
        default_mat = gen_data.get("default_mat", "default")

        # Lancer run_pipeline_preview avec EXACTEMENT les mêmes arguments que generation.html
        preview_result = api.run_pipeline_preview(params, mask_config, default_mat)

        if not preview_result.get("ok"):
            error_msg = f"Erreur run_pipeline_preview : {preview_result.get('error', 'inconnue')}"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "result.json").write_text(
                json.dumps({"ok": False, "error": error_msg, "masks": []}, indent=2),
                encoding="utf-8"
            )
            return 1

        # Les masques PNG sont dans data/projects/<projet>/outputs/generated/pipeline_preview/
        masks_source = project_path / "outputs" / "generated" / "pipeline_preview"
        if not masks_source.exists():
            error_msg = f"Dossier masques introuvable : {masks_source}"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "result.json").write_text(
                json.dumps({"ok": False, "error": error_msg, "masks": []}, indent=2),
                encoding="utf-8"
            )
            return 1

        # Copier tous les .png vers out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        copied_masks = []
        for png_file in sorted(masks_source.glob("*.png")):
            dest = out_dir / png_file.name
            shutil.copy2(png_file, dest)
            copied_masks.append(png_file.name)

        # Écrire result.json
        result = {
            "ok": True,
            "error": None,
            "masks": copied_masks
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
            json.dumps({"ok": False, "error": str(e), "masks": []}, indent=2),
            encoding="utf-8"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
