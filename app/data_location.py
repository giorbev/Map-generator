# -*- coding: utf-8 -*-
"""
data_location.py — Emplacement du dossier des données de l'exe (projets, textures, réglages, logs)

Le chemin retenu est noté dans %APPDATA%\\MapGeneratorPro\\location.json, hors du dossier des données
(sinon settings.json serait introuvable). Dans cet ordre :
  1. variable d'environnement MGP_DATA_DIR (tests : dossier utilisateur temporaire) ;
  2. location.json, si le dossier qu'il désigne existe (écrit par l'installeur à la première
     installation, page « Dossier des données », UTF-8 avec BOM, ou par l'application) ;
  3. ancien emplacement des V8 (<profil>\\Documents\\MapGeneratorPro), s'il existe : une installation
     existante garde ses données ;
  4. MapGeneratorPro dans le vrai dossier Documents de Windows (SHGetKnownFolderPath : suit un
     Documents déplacé vers OneDrive ou un autre disque).
Le mode dev n'utilise pas ce module (données dans le dépôt).

Changer l'emplacement (copy_data_dir) copie les données dans le nouveau dossier (dossier .tmp puis
renommage) ; l'ancien dossier n'est pas supprimé. L'application doit être relancée ensuite.
"""

import json
import os
import shutil
from pathlib import Path

APP_FOLDER = "MapGeneratorPro"
LOCATION_NAME = "location.json"
ENV_OVERRIDE = "MGP_DATA_DIR"
# FOLDERID_Documents
_DOCUMENTS_GUID = "FDD39AD0-238F-46AF-ADB4-6C85480369C7"


def documents_dir() -> Path:
    """Vrai dossier Documents de Windows (repli : <profil>\\Documents)."""
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        guid = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID(_DOCUMENTS_GUID).bytes_le)
        out = ctypes.c_wchar_p()
        fn = ctypes.windll.shell32.SHGetKnownFolderPath
        fn.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
        if fn(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0 and out.value:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception:
        pass
    return Path.home() / "Documents"


def location_file() -> Path:
    base = os.environ.get("APPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Roaming") / APP_FOLDER / LOCATION_NAME


def default_data_dir() -> Path:
    return documents_dir() / APP_FOLDER


def read_location():
    """Dossier noté dans location.json, ou None."""
    try:
        p = Path(json.loads(location_file().read_text(encoding="utf-8-sig"))["data_dir"])
        return p if p.is_dir() else None
    except Exception:
        return None


def save_location(data_dir) -> None:
    f = location_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"data_dir": str(data_dir)}, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_data_dir() -> Path:
    """Dossier des données de l'exe (voir l'ordre en tête du module) ; noté dans location.json."""
    env = os.environ.get(ENV_OVERRIDE)
    if env:
        return Path(env)
    known = read_location()
    if known:
        return known
    legacy = Path.home() / "Documents" / APP_FOLDER
    chosen = legacy if legacy.is_dir() else default_data_dir()
    try:
        chosen.mkdir(parents=True, exist_ok=True)
        save_location(chosen)
    except Exception:
        pass
    return chosen


def target_for(folder) -> Path:
    """Dossier des données dans le dossier choisi : <choix>\\MapGeneratorPro (sauf s'il porte déjà ce nom)."""
    p = Path(folder)
    return p if p.name.lower() == APP_FOLDER.lower() else p / APP_FOLDER


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def copy_data_dir(current, folder) -> dict:
    """Prépare le dossier des données dans <folder> (copie de <current>) sans rien supprimer.

    Retourne {"ok", "path", "copied", "size"} ; si le dossier choisi contient déjà des données
    Map Generator Pro, elles sont reprises telles quelles (copied False).
    Le dossier n'est pas encore utilisé : appeler save_location puis relancer l'application.
    """
    src = Path(current).resolve()
    dst = target_for(folder).resolve()
    if dst == src:
        return {"ok": False, "error": "C'est déjà le dossier des données"}
    for a, b in ((dst, src), (src, dst)):
        try:
            a.relative_to(b)
            return {"ok": False, "error": "Le nouveau dossier ne peut pas être dans l'ancien (ni l'inverse)"}
        except ValueError:
            pass
    if (dst / "data" / "projects").is_dir():
        return {"ok": True, "path": str(dst), "copied": False, "size": 0}
    if dst.exists() and any(dst.iterdir()):
        return {"ok": False, "error": f"Le dossier {dst} existe et n'est pas vide"}

    size = _dir_size(src)
    free = shutil.disk_usage(dst.parent if dst.parent.exists() else dst.anchor).free
    if size > free:
        return {"ok": False, "error": f"Place insuffisante : {size / 1e9:.1f} Go à copier, {free / 1e9:.1f} Go libres"}

    tmp = dst.with_name(dst.name + ".tmp")
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(src, tmp)
        # Dernier projet ouvert : chemin ramené dans le nouveau dossier
        settings = tmp / "settings.json"
        if settings.is_file():
            s = json.loads(settings.read_text(encoding="utf-8"))
            last = s.get("last_project_path")
            if last:
                try:
                    s["last_project_path"] = str(dst / Path(last).resolve().relative_to(src))
                    settings.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
                except ValueError:
                    pass
        if dst.exists():
            dst.rmdir()
        os.replace(tmp, dst)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return {"ok": False, "error": f"Copie impossible : {type(e).__name__}: {e}"}
    return {"ok": True, "path": str(dst), "copied": True, "size": size}
