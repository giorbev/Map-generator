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

Import (import_project) : l'archive est vérifiée (format, version, chemins des membres), extraite
dans un dossier temporaire du dossier des projets puis renommée. En cas de remplacement, l'ancien
dossier est d'abord renommé à côté (.<nom>.old), puis supprimé une fois l'import réussi ; si
l'import échoue, il est remis en place.
"""

import json
import os
import shutil
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


def _member_parts(name: str):
    """Découpe un nom de membre ; None si le chemin sort du dossier (absolu, lecteur, ..)."""
    norm = name.replace("\\", "/")
    if norm.startswith("/") or ":" in norm:
        return None
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return parts


def read_manifest(archive_path) -> dict:
    """Lit et vérifie le manifeste d'une archive (aperçu avant import, rien n'est écrit).

    Retourne {"ok", "manifest", "n_files", "size", "has_textures"} ou {"ok": False, "error"}.
    """
    src = Path(archive_path)
    if not src.is_file():
        return {"ok": False, "error": f"Fichier introuvable : {src}"}
    try:
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
            if MANIFEST_NAME not in names:
                return {"ok": False, "error": "Ce fichier n'est pas une sauvegarde Map Generator Pro (manifest.json absent)"}
            manifest = json.loads(z.read(MANIFEST_NAME).decode("utf-8"))
            infos = [i for i in z.infolist() if not i.is_dir() and i.filename != MANIFEST_NAME]
    except zipfile.BadZipFile:
        return {"ok": False, "error": "Ce fichier n'est pas une archive zip valide"}
    except (ValueError, UnicodeDecodeError) as e:
        return {"ok": False, "error": f"manifest.json illisible : {e}"}
    if not isinstance(manifest, dict) or manifest.get("format") != MANIFEST_FORMAT:
        return {"ok": False, "error": "Ce fichier n'est pas une sauvegarde Map Generator Pro (format inconnu)"}
    version = manifest.get("format_version")
    if not isinstance(version, int) or version > MANIFEST_VERSION:
        return {"ok": False, "error": f"Sauvegarde au format {version}, non lisible par cette version de "
                                      f"l'application (format {MANIFEST_VERSION} maximum) : mettre l'application à jour"}
    bad = [i.filename for i in infos if _member_parts(i.filename) is None]
    if bad:
        return {"ok": False, "error": f"Archive refusée : chemin interdit dans l'archive ({bad[0]})"}
    if "project.json" not in names:
        return {"ok": False, "error": "Archive incomplète : project.json absent"}
    return {
        "ok": True,
        "manifest": manifest,
        "n_files": len(infos),
        "size": sum(i.file_size for i in infos),
        "has_textures": any(i.filename.startswith(PROJECT_TEXTURES_SUBDIR + "/") for i in infos),
    }


def _safe_folder_name(name: str) -> str:
    """Nom de dossier d'un projet (même règle que la création : espaces → _), sans séparateur."""
    slug = name.strip().replace(" ", "_")
    return "".join("_" if c in '<>:"/\\|?*' else c for c in slug).strip(".")


def _free_name(projects_dir: Path, base: str) -> str:
    """Premier nom libre : <base>_2, <base>_3…"""
    n = 2
    while (projects_dir / f"{base}_{n}").exists():
        n += 1
    return f"{base}_{n}"


def import_project(archive_path, projects_dir, new_name=None, replace: bool = False) -> dict:
    """Crée un projet à partir d'une archive .mgp.zip.

    new_name : nom du projet (et du dossier) à la place de celui de l'archive.
    replace : remplace un projet existant du même dossier (sinon conflit renvoyé).
    Retourne {"ok", "path", "n_files", "missing_external", "has_textures", "app_version",
              "renamed", "project_name", "replaced"}, ou {"ok": False, "conflict": True,
              "suggested_name", "folder"} si le dossier existe, ou {"ok": False, "error"}.
    """
    info = read_manifest(archive_path)
    if not info["ok"]:
        return info
    manifest = info["manifest"]
    projects = Path(projects_dir)
    orig_name = manifest.get("project_name") or manifest.get("project_folder") or "projet"
    folder = _safe_folder_name(new_name) if new_name else _safe_folder_name(
        manifest.get("project_folder") or orig_name)
    if not folder:
        return {"ok": False, "error": "Nom de projet invalide"}
    target = projects / folder
    if target.exists() and not replace:
        return {"ok": False, "conflict": True, "folder": folder, "suggested_name": _free_name(projects, folder)}

    projects.mkdir(parents=True, exist_ok=True)
    tmp = projects / f".{folder}.import.tmp"
    old = projects / f".{folder}.old"
    for leftover in (tmp, old):
        if leftover.exists():
            shutil.rmtree(leftover)
    try:
        with zipfile.ZipFile(archive_path) as z:
            n_files = 0
            for i in z.infolist():
                if i.is_dir() or i.filename == MANIFEST_NAME:
                    continue
                dest = tmp.joinpath(*_member_parts(i.filename))
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(i) as fin, open(dest, "wb") as fout:
                    shutil.copyfileobj(fin, fout, 1 << 20)
                n_files += 1
        pj = tmp / "project.json"
        data = json.loads(pj.read_text(encoding="utf-8"))
        renamed = bool(new_name) and new_name.strip() != orig_name
        if renamed:
            data.setdefault("project", {})["name"] = new_name.strip()
            pj.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return {"ok": False, "error": f"Extraction impossible : {type(e).__name__}: {e}"}

    replaced = target.exists()
    try:
        if replaced:
            os.replace(target, old)
        os.replace(tmp, target)
    except Exception as e:
        if replaced and old.exists() and not target.exists():
            os.replace(old, target)
        shutil.rmtree(tmp, ignore_errors=True)
        return {"ok": False, "error": f"Impossible d'installer le projet : {type(e).__name__}: {e}"}
    old_left = ""
    if replaced:
        shutil.rmtree(old, ignore_errors=True)
        old_left = str(old) if old.exists() else ""

    paths = data.get("paths", {})
    missing_external = [{"key": k, "path": paths[k]} for k in EXTERNAL_KEYS
                        if paths.get(k) and not Path(paths[k]).exists()]
    return {
        "ok": True,
        "path": str(target),
        "project_name": data.get("project", {}).get("name", folder),
        "n_files": n_files,
        "missing_external": missing_external,
        "has_textures": (target / PROJECT_TEXTURES_SUBDIR).is_dir(),
        "app_version": manifest.get("app_version", ""),
        "renamed": renamed,
        "replaced": replaced,
        "old_left": old_left,
    }


def default_archive_name(project_name: str) -> str:
    """Nom proposé : <projet>_AAAA-MM-JJ.mgp.zip"""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name.strip()) or "projet"
    return f"{safe}_{datetime.now().strftime('%Y-%m-%d')}{ARCHIVE_SUFFIX}"
