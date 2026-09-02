"""
Map Generator Pro — Project Manager
Gestion des projets : créer, ouvrir, sauvegarder, importer/exporter.

Arborescence d'un projet :
  data/projects/<NomProjet>/
      project.json
      sources/          ← heightmap, satmap, masque protection (ne jamais écraser)
      generated/        ← rendus intermédiaires
      masks/
          global/       ← masques map entière
          tiles/        ← masques par tuile
      reports/          ← json analyse, airfields, anchors
      snapshots/        ← états UI sauvegardés
"""

import json
import os
import re
import shutil
import zipfile
import io
from datetime import datetime
from pathlib import Path

# Dossier racine des projets
PROJECTS_ROOT = Path("data/projects")

# Version courante du format project.json
PROJECT_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _safe_name(name: str) -> str:
    """Transforme un nom libre en nom de dossier sûr."""
    return re.sub(r'[^\w\-\. ]', '_', name).strip().replace(' ', '_')


def project_dir(name: str) -> Path:
    return PROJECTS_ROOT / _safe_name(name)


def project_json_path(name: str) -> Path:
    return project_dir(name) / "project.json"


# ---------------------------------------------------------------------------
# Création d'un projet
# ---------------------------------------------------------------------------

def create_project(name: str, author: str = "", description: str = "") -> dict:
    """
    Crée l'arborescence d'un nouveau projet et retourne le dict projet.
    Lève FileExistsError si le projet existe déjà.
    """
    pdir = project_dir(name)
    if pdir.exists():
        raise FileExistsError(f"Un projet '{name}' existe déjà.")

    for sub in ["sources", "generated", "masks/global", "masks/tiles", "reports", "snapshots"]:
        (pdir / sub).mkdir(parents=True, exist_ok=True)

    project = _empty_project(name, author, description)
    _write_json(project_json_path(name), project)
    return project


def _empty_project(name: str, author: str = "", description: str = "") -> dict:
    return {
        "version": PROJECT_VERSION,
        "created_at": _now(),
        "updated_at": _now(),

        "project": {
            "name": name,
            "author": author,
            "description": description,
            "tags": [],
        },

        "assets": {
            "heightmap": {
                "filename": "",
                "format": "",
                "cellsize": 10.0,
                "width": 0,
                "height": 0,
                "alt_min": 0.0,
                "alt_max": 1000.0,
            },
            "satmap": {
                "filename": "",
                "width": 0,
                "height": 0,
            },
            "protection_mask": {
                "filename": "",
                "inverted": False,
                "softness_px": 0,
            },
        },

        "reforger_grid": {
            "planar_resolution_m": 4.0,
            "tile_size_m": 512,
            "tile_size_px": 512,
            "tiles_x": 32,
            "tiles_y": 32,
            "blocks_per_tile_x": 4,
            "blocks_per_tile_y": 4,
            "block_size_m": 128,
            "surface_map_total_px": [16257, 16257],
            "tile_origin": "bottom_left",
        },

        "modules": {
            "hypsometric": {
                "add_hillshade": True,
                "hillshade_strength": 0.35,
                "last_output": "",
            },
            "naturemap": {
                "last_output": "",
            },
            "terrain_preview": {
                "climate_profile": "tempere",
                "snow_percentile": 95,
                "flow_percentile": 85,
                "mode": "morpho",
                "sat_strength": 0.0,
                "last_output": "",
            },
            "masks": {
                "profile": "europe_temperee",
                "enforce_blocks": True,
                "dynamic_budget": True,
                "mode": "morpho",
                "sat_strength": 0.35,
                "last_outputs": {
                    "global": "",
                    "last_tile": {"x": 0, "y": 0, "n": 0},
                    "last_block": {"tile_x": 0, "tile_y": 0, "bx": 0, "by": 0},
                },
            },
            "urban_analysis": {
                "num_seeds": 20,
                "last_output": "",
                "seeds_file": "",
            },
            "airfield_analysis": {
                "mode": "voronoi",
                "last_output": "",
                "report_file": "",
            },
        },

        "snapshots": [],
    }


# ---------------------------------------------------------------------------
# Lecture / écriture
# ---------------------------------------------------------------------------

