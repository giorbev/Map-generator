# -*- coding: utf-8 -*-
"""
Map Generator Pro v8.0.1 — PyWebView Launcher
Remplace app.py Streamlit par une fenêtre native desktop.

Lancement : python app/main.py
"""

import webview
import sys as _sys
if hasattr(_sys.stdout, 'reconfigure'):
    try:
        _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        _sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import json
import shutil
import sys
# Fix PyInstaller + LZ4/joblib sur Windows — évite le double lancement
if getattr(sys, 'frozen', False):
    import multiprocessing
    multiprocessing.freeze_support()
import os
from pathlib import Path
from datetime import datetime

# Force le chemin pour trouver les modules locaux (compatible PyInstaller)
# (mode dev : racine du dépôt, parent de app/, où sont web/ et data/)
_RUNTIME_DIR = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
# Forcer le cwd vers le dossier de l'exe pour que les DLL soient trouvées
os.chdir(str(_RUNTIME_DIR))
sys.path.append(str(_RUNTIME_DIR))

# Import module partagé pour chemins catalog
from catalog_config import (USER_DIR as _USER_DIR, TEXTURES_USER_DIR as _TEXTURES_USER_DIR, get_catalog_path,
                            get_emat_dir, get_middles_dir, get_project_textures_dir, ensure_project_textures)
# Import module unique de résolution projet
import project_reader

# ── Constantes ────────────────────────────────────────────────────────────────
# Compatibilité PyInstaller (exe) et développement (script)
if getattr(sys, 'frozen', False):
    _APP_DIR = Path(sys._MEIPASS)
else:
    # Racine du dépôt (parent de app/)
    _APP_DIR = Path(__file__).resolve().parent.parent

_SETTINGS_FILE = _USER_DIR / "settings.json"
_VANILLA_BASE_SRC = _APP_DIR / "data" / "Textures_ArmaReforger" / "vanilla_base"

def _save_settings(key: str, value) -> None:
    """Sauvegarde une valeur dans settings.json (rien n'est écrit si la valeur est inchangée)."""
    try:
        s = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")) if _SETTINGS_FILE.exists() else {}
        if key in s and s[key] == value:
            return
        s[key] = value
        _SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def _load_settings(key: str, default=None):
    """Charge une valeur depuis settings.json."""
    try:
        if _SETTINGS_FILE.exists():
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8")).get(key, default)
    except Exception:
        pass
    return default

def _init_first_launch() -> None:
    """Copie vanilla_base vers USER_DIR au premier lancement si absent."""
    import shutil
    marker = _TEXTURES_USER_DIR / ".initialized"
    if marker.exists():
        return
    if not _VANILLA_BASE_SRC.exists():
        print(f"[INIT] vanilla_base introuvable : {_VANILLA_BASE_SRC}")
        return
    print(f"[INIT] Premier lancement — copie vanilla_base vers {_TEXTURES_USER_DIR}")
    try:
        _TEXTURES_USER_DIR.mkdir(parents=True, exist_ok=True)
        # Copier emat/
        src_emat = _VANILLA_BASE_SRC / "emat"
        dst_emat = _TEXTURES_USER_DIR / "emat"
        if src_emat.exists():
            shutil.copytree(str(src_emat), str(dst_emat), dirs_exist_ok=True)
            print(f"[INIT] emat/ copié : {len(list(dst_emat.glob('*.emat')))} fichiers")
        # Copier texture_Middle/
        src_mid = _VANILLA_BASE_SRC / "texture_Middle"
        dst_mid = _TEXTURES_USER_DIR / "texture_Middle"
        if src_mid.exists():
            shutil.copytree(str(src_mid), str(dst_mid), dirs_exist_ok=True)
            print(f"[INIT] texture_Middle/ copié : {len(list(dst_mid.glob('*.*')))} fichiers")
        # Copier catalog.json et biomes_presets.json UNIQUEMENT si absents
        for fname in ("catalog.json", "biomes_presets.json"):
            src_f = _VANILLA_BASE_SRC / fname
            dst_f = _TEXTURES_USER_DIR / fname
            if src_f.exists() and not dst_f.exists():
                shutil.copy2(str(src_f), str(dst_f))
                print(f"[INIT] {fname} copié")
        # Marker
        marker.write_text("ok", encoding="utf-8")
        print("[INIT] Premier lancement terminé")
    except Exception as e:
        print(f"[INIT] Erreur copie vanilla_base : {e}")

WEB_DIR = _APP_DIR / "web"
PROJECTS_DIR = _USER_DIR / "data" / "projects"
_FIRST_LAUNCH = not PROJECTS_DIR.exists()
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
# Logs globaux
_GLOBAL_LOGS_DIR = _USER_DIR / "logs"
_GLOBAL_LOGS_DIR.mkdir(parents=True, exist_ok=True)
PROJECT_VERSION = "1.2"

# ── Session state simplifié (dict Python) ────────────────────────────────────
_session = {
    "current_project_path": None,
    "current_project": None,
    "active_tab": None,
    "session_log": [],
    "skip_restore": False,
}


