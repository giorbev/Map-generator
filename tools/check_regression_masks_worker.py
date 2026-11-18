#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_regression_masks_worker.py — Worker de génération des masques

Appelé en sous-processus par check_regression.py.
Génère les masques du biome tempéré via la vraie API de main.py (comme les boutons de l'onglet Generation).
"""

import sys
import json
import argparse
import shutil
from pathlib import Path


def main():
    # Reconfiguration encodage AVANT tout affichage (fix UnicodeEncodeError avec redirection stdout)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Worker de génération des masques")
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

        # Biome tempéré (moteur de génération depuis le retrait du classique, 18/11/2026), textures proposées,
        # export comme le bouton « Exporter les masques » de l'onglet Baking
        classes = api.biome_climat_classes("tempere")
        if not classes.get("ok"):
            raise RuntimeError(f"biome_climat_classes : {classes.get('error', 'inconnue')}")
        association = {l["classe"]: l["texture"] for l in classes["lignes"]}
        export = api.biome_climat_exporter("tempere", association)
        if not export.get("ok"):
            raise RuntimeError(f"biome_climat_exporter : {export.get('error', 'inconnue')}")
        masks_source = Path(export["dossier"])

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