def load_project(name: str) -> dict:
    """Charge et retourne le project.json. Lève FileNotFoundError si absent."""
    path = project_json_path(name)
    if not path.exists():
        raise FileNotFoundError(f"Projet '{name}' introuvable.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_project(project: dict) -> None:
    """Écrit le project.json en mettant à jour updated_at."""
    project["updated_at"] = _now()
    name = project["project"]["name"]
    _write_json(project_json_path(name), project)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Liste des projets existants
# ---------------------------------------------------------------------------

def list_projects() -> list[dict]:
    """
    Retourne la liste des projets disponibles, triés par date de modification
    décroissante.
    Chaque entrée : {"name", "author", "updated_at", "path"}
    """
    projects = []
    if not PROJECTS_ROOT.exists():
        return projects

    for pdir in sorted(PROJECTS_ROOT.iterdir()):
        pjson = pdir / "project.json"
        if not pjson.exists():
            continue
        try:
            with open(pjson, "r", encoding="utf-8") as f:
                data = json.load(f)
            projects.append({
                "name": data["project"]["name"],
                "author": data["project"].get("author", ""),
                "updated_at": data.get("updated_at", ""),
                "description": data["project"].get("description", ""),
                "path": str(pdir),
            })
        except Exception:
            continue

    projects.sort(key=lambda x: x["updated_at"], reverse=True)
    return projects


# ---------------------------------------------------------------------------
# Chemins utilitaires
# ---------------------------------------------------------------------------

def sources_dir(project: dict) -> Path:
    return project_dir(project["project"]["name"]) / "sources"


def generated_dir(project: dict) -> Path:
    return project_dir(project["project"]["name"]) / "generated"


def masks_global_dir(project: dict) -> Path:
    return project_dir(project["project"]["name"]) / "masks" / "global"


def masks_tile_dir(project: dict, tx: int, ty: int) -> Path:
    return project_dir(project["project"]["name"]) / "masks" / "tiles" / f"tile_{tx}_{ty}"


def masks_block_dir(project: dict, tx: int, ty: int, bx: int, by: int) -> Path:
    return masks_tile_dir(project, tx, ty) / f"block_{bx}_{by}"


def reports_dir(project: dict) -> Path:
    return project_dir(project["project"]["name"]) / "reports"


def snapshots_dir(project: dict) -> Path:
    return project_dir(project["project"]["name"]) / "snapshots"


def source_path(project: dict, filename: str) -> Path:
    return sources_dir(project) / filename


def output_path(project: dict, filename: str) -> Path:
    d = generated_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    return d / filename


# ---------------------------------------------------------------------------
# Sauvegarder un asset source
# ---------------------------------------------------------------------------

def save_source_file(project: dict, file_bytes: bytes, filename: str) -> Path:
    """
    Copie les bytes d'un fichier source (heightmap, satmap…) dans sources/.
    Retourne le chemin absolu.
    """
    sdir = sources_dir(project)
    sdir.mkdir(parents=True, exist_ok=True)
    dest = sdir / filename
    with open(dest, "wb") as f:
        f.write(file_bytes)
    return dest


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def save_snapshot(project: dict, label: str, modules_state: dict) -> dict:
    """
    Crée un snapshot de l'état des modules.
    Ajoute l'entrée dans project["snapshots"] et écrit le fichier d'état.
    """
    snap_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    snap_file = snapshots_dir(project) / f"{snap_id}.json"
    snap_file.parent.mkdir(parents=True, exist_ok=True)

    with open(snap_file, "w", encoding="utf-8") as f:
        json.dump(modules_state, f, indent=2, ensure_ascii=False)

    entry = {
        "id": snap_id,
        "label": label,
        "date": _now(),
        "modules_state": str(snap_file.relative_to(project_dir(project["project"]["name"]))),
    }
    project["snapshots"].append(entry)
    save_project(project)
    return entry


def load_snapshot(project: dict, snap_id: str) -> dict:
    """Charge et retourne l'état d'un snapshot."""
    pdir = project_dir(project["project"]["name"])
    for entry in project.get("snapshots", []):
        if entry["id"] == snap_id:
            snap_file = pdir / entry["modules_state"]
            with open(snap_file, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"Snapshot '{snap_id}' introuvable.")


# ---------------------------------------------------------------------------
# Import / Export ZIP
# ---------------------------------------------------------------------------

def export_project_zip(project: dict) -> bytes:
    """
    Compresse le dossier projet entier dans un ZIP en mémoire.
    Retourne les bytes du ZIP.
    """
    pdir = project_dir(project["project"]["name"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in pdir.rglob("*"):
            if fpath.is_file():
                arcname = fpath.relative_to(pdir.parent)
                zf.write(fpath, arcname)
    buf.seek(0)
    return buf.getvalue()


def import_project_zip(zip_bytes: bytes, overwrite: bool = False) -> str:
    """
    Extrait un ZIP de projet dans PROJECTS_ROOT.
    Retourne le nom du projet importé.
    Lève FileExistsError si le projet existe déjà et overwrite=False.
    """
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        # Détecter le nom du projet depuis le premier dossier dans le ZIP
        top_dirs = {Path(n).parts[0] for n in zf.namelist() if "/" in n}
        if not top_dirs:
            raise ValueError("ZIP invalide : aucun dossier projet détecté.")
        project_folder = top_dirs.pop()
        dest = PROJECTS_ROOT / project_folder
        if dest.exists() and not overwrite:
            raise FileExistsError(f"Un projet '{project_folder}' existe déjà.")
        zf.extractall(PROJECTS_ROOT)
    # Lire le nom réel depuis project.json
    candidate_json = dest / "project.json"
    if candidate_json.exists():
        with open(candidate_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["project"]["name"]
    return project_folder


# ---------------------------------------------------------------------------
# Parser copier-coller Workbench Reforger
# ---------------------------------------------------------------------------

def parse_reforger_workbench_paste(text: str) -> dict:
    """
    Parse un bloc de texte collé depuis Reforger Workbench (format libre).
    Extrait les valeurs clés de la section Surface Map et de la heightmap.
    Retourne un dict partiel compatible avec project["reforger_grid"].

    Format attendu (ex):
        Planar resolution: 4 m
        Blocks per tile: 4 x 4
        Tiles: 32 x 32
        Tile resolution: 512 x 512 px   ← on prend celui de Surface Map
        Total: 16257 x 16257 px         ← idem
        Block: 33 x 33 vertices ...
        Tile: 129 x 129 vertices ...
    """
    result = {}
    # Nettoyage robuste du texte collé depuis le presse-papiers Windows/Reforger
    cleaned_text = (
        text
        .replace('\r\n', '\n')
        .replace('\r', '\n')
        .replace('\u00A0', ' ')   # nbsp
        .replace('\u2007', ' ')   # figure space
        .replace('\u202F', ' ')   # narrow nbsp
        .replace('\u200B', '')    # zero-width space
        .replace('\uFEFF', '')    # bom/zw no-break space
    )
    lines = cleaned_text.split('\n')

    # Normaliser le texte collé : Reforger met souvent la clé et la valeur
    # sur 2 lignes séparées (ex: "Tiles:" puis "64 x 64").
    def _normalize_lines(src_lines):
        norm = []
        i = 0
        while i < len(src_lines):
            cur = re.sub(r'\s+', ' ', src_lines[i]).strip()
            if not cur:
                i += 1
                continue
            if cur.endswith(':') and i + 1 < len(src_lines):
                nxt = re.sub(r'\s+', ' ', src_lines[i + 1]).strip()
                if nxt and not nxt.endswith(':'):
                    norm.append(f"{cur} {nxt}")
                    i += 2
                    continue
            norm.append(cur)
            i += 1
        return norm

    lines_norm = _normalize_lines(lines)

    # On repère les sections pour différencier Satellite / Surface / Normal
    surface_map_idx = None
    normal_map_idx = None
    for i, line in enumerate(lines_norm):
        stripped = line.strip().lower()
        if 'surface map' in stripped:
            surface_map_idx = i
        elif 'normal map' in stripped and surface_map_idx is not None:
            normal_map_idx = i
            break

    # Sous-ensemble lignes Surface Map (si délimité)
    surface_lines = lines_norm
    if surface_map_idx is not None:
        end = normal_map_idx if normal_map_idx is not None else len(lines_norm)
        surface_lines = lines_norm[surface_map_idx:end]

    def _first_match(pattern, search_lines, cast=float):
        for ln in search_lines:
            m = re.search(pattern, ln, re.IGNORECASE)
            if m:
                try:
                    return cast(m.group(1))
                except (ValueError, IndexError):
                    pass
        return None

    def _first_2int(pattern, search_lines):
        for ln in search_lines:
            m = re.search(pattern, ln, re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1)), int(m.group(2))
                except (ValueError, IndexError):
                    pass
        return None

    # --- Hauteur / résolution depuis toutes les lignes ---
    planar = _first_match(r'planar resolution[:\s]+(\d+(?:\.\d+)?)\s*m', lines_norm)
    if planar is not None:
        result["planar_resolution_m"] = planar

    tiles = _first_2int(r'tiles[:\s]+(\d+)\s*[xX×]\s*(\d+)', lines_norm)
    if tiles:
        result["tiles_x"] = tiles[0]
        result["tiles_y"] = tiles[1]

    blocks_per_tile = _first_2int(r'blocks per tile[:\s]+(\d+)\s*[xX×]\s*(\d+)', lines_norm)
    if blocks_per_tile:
        result["blocks_per_tile_x"] = blocks_per_tile[0]
        result["blocks_per_tile_y"] = blocks_per_tile[1]

    # --- Depuis Surface Map ---
    tile_res = _first_2int(r'tile resolution[:\s]+(\d+)\s*[xX×]\s*(\d+)\s*px', surface_lines)
    if tile_res:
        result["tile_size_px"] = tile_res[0]

    total_px = _first_2int(r'total[:\s]+(\d+)\s*[xX×]\s*(\d+)\s*px', surface_lines)
    if total_px:
        result["surface_map_total_px"] = list(total_px)

    surface_res = _first_match(r'resolution[:\s]+(\d+(?:\.\d+)?)\s*m', surface_lines)
    if surface_res is not None:
        result["surface_map_resolution_m"] = surface_res

    # Déduire tile_size_m si possible
    if "planar_resolution_m" in result and "tile_size_px" in result:
        result["tile_size_m"] = int(result["planar_resolution_m"] * result["tile_size_px"])

    # Déduire block_size_m
    if "tile_size_m" in result and "blocks_per_tile_x" in result:
        result["block_size_m"] = result["tile_size_m"] // result["blocks_per_tile_x"]

    result["tile_origin"] = "bottom_left"

    return result


# ---------------------------------------------------------------------------
# Conversion coordonnées tuile
# (origine bas-gauche, numérotation ligne par ligne vers le haut)
# ---------------------------------------------------------------------------

def tile_n_to_xy(n: int, ntx: int, nty: int) -> tuple[int, int]:
    """
    Numéro de tuile → (col, ligne) avec origine bas-gauche.
    n=0 → (0, 0) → bas-gauche.
    """
    col = n % ntx
    row_from_bottom = n // ntx
    return col, row_from_bottom


def tile_xy_to_n(col: int, row_from_bottom: int, ntx: int) -> int:
    """(col, ligne depuis bas) → numéro de tuile."""
    return row_from_bottom * ntx + col


def tile_xy_to_image_row(row_from_bottom: int, nty: int) -> int:
    """
    Convertit une ligne bottom-left en ligne image (top=0).
    """
    return (nty - 1) - row_from_bottom


def tile_pixel_bounds(col: int, row_from_bottom: int, tile_px: int,
                      img_w: int, img_h: int, nty: int) -> tuple[int, int, int, int]:
    """
    Retourne (x0, y0, x1, y1) en coordonnées image (y0 depuis le haut).
    """
    img_row = tile_xy_to_image_row(row_from_bottom, nty)
    x0 = col * tile_px
    y0 = img_row * tile_px
    x1 = min(x0 + tile_px, img_w)
    y1 = min(y0 + tile_px, img_h)
    return x0, y0, x1, y1