# ─────────────────────────────────────────────────────────────────────────────
# API exposée au JavaScript via window.pywebview.api.*
# ─────────────────────────────────────────────────────────────────────────────
class Api:

    # ── Projets ───────────────────────────────────────────────────────────────

    def list_projects(self) -> list:
        """Retourne la liste des projets triés par date de modification."""
        projects = []
        for p in PROJECTS_DIR.iterdir():
            json_file = p / "project.json"
            if p.is_dir() and json_file.exists():
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    hm_path = data.get("paths", {}).get("heightmap", "")
                    hm_name = ""
                    if hm_path:
                        # Chercher le premier fichier dans le dossier heightmap
                        hm_dir = p / hm_path
                        if hm_dir.exists():
                            files = list(hm_dir.glob("*.asc")) + list(hm_dir.glob("*.png")) + list(hm_dir.glob("*.tif"))
                            hm_name = files[0].name if files else ""
                    projects.append({
                        "path": str(p),
                        "name": data["project"]["name"],
                        "author": data["project"].get("author", ""),
                        "description": data["project"].get("description", ""),
                        "updated_at": data.get("updated_at", ""),
                        "heightmap": hm_name,
                    })
                except Exception:
                    pass
        return sorted(projects, key=lambda x: x["updated_at"], reverse=True)

    def create_project(self, name: str, author: str = "", description: str = "") -> dict:
        """Crée un nouveau projet et le charge."""
        try:
            slug = name.strip().replace(" ", "_")
            project_dir = PROJECTS_DIR / slug
            subdirs = [
                "inputs/heightmap", "inputs/satmap", "inputs/masks", "inputs/gaea",
                "outputs/masks/latest", "outputs/satmap", "outputs/reports",
                "outputs/generated", "outputs/cache", "outputs/logs",
            ]
            for subdir in subdirs:
                (project_dir / subdir).mkdir(parents=True, exist_ok=True)

            now = datetime.now().isoformat(timespec="seconds")
            data = {
                "version": PROJECT_VERSION,
                "created_at": now,
                "updated_at": now,
                "project": {"name": name, "author": author, "description": description, "tags": []},
                "paths": {
                    "heightmap": "inputs/heightmap/",
                    "satmap": "inputs/satmap/",
                    "exclusion_mask": "inputs/masks/",
                    "gaea_flow": "inputs/gaea/",
                    "gaea_deposit": "inputs/gaea/",
                    "addon_reforger": "",
                    "satmap_v2": "outputs/generated/satmap_v2_textured_4097.png",
                    "data_dir": ""
                },
            }
            (project_dir / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._load_project_internal(str(project_dir), data)
            self._log(f"[PROJET] Créé : {name}")
            return {"ok": True, "path": str(project_dir), "name": name}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def load_project(self, project_path: str) -> dict:
        """Charge un projet existant."""
        try:
            p = Path(project_path)
            data = json.loads((p / "project.json").read_text(encoding="utf-8"))
            self._load_project_internal(str(p), data)
            self._log(f"[PROJET] Chargé : {data['project']['name']}")
            _save_settings("last_project_path", str(p))
            return {"ok": True, "name": data["project"]["name"], "path": str(p)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def delete_project(self, project_path: str) -> dict:
        """Supprime un projet définitivement."""
        try:
            p = Path(project_path)
            name = json.loads((p / "project.json").read_text(encoding="utf-8"))["project"]["name"]
            shutil.rmtree(p, ignore_errors=True)
            if _session["current_project_path"] == str(p):
                _session["current_project_path"] = None
                _session["current_project"] = None
            self._log(f"[PROJET] Supprimé : {name}")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def restore_last_project(self) -> dict:
        """Restaure le dernier projet ouvert au démarrage."""
        if _session.get("skip_restore"):
            _session["skip_restore"] = False
            return {"ok": False}
        _session["skip_restore"] = False
        last = _load_settings("last_project_path")
        if not last:
            return {"ok": False}
        p = Path(last)
        if not p.exists() or not (p / "project.json").exists():
            return {"ok": False}
        return self.load_project(str(p))

    def get_current_project(self) -> dict | None:
        """Retourne les infos du projet courant."""
        if not _session["current_project_path"]:
            return None
        p = _session["current_project"]
        return {
            "path": _session["current_project_path"],
            "name": p["project"]["name"],
            "author": p["project"].get("author", ""),
            "updated_at": p.get("updated_at", ""),
        }

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self, tab: str):
        """Change l'onglet actif — fire and forget, aucun retour JS."""
        import threading
        _session["active_tab"] = tab
        tab_map = {
            "heightmap":    "terrain.html",
            "diagnostic":   "diagnostic.html",
            "pipeline_v5":  "generation.html",
            "satmap":       "satmap.html",
            "help":         "help.html",
        }
        html_file = tab_map.get(tab, "navigation_preview.html")
        html_path = WEB_DIR / html_file
        window = webview.windows[0] if webview.windows else None
        if window and html_path.exists():
            uri = html_path.as_uri()
            t = threading.Thread(target=lambda: __import__('time').sleep(0.1) or window.load_url(uri), daemon=True)
            t.start()

    def go_navigation(self):
        """Charge la page navigation."""
        import threading
        html_path = WEB_DIR / "navigation_preview.html"
        window = webview.windows[0] if webview.windows else None
        if window and html_path.exists():
            threading.Timer(0.05, lambda: window.load_url(html_path.as_uri())).start()

    def go_projects(self):
        """Charge la page de gestion des projets (depuis accueil)."""
        _session["skip_restore"] = True
        import threading
        if _FIRST_LAUNCH:
            self._log(f"[INIT] Premier lancement — dossier projets cree : {PROJECTS_DIR}")
        html_path = WEB_DIR / "projects.html"
        window = webview.windows[0] if webview.windows else None
        if window and html_path.exists():
            threading.Timer(0.05, lambda: window.load_url(html_path.as_uri())).start()

    def go_accueil(self):
        """Retourne à la page d'accueil animée."""
        import threading
        html_path = WEB_DIR / "accueil_preview.html"
        window = webview.windows[0] if webview.windows else None
        if window and html_path.exists():
            threading.Timer(0.05, lambda: window.load_url(html_path.as_uri())).start()

    # ── Log ───────────────────────────────────────────────────────────────────

    def get_log(self) -> list:
        """Retourne les lignes du log session."""
        return _session["session_log"][-100:]

    def clear_log(self) -> dict:
        _session["session_log"] = []
        return {"ok": True}


    # ── Terrain — Heightmap & Chemins ─────────────────────────────────────────

    def get_paths(self) -> dict | None:
        """Retourne les chemins du projet courant."""
        if not _session["current_project_path"]:
            return None
        try:
            p = Path(_session["current_project_path"])
            data = json.loads((p / "project.json").read_text(encoding="utf-8"))
            return data.get("paths", {})
        except Exception:
            return None

    def pick_file(self, key: str, extensions: list) -> dict:
        """Ouvre un dialogue de sélection de fichier et copie dans inputs/."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        window = webview.windows[0] if webview.windows else None
        if not window:
            return {"ok": False, "error": "Pas de fenêtre"}
        if extensions:
            file_types = tuple(f"{e.upper()} files (*.{e})" for e in extensions)
        else:
            file_types = ("All files (*.*)",)
        try:
            from webview import FileDialog
            open_const = FileDialog.OPEN
        except (ImportError, AttributeError):
            open_const = getattr(webview, 'OPEN', None) or getattr(webview, 'OPEN_DIALOG', 0)
        files = window.create_file_dialog(open_const, allow_multiple=False, file_types=file_types)
        if not files:
            return {"ok": False, "cancelled": True}
        src = Path(files[0])
        proj = Path(_session["current_project_path"])
        dest_dir = proj / "inputs"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        import shutil as _shutil
        _shutil.copy2(src, dest)
        rel_path = f"inputs/{src.name}"
        # Sauvegarder dans project.json
        try:
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            data.setdefault("paths", {})[key] = rel_path
            data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            (proj / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            return {"ok": False, "error": str(e)}
        self._log(f"[TERRAIN] Fichier {key} : {src.name}")
        return {"ok": True, "path": rel_path, "filename": src.name}

    def pick_folder(self, key: str) -> dict:
        """Ouvre un dialogue de sélection de dossier."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        window = webview.windows[0] if webview.windows else None
        if not window:
            return {"ok": False, "error": "Pas de fenêtre"}
        folders = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not folders:
            return {"ok": False, "cancelled": True}
        folder_path = str(folders[0])
        try:
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            old_value = data.get("paths", {}).get(key)
            data.setdefault("paths", {})[key] = folder_path
            data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            (proj / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

            # Recharger matériaux si addon_reforger a changé (affecte chemin .terr)
            if key == "addon_reforger" and old_value != folder_path:
                _session["current_project"] = data  # Mettre à jour session avant reload
                self._load_materials_from_terr()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        self._log(f"[TERRAIN] Dossier {key} : {folder_path}")
        return {"ok": True, "path": folder_path}

    def remove_path(self, key: str) -> dict:
        """Supprime un chemin du project.json."""
        if not _session["current_project_path"]:
            return {"ok": False}
        try:
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            data.setdefault("paths", {})[key] = ""
            data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            (proj / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_terrain_stats(self) -> dict:
        """Retourne les stats terrain si disponibles (cache npz)."""
        if not _session["current_project_path"]:
            return {"ok": False}
        try:
            import numpy as np
            proj = Path(_session["current_project_path"])
            cache = proj / "outputs" / "cache" / "terrain_data.npz"
            if not cache.exists():
                return {"ok": False, "reason": "no_cache"}
            d = np.load(str(cache), allow_pickle=True)
            hm = d["heightmap"]
            cellsize = float(d.get("cellsize", 1.0)) if "cellsize" in d else 1.0
            # Préférer cell_size de project.json si disponible (valeur Workbench)
            proj_data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            if proj_data.get("cell_size"):
                cellsize = float(proj_data["cell_size"])
            land_mask = hm > 0
            alt_land = hm[land_mask] if land_mask.any() else hm.flatten()
            total_px = hm.size
            land_px = int(land_mask.sum())
            sea_px = total_px - land_px
            params = {}
            if "params" in d:
                p = d["params"].item() if hasattr(d["params"], "item") else {}
                params = {k: round(float(v), 1) if isinstance(v, float) else v for k, v in p.items()}
            return {
                "ok": True,
                "denivele": round(float(alt_land.max() - alt_land.min())),
                "land_pct": round(land_px / total_px * 100, 1),
                "sea_pct": round(sea_px / total_px * 100, 1),
                "cellsize": cellsize,
                "params": params,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def analyse_terrain(self) -> dict:
        """Calcule les dérivés terrain et sauvegarde le cache terrain_data.npz."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            import numpy as np
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            hm_rel = data.get("paths", {}).get("heightmap", "inputs/heightmap/")
            hm_dir = proj / hm_rel
            # Chercher le fichier .asc
            if hm_dir.is_file() and hm_dir.suffix == ".asc":
                candidates = [hm_dir]
            else:
                candidates = list(hm_dir.glob("*.asc"))
            if not candidates:
                return {"ok": False, "error": "Aucune heightmap .asc trouvée — configurez le chemin dans Terrain > Chemins"}
            hm_path = candidates[0]
            cache_dir = proj / "outputs" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / "terrain_data.npz"

            from terrain_analysis import compute_terrain_data

            def progress_cb(step, pct):
                self._log(f"[ATLAS] {step} — {int(pct*100)}%")

            self._log(f"[ATLAS] Analyse terrain : {hm_path.name}")
            terrain_data = compute_terrain_data(str(hm_path), progress_callback=progress_cb)

            # Sauvegarder en npz
            np.savez_compressed(
                str(cache_path),
                heightmap=terrain_data["heightmap"],
                slope=terrain_data["slope"],
                cellsize=terrain_data["cellsize"],
                params=terrain_data["params"],
            )
            self._log(f"[ATLAS] Cache sauvegardé : {cache_path}")
            return {"ok": True, "computation_time": round(terrain_data["computation_time"], 1)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def gen_hypsometric(self, hillshade: bool = False, enrichment: bool = False) -> dict:
        """Génère la colormap hypsométrique et retourne le chemin."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            from hypsometric_colormap import HypsometricColormapGenerator
            proj = Path(_session["current_project_path"])
            # Chercher la heightmap
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            hm_rel = data.get("paths", {}).get("heightmap", "")
            if not hm_rel:
                return {"ok": False, "error": "Heightmap non configurée"}
            hm_path = proj / hm_rel
            if not hm_path.exists() or not hm_path.is_file():
                # Chercher dans inputs/
                candidates = list((proj / "inputs").glob("*.asc")) + list((proj / "inputs").glob("*.png"))
                if not candidates:
                    return {"ok": False, "error": "Fichier heightmap introuvable"}
                hm_path = candidates[0]
            output_dir = proj / "outputs" / "generated"
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"color_map_hypsometric_{ts}.png"
            gen = HypsometricColormapGenerator(str(hm_path), output_dir=str(output_dir))
            gen.save(filename, add_hillshade=hillshade, add_enrichment=enrichment)
            out_path = str(output_dir / filename)
            self._log(f"[TERRAIN] Hypsométrique générée : {filename}")
            return {"ok": True, "path": out_path, "filename": filename}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_file_location(self, path: str) -> dict:
        """Ouvre l'explorateur Windows sur le dossier du fichier."""
        import subprocess
        try:
            p = Path(path)
            if p.is_file():
                subprocess.Popen(f'explorer /select,"{p}"')
            elif p.is_dir():
                subprocess.Popen(f'explorer "{p}"')
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def open_project_folder(self):
        """Ouvre l'explorateur Windows sur le dossier du projet courant — fire and forget."""
        import subprocess, threading
        if not _session["current_project_path"]:
            return
        path = _session["current_project_path"]
        threading.Thread(target=lambda: subprocess.Popen(f'explorer "{path}"'), daemon=True).start()

    def parse_workbench_info(self, text: str) -> dict:
        """Parse le texte copié depuis Workbench pour extraire grid_w, num_blk, cell_size, tile_size_m, surface_tile_px."""
        import re
        try:
            self._log("[GENERATION] Analyse info Workbench...")

            # Normaliser \r\n → \n
            text = text.replace('\r\n', '\n')

            # Sections connues (pour bornage)
            SECTIONS = ["Blocks and Tiles", "Height Map:", "Satellite Texture:", "Surface Map:", "Normal Map:"]

            def find_section_end(text_pos: int, current_section: str) -> int:
                """Trouve la fin d'une section = début de la prochaine section connue (hors section courante)."""
                min_pos = len(text)
                for section in SECTIONS:
                    if section == current_section:
                        continue
                    pos = text.find(section, text_pos + len(current_section))
                    if pos != -1 and pos < min_pos:
                        min_pos = pos
                return min_pos

            # === VALEURS EXISTANTES (TOUJOURS EXTRAITES) ===

            # Tiles: \n32 x 32
            m_grid = re.search(r'Tiles:\s*\n\s*(\d+)\s*x\s*(\d+)', text)
            # Blocks per tile: \n4 x 4
            m_blk  = re.search(r'Blocks per tile:\s*\n\s*(\d+)\s*x\s*(\d+)', text)
            # Planar resolution: \n4 m
            m_cell = re.search(r'Planar resolution:\s*\n\s*([0-9.]+)\s*m', text)

            if not m_grid:
                self._log("[GENERATION] ERREUR : 'Tiles:' non trouvé dans le texte")
                return {"ok": False, "error": "Tiles non trouvé — coller le texte complet depuis Workbench"}
            if not m_blk:
                self._log("[GENERATION] ERREUR : 'Blocks per tile:' non trouvé dans le texte")
                return {"ok": False, "error": "Blocks per tile non trouvé — coller le texte complet depuis Workbench"}
            if not m_cell:
                self._log("[GENERATION] ERREUR : 'Planar resolution:' non trouvé dans le texte")
                return {"ok": False, "error": "Planar resolution non trouvé — coller le texte complet depuis Workbench"}

            grid_w    = int(m_grid.group(1))
            num_blk   = int(m_blk.group(1))
            cell_size = float(m_cell.group(1))

            # === NOUVELLES VALEURS (PEUVENT ÉCHOUER) ===

            tile_size_m = None
            surface_tile_px = None
            warnings = []

            # 1. tile_size_m — Section "Height Map:", ligne "Tile: 129 x 129 vertices (512 x 512 m2)"
            height_map_pos = text.find("Height Map:")

            if height_map_pos != -1:
                # Borner section
                height_end = find_section_end(height_map_pos, "Height Map:")
                height_section = text[height_map_pos:height_end]

                # Regex ancrée sur "Tile:" uniquement
                m_tile = re.search(r'Tile:\s*\d+\s*x\s*\d+\s*vertices\s*\(\s*(\d+)\s*x\s*\d+\s*m2\)', height_section)
                if m_tile:
                    tile_size_m = int(m_tile.group(1))
                else:
                    warnings.append("Height Map > Tile: regex non trouvée")
            else:
                warnings.append("Section Height Map: introuvable")

            # 2. surface_tile_px — Section "Surface Map:", ligne "Tile resolution: 512 x 512 px"
            surface_map_pos = text.find("Surface Map:")

            if surface_map_pos != -1:
                # Borner section
                surface_end = find_section_end(surface_map_pos, "Surface Map:")
                surface_section = text[surface_map_pos:surface_end]

                # Regex "Tile resolution:" dans cette section uniquement
                m_surface = re.search(r'Tile resolution:\s*(\d+)\s*x\s*\d+\s*px', surface_section)
                if m_surface:
                    surface_tile_px = int(m_surface.group(1))
                else:
                    warnings.append("Surface Map > Tile resolution: regex non trouvée")
            else:
                warnings.append("Section Surface Map: introuvable")

            # 3. Calcul échelle si valeurs présentes
            echelle_m_per_px = None
            if tile_size_m is not None and surface_tile_px is not None:
                echelle_m_per_px = tile_size_m / surface_tile_px
            else:
                warnings.append("Échelle non calculée (valeurs manquantes)")

            # Sauvegarder dans le projet courant
            if _session["current_project_path"]:
                proj_path = Path(_session["current_project_path"])
                data = json.loads((proj_path / "project.json").read_text(encoding="utf-8"))
                data["grid_w"]    = grid_w
                data["num_blk"]   = num_blk
                data["cell_size"] = cell_size
                # Ne pas écrire None (conserver valeur existante)
                if tile_size_m is not None:
                    data["tile_size_m"] = tile_size_m
                if surface_tile_px is not None:
                    data["surface_tile_px"] = surface_tile_px
                # Enregistrer le texte brut et la date (EN PLUS)
                data["workbench_info_raw"] = text
                data["workbench_info_updated"] = datetime.now().isoformat(timespec="seconds")
                data["updated_at"] = datetime.now().isoformat(timespec="seconds")
                (proj_path / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                # Mettre à jour la session
                _session["current_project"] = data

            # Log
            log_msg = f"[GENERATION] Grille OK : {grid_w}×{grid_w} tiles | {num_blk} blk/tile | {cell_size} m/cell"
            if echelle_m_per_px is not None:
                log_msg += f" | échelle {echelle_m_per_px:.3f} m/px"
            self._log(log_msg)

            if warnings:
                for w in warnings:
                    self._log(f"[GENERATION] WARNING : {w}")

            # Retourner TOUJOURS ok: True avec grid_w/num_blk/cell_size
            return {
                "ok": True,
                "grid_w": grid_w,
                "num_blk": num_blk,
                "cell_size": cell_size,
                "tile_size_m": tile_size_m,
                "surface_tile_px": surface_tile_px,
                "echelle_m_per_px": echelle_m_per_px,
                "warnings": warnings
            }

        except Exception as e:
            self._log(f"[GENERATION] ERREUR parse_workbench_info : {e}")
            return {"ok": False, "error": str(e)}

    def get_block_budget(self) -> dict:
        """Retourne la valeur actuelle de pipeline.reforger_block_limit (5, 7 ou vide)."""
        if not _session["current_project_path"]:
            return {"value": None}
        try:
            proj_path = Path(_session["current_project_path"])
            # Délégation à project_reader
            budget = project_reader.get_block_budget(proj_path)
            return {"value": budget}
        except Exception as e:
            self._log(f"[TERRAIN] ERREUR get_block_budget : {e}")
            return {"value": None}

    def set_block_budget(self, value: int) -> dict:
        """Sauvegarde pipeline.reforger_block_limit dans project.json."""
        if not _session["current_project_path"]:
            return {"ok": False, "error_key": "error.no.project"}

        # Valider : uniquement 5 ou 7
        if value not in (5, 7):
            return {"ok": False, "error_key": "terrain.budget.error.invalid"}

        try:
            proj_path = Path(_session["current_project_path"])
            pjson = proj_path / "project.json"
            if not pjson.exists():
                return {"ok": False, "error": "project.json introuvable"}

            # Lire project.json
            data = json.loads(pjson.read_text(encoding="utf-8"))

            # Créer section pipeline si absente
            if "pipeline" not in data:
                data["pipeline"] = {}

            # Écrire uniquement reforger_block_limit
            data["pipeline"]["reforger_block_limit"] = value
            data["updated_at"] = datetime.now().isoformat(timespec="seconds")

            # Sauvegarder
            pjson.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

            # Mettre à jour la session
            _session["current_project"] = data

            self._log(f"[TERRAIN] Budget textures par bloc défini : {value} (fichier : {pjson.resolve()})")

            return {"ok": True}

        except Exception as e:
            self._log(f"[TERRAIN] ERREUR set_block_budget : {e}")
            return {"ok": False, "error": str(e)}

    def get_saved_workbench_info(self) -> dict:
        """Retourne les valeurs de grille enregistrées via project_reader + date."""
        if not _session["current_project_path"]:
            return {"ok": False}

        try:
            proj_path = Path(_session["current_project_path"])

            # Lire via project_reader
            grid_result = project_reader.get_grid(proj_path)

            if not grid_result.get("ok"):
                # Aucune grille enregistrée
                return {"ok": False}

            # Charger project.json pour récupérer la date
            data = json.loads((proj_path / "project.json").read_text(encoding="utf-8"))
            date_updated = data.get("workbench_info_updated")

            # Calculer taille terrain en km
            terrain_size_km = grid_result["terrain_size_m"] / 1000

            return {
                "ok": True,
                "grid_w": grid_result["grid_w"],
                "num_blk": grid_result["num_blk"],
                "tile_size_m": grid_result["tile_size_m"],
                "surface_tile_px": grid_result["surface_tile_px"],
                "m_per_px": grid_result["m_per_px"],
                "terrain_size_km": terrain_size_km,
                "date_updated": date_updated,
            }

        except Exception as e:
            self._log(f"[TERRAIN] ERREUR get_saved_workbench_info : {e}")
            return {"ok": False}

    # ── Tile Diagnostic : cache du scan global ───────────────────────────────────

    def _qtre_cache_stale(self, data: dict) -> bool:
        """Cache QTRE périmé : ancien format, ou .ttile / _layer ajoutés, retirés ou modifiés depuis le scan."""
        from tile_inspector import SCAN_FORMAT_VERSION, source_signature
        if data.get("version") != SCAN_FORMAT_VERSION or "source" not in data:
            return True
        grid = self._get_tile_grid()
        if not grid.get("ok"):
            return True
        dirs = grid["dirs"]
        current = source_signature(Path(dirs["data_dir"]), Path(dirs["editor_dir"]), grid["tile_prefix"])
        return current != data["source"]

    def get_satmap_b64(self) -> dict:
        """Retourne la satmap fond encodée en base64 pour la grille QTRE."""
        if not _session["current_project_path"]:
            return {"ok": False}
        try:
            import base64
            proj = Path(_session["current_project_path"])
            # Chercher satmap_fond_512.png ou satmap dans inputs/
            candidates = [
                proj / "outputs" / "generated" / "satmap_fond_512.png",
                proj / "inputs" / "satmap_fond_512.png",
                proj / "inputs" / "satmap_fond_512.jpg",
            ]
            for c in candidates:
                if c.exists():
                    ext = c.suffix.lower().replace(".", "")
                    b64 = base64.b64encode(c.read_bytes()).decode()
                    return {"ok": True, "b64": b64, "ext": ext}
            return {"ok": False, "reason": "no_satmap"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_scan_info(self) -> dict:
        """Retourne les infos du cache scan."""
        if not _session["current_project_path"]:
            return {"has_cache": False}
        try:
            proj = Path(_session["current_project_path"])
            cache = proj / "outputs" / "cache" / "qtre_scan.json"
            if not cache.exists():
                return {"has_cache": False}
            data = json.loads(cache.read_text(encoding="utf-8"))
            return {
                "has_cache": True,
                "n_tiles": len(data.get("tiles", [])),
                "generated_at": data.get("generated_at", "")[:19],
                "stale": self._qtre_cache_stale(data)
            }
        except Exception:
            return {"has_cache": False}

    def scan_tiles(self) -> dict:
        """Scanne toutes les tuiles .ttile (tile_inspector.export_json, appel direct en dev comme en exe)."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            proj = Path(_session["current_project_path"])

            # Récupérer grille + préfixe
            grid = self._get_tile_grid()
            if not grid.get("ok"):
                return {"ok": False, "error": grid["error"]}

            grid_w = grid["grid_w"]
            num_blk = grid["num_blk"]
            tile_prefix = grid["tile_prefix"]
            dirs = grid["dirs"]
            data_dir = Path(dirs["data_dir"])
            editor_dir = Path(dirs["editor_dir"])

            # Lire reforger_block_limit
            pjson = proj / "project.json"
            if not pjson.exists():
                return {"ok": False, "error": "project.json introuvable"}
            try:
                pdata = json.loads(pjson.read_text(encoding="utf-8"))
            except Exception as e:
                return {"ok": False, "error": f"Erreur lecture project.json : {e}"}

            block_budget = pdata.get("pipeline", {}).get("reforger_block_limit")
            if block_budget is None:
                return {"ok": False, "error_key": "terrain.budget.error.missing"}
            if block_budget not in (5, 7):
                return {"ok": False, "error_key": "terrain.budget.error.invalid"}

            if not data_dir.exists():
                return {"ok": False, "error": f"Dossier .Data introuvable : {data_dir}"}
            cache_dir = proj / "outputs" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_json = cache_dir / "qtre_scan.json"

            # Appel direct, même chemin en dev et en exe
            import io, contextlib
            from tile_inspector import export_json
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = export_json(data_dir, editor_dir, cache_json, grid_w, num_blk, tile_prefix, block_budget)
            log = buf.getvalue()[-3000:]
            if rc != 0:
                return {"ok": False, "error": "Erreur scan", "log": log}
            scan_data = json.loads(cache_json.read_text(encoding="utf-8")) if cache_json.exists() else {}
            n = len(scan_data.get("tiles", []))
            budget_str = f", budget={block_budget}" if block_budget else ""
            self._log(f"[DIAGNOSTIC] Scan terminé : {n} tuiles, grille={grid_w}×{grid_w}, préfixe={tile_prefix}{budget_str}")
            return {"ok": True, "n_tiles": n, "log": log}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Tile Diagnostic (étape 11d) ──────────────────────────────────────────────

    def _load_scan_v2(self) -> dict:
        """Charge qtre_scan.json (format version 2), gardé en mémoire tant que le fichier ne change pas."""
        from tile_inspector import SCAN_FORMAT_VERSION
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        cache = Path(_session["current_project_path"]) / "outputs" / "cache" / "qtre_scan.json"
        if not cache.exists():
            return {"ok": False, "reason": "no_cache"}
        key = (str(cache), cache.stat().st_mtime)
        if _session.get("scan_v2_key") != key:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("version") != SCAN_FORMAT_VERSION:
                return {"ok": False, "reason": "old_format"}
            _session["scan_v2"] = data
            _session["scan_v2_key"] = key
        return {"ok": True, "data": _session["scan_v2"]}

    def _surface_name(self, surfaces: list, mat_id: int) -> str:
        """Nom du matériau mat_id dans la table du .terr (MAT_<id> s'il est hors table)."""
        if mat_id >= len(surfaces):
            return f"MAT_{mat_id}"
        s = surfaces[mat_id]
        return s.get("emat", s.get("name", str(mat_id))) if isinstance(s, dict) else str(s)

    def diagnostic_grid(self) -> dict:
        """Grille du projet pour la page Tile Diagnostic : {"ok", "grid_w", "num_blk"}."""
        grid = self._get_tile_grid()
        if not grid.get("ok"):
            return {"ok": False, "error": grid["error"]}
        return {"ok": True, "grid_w": grid["grid_w"], "num_blk": grid["num_blk"]}

    def diagnostic_map(self, threshold: float) -> dict:
        """
        Carte globale : pour chaque tuile, nombre de textures et de slots négligeables de chaque bloc.

        Bloc i d'une tuile = (bx, by) avec i = by * num_blk + bx. Slot négligeable : couverture < threshold (0-1).
        Returns:
            {"ok", "grid_w", "num_blk", "block_budget", "generated_at", "stale",
             "tiles": [{"tx", "ty", "n_tex": [..], "n_neg": [..]}]}
        """
        try:
            scan = self._load_scan_v2()
            if not scan["ok"]:
                return scan
            data = scan["data"]
            num_blk = data["num_blk"]
            block_px = data["block_px"] or 1
            tiles = []
            for t in data["tiles"]:
                n_tex = [0] * (num_blk * num_blk)
                n_neg = [0] * (num_blk * num_blk)
                for b in t["blocks"]:
                    i = b["by"] * num_blk + b["bx"]
                    n_tex[i] = len(b["mat_ids"])
                    n_neg[i] = sum(1 for c in (b["coverage_px"] or []) if c / block_px < threshold)
                tiles.append({"tx": t["tx"], "ty": t["ty"], "n_tex": n_tex, "n_neg": n_neg})
            return {"ok": True, "grid_w": data["grid_w"], "num_blk": num_blk, "block_budget": data["block_budget"],
                    "generated_at": data["generated_at"], "stale": self._qtre_cache_stale(data), "tiles": tiles}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def diagnostic_materials(self) -> dict:
        """Textures de la table du .terr présentes dans le scan, avec leur nombre de blocs (pour la recherche)."""
        try:
            scan = self._load_scan_v2()
            if not scan["ok"]:
                return scan
            grid = self._get_tile_grid()
            if not grid.get("ok"):
                return {"ok": False, "error": grid["error"]}
            surfaces = grid["dirs"]["surfaces"]
            counts = {}
            for t in scan["data"]["tiles"]:
                for b in t["blocks"]:
                    for m in b["mat_ids"]:
                        counts[m] = counts.get(m, 0) + 1
            mats = [{"id": m, "name": self._surface_name(surfaces, m), "n_blocks": n} for m, n in counts.items()]
            mats.sort(key=lambda x: x["name"].lower())
            return {"ok": True, "materials": mats}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _blocks_with_all(self, data: dict, mat_ids: list):
        """Blocs du scan qui contiennent toutes les textures mat_ids (tous les blocs si la liste est vide)."""
        wanted = set(mat_ids)
        for t in data["tiles"]:
            for b in t["blocks"]:
                if wanted <= set(b["mat_ids"]):
                    yield t, b

    def diagnostic_search_blocks(self, mat_ids: list) -> dict:
        """Recherche des blocs contenant toutes les textures choisies. Returns {"ok", "blocks": [[tx, ty, bx, by], ..]}."""
        try:
            if not mat_ids:
                return {"ok": False, "error": "Aucune texture choisie"}
            scan = self._load_scan_v2()
            if not scan["ok"]:
                return scan
            blocks = [[t["tx"], t["ty"], b["bx"], b["by"]] for t, b in self._blocks_with_all(scan["data"], mat_ids)]
            self._log(f"[DIAGNOSTIC] Recherche {len(mat_ids)} texture(s) : {len(blocks)} bloc(s)")
            return {"ok": True, "blocks": blocks}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def diagnostic_export_csv(self, threshold: float, mat_ids: list) -> dict:
        """
        Exporte les blocs en CSV (séparateur ;) dans outputs/generated/diagnostic_blocs.csv :
        tous les blocs, ou seulement ceux qui contiennent toutes les textures mat_ids.
        """
        try:
            import csv
            scan = self._load_scan_v2()
            if not scan["ok"]:
                return scan
            grid = self._get_tile_grid()
            if not grid.get("ok"):
                return {"ok": False, "error": grid["error"]}
            surfaces = grid["dirs"]["surfaces"]
            data = scan["data"]
            num_blk = data["num_blk"]
            budget = data["block_budget"]
            block_px = data["block_px"] or 1

            out = Path(_session["current_project_path"]) / "outputs" / "generated" / "diagnostic_blocs.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            n_rows = 0
            with open(out, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["tx", "ty", "bx", "by", "lrs_x", "lrs_y", "n_textures", "budget", "depassement",
                            "slots_negligeables", "textures (couverture %)"])
                for t, b in self._blocks_with_all(data, mat_ids or []):
                    cov = b["coverage_px"]
                    names = [self._surface_name(surfaces, m) for m in b["mat_ids"]]
                    pcts = [c / block_px * 100 for c in cov] if cov else None
                    n_neg = sum(1 for p in pcts if p < threshold * 100) if pcts else ""
                    textures = " | ".join(f"{n} {p:.1f}" for n, p in zip(names, pcts)) if pcts else " | ".join(names)
                    n_tex = len(b["mat_ids"])
                    w.writerow([t["tx"], t["ty"], b["bx"], b["by"], t["tx"] * num_blk + b["bx"], t["ty"] * num_blk + b["by"],
                                n_tex, budget, "oui" if budget and n_tex > budget else "non", n_neg, textures])
                    n_rows += 1
            self._log(f"[DIAGNOSTIC] Export CSV : {n_rows} bloc(s) → {out}")
            return {"ok": True, "path": str(out), "n_rows": n_rows}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def diagnostic_inspect_tile(self, tx: int, ty: int, mode: str) -> dict:
        """
        Inspect d'une tuile (mode inspect, weights ou validate), coordonnées bornées par la grille.
        Returns: {"ok", "log", "img_b64"} (img_b64 = None pour validate)
        """
        try:
            import base64
            import io, contextlib
            if mode not in ("inspect", "weights", "validate"):
                return {"ok": False, "error": f"Mode inconnu : {mode}"}
            grid = self._get_tile_grid()
            if not grid.get("ok"):
                return {"ok": False, "error": grid["error"]}
            grid_w = grid["grid_w"]
            tx, ty = int(tx), int(ty)
            if not (0 <= tx < grid_w and 0 <= ty < grid_w):
                return {"ok": False, "error_key": "diag.tile.out.of.grid", "max": grid_w - 1}

            dirs = grid["dirs"]
            dest_dir = Path(_session["current_project_path"]) / "outputs" / "generated" / "tiles"
            dest_dir.mkdir(parents=True, exist_ok=True)

            from clean_weights import mode_inspect, mode_weights, mode_validate
            args = (tx, ty, Path(dirs["data_dir"]), Path(dirs["editor_dir"]), dirs["surfaces"])
            common = {"grid_w": grid_w, "num_blk": grid["num_blk"], "tile_prefix": grid["tile_prefix"]}
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                if mode == "inspect":
                    rc = mode_inspect(*args, threshold=0.01, output_dir=dest_dir, tile_size_m=grid["tile_size_m"],
                                      catalog_path=get_catalog_path(_session["current_project_path"]), **common)
                    img_path = dest_dir / f"tile_{tx}_{ty}_cleanup.png"
                elif mode == "weights":
                    rc = mode_weights(*args, output_dir=dest_dir, **common)
                    img_path = dest_dir / f"tile_{tx}_{ty}_weights.png"
                else:
                    rc = mode_validate(*args, **common)
                    img_path = None
            log = buf.getvalue()
            if len(log) > 2_000_000:
                log = "[SORTIE TRONQUÉE]\n" + log[-2_000_000:]

            self._log(f"[DIAGNOSTIC] Inspect ({tx},{ty}) mode={mode}")
            # validate renvoie 1 quand il trouve des erreurs : le rapport reste affiché
            if rc != 0 and mode != "validate":
                return {"ok": False, "error": "Erreur inspect", "log": log}
            img_b64 = base64.b64encode(img_path.read_bytes()).decode() if img_path else None
            return {"ok": True, "log": log, "img_b64": img_b64}
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "log": traceback.format_exc()[-800:]}

    # ── Generation ───────────────────────────────────────────────────────────────

    def get_generation_data(self) -> dict:
        """Retourne toutes les données nécessaires à l'onglet Generation."""
        if not _session["current_project_path"]:
            return {"ok": False}
        try:
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            paths = data.get("paths", {})
            # Textures depuis surfaces.json
            textures = ["default"]
            surfaces_json = proj / "surfaces.json"
            if surfaces_json.exists():
                s = json.loads(surfaces_json.read_text(encoding="utf-8"))
                textures = list(s.get("materials", {}).keys()) or ["default"]
            # Mask config depuis project_mask_config.json ou DEFAULT_MASK_CONFIG
            mask_config = []
            import pipeline_v5 as pv5
            mc_path = proj / "project_mask_config.json"
            tex_map = {t: i for i, t in enumerate(textures)}
            if mc_path.exists():
                mc_data = json.loads(mc_path.read_text(encoding="utf-8"))
                cfg = mc_data.get("mask_config", {})
                default_mat = mc_data.get("default_mat", "default")
                for i, (name, def_tex, _) in enumerate(pv5.DEFAULT_MASK_CONFIG, 1):
                    short = name.replace("mask_", "")
                    tex = cfg.get(name, def_tex)
                    mask_config.append({
                        "Masque": short, "Priorite": i,
                        "Texture": tex, "ID": tex_map.get(tex, 0)
                    })
            else:
                default_mat = "Grass_03" if "Grass_03" in textures else textures[0]
                for i, (name, tex, _) in enumerate(pv5.DEFAULT_MASK_CONFIG, 1):
                    short = name.replace("mask_", "")
                    mask_config.append({
                        "Masque": short, "Priorite": i,
                        "Texture": tex, "ID": tex_map.get(tex, 0)
                    })
            # Biomes
            biomes = {}
            biomes_path = _TEXTURES_USER_DIR / "biomes_presets.json"
            if biomes_path.exists():
                biomes = json.loads(biomes_path.read_text(encoding="utf-8-sig"))
            # Params
            params = data.get("pipeline_v5", {}).get("params", {})
            cal = data.get("pipeline_calibration", {}).get("values", {})
            params.update(cal)
            return {
                "ok": True,
                "textures": textures,
                "mask_config": mask_config,
                "biomes": {k: {"label": v.get("label",""), "label_en": v.get("label_en",""), "description": v.get("description",""), "custom_warning": v.get("custom_warning",[])} for k,v in biomes.items()},
                "biome_key": params.get("biome_key", ""),
                "default_mat": default_mat,
                "sources": paths,
                "params": params,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def apply_biome_preset(self, biome_key: str) -> dict:
        """Applique un preset biome et retourne le nouveau mask_config + params."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            biomes_path = _TEXTURES_USER_DIR / "biomes_presets.json"
            if not biomes_path.exists():
                return {"ok": False, "error": "biomes_presets.json introuvable"}
            biomes = json.loads(biomes_path.read_text(encoding="utf-8-sig"))
            preset = biomes.get(biome_key)
            if not preset:
                return {"ok": False, "error": f"Biome inconnu : {biome_key}"}
            proj = Path(_session["current_project_path"])
            # Appliquer textures → project_mask_config.json
            import pipeline_v5 as pv5
            surfaces_json = proj / "surfaces.json"
            textures = ["default"]
            tex_map = {}
            if surfaces_json.exists():
                s = json.loads(surfaces_json.read_text(encoding="utf-8"))
                textures = list(s.get("materials", {}).keys()) or ["default"]
                tex_map = {t: i for i, t in enumerate(textures)}
            tex_preset = preset.get("textures", {})
            cfg = {}
            mask_config = []
            for i, (name, def_tex, _) in enumerate(pv5.DEFAULT_MASK_CONFIG, 1):
                short = name.replace("mask_", "")
                tex = tex_preset.get(short, def_tex)
                if tex.startswith("CUSTOM_"):
                    tex = def_tex
                cfg[name] = tex
                mask_config.append({"Masque": short, "Priorite": i, "Texture": tex, "ID": tex_map.get(tex, 0)})
            # Sauvegarder project_mask_config.json
            mc_data = {"mask_config": cfg, "default_mat": tex_preset.get("default", "Grass_03"), "updated": datetime.now().isoformat()}
            (proj / "project_mask_config.json").write_text(json.dumps(mc_data, indent=2, ensure_ascii=False), encoding="utf-8")
            # Params du preset
            params = preset.get("sliders", {})
            params["biome_key"] = biome_key
            self._log(f"[GENERATION] Preset biome applique : {biome_key}")
            return {"ok": True, "mask_config": mask_config, "params": params}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def auto_calibrate_params(self, biome_key: str) -> dict:
        """Auto-calibre les seuils depuis le cache terrain npz."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            import numpy as np
            proj = Path(_session["current_project_path"])
            cache = proj / "outputs" / "cache" / "terrain_data.npz"
            if not cache.exists():
                return {"ok": False, "error": "Heightmap non analysee - allez dans Terrain > Atlas Metrique"}
            d = np.load(str(cache), allow_pickle=True)
            slope = d["slope"]
            hm = d["heightmap"]
            land = hm[hm > 0]
            if len(land) == 0: land = hm.flatten()
            flat = slope[~np.isnan(slope)]
            p85 = float(np.percentile(flat, 85))
            p95 = float(np.percentile(flat, 95))
            params = {
                "rock": round(p85, 1),
                "cliff": round(p95, 1),
                "coastal_width": round(float(np.percentile(land, 5)), 0),
                "prairie_alt_max": round(float(np.percentile(land, 30)), 0),
                "landes_plateau_min": round(float(np.percentile(land, 60)), 0),
                "alpages_alt_min": round(float(np.percentile(land, 80)), 0),
            }
            self._log(f"[GENERATION] Auto-calibrage : rock={params['rock']}° cliff={params['cliff']}°")
            return {"ok": True, "params": params}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_default_mask_config(self) -> dict:
        """Retourne le DEFAULT_MASK_CONFIG de pipeline_v5."""
        try:
            import pipeline_v5 as pv5
            proj = Path(_session["current_project_path"]) if _session["current_project_path"] else None
            textures = ["default"]
            if proj:
                s = proj / "surfaces.json"
                if s.exists():
                    textures = list(json.loads(s.read_text(encoding="utf-8")).get("materials", {}).keys()) or ["default"]
            tex_map = {t: i for i, t in enumerate(textures)}
            mask_config = []
            for i, (name, tex, _) in enumerate(pv5.DEFAULT_MASK_CONFIG, 1):
                mask_config.append({"Masque": name.replace("mask_",""), "Priorite": i, "Texture": tex, "ID": tex_map.get(tex, 0)})
            return {"ok": True, "mask_config": mask_config}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_mask_mapping(self, mask_config: list, default_mat: str) -> dict:
        """Sauvegarde le mapping masque→texture dans project_mask_config.json."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            proj = Path(_session["current_project_path"])
            import pipeline_v5 as pv5
            cfg = {}
            for i, (name, _, _) in enumerate(pv5.DEFAULT_MASK_CONFIG):
                short = name.replace("mask_", "")
                row = next((r for r in mask_config if r.get("Masque") == short), None)
                if row:
                    cfg[name] = row.get("Texture", "default")
            mc_data = {"mask_config": cfg, "default_mat": default_mat, "updated": datetime.now().isoformat()}
            (proj / "project_mask_config.json").write_text(json.dumps(mc_data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._log("[GENERATION] Mapping masques sauvegarde")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_v5_params(self, params: dict) -> dict:
        """Sauvegarde les paramètres pipeline_v5 dans project.json."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            # Séparer params pipeline_v5 et calibration
            v5_keys = ["roughness_mode","amplitude","scale","octaves","gentle","landes","rock","cliff","stretch","wmin","flow_cut","dep_cut","flow_gamma","dep_gamma","qtre_thresh","biome_key"]
            cal_keys = ["coastal_width","prairie_alt_max","prairie_seche_min","landes_plateau_min","maquis_alt_min","maquis_alt_max","foret_alt_min","alpages_alt_min","threshold_rock","threshold_cliff"]
            v5_params = {k: params[k] for k in v5_keys if k in params}
            cal_params = {k: params[k] for k in cal_keys if k in params}
            data.setdefault("pipeline_v5", {})["params"] = v5_params
            if cal_params:
                data["pipeline_calibration"] = {"updated": datetime.now().isoformat(), "values": cal_params}
            data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            (proj / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._log("[GENERATION] Parametres pipeline sauvegardes")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def run_pipeline_preview(self, params: dict, mask_config: list, default_mat: str) -> dict:
        """Lance pipeline_v5 en mode preview et retourne l'image composite en base64."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            import base64, numpy as np
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            paths = data.get("paths", {})
            import pipeline_v5 as pv5
            # Sauvegarder params et mapping d'abord
            self.save_v5_params(params)
            self.save_mask_mapping(mask_config, default_mat)
            # Résoudre chemins
            def resolve(rel):
                if not rel: return None
                p = Path(rel)
                if p.is_absolute(): return str(p) if p.exists() else None
                full = proj / rel
                return str(full) if full.exists() else None
            asc_path = resolve(paths.get("heightmap",""))
            if not asc_path:
                candidates = list((proj / "inputs").glob("*.asc"))
                if candidates: asc_path = str(candidates[0])
            if not asc_path:
                return {"ok": False, "error": "Heightmap introuvable"}
            output_dir = proj / "outputs" / "generated" / "pipeline_preview"
            output_dir.mkdir(parents=True, exist_ok=True)
            # Construire mask_config pour pipeline
            mc_path = proj / "project_mask_config.json"
            if mc_path.exists():
                mc_data = json.loads(mc_path.read_text(encoding="utf-8"))
                cfg_dict = mc_data.get("mask_config", {})
            else:
                cfg_dict = {}
            # Construire mask_cfg : (nom_masque, nom_texture, couleur)
            mask_cfg = []
            for name, def_tex, color in pv5.DEFAULT_MASK_CONFIG:
                tex = cfg_dict.get(name, def_tex)
                mask_cfg.append((name, tex, color))
            # Calibration
            calibration = {
                "coastal_width": float(params.get("coastal_width", 40)),
                "prairie_alt_max": float(params.get("prairie_alt_max", 80)),
                "prairie_seche_min": float(params.get("prairie_seche_min", 15)),
                "prairie_seche_max": float(params.get("prairie_alt_max", 80)),
                "landes_plateau_min": float(params.get("landes_plateau_min", 120)),
                "maquis_alt_min": float(params.get("maquis_alt_min", 30)),
                "maquis_alt_max": float(params.get("maquis_alt_max", 120)),
                "foret_alt_min": float(params.get("foret_alt_min", 30)),
                "alpages_alt_min": float(params.get("alpages_alt_min", 180)),
                "threshold_rock": float(params.get("rock", 22)),
                "threshold_cliff": float(params.get("cliff", 26)),
                "flow_cut": float(params.get("flow_cut", 0.45)),
                "flow_gamma": float(params.get("flow_gamma", 0.5)),
                "dep_cut": float(params.get("dep_cut", 0.30)),
                "dep_gamma": float(params.get("dep_gamma", 1.0)),
                "gamma_global": 1.0,
            }
            # Patcher globals pipeline_v5
            pv5.ROUGHNESS_AMPLITUDE = float(params.get("amplitude", 8.0))
            pv5.ROUGHNESS_SCALE = float(params.get("scale", 0.008))
            pv5.ROUGHNESS_OCTAVES = int(params.get("octaves", 6))
            pv5.ROUGHNESS_MODE = params.get("roughness_mode", "slope_perturb")
            pv5.THRESHOLD_ROCK = float(params.get("rock", 22))
            pv5.THRESHOLD_CLIFF = float(params.get("cliff", 26))
            pv5.WEIGHT_MIN = float(params.get("wmin", 0.10))
            pv5.STRETCH_AUTO = bool(params.get("stretch", True))
            pv5.DEPOSIT_CUT_LOW = float(params.get("dep_cut", 0.30))
            # Chemins optionnels
            excl = resolve(paths.get("exclusion_mask",""))
            flow = resolve(paths.get("gaea_flow",""))
            deposit = resolve(paths.get("gaea_deposit",""))
            # Lancer preview
            grid = self._get_project_grid()
            if not grid.get("ok"):
                return {"ok": False, "error": grid["error"]}
            grid_w = grid["grid_w"]
            num_blk = grid["num_blk"]

            # Lire tile_prefix et budget depuis project_reader
            import project_reader
            addon_path = data.get("paths", {}).get("addon_reforger", "")
            if addon_path:
                tile_prefix = project_reader.get_tile_prefix(Path(addon_path) / ".Data")
            else:
                tile_prefix = "Terrain_"  # Fallback
            block_budget = project_reader.get_block_budget(proj)

            # Obtenir data_dir pour Zone B et table matériaux depuis .terr
            dirs = self._get_terrain_dirs()
            data_dir_path = None
            mat_id_to_name = None
            if dirs.get("ok"):
                data_dir_path = Path(dirs["data_dir"]) if dirs.get("data_dir") else None
                if data_dir_path and data_dir_path.exists():
                    mat_id_to_name = self._get_materials_table()

            import io, contextlib

            # Capturer stdout du pipeline
            stdout_capture = io.StringIO()
            with contextlib.redirect_stdout(stdout_capture):
                result = pv5.run_pipeline(
                    asc_path=Path(asc_path),
                    output_dir=output_dir,
                    grid_w=grid_w,
                    num_blk=num_blk,
                    tile_prefix=tile_prefix,
                    block_budget=block_budget,
                    exclusion_path=Path(excl) if excl else None,
                    gaea_flow=Path(flow) if flow else None,
                    gaea_deposit=Path(deposit) if deposit else None,
                    data_dir=data_dir_path,
                    mask_config=mask_cfg,
                    mat_id_to_name=mat_id_to_name,
                    calibration=calibration,
                    mode="preview",
                )

            # Injecter les lignes capturées dans le log session
            pipeline_output = stdout_capture.getvalue()
            for line in pipeline_output.splitlines():
                line = line.strip()
                if line:
                    _session["session_log"].append(f"[PIPELINE] {line}")

            masks = result.get('masques', {})
            # Sauvegarder les masques ndarrays en PNG 16-bit dans output_dir
            import cv2 as _cv2
            for _name, _arr in masks.items():
                if _arr is None: continue
                _png_path = output_dir / f"{_name}.png"
                _cv2.imwrite(str(_png_path), (_arr * 65535).astype('uint16'))
            # Générer image composite
            from PIL import Image
            composite = None
            colors = {name: color for name, _, color in pv5.DEFAULT_MASK_CONFIG}
            for k, v in masks.items():
                if v is None: continue
                color = colors.get(k, (136, 136, 136))
                if isinstance(color, tuple):
                    r, g, b = color[0], color[1], color[2]
                else:
                    color_hex = color.lstrip("#")
                    r,g,b = int(color_hex[0:2],16), int(color_hex[2:4],16), int(color_hex[4:6],16)
                layer = np.zeros((*v.shape, 4), dtype=np.uint8)
                layer[...,0] = r; layer[...,1] = g; layer[...,2] = b
                layer[...,3] = (np.clip(v,0,1)*200).astype(np.uint8)
                img = Image.fromarray(layer, 'RGBA')
                img = img.resize((512,512), Image.LANCZOS)
                if composite is None:
                    composite = img
                else:
                    composite = Image.alpha_composite(composite, img)
            if composite is None:
                return {"ok": False, "error": "Aucun masque genere"}
            import io
            buf = io.BytesIO()
            composite.convert('RGB').save(buf, format='PNG', optimize=True)
            img_b64 = base64.b64encode(buf.getvalue()).decode()
            preview_png = output_dir / "pipeline_preview.png"
            if preview_png.exists():
                self._log(f"[GENERATION] Preview : {preview_png}")
            self._log(f"[GENERATION] Preview generee : {len(masks)} masques")
            return {"ok": True, "img_b64": img_b64, "n_masks": len(masks)}
        except Exception as e:
            import traceback
            self._log(f"[GENERATION] ERREUR : {e}")
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc()[-500:]}

    def export_masks_png(self) -> dict:
        """Copie les masques preview vers outputs/masks/latest/."""
        if not _session["current_project_path"]:
            return {"ok": False}
        try:
            import shutil
            proj = Path(_session["current_project_path"])
            src = proj / "outputs" / "generated" / "pipeline_preview"
            dst = proj / "outputs" / "masks" / "latest"
            dst.mkdir(parents=True, exist_ok=True)
            n = 0
            for f in src.glob("mask_*.png"):
                shutil.copy2(f, dst / f.name)
                n += 1
            self._log(f"[GENERATION] {n} masques PNG exportes")
            return {"ok": True, "n": n}
        except Exception as e:
            return {"ok": False, "error": str(e)}


    # ── Textures du projet ───────────────────────────────────────────────────────

    def _textures_context(self) -> dict:
        """Dossier de textures du projet, addon et .terr ; {"ok": False, "error"} si incomplet."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        proj = Path(_session["current_project_path"])
        tex = ensure_project_textures(proj)
        if not tex["ok"]:
            return tex
        rp = project_reader.get_terrain_dirs(proj)
        if not rp.get("ok"):
            return {"ok": False, "error": rp.get("error")}
        if not rp.get("terr_file"):
            return {"ok": False, "error": "Fichier .terr introuvable dans le dossier du terrain"}
        return {"ok": True, "textures_dir": get_project_textures_dir(proj),
                "addon_dir": Path(project_reader.get_addon_path(proj)["addon_path"]),
                "terr_file": Path(rp["terr_file"])}

    def textures_status(self) -> dict:
        """État des textures du projet : une ligne par matériau du .terr (lecture seule)."""
        ctx = self._textures_context()
        if not ctx["ok"]:
            return ctx
        try:
            from textures_sync import textures_status
            return textures_status(ctx["textures_dir"], ctx["addon_dir"], ctx["terr_file"], _VANILLA_BASE_SRC)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def textures_sync(self) -> dict:
        """Synchronise les textures du projet avec le .terr et l'addon (.emat, middles, catalog.json)."""
        ctx = self._textures_context()
        if not ctx["ok"]:
            return ctx
        try:
            from textures_sync import sync_textures
            self._log("[TEXTURES] Synchronisation avec le .terr et l'addon...")
            r = sync_textures(ctx["textures_dir"], ctx["addon_dir"], ctx["terr_file"], _VANILLA_BASE_SRC)
            if not r["ok"]:
                self._log(f"[TEXTURES] Erreur : {r['error']}")
                return r
            self._log(f"[TEXTURES] .emat ajoutés : {len(r['emat_added'])}, mis à jour : {len(r['emat_updated'])}, "
                      f"middles ajoutés : {len(r['middles_added'])}, entrées du catalog écrites : {len(r['entries_written'])}")
            for item in r["middle_missing"]:
                self._log(f"[TEXTURES] Middle manquant : {item['emat']} -> {item['middle']}")
            for name in r["emat_missing"]:
                self._log(f"[TEXTURES] .emat introuvable (ni addon ni projet) : {name}")
            for name in r["parent_missing"]:
                self._log(f"[TEXTURES] Parent introuvable : {name}")
            return r
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def textures_set_middle(self, emat_name: str, image_path: str = "") -> dict:
        """Choix manuel du middle d'un matériau ; image_path vide retire le choix manuel."""
        ctx = self._textures_context()
        if not ctx["ok"]:
            return ctx
        try:
            from textures_sync import set_manual_middle
            r = set_manual_middle(ctx["textures_dir"], emat_name, image_path)
            if r["ok"] and r.get("changed"):
                what = r.get("middle") or "choix manuel retiré"
                self._log(f"[TEXTURES] Middle de {emat_name} : {what}")
            return r
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def textures_thumbnails(self, size: int = 64) -> dict:
        """Vignettes des middles teintés, en JPEG base64 : {"ok", "thumbs": {emat: b64}}."""
        ctx = self._textures_context()
        if not ctx["ok"]:
            return ctx
        try:
            from textures_sync import middle_thumbnails
            return {"ok": True, "thumbs": middle_thumbnails(ctx["textures_dir"], ctx["terr_file"], int(size))}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def textures_open_dir(self, kind: str) -> dict:
        """Ouvre l'explorateur sur le dossier des .emat (kind="emat") ou des middles (kind="middles") du projet."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        proj = _session["current_project_path"]
        dirs = {"emat": get_emat_dir(proj), "middles": get_middles_dir(proj)}
        if kind not in dirs:
            return {"ok": False, "error": f"Dossier inconnu : {kind}"}
        return self.open_file_location(str(dirs[kind]))


    # ── Satmap ───────────────────────────────────────────────────────────────────

    def check_satmap_catalog(self) -> dict:
        """Vérifie le catalog.json et résout les chemins terrain."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            paths = data.get("paths", {})

            # Ignorer catalog_json du project.json (legacy), utiliser celui de <projet>/textures/
            if "catalog_json" in paths:
                print("[INFO] Clé 'catalog_json' ignorée dans project.json (legacy)")

            catalog_path = get_catalog_path(proj)
            if not catalog_path.exists():
                return {"ok": False, "error": "catalog.json du projet introuvable — synchronisez dans l'onglet Textures"}
            cat = json.loads(catalog_path.read_text(encoding="utf-8"))
            n_entries = len(cat)
            # Résoudre terrain_dir depuis addon_reforger
            terrain_dir = ""
            terrain_ok = False
            try:
                rp = self._get_terrain_dirs()
                if rp.get("ok"):
                    terrain_dir = rp.get("terrain_dir", "")
                    terrain_ok = bool(terrain_dir and Path(terrain_dir).exists())
            except Exception:
                pass
            return {
                "ok": True,
                "catalog_name": catalog_path.name,
                "n_entries": n_entries,
                "terrain_dir": terrain_dir,
                "terrain_ok": terrain_ok,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def generate_satmap_v2(self, resolution: int) -> dict:
        """Lance la génération Satmap v2.0 (mode texturé, textures du projet)."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            # Vérifier grille configurée
            grid = self._get_project_grid()
            if not grid.get("ok"):
                return {"ok": False, "error": grid["error"]}

            import base64, io
            from PIL import Image
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            paths = data.get("paths", {})

            # Ignorer catalog_json du project.json (legacy)
            if "catalog_json" in paths:
                print("[INFO] Clé 'catalog_json' ignorée dans project.json (legacy)")

            catalog_path = get_catalog_path(proj)
            if not catalog_path.exists():
                return {"ok": False, "error": "catalog.json introuvable"}

            rp = self._get_terrain_dirs()
            if not rp.get("ok"):
                return {"ok": False, "error": f"Addon invalide : {rp.get('error')}"}
            terrain_dir = Path(rp["terrain_dir"])
            terr_file = rp.get("terr_file")
            # Sortie
            output_dir = proj / "outputs" / "generated"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Middles du projet (couleurs unies si le dossier manque)
            middles_dir = get_middles_dir(proj)
            if not middles_dir.exists():
                middles_dir = None
                self._log("[SATMAP] Dossier des middles du projet introuvable : couleurs unies")

            # Calculer échelle depuis grille
            echelle_m_per_px = grid["tile_size_m"] / grid["surface_tile_px"]
            self._log(f"[SATMAP] Échelle : {echelle_m_per_px:.3f} m/px (tile_size_m={grid['tile_size_m']}, surface_tile_px={grid['surface_tile_px']})")

            # Générer satmap
            from satmap_v2_textured_v2 import generate_satmap_v2_textured_complete
            emat_dir = get_emat_dir(proj)

            # Chemin temporaire (sera remplacé par le nommage selon règles dans la fonction)
            temp_output_path = output_dir / "satmap_v2_textured_temp.png"

            stats = generate_satmap_v2_textured_complete(
                terrain_dir, catalog_path, temp_output_path,
                grid["grid_w"], grid["num_blk"],
                terr_file=terr_file, mode="textured",
                target_resolution=resolution if resolution != 0 else None, verbose=True,
                middles_dir=middles_dir,
                emat_dir=emat_dir,
                echelle_m_per_px=echelle_m_per_px
            )

            if not stats or "output_path" not in stats:
                return {"ok": False, "error": "Fichier satmap non généré"}

            output_path = Path(stats["output_path"])
            if not output_path.exists():
                return {"ok": False, "error": f"Fichier non trouvé : {output_path}"}

            self._log(f"[SATMAP] Sauvegardé : {output_path.name}")

            # Thumbnail base64
            Image.MAX_IMAGE_PIXELS = None
            img = Image.open(str(output_path))
            img.thumbnail((800, 800), Image.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            # Lire dimensions réelles
            w, h = img.size

            self._log(f"[SATMAP] Satmap v2.0 générée : {output_path.name}")
            return {
                "ok": True,
                "filename": output_path.name,
                "output_path": str(output_path),
                "img_b64": img_b64,
                "ext": "jpeg",
                "stats": {
                    "size": stats.get("size", f"{w}x{h}"),
                    "missing_layers": stats.get("missing_layers", 0),
                    "material_issues": stats.get("material_issues", 0),
                }
            }
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc()[-800:]}

    def pick_any_file(self, extensions: list) -> dict:
        """Ouvre un dialogue de sélection de fichier sans copier — retourne le chemin absolu."""
        window = webview.windows[0] if webview.windows else None
        if not window:
            return {"ok": False, "error": "Pas de fenetre"}
        if extensions:
            file_types = tuple(f"{e.upper()} files (*.{e})" for e in extensions)
        else:
            file_types = ("All files (*.*)",)
        try:
            from webview import FileDialog
            open_const = FileDialog.OPEN
        except (ImportError, AttributeError):
            open_const = getattr(webview, 'OPEN', None) or getattr(webview, 'OPEN_DIALOG', 0)
        files = window.create_file_dialog(open_const, allow_multiple=False, file_types=file_types)
        if not files:
            return {"ok": False, "cancelled": True}
        path = str(files[0])
        return {"ok": True, "path": path, "filename": Path(files[0]).name}

    # ── Grille et dossiers terrain du projet ─────────────────────────────────────

    def _get_terrain_dirs(self) -> dict:
        """Retourne les dossiers terrain (.Data, .EditorData) et surfaces depuis le projet."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}

        proj = Path(_session["current_project_path"])

        # Délégation à project_reader pour résoudre les chemins terrain
        result = project_reader.get_terrain_dirs(proj)
        if not result.get("ok"):
            return result

        # Utiliser table matériaux en mémoire (chargée depuis .terr)
        mat_id_to_name = self._get_materials_table()
        if not mat_id_to_name:
            return {"ok": False, "error": "Matériaux non chargés (table vide)"}

        max_id = max(mat_id_to_name.keys())
        surfaces = [mat_id_to_name.get(i, f"MAT_{i}") for i in range(max_id + 1)]

        return {
            "ok": True,
            "terrain_dir": result["terrain_dir"],
            "data_dir": result["data_dir"],
            "editor_dir": result["editor_dir"],
            "surfaces": surfaces,
            "terr_file": result["terr_file"],
        }

    def _get_tile_grid(self) -> dict:
        """
        Retourne la configuration grille + détection du préfixe des .ttile.

        Combine _get_project_grid() + détection automatique du tile_prefix depuis .Data.

        Returns:
            {"ok": True, "grid_w", "num_blk", "surface_tile_px", "tile_size_m", "tile_prefix": str, "dirs": dict}
            ou {"ok": False, "error": str}
        """
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}

        # Lire grille depuis project_reader
        grid = self._get_project_grid()
        if not grid.get("ok"):
            return grid

        # Obtenir dirs terrain depuis project_reader
        dirs = self._get_terrain_dirs()
        if not dirs["ok"]:
            return {"ok": False, "error": dirs["error"]}

        # Détecter préfixe depuis project_reader
        prefix_result = project_reader.get_tile_prefix(Path(dirs["data_dir"]))
        if not prefix_result.get("ok"):
            return prefix_result

        return {
            "ok": True,
            "grid_w": grid["grid_w"],
            "num_blk": grid["num_blk"],
            "surface_tile_px": grid["surface_tile_px"],
            "tile_size_m": grid["tile_size_m"],
            "tile_prefix": prefix_result["tile_prefix"],
            "dirs": dirs,
        }

    def _get_project_grid(self) -> dict:
        """
        Lit la configuration grille depuis project.json uniquement.

        Clés OBLIGATOIRES (entiers > 0) :
        - grid_w : nombre de tuiles par côté (ex: 32 → 32×32)
        - num_blk : nombre de blocs par tuile et par côté (ex: 4 → 4×4)
        - surface_tile_px : résolution de la surface map par tuile (ex: 512)
        - tile_size_m : taille d'une tuile en mètres (ex: 512)

        Returns:
            {"ok": True, "grid_w": int, "num_blk": int, "surface_tile_px": int, "tile_size_m": int}
            ou {"ok": False, "missing": [str], "error": str}
        """
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}

        proj = Path(_session["current_project_path"])

        # Délégation à project_reader
        result = project_reader.get_grid(proj)

        # Retourner seulement les 4 clés attendues (pas m_per_px ni terrain_size_m)
        if result.get("ok"):
            return {
                "ok": True,
                "grid_w": result["grid_w"],
                "num_blk": result["num_blk"],
                "surface_tile_px": result["surface_tile_px"],
                "tile_size_m": result["tile_size_m"],
            }

        return result

    def diagnostic_scan_zone(self, mask_path: str) -> dict:
        """Scan par zone définie par un masque PNG."""
        try:
            import io, contextlib
            mask = Path(mask_path)
            if not mask.exists():
                return {"ok": False, "error": f"Masque introuvable : {mask_path}"}

            # Récupérer grille et tile_prefix
            grid = self._get_tile_grid()
            if not grid.get("ok"):
                return {"ok": False, "error": grid["error"]}

            dirs = grid["dirs"]

            # Appel direct
            from clean_weights import mode_scan_zone
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                mode_scan_zone(mask, Path(dirs["data_dir"]), Path(dirs["editor_dir"]), dirs["surfaces"], grid["grid_w"], grid["num_blk"], grid["tile_prefix"])
            log = buf.getvalue()
            if len(log) > 2_000_000:
                log = "[SORTIE TRONQUÉE]\n" + log[-2_000_000:]
            self._log(f"[DIAGNOSTIC] Scan zone termine : {mask.name}")
            return {"ok": True, "log": log}
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "log": traceback.format_exc()[-800:]}

    def diagnostic_terrain_health(self) -> dict:
        """Analyse de santé globale du terrain."""
        try:
            import re

            # Récupérer grille et tile_prefix
            grid = self._get_tile_grid()
            if not grid.get("ok"):
                return {"ok": False, "error": grid["error"]}

            dirs = grid["dirs"]
            data_dir = Path(dirs["data_dir"])
            editor_dir = Path(dirs["editor_dir"])
            tile_prefix = grid["tile_prefix"]

            if not data_dir.exists():
                return {"ok": False, "error": f"Dossier .Data introuvable : {data_dir}"}

            self._log(f"[DIAGNOSTIC] Terrain Health : dossier={data_dir}, préfixe={tile_prefix}")

            # Lister tuiles avec le préfixe du projet
            pattern = re.compile(rf'^{re.escape(tile_prefix)}(\d+)\.ttile$')
            ttiles = [f for f in data_dir.glob("*.ttile") if pattern.match(f.name)]
            n_tiles = len(ttiles)
            n_ok = 0; n_warn = 0; n_err = 0
            log_lines = [f"[SANTE] {n_tiles} tuiles .ttile trouvees dans {data_dir}"]
            # Vérifier taille minimale de chaque tuile
            for t in ttiles[:100]:  # Limiter à 100 pour la perf
                size = t.stat().st_size
                if size < 100:
                    n_err += 1
                    log_lines.append(f"  ERREUR tuile trop petite : {t.name} ({size} bytes)")
                elif size < 1000:
                    n_warn += 1
                    log_lines.append(f"  WARN tuile suspecte : {t.name} ({size} bytes)")
                else:
                    n_ok += 1
            if n_tiles > 100:
                log_lines.append("  (Analyse limitee aux 100 premieres tuiles)")
            # Vérifier .EditorData
            if editor_dir.exists():
                edds = list(editor_dir.glob("*.edds"))
                log_lines.append(f"[SANTE] {len(edds)} fichiers .edds dans .EditorData")
            else:
                log_lines.append("[SANTE] WARN : .EditorData absent")
                n_warn += 1
            log = chr(10).join(log_lines)
            self._log(f"[DIAGNOSTIC] Sante terrain : {n_ok} OK / {n_warn} warn / {n_err} err")
            return {"ok": True, "n_tiles": n_tiles, "n_ok": n_ok, "n_warn": n_warn, "n_err": n_err, "log": log}
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "log": traceback.format_exc()[-800:]}

    def diagnostic_file_inventory(self) -> dict:
        """Inventaire complet des fichiers .ttile et .edds attendus vs présents."""
        try:
            import re

            # Vérifier grille AVANT l'addon
            grid = self._get_tile_grid()
            if not grid.get("ok"):
                return {"ok": False, "error": grid["error"]}

            grid_w = grid["grid_w"]
            tile_prefix = grid["tile_prefix"]
            dirs = grid["dirs"]
            data_dir = Path(dirs["data_dir"])
            editor_dir = Path(dirs["editor_dir"])

            if not data_dir.exists():
                return {"ok": False, "error": f"Dossier .Data introuvable : {data_dir}"}

            self._log(f"[DIAGNOSTIC] Inventaire : dossier={data_dir}, préfixe={tile_prefix}, grille={grid_w}x{grid_w}")

            # .ttile attendus : {prefix}0.ttile … {prefix}{grid_w*grid_w - 1}.ttile
            n_expected = grid_w * grid_w
            present_ttile = set()
            pattern = re.compile(rf'^{re.escape(tile_prefix)}(\d+)\.ttile$')

            for f in data_dir.glob("*.ttile"):
                match = pattern.match(f.name)
                if match:
                    try:
                        n = int(match.group(1))
                        present_ttile.add(n)
                    except ValueError:
                        pass

            missing = [f"{tile_prefix}{i}.ttile" for i in range(n_expected) if i not in present_ttile]
            # Layers : .edds dans .Data | Weights : .dds dans .EditorData
            n_edds = len(list(data_dir.glob("*.edds"))) if data_dir.exists() else 0
            n_dds = len(list(editor_dir.glob("*.dds"))) if editor_dir.exists() else 0
            log_lines = [
                f"[INVENTAIRE] Grille {grid_w}x{grid_w} = {n_expected} tuiles attendues",
                f"[INVENTAIRE] .ttile presents : {len(present_ttile)} / {n_expected}",
                f"[INVENTAIRE] .ttile manquants : {len(missing)}",
                f"[INVENTAIRE] Layers : {n_edds} .edds (.Data) | {n_dds} .dds (.EditorData)",
            ]
            if missing[:10]:
                log_lines.append(f"[INVENTAIRE] Premiers manquants : {', '.join(missing[:10])}")
            self._log(f"[DIAGNOSTIC] Inventaire : {len(missing)} .ttile manquants")
            return {
                "ok": True,
                "n_ttile_present": len(present_ttile),
                "missing_ttile": len(missing),
                "n_edds_present": n_edds,
                "n_dds_present": n_dds,
                "missing_list": missing[:50],
                "log": chr(10).join(log_lines),
            }
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "log": traceback.format_exc()[-800:]}

    def pick_existing_project(self) -> dict:
        """Ouvre un dialogue pour selectionner un dossier projet existant."""
        window = webview.windows[0] if webview.windows else None
        if not window:
            return {"ok": False, "error": "Pas de fenetre"}
        try:
            from webview import FileDialog
            folder_const = FileDialog.FOLDER
        except (ImportError, AttributeError):
            folder_const = getattr(webview, 'FOLDER', None) or getattr(webview, 'FOLDER_DIALOG', 1)
        folders = window.create_file_dialog(folder_const)
        if not folders:
            return {"ok": False, "cancelled": True}
        folder = Path(folders[0])
        project_json = folder / "project.json"
        if not project_json.exists():
            return {"ok": False, "error": "Aucun project.json dans ce dossier"}
        # Charger le projet
        result = self.load_project(str(folder))
        if result.get("ok"):
            self._log(f"[PROJET] Projet existant ouvert : {folder.name}")
        return result

    # ── Interne ───────────────────────────────────────────────────────────────

    def _compare_materials_snapshot(self, old_materials: dict, new_materials: dict) -> list:
        """Compare ancien/nouveau snapshot matériaux, retourne liste IDs modifiés."""
        changes = []
        all_ids = set(old_materials.keys()) | set(new_materials.keys())

        for id_ in sorted(all_ids):
            old_name = old_materials.get(id_, None)
            new_name = new_materials.get(id_, None)
            if old_name != new_name:
                changes.append((id_, old_name or "(absent)", new_name or "(absent)"))

        return changes

    def _load_materials_from_terr(self):
        """Charge table matériaux depuis .terr du projet courant. WARNING si erreur, table vide."""
        from terrain_terr_reader import read_mats_from_terr
        import json
        from datetime import datetime

        # Vider table AVANT lecture
        _session["materials_id_to_name"] = {}
        _session["materials_terr_path"] = None
        _session["materials_terr_mtime"] = None

        proj_path = _session.get("current_project_path")
        if not proj_path:
            return

        proj = Path(proj_path)

        # Résoudre chemins via project_reader
        terrain_result = project_reader.get_terrain_dirs(proj)

        if not terrain_result.get("ok"):
            self._log(f"[WARNING] Erreur résolution terrain : {terrain_result.get('error')}")
            return

        terr_file = terrain_result.get("terr_file")
        if not terr_file:
            self._log(f"[WARNING] Aucun .terr trouvé dans {terrain_result.get('terrain_dir')}")
            return

        terr_path = Path(terr_file)

        try:
            # Lire matériaux depuis .terr
            entries = read_mats_from_terr(terr_path)

            if len(entries) == 0:
                self._log(f"[WARNING] .terr retourne 0 matériaux : {terr_path}")
                return

            # Stocker en session
            materials_id_to_name = {e["id"]: e["name"] for e in entries}
            _session["materials_id_to_name"] = materials_id_to_name
            _session["materials_terr_path"] = str(terr_path)
            _session["materials_terr_mtime"] = terr_path.stat().st_mtime

            self._log(f"[MATERIAUX] Chargés depuis .terr : {terr_path.name} ({len(entries)} matériaux)")

            # Instantané surfaces.json : comparer + écrire
            surfaces_json = proj / "surfaces.json"
            old_materials = {}
            s = {}

            if surfaces_json.exists():
                try:
                    s = json.loads(surfaces_json.read_text(encoding="utf-8"))
                    old_mats = s.get("materials", {})
                    # Inverser nom→ID vers ID→nom
                    old_materials = {int(v): k for k, v in old_mats.items()}
                except Exception as e:
                    self._log(f"[WARNING] Erreur lecture ancien surfaces.json : {e}")

            # Comparer
            changes = self._compare_materials_snapshot(old_materials, materials_id_to_name)

            if changes:
                self._log(f"[WARNING] Ordre/contenu matériaux modifié dans Workbench - {len(changes)} IDs changés")
                self._log("[WARNING] Cache scan global à régénérer")
                for id_, old_name, new_name in changes[:10]:  # Max 10 premiers
                    self._log(f"  ID {id_:2d} : {old_name} → {new_name}")
                if len(changes) > 10:
                    self._log(f"  ... et {len(changes) - 10} autres")

            # Écrire nouveau snapshot (seulement si le contenu change, "generated" exclu)
            snapshot = {
                "terr_path": str(terr_path),
                "terr_size": terr_path.stat().st_size,
                "generated": datetime.now().isoformat(),
                "count": len(materials_id_to_name),
                "materials": {name: id_ for id_, name in materials_id_to_name.items()}
            }
            content_keys = ("terr_path", "terr_size", "count", "materials")
            if any(s.get(k) != snapshot[k] for k in content_keys):
                surfaces_json.write_text(
                    json.dumps(snapshot, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
                self._log(f"[MATERIAUX] surfaces.json mis à jour : {surfaces_json}")

        except Exception as e:
            self._log(f"[WARNING] Erreur chargement matériaux : {e}")
            import traceback
            self._log(traceback.format_exc()[-500:])

    def _get_materials_table(self) -> dict:
        """
        Point d'accès unique à la table matériaux.
        Vérifie la validité du cache (chemin .terr + mtime) et recharge si nécessaire.
        """
        proj_path = _session.get("current_project_path")
        if not proj_path:
            return {}

        proj = Path(proj_path)

        # Obtenir chemin .terr de la même façon que _load_materials_from_terr()
        terrain_result = project_reader.get_terrain_dirs(proj)
        if not terrain_result.get("ok"):
            return {}

        terr_file = terrain_result.get("terr_file")
        if not terr_file:
            return {}

        terr_path = Path(terr_file)
        terr_path_str = str(terr_path)

        # Vérifier validité du cache
        cached_path = _session.get("materials_terr_path")
        cached_mtime = _session.get("materials_terr_mtime")

        reload_needed = False
        log_modified = False

        if not cached_path or cached_path != terr_path_str:
            # Pas de cache ou changement de projet
            reload_needed = True
            log_modified = False
        else:
            # Même chemin : vérifier mtime
            try:
                current_mtime = terr_path.stat().st_mtime
                if cached_mtime is None or current_mtime != cached_mtime:
                    reload_needed = True
                    log_modified = True
            except (OSError, FileNotFoundError):
                reload_needed = True
                log_modified = False

        if reload_needed:
            if log_modified:
                self._log(f"[INFO] .terr modifié depuis le dernier chargement, relecture : {terr_path_str}")
            self._load_materials_from_terr()

        return _session.get("materials_id_to_name", {})

    def _load_project_internal(self, path: str, data: dict):
        _session["current_project_path"] = path
        _session["current_project"] = data
        # Textures du projet : copie du dossier modèle si le projet n'en a pas encore
        tex = ensure_project_textures(path)
        if not tex["ok"]:
            self._log(f"[TEXTURES] WARNING : {tex['error']}")
        elif tex["copied"]:
            self._log(f"[TEXTURES] Dossier modèle copié dans {tex['textures_dir']}")
        # Charger matériaux depuis .terr
        self._load_materials_from_terr()
        # Détecter et logger grille projet
        grid = self._get_project_grid()
        if grid.get("ok"):
            self._log(f"[GRID] Configuré : grid_w={grid['grid_w']}, num_blk={grid['num_blk']}, tile_size_m={grid['tile_size_m']}, surface_tile_px={grid['surface_tile_px']}")
        else:
            self._log(f"[GRID] WARNING : {grid['error']}")

    def _log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        # Supprimer les caracteres speciaux non-ASCII pour compatibilite Windows
        safe_msg = message.encode('ascii', errors='replace').decode('ascii')
        line = f"[{ts}] {safe_msg}"
        _session["session_log"].append(line)
        log_path = self._get_log_path()
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _get_log_path(self) -> Path | None:
        p = _session.get("current_project_path")
        if p:
            log_dir = Path(p) / "outputs" / "logs"
        else:
            log_dir = _GLOBAL_LOGS_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d")
        return log_dir / f"session_{ts}.log"


# ── Lancement ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    api = Api()
    _init_first_launch()

    # Fichier d'entrée : accueil animé
    accueil_path = WEB_DIR / "accueil_preview.html"
    if not accueil_path.exists():
        # Fallback sur navigation si accueil absent
        accueil_path = WEB_DIR / "navigation_preview.html"

    window = webview.create_window(
        title="Map Generator Pro v8.0.1",
        url=accueil_path.as_uri(),
        js_api=api,
        min_size=(900, 600),
        resizable=True,
        frameless=False,
    )

    def _maximize():
        import time
        time.sleep(0.3)
        try:
            window.maximize()
        except Exception:
            pass

    import threading
    threading.Thread(target=_maximize, daemon=True).start()

    webview.start(debug=False)
