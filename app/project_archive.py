# -*- coding: utf-8 -*-
"""
project_archive.py — Sauvegarde d'un projet dans un fichier .mgp.zip (export)

Contenu de l'archive (seulement ce que l'application utilise) :
  manifest.json                 version de l'app, date, chemins d'origine, liste des fichiers
  project.json, project_mask_config.json, surfaces.json
  inputs/                       fichiers d'entrée pointés dans project.json (heightmap, masques)
  textures/                     textures du projet (catalog.json, emat/, texture_Middle/)
  outputs/                      seulement si include_outputs : cache, generated, masks, reports

Un fichier d'entrée pointé hors du dossier du projet (chemin absolu) est rangé dans inputs/
de l'archive et son chemin est réécrit dans le project.json de l'archive.
Les chemins vers l'addon Workbench et le Data Dir restent ceux d'origine (notés dans le
manifeste) : ils sont à repointer à l'import si le PC n'est pas le même.
"""

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

from catalog_config import PROJECT_TEXTURES_SUBDIR

ARCHIVE_SUFFIX = ".mgp.zip"
MANIFEST_NAME = "manifest.json"
MANIFEST_FORMAT = "mgp-project"
MANIFEST_VERSION = 1

# Fichiers de réglages à la racine du projet
ROOT_FILES = ("project.json", "project_mask_config.json", "surfaces.json")
# Clés de project.json["paths"] qui désignent des fichiers d'entrée à emporter
INPUT_KEYS = ("heightmap", "satmap", "exclusion_mask", "gaea_flow", "gaea_deposit")
# Clés de project.json["paths"] qui désignent des dossiers de la machine (à repointer à l'import)
EXTERNAL_KEYS = ("addon_reforger", "data_dir")
# Dossier où ranger les entrées pointées hors du projet
INPUTS_DIR = "inputs"
# Sous-dossiers de outputs/ emportés quand les résultats sont inclus (logs et inspection exclus)
OUTPUT_DIRS = ("outputs/cache", "outputs/generated", "outputs/masks", "outputs/reports")
# Extensions déjà compressées : rangées sans recompression (plus rapide, même taille)
STORED_EXTS = {".png", ".jpg", ".jpeg", ".npz", ".zip", ".edds", ".dds", ".tif", ".tiff"}


def _iter_files(path: Path):
    """Fichiers d'un dossier (récursif, triés) ou le fichier lui-même."""
    if path.is_file():
        yield path
    elif path.is_dir():
        for p in sorted(path.rglob("*")):
            if p.is_file():
                yield p


def _arc(path: Path) -> str:
    return path.as_posix()


def collect_project_files(project_dir, include_outputs: bool = False) -> dict:
    """Liste ce qui part dans l'archive, sans rien écrire.

    Retourne {"files": [(source, nom_dans_archive)], "paths": paths réécrits,
              "rewritten": {clé: (ancien, nouveau)}, "missing": [(clé, chemin)],
              "external": {clé: chemin}, "project": données de project.json}.
    """
    proj = Path(project_dir)
    data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    paths = dict(data.get("paths", {}))
    files, rewritten, missing, seen = [], {}, [], set()

    def add(src: Path, arc: str):
        if arc not in seen:
            seen.add(arc)
            files.append((src, arc))

    for name in ROOT_FILES:
        if (proj / name).is_file():
            add(proj / name, name)

    for key in INPUT_KEYS:
        rel = paths.get(key) or ""
        if not rel:
            continue
        p = Path(rel)
        full = p if p.is_absolute() else proj / p
        if not full.exists():
            missing.append((key, rel))
            continue
        try:
            inside = full.resolve().relative_to(proj.resolve())
        except ValueError:
            inside = None
        if inside is not None:
            for f in _iter_files(full):
                add(f, _arc(f.resolve().relative_to(proj.resolve())))
        else:
            # Entrée hors du projet : rangée dans inputs/ de l'archive, chemin réécrit
            new_rel = f"{INPUTS_DIR}/{full.name}" + ("/" if full.is_dir() else "")
            for f in _iter_files(full):
                add(f, _arc(Path(INPUTS_DIR) / full.name / f.relative_to(full)) if full.is_dir()
                    else f"{INPUTS_DIR}/{full.name}")
            rewritten[key] = (rel, new_rel)
            paths[key] = new_rel

    for f in _iter_files(proj / PROJECT_TEXTURES_SUBDIR):
        add(f, _arc(f.relative_to(proj)))

    if include_outputs:
        for sub in OUTPUT_DIRS:
            for f in _iter_files(proj / sub):
                add(f, _arc(f.relative_to(proj)))

    external = {k: paths.get(k, "") for k in EXTERNAL_KEYS if paths.get(k)}
    return {"files": files, "paths": paths, "rewritten": rewritten, "missing": missing,
            "external": external, "project": data}


def export_project(project_dir, dest_path, include_outputs: bool = False, app_version: str = "") -> dict:
    """Écrit l'archive .mgp.zip du projet (fichier temporaire puis renommage).

    Retourne {"ok", "path", "n_files", "size", "missing", "rewritten", "has_textures"}.
    """
    proj = Path(project_dir)
    dest = Path(dest_path)
    if not (proj / "project.json").is_file():
        return {"ok": False, "error": f"project.json introuvable dans {proj}"}
    try:
        dest.resolve().relative_to(proj.resolve())
        return {"ok": False, "error": "L'archive ne peut pas être enregistrée dans le dossier du projet"}
    except ValueError:
        pass

    col = collect_project_files(proj, include_outputs)
    data = col["project"]
    manifest = {
        "format": MANIFEST_FORMAT,
        "format_version": MANIFEST_VERSION,
        "app_version": app_version,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "project_name": data.get("project", {}).get("name", proj.name),
        "project_folder": proj.name,
        "include_outputs": bool(include_outputs),
        "external_paths": col["external"],
        "rewritten_paths": {k: {"from": a, "to": b} for k, (a, b) in col["rewritten"].items()},
        "missing_inputs": [{"key": k, "path": p} for k, p in col["missing"]],
        "files": [{"path": arc, "size": src.stat().st_size} for src, arc in col["files"]],
    }

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp, "w", allowZip64=True) as z:
            z.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
            for src, arc in col["files"]:
                if arc == "project.json" and col["rewritten"]:
                    out = dict(data)
                    out["paths"] = col["paths"]
                    z.writestr(arc, json.dumps(out, indent=2, ensure_ascii=False), zipfile.ZIP_DEFLATED)
                    continue
                comp = zipfile.ZIP_STORED if src.suffix.lower() in STORED_EXTS else zipfile.ZIP_DEFLATED
                z.write(src, arc, compress_type=comp)
        os.replace(tmp, dest)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    return {
        "ok": True,
        "path": str(dest),
        "n_files": len(col["files"]),
        "size": dest.stat().st_size,
        "missing": manifest["missing_inputs"],
        "rewritten": manifest["rewritten_paths"],
        "has_textures": (proj / PROJECT_TEXTURES_SUBDIR).is_dir(),
    }


def default_archive_name(project_name: str) -> str:
    """Nom proposé : <projet>_AAAA-MM-JJ.mgp.zip"""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name.strip()) or "projet"
    return f"{safe}_{datetime.now().strftime('%Y-%m-%d')}{ARCHIVE_SUFFIX}"
