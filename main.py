# -*- coding: utf-8 -*-
"""
Map Generator Pro v7.0 — PyWebView Launcher
Remplace app.py Streamlit par une fenêtre native desktop.

Lancement : python main.py
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
_RUNTIME_DIR = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
# Forcer le cwd vers le dossier de l'exe pour que les DLL soient trouvées
os.chdir(str(_RUNTIME_DIR))
sys.path.append(str(_RUNTIME_DIR))

# ── Constantes ────────────────────────────────────────────────────────────────
# Compatibilité PyInstaller (exe) et développement (script)
if getattr(sys, 'frozen', False):
    _APP_DIR = Path(sys._MEIPASS)
    # Données utilisateur dans Documents/MapGeneratorPro/
    _USER_DIR = Path.home() / "Documents" / "MapGeneratorPro"
else:
    _APP_DIR = Path(__file__).parent
    _USER_DIR = _APP_DIR  # En dev, tout reste dans le dossier du projet

WEB_DIR = _APP_DIR / "web"
PROJECTS_DIR = _USER_DIR / "data" / "projects"
_FIRST_LAUNCH = not PROJECTS_DIR.exists()
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
# Logs globaux
_GLOBAL_LOGS_DIR = _USER_DIR / "logs"
_GLOBAL_LOGS_DIR.mkdir(parents=True, exist_ok=True)
# Config utilisateur
_USER_CONFIG = _USER_DIR / "config.json"
PROJECT_VERSION = "1.2"

# ── Session state simplifié (dict Python) ────────────────────────────────────
_session = {
    "current_project_path": None,
    "current_project": None,
    "active_tab": None,
    "session_log": [],
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
                "assets": {
                    "heightmap": {"filename": "", "format": "", "cellsize": 1.0, "width": 0, "height": 0, "alt_min": 0.0, "alt_max": 0.0},
                    "satmap": {"filename": "", "width": 0, "height": 0},
                },
                "reforger_grid": {},
                "terr_project_path": "",
                "paths": {
                    "heightmap": "inputs/heightmap/",
                    "satmap": "inputs/satmap/",
                    "exclusion_mask": "inputs/masks/",
                    "gaea_flow": "inputs/gaea/",
                    "gaea_deposit": "inputs/gaea/",
                    "exports_mask": "outputs/masks/latest/",
                    "addon_reforger": "",
                    "catalog_json": "",
                    "satmap_v2": "outputs/generated/satmap_v2_textured_4097.png",
                    "data_dir": ""
                },
                "modules": {
                    "terrain_preview": {"climate_profile": "tempere", "snow_percentile": 95, "flow_percentile": 85},
                },
                "snapshots": [],
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
            "terrain":      "inspection.html",
            "pipeline_v5":  "generation.html",
            "satmap":       "satmap.html",
            "corrections":  "corrections.html",
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
        import threading
        result = {"ok": False}
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
            data.setdefault("paths", {})[key] = folder_path
            data["updated_at"] = datetime.now().isoformat(timespec="seconds")
            (proj / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
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
            slope = d.get("slope", None)
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

    def gen_hypsometric(self, hillshade: bool = False, enrichment: bool = False) -> dict:
        """Génère la colormap hypsométrique et retourne le chemin."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            sys.path.append(str(_APP_DIR))
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
        """Parse le texte copié depuis Workbench pour extraire grid_w, num_blk, cell_size."""
        import re
        try:
            self._log("[GENERATION] Analyse info Workbench...")

            # Tiles: \n32 x 32
            m_grid = re.search(r'Tiles:\s*\n\s*(\d+)\s*x\s*(\d+)', text)
            # Blocks per tile: \n4 x 4
            m_blk  = re.search(r'Blocks per tile:\s*\n\s*(\d+)\s*x\s*(\d+)', text)
            # Planar resolution: \n4 m
            m_cell = re.search(r'Planar resolution:\s*\n\s*([0-9.]+)\s*m', text)

            if not m_grid:
                self._log("[GENERATION] ERREUR : 'Tiles:' non trouvé dans le texte")
                return {"ok": False, "error": "Tiles non trouvé — coller le texte complet depuis Workbench"}

            grid_w    = int(m_grid.group(1))
            num_blk   = int(m_blk.group(1))  if m_blk  else 4
            cell_size = float(m_cell.group(1)) if m_cell else 2.0

            # Sauvegarder dans le projet courant
            if _session["current_project_path"]:
                proj_path = Path(_session["current_project_path"])
                data = json.loads((proj_path / "project.json").read_text(encoding="utf-8"))
                data["grid_w"]    = grid_w
                data["num_blk"]   = num_blk
                data["cell_size"] = cell_size
                data["updated_at"] = datetime.now().isoformat(timespec="seconds")
                (proj_path / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                # Mettre à jour la session
                _session["current_project"] = data

            self._log(f"[GENERATION] Grille OK : {grid_w}×{grid_w} tiles | {num_blk} blk/tile | {cell_size} m/cell")
            return {"ok": True, "grid_w": grid_w, "num_blk": num_blk, "cell_size": cell_size}

        except Exception as e:
            self._log(f"[GENERATION] ERREUR parse_workbench_info : {e}")
            return {"ok": False, "error": str(e)}

    # ── Inspection ───────────────────────────────────────────────────────────────

    def get_qtre_cache(self) -> dict:
        """Retourne le cache QTRE scan (qtre_scan.json)."""
        if not _session["current_project_path"]:
            return {"ok": False}
        try:
            proj = Path(_session["current_project_path"])
            cache = proj / "outputs" / "cache" / "qtre_scan.json"
            if not cache.exists():
                return {"ok": False, "reason": "no_cache"}
            data = json.loads(cache.read_text(encoding="utf-8"))
            return {"ok": True, "tiles": data.get("tiles", []), "generated_at": data.get("generated_at", "")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_satmap_b64(self) -> dict:
        """Retourne la satmap fond encodée en base64 pour la grille QTRE."""
        if not _session["current_project_path"]:
            return {"ok": False}
        try:
            import base64
            proj = Path(_session["current_project_path"])
            # Chercher satmap_fond_512.png ou satmap dans inputs/
            candidates = [
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
                "generated_at": data.get("generated_at", "")[:19]
            }
        except Exception:
            return {"has_cache": False}

    def delete_scan_cache(self) -> dict:
        """Supprime le cache QTRE pour forcer un nouveau scan."""
        if not _session["current_project_path"]:
            return {"ok": False}
        try:
            proj = Path(_session["current_project_path"])
            cache = proj / "outputs" / "cache" / "qtre_scan.json"
            if cache.exists():
                cache.unlink()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def scan_tiles(self) -> dict:
        """Lance tile_inspector.py pour scanner toutes les tuiles .ttile."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            proj = Path(_session["current_project_path"])
            dirs = self._get_terrain_dirs()
            if not dirs.get("ok"):
                return {"ok": False, "error": dirs.get("error", "Dossier terrain introuvable")}
            data_dir = dirs["data_dir"]
            if not data_dir.exists():
                return {"ok": False, "error": f"Dossier .Data introuvable : {data_dir}"}
            cache_dir = proj / "outputs" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_json = cache_dir / "qtre_scan.json"

            if getattr(sys, 'frozen', False):
                # Mode exe — appel direct
                import io, contextlib
                sys.path.append(str(_APP_DIR))
                from tile_inspector import export_json
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    export_json(data_dir, cache_json)
                log = buf.getvalue()[-3000:]
                scan_data = json.loads(cache_json.read_text(encoding="utf-8")) if cache_json.exists() else {}
                n = len(scan_data.get("tiles", []))
                self._log(f"[INSPECTION] Scan terminé : {n} tuiles")
                return {"ok": True, "n_tiles": n, "log": log}
            else:
                # Mode dev — subprocess
                tile_inspector = _APP_DIR / "tile_inspector.py"
                if not tile_inspector.exists():
                    tile_inspector = _APP_DIR / "scripts" / "tile_inspector.py"
                if not tile_inspector.exists():
                    return {"ok": False, "error": "tile_inspector.py introuvable"}
                import subprocess, os as _os
                result = subprocess.run(
                    [sys.executable, str(tile_inspector),
                     "--tiles-dir", str(data_dir),
                     "--export-json", str(cache_json)],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    env={**_os.environ, "PYTHONIOENCODING": "utf-8"},
                    timeout=300
                )
                log = ((result.stdout or '') + (result.stderr or ''))[-3000:]
                if result.returncode == 0:
                    scan_data = json.loads(cache_json.read_text(encoding="utf-8")) if cache_json.exists() else {}
                    n = len(scan_data.get("tiles", []))
                    self._log(f"[INSPECTION] Scan terminé : {n} tuiles")
                    return {"ok": True, "n_tiles": n, "log": log}
                else:
                    return {"ok": False, "error": "Erreur scan", "log": log}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def inspect_tile(self, tx: int, ty: int) -> dict:
        """Lance clean_weights.py --inspect tx,ty et retourne l'image en base64."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            import base64
            proj = Path(_session["current_project_path"])
            dest_dir = proj / "outputs" / "generated" / "tiles"
            dest_dir.mkdir(parents=True, exist_ok=True)
            img_name = f"tile_{tx}_{ty}_cleanup.png"

            if getattr(sys, 'frozen', False):
                # Mode exe — appel direct
                import io, contextlib
                sys.path.append(str(_APP_DIR))
                from clean_weights import mode_inspect
                dirs = self._get_terrain_dirs()
                if not dirs["ok"]:
                    return {"ok": False, "error": dirs["error"]}
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    mode_inspect(tx, ty, dirs["data_dir"], dirs["editor_dir"], dirs["surfaces"], threshold=0.01, output_dir=dest_dir)
                log = buf.getvalue()[-2000:]
            else:
                # Mode dev — subprocess
                import subprocess, os as _os
                clean_weights = _APP_DIR / "clean_weights.py"
                if not clean_weights.exists():
                    clean_weights = _APP_DIR / "scripts" / "clean_weights.py"
                if not clean_weights.exists():
                    return {"ok": False, "error": "clean_weights.py introuvable"}
                result = subprocess.run(
                    [sys.executable, str(clean_weights), "--inspect", f"{tx},{ty}"],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    env={**_os.environ, "PYTHONIOENCODING": "utf-8"},
                    timeout=120,
                    cwd=str(_APP_DIR)
                )
                log = ((result.stdout or '') + (result.stderr or ''))[-2000:]

            # Chercher l'image générée
            candidates = [
                dest_dir / img_name,
                _APP_DIR.parent / img_name,
                _APP_DIR / img_name,
                Path("H:/logiciel perso") / img_name,
            ]
            img_b64 = None
            for c in candidates:
                if c.exists():
                    import shutil as _sh
                    dest = dest_dir / img_name
                    if c != dest:
                        _sh.copy2(c, dest)
                    img_b64 = base64.b64encode(dest.read_bytes()).decode()
                    break
            self._log(f"[INSPECTION] Inspect tuile ({tx},{ty})")
            return {"ok": True, "log": log, "img_b64": img_b64}
        except Exception as e:
            return {"ok": False, "error": str(e)}


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
            sys.path.append(str(_APP_DIR))
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
            biomes_path = _APP_DIR / "data" / "Textures_ArmaReforger" / "biomes_presets.json"
            if biomes_path.exists():
                biomes = json.loads(biomes_path.read_text(encoding="utf-8"))
            # Params
            params = data.get("pipeline_v5", {}).get("params", {})
            cal = data.get("pipeline_calibration", {}).get("values", {})
            params.update(cal)
            return {
                "ok": True,
                "textures": textures,
                "mask_config": mask_config,
                "biomes": {k: {"label": v.get("label",""), "description": v.get("description",""), "custom_warning": v.get("custom_warning",[])} for k,v in biomes.items()},
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
            biomes_path = _APP_DIR / "data" / "Textures_ArmaReforger" / "biomes_presets.json"
            if not biomes_path.exists():
                return {"ok": False, "error": "biomes_presets.json introuvable"}
            biomes = json.loads(biomes_path.read_text(encoding="utf-8"))
            preset = biomes.get(biome_key)
            if not preset:
                return {"ok": False, "error": f"Biome inconnu : {biome_key}"}
            proj = Path(_session["current_project_path"])
            # Appliquer textures → project_mask_config.json
            sys.path.append(str(_APP_DIR))
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
            sys.path.append(str(_APP_DIR))
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
            sys.path.append(str(_APP_DIR))
            import pipeline_v5 as pv5
            cfg = {}
            for i, (name, _, _) in enumerate(pv5.DEFAULT_MASK_CONFIG):
                short = name.replace("mask_", "")
                row = next((r for r in mask_config if r.get("Masque") == short), None)
                if row:
                    cfg[name] = row.get("Texture", "default")
            mc_data = {"mask_config": cfg, "default_mat": default_mat, "updated": datetime.now().isoformat()}
            (proj / "project_mask_config.json").write_text(json.dumps(mc_data, indent=2, ensure_ascii=False), encoding="utf-8")
            self._log(f"[GENERATION] Mapping masques sauvegarde")
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
            self._log(f"[GENERATION] Parametres pipeline sauvegardes")
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
            sys.path.append(str(_APP_DIR))
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
                def_mat = mc_data.get("default_mat", "default")
            else:
                cfg_dict = {}
                def_mat = default_mat
            # Charger surfaces
            surfaces_json = proj / "surfaces.json"
            mat_id_map = {}
            if surfaces_json.exists():
                s = json.loads(surfaces_json.read_text(encoding="utf-8"))
                mat_id_map = s.get("materials", {})
            mask_cfg = []
            for name, def_tex, color in pv5.DEFAULT_MASK_CONFIG:
                tex = cfg_dict.get(name, def_tex)
                mat_id = mat_id_map.get(tex, 0)
                mask_cfg.append((name, mat_id, color))
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
            reforger_grid = data.get("reforger_grid", {})
            tiles_list = reforger_grid.get("tiles", [32, 32])
            grid_w = tiles_list[0] if isinstance(tiles_list, list) else 32
            blk_list = reforger_grid.get("blocks_per_tile", [4, 4])
            num_blk = blk_list[0] if isinstance(blk_list, list) else 4
            import io, contextlib

            # Capturer stdout du pipeline
            stdout_capture = io.StringIO()
            with contextlib.redirect_stdout(stdout_capture):
                result = pv5.run_pipeline(
                    asc_path=Path(asc_path),
                    output_dir=output_dir,
                    exclusion_path=Path(excl) if excl else None,
                    gaea_flow=Path(flow) if flow else None,
                    gaea_deposit=Path(deposit) if deposit else None,
                    mask_config=mask_cfg,
                    calibration=calibration,
                    grid_w=grid_w,
                    num_blk=num_blk,
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


    # ── Satmap ───────────────────────────────────────────────────────────────────

    def check_satmap_catalog(self) -> dict:
        """Vérifie le catalog.json et résout les chemins terrain."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            paths = data.get("paths", {})
            catalog_str = paths.get("catalog_json", "")
            catalog_path = proj / catalog_str if catalog_str and not Path(catalog_str).is_absolute() else Path(catalog_str) if catalog_str else None
            if not catalog_path or not catalog_path.exists():
                return {"ok": False, "error": "catalog.json introuvable — configurez-le dans Terrain > Chemins"}
            cat = json.loads(catalog_path.read_text(encoding="utf-8"))
            n_entries = len(cat)
            # Résoudre terrain_dir depuis addon_reforger
            addon = paths.get("addon_reforger", "")
            terrain_dir = ""
            terrain_ok = False
            if addon:
                sys.path.append(str(_APP_DIR))
                try:
                    from app_config import resolve_paths
                    rp = resolve_paths(addon)
                    if rp.get("valid"):
                        terrain_dir = rp.get("terrain_dir", "")
                        terrain_ok = bool(terrain_dir and Path(terrain_dir).exists())
                except Exception:
                    pass
            # Textures manquantes
            surfaces_json = proj / "surfaces.json"
            missing = []
            if surfaces_json.exists():
                s = json.loads(surfaces_json.read_text(encoding="utf-8"))
                mats = list(s.get("materials", {}).keys())
                for m in mats:
                    if m not in cat and m + ".emat" not in cat and m != "default":
                        missing.append(m)
            return {
                "ok": True,
                "catalog_name": catalog_path.name,
                "n_entries": n_entries,
                "terrain_dir": terrain_dir,
                "terrain_ok": terrain_ok,
                "missing": missing[:20],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def scan_emat(self) -> dict:
        """Scanne les fichiers .emat et enrichit catalog.json."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            catalog_str = data.get("paths", {}).get("catalog_json", "")
            catalog_path = Path(catalog_str) if Path(catalog_str).is_absolute() else proj / catalog_str
            if not catalog_path.exists():
                return {"ok": False, "error": "catalog.json introuvable"}
            sys.path.append(str(_APP_DIR))
            from emat_scanner_simple import scan_emat_directory
            emat_dir = catalog_path.parent / "emat"
            if not emat_dir.exists():
                return {"ok": False, "error": f"Dossier emat introuvable : {emat_dir}"}
            result = scan_emat_directory(emat_dir, catalog_path)
            self._log(f"[SATMAP] Scan .emat : {result['updated_count']} surfaces enrichies")
            return {"ok": True, "updated": result["updated_count"], "warnings": result.get("warnings", [])}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def generate_satmap_v2(self, resolution: int, middles_dir_str: str) -> dict:
        """Lance la génération Satmap v2.0 (mode texturé)."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        try:
            import base64, io
            from PIL import Image
            proj = Path(_session["current_project_path"])
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            paths = data.get("paths", {})
            catalog_str = paths.get("catalog_json", "")
            catalog_path = Path(catalog_str) if Path(catalog_str).is_absolute() else proj / catalog_str
            if not catalog_path.exists():
                return {"ok": False, "error": "catalog.json introuvable"}
            addon = paths.get("addon_reforger", "")
            if not addon:
                return {"ok": False, "error": "Chemin addon_reforger non configure"}
            sys.path.append(str(_APP_DIR))
            from app_config import resolve_paths
            rp = resolve_paths(addon)
            if not rp.get("valid"):
                return {"ok": False, "error": f"Addon invalide : {rp.get('error')}"}
            terrain_dir = Path(rp["terrain_dir"])
            terr_file = rp.get("terr_file")
            # Sortie
            output_dir = proj / "outputs" / "generated"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"satmap_v2_textured_{resolution}.png"
            # middles_dir
            middles_dir = None
            if middles_dir_str:
                p = Path(middles_dir_str)
                if not p.is_absolute():
                    p = _APP_DIR / middles_dir_str
                if p.exists():
                    middles_dir = p
            # Générer
            from satmap_v2_textured import generate_satmap_v2_textured_complete
            stats = generate_satmap_v2_textured_complete(
                terrain_dir, catalog_path, output_path,
                terr_file=terr_file, mode="textured",
                target_resolution=resolution, verbose=True,
                middles_dir=middles_dir
            )
            if not output_path.exists():
                return {"ok": False, "error": "Fichier non généré"}
            # Thumbnail base64
            img = Image.open(str(output_path))
            img.thumbnail((800, 800), Image.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            img_b64 = base64.b64encode(buf.getvalue()).decode()
            self._log(f"[SATMAP] Satmap v2.0 generee : {output_path.name}")
            return {
                "ok": True,
                "filename": output_path.name,
                "output_path": str(output_path),
                "img_b64": img_b64,
                "ext": "jpeg",
                "stats": {
                    "size": f"{resolution}x{resolution}",
                    "missing_layers": stats.get("missing_layers", 0) if stats else 0,
                    "material_issues": stats.get("material_issues", 0) if stats else 0,
                }
            }
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc()[-800:]}

    def run_kmeans_classifier(self, satmap_path: str | None, n_clusters: int, reuse: bool):
        """Lance le classificateur K-means dans un thread — fire and forget, résultat via get_classifier_result()."""
        import threading
        _session["classifier_result"] = None  # reset
        def _run():
            if not _session["current_project_path"]:
                _session["classifier_result"] = {"ok": False, "error": "Aucun projet ouvert"}
                return
            try:
                import subprocess as _sub, os as _os
                proj = Path(_session["current_project_path"])
                masks_out_dir = proj / "outputs" / "satmap" / "masks_classifier"
                classif_json = proj / "outputs" / "satmap" / "classification.json"
                masks_out_dir.mkdir(parents=True, exist_ok=True)
                sat_path_str = str(Path(satmap_path)) if satmap_path else None

                if getattr(sys, 'frozen', False):
                    # Mode exe — appel direct
                    import io, contextlib
                    sys.path.append(str(_APP_DIR))
                    from satmap_classifier import run_classification
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        run_classification(
                            input_path=sat_path_str,
                            output_dir=str(masks_out_dir),
                            n_clusters=n_clusters,
                            classif_json=str(classif_json) if reuse else None,
                            save_classif_json=str(classif_json),
                            interactive=False
                        )
                    masks = [f.name for f in Path(masks_out_dir).glob('*.png')]
                    data = {"ok": True, "n_masks": len(masks), "masks": masks[:30]}
                    _session["classifier_result"] = data
                    self._log(f"[SATMAP] Classification terminee : {data.get('n_masks', 0)} masks → {masks_out_dir}")
                else:
                    # Mode dev — subprocess existant
                    script = f"""
import sys
sys.path.insert(0, r'{str(_APP_DIR)}')
# Bloquer les imports Streamlit avant tout
import unittest.mock as _mock
sys.modules['streamlit'] = _mock.MagicMock()
sys.modules['streamlit.runtime'] = _mock.MagicMock()
import satmap_classifier as sc
import importlib; importlib.reload(sc)
result = sc.run_classification(
    input_path=r'{sat_path_str}' if {bool(sat_path_str)} else None,
    output_dir=r'{masks_out_dir}',
    n_clusters={n_clusters},
    classif_json=r'{classif_json}' if {reuse} else None,
    save_classif_json=r'{classif_json}',
    interactive=False
)
import json, pathlib
masks = [f.name for f in pathlib.Path(r'{masks_out_dir}').glob('*.png')]
print(json.dumps({{"ok": True, "n_masks": len(masks), "masks": masks[:30]}}))
"""
                    result = _sub.run(
                        [sys.executable, "-c", script],
                        capture_output=True, encoding="utf-8", errors="replace",
                        env={**_os.environ, "PYTHONIOENCODING": "utf-8"},
                        timeout=300
                    )
                    if result.returncode == 0:
                        import json as _json
                        lines = [l for l in result.stdout.strip().splitlines() if l.startswith('{')]
                        if lines:
                            data = _json.loads(lines[-1])
                            _session["classifier_result"] = data
                            self._log(f"[SATMAP] Classification terminee : {data.get('n_masks', 0)} masks → {masks_out_dir}")
                        else:
                            _session["classifier_result"] = {"ok": False, "error": "Pas de sortie JSON", "log": result.stdout[-500:]}
                    else:
                        _session["classifier_result"] = {"ok": False, "error": "Erreur subprocess", "log": result.stderr[-800:]}
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                self._log(f"[SATMAP] ERREUR classificateur : {e}")
                print(f"[SATMAP CLASSIFIER ERROR]\n{tb}")
                _session["classifier_result"] = {"ok": False, "error": str(e), "log": tb[-800:]}
        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def get_classifier_result(self) -> dict:
        """Récupère le résultat du classificateur stocké dans _session."""
        result = _session.get("classifier_result", {"ok": False, "error": "Aucun résultat"})
        _session["classifier_result"] = None  # Clear après lecture
        return result

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

    # ── Corrections ──────────────────────────────────────────────────────────────

    def _get_terrain_dirs(self) -> dict:
        """Retourne les dossiers terrain (.Data, .EditorData) et surfaces depuis le projet."""
        if not _session["current_project_path"]:
            return {"ok": False, "error": "Aucun projet ouvert"}
        proj = Path(_session["current_project_path"])
        data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
        addon = data.get("paths", {}).get("addon_reforger", "")
        if not addon:
            return {"ok": False, "error": "Chemin addon_reforger non configure"}
        sys.path.append(str(_APP_DIR))
        from app_config import resolve_paths
        rp = resolve_paths(addon)
        if not rp.get("valid"):
            return {"ok": False, "error": f"Addon invalide : {rp.get('error')}"}
        terrain_dir = Path(rp["terrain_dir"])
        surfaces = []
        surfaces_json = proj / "surfaces.json"
        if surfaces_json.exists():
            s = json.loads(surfaces_json.read_text(encoding="utf-8"))
            mats = s.get("materials", {})
            # surfaces comme List[str] indexée par mat_id, compatible clean_weights.py
            mat_id_to_name = {int(v): k for k, v in mats.items()}
            max_id = max(mat_id_to_name.keys()) if mat_id_to_name else 0
            surfaces = [mat_id_to_name.get(i, f"MAT_{i}") for i in range(max_id + 1)]
        return {
            "ok": True,
            "terrain_dir": terrain_dir,
            "data_dir": terrain_dir / ".Data",
            "editor_dir": terrain_dir / ".EditorData",
            "surfaces": surfaces,
            "terr_file": rp.get("terr_file"),
        }

    def corrections_scan_global(self, threshold: float) -> dict:
        """Scan global de tous les blocs — détecte les slots à couverture négligeable."""
        try:
            dirs = self._get_terrain_dirs()
            if not dirs["ok"]:
                return {"ok": False, "error": dirs["error"]}

            if getattr(sys, 'frozen', False):
                # Mode exe — appel direct
                import io, contextlib
                sys.path.append(str(_APP_DIR))
                from clean_weights import mode_scan
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    mode_scan(dirs["data_dir"], dirs["editor_dir"], threshold)
                log = buf.getvalue()
                self._log(f"[CORRECTIONS] Scan global termine")
                return {"ok": True, "log": log[-3000:]}
            else:
                # Mode dev — subprocess
                import subprocess, os as _os
                clean_weights = _APP_DIR / "clean_weights.py"
                if not clean_weights.exists():
                    clean_weights = _APP_DIR / "scripts" / "clean_weights.py"
                if not clean_weights.exists():
                    return {"ok": False, "error": "clean_weights.py introuvable"}
                result = subprocess.run(
                    [sys.executable, str(clean_weights), "--scan", str(threshold)],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    env={**_os.environ, "PYTHONIOENCODING": "utf-8"},
                    timeout=300,
                    cwd=str(_APP_DIR)
                )
                log = ((result.stdout or '') + (result.stderr or ''))[-3000:]
                self._log(f"[CORRECTIONS] Scan global termine")
                return {"ok": True, "log": log}
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "log": traceback.format_exc()[-800:]}

    def corrections_scan_zone(self, mask_path: str) -> dict:
        """Scan par zone définie par un masque PNG."""
        try:
            dirs = self._get_terrain_dirs()
            if not dirs["ok"]:
                return {"ok": False, "error": dirs["error"]}
            mask = Path(mask_path)
            if not mask.exists():
                return {"ok": False, "error": f"Masque introuvable : {mask_path}"}

            if getattr(sys, 'frozen', False):
                # Mode exe — appel direct
                import io, contextlib
                sys.path.append(str(_APP_DIR))
                from clean_weights import mode_scan_zone
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    mode_scan_zone(mask, dirs["data_dir"], dirs["editor_dir"], dirs["surfaces"])
                log = buf.getvalue()
                self._log(f"[CORRECTIONS] Scan zone termine : {mask.name}")
                return {"ok": True, "log": log[-3000:]}
            else:
                # Mode dev — subprocess
                import subprocess, os as _os
                clean_weights = _APP_DIR / "clean_weights.py"
                if not clean_weights.exists():
                    clean_weights = _APP_DIR / "scripts" / "clean_weights.py"
                if not clean_weights.exists():
                    return {"ok": False, "error": "clean_weights.py introuvable"}
                result = subprocess.run(
                    [sys.executable, str(clean_weights), "--scan-zone", str(mask)],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    env={**_os.environ, "PYTHONIOENCODING": "utf-8"},
                    timeout=300,
                    cwd=str(_APP_DIR)
                )
                log = ((result.stdout or '') + (result.stderr or ''))[-3000:]
                self._log(f"[CORRECTIONS] Scan zone termine : {mask.name}")
                return {"ok": True, "log": log}
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "log": traceback.format_exc()[-800:]}

    def corrections_inspect_tile(self, tx: int, ty: int, mode: str) -> dict:
        """Inspection d'une tuile par coordonnées."""
        try:
            dirs = self._get_terrain_dirs()
            if not dirs["ok"]:
                return {"ok": False, "error": dirs["error"]}
            proj = Path(_session["current_project_path"])
            out_dir = proj / "outputs" / "inspection"
            out_dir.mkdir(parents=True, exist_ok=True)

            if getattr(sys, 'frozen', False):
                # Mode exe — appel direct
                import io, contextlib
                sys.path.append(str(_APP_DIR))
                from clean_weights import mode_inspect, mode_weights, mode_validate
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    if mode == "inspect":
                        mode_inspect(tx, ty, dirs["data_dir"], dirs["editor_dir"], dirs["surfaces"], threshold=0.01, output_dir=out_dir)
                    elif mode == "weights":
                        mode_weights(tx, ty, dirs["data_dir"], dirs["editor_dir"], dirs["surfaces"], output_dir=out_dir)
                    else:
                        mode_validate(tx, ty, dirs["data_dir"], dirs["editor_dir"], dirs["surfaces"])
                log = buf.getvalue()
            else:
                # Mode dev — subprocess
                import subprocess, os as _os
                clean_weights = _APP_DIR / "clean_weights.py"
                if not clean_weights.exists():
                    clean_weights = _APP_DIR / "scripts" / "clean_weights.py"
                if not clean_weights.exists():
                    return {"ok": False, "error": "clean_weights.py introuvable"}
                cmd_args = [sys.executable, str(clean_weights)]
                if mode == "inspect":
                    cmd_args.extend(["--inspect", f"{tx},{ty}"])
                elif mode == "weights":
                    cmd_args.extend(["--weights", f"{tx},{ty}"])
                else:
                    cmd_args.extend(["--validate", f"{tx},{ty}"])
                result = subprocess.run(
                    cmd_args,
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    env={**_os.environ, "PYTHONIOENCODING": "utf-8"},
                    timeout=120,
                    cwd=str(_APP_DIR)
                )
                log = ((result.stdout or '') + (result.stderr or ''))[-3000:]

            # Déplacer l'image générée vers outputs/generated/tiles/ du projet
            import shutil as _sh
            dest_dir = proj / "outputs" / "generated" / "tiles"
            dest_dir.mkdir(parents=True, exist_ok=True)
            img_name = f"tile_{tx}_{ty}_cleanup.png"
            candidates = [
                out_dir / img_name,
                _APP_DIR / img_name,
                _APP_DIR.parent / img_name,
                Path("H:/logiciel perso") / img_name,
                Path("H:/logiciel perso/Map generator") / img_name,
            ]
            for c in candidates:
                if c.exists():
                    _sh.move(str(c), str(dest_dir / img_name))
                    log += f"\n[OK] Image deplacee vers {dest_dir / img_name}"
                    break
            self._log(f"[CORRECTIONS] Inspect ({tx},{ty}) mode={mode}")
            return {"ok": True, "log": log[-3000:]}
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "log": traceback.format_exc()[-800:]}

    def corrections_terrain_health(self) -> dict:
        """Analyse de santé globale du terrain."""
        try:
            dirs = self._get_terrain_dirs()
            if not dirs["ok"]:
                return {"ok": False, "error": dirs["error"]}
            data_dir = dirs["data_dir"]
            editor_dir = dirs["editor_dir"]
            if not data_dir.exists():
                return {"ok": False, "error": f"Dossier .Data introuvable : {data_dir}"}
            # Analyse simple : compter les tuiles, détecter les anomalies
            import struct
            ttiles = list(data_dir.glob("Terrain_*.ttile"))
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
                log_lines.append(f"  (Analyse limitee aux 100 premieres tuiles)")
            # Vérifier .EditorData
            if editor_dir.exists():
                edds = list(editor_dir.glob("*.edds"))
                log_lines.append(f"[SANTE] {len(edds)} fichiers .edds dans .EditorData")
            else:
                log_lines.append(f"[SANTE] WARN : .EditorData absent")
                n_warn += 1
            log = chr(10).join(log_lines)
            self._log(f"[CORRECTIONS] Sante terrain : {n_ok} OK / {n_warn} warn / {n_err} err")
            return {"ok": True, "n_tiles": n_tiles, "n_ok": n_ok, "n_warn": n_warn, "n_err": n_err, "log": log}
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "log": traceback.format_exc()[-800:]}

    def corrections_file_inventory(self) -> dict:
        """Inventaire complet des fichiers .ttile et .edds attendus vs présents."""
        try:
            dirs = self._get_terrain_dirs()
            if not dirs["ok"]:
                return {"ok": False, "error": dirs["error"]}
            # Lire la grille depuis project.json
            proj = Path(_session["current_project_path"])
            pdata = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            grid = pdata.get("reforger_grid", {})
            tiles_list = grid.get("tiles", [32, 32])
            grid_w = tiles_list[0] if isinstance(tiles_list, list) else 32
            data_dir = dirs["data_dir"]
            editor_dir = dirs["editor_dir"]
            if not data_dir.exists():
                return {"ok": False, "error": f"Dossier .Data introuvable : {data_dir}"}
            # .ttile attendus : Terrain_0.ttile … Terrain_{grid_w*grid_w - 1}.ttile
            n_expected = grid_w * grid_w
            present_ttile = set()
            for f in data_dir.glob("Terrain_*.ttile"):
                try:
                    n = int(f.stem.replace("Terrain_", ""))
                    present_ttile.add(n)
                except ValueError:
                    pass
            missing = [f"Terrain_{i}.ttile" for i in range(n_expected) if i not in present_ttile]
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
            self._log(f"[CORRECTIONS] Inventaire : {len(missing)} .ttile manquants")
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

    def _load_project_internal(self, path: str, data: dict):
        _session["current_project_path"] = path
        _session["current_project"] = data

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

    # Fichier d'entrée : accueil animé
    accueil_path = WEB_DIR / "accueil_preview.html"
    if not accueil_path.exists():
        # Fallback sur navigation si accueil absent
        accueil_path = WEB_DIR / "navigation_preview.html"

    window = webview.create_window(
        title="Map Generator Pro v7.0",
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
