# -*- coding: utf-8 -*-
"""
Map Generator Pro v7.0 — PyWebView Launcher
Remplace app.py Streamlit par une fenêtre native desktop.

Lancement : python main.py
"""

import webview
import json
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime

# Force le chemin pour trouver les modules locaux
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ── Constantes ────────────────────────────────────────────────────────────────
# Chemin absolu basé sur l'emplacement de main.py
_APP_DIR = Path(__file__).parent
PROJECTS_DIR = _APP_DIR / "data" / "projects"
PROJECT_VERSION = "1.2"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

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
        """Change l'onglet actif — charge la page dans un thread pour éviter le callback JS error."""
        import threading
        _session["active_tab"] = tab
        tab_map = {
            "heightmap":   "terrain.html",
            "terrain":     "inspection.html",
            "pipeline_v5": "generation.html",
            "satmap":      "satmap.html",
        }
        html_file = tab_map.get(tab, "navigation_preview.html")
        html_path = Path(__file__).parent / html_file
        window = webview.windows[0] if webview.windows else None
        if window and html_path.exists():
            def _load():
                try:
                    window.load_url(html_path.as_uri())
                except Exception:
                    pass
            threading.Timer(0.1, _load).start()
        # Pas de return — PyWebView ne doit pas sérialiser de valeur de retour

    def go_navigation(self):
        """Charge la page navigation."""
        import threading
        html_path = Path(__file__).parent / "navigation_preview.html"
        window = webview.windows[0] if webview.windows else None
        if window and html_path.exists():
            threading.Timer(0.05, lambda: window.load_url(html_path.as_uri())).start()

    def go_projects(self):
        """Charge la page de gestion des projets (depuis accueil)."""
        import threading
        html_path = Path(__file__).parent / "projects.html"
        window = webview.windows[0] if webview.windows else None
        if window and html_path.exists():
            threading.Timer(0.05, lambda: window.load_url(html_path.as_uri())).start()

    def go_accueil(self):
        """Retourne à la page d'accueil animée."""
        import threading
        html_path = Path(__file__).parent / "accueil_preview.html"
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
        file_types = tuple(f"*.{e}" for e in extensions) if extensions else ("*.*",)
        files = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
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
            sys.path.append(str(Path(__file__).parent))
            from hypsometric_colormap import HypsometricColormapGenerator
            proj = Path(_session["current_project_path"])
            # Chercher la heightmap
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            hm_rel = data.get("paths", {}).get("heightmap", "")
            if not hm_rel:
                return {"ok": False, "error": "Heightmap non configurée"}
            hm_path = proj / hm_rel
            if not hm_path.exists():
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
            data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
            addon_path = data.get("paths", {}).get("addon_reforger", "")
            if not addon_path:
                return {"ok": False, "error": "Chemin addon Reforger non configuré (onglet Terrain → Chemins)"}
            # Chercher le dossier .Data
            from pathlib import Path as _P
            terrain_dir = None
            for root, dirs, files in __import__('os').walk(addon_path):
                for f in files:
                    if f.endswith(".terr"):
                        terrain_dir = _P(root)
                        break
                if terrain_dir:
                    break
            if not terrain_dir:
                # Fallback : data_dir depuis paths
                data_dir_path = data.get("paths", {}).get("data_dir", "")
                if data_dir_path:
                    terrain_dir = _P(data_dir_path).parent
            if not terrain_dir:
                return {"ok": False, "error": "Dossier terrain introuvable dans addon_reforger"}
            data_dir = terrain_dir / ".Data"
            if not data_dir.exists():
                return {"ok": False, "error": f"Dossier .Data introuvable : {data_dir}"}
            cache_dir = proj / "outputs" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_json = cache_dir / "qtre_scan.json"
            tile_inspector = Path(__file__).parent / "tile_inspector.py"
            if not tile_inspector.exists():
                tile_inspector = Path(__file__).parent / "scripts" / "tile_inspector.py"
            if not tile_inspector.exists():
                return {"ok": False, "error": "tile_inspector.py introuvable"}
            import subprocess, os as _os
            result = subprocess.run(
                [sys.executable, str(tile_inspector),
                 "--tiles-dir", str(data_dir),
                 "--export-json", str(cache_json)],
                capture_output=True,
                encoding="utf-8", errors="replace",
                env={**_os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                timeout=300
            )
            log = (result.stdout + result.stderr)[-3000:]
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
            import base64, subprocess, os as _os
            proj = Path(_session["current_project_path"])
            clean_weights = Path(__file__).parent / "clean_weights.py"
            if not clean_weights.exists():
                clean_weights = Path(__file__).parent / "scripts" / "clean_weights.py"
            if not clean_weights.exists():
                return {"ok": False, "error": "clean_weights.py introuvable"}
            result = subprocess.run(
                [sys.executable, str(clean_weights), "--inspect", f"{tx},{ty}"],
                capture_output=True,
                encoding="utf-8", errors="replace",
                env={**_os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                timeout=120,
                cwd=str(Path(__file__).parent)
            )
            log = (result.stdout + result.stderr)[-2000:]
            # Chercher l'image générée
            dest_dir = proj / "outputs" / "generated" / "tiles"
            dest_dir.mkdir(parents=True, exist_ok=True)
            img_name = f"tile_{tx}_{ty}_cleanup.png"
            # Chercher dans plusieurs endroits
            candidates = [
                Path(__file__).parent.parent / img_name,
                Path(__file__).parent / img_name,
                Path("H:/logiciel perso") / img_name,
            ]
            img_b64 = None
            for c in candidates:
                if c.exists():
                    import shutil as _sh
                    dest = dest_dir / img_name
                    _sh.copy2(c, dest)
                    img_b64 = base64.b64encode(c.read_bytes()).decode()
                    break
            self._log(f"[INSPECTION] Inspect tuile ({tx},{ty})")
            return {"ok": True, "log": log, "img_b64": img_b64}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Interne ───────────────────────────────────────────────────────────────

    def _load_project_internal(self, path: str, data: dict):
        _session["current_project_path"] = path
        _session["current_project"] = data

    def _log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        _session["session_log"].append(line)
        log_path = self._get_log_path()
        if log_path:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _get_log_path(self) -> Path | None:
        p = _session.get("current_project_path")
        if not p:
            return None
        log_dir = Path(p) / "outputs" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d")
        return log_dir / f"session_{ts}.log"


# ── Lancement ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    api = Api()

    # Fichier d'entrée : accueil animé
    accueil_path = Path(__file__).parent / "accueil_preview.html"
    if not accueil_path.exists():
        # Fallback sur navigation si accueil absent
        accueil_path = Path(__file__).parent / "navigation_preview.html"

    window = webview.create_window(
        title="Map Generator Pro v7.0",
        url=accueil_path.as_uri(),
        js_api=api,
        width=1280,
        height=800,
        min_size=(900, 600),
        resizable=True,
        frameless=False,
    )

    webview.start(debug=False)
