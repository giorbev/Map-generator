"""
Map Generator Pro v3.0 — Streamlit Application
Interface complète de génération de cartes topographiques
"""

import streamlit as st
import numpy as np
from PIL import Image
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Force le chemin pour que Python trouve les modules locaux
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Imports modules métier
from base_map import BaseMap
from hypsometric_colormap import HypsometricColormapGenerator
from texture_layer_generator import TextureLayerGenerator

# ============================================================================
# CONFIGURATION STREAMLIT
# ============================================================================

st.set_page_config(
    page_title="Map Generator Pro v3.0",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personnalisé
st.markdown("""
<style>
    .main-header {font-size: 2em; font-weight: bold; color: #1f77b4;}
    .section-header {font-size: 1.3em; font-weight: bold; color: #2ca02c; margin-top: 1em;}
    .info-box {background-color: #e8f4f8; padding: 1em; border-radius: 5px; margin: 0.5em 0;}
    .success-box {background-color: #e8f5e9; padding: 1em; border-radius: 5px; margin: 0.5em 0;}
</style>
""", unsafe_allow_html=True)

# ============================================================================
# GESTION DE PROJETS
# ============================================================================

PROJECTS_DIR = Path("data/projects")
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_VERSION = "1.1"

def list_projects() -> list[dict]:
    """Retourne la liste des projets triés par date de modification (récents en premier)."""
    projects = []
    for p in PROJECTS_DIR.iterdir():
        json_file = p / "project.json"
        if p.is_dir() and json_file.exists():
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                projects.append({
                    "path": str(p),
                    "name": data["project"]["name"],
                    "description": data["project"].get("description", ""),
                    "updated_at": data.get("updated_at", ""),
                    "heightmap": data.get("assets", {}).get("heightmap", {}).get("filename", ""),
                })
            except Exception:
                pass
    return sorted(projects, key=lambda x: x["updated_at"], reverse=True)


def create_project(name: str, author: str, description: str) -> Path:
    """Crée la structure d'un nouveau projet et retourne son chemin."""
    slug = name.strip().replace(" ", "_")
    project_dir = PROJECTS_DIR / slug
    for sub in ["sources", "generated", "masks", "snapshots", "reports"]:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

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
        "modules": {
            "terrain_preview": {"climate_profile": "tempere", "snow_percentile": 95, "flow_percentile": 85},
        },
        "snapshots": [],
    }
    (project_dir / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return project_dir


def load_project(project_path: str):
    """Charge un projet dans le session state."""
    p = Path(project_path)
    data = json.loads((p / "project.json").read_text(encoding="utf-8"))

    st.session_state.current_project_path = str(p)
    st.session_state.current_project      = data

    # Heightmap
    hm_filename = data.get("assets", {}).get("heightmap", {}).get("filename", "")
    hm_path = p / "sources" / hm_filename if hm_filename else None
    if hm_path and hm_path.exists():
        st.session_state.heightmap_path = str(hm_path)
        try:
            bm = BaseMap(str(hm_path))
            st.session_state.base_map = bm
            # Patch les métadonnées avec les vraies valeurs du fichier
            data["assets"]["heightmap"].update({
                "alt_min":  float(bm.altitude_min),
                "alt_max":  float(bm.altitude_max),
                "width":    int(bm.width),
                "height":   int(bm.height),
            })
            # Synchronise reforger_grid avec les vraies altitudes
            if st.session_state.reforger_data:
                st.session_state.reforger_data["height_min_m"] = float(bm.altitude_min)
                st.session_state.reforger_data["height_max_m"] = float(bm.altitude_max)
            st.session_state.current_project = data
            (p / "project.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            st.session_state.base_map = None
    else:
        st.session_state.heightmap_path = None
        st.session_state.base_map = None

    # Satmap
    sat_filename = data.get("assets", {}).get("satmap", {}).get("filename", "")
    sat_path = p / "sources" / sat_filename if sat_filename else None
    st.session_state.satmap_path = str(sat_path) if sat_path and sat_path.exists() else None

    # Masques Instant Terra (slope_rock, slope_transition, curvature, sediment)
    _it_cfg = data.get("assets", {}).get("it_masks", {})
    # Mise à jour différée : on ne peut pas modifier les clés de widget après leur instanciation.
    # On écrit dans _pending_widget_it_* ; le haut du script les transfère avant la création des widgets.
    for _role in ("slopes", "curvature", "sediment"):
        st.session_state[f"_pending_widget_it_{_role}"] = _it_cfg.get(_role, "")
    _it_loaded: dict = {}
    if _it_cfg:
        try:
            from reforger_texture_budget import load_it_mask as _load_it
            _hm_shape = (
                data.get("assets", {}).get("heightmap", {}).get("height", 0),
                data.get("assets", {}).get("heightmap", {}).get("width",  0),
            )
            for _role, _rel in _it_cfg.items():
                _abs = p / _rel if not Path(_rel).is_absolute() else Path(_rel)
                if _abs.exists() and _hm_shape[0] > 0:
                    _it_loaded[_role] = _load_it(str(_abs), _hm_shape)
        except Exception as _e:
            st.warning(f"IT masks : chargement partiel ({_e})")
    st.session_state.it_masks = _it_loaded if _it_loaded else None

    # Données Reforger — enrichies avec les altitudes de assets.heightmap
    rd = data.get("reforger_grid", {})
    if rd:
        hm_meta = data.get("assets", {}).get("heightmap", {})
        rd.setdefault("height_min_m", hm_meta.get("alt_min", 0.0))
        rd.setdefault("height_max_m", hm_meta.get("alt_max", 1000.0))

        # ── Migration ancien format → nouveau ────────────────────────────────
        # Ancien format : tiles_x/tiles_y/blocks_per_tile_x/blocks_per_tile_y (ints séparés)
        # Nouveau format : tiles/(int,int), blocks_per_tile/(int,int), block_size_m/(int,int)
        if "tiles" not in rd and "tiles_x" in rd:
            rd["tiles"] = (int(rd["tiles_x"]), int(rd["tiles_y"]))
        if "blocks_per_tile" not in rd and "blocks_per_tile_x" in rd:
            rd["blocks_per_tile"] = (int(rd["blocks_per_tile_x"]), int(rd["blocks_per_tile_y"]))

        # Recalculer tile_size_m et block_size_m depuis la structure réelle si le
        # format est ancien (les anciennes valeurs étaient souvent 4× trop grandes).
        hm_w   = hm_meta.get("width",  0)
        cell_m = float(rd.get("planar_resolution_m", 1.0))

        tiles_ref = rd.get("tiles", (rd.get("tiles_x", 1), rd.get("tiles_y", 1)))
        bpt_ref   = rd.get("blocks_per_tile", (rd.get("blocks_per_tile_x", 1), rd.get("blocks_per_tile_y", 1)))
        ntx       = int(tiles_ref[0])
        btx       = ntx * int(bpt_ref[0])

        if hm_w > 1:
            usable_px = hm_w - 1  # heightmap Reforger = N+1 vertices pour N cellules

            tsm = rd.get("tile_size_m")
            if isinstance(tsm, (int, float)) and ntx > 0 and "tiles_x" in rd:
                correct_tsm = int(round((usable_px / ntx) * cell_m))
                if correct_tsm > 0 and correct_tsm != int(tsm):
                    rd["tile_size_m"] = (correct_tsm, correct_tsm)

            bsm = rd.get("block_size_m", 32)
            if isinstance(bsm, (int, float)) and btx > 0 and "tiles_x" in rd:
                correct_bsm = int(round((usable_px / btx) * cell_m))
                if correct_bsm > 0 and correct_bsm != int(bsm):
                    rd["block_size_m"] = (correct_bsm, correct_bsm)

    st.session_state.reforger_data = rd if rd else None

    # Projet .terr
    st.session_state.terr_project_path = data.get("terr_project_path", "")
    # Delete the widget key so it re-reads value= on the next rerun.
    # Setting it directly raises StreamlitAPIException if the widget is already rendered.
    if "terr_project_input" in st.session_state:
        del st.session_state["terr_project_input"]
    st.session_state.terr_materials = []

    # Modules
    mods = data.get("modules", {})
    tp   = mods.get("terrain_preview", {})
    if tp.get("climate_profile"):
        st.session_state.biome_cfg_profile = tp["climate_profile"]

    # Aperçu Texture — restauration des clés widget
    for _wk, _pk, _def in [
        ("tex_climate",          "climate_profile",  "tempere"),
        ("tex_max_slots",        "max_slots",        4),
        ("tex_snow",             "snow_pct",         92),
        ("tex_flow",             "flow_pct",         88),
        ("tex_coastal",          "coastal_dist_m",   60),
        ("tex_snowline",         "snowline_pct",     0.75),
        ("tex_sat_str",          "sat_strength",     0.35),
    ]:
        if _pk in tp:
            st.session_state[_wk] = tp[_pk]
    if tp.get("biome_cfg"):
        st.session_state.biome_cfg_data = tp["biome_cfg"]

    # Végétation
    _veg = mods.get("vegetation", {})
    for _wk, _pk, _def in [
        ("veg_blend",       "blend",       True),
        ("veg_min_score",   "min_score",   0.15),
        ("veg_res",         "resolution",  1024),
        ("veg_use_lock",    "use_lock",    False),
        ("veg_lock_folder", "lock_folder", ""),
    ]:
        st.session_state[_wk] = _veg.get(_pk, _def)

    # Fusion
    _fus = mods.get("fusion", {})
    for _wk, _pk, _def in [
        ("fusion2_folder",     "folder",     ""),
        ("fusion2_lock_seuil", "lock_seuil", 0.05),
        ("fusion2_out_bits",   "out_bits",   "16-bit"),
    ]:
        st.session_state[_wk] = _fus.get(_pk, _def)

    # Reconstruction
    _recon = mods.get("reconstruction", {})
    st.session_state["recon_folder"] = _recon.get("folder", "")
    st.session_state["recon_res"]    = _recon.get("resolution", 2048)

    # ── Bibliothèque de matériaux ────────────────────────────────────────────
    _lib = load_merged_library(str(p))
    st.session_state.material_library = _lib
    from reforger_texture_budget import set_runtime_library
    set_runtime_library(_lib["materials"], _lib["roles"])


def save_project():
    """Sauvegarde l'état courant dans project.json."""
    p = Path(st.session_state.current_project_path)
    data = st.session_state.current_project.copy()

    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    # Lire depuis la clé widget en priorité (le bouton save est rendu avant le
    # champ texte, donc la sync terr_project_path n'a pas encore eu lieu).
    data["terr_project_path"] = st.session_state.get(
        "terr_project_input", st.session_state.get("terr_project_path", "")
    )

    # Heightmap
    bm = st.session_state.get("base_map")
    if bm:
        hm_path = Path(st.session_state.heightmap_path)
        dest = p / "sources" / hm_path.name
        if not dest.exists():
            import shutil
            shutil.copy2(str(hm_path), str(dest))
        data["assets"]["heightmap"] = {
            "filename": hm_path.name,
            "format": hm_path.suffix.lstrip("."),
            "cellsize": float(getattr(bm, "cellsize", 1.0)),
            "width": int(bm.width),
            "height": int(bm.height),
            "alt_min": float(bm.altitude_min),
            "alt_max": float(bm.altitude_max),
        }

    # Reforger grid
    if st.session_state.get("reforger_data"):
        data["reforger_grid"] = st.session_state.reforger_data

    # Modules
    data.setdefault("modules", {})
    data["modules"]["terrain_preview"] = {
        "climate_profile":  st.session_state.get("tex_climate",
                                st.session_state.get("biome_cfg_profile", "tempere")),
        "max_slots":        st.session_state.get("tex_max_slots",        4),
        "snow_pct":         st.session_state.get("tex_snow",             92),
        "flow_pct":         st.session_state.get("tex_flow",             88),
        "coastal_dist_m":   st.session_state.get("tex_coastal",          60),
        "snowline_pct":     st.session_state.get("tex_snowline",         0.75),
        "sat_strength":     st.session_state.get("tex_sat_str",          0.35),
        "biome_cfg":        st.session_state.get("biome_cfg_data",       {}),
    }
    data["modules"]["vegetation"] = {
        "blend":       st.session_state.get("veg_blend",       True),
        "min_score":   st.session_state.get("veg_min_score",   0.15),
        "resolution":  st.session_state.get("veg_res",         1024),
        "use_lock":    st.session_state.get("veg_use_lock",    False),
        "lock_folder": st.session_state.get("veg_lock_folder", ""),
    }
    data["modules"]["fusion"] = {
        "folder":     st.session_state.get("fusion2_folder",     ""),
        "lock_seuil": st.session_state.get("fusion2_lock_seuil", 0.05),
        "out_bits":   st.session_state.get("fusion2_out_bits",   "16-bit"),
    }
    data["modules"]["reconstruction"] = {
        "folder":     st.session_state.get("recon_folder", ""),
        "resolution": st.session_state.get("recon_res",    2048),
    }

    # Masques Instant Terra — chemins sauvegardés comme relatifs si possible
    _it_paths = {}
    for _role in ("slopes", "curvature", "sediment"):
        _path_str = st.session_state.get(f"it_path_{_role}", "").strip()
        if _path_str:
            _abs_it = Path(_path_str)
            try:
                _rel_it = _abs_it.relative_to(p)
                _it_paths[_role] = str(_rel_it).replace("\\", "/")
            except ValueError:
                _it_paths[_role] = str(_abs_it).replace("\\", "/")
    data["assets"]["it_masks"] = _it_paths

    st.session_state.current_project = data
    (p / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ============================================================================
# SESSION STATE MANAGEMENT
# ============================================================================

def initialize_session():
    """Initialise les variables de session."""
    if 'current_project_path' not in st.session_state:
        st.session_state.current_project_path = None
    if 'current_project' not in st.session_state:
        st.session_state.current_project = None
    if 'heightmap_path' not in st.session_state:
        st.session_state.heightmap_path = None
    if 'base_map' not in st.session_state:
        st.session_state.base_map = None
    if 'satmap_path' not in st.session_state:
        st.session_state.satmap_path = None
    if 'last_generated' not in st.session_state:
        st.session_state.last_generated = {}
    if 'reforger_data' not in st.session_state:
        st.session_state.reforger_data = None
    if 'biome_cfg_profile' not in st.session_state:
        st.session_state.biome_cfg_profile = None
    if 'biome_cfg_data' not in st.session_state:
        st.session_state.biome_cfg_data = {}
    if 'tex_reforger' not in st.session_state:
        st.session_state.tex_reforger = None
    if 'terr_project_path' not in st.session_state:
        st.session_state.terr_project_path = ""
    if 'terr_materials' not in st.session_state:
        st.session_state.terr_materials = []

initialize_session()

# Applique les chemins IT en attente (définis par load_project) AVANT que les widgets soient créés.
# Streamlit interdit de modifier une clé de widget après son instanciation dans le même run ;
# load_project() écrit donc dans _pending_widget_it_*, et on les transfère ici.
_IT_ROLES_KEYS = ("slopes", "curvature", "sediment")
for _r in _IT_ROLES_KEYS:
    _pk = f"_pending_widget_it_{_r}"
    if _pk in st.session_state:
        st.session_state[f"_widget_it_{_r}"] = st.session_state.pop(_pk)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_output_dir():
    """Retourne le dossier output du projet courant, ou 'output/' local si aucun projet chargé."""
    proj = st.session_state.get("current_project_path")
    output_dir = str(Path(proj) / "output") if proj else "output"
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

def load_image(path):
    """Charge une image en mémoire complète (force le chargement des pixels)."""
    try:
        img = Image.open(path)
        img.load()   # force full decode — évite les problèmes de file handle fermé
        return img
    except Exception as e:
        st.error(f"❌ Erreur chargement image: {e}")
        return None

def get_file_size_mb(path):
    """Retourne la taille d'un fichier en MB."""
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except:
        return 0

def format_timestamp():
    """Retourne un timestamp formaté."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


_VANILLA_LIB_PATH = Path("data/material_library_vanilla.json")


def load_merged_library(project_path: str | None = None) -> dict:
    """
    Charge et fusionne la bibliothèque vanilla (globale) et custom (projet).

    Règles de fusion :
    - Roles   : union vanilla + custom (custom complète, pas de doublon sur id)
    - Materials: union vanilla + custom ; même stem → custom remplace vanilla
    - L'ordre de la liste materials est respecté (custom en tête pour mat_to_role)

    Retourne un dict {"roles": [...], "materials": [...]} prêt pour
    set_runtime_library().
    """
    def _read(path):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return {"roles": [], "materials": []}

    van  = _read(_VANILLA_LIB_PATH)
    cust = {"roles": [], "materials": []}
    if project_path:
        cust_path = Path(project_path) / "material_library_custom.json"
        cust = _read(cust_path)

    # Fusion rôles : vanilla base + custom ajoute les nouveaux
    van_role_ids  = {r["id"] for r in van.get("roles", [])}
    merged_roles  = list(van.get("roles", []))
    for r in cust.get("roles", []):
        if r["id"] not in van_role_ids:
            merged_roles.append(r)

    # Fusion matériaux : custom en tête, stems custom écrasent vanilla
    cust_stems    = {m["stem"] for m in cust.get("materials", [])}
    van_mats_kept = [m for m in van.get("materials", []) if m["stem"] not in cust_stems]
    merged_mats   = list(cust.get("materials", [])) + van_mats_kept

    return {"roles": merged_roles, "materials": merged_mats}


def save_custom_library(project_path: str, roles: list, materials: list) -> None:
    """Sauvegarde la bibliothèque custom du projet."""
    data = {
        "version": "1.0",
        "comment": "Bibliothèque custom du projet — complémentaire à vanilla.",
        "roles":     roles,
        "materials": materials,
    }
    path = Path(project_path) / "material_library_custom.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def save_vanilla_library(roles: list, materials: list) -> None:
    """Sauvegarde la bibliothèque vanilla globale."""
    data = {
        "version": "1.0",
        "comment": "Bibliothèque globale Reforger vanilla — partagée entre tous les projets.",
        "roles":     roles,
        "materials": materials,
    }
    _VANILLA_LIB_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _build_tmat_legend_image(rgb_array: np.ndarray, rows: list) -> bytes:
    """Compose image TMAT + panneau légende latéral → bytes PNG."""
    import io
    from PIL import Image, ImageDraw, ImageFont

    H, W   = rgb_array.shape[:2]
    leg_w  = 300
    row_h  = 26
    pad    = 14
    leg_h  = max(H, len(rows) * row_h + pad * 2 + 32)

    canvas = Image.new("RGB", (W + leg_w, max(H, leg_h)), (28, 28, 28))
    canvas.paste(Image.fromarray(rgb_array), (0, 0))

    draw = ImageDraw.Draw(canvas)
    try:
        font_t = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 13)
        font   = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 12)
    except Exception:
        font_t = font = ImageFont.load_default()

    x0 = W + pad
    y  = pad
    draw.text((x0, y), "Matériaux TMAT", fill=(230, 230, 230), font=font_t)
    y += 32

    for row in rows:
        hx = row["Couleur"]
        r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
        draw.rectangle([x0, y + 4, x0 + 16, y + 20], fill=(r, g, b), outline=(180, 180, 180))
        name = row["Matériau (.emat)"]
        if len(name) > 24:
            name = name[:22] + "…"
        draw.text((x0 + 22, y + 4), f"{name}  {row['Couverture %']}%",
                  fill=(210, 210, 210), font=font)
        y += row_h
        if y + row_h > leg_h - pad:
            draw.text((x0, y), "…", fill=(150, 150, 150), font=font)
            break

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def parse_reforger_world_data(text: str) -> dict:
    """
    Parse le copier-coller des données World Composition de Reforger/Enfusion.

    Retourne un dict avec les champs extraits, ou lève ValueError si
    le texte ne ressemble pas au format attendu.
    """
    import re

    SECTION_HEADERS = {
        "Blocks and Tiles": "blocks",
        "Height Map:":       "heightmap",
        "Satellite Texture:": "satellite",
        "Surface Map:":      "surface",
        "Normal Map:":       "normal",
    }

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("Texte vide")

    result: dict = {}
    section: str | None = None

    def _dims(s):
        m = re.match(r"(\d+)\s*[xX×]\s*(\d+)", s)
        return (int(m.group(1)), int(m.group(2))) if m else None

    def _px_dims(s):
        m = re.match(r"(\d+)\s*[xX×]\s*(\d+)\s*px", s)
        return (int(m.group(1)), int(m.group(2))) if m else None

    def _vertex_dims(s):
        m = re.match(r"(\d+)\s*[xX×]\s*(\d+)\s*vertices?\s*\((\d+)\s*[xX×]\s*(\d+)\s*m2\)", s)
        if m:
            return (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))
        return None, None

    def _float_m(s):
        m = re.match(r"([\d.]+)\s*m\b", s)
        return float(m.group(1)) if m else None

    def _float_cm(s):
        m = re.match(r"([\d.]+)\s*cm\b", s)
        return float(m.group(1)) if m else None

    def _int_first(s):
        m = re.match(r"(\d+)", s)
        return int(m.group(1)) if m else None

    def _apply(key, value):
        nonlocal section
        # Section-agnostic keys
        if key == "Tiles":
            d = _dims(value)
            if d: result["tiles"] = d
        elif key == "Blocks per tile":
            d = _dims(value)
            if d: result["blocks_per_tile"] = d
        elif key == "Blocks total":
            d = _dims(value)
            if d: result["blocks_total"] = d
        elif key == "Height resolution":
            f = _float_cm(value)
            if f: result["height_resolution_cm"] = f
        elif key == "Height range":
            m = re.match(r"(-?[\d.]+)\s*\.\.\.\s*(-?[\d.]+)", value)
            if m:
                result["height_min_m"] = float(m.group(1))
                result["height_max_m"] = float(m.group(2))
        elif key == "Bits per surface texel":
            n = _int_first(value)
            if n is not None: result["bits_per_texel"] = n
        # Height Map section
        elif section == "heightmap":
            if key == "Planar resolution":
                f = _float_m(value)
                if f: result["planar_resolution_m"] = f
            elif key == "Block":
                verts, size = _vertex_dims(value)
                if verts:
                    result["block_vertices"] = verts
                    result["block_size_m"] = size
            elif key == "Tile":
                verts, size = _vertex_dims(value)
                if verts:
                    result["tile_vertices"] = verts
                    result["tile_size_m"] = size
            elif key == "Total":
                verts, size = _vertex_dims(value)
                if verts:
                    result["total_vertices"] = verts
                    result["total_size_m"] = size
        # Satellite Texture section
        elif section == "satellite":
            if key == "Tile resolution":
                d = _px_dims(value)
                if d: result["sat_tile_res_px"] = d
            elif key == "Tile texture border":
                n = _int_first(value)
                if n is not None: result["sat_tile_border_px"] = n
            elif key == "Tile overlap":
                n = _int_first(value)
                if n is not None: result["sat_tile_overlap_px"] = n
            elif key == "Total":
                d = _px_dims(value)
                if d: result["sat_total_px"] = d
            elif key == "Resolution":
                f = _float_m(value)
                if f: result["sat_resolution_m"] = f
        # Surface Map section
        elif section == "surface":
            if key == "Tile resolution":
                d = _px_dims(value)
                if d: result["surface_tile_res_px"] = d
            elif key == "Block overlap":
                n = _int_first(value)
                if n is not None: result["surface_block_overlap_px"] = n
            elif key == "Total":
                d = _px_dims(value)
                if d: result["surface_total_px"] = d
            elif key == "Resolution":
                f = _float_m(value)
                if f: result["surface_resolution_m"] = f
        # Normal Map section
        elif section == "normal":
            if key == "Tile resolution":
                d = _px_dims(value)
                if d: result["normal_tile_res_px"] = d
            elif key == "Tile overlap":
                n = _int_first(value)
                if n is not None: result["normal_tile_overlap_px"] = n
            elif key == "Total":
                d = _px_dims(value)
                if d: result["normal_total_px"] = d
            elif key == "Resolution":
                f = _float_m(value)
                if f: result["normal_resolution_m"] = f

    i = 0
    while i < len(lines):
        line = lines[i]

        if line in SECTION_HEADERS:
            section = SECTION_HEADERS[line]
            i += 1
            continue

        if line.endswith(":") and i + 1 < len(lines):
            key = line[:-1].strip()
            value = lines[i + 1].strip()
            # Skip if next line is itself a section header or key
            if not value.endswith(":") and value not in SECTION_HEADERS:
                _apply(key, value)
                i += 2
                continue

        i += 1

    if not result:
        raise ValueError("Aucune donnée reconnue — vérifier le format Reforger")

    return result

# ============================================================================
# SIDEBAR — CHARGEMENT ET EXPORT
# ============================================================================

# ── Projet courant dans la sidebar ───────────────────────────────────────────
if st.session_state.current_project_path:
    proj_info = st.session_state.current_project["project"]
    st.sidebar.markdown(f"### 📁 {proj_info['name']}")
    st.sidebar.caption(proj_info.get("description", ""))
    col_save, col_close = st.sidebar.columns(2)
    if col_save.button("💾 Sauvegarder", use_container_width=True):
        save_project()
        st.sidebar.success("Sauvegardé")
    if col_close.button("✖ Fermer", use_container_width=True):
        st.session_state.current_project_path = None
        st.session_state.current_project      = None
        st.session_state.heightmap_path       = None
        st.session_state.base_map             = None
        st.session_state.reforger_data        = None
        st.session_state.terr_materials       = []
        st.rerun()
    st.sidebar.divider()

st.sidebar.markdown("## 📂 **Chargement & Export**")
st.sidebar.divider()

# Section Chargement Heightmap
st.sidebar.markdown("### 📁 Heightmap")
uploaded_heightmap = st.sidebar.file_uploader(
    "Charger une heightmap",
    type=["asc", "png", "tga", "jpg"],
    help="Formats acceptés: ASC (recommandé), PNG, TGA, JPG"
)

if uploaded_heightmap is not None:
    # Sauvegarde temporaire
    temp_heightmap = f"temp_{uploaded_heightmap.name}"
    with open(temp_heightmap, "wb") as f:
        f.write(uploaded_heightmap.getbuffer())
    
    st.session_state.heightmap_path = temp_heightmap
    
    st.sidebar.success(f"✅ Heightmap chargée: {uploaded_heightmap.name}")
    st.sidebar.metric("Taille", f"{get_file_size_mb(temp_heightmap):.2f} MB")
    
    # Charger ou mettre à jour BaseMap
    try:
        with st.spinner("⏳ Analyse heightmap..."):
            bm = BaseMap(temp_heightmap)
            st.session_state.base_map = bm

        # Mise à jour du projet courant si ouvert
        if st.session_state.current_project_path:
            save_project()

        st.sidebar.success("✅ BaseMap créée")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            st.metric("Largeur", f"{st.session_state.base_map.width}px")
        with col2:
            st.metric("Hauteur", f"{st.session_state.base_map.height}px")
        
        col3, col4 = st.sidebar.columns(2)
        with col3:
            st.metric("Alt. min", f"{st.session_state.base_map.altitude_min:.0f}m")
        with col4:
            st.metric("Alt. max", f"{st.session_state.base_map.altitude_max:.0f}m")
    except Exception as e:
        st.sidebar.error(f"❌ Erreur: {e}")

# Section SatMap optionnelle
st.sidebar.markdown("### 🛰️ SatMap (Optionnel)")
uploaded_satmap = st.sidebar.file_uploader(
    "Charger une SatMap",
    type=["png", "jpg"],
    help="Image satellite ou ortho-photo (optionnel)"
)

if uploaded_satmap is not None:
    temp_satmap = f"temp_satmap_{uploaded_satmap.name}"
    with open(temp_satmap, "wb") as f:
        f.write(uploaded_satmap.getbuffer())
    st.session_state.satmap_path = temp_satmap
    st.sidebar.success(f"✅ SatMap chargée: {uploaded_satmap.name}")

# ── Section Masques Instant Terra ────────────────────────────────────────────
st.sidebar.markdown("### 🗺️ Masques Instant Terra")
_IT_ROLES = {
    "slopes":    "Slope 0–90° (continu)",
    "curvature": "Curvature (crêtes/creux)",
    "sediment":  "Sediment (dépôts)",
}
for _it_role, _it_label in _IT_ROLES.items():
    _it_val = st.sidebar.text_input(
        _it_label,
        value=st.session_state.get(f"it_path_{_it_role}", ""),
        placeholder="Chemin absolu ou relatif au projet…",
        key=f"_widget_it_{_it_role}",
    )
    st.session_state[f"it_path_{_it_role}"] = _it_val

if st.sidebar.button("🔄 Charger/Recharger masques IT", key="btn_reload_it"):
    if st.session_state.current_project_path:
        _p_it   = Path(st.session_state.current_project_path)
        _hm_s   = st.session_state.get("base_map")
        _hm_shape = (int(_hm_s.height), int(_hm_s.width)) if _hm_s else (0, 0)
        if _hm_shape[0] > 0:
            try:
                from reforger_texture_budget import load_it_mask as _reload_it
                _loaded = {}
                for _r in _IT_ROLES:
                    _ps = st.session_state.get(f"it_path_{_r}", "").strip()
                    if _ps:
                        _abs_it = Path(_ps) if Path(_ps).is_absolute() else _p_it / _ps
                        if _abs_it.exists():
                            _loaded[_r] = _reload_it(str(_abs_it), _hm_shape)
                st.session_state.it_masks = _loaded if _loaded else None
                save_project()
                st.sidebar.success(f"✅ {len(_loaded)} masque(s) IT chargé(s)")
            except Exception as _e_it:
                st.sidebar.error(f"Erreur IT : {_e_it}")
        else:
            st.sidebar.warning("Chargez d'abord une heightmap.")
    else:
        st.sidebar.warning("Ouvrez un projet d'abord.")

_it_status = st.session_state.get("it_masks") or {}
if _it_status:
    st.sidebar.caption(f"IT actifs : {', '.join(_it_status.keys())}")
else:
    st.sidebar.caption("Aucun masque IT chargé.")

st.sidebar.divider()

# ── Section Projet Reforger (.terr) ──────────────────────────────────────────
st.sidebar.markdown("### 📁 Projet Reforger")

terr_path_input = st.sidebar.text_input(
    "Chemin dossier addon",
    value=st.session_state.terr_project_path,
    placeholder=r"I:\Reforger_addons travail\ZBK_repo",
    key="terr_project_input",
)

if terr_path_input != st.session_state.terr_project_path:
    st.session_state.terr_project_path = terr_path_input
    st.session_state.terr_materials = []
    if st.session_state.current_project_path:
        save_project()

if terr_path_input and Path(terr_path_input).exists():
    from reforger_texture_budget import find_terr_files, parse_terr_materials as _parse_terr
    terr_files = find_terr_files(terr_path_input)
    if terr_files:
        if len(terr_files) == 1:
            selected_terr = str(terr_files[0])
        else:
            selected_terr = st.sidebar.selectbox(
                "Fichier .terr",
                [str(f) for f in terr_files],
                key="terr_file_select",
            )
        if not st.session_state.terr_materials:
            st.session_state.terr_materials = _parse_terr(selected_terr)
        st.sidebar.success(f"✅ {len(st.session_state.terr_materials)} matériaux chargés")
        with st.sidebar.expander("Matériaux disponibles"):
            for i, m in enumerate(st.session_state.terr_materials):
                st.caption(f"[{i:2d}] {m}")
    else:
        st.sidebar.warning("Aucun .terr trouvé dans ce dossier.")
elif terr_path_input:
    st.sidebar.error("Dossier introuvable.")

st.sidebar.divider()

# ── Section Données Reforger ─────────────────────────────────────────────────
st.sidebar.markdown("### 🗺️ Données Reforger")

with st.sidebar.expander("📋 Coller les données World Composition", expanded=st.session_state.reforger_data is None):
    reforger_raw = st.text_area(
        "Copier-coller depuis Reforger Workbench",
        height=180,
        placeholder=(
            "Blocks and Tiles\n"
            "Tiles:\n64 x 64\n"
            "Blocks per tile:\n4 x 4\n"
            "...\n"
            "Height Map:\nPlanar resolution:\n1 m\n"
            "Height range:\n-204.781 ... 1843.188 m\n..."
        ),
        label_visibility="collapsed",
        key="reforger_raw_input",
    )
    if st.button("🔍 Analyser", key="btn_parse_reforger"):
        if reforger_raw.strip():
            try:
                data = parse_reforger_world_data(reforger_raw)
                st.session_state.reforger_data = data
                st.success("✅ Données importées")
            except ValueError as e:
                st.error(f"❌ {e}")
        else:
            st.warning("Coller des données avant d'analyser.")

if st.session_state.reforger_data is not None:
    rd = st.session_state.reforger_data
    st.sidebar.markdown("**Terrain**")
    if "total_size_m" in rd:
        w, h = rd["total_size_m"]
        st.sidebar.caption(f"Taille : {w:,} × {h:,} m ({w/1000:.1f} × {h/1000:.1f} km)")
    if "planar_resolution_m" in rd:
        st.sidebar.caption(f"Cellsize : {rd['planar_resolution_m']} m/px")
    if "height_min_m" in rd and "height_max_m" in rd:
        st.sidebar.caption(f"Altitude : {rd['height_min_m']:.1f} … {rd['height_max_m']:.1f} m")

    st.sidebar.markdown("**Tiles / Blocs**")
    if "tiles" in rd:
        tx, ty = rd["tiles"]
        st.sidebar.caption(f"Tiles : {tx} × {ty} = {tx*ty:,} total")
    if "blocks_per_tile" in rd:
        bx, by = rd["blocks_per_tile"]
        st.sidebar.caption(f"Blocs/tile : {bx} × {by} = {bx*by}/tile")
    if "blocks_total" in rd:
        btx, bty = rd["blocks_total"]
        st.sidebar.caption(f"Blocs total : {btx} × {bty} = {btx*bty:,}")

    st.sidebar.markdown("**Surface Map**")
    if "surface_tile_res_px" in rd:
        sx, sy = rd["surface_tile_res_px"]
        st.sidebar.caption(f"Résolution/tile : {sx} × {sy} px")
    if "surface_resolution_m" in rd:
        st.sidebar.caption(f"Résolution : {rd['surface_resolution_m']} m/px")
    if "bits_per_texel" in rd:
        st.sidebar.caption(f"Bits/texel : {rd['bits_per_texel']}")

    if st.sidebar.button("🗑️ Effacer", key="btn_clear_reforger"):
        st.session_state.reforger_data = None
        st.rerun()

st.sidebar.divider()

# Section Export heightmap
if st.session_state.heightmap_path is not None:
    st.sidebar.markdown("### 📥 Export Heightmap")
    
    export_format = st.sidebar.radio(
        "Format export",
        ["PNG 16-bit", "PNG 8-bit", "RAW 16-bit", "ASC"],
        horizontal=True
    )
    
    if st.sidebar.button("📥 Exporter", key="export_heightmap"):
        try:
            output_dir = get_output_dir()
            timestamp = format_timestamp()
            
            base_map = st.session_state.base_map
            
            if export_format == "PNG 16-bit":
                import cv2 as _cv2
                # Partir des données float brutes (précision réelle, pas uint8 upscalé)
                h_min = base_map.altitude_min
                h_range = base_map.altitude_range
                heightmap_16 = np.clip(
                    (base_map.heightmap_float - h_min) / h_range * 65535.0,
                    0, 65535
                ).astype(np.uint16)
                output_path = f"{output_dir}/heightmap_export_{timestamp}_16bit.png"
                _cv2.imwrite(output_path, heightmap_16)

                metadata = {
                    "altitude_min": float(h_min),
                    "altitude_max": float(base_map.altitude_max),
                    "width": base_map.width,
                    "height": base_map.height,
                    "timestamp": timestamp,
                    "encoding": "uint16 linear, 0=alt_min, 65535=alt_max",
                }
                with open(f"{output_dir}/heightmap_export_{timestamp}_16bit_metadata.json", "w") as f:
                    json.dump(metadata, f, indent=2)

            elif export_format == "PNG 8-bit":
                output_path = f"{output_dir}/heightmap_export_{timestamp}_8bit.png"
                Image.fromarray(base_map.heightmap_uint8, mode='L').save(output_path)

            elif export_format == "RAW 16-bit":
                h_min   = base_map.altitude_min
                h_range = base_map.altitude_range
                # uint16 little-endian (LSB first), sans header
                heightmap_16 = np.clip(
                    (base_map.heightmap_float - h_min) / h_range * 65535.0,
                    0, 65535
                ).astype('<u2')   # '<u2' = uint16 little-endian explicite
                output_path = f"{output_dir}/heightmap_export_{timestamp}_16bit.raw"
                heightmap_16.tofile(output_path)

                metadata = {
                    "altitude_min": float(h_min),
                    "altitude_max": float(base_map.altitude_max),
                    "width": base_map.width,
                    "height": base_map.height,
                    "timestamp": timestamp,
                    "encoding": "uint16 little-endian (LSB first), no header, row-major",
                }
                with open(f"{output_dir}/heightmap_export_{timestamp}_16bit_raw_metadata.json", "w") as f:
                    json.dump(metadata, f, indent=2)

            # ASC export — TODO: implémenter selon format ASC
            
            st.sidebar.success(f"✅ Exporté: {Path(output_path).name}")
        except Exception as e:
            st.sidebar.error(f"❌ Erreur export: {e}")

# ── Bibliothèque de matériaux ────────────────────────────────────────────────
st.sidebar.divider()
with st.sidebar.expander("📚 Bibliothèque de matériaux", expanded=False):
    import pandas as _pd_lib

    _lib_state = st.session_state.get("material_library")
    _proj_path = st.session_state.get("current_project_path")

    if _lib_state is None:
        st.info("Ouvrez un projet pour accéder à la bibliothèque.")
    else:
        _lib_tab_v, _lib_tab_c = st.tabs(["🌐 Vanilla", "🎨 Custom projet"])

        # ── helpers ──────────────────────────────────────────────────────────
        def _color_dot(rgb):
            return f'<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:rgb({rgb[0]},{rgb[1]},{rgb[2]});margin-right:4px;vertical-align:middle"></span>'

        def _reload_lib():
            _lib2 = load_merged_library(_proj_path)
            st.session_state.material_library = _lib2
            from reforger_texture_budget import set_runtime_library
            set_runtime_library(_lib2["materials"], _lib2["roles"])

        # ── Onglet VANILLA ───────────────────────────────────────────────────
        with _lib_tab_v:
            _van_raw = json.loads(_VANILLA_LIB_PATH.read_text(encoding="utf-8")) \
                if _VANILLA_LIB_PATH.exists() else {"roles": [], "materials": []}

            st.markdown("**Rôles**")
            _van_roles = _van_raw.get("roles", [])
            for _vr in _van_roles:
                _col_vr, _col_vr_del = st.columns([4, 1])
                _col_vr.markdown(
                    _color_dot(_vr["color"]) + f'`{_vr["id"]}` — {_vr["label"]}',
                    unsafe_allow_html=True,
                )
                if _col_vr_del.button("🗑️", key=f"del_vr_{_vr['id']}"):
                    _van_roles = [r for r in _van_roles if r["id"] != _vr["id"]]
                    save_vanilla_library(_van_roles, _van_raw.get("materials", []))
                    _reload_lib()
                    st.rerun()

            st.markdown("**Ajouter un rôle**")
            with st.form("form_van_add_role", clear_on_submit=True):
                _vr_id    = st.text_input("ID rôle (ex: marais)", key="vr_id")
                _vr_label = st.text_input("Label",                key="vr_label")
                _vr_color = st.color_picker("Couleur", "#507850",  key="vr_color")
                if st.form_submit_button("➕ Ajouter rôle vanilla"):
                    if _vr_id and not any(r["id"] == _vr_id for r in _van_roles):
                        _c = tuple(int(_vr_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
                        _van_roles.append({"id": _vr_id, "label": _vr_label or _vr_id, "color": list(_c)})
                        save_vanilla_library(_van_roles, _van_raw.get("materials", []))
                        _reload_lib()
                        st.rerun()

            st.markdown("---")
            st.markdown("**Matériaux**")
            _van_mats  = _van_raw.get("materials", [])
            _van_roles_ids = [r["id"] for r in _van_roles]
            _filt_role = st.selectbox("Filtrer par rôle", ["(tous)"] + _van_roles_ids, key="lib_van_filt")
            _shown     = [m for m in _van_mats if _filt_role == "(tous)" or m["role"] == _filt_role]
            for _vm in _shown:
                _col_vm, _col_vm_del = st.columns([4, 1])
                _col_vm.markdown(f'`{_vm["stem"]}` → **{_vm["role"]}** — {_vm["label"]}')
                if _col_vm_del.button("🗑️", key=f"del_vm_{_vm['stem']}"):
                    _van_mats = [m for m in _van_mats if m["stem"] != _vm["stem"]]
                    save_vanilla_library(_van_roles, _van_mats)
                    _reload_lib()
                    st.rerun()

            st.markdown("**Ajouter un matériau**")
            with st.form("form_van_add_mat", clear_on_submit=True):
                _vm_stem  = st.text_input("Stem .emat (ex: Grass_04)", key="vm_stem")
                _vm_role  = st.selectbox("Rôle",  _van_roles_ids or ["erosion"], key="vm_role")
                _vm_label = st.text_input("Label", key="vm_label")
                _vm_pipe  = st.checkbox("terrain_pipeline", value=True, key="vm_pipe")
                if st.form_submit_button("➕ Ajouter matériau vanilla"):
                    if _vm_stem:
                        _van_mats.append({
                            "stem": _vm_stem, "role": _vm_role,
                            "label": _vm_label or _vm_stem,
                            "terrain_pipeline": _vm_pipe,
                        })
                        save_vanilla_library(_van_roles, _van_mats)
                        _reload_lib()
                        st.rerun()

        # ── Onglet CUSTOM ────────────────────────────────────────────────────
        with _lib_tab_c:
            if not _proj_path:
                st.info("Aucun projet ouvert.")
            else:
                _cust_path = Path(_proj_path) / "material_library_custom.json"
                _cust_raw  = json.loads(_cust_path.read_text(encoding="utf-8")) \
                    if _cust_path.exists() else {"roles": [], "materials": []}
                _cust_roles = _cust_raw.get("roles", [])
                _cust_mats  = _cust_raw.get("materials", [])

                # Rôles custom
                st.markdown("**Rôles custom**")
                if not _cust_roles:
                    st.caption("Aucun rôle custom.")
                for _cr in _cust_roles:
                    col_cr, col_del = st.columns([4, 1])
                    col_cr.markdown(
                        _color_dot(_cr["color"]) + f'`{_cr["id"]}` — {_cr["label"]}',
                        unsafe_allow_html=True,
                    )
                    if col_del.button("🗑️", key=f"del_cr_{_cr['id']}"):
                        _cust_roles = [r for r in _cust_roles if r["id"] != _cr["id"]]
                        save_custom_library(_proj_path, _cust_roles, _cust_mats)
                        _reload_lib()
                        st.rerun()

                with st.form("form_cust_add_role", clear_on_submit=True):
                    _cr_id    = st.text_input("ID rôle custom", key="cr_id")
                    _cr_label = st.text_input("Label",          key="cr_label")
                    _cr_color = st.color_picker("Couleur", "#806040", key="cr_color")
                    if st.form_submit_button("➕ Ajouter rôle custom"):
                        if _cr_id:
                            _c2 = tuple(int(_cr_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
                            _cust_roles.append({"id": _cr_id, "label": _cr_label or _cr_id, "color": list(_c2)})
                            save_custom_library(_proj_path, _cust_roles, _cust_mats)
                            _reload_lib()
                            st.rerun()

                st.markdown("---")
                st.markdown("**Matériaux custom**")
                if not _cust_mats:
                    st.caption("Aucun matériau custom.")
                for _cm in _cust_mats:
                    col_cm, col_del2 = st.columns([4, 1])
                    col_cm.markdown(f'`{_cm["stem"]}` → **{_cm["role"]}** — {_cm["label"]}')
                    if col_del2.button("🗑️", key=f"del_cm_{_cm['stem']}"):
                        _cust_mats = [m for m in _cust_mats if m["stem"] != _cm["stem"]]
                        save_custom_library(_proj_path, _cust_roles, _cust_mats)
                        _reload_lib()
                        st.rerun()

                # Rôles disponibles = vanilla + custom
                _all_roles_ids = [r["id"] for r in _lib_state.get("roles", [])]
                with st.form("form_cust_add_mat", clear_on_submit=True):
                    _cm_stem  = st.text_input("Stem .emat", key="cm_stem",
                                              help="Même stem qu'une entrée vanilla = override pour ce projet")
                    _cm_role  = st.selectbox("Rôle", _all_roles_ids or ["erosion"], key="cm_role")
                    _cm_label = st.text_input("Label", key="cm_label")
                    _cm_pipe  = st.checkbox("terrain_pipeline", value=False, key="cm_pipe")
                    if st.form_submit_button("➕ Ajouter matériau custom"):
                        if _cm_stem:
                            _cust_mats.append({
                                "stem": _cm_stem, "role": _cm_role,
                                "label": _cm_label or _cm_stem,
                                "terrain_pipeline": _cm_pipe,
                            })
                            save_custom_library(_proj_path, _cust_roles, _cust_mats)
                            _reload_lib()
                            st.rerun()

# ============================================================================
# MAIN CONTENT — ONGLETS
# ============================================================================

st.markdown('<h1 class="main-header">🗺️ Map Generator Pro v3.0</h1>', unsafe_allow_html=True)

# ── Page d'accueil si aucun projet ouvert ────────────────────────────────────
if st.session_state.current_project_path is None:
    st.markdown("### Bienvenue — choisissez ou créez un projet")
    col_new, col_open = st.columns([1, 2])

    with col_new:
        st.markdown("#### Nouveau projet")
        with st.form("form_new_project"):
            pname  = st.text_input("Nom du projet", placeholder="ZBK_island")
            pauthor = st.text_input("Auteur", value="[otea] Giorbev")
            pdesc  = st.text_area("Description", height=80)
            if st.form_submit_button("Créer", use_container_width=True):
                if pname.strip():
                    new_path = create_project(pname.strip(), pauthor.strip(), pdesc.strip())
                    load_project(str(new_path))
                    st.rerun()
                else:
                    st.error("Le nom du projet est requis.")

    with col_open:
        st.markdown("#### Projets récents")
        projects = list_projects()
        if not projects:
            st.info("Aucun projet trouvé dans data/projects/")
        else:
            for proj in projects:
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**{proj['name']}**")
                    if proj["description"]:
                        st.caption(proj["description"])
                    if proj["heightmap"]:
                        st.caption(f"Heightmap : {proj['heightmap']}")
                    if proj["updated_at"]:
                        st.caption(f"Modifié : {proj['updated_at'][:10]}")
                with c2:
                    if st.button("Ouvrir", key=f"open_{proj['name']}"):
                        load_project(proj["path"])
                        st.rerun()
                st.divider()

    st.stop()

# ── En-tête projet courant ────────────────────────────────────────────────────
proj_name = st.session_state.current_project["project"]["name"]
st.caption(f"Projet : **{proj_name}**")

if st.session_state.base_map is None:
    st.warning("⚠️ Veuillez d'abord charger une heightmap dans la barre latérale (gauche)")
else:
    # Onglets principaux
    tab_terrain, tab_gen, tab_export = st.tabs([
        "🏔️ Terrain",
        "🎨 Génération",
        "🗂️ Calques & Export",
    ])
    
    # ========================================================================
    # ONGLET TERRAIN — sous-onglets : Hypsométrique / NatureMap / Analyse
    # ========================================================================

    with tab_terrain:
        _t_hypso, _t_analyse = st.tabs([
            "🎨 Hypsométrique", "📈 Analyse",
        ])

    with _t_hypso:
        st.markdown("### 🎨 Colormap Hypsométrique")
        st.markdown("""
        Génère une carte colorée basée **uniquement** sur l'altitude, sans texture complexe.
        
        **Palette:** Vert (bas) → Jaune → Orange → Rouge → Marron (haut)
        """)
        
        col1, col2, col3 = st.columns(3)

        with col1:
            enable_hillshade = st.checkbox("☀️ Hillshading", value=False)
        with col2:
            enable_enrichment = st.checkbox(
                "✨ Enrichissement morphologique",
                value=False,
                help="Ajoute modulation TPI (relief), talwegs bleutés (flow D8) et dépressions cyan"
            )
        with col3:
            if st.button("🚀 Générer Hypsométrique", key="gen_hypsometric"):
                try:
                    with st.spinner("⏳ Génération colormap hypsométrique..."):
                        output_dir = get_output_dir()
                        timestamp = format_timestamp()
                        filename = f"color_map_hypsometric_{timestamp}.png"
                        hypsometric_gen = HypsometricColormapGenerator(
                            st.session_state.heightmap_path,
                            output_dir=output_dir
                        )
                        hypsometric_gen.save(
                            filename,
                            add_hillshade=enable_hillshade,
                            add_enrichment=enable_enrichment
                        )
                        colormap_path = f"{output_dir}/{filename}"
                        st.session_state.last_generated['hypsometric'] = colormap_path
                        st.success("✅ Hypsométrique générée")
                except Exception as e:
                    st.error(f"❌ Erreur: {e}")
        
        # Affichage résultat
        if 'hypsometric' in st.session_state.last_generated:
            try:
                hyp_path = st.session_state.last_generated['hypsometric']
                img = load_image(hyp_path)
                if img:
                    MAX_DISP_HY = 2048
                    if max(img.width, img.height) > MAX_DISP_HY:
                        scale = MAX_DISP_HY / max(img.width, img.height)
                        img = img.resize(
                            (int(img.width * scale), int(img.height * scale)),
                            Image.BOX,
                        )
                    st.image(img, caption="Colormap Hypsométrique", use_container_width=True)
                    with open(hyp_path, "rb") as f:
                        st.download_button(
                            "📥 Télécharger PNG", f.read(),
                            file_name=Path(hyp_path).name, mime="image/png",
                        )
            except Exception as e:
                st.error(f"❌ Erreur affichage: {e}")
    
    
    # ========================================================================
    # ONGLET GÉNÉRATION — sous-onglets : Aperçu Texture / Végétation / Fusion
    # ========================================================================

    with tab_gen:
        _g_tex, _g_veg = st.tabs([
            "🖼️ Aperçu Texture", "🌱 Végétation",
        ])

    with _g_tex:
        import pandas as pd
        from reforger_texture_budget import (
            BIOME_TEXTURES, BIOME_SNOWLINE, TEXTURE_COLORS, TEXTURE_LABELS, TEXTURE_ORDER,
            SATMAP_TEXTURE_ORDER,
            compute_texture_scores, apply_block_budget,
            render_rgb, draw_grid_overlay, get_tile_debug_info,
        )
        has_reforger = st.session_state.reforger_data is not None

        st.markdown("### 🖼️ Aperçu Texture Terrain 2D")
        if has_reforger:
            st.info(
                "🗺️ Données Reforger actives — budget textures par bloc configurable, "
                "grille tuiles/blocs, indices Reforger."
            )

        from reforger_texture_budget import get_role_options

        # ── Profil climatique + budget ───────────────────────────────────────
        col1, col2 = st.columns(2)
        with col1:
            climate_profile = st.selectbox(
                "🌍 Profil climatique",
                list(BIOME_TEXTURES.keys()),
                key="tex_climate",
            )
        with col2:
            max_textures = st.slider(
                "Budget textures/bloc", 2, 4, 3, key="tex_max_slots",
                help=(
                    "Max textures simultanées par bloc (limite QTRE Reforger = 4). "
                    "Si une texture est peinte en base dans Workbench (ex: prairie), "
                    "elle occupe 1 slot permanent → réglez à 3."
                ),
            )
        if not has_reforger:
            preview_mode = st.selectbox(
                "🔍 Mode d'aperçu",
                ["Morphologique (actuel)", "Morphologique + SatMap", "SatMap (indépendant)"],
                key="tex_mode",
            )

        # ── Table textures du biome — selectbox par rôle ────────────────────
        if has_reforger:
            biome_defaults = BIOME_TEXTURES.get(climate_profile, {})

            # Réinitialiser si le biome a changé
            if st.session_state.biome_cfg_profile != climate_profile:
                st.session_state.biome_cfg_profile = climate_profile
                st.session_state.biome_cfg_data    = dict(biome_defaults)
            else:
                # Patcher les rôles ajoutés depuis la dernière init (sans écraser les choix utilisateur)
                for _r, _e in biome_defaults.items():
                    if _r not in st.session_state.biome_cfg_data:
                        st.session_state.biome_cfg_data[_r] = _e

            with st.expander("✏️ Textures du biome — sélectionner ou personnaliser"):
                st.caption(
                    "Défaut biome en tête de liste. "
                    "Choisissez ✏️ Personnalisé… pour saisir un fichier hors catalogue."
                )
                cfg = st.session_state.biome_cfg_data

                for role in TEXTURE_ORDER:
                    biome_def  = biome_defaults.get(role, "")
                    current    = cfg.get(role, biome_def)
                    options    = get_role_options(biome_def)

                    # Index courant dans la liste
                    if current in options:
                        idx = options.index(current)
                    elif current:
                        # valeur personnalisée non listée → ajouter temporairement
                        options.insert(1, current)
                        idx = 1
                    else:
                        idx = 0

                    c_label, c_sel, c_custom = st.columns([1.6, 2.4, 2])
                    c_label.markdown(
                        f"**{TEXTURE_LABELS.get(role, role)}**",
                        help=f"Rôle : `{role}`",
                    )
                    chosen = c_sel.selectbox(
                        "", options, index=idx,
                        key=f"tex_sel_{role}",
                        label_visibility="collapsed",
                    )
                    if chosen == "✏️ Personnalisé…":
                        custom_val = c_custom.text_input(
                            "", value=current if current not in options[:-1] else "",
                            placeholder="MonTexture.emat",
                            key=f"tex_custom_{role}",
                            label_visibility="collapsed",
                        )
                        cfg[role] = custom_val or current
                    else:
                        cfg[role] = chosen

        # ── Paramètres morphologiques ────────────────────────────────────────
        with st.expander("⚙️ Paramètres morphologiques"):
            mp1, mp2, mp3 = st.columns(3)
            with mp1:
                preview_snow_pct = st.slider(
                    "Percentile neige (%)", 80, 99, 92, key="tex_snow",
                )
                preview_soil_flow_pct = st.slider(
                    "Percentile flow sol (%)", 70, 98, 88, key="tex_flow",
                )
            with mp2:
                coastal_dist_m = st.slider(
                    "Zone côtière (m)", 20, 200, 60, step=10, key="tex_coastal",
                    disabled=not has_reforger,
                    help="Largeur de la transition terre/mer en mètres",
                )
                if not has_reforger:
                    sat_mode = preview_mode in (
                        "Morphologique + SatMap", "SatMap (indépendant)"
                    )
                    sat_strength = st.slider(
                        "Force guidance SatMap", 0.0, 1.0, 0.35, step=0.05,
                        key="tex_sat_str", disabled=not sat_mode,
                    )
            with mp3:
                _snowline_default = BIOME_SNOWLINE.get(climate_profile, 0.75)
                snowline_pct = st.slider(
                    "Snowline (altitude min neige)",
                    0.0, 1.0, _snowline_default, step=0.05,
                    key="tex_snowline",
                    help=(
                        f"Fraction de l'altitude normalisée en dessous de laquelle "
                        f"la neige est supprimée. Défaut biome {climate_profile} : "
                        f"{_snowline_default:.0%}. "
                        f"0 = neige partout (arctique), 0.9 = sommets seulement."
                    ),
                )

        # ── Bouton génération ────────────────────────────────────────────────
        if st.button("🚀 Générer Aperçu Texture", key="gen_texture_preview"):
            try:
                with st.spinner("⏳ Analyse morphologique + budget textures Reforger..."):
                    output_dir = get_output_dir()

                    if has_reforger:
                        # ── Chemin Reforger : pipeline direct ────────────────
                        rd = st.session_state.reforger_data
                        cell_m      = float(rd.get("planar_resolution_m", 1.0))
                        png_alt_max = float(rd.get("height_max_m", 1000.0))
                        _bsm = rd.get("block_size_m", 32)
                        block_size_m = float(_bsm[0] if isinstance(_bsm, (list, tuple)) else _bsm)

                        from naturemap_biomes_generator import NatureMapBiomesGenerator
                        nat_gen = NatureMapBiomesGenerator(
                            st.session_state.heightmap_path,
                            output_dir=output_dir,
                            png_alt_max=png_alt_max,
                            png_cellsize=cell_m,
                        )
                        st.session_state.nat_gen = nat_gen

                        tex_scores = compute_texture_scores(
                            nat_gen,
                            climate_profile=climate_profile,
                            coastal_distance_m=float(coastal_dist_m),
                            snowline_alt_pct=float(snowline_pct),
                            snow_pct=int(preview_snow_pct),
                            flow_pct=int(preview_soil_flow_pct),
                            it_masks=st.session_state.get("it_masks"),
                        )

                        block_px = max(1, round(block_size_m / nat_gen.cellsize))
                        # Lire le rôle de base depuis la section export (session_state).
                        # La base occupe 1 slot QTRE permanent → budgeter les autres à max-1.
                        _use_base_budget = st.session_state.get("export_base_tex_enabled", True)
                        _base_role_budget = (
                            st.session_state.get("export_base_role_sel", "prairie")
                            if _use_base_budget else None
                        )
                        constrained, block_assignments = apply_block_budget(
                            tex_scores, block_px,
                            max_textures=int(max_textures),
                            base_role=_base_role_budget,
                        )

                        _bm = st.session_state.base_map
                        preview_arr = render_rgb(
                            constrained,
                            heightmap=_bm.heightmap_float if _bm is not None else None,
                            alt_min=float(rd.get("height_min_m", 0.0)),
                        )

                        timestamp    = format_timestamp()
                        preview_path = f"{output_dir}/terrain_texture_reforger_{timestamp}.png"
                        Image.fromarray(preview_arr, mode="RGB").save(preview_path)

                        st.session_state.tex_reforger = {
                            "image":              preview_arr,
                            "constrained_scores": constrained,
                            "block_assignments":  block_assignments,
                            "cell_m":             float(nat_gen.cellsize),
                            "reforger_data":      rd,
                            "biome_config":       dict(st.session_state.biome_cfg_data),
                            "climate_profile":    climate_profile,
                            "max_textures":       int(max_textures),
                        }
                        st.session_state.last_generated["texture_preview"] = preview_path
                        st.success("✅ Aperçu Reforger généré")

                    else:
                        # ── Chemin standard ──────────────────────────────────
                        from map_generator.application.use_cases.generate_terrain_preview_use_case import (
                            GenerateTerrainPreviewUseCase,
                        )
                        from map_generator.domain.models.terrain import TerrainPreviewRequest

                        sat_array = None
                        if preview_mode in ("Morphologique + SatMap", "SatMap (indépendant)") \
                                and st.session_state.satmap_path:
                            sat_img   = Image.open(st.session_state.satmap_path).convert("RGB")
                            sat_array = np.array(sat_img)

                        bm          = st.session_state.base_map
                        png_alt_max = float(getattr(bm, "altitude_max", 1000.0))

                        request = TerrainPreviewRequest(
                            heightmap_path=st.session_state.heightmap_path,
                            output_dir=output_dir,
                            climate_profile=climate_profile,
                            preview_mode=preview_mode,
                            preview_snow_pct=preview_snow_pct,
                            preview_soil_flow_pct=preview_soil_flow_pct,
                            sat_guidance_strength=sat_strength,
                            sat_array=sat_array,
                            png_alt_max=png_alt_max,
                        )
                        result = GenerateTerrainPreviewUseCase().execute(request)

                        timestamp    = format_timestamp()
                        preview_path = f"{output_dir}/terrain_texture_preview_{timestamp}.png"
                        Image.fromarray(result.preview_image, mode="RGB").save(preview_path)

                        st.session_state.last_generated["texture_preview"]        = preview_path
                        st.session_state.last_generated["texture_preview_result"] = result
                        st.success("✅ Aperçu texture généré")

            except Exception as e:
                st.error(f"❌ Erreur: {e}")
                st.exception(e)

        # ── Affichage résultat Reforger ──────────────────────────────────────
        if has_reforger and st.session_state.tex_reforger is not None:
            tr          = st.session_state.tex_reforger
            preview_arr = tr["image"]
            rd_stored   = tr["reforger_data"]
            cell_m_st   = tr["cell_m"]
            blk_asgn    = tr["block_assignments"]
            biome_cfg   = tr["biome_config"]

            # Contrôles grille (avant affichage pour réactivité)
            gc1, gc2 = st.columns(2)
            show_grid   = gc1.checkbox("📐 Grille tuiles/blocs", value=True,  key="chk_grid")
            show_labels = gc2.checkbox("🏷️ Numéros de tuiles",  value=True,  key="chk_labels")

            # Construire image d'affichage — downscaler EN PREMIER, grille APRÈS
            # (sinon les lignes 1-2px sont sub-pixel après réduction et invisibles)
            disp = preview_arr.copy()
            MAX_DISP = 2048
            disp_scale = 1.0
            if max(disp.shape[:2]) > MAX_DISP:
                from PIL import Image as _PIL
                pil_d      = _PIL.fromarray(disp)
                disp_scale = MAX_DISP / max(pil_d.width, pil_d.height)
                pil_d      = pil_d.resize(
                    (int(pil_d.width * disp_scale), int(pil_d.height * disp_scale)),
                    _PIL.BOX,  # BOX = filtre aire, pas d'oscillations LANCZOS aux frontières eau/terre
                )
                disp = np.array(pil_d)

            # Grille tracée sur l'image déjà réduite → lignes toujours 1-2 px
            if show_grid:
                effective_cell_m = cell_m_st / disp_scale
                try:
                    disp = draw_grid_overlay(
                        disp, rd_stored, effective_cell_m,
                        show_blocks=True, show_tile_labels=show_labels,
                    )
                except Exception as _grid_err:
                    st.warning(f"⚠️ Grille non tracée : {_grid_err}")

            st.image(disp, caption="Aperçu Texture — Budget Reforger", use_container_width=True)

            preview_path = st.session_state.last_generated.get("texture_preview")
            if preview_path and Path(preview_path).exists():
                with open(preview_path, "rb") as fh:
                    st.download_button(
                        "📥 Télécharger PNG (sans grille)", fh.read(),
                        file_name=Path(preview_path).name, mime="image/png",
                        key="dl_reforger_preview",
                    )

            # Répartition dominante par texture
            st.markdown("#### Répartition dominante par texture")
            dominance: dict = {}
            for asg in blk_asgn.values():
                if asg:
                    dominance[asg[0][0]] = dominance.get(asg[0][0], 0) + 1
            total_blks = max(len(blk_asgn), 1)
            tex_cols   = st.columns(len(TEXTURE_ORDER))
            for i, role in enumerate(TEXTURE_ORDER):
                pct = dominance.get(role, 0) / total_blks * 100
                tex_cols[i].metric(TEXTURE_LABELS.get(role, role), f"{pct:.1f}%")

            # Analyse poids par bloc — visibilité up-close
            with st.expander("🔬 Analyse visibilité par bloc (poids QTRE)"):
                st.caption(
                    "Pour qu'une texture soit **visible de près**, elle doit avoir "
                    "un poids ≥ 25 % dans le bloc. En dessous, elle est un tint subtil. "
                    "En dessous de 15 % (seuil min), elle est exclue du bloc."
                )
                # Collecte des poids par texture dans tous les blocs
                import collections as _col
                _tex_weights = _col.defaultdict(list)
                for _asg in blk_asgn.values():
                    for _k, _w in _asg:
                        _tex_weights[_k].append(_w)

                _hdr = ["Texture", "Blocs sélectionnés", "Poids moy. (%)", "Blocs >25 % (visible)", "Blocs >40 % (dominant)"]
                _rows = []
                for _role in TEXTURE_ORDER:
                    _ws = _tex_weights.get(_role, [])
                    if not _ws:
                        _rows.append([TEXTURE_LABELS.get(_role, _role), "—", "—", "—", "—"])
                        continue
                    _n       = len(_ws)
                    _avg     = float(np.mean(_ws)) * 100
                    _n25     = sum(1 for w in _ws if w > 0.25)
                    _n40     = sum(1 for w in _ws if w > 0.40)
                    _pct_blk = _n / total_blks * 100
                    _rows.append([
                        TEXTURE_LABELS.get(_role, _role),
                        f"{_n} ({_pct_blk:.1f}% des blocs)",
                        f"{_avg:.1f}%",
                        f"{_n25} ({_n25/_n*100:.0f}% des blocs sélectionnés)" if _n else "—",
                        f"{_n40} ({_n40/_n*100:.0f}%)" if _n else "—",
                    ])
                import pandas as _pd
                st.table(_pd.DataFrame(_rows, columns=_hdr))

            # Occupation pixel par texture + diagnostic Default
            with st.expander("📊 Occupation pixels par texture (Default texture)"):
                _cs_diag = tr["constrained_scores"]
                _h_d, _w_d = next(iter(_cs_diag.values())).shape
                _n_pix = _h_d * _w_d

                # Somme de tous les masques → résidu = part Default
                _sum_all = sum(_cs_diag.values())
                _default_pct = float(np.mean(_sum_all < 0.05)) * 100
                _coverage_pct = 100.0 - _default_pct

                _dc1, _dc2 = st.columns(2)
                _dc1.metric(
                    "Couverture totale",
                    f"{_coverage_pct:.2f}%",
                    help="% de pixels avec au moins une texture active (sum > 0.05)",
                )
                _dc2.metric(
                    "Texture Default résiduelle",
                    f"{_default_pct:.2f}%",
                    delta="OK" if _default_pct < 0.1 else f"{_default_pct:.2f}% de la surface",
                    delta_color="normal" if _default_pct < 0.1 else "inverse",
                    help="% de pixels sans texture → Reforger affiche la Default.emat ici",
                )
                if _default_pct < 0.1:
                    st.success("✅ Couverture complète — aucune Default texture visible.")
                else:
                    st.warning(
                        f"⚠️ {_default_pct:.2f}% des pixels sont sans texture. "
                        "Ces zones afficheront la Default.emat dans Reforger."
                    )

                # Tableau occupation par texture
                st.markdown("**Occupation par texture**")
                _occ_rows = []
                for _rl in TEXTURE_ORDER:
                    if _rl not in _cs_diag:
                        continue
                    _arr = _cs_diag[_rl]
                    _pct_active  = float(np.mean(_arr > 0.05))  * 100   # pixels actifs
                    _pct_dom     = float(np.mean(_arr > 0.40))  * 100   # pixels dominants
                    _avg_w       = float(np.mean(_arr))          * 100   # poids moyen
                    _occ_rows.append({
                        "Texture":          TEXTURE_LABELS.get(_rl, _rl),
                        "Pixels actifs >5%":  f"{_pct_active:.1f}%",
                        "Pixels dominants >40%": f"{_pct_dom:.1f}%",
                        "Poids moyen":       f"{_avg_w:.2f}%",
                    })
                import pandas as _pd_occ
                st.table(_pd_occ.DataFrame(_occ_rows))
                del _sum_all, _default_pct, _coverage_pct, _occ_rows


            # ── Budget moyen par bloc ─────────────────────────────────────────
            with st.expander("📊 Budget textures — utilisation par bloc"):
                counts = [len(asg) for asg in blk_asgn.values() if asg]
                if counts:
                    max_tex     = tr.get("max_textures", 4)
                    avg_tex     = float(np.mean(counts))
                    slots_libres = max_tex - avg_tex
                    dist        = {i: counts.count(i) for i in range(1, max_tex + 1)}
                    pct_sature  = counts.count(max_tex) / len(counts) * 100

                    ba1, ba2, ba3 = st.columns(3)
                    ba1.metric(
                        "Moy. textures / bloc",
                        f"{avg_tex:.2f} / {max_tex}",
                        help="Nombre moyen de textures actives dans un bloc Reforger",
                    )
                    ba2.metric(
                        "Slots libres en moyenne",
                        f"{slots_libres:.2f}",
                        delta=f"{'✅ Ajout possible' if slots_libres >= 0.8 else '⚠️ Serré'}",
                        delta_color="normal" if slots_libres >= 0.8 else "inverse",
                    )
                    ba3.metric(
                        "Blocs saturés (= max)",
                        f"{pct_sature:.1f}%",
                        help=f"Blocs utilisant déjà les {max_tex} slots — aucune texture supplémentaire possible",
                    )

                    st.markdown("**Distribution du nombre de textures par bloc :**")
                    dist_cols = st.columns(max_tex)
                    for i in range(1, max_tex + 1):
                        n   = dist.get(i, 0)
                        pct = n / len(counts) * 100
                        label = f"{i} texture{'s' if i > 1 else ''}"
                        dist_cols[i - 1].metric(label, f"{pct:.1f}%", f"{n} blocs")

                    if slots_libres >= 1.0:
                        st.success(
                            f"✅ En moyenne **{slots_libres:.1f} slot(s) libre(s)** par bloc — "
                            f"tu peux ajouter une texture supplémentaire sur la majorité de la map."
                        )
                    elif slots_libres >= 0.5:
                        st.warning(
                            f"⚠️ Seulement **{slots_libres:.1f} slot libre** en moyenne — "
                            f"une texture supplémentaire passera sur certaines zones, "
                            f"mais {pct_sature:.0f}% des blocs sont déjà saturés."
                        )
                    else:
                        st.error(
                            f"❌ Budget quasi-plein ({avg_tex:.1f}/{max_tex} en moy.) — "
                            f"ajouter une texture risque de dépasser le budget sur {pct_sature:.0f}% des blocs."
                        )

            # ── Debug — inspecter une tuile ──────────────────────────────────
            with st.expander("🔍 Debug — Inspecter une tuile Reforger"):
                blocks_per_tile = rd_stored.get("blocks_per_tile", (4, 4))
                tiles           = rd_stored.get("tiles",           (64, 64))

                dbg1, dbg2 = st.columns(2)
                tile_x_sel = dbg1.number_input(
                    "Tuile X", 0, tiles[0] - 1, 0, key="dbg_tx",
                )
                tile_y_sel = dbg2.number_input(
                    "Tuile Y  (0 = bas)", 0, tiles[1] - 1, 0, key="dbg_ty",
                )

                debug_blocs = get_tile_debug_info(
                    blk_asgn,
                    int(tile_x_sel), int(tile_y_sel),
                    blocks_per_tile, biome_cfg,
                )

                st.markdown(
                    f"**Tuile Reforger ({int(tile_x_sel)}, {int(tile_y_sel)})** "
                    f"— {blocks_per_tile[0]}×{blocks_per_tile[1]} blocs"
                )

                rows_dbg = []
                for bloc in debug_blocs:
                    dbx, dby = bloc["bloc_local"]
                    for t in bloc["textures"]:
                        rows_dbg.append({
                            "Bloc": f"({dbx},{dby})",
                            "Rôle": t["label"],
                            "Fichier": t["emat"],
                            "Poids (%)": t["poids_%"],
                        })
                if rows_dbg:
                    df_dbg = pd.DataFrame(rows_dbg)
                    st.dataframe(df_dbg, use_container_width=True, hide_index=True)

                    n_over = sum(
                        1 for b in debug_blocs if len(b["textures"]) > max_textures
                    )
                    if n_over:
                        st.warning(
                            f"⚠️ {n_over} bloc(s) dépassent le budget de "
                            f"{max_textures} textures."
                        )
                    else:
                        st.success(
                            f"✅ Tous les blocs respectent le budget de "
                            f"{max_textures} textures."
                        )

        # ── Affichage résultat standard (sans Reforger) ──────────────────────
        elif not has_reforger and "texture_preview" in st.session_state.last_generated:
            preview_path = st.session_state.last_generated["texture_preview"]
            result       = st.session_state.last_generated.get("texture_preview_result")

            img_preview = load_image(preview_path)
            if img_preview:
                st.image(img_preview, caption="Aperçu Texture Terrain 2D",
                         use_container_width=True)
                with open(preview_path, "rb") as fh:
                    st.download_button(
                        "📥 Télécharger PNG", fh.read(),
                        file_name=Path(preview_path).name, mime="image/png",
                        key="dl_texture_preview",
                    )

            if result:
                stats = result.stats
                st.markdown("#### Répartition des matériaux")
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("🌊 Eau",   f"{stats['eau_pct']:.1f}%")
                c2.metric("🌱 Herbe", f"{stats['herbe_pct']:.1f}%")
                c3.metric("🟫 Sol",   f"{stats['terre_pct']:.1f}%")
                c4.metric("🪨 Roche", f"{stats['roche_pct']:.1f}%")
                c5.metric("❄️ Neige", f"{stats['neige_pct']:.1f}%")

                targets = stats.get("targets", {})
                if targets:
                    key_map = {
                        "prairie": "herbe_pct", "terre": "terre_pct",
                        "roche": "roche_pct", "neige": "neige_pct",
                    }
                    rows_std = []
                    for mat, (lo, hi) in targets.items():
                        actual = stats.get(key_map.get(mat, mat + "_pct"), 0.0)
                        status = "✅" if lo <= actual <= hi else ("⬆️" if actual > hi else "⬇️")
                        rows_std.append({
                            "Matériau": mat.capitalize(),
                            "Min (%)": lo, "Max (%)": hi,
                            "Obtenu (%)": round(actual, 1), "Statut": status,
                        })
                    st.markdown("#### Calibration — Cibles vs Obtenu")
                    st.dataframe(pd.DataFrame(rows_std), use_container_width=True,
                                 hide_index=True)

    # ========================================================================
    # ONGLET CALQUES & EXPORT — sous-onglets : Texture / TMAT / SatMap / Reconstruction
    # ========================================================================

    with tab_export:
        _e_tex, _e_tmat, _e_sat, _e_recon, _e_fusion = st.tabs([
            "🖼️ Calque Texture", "🎨 Calque TMAT", "🛰️ Calque SatMap",
            "🗺️ Carte Reconstruction", "🔀 Fusion Masques",
        ])

    with _e_tex:
        import io
        import zipfile
        from reforger_texture_budget import TEXTURE_ORDER, TEXTURE_LABELS

        st.markdown("### 🖼️ Calque Texture — Masques morphologiques")

        tr = st.session_state.get("tex_reforger")

        # ── Affichage des masques existants dans le dossier projet ───────────
        _proj_masks_existing = None
        if st.session_state.current_project_path:
            _pmd = Path(st.session_state.current_project_path) / "masks"
            _existing_pngs = sorted(_pmd.glob("[0-9]*.png")) if _pmd.exists() else []
            if _existing_pngs:
                _proj_masks_existing = _existing_pngs

        if _proj_masks_existing and (tr is None or "constrained_scores" not in tr):
            st.info(
                "Masques trouvés dans le dossier projet. "
                "Générez l'**Aperçu Texture** pour régénérer avec les paramètres actuels."
            )
            n_cols = 5
            for _rs in range(0, len(_proj_masks_existing), n_cols):
                _ccols = st.columns(n_cols)
                for _jj, _fp in enumerate(_proj_masks_existing[_rs:_rs + n_cols]):
                    with _ccols[_jj]:
                        _raw = np.array(Image.open(_fp))
                        # Convertir 16-bit → 8-bit pour st.image (JPEG ne supporte pas I;16)
                        if _raw.dtype == np.uint16:
                            _disp8 = (_raw >> 8).astype(np.uint8)
                        else:
                            _disp8 = _raw.astype(np.uint8)
                        st.image(_disp8, caption=_fp.stem, use_container_width=True)
                        with open(_fp, "rb") as _fh:
                            st.download_button(
                                "⬇️ PNG", _fh.read(),
                                file_name=_fp.name, mime="image/png",
                                key=f"dl_existing_{_fp.stem}",
                                use_container_width=True,
                            )
        elif tr is None or "constrained_scores" not in tr:
            st.info(
                "Générez d'abord l'**Aperçu Texture** (onglet 🖼️) avec les données "
                "Reforger actives pour activer l'export des masques."
            )
        else:
            constrained = tr["constrained_scores"]
            biome_cfg   = tr["biome_config"]
            rd_stored   = tr["reforger_data"]
            h_px, w_px  = next(iter(constrained.values())).shape

            # ── Récapitulatif couverture + ordre d'import ────────────────────
            import pandas as pd
            rows_cov = []
            for i, role in enumerate(TEXTURE_ORDER):
                if role not in constrained:
                    continue
                coverage = float(np.mean(constrained[role] > 0.005)) * 100
                rows_cov.append({
                    "Ordre": f"{i+1:02d}",
                    "Rôle":  TEXTURE_LABELS.get(role, role),
                    "Texture .emat": biome_cfg.get(role, "???"),
                    "Couverture %": f"{coverage:.1f}",
                    "Actif": "✅" if coverage > 0.1 else "—",
                })

            st.markdown("#### Ordre d'import Workbench")
            st.caption(
                "Importer dans cet ordre : couches de base en premier, "
                "surcharges (roche, neige) en dernier. "
                "Chaque import remplace entièrement le masque de ce matériau sur toute la carte."
            )
            st.dataframe(pd.DataFrame(rows_cov), use_container_width=True, hide_index=True)

            # ── Options export ───────────────────────────────────────────────
            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                export_active_only = st.checkbox(
                    "Rôles actifs uniquement", value=True,
                    help="N'exporte que les rôles avec couverture > 0.1%",
                )
            with mc2:
                bit_16 = st.checkbox(
                    "PNG 16 bits", value=True,
                    help="Recommandé Enfusion (0-65535). 8 bits fonctionne mais moins précis.",
                )
            with mc3:
                surf_px = rd_stored.get("surface_total_px")
                hires_ok = surf_px is not None
                _hires_mem_mb = (surf_px[0] * surf_px[1] * 2) // (1024 * 1024) if surf_px else 0
                export_hires = st.checkbox(
                    f"Haute résolution ({surf_px[0]}×{surf_px[1]} px, ~{_hires_mem_mb} Mo/masque)" if surf_px else "Haute résolution",
                    value=False, disabled=not hires_ok,
                    help="Export à la résolution native surface map. Export bloc par bloc — pas d'OOM. Requis pour éviter les conflits QTRE dans WB.",
                )

            # ── Texture de base pré-peinte ────────────────────────────────────
            # Protocole WB : peindre une texture à 100% sur toute la carte avant
            # d'appliquer les masques. Cette texture occupe 1 slot QTRE permanent,
            # il ne faut donc NI exporter son masque NI l'inclure dans le budget 4.
            # → Régler le slider "Budget textures/bloc" à 3 avant de générer l'aperçu.
            st.markdown("---")
            _all_pipeline_roles = [r for r in TEXTURE_ORDER if r in constrained]
            base_tex_enabled = st.checkbox(
                "Texture de base pré-peinte (protocole WB anti-conflit)",
                value=True,
                key="export_base_tex_enabled",
                help=(
                    "Si vous peignez d'abord une texture sur toute la carte dans WB "
                    "(pour écraser default.emat), cocher cette case supprime son masque à l'export. "
                    "Réduisez aussi le budget à 3 textures/bloc dans l'onglet Aperçu Texture."
                ),
            )
            base_role_export = None
            if base_tex_enabled:
                _default_base_idx = _all_pipeline_roles.index("prairie") if "prairie" in _all_pipeline_roles else 0
                base_role_export = st.selectbox(
                    "Rôle de la texture de base",
                    _all_pipeline_roles,
                    index=_default_base_idx,
                    format_func=lambda r: f"{TEXTURE_LABELS.get(r, r)}  —  {biome_cfg.get(r, '?')}",
                    key="export_base_role_sel",
                )
                _base_emat_name = biome_cfg.get(base_role_export, "Grass_02.emat")
                st.info(
                    f"📋 **Protocole WB** : peignez **{_base_emat_name}** à 100% sur tout le terrain, "
                    f"puis importez les masques ci-dessous par dessus.  \n"
                    f"⚠️ Réglez le **budget à 3 textures/bloc** dans Aperçu Texture avant de re-générer "
                    f"(base + 3 masques = 4 slots QTRE max)."
                )

            # Avertissement si l'aperçu a été calculé sans le budget base
            if base_tex_enabled and base_role_export:
                _stored_max = tr.get("max_textures", 4)
                if _stored_max > 3:
                    st.warning(
                        f"⚠️ L'aperçu a été calculé avec budget = {_stored_max}. "
                        f"Avec la texture de base, le pipeline utilise maintenant automatiquement "
                        f"max-1 slots pour les masques. **Re-générez l'aperçu** pour valider "
                        f"(le budget textures/bloc peut rester à {_stored_max})."
                    )

            # ── Export vers projet ───────────────────────────────────────────
            proj_masks_dir = None
            export_to_project = False
            if st.session_state.current_project_path:
                proj_masks_dir = Path(st.session_state.current_project_path) / "masks"
                export_to_project = st.checkbox(
                    f"Copier dans le projet (masks/)", value=True,
                )

            # ── Génération ───────────────────────────────────────────────────
            if st.button("🎭 Générer masques PNG", key="gen_masks"):
                try:
                    with st.spinner("⏳ Génération des masques..."):
                        import cv2 as _cv2

                        out_dir = Path(get_output_dir()) / f"masks_{format_timestamp()}"
                        out_dir.mkdir(parents=True, exist_ok=True)
                        if export_to_project and proj_masks_dir:
                            proj_masks_dir.mkdir(parents=True, exist_ok=True)

                        generated = []
                        manifest_lines = [
                            f"Masques PNG — profil {tr['climate_profile']}",
                            f"Heightmap  : {w_px} × {h_px} px",
                            f"Format     : {'16 bits (uint16)' if bit_16 else '8 bits (uint8)'}",
                            f"Résolution : {'surface map Reforger' if export_hires and hires_ok else 'heightmap'}",
                            "",
                            "Masques générés (ordre de numérotation) :",
                            "─" * 55,
                        ]

                        for i, role in enumerate(TEXTURE_ORDER):
                            if role not in constrained:
                                continue
                            arr      = constrained[role]
                            coverage = float(np.mean(arr > 0.005)) * 100
                            emat     = biome_cfg.get(role, role)
                            label    = TEXTURE_LABELS.get(role, role)

                            # Skip la texture de base (pré-peinte dans WB, pas de masque)
                            if base_tex_enabled and base_role_export and role == base_role_export:
                                manifest_lines.append(
                                    f"  {i+1:02d}. {label:25s} → {emat:35s}  — BASE pré-peinte (masque non exporté)"
                                )
                                continue

                            if export_active_only and coverage <= 0.1:
                                manifest_lines.append(
                                    f"  {i+1:02d}. {label:25s} — ignoré ({coverage:.2f}%)"
                                )
                                continue

                            emat_slug = emat.replace(".emat", "").replace("CUSTOM_", "custom_")
                            filename  = f"{i+1:02d}_{role}_{emat_slug}.png"
                            path      = out_dir / filename

                            if export_hires and hires_ok and surf_px:
                                # Export bloc par bloc à la résolution surface map native.
                                # Un cv2.resize global (INTER_LINEAR) crée des fuites non-nulles
                                # aux frontières des blocs budget (valeur 0 → voisin non-nul
                                # → gradient). WB compte ces fuites comme une 5ème texture → conflit QTRE.
                                # En traitant chaque bloc indépendamment, les blocs exclus restent
                                # strictement à zéro dans l'image finale.
                                _sw_e, _sh_e = surf_px[0], surf_px[1]
                                _bsm_e = rd_stored.get("block_size_m", 32)
                                _bsm_e = float(_bsm_e[0] if isinstance(_bsm_e, (list, tuple)) else _bsm_e)
                                _bpx_e = max(1, round(_bsm_e / max(float(cell_m_st), 1e-6)))
                                _aH_e, _aW_e = arr.shape
                                _scx_e = (_sw_e - 1) / max(_aW_e - 1, 1)
                                _scy_e = (_sh_e - 1) / max(_aH_e - 1, 1)
                                _dt_e  = np.uint16 if bit_16 else np.uint8
                                _mv_e  = 65535    if bit_16 else 255
                                img_data = np.zeros((_sh_e, _sw_e), dtype=_dt_e)
                                for _by_e in range((_aH_e + _bpx_e - 1) // _bpx_e):
                                    for _bx_e in range((_aW_e + _bpx_e - 1) // _bpx_e):
                                        _esy0 = _by_e * _bpx_e
                                        _esy1 = min(_esy0 + _bpx_e, _aH_e)
                                        _esx0 = _bx_e * _bpx_e
                                        _esx1 = min(_esx0 + _bpx_e, _aW_e)
                                        _eblk = arr[_esy0:_esy1, _esx0:_esx1]
                                        if not np.any(_eblk > 0):
                                            continue
                                        _ety0 = min(round(_esy0 * _scy_e), _sh_e)
                                        _ety1 = min(round(_esy1 * _scy_e), _sh_e)
                                        _etx0 = min(round(_esx0 * _scx_e), _sw_e)
                                        _etx1 = min(round(_esx1 * _scx_e), _sw_e)
                                        if _ety1 <= _ety0 or _etx1 <= _etx0:
                                            continue
                                        _eup = _cv2.resize(
                                            _eblk, (_etx1 - _etx0, _ety1 - _ety0),
                                            interpolation=_cv2.INTER_LINEAR,
                                        )
                                        img_data[_ety0:_ety1, _etx0:_etx1] = (
                                            _eup * _mv_e
                                        ).clip(0, _mv_e).astype(_dt_e)
                            else:
                                if bit_16:
                                    img_data = (arr * 65535).clip(0, 65535).astype(np.uint16)
                                else:
                                    img_data = (arr * 255).clip(0, 255).astype(np.uint8)

                            if img_data.dtype == np.uint8:
                                Image.fromarray(img_data, mode="L").save(str(path))
                            else:
                                Image.fromarray(img_data).save(str(path))

                            if export_to_project and proj_masks_dir:
                                import shutil as _shutil
                                _shutil.copy2(str(path), str(proj_masks_dir / filename))

                            generated.append((role, emat, str(path), coverage))
                            manifest_lines.append(
                                f"  {i+1:02d}. {label:25s} → {emat:35s}  {coverage:.1f}%"
                            )

                        # ── Ordre d'import Workbench recommandé ─────────────
                        if base_tex_enabled and base_role_export:
                            _base_role  = base_role_export
                            _base_emat  = biome_cfg.get(_base_role, "Grass_02.emat")
                            _base_label = TEXTURE_LABELS.get(_base_role, _base_role)
                            _import_list = sorted(
                                [(r, e, c) for r, e, _, c in generated],
                                key=lambda x: x[2],   # couverture croissante
                            )
                            manifest_lines += [
                                "",
                                "Ordre d'import Workbench recommandé :",
                                "─" * 55,
                                f"  0. [BASE]   Peindre {_base_label} ({_base_emat}) = 100% sur toute la carte",
                            ]
                            for _step, (_r, _e, _c) in enumerate(_import_list, 1):
                                _lbl = TEXTURE_LABELS.get(_r, _r)
                                manifest_lines.append(
                                    f"  {_step}. {_lbl:25s} → {_e:35s}  ({_c:.1f}%)"
                                )
                        else:
                            _base_role  = "prairie"
                            _base_label = TEXTURE_LABELS.get(_base_role, _base_role)
                            _base_emat  = next((e for r, e, _, _ in generated if r == _base_role), "Grass_02.emat")
                            _import_list = sorted(
                                [(r, e, c) for r, e, _, c in generated if r != _base_role],
                                key=lambda x: x[2],
                            )
                            manifest_lines += [
                                "",
                                "Ordre d'import Workbench recommandé :",
                                "─" * 55,
                                f"  0. [RESET]  Peindre {_base_label} ({_base_emat}) = 100% sur toute la map",
                            ]
                            for _step, (_r, _e, _c) in enumerate(_import_list, 1):
                                _lbl = TEXTURE_LABELS.get(_r, _r)
                                manifest_lines.append(
                                    f"  {_step}. {_lbl:25s} → {_e:35s}  ({_c:.1f}%)"
                                )
                            manifest_lines.append(
                                f"  {len(_import_list)+1}. [RESIDU] {_base_label:24s} → {_base_emat:35s}  — ne pas importer"
                            )

                        manifest_path = out_dir / "manifest.txt"
                        manifest_path.write_text("\n".join(manifest_lines), encoding="utf-8")
                        if export_to_project and proj_masks_dir:
                            import shutil as _shutil
                            _shutil.copy2(str(manifest_path), str(proj_masks_dir / "manifest.txt"))

                        st.session_state.last_generated["masks"] = {
                            "dir":      str(out_dir),
                            "files":    generated,
                            "manifest": str(manifest_path),
                            "bit_16":   bit_16,
                            "proj_dir": str(proj_masks_dir) if (export_to_project and proj_masks_dir) else None,
                        }
                    st.success(f"✅ {len(generated)} masques générés dans {out_dir.name}/")

                except Exception as e:
                    st.error(f"❌ Erreur: {e}")
                    st.exception(e)

            # ── Affichage résultats ──────────────────────────────────────────
            if "masks" in st.session_state.last_generated:
                masks_info = st.session_state.last_generated["masks"]
                files      = masks_info["files"]

                st.markdown("#### Masques générés")

                n_cols = 5
                for row_start in range(0, len(files), n_cols):
                    cols_th = st.columns(n_cols)
                    for j, (role, emat, path, coverage) in enumerate(
                        files[row_start: row_start + n_cols]
                    ):
                        with cols_th[j]:
                            arr_disp = (constrained.get(role, np.zeros((4, 4))) * 255).astype(np.uint8)
                            st.image(
                                arr_disp,
                                caption=f"{TEXTURE_LABELS.get(role, role)}\n"
                                        f"{emat.replace('.emat', '')}  {coverage:.0f}%",
                                use_container_width=True,
                            )
                            with open(path, "rb") as fh:
                                st.download_button(
                                    "⬇️ PNG", fh.read(),
                                    file_name=Path(path).name,
                                    mime="image/png",
                                    key=f"dl_mask_{role}",
                                    use_container_width=True,
                                )

                # ZIP masques + manifest
                st.markdown("---")
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for role, emat, path, _ in files:
                        zf.write(path, Path(path).name)
                    if masks_info.get("manifest"):
                        zf.write(masks_info["manifest"], "manifest.txt")
                zip_buf.seek(0)

                st.download_button(
                    "📦 Télécharger tous les masques (.zip)",
                    zip_buf.getvalue(),
                    file_name=f"masks_{tr['climate_profile']}_{format_timestamp()}.zip",
                    mime="application/zip",
                    key="dl_masks_zip",
                    use_container_width=True,
                )

                with st.expander("📋 Manifest — récapitulatif import"):
                    if masks_info.get("manifest"):
                        st.text(Path(masks_info["manifest"]).read_text(encoding="utf-8"))

                # ── Diagnostic QTRE ───────────────────────────────────────────
                with st.expander("Diagnostic QTRE — Vérifier les masques", expanded=True):
                    _diag_dir   = Path(masks_info["dir"])
                    _diag_files = sorted(_diag_dir.glob("[0-9]*.png"))
                    st.caption(f"{len(_diag_files)} masques dans `{_diag_dir.name}`")
                    if not _diag_files:
                        st.info("Aucun masque numéroté trouvé dans le dossier d'export.")
                    else:
                        _diag_key = f"_qtre_diag_{_diag_dir}"
                        if st.button("Vérifier les masques QTRE", key="btn_diag_qtre"):
                            with st.spinner(f"Analyse de {len(_diag_files)} masques…"):
                                _THOLD = 1.0 / 65535 * 256
                                _dn, _da = [], []
                                for _fp in _diag_files:
                                    _a = np.array(Image.open(_fp), dtype=np.float32)
                                    _dn.append(_fp.name)
                                    _da.append(_a / (65535.0 if _a.max() > 255 else 255.0))
                                _H, _W = _da[0].shape
                                _bpx = 32 if _H <= 9000 else 127
                                _ny = (_H + _bpx - 1) // _bpx
                                _nx = (_W + _bpx - 1) // _bpx
                                _tot = _ny * _nx
                                _stk = np.stack(_da, axis=0)
                                _ph  = _ny * _bpx - _H
                                _pw  = _nx * _bpx - _W
                                _sp  = np.pad(_stk, ((0, 0), (0, _ph), (0, _pw)))
                                _bm  = _sp.reshape(len(_dn), _ny, _bpx, _nx, _bpx).mean(axis=(2, 4))
                                _cnt = (_bm > _THOLD).sum(axis=0)
                                _vyx = np.argwhere(_cnt > 4).tolist()
                                _vdrops = []
                                for _by, _bx in _vyx:
                                    _sidx = np.argsort(_bm[:, _by, _bx])[::-1]
                                    _aidx = [i for i in _sidx if _bm[i, _by, _bx] > _THOLD]
                                    _vdrops.append((_by, _bx, [_dn[i] for i in _aidx[4:]]))
                                st.session_state[_diag_key] = {
                                    "nv": len(_vyx), "pct": len(_vyx) / _tot * 100,
                                    "total": _tot, "block_px": _bpx,
                                    "H": _H, "W": _W, "vdrops": _vdrops,
                                }

                        if _diag_key in st.session_state:
                            _dg = st.session_state[_diag_key]
                            _qc1, _qc2, _qc3 = st.columns(3)
                            _qc1.metric("Blocs 32m analysés", f"{_dg['total']:,}")
                            _qc2.metric("Violations (>4 tex./bloc)", str(_dg["nv"]),
                                        delta="OK" if _dg["nv"] == 0 else f"{_dg['pct']:.2f}%",
                                        delta_color="normal" if _dg["nv"] == 0 else "inverse")
                            _qc3.metric("Taux", f"{_dg['pct']:.3f}%")

                            if _dg["nv"] == 0:
                                st.success("Aucune violation QTRE — masques prets pour l'import Workbench.")
                            else:
                                st.warning(
                                    f"{_dg['nv']} blocs en conflit ({_dg['pct']:.2f}%). "
                                    "La correction conserve les 4 textures dominantes par bloc et renormalise."
                                )
                                if st.button("Corriger et re-sauvegarder", key="btn_fix_qtre"):
                                    with st.spinner("Correction en cours…"):
                                        _cd = Path(masks_info["dir"])
                                        _cn2, _ca2 = [], []
                                        for _fp2 in sorted(_cd.glob("[0-9]*.png")):
                                            _a2 = np.array(Image.open(_fp2), dtype=np.float32)
                                            _cn2.append(_fp2.name)
                                            _ca2.append(_a2 / (65535.0 if _a2.max() > 255 else 255.0))
                                        _cr = {n: a.copy() for n, a in zip(_cn2, _ca2)}
                                        _bpx2 = _dg["block_px"]
                                        _H2, _W2 = _dg["H"], _dg["W"]
                                        for _by2, _bx2, _drop in _dg["vdrops"]:
                                            _y0 = _by2 * _bpx2; _y1 = min(_y0 + _bpx2, _H2)
                                            _x0 = _bx2 * _bpx2; _x1 = min(_x0 + _bpx2, _W2)
                                            for _n in _drop:
                                                if _n in _cr:
                                                    _cr[_n][_y0:_y1, _x0:_x1] = 0.0
                                            _kns = [n for n in _cn2 if n not in set(_drop)]
                                            _s2  = sum(_cr[n][_y0:_y1, _x0:_x1] for n in _kns)
                                            _s2  = np.maximum(_s2, 1e-8)
                                            for _n in _kns:
                                                _cr[_n][_y0:_y1, _x0:_x1] /= _s2
                                        _is16 = masks_info.get("bit_16", True)
                                        for _n, _a in _cr.items():
                                            _op = _cd / _n
                                            if _is16:
                                                Image.fromarray((_a * 65535).clip(0, 65535).astype(np.uint16)).save(str(_op))
                                            else:
                                                Image.fromarray((_a * 255).clip(0, 255).astype(np.uint8), "L").save(str(_op))
                                        _pd = masks_info.get("proj_dir")
                                        if _pd:
                                            import shutil as _sh2
                                            for _n in _cr:
                                                _sh2.copy2(str(_cd / _n), str(Path(_pd) / _n))
                                        del st.session_state[_diag_key]
                                        st.success(f"{len(_cr)} masques corriges dans {_cd.name}/")
                                        st.rerun()

        # ── Correctif QTRE depuis error.png Workbench ────────────────────────
        import io as _io_fus
        import zipfile as _zp_fus
        _QTRE_ROLE_CLR = {
            "fond_marin": (55,100,155), "sable": (178,162,128),
            "cotier": (108,142,72),   "galets": (155,148,130),
            "prairie": (68,125,52),     "lande": (90,140,60),
            "foret": (34,85,34),      "erosion": (139,105,70),
            "debris": (120,100,80),   "roche": (110,100,90),
            "neige": (230,230,245),   "eau": (55,100,200),
        }
        st.markdown("---")
        st.markdown("### 🔧 Correctif QTRE depuis error.png Workbench")
        st.caption(
            "Pointez vers le dossier contenant vos masques WB. "
            "Les fichiers nommés **error_xxx.png** et **defaut.png** sont détectés automatiquement. "
            "L'outil visualise les zones en conflit et corrige les masques (top-4 par bloc)."
        )

        _qfix_folder = st.text_input(
            "Dossier masques WB (contient les mask + error_xxx.png)",
            key="qfix_folder", placeholder="ex: D:/WB/ZBK/masks/",
        )
        _qf3, _qf4, _qf5, _qf6 = st.columns(4)
        _qfix_bpx  = _qf3.slider("Taille bloc (px)", 8, 128, 32, 8, key="qfix_bpx")
        _qfix_thr  = _qf4.slider("Seuil actif (%)", 0.01, 5.0, 0.1, 0.01, key="qfix_thr") / 100.0
        _qfix_bits = _qf5.radio("Format", ["8-bit", "16-bit"], index=1,
                                 horizontal=True, key="qfix_out_bits")
        _qfix_base = _qf6.number_input(
            "Couches de base (non exportées)",
            min_value=0, max_value=3, value=1, step=1, key="qfix_base",
            help="Textures peintes en base dans Workbench (ex: prairie = 1). "
                 "Budget effectif = 4 − base.",
        )
        _qfix_budget = 4 - int(_qfix_base)

        _qfix_pngs = []
        _qfix_err_pngs = []
        _ERR_KEYWORDS = ("error", "defaut", "default")
        if _qfix_folder and Path(_qfix_folder).is_dir():
            _all_pngs = sorted(Path(_qfix_folder).glob("*.png"))
            _qfix_pngs     = [p for p in _all_pngs
                              if not any(k in p.stem.lower() for k in _ERR_KEYWORDS)]
            _qfix_err_pngs = [p for p in _all_pngs
                              if any(k in p.stem.lower() for k in _ERR_KEYWORDS)]

        _qfix_masks_ok = len(_qfix_pngs) > 0
        _qfix_err_ok   = len(_qfix_err_pngs) > 0
        if _qfix_masks_ok:
            st.caption(
                f"{len(_qfix_pngs)} masques texture + "
                f"{len(_qfix_err_pngs)} masque(s) erreur/défaut détectés "
                f"({', '.join(p.name for p in _qfix_err_pngs)})."
            )
        if _qfix_masks_ok and not _qfix_err_ok:
            st.warning("Aucun fichier error_xxx/defaut.png trouvé — seul le diagnostic QTRE sera affiché.")

        _qba, _qbc = st.columns(2)

        if _qba.button("🔍 Analyser", key="btn_qfix_analyse", disabled=not _qfix_masks_ok):
            try:
                from reforger_texture_budget import mat_to_role as _qm2r
                Image.MAX_IMAGE_PIXELS = None

                _qref = Image.open(str(_qfix_pngs[0])).convert("L")
                _QW, _QH = _qref.size
                del _qref

                _qerr_arr  = np.zeros((_QH, _QW), dtype=np.float32)
                _qerr_natW = 0
                _qerr_natH = 0
                _qerr_nat  = None
                for _qep in _qfix_err_pngs:
                    _is_block_err = "error" in _qep.stem.lower()
                    _qei = Image.open(str(_qep)).convert("L")
                    _qeW, _qeH = _qei.size
                    if _is_block_err:
                        # Small file (256×256) — safe to load as numpy for grid definition
                        if _qerr_nat is None:
                            _qerr_natW, _qerr_natH = _qeW, _qeH
                            _qerr_nat = np.zeros((_qeH, _qeW), dtype=np.float32)
                        _qei_a = np.array(_qei, dtype=np.float32) / 255.0
                        if (_qeH, _qeW) == (_qerr_natH, _qerr_natW):
                            _qerr_nat = np.maximum(_qerr_nat, _qei_a)
                        del _qei_a
                    # All files contribute to display overlay — downsample in PIL to avoid OOM
                    _qei_needs_del = False
                    if _qeW > _QW or _qeH > _QH:
                        _qei_sm = _qei.resize((_QW, _QH), Image.BOX)
                        _qei_needs_del = True
                    else:
                        _qei_sm = _qei
                    _qei_up = np.array(
                        _qei_sm.resize((_QW, _QH), Image.NEAREST), dtype=np.float32
                    ) / 255.0
                    _qerr_arr = np.maximum(_qerr_arr, _qei_up)
                    if _qei_needs_del:
                        del _qei_sm
                    del _qei, _qei_up

                _qBW = _qerr_natW if _qfix_err_ok and _qerr_natW > 0 else None
                _qBH = _qerr_natH if _qfix_err_ok and _qerr_natH > 0 else None
                _qfix_bpx_used = int(_QW / _qBW) if _qBW else _qfix_bpx
                st.info(
                    f"Grille de blocs : **{_qBW}×{_qBH}** "
                    f"({'grille exacte Reforger' if _qfix_err_ok else 'slider'})"
                )

                with st.spinner("Chargement des masques…"):
                    _qmasks = {}
                    _qroles = {}
                    for _qp in _qfix_pngs:
                        _qi = Image.open(str(_qp)).convert("L")
                        if (_qi.height, _qi.width) != (_QH, _QW):
                            _qi = _qi.resize((_QW, _QH), Image.BILINEAR)
                        _qmasks[_qp.stem] = np.array(_qi, dtype=np.float32) / 255.0
                        _qroles[_qp.stem] = _qm2r(_qp.stem)
                        del _qi

                with st.spinner("Analyse QTRE…"):
                    _qstems = list(_qmasks.keys())
                    _qGW = _qBW if _qBW else max(1, _QW // _qfix_bpx_used)
                    _qGH = _qBH if _qBH else max(1, _QH // _qfix_bpx_used)
                    _qblk = {}
                    for _qstem in _qstems:
                        _qds = Image.fromarray(
                            (_qmasks[_qstem] * 255).clip(0, 255).astype(np.uint8)
                        ).resize((_qGW, _qGH), Image.BOX)
                        _qblk[_qstem] = np.array(_qds, dtype=np.float32) / 255.0
                        del _qds

                    _qbm_stk  = np.stack([_qblk[s] for s in _qstems], axis=0)
                    _qactive  = _qbm_stk > _qfix_thr
                    _qviol    = _qactive.sum(axis=0) > _qfix_budget

                    if _qerr_nat is not None and _qerr_nat.shape == (_qGH, _qGW):
                        _qviol_combined = _qviol | (_qerr_nat > 0.5)
                    else:
                        _qviol_combined = _qviol

                    _qheat = np.zeros((_QH, _QW, 3), dtype=np.float32)
                    for _qstem2 in _qstems:
                        _qrl2 = _qroles[_qstem2]
                        _qclr = np.array(_QTRE_ROLE_CLR.get(_qrl2, (128, 128, 128)), np.float32)
                        _qheat += _qmasks[_qstem2][..., np.newaxis] * _qclr
                    _qheat = np.clip(_qheat, 0, 255).astype(np.uint8)

                    _qviol_up = np.array(
                        Image.fromarray(_qviol_combined.astype(np.uint8) * 255)
                        .resize((_QW, _QH), Image.NEAREST), dtype=bool
                    )
                    _qerr_px  = _qerr_arr > 0.5
                    _qmask_ov = _qviol_up | _qerr_px
                    _qheat[_qmask_ov] = np.clip(
                        _qheat[_qmask_ov].astype(np.float32) * 0.25
                        + np.array([220, 30, 30], np.float32) * 0.75,
                        0, 255,
                    ).astype(np.uint8)

                    _qconflict = {}
                    for _qi3, _qstem3 in enumerate(_qstems):
                        _qcnt = int((_qactive[_qi3] & _qviol_combined).sum())
                        if _qcnt:
                            _qconflict[_qstem3] = _qcnt

                    st.session_state["qfix_result"] = {
                        "heat":       _qheat,
                        "n_viol":     int(_qviol_combined.sum()),
                        "n_viol_our": int(_qviol.sum()),
                        "n_err_px":   int(_qerr_px.sum()),
                        "conflict":   _qconflict,
                        "masks":      _qmasks,
                        "blk":        _qblk,
                        "viol":       _qviol_combined,
                        "stems":      _qstems,
                        "roles":      _qroles,
                        "GW": _qGW, "GH": _qGH,
                        "QH": _QH,  "QW": _QW,
                    }
                    del _qviol_up, _qerr_px, _qmask_ov

            except Exception as _qex:
                st.error(f"Erreur analyse : {_qex}")
                st.exception(_qex)

        if "qfix_result" in st.session_state:
            _qres = st.session_state["qfix_result"]
            st.image(_qres["heat"],
                     caption="Composite masques + zones en erreur (rouge)",
                     use_container_width=True)
            _qmc1, _qmc2, _qmc3 = st.columns(3)
            _qmc1.metric("Violations (notre calcul)", _qres.get("n_viol_our", _qres["n_viol"]))
            _qmc2.metric("Violations (+ Reforger)",   _qres["n_viol"],
                         delta_color="inverse" if _qres["n_viol"] > 0 else "normal")
            _qmc3.metric("Pixels error masks",         _qres["n_err_px"])

            if _qres["conflict"]:
                st.markdown("**Textures dans les blocs en conflit :**")
                for _qstem4, _qcnt4 in sorted(_qres["conflict"].items(), key=lambda x: -x[1]):
                    _qrl4 = _qres["roles"].get(_qstem4, _qstem4)
                    st.caption(f"  • {TEXTURE_LABELS.get(_qrl4, _qrl4)} (`{_qstem4}`) — {_qcnt4} blocs")

            if _qbc.button("✅ Corriger et exporter", key="btn_qfix_correct"):
                try:
                    _qmk2  = _qres["masks"]
                    _qst2  = _qres["stems"]
                    _qblk2 = _qres["blk"]
                    _qv2   = _qres["viol"]
                    _QH3, _QW3 = _qres["QH"], _qres["QW"]
                    _qGW2, _qGH2 = _qres["GW"], _qres["GH"]

                    _qkeep = {s: np.ones((_qGH2, _qGW2), dtype=np.float32) for s in _qst2}
                    with st.spinner("Calcul des keep-maps…"):
                        for _qgy in range(_qGH2):
                            for _qgx in range(_qGW2):
                                if not _qv2[_qgy, _qgx]:
                                    continue
                                _qmns2 = {s: float(_qblk2[s][_qgy, _qgx]) for s in _qst2}
                                _qtop4 = {s for s, _ in
                                          sorted(_qmns2.items(), key=lambda x: -x[1])[:_qfix_budget]}
                                for _qs in _qst2:
                                    if _qs not in _qtop4:
                                        _qkeep[_qs][_qgy, _qgx] = 0.0

                    _qfixed = {}
                    with st.spinner("Application et renormalisation…"):
                        for _qs3 in _qst2:
                            _qkm_up = np.array(
                                Image.fromarray((_qkeep[_qs3] * 255).astype(np.uint8))
                                .resize((_QW3, _QH3), Image.NEAREST),
                                dtype=np.float32
                            ) / 255.0
                            _qfixed[_qs3] = _qmk2[_qs3] * _qkm_up
                            del _qkm_up
                        _qtot_f = sum(_qfixed.values()) + 1e-8
                        for _qs3 in _qst2:
                            _qfixed[_qs3] = (_qfixed[_qs3] / _qtot_f).astype(np.float32)
                        del _qtot_f

                    _qv2_check = np.zeros((_qGH2, _qGW2), dtype=np.int32)
                    for _qs3 in _qst2:
                        _qds2 = np.array(
                            Image.fromarray((_qfixed[_qs3] * 255).astype(np.uint8))
                            .resize((_qGW2, _qGH2), Image.BOX), dtype=np.float32
                        ) / 255.0
                        _qv2_check += (_qds2 > _qfix_thr).astype(np.int32)
                        del _qds2
                    _qviol2_n = int((_qv2_check > _qfix_budget).sum())
                    del _qv2_check
                    if _qviol2_n == 0:
                        st.success("✅ Validation : 0 violation à la résolution Reforger.")
                    else:
                        st.warning(
                            f"⚠️ {_qviol2_n} blocs encore en violation "
                            f"(seuil {_qfix_thr*100:.2f}%)."
                        )

                    with st.spinner("Export…"):
                        _qout = Path(get_output_dir()) / f"qfix_{format_timestamp()}"
                        _qout.mkdir(parents=True, exist_ok=True)
                        for _qp5 in _qfix_pngs:
                            _qa5 = _qfixed[_qp5.stem]
                            _qo5 = (
                                (_qa5 * 65535).clip(0, 65535).astype(np.uint16)
                                if _qfix_bits == "16-bit"
                                else (_qa5 * 255).clip(0, 255).astype(np.uint8)
                            )
                            Image.fromarray(_qo5).save(str(_qout / _qp5.name))
                            del _qo5
                        _qproj2 = st.session_state.get("current_project_path")
                        if _qproj2:
                            import shutil as _qsh2
                            _qmdir3 = Path(_qproj2) / "masks" / "fusion"
                            _qmdir3.mkdir(parents=True, exist_ok=True)
                            for _qsp2 in _qout.glob("*.png"):
                                _qsh2.copy2(str(_qsp2), str(_qmdir3 / _qsp2.name))
                        _qfzbuf = _io_fus.BytesIO()
                        with _zp_fus.ZipFile(_qfzbuf, "w", _zp_fus.ZIP_DEFLATED) as _qzff2:
                            for _qfp5 in sorted(_qout.glob("*.png")):
                                _qzff2.write(str(_qfp5), _qfp5.name)
                        _qfzbuf.seek(0)
                    st.success(f"✓ {len(_qfix_pngs)} masques corrigés → `{_qout.name}/`")
                    st.download_button(
                        "⬇️ Télécharger masques corrigés (.zip)",
                        _qfzbuf.getvalue(),
                        file_name=f"qfix_{format_timestamp()}.zip",
                        mime="application/zip",
                        key="dl_qfix_zip",
                        use_container_width=True,
                    )

                except Exception as _qex2:
                    st.error(f"Erreur correction : {_qex2}")
                    st.exception(_qex2)

    with _e_tmat:
        from reforger_texture_budget import (
            find_terr_files, parse_terr_materials,
            find_ttile_files, read_tmat_grid, render_tmat_rgb,
            render_tmat_rgb_blended, mat_to_role, tmat_cleanup_scan,
            draw_grid_overlay, TEXTURE_COLORS, TEXTURE_LABELS,
        )

        tmat_proj = st.session_state.get("terr_project_path", "")
        rd_tmat   = st.session_state.reforger_data

        if not tmat_proj:
            st.info(
                "Renseignez le **chemin projet Workbench** dans la barre latérale "
                "pour activer la lecture TMAT."
            )
        elif rd_tmat is None:
            st.info(
                "Renseignez les **données World Composition** (tuiles/blocs) "
                "pour lire le TMAT."
            )
        else:
            tiles_tmat       = rd_tmat.get("tiles", (64, 64))
            bpt_tmat         = rd_tmat.get("blocks_per_tile", (4, 4))
            tiles_x, tiles_y = int(tiles_tmat[0]), int(tiles_tmat[1])
            bpt_x, bpt_y     = int(bpt_tmat[0]),   int(bpt_tmat[1])


            terr_files_tmat = find_terr_files(tmat_proj)
            if not terr_files_tmat:
                st.warning(f"Aucun fichier .terr trouvé dans `{tmat_proj}`")
            else:
                materials_tmat = parse_terr_materials(str(terr_files_tmat[0]))
                ttile_files    = find_ttile_files(tmat_proj)

                ti1, ti2 = st.columns([4, 1])
                with ti1:
                    st.caption(
                        f".terr : **{terr_files_tmat[0].name}** "
                        f"({len(materials_tmat)} matériaux)  |  "
                        f".ttile : **{len(ttile_files)}** fichier(s)  |  "
                        f"Grille : {tiles_x}×{tiles_y} tuiles "
                        f"× {bpt_x}×{bpt_y} blocs"
                    )
                with ti2:
                    load_tmat_btn = st.button("🔄 Charger TMAT", key="btn_load_tmat")

                blended_mode = st.toggle(
                    "Rendu pondéré (mix couleurs par poids QTRE)",
                    value=False,
                    key="tmat_blended_mode",
                    help="Activé : mélange les couleurs par poids réels de chaque matériau. "
                         "Plus précis mais plus lent (~2× le temps de lecture).",
                )

                if load_tmat_btn:
                    if not ttile_files:
                        st.error(
                            "Aucun fichier .ttile trouvé dans le projet. "
                            "Vérifiez que le chemin pointe vers la racine du projet Workbench "
                            "et que la map a été compilée."
                        )
                    else:
                        with st.spinner(
                            f"⏳ Lecture de {len(ttile_files)} fichier(s) .ttile…"
                        ):
                            try:
                                grid_tmat, mat_counts_tmat = read_tmat_grid(
                                    ttile_files, tiles_x, tiles_y, bpt_x, bpt_y
                                )
                                if blended_mode:
                                    rgb_tmat, mat_fracs_tmat = render_tmat_rgb_blended(
                                        ttile_files, tiles_x, tiles_y, bpt_x, bpt_y,
                                        materials_tmat,
                                    )
                                    n_p = int((grid_tmat >= 0).sum())
                                    mat_counts_tmat = {
                                        k: int(v * n_p)
                                        for k, v in mat_fracs_tmat.items()
                                        if v > 0
                                    }
                                else:
                                    rgb_tmat = render_tmat_rgb(grid_tmat, materials_tmat)
                                st.session_state["tmat_data"] = {
                                    "grid":       grid_tmat,
                                    "rgb":        np.flipud(rgb_tmat),
                                    "mat_counts": mat_counts_tmat,
                                    "materials":  materials_tmat,
                                    "blended":    blended_mode,
                                }
                                st.success(
                                    f"✅ {len(mat_counts_tmat)} matériau(x) lus sur "
                                    f"{tiles_x * tiles_y} tuile(s)."
                                )
                            except Exception as e:
                                st.error(f"❌ Erreur lecture TMAT : {e}")
                                st.exception(e)

                tmat_data = st.session_state.get("tmat_data")
                if tmat_data:
                    rgb_tmat_disp = tmat_data["rgb"]
                    mat_cnt_disp  = tmat_data["mat_counts"]
                    mats_disp     = tmat_data["materials"]

                    _caption = (
                        "TMAT — couleurs pondérées par poids QTRE (rôles)"
                        if tmat_data.get("blended")
                        else "TMAT — matériau dominant par bloc (couleurs = rôles)"
                    )

                    gc1, gc2 = st.columns(2)
                    show_tmat_grid   = gc1.checkbox("📐 Grille tuiles", value=False,
                                                    key="chk_tmat_grid")
                    # Labels utiles seulement si les tuiles font au moins 12px dans l'image
                    can_label = (bpt_x >= 12 and bpt_y >= 12)
                    show_tmat_labels = gc2.checkbox(
                        "🏷️ Numéros de tuiles", value=False,
                        key="chk_tmat_labels",
                        disabled=not can_label,
                        help="Activez la grille tuiles — nécessite bpt ≥ 12 px/tuile." if not can_label else "",
                    )

                    disp_tmat = rgb_tmat_disp.copy()
                    if show_tmat_grid:
                        import cv2 as _cv2
                        disp_tmat = np.ascontiguousarray(disp_tmat)
                        h_dt, w_dt = disp_tmat.shape[:2]
                        # 1 px jaune tous les bpt blocs (= frontière de tuile)
                        for gx in range(0, w_dt, bpt_x):
                            _cv2.line(disp_tmat, (gx, 0), (gx, h_dt - 1), (255, 220, 0), 1)
                        for gy in range(0, h_dt, bpt_y):
                            _cv2.line(disp_tmat, (0, gy), (w_dt - 1, gy), (255, 220, 0), 1)
                        if show_tmat_labels and can_label:
                            _font = _cv2.FONT_HERSHEY_SIMPLEX
                            _scale = max(0.25, min(0.5, bpt_x / 30))
                            for tx in range(tiles_x):
                                for ty_img in range(tiles_y):
                                    ty_rf = tiles_y - 1 - ty_img
                                    xp = tx * bpt_x + 2
                                    yp = ty_img * bpt_y + int(bpt_y * 0.7)
                                    lbl = f"{tx},{ty_rf}"
                                    _cv2.putText(disp_tmat, lbl, (xp, yp), _font,
                                                 _scale, (0, 0, 0), 2, _cv2.LINE_AA)
                                    _cv2.putText(disp_tmat, lbl, (xp, yp), _font,
                                                 _scale, (255, 255, 255), 1, _cv2.LINE_AA)

                    st.image(disp_tmat, caption=_caption, use_container_width=True)

                    total_painted  = max(sum(mat_cnt_disp.values()), 1)
                    n_total_blocks = tmat_data["grid"].size
                    n_unpainted    = int(np.sum(tmat_data["grid"] < 0))

                    rows_tmat = []
                    for mat_idx, count in sorted(mat_cnt_disp.items(), key=lambda x: -x[1]):
                        mat_name = (
                            mats_disp[mat_idx] if mat_idx < len(mats_disp) else f"mat_{mat_idx}"
                        )
                        role    = mat_to_role(mat_name)
                        pct     = count / total_painted * 100
                        color   = TEXTURE_COLORS.get(role, (128, 128, 128))
                        hex_col = "#{:02X}{:02X}{:02X}".format(*color)
                        rows_tmat.append({
                            "Index":            mat_idx,
                            "Matériau (.emat)": mat_name,
                            "Rôle":             TEXTURE_LABELS.get(role, role),
                            "Couleur":          hex_col,
                            "Blocs peints":     count,
                            "Couverture %":     f"{pct:.1f}",
                        })

                    import pandas as pd
                    st.markdown("#### Répartition matériaux TMAT")
                    st.dataframe(pd.DataFrame(rows_tmat), use_container_width=True, hide_index=True)

                    tmat_map_bytes = _build_tmat_legend_image(rgb_tmat_disp, rows_tmat)
                    col_dl, col_sv = st.columns(2)
                    with col_dl:
                        st.download_button(
                            "📥 Télécharger carte TMAT (PNG)", tmat_map_bytes,
                            file_name="tmat_map.png", mime="image/png", key="dl_tmat_map",
                        )
                    proj_path = st.session_state.get("current_project_path")
                    if proj_path:
                        with col_sv:
                            if st.button("💾 Sauvegarder dans le projet", key="btn_save_tmat"):
                                out = Path(proj_path) / "generated" / "tmat_map.png"
                                out.write_bytes(tmat_map_bytes)
                                st.success("✅ Sauvegardé → generated/tmat_map.png")

                    if n_unpainted:
                        st.info(
                            f"ℹ️ {n_unpainted:,} bloc(s) non peints sur {n_total_blocks:,} "
                            f"({n_unpainted / n_total_blocks * 100:.1f}%) — affichés en gris foncé."
                        )

                    with st.expander("🔍 Scan blocs résiduels", expanded=False):
                        st.markdown(
                            "Détecte les blocs où un matériau occupe moins d'un certain seuil "
                            "de surface (erreurs de peinture résiduelles)."
                        )
                        residual_threshold = st.slider(
                            "Seuil résiduel (%)", min_value=1, max_value=20, value=5,
                            key="residual_threshold_slider",
                            help="Un matériau en dessous de ce % dans un bloc est considéré résiduel.",
                        ) / 100.0

                        if st.button("🔍 Lancer le scan", key="btn_cleanup_scan"):
                            with st.spinner(f"⏳ Scan de {len(ttile_files)} fichier(s) .ttile…"):
                                try:
                                    scan_result = tmat_cleanup_scan(
                                        ttile_files, mats_disp,
                                        residual_threshold=residual_threshold,
                                    )
                                    st.session_state["tmat_cleanup"] = scan_result
                                except Exception as e:
                                    st.error(f"❌ Erreur scan : {e}")
                                    st.exception(e)

                        cleanup = st.session_state.get("tmat_cleanup")
                        if cleanup:
                            res_blocks  = cleanup["residual_blocks"]
                            def_blocks  = cleanup["default_blocks"]
                            mat_summary = cleanup["mat_summary"]
                            col_r1, col_r2 = st.columns(2)
                            col_r1.metric("Blocs résiduels", len(res_blocks))
                            col_r2.metric("Blocs dominant=default", len(def_blocks))
                            if mat_summary:
                                st.markdown("**Matériaux les plus souvent résiduels :**")
                                import pandas as pd
                                rows_res = []
                                for mat_id, nb in mat_summary.items():
                                    mat_name = (
                                        mats_disp[mat_id]
                                        if mat_id < len(mats_disp)
                                        else f"mat_{mat_id}"
                                    )
                                    rows_res.append({
                                        "Index":            mat_id,
                                        "Matériau (.emat)": mat_name,
                                        "Rôle":             TEXTURE_LABELS.get(mat_to_role(mat_name), mat_to_role(mat_name)),
                                        "Blocs résiduels":  nb,
                                    })
                                st.dataframe(pd.DataFrame(rows_res),
                                             use_container_width=True, hide_index=True)
                            else:
                                st.success("✅ Aucun bloc résiduel détecté avec ce seuil.")
                            if def_blocks:
                                st.warning(
                                    f"⚠️ {len(def_blocks)} bloc(s) avec le matériau **default** (index 0) "
                                    f"comme dominant — probablement des zones non peintes."
                                )

                    with st.expander("🎯 Sélection de zones à compléter", expanded=False):
                        st.markdown(
                            "Cliquez sur les tuiles à **compléter** avec le générateur. "
                            "Les tuiles sélectionnées (rouge) seront écrasées par les scores "
                            "morphologiques. Les autres conservent la peinture TMAT."
                        )
                        import plotly.express as px

                        if "tmat_selected_tiles" not in st.session_state:
                            st.session_state["tmat_selected_tiles"] = set()
                        selected = st.session_state["tmat_selected_tiles"]
                        h_img, w_img = rgb_tmat_disp.shape[:2]

                        fig_zt = px.imshow(rgb_tmat_disp)
                        fig_zt.update_layout(
                            height=750,
                            margin=dict(l=0, r=0, t=0, b=0),
                            xaxis=dict(showticklabels=False, showgrid=False),
                            yaxis=dict(showticklabels=False, showgrid=False),
                            dragmode="zoom",
                        )
                        shapes_zt = []
                        for tx in range(0, w_img + 1, bpt_x):
                            shapes_zt.append(dict(
                                type="line", xref="x", yref="y",
                                x0=tx - 0.5, y0=-0.5, x1=tx - 0.5, y1=h_img - 0.5,
                                line=dict(color="rgba(255,220,0,0.7)", width=1),
                            ))
                        for ty in range(0, h_img + 1, bpt_y):
                            shapes_zt.append(dict(
                                type="line", xref="x", yref="y",
                                x0=-0.5, y0=ty - 0.5, x1=w_img - 0.5, y1=ty - 0.5,
                                line=dict(color="rgba(255,220,0,0.7)", width=1),
                            ))
                        for (tc, tr) in selected:
                            shapes_zt.append(dict(
                                type="rect", xref="x", yref="y",
                                x0=tc * bpt_x - 0.5,       y0=tr * bpt_y - 0.5,
                                x1=(tc + 1) * bpt_x - 0.5, y1=(tr + 1) * bpt_y - 0.5,
                                fillcolor="rgba(255,50,50,0.35)",
                                line=dict(color="rgba(255,50,50,0.9)", width=1),
                            ))
                        fig_zt.update_layout(shapes=shapes_zt)

                        st.caption(
                            "Scroll ou glisser pour zoomer · Clic pour sélectionner/désélectionner une tuile"
                        )
                        event_zt = st.plotly_chart(
                            fig_zt, key="tmat_zone_chart",
                            on_select="rerun", selection_mode="points",
                            use_container_width=True,
                            config={"scrollZoom": True, "displayModeBar": False},
                        )
                        if event_zt and event_zt.selection.points:
                            for pt in event_zt.selection.points:
                                px_x = int(round(pt["x"]))
                                px_y = int(round(pt["y"]))
                                tc = max(0, min(tiles_x - 1, px_x // bpt_x))
                                tr = max(0, min(tiles_y - 1, px_y // bpt_y))
                                key_t = (tc, tr)
                                if key_t in selected:
                                    selected.discard(key_t)
                                else:
                                    selected.add(key_t)
                            st.session_state["tmat_selected_tiles"] = selected
                            st.rerun()

                        n_sel = len(selected)
                        c_info, c_clr, c_inv, c_exp = st.columns([2, 1, 1, 1])
                        c_info.info(f"{n_sel} tuile(s) sélectionnée(s)")
                        if c_clr.button("🗑️ Effacer", key="btn_zt_clear"):
                            st.session_state["tmat_selected_tiles"] = set()
                            st.rerun()
                        if c_inv.button("⇄ Inverser", key="btn_zt_inv"):
                            all_t = {(tc, tr) for tc in range(tiles_x) for tr in range(tiles_y)}
                            st.session_state["tmat_selected_tiles"] = all_t - selected
                            st.rerun()
                        if n_sel > 0:
                            import io
                            zone_mask = np.zeros((h_img, w_img), dtype=np.uint8)
                            for (tc, tr) in selected:
                                x0z, y0z = tc * bpt_x, tr * bpt_y
                                zone_mask[y0z:y0z + bpt_y, x0z:x0z + bpt_x] = 255
                            buf_zm = io.BytesIO()
                            Image.fromarray(zone_mask).save(buf_zm, format="PNG")
                            c_exp.download_button(
                                "📥 Masque zone", buf_zm.getvalue(),
                                file_name="zone_mask.png", mime="image/png",
                                key="dl_zone_mask",
                            )

                    # ── Fusion TMAT + Générateur ──────────────────────────────
                    with st.expander("🔀 Fusion TMAT + Générateur", expanded=False):
                        tr_gen   = st.session_state.get("tex_reforger")
                        n_sel_f  = len(st.session_state.get("tmat_selected_tiles", set()))
                        ok_tmat  = tmat_data is not None
                        ok_gen   = tr_gen is not None and "constrained_scores" in tr_gen
                        ok_sel   = n_sel_f > 0

                        if not ok_tmat:
                            st.info("Chargez d'abord le **TMAT** (bouton ci-dessus).")
                        elif not ok_gen:
                            st.info("Générez d'abord l'**Aperçu Texture** (onglet 🖼️).")
                        elif not ok_sel:
                            st.info("Sélectionnez les tuiles à compléter (expander ci-dessus).")
                        else:
                            st.markdown(
                                f"**{n_sel_f} tuile(s) sélectionnée(s)** seront remplies par "
                                f"les scores morphologiques. Le reste conserve la peinture TMAT."
                            )
                            if st.button("🔀 Générer masques hybrides", key="btn_fusion"):
                                from reforger_texture_budget import extract_tmat_block_coverage
                                from pathlib import Path as _P
                                import zipfile

                                constrained = tr_gen["constrained_scores"]
                                biome_cfg   = tr_gen["biome_config"]
                                selected_f  = st.session_state["tmat_selected_tiles"]
                                BLOCK_PX    = 32  # toujours 32 faces/bloc dans la heightmap

                                with st.spinner("⏳ Extraction couverture TMAT…"):
                                    tmat_cov = extract_tmat_block_coverage(
                                        ttile_files, tiles_x, tiles_y, bpt_x, bpt_y,
                                        len(materials_tmat),
                                    )
                                    # Aligner sur coords image (flip Y pour matcher heightmap)
                                    tmat_cov = np.flip(tmat_cov, axis=1)

                                # Mapping emat → mat_idx
                                emat_to_idx = {
                                    m.lower().replace(".emat", ""): i
                                    for i, m in enumerate(materials_tmat)
                                }

                                n_by_b = tiles_y * bpt_y
                                n_bx_b = tiles_x * bpt_x

                                with st.spinner("⏳ Fusion et génération des masques…"):
                                    merged_masks = {}
                                    for mat_idx, mat_name in enumerate(materials_tmat):
                                        if mat_name == "default":
                                            continue
                                        role = mat_to_role(mat_name)

                                        # Scores générateur → niveau bloc
                                        gen_px = constrained.get(role)
                                        if gen_px is not None:
                                            H, W = gen_px.shape
                                            by_b = min(H // BLOCK_PX, n_by_b)
                                            bx_b = min(W // BLOCK_PX, n_bx_b)
                                            gen_block = gen_px[:by_b*BLOCK_PX, :bx_b*BLOCK_PX] \
                                                .reshape(by_b, BLOCK_PX, bx_b, BLOCK_PX) \
                                                .mean(axis=(1, 3))
                                        else:
                                            gen_block = None

                                        # Couverture TMAT pour ce matériau
                                        tmat_layer = tmat_cov[mat_idx].copy()  # (n_by_b, n_bx_b)

                                        # Appliquer la sélection
                                        for (tc, tr_) in selected_f:
                                            bx0 = tc  * bpt_x
                                            by0 = tr_ * bpt_y
                                            if by0 + bpt_y > n_by_b or bx0 + bpt_x > n_bx_b:
                                                continue
                                            if gen_block is not None:
                                                tmat_layer[by0:by0+bpt_y, bx0:bx0+bpt_x] = \
                                                    gen_block[by0:by0+bpt_y, bx0:bx0+bpt_x]
                                            else:
                                                tmat_layer[by0:by0+bpt_y, bx0:bx0+bpt_x] = 0.0

                                        # Upsample vers résolution heightmap
                                        merged_px = np.repeat(
                                            np.repeat(tmat_layer, BLOCK_PX, axis=0),
                                            BLOCK_PX, axis=1
                                        ).astype(np.float32)
                                        merged_masks[mat_name] = merged_px

                                # Export ZIP
                                import io as _io
                                buf_zip = _io.BytesIO()
                                n_exported = 0
                                with zipfile.ZipFile(buf_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                                    for i, (mat_name, arr) in enumerate(merged_masks.items()):
                                        if arr.max() < 1e-6:
                                            continue
                                        role  = mat_to_role(mat_name)
                                        label = TEXTURE_LABELS.get(role, role)
                                        fname = f"{i+1:02d}_{role}_{mat_name}_hybrid.png"
                                        img16 = (np.clip(arr, 0, 1) * 65535).astype(np.uint16)
                                        buf_png = _io.BytesIO()
                                        Image.fromarray(img16).save(buf_png, format="PNG")
                                        zf.writestr(fname, buf_png.getvalue())
                                        n_exported += 1

                                buf_zip.seek(0)
                                st.success(f"✅ {n_exported} masques hybrides générés.")
                                st.download_button(
                                    "📦 Télécharger masques hybrides (.zip)",
                                    buf_zip.getvalue(),
                                    file_name="masks_hybrid.zip",
                                    mime="application/zip",
                                    key="dl_hybrid_masks",
                                )

    with _e_sat:
        from reforger_texture_budget import TEXTURE_ORDER, TEXTURE_LABELS, SATMAP_TEXTURE_ORDER

        # ── Export SatMap réaliste ──────────────────────────────────────────
        st.markdown("### 🗺️ Export SatMap réaliste")
        st.caption(
            "Génère une SatMap cohérente en tuilant les BCRMiddleMap de chaque matériau, "
            "colorisées par Color×MiddleColor et blendées par les masques morphologiques. "
            "Fallback couleur unie si la texture PNG n'est pas trouvée."
        )

        _tr_sat = st.session_state.get("tex_reforger")
        if _tr_sat is None or "constrained_scores" not in _tr_sat:
            st.info("Générez d'abord l'**Aperçu Texture** (onglet 🖼️) pour activer cette section.")
        else:
            from reforger_texture_budget import TEXTURE_COLORS
            _constrained_sat = _tr_sat["constrained_scores"]
            _biome_cfg_sat   = _tr_sat["biome_config"]
            _rd_sat          = _tr_sat["reforger_data"]
            _cell_m_sat      = float(_rd_sat.get("planar_resolution_m", 1.0))
            _H_sat, _W_sat   = next(iter(_constrained_sat.values())).shape
            st.caption(
                f"Terrain : {_W_sat}×{_H_sat} px — "
                f"{_W_sat * _cell_m_sat:.0f}×{_H_sat * _cell_m_sat:.0f} m — "
                f"{_cell_m_sat:.1f} m/px"
            )

            # Dossier local de textures SatMap — convention : {emat_stem}.png
            _SAT_TEX_DIR = Path("data/satmap_textures")
            _SAT_TEX_DIR.mkdir(parents=True, exist_ok=True)
            # Index insensible à la casse : stem → Path
            _tex_index = {
                f.stem.lower(): f
                for f in _SAT_TEX_DIR.iterdir()
                if f.suffix.lower() in (".png", ".jpg")
            }

            def _find_png_for_role(role):
                stem = _biome_cfg_sat.get(role, "").replace(".emat", "").lower()
                return _tex_index.get(stem)

            # Rôles actifs
            _active_roles_sat = [
                (r, _constrained_sat[r])
                for r in TEXTURE_ORDER
                if r in _constrained_sat and float(np.max(_constrained_sat[r])) > 0.001
            ]

            # Dossier .emat optionnel pour lire MiddleColor / MiddleScaleUV
            _sat_emat_dir = st.text_input(
                "📁 Dossier .emat (optionnel — pour lire MiddleColor et MiddleScaleUV)",
                value="",
                placeholder="I:\\Reforger_addons travail\\ZBK_repo\\Terrains\\Common\\Surfaces",
                key="sat_export_emat_dir",
                help=(
                    "Optionnel. Si renseigné, affine les teintes (MiddleColor×Color) "
                    "et la taille de tuile (MiddleScaleUV) depuis les .emat."
                ),
            ).strip().strip('"').strip("'")

            # Tableau de statut auto-détection
            st.markdown("#### 🖼️ Textures détectées")
            st.caption(
                f"Convention : **`data/satmap_textures/{{nom_emat}}.png`** — "
                f"{len(_tex_index)} fichier(s) présent(s).  \n"
                "Ex : biome utilise `Grass_02.emat` → placez `Grass_02.png` dans le dossier."
            )
            import pandas as pd
            _status_rows = []
            for _r, _marr in _active_roles_sat:
                _cov   = float(np.mean(_marr > 0.005)) * 100
                _emat  = _biome_cfg_sat.get(_r, "—")
                _png_f = _find_png_for_role(_r)
                _status_rows.append({
                    "Rôle":    TEXTURE_LABELS.get(_r, _r),
                    "Texture .emat": _emat,
                    "PNG trouvé":    _png_f.name if _png_f else "— manquant",
                    "Mode":    "🖼️ texture" if _png_f else "🎨 couleur unie",
                    "%":       f"{_cov:.0f}",
                })
            st.dataframe(pd.DataFrame(_status_rows), use_container_width=True, hide_index=True)

            _sc1, _sc2 = st.columns([2, 1])
            with _sc1:
                _sat_brightness = st.slider(
                    "☀️ Luminosité (multiplicateur)",
                    min_value=0.5, max_value=4.0, value=2.5, step=0.1,
                    key="sat_brightness",
                    help=(
                        "Les TEXTURE_COLORS sont calibrées sur des BCR de détail (AO baked → sombres). "
                        "Multiplier par 2–3 donne un résultat plus proche d'une vue aérienne réelle."
                    ),
                )
            with _sc2:
                _sat_ocean_blue = st.checkbox(
                    "🌊 Mer en bleu",
                    value=True,
                    key="sat_ocean_blue",
                    help="Remplace le rôle fond_marin par un bleu océan fixe (ignore la texture et la luminosité).",
                )

            if st.button("🗺️ Générer SatMap réaliste", key="btn_gen_satmap_realiste"):
                try:
                    with st.spinner("⏳ Génération SatMap réaliste…"):
                        import math as _math

                        _emat_root = Path(_sat_emat_dir) if _sat_emat_dir and Path(_sat_emat_dir).is_dir() else None

                        def _emat_search(emat_fp, param):
                            try:
                                with open(emat_fp, encoding="utf-8", errors="replace") as _f:
                                    for _ln in _f:
                                        if f" {param} " in _ln:
                                            return _ln.split(f" {param} ", 1)[1].strip()
                            except Exception:
                                pass
                            return None

                        def _find_emat(stem):
                            if _emat_root:
                                for fp in _emat_root.rglob(f"{stem}.emat"):
                                    return fp
                            return None

                        def _emat_param(emat_fp, param, visited=None):
                            if visited is None:
                                visited = set()
                            if str(emat_fp) in visited:
                                return None
                            visited.add(str(emat_fp))
                            val = _emat_search(emat_fp, param)
                            if val is not None:
                                return val
                            parent_rn = _emat_search(emat_fp, "TerrainMaterial :")
                            if parent_rn:
                                pstem = parent_rn.split(".")[-2].split("/")[-1]
                                pfp = _find_emat(pstem)
                                if pfp:
                                    return _emat_param(pfp, param, visited)
                            return {"Color": "1 1 1 1", "MiddleColor": "1 1 1 1", "MiddleScaleUV": "100"}.get(param)

                        def _parse_color(s):
                            try:
                                return np.array([float(x) for x in (s or "1 1 1 1").split()[:3]], np.float32)
                            except Exception:
                                return np.ones(3, np.float32)

                        def _lin2srgb(c):
                            return np.where(c <= 0.0031308, 12.92 * c, 1.055 * (c ** (1/2.4)) - 0.055)

                        # Couleurs aériennes corrigées — remplacent TEXTURE_COLORS pour la satmap.
                        # TEXTURE_COLORS sont calibrées sur les BCR de détail (olive/sombre).
                        # Ces valeurs visent un rendu aerial réaliste avant multiplication luminosité.
                        _AERIAL_COLORS = {
                            "fond_marin":   ( 40,  55,  45),  # remplacé par bleu océan de toute façon
                            "sable":        ( 85,  78,  55),  # sable beige naturel
                            "cotier":       ( 48,  72,  35),  # herbe côtière — vert modéré
                            "galets":       ( 80,  76,  68),  # galets gris-brun
                            "prairie":        ( 42,  72,  28),  # herbe rase — vert franc
                            "lande":       ( 48,  70,  30),  # herbe sauvage — vert moyen
                            "feuillus":        ( 38,  62,  28),  # forêt mixte — vert foncé
                            "coniferes":  ( 22,  45,  18),  # forêt dense / conifères — vert très sombre
                            "lisiere": ( 55,  88,  42),  # forêt clairsemée / lisière — vert moyen
                            "champs1":      ( 75,  58,  38),  # sol nu / champs brun foncé
                            "champs2":      (105,  88,  55),  # champs ocre / chaume — brun chaud
                            "champs3":      ( 58,  95,  42),  # champs verts / cultures — vert clair
                            "erosion":      ( 88,  72,  52),  # terre / érosion — brun neutre
                            "débris":       ( 78,  72,  65),  # débris — gris-brun
                            "roche":        ( 82,  80,  78),  # roche — gris neutre
                            "neige":        (220, 225, 235),  # neige — blanc légèrement bleuté
                        }

                        _acc_rgb  = np.zeros((_H_sat, _W_sat, 3), np.float64)
                        _acc_mask = np.zeros((_H_sat, _W_sat),    np.float64)
                        _n_tex = _n_solid = 0
                        _report = []

                        for _role, _mask_arr in _active_roles_sat:
                            _label     = TEXTURE_LABELS.get(_role, _role)
                            _emat_stem = _biome_cfg_sat.get(_role, "").replace(".emat", "")
                            _emat_fp   = _find_emat(_emat_stem) if _emat_stem else None

                            # Teinte : MiddleColor×Color depuis .emat, sinon couleurs aériennes corrigées
                            if _emat_fp:
                                _cm   = _parse_color(_emat_param(_emat_fp, "MiddleColor"))
                                _cd   = _parse_color(_emat_param(_emat_fp, "Color"))
                                _tint = _lin2srgb(np.clip(_cm * _cd, 0, 1))
                            else:
                                _tint = np.array(_AERIAL_COLORS.get(_role, TEXTURE_COLORS.get(_role, (128, 128, 128))), np.float32) / 255.0

                            _scale_m = float(_emat_param(_emat_fp, "MiddleScaleUV") or "100") if _emat_fp else 100.0
                            _mm_fp   = _find_png_for_role(_role)
                            _m       = _mask_arr.astype(np.float64)

                            if _mm_fp is not None:
                                _tile_px = max(1, round(_scale_m / _cell_m_sat))
                                _tex_np  = (
                                    np.array(
                                        Image.open(str(_mm_fp)).convert("RGB")
                                        .resize((_tile_px, _tile_px), Image.LANCZOS),
                                        np.float32,
                                    ) / 255.0
                                )
                                _ty2 = _math.ceil(_H_sat / _tile_px)
                                _tx2 = _math.ceil(_W_sat / _tile_px)
                                _layer = (
                                    np.tile(_tex_np, (_ty2, _tx2, 1))[:_H_sat, :_W_sat]
                                    * _tint[np.newaxis, np.newaxis, :]
                                )
                                _report.append((_label, "🖼️ texture", _mm_fp.name))
                                _n_tex += 1
                            else:
                                _layer = np.full((_H_sat, _W_sat, 3), _tint, np.float64)
                                _src   = "emat MiddleColor" if _emat_fp else "TEXTURE_COLORS"
                                _report.append((_label, "🎨 couleur unie", _src))
                                _n_solid += 1

                            _acc_rgb  += _layer * _m[..., np.newaxis]
                            _acc_mask += _m

                        # Pixels non couverts → couleur de fond = moyenne pondérée des matériaux actifs
                        _bg_color = np.zeros(3, np.float64)
                        _bg_total = 0.0
                        for _role, _mask_arr in _active_roles_sat:
                            _w = float(np.mean(_mask_arr))
                            _c = np.array(_AERIAL_COLORS.get(_role, TEXTURE_COLORS.get(_role, (128, 128, 128))), np.float64) / 255.0
                            _bg_color += _c * _w
                            _bg_total += _w
                        if _bg_total > 0:
                            _bg_color /= _bg_total
                        else:
                            _bg_color = np.array([0.4, 0.35, 0.25], np.float64)

                        _denom = np.where(_acc_mask < 1e-6, 1.0, _acc_mask)
                        _normalized = _acc_rgb / _denom[..., np.newaxis]
                        # Remplacer pixels sans couverture par la couleur de fond
                        _no_cov = _acc_mask < 1e-6
                        _normalized[_no_cov] = _bg_color

                        # Appliquer le multiplicateur de luminosité
                        _result_np = np.clip(_normalized * _sat_brightness * 255, 0, 255).astype(np.uint8)

                        # Post-process : mer en bleu
                        if _sat_ocean_blue and "fond_marin" in _constrained_sat:
                            _fm = _constrained_sat["fond_marin"].astype(np.float32)
                            # Fond_marin dominant = valeur la plus haute parmi tous les rôles actifs
                            _fm_dom = np.ones((_H_sat, _W_sat), bool)
                            for _rr, _marr in _active_roles_sat:
                                if _rr != "fond_marin":
                                    _fm_dom &= (_fm >= _marr.astype(np.float32))
                            _fm_dom &= (_fm > 0.01)
                            # Dégradé de profondeur : bleu clair (côte) → bleu sombre (fond)
                            _blue_shallow = np.array([55, 140, 190], np.float32)
                            _blue_deep    = np.array([15,  60, 110], np.float32)
                            _depth_n = np.clip(_fm, 0.0, 1.0)
                            _ocean_rgb = (
                                _blue_shallow[np.newaxis, np.newaxis, :] * (1.0 - _depth_n[..., np.newaxis])
                                + _blue_deep[np.newaxis, np.newaxis, :] * _depth_n[..., np.newaxis]
                            ).astype(np.uint8)
                            _result_np[_fm_dom] = _ocean_rgb[_fm_dom]

                        _result_img = Image.fromarray(_result_np, "RGB")

                        # Redimensionner à la puissance de 2 supérieure (requis par Workbench)
                        def _next_pow2(n):
                            return 2 ** _math.ceil(_math.log2(max(n, 1)))
                        _pw = _next_pow2(_W_sat)
                        _ph = _next_pow2(_H_sat)
                        if _pw != _W_sat or _ph != _H_sat:
                            _result_img = _result_img.resize((_pw, _ph), Image.LANCZOS)

                        _out_sat = Path(get_output_dir()) / f"satmap_realiste_{format_timestamp()}.png"
                        # Sauvegarder sans profil ICC ni métadonnées — requis par Workbench
                        Image.MAX_IMAGE_PIXELS = None
                        _clean_img = Image.new("RGB", _result_img.size)
                        _clean_img.paste(_result_img)
                        _clean_img.save(str(_out_sat), format="PNG")

                        # Miniature pour l'aperçu (max 2048px)
                        _preview_img = _result_img.copy()
                        _preview_img.thumbnail((2048, 2048), Image.LANCZOS)
                        _out_preview = Path(get_output_dir()) / "satmap_realiste_preview.png"
                        _preview_img.save(str(_out_preview), format="PNG")

                        st.session_state["satmap_export_result"]  = str(_out_sat)
                        st.session_state["satmap_export_preview"] = str(_out_preview)
                        st.session_state["satmap_export_report"]  = _report
                        _size_info = f"{_pw}×{_ph} px" + (f" (redimensionné depuis {_W_sat}×{_H_sat})" if _pw != _W_sat or _ph != _H_sat else "")
                        st.success(f"✅ SatMap générée — {_n_tex} texture(s), {_n_solid} couleur(s) unie(s) — {_size_info}")

                except Exception as _e:
                    st.error(f"❌ Erreur : {_e}")
                    st.exception(_e)

            _sat_res     = st.session_state.get("satmap_export_result")
            _sat_preview = st.session_state.get("satmap_export_preview")
            _sat_report  = st.session_state.get("satmap_export_report", [])
            if _sat_res and Path(_sat_res).exists():
                Image.MAX_IMAGE_PIXELS = None
                if _sat_preview and Path(_sat_preview).exists():
                    st.image(_sat_preview, caption="SatMap réaliste (aperçu)", use_container_width=True)
                else:
                    _prev = Image.open(_sat_res)
                    _prev.thumbnail((2048, 2048), Image.LANCZOS)
                    st.image(_prev, caption="SatMap réaliste (aperçu)", use_container_width=True)
                with open(_sat_res, "rb") as _fh:
                    st.download_button(
                        "📥 Télécharger SatMap PNG", _fh.read(),
                        file_name=Path(_sat_res).name, mime="image/png",
                        key="dl_satmap_realiste",
                    )
                if _sat_report:
                    with st.expander("📋 Détail par matériau"):
                        import pandas as pd
                        st.dataframe(
                            pd.DataFrame(_sat_report, columns=["Label", "Mode", "Source"]),
                            use_container_width=True, hide_index=True,
                        )

        st.markdown("---")

        # ── Masques depuis SatMap (segmentation K-means) ───────────────────
        st.markdown("### Masques depuis SatMap — Segmentation couleur")

        if not st.session_state.satmap_path:
            st.info("Chargez une **SatMap** dans la barre latérale pour activer cette section.")
        elif st.session_state.base_map is None:
            st.info("Chargez une heightmap pour définir la résolution cible des masques.")
        else:
            bm_sat = st.session_state.base_map
            tgt_h  = bm_sat.height
            tgt_w  = bm_sat.width

            _sa1, _sa2 = st.columns(2)
            with _sa1:
                n_clusters = st.slider(
                    "Nombre de clusters", 4, 28, 16, key="sat_n_clusters",
                    help="16–20 pour une carte variée. Plus de clusters = plus de nuances de couleur détectées.",
                )
            with _sa2:
                blur_sigma = st.slider(
                    "Lissage pré-segmentation (sigma)", 1, 8, 4, key="sat_blur_pre",
                    help="Flou gaussien appliqué à l'image avant K-means pour réduire le bruit pixel.",
                )

            if st.button("Analyser SatMap", key="btn_analyze_satmap"):
                try:
                    with st.spinner("Segmentation K-means..."):
                        from scipy.ndimage import gaussian_filter as _gf_sat
                        from sklearn.cluster import MiniBatchKMeans as _MBK

                        # Load at native res, cap working resolution at 2048px
                        _sat_pil = Image.open(st.session_state.satmap_path).convert("RGB")
                        _nw, _nh = _sat_pil.size
                        _wscale  = min(1.0, 2048 / max(_nh, _nw))
                        _ww      = max(1, int(_nw * _wscale))
                        _wh      = max(1, int(_nh * _wscale))
                        _sat_w   = np.array(_sat_pil.resize((_ww, _wh), Image.LANCZOS), dtype=np.float32)

                        # Blur BEFORE k-means to remove pixel noise
                        _sat_bl = np.stack([
                            _gf_sat(_sat_w[:, :, _c], sigma=float(blur_sigma))
                            for _c in range(3)
                        ], axis=-1)

                        # Downscale blurred to 512px for fast k-means
                        _ks  = min(1.0, 512 / max(_wh, _ww))
                        _kw  = max(1, int(_ww * _ks))
                        _kh  = max(1, int(_wh * _ks))
                        _km_arr = np.array(
                            Image.fromarray(_sat_bl.clip(0, 255).astype(np.uint8))
                            .resize((_kw, _kh), Image.LANCZOS),
                            dtype=np.float32,
                        )
                        _km = _MBK(n_clusters=n_clusters, random_state=42,
                                   max_iter=200, batch_size=4096)
                        _km.fit(_km_arr.reshape(-1, 3))
                        _cen = np.clip(_km.cluster_centers_, 0, 255).astype(np.uint8)

                        # Sort clusters darkest → brightest
                        _lum_v   = (0.299 * _cen[:, 0].astype(float)
                                    + 0.587 * _cen[:, 1].astype(float)
                                    + 0.114 * _cen[:, 2].astype(float))
                        _lum_ord = np.argsort(_lum_v)
                        _cen_s   = _cen[_lum_ord]

                        # Assign labels at working resolution (chunked)
                        _pix   = _sat_bl.reshape(-1, 3).astype(np.float32)
                        _cenf  = _cen_s.astype(np.float32)
                        _lflat = np.zeros(len(_pix), dtype=np.uint8)
                        _chunk = 65536
                        for _s in range(0, len(_pix), _chunk):
                            _p = _pix[_s:_s + _chunk]
                            _d = np.sum((_p[:, np.newaxis, :] - _cenf[np.newaxis, :, :]) ** 2, axis=2)
                            _lflat[_s:_s + _chunk] = np.argmin(_d, axis=1)
                        _lbl_w = _lflat.reshape(_wh, _ww)

                        _tot = _wh * _ww
                        _cov = {
                            i: float(np.sum(_lbl_w == i)) / _tot * 100
                            for i in range(n_clusters)
                        }

                        # Auto zone heuristic from RGB — ordered from most specific to most generic
                        def _detect_zone(_rgb):
                            _r2, _g2, _b2 = int(_rgb[0]), int(_rgb[1]), int(_rgb[2])
                            _l2   = 0.299 * _r2 + 0.587 * _g2 + 0.114 * _b2
                            _n2   = max(abs(_r2 - _g2), abs(_g2 - _b2), abs(_r2 - _b2))
                            _warm = _r2 - _b2   # >0 = chaud/brun, <0 = froid/bleu
                            _gdom = _g2 - max(_r2, _b2)  # vert dominant si >0
                            # Eau profonde
                            if _b2 > _r2 + 15 and _l2 < 40:
                                return "Océan profond",              "fond_marin"
                            if _b2 > _r2 + 5 and _l2 < 70:
                                return "Eau / Mer",                  "fond_marin"
                            # Eau peu profonde (bleue même très claire, b > r)
                            if _b2 > _r2 and _l2 > 80:
                                return "Eau peu profonde",           "fond_marin"
                            # Forêt dense (vert froid très sombre)
                            if _gdom > 12 and _l2 < 55:
                                return "Forêt dense (conifères)",    "coniferes"
                            if _gdom > 8 and _l2 < 85:
                                return "Forêt mixte",                "feuillus"
                            # Forêt clairsemée : vert FROID uniquement (warm < 10)
                            # Les champs verts sont chauds (warm >= 8) → passent au-dessous
                            if _gdom > 5 and _warm < 10 and _l2 < 135:
                                return "Forêt clairsemée / Lisière", "lisiere"
                            # Champs en terre / sol nu (rouge > vert, chaud, pas trop lumineux)
                            if _r2 > _g2 and _warm > 18 and _l2 < 115:
                                return "Champs brun / Sol nu",       "champs1"
                            # Champs ocre / chaume (chaud, rouge ≥ vert)
                            if _warm > 10 and _r2 >= _g2 - 8 and _l2 < 158:
                                return "Champs ocre / Chaume",       "champs2"
                            # Champs verts / cultures (vert tiède : gdom > 0 mais warm ≥ 8)
                            if _gdom > 0 and 75 < _l2 < 168:
                                return "Champs verts / Cultures",    "champs3"
                            # Herbe / prairie naturelle (vert équilibré résiduel)
                            if _g2 > _b2 and 65 < _l2 < 168:
                                return "Herbe / Prairie",            "prairie"
                            # Roche / urbain (gris neutre)
                            if _n2 < 22 and 50 < _l2 < 175:
                                return "Roche / Urbain",             "roche"
                            # Sable (lumineux ET chaud)
                            if _l2 > 155 and _warm > 5:
                                return "Sable / Plage",              "sable"
                            if _l2 > 175:
                                return "Zone lumineuse / Nuages",    "neige"
                            return "Végétation (mixte)",             "lande"

                        _zones = {i: _detect_zone(_cen_s[i]) for i in range(n_clusters)}

                        st.session_state["satmap_analysis"] = {
                            "centers_rgb": _cen_s,
                            "labels_work": _lbl_w,
                            "coverage":    _cov,
                            "zones":       _zones,
                            "n_clusters":  n_clusters,
                            "work_wh":     (_ww, _wh),
                        }
                except Exception as _ex_ana:
                    st.error(f"Erreur analyse SatMap : {_ex_ana}")
                    st.exception(_ex_ana)

            _ana = st.session_state.get("satmap_analysis")
            if _ana and _ana.get("n_clusters") == n_clusters:
                _cen_rgb = _ana["centers_rgb"]
                _lbl_w   = _ana["labels_work"]
                _cov_sat = _ana["coverage"]
                _zones   = _ana["zones"]
                _nc      = _ana["n_clusters"]
                _ww, _wh = _ana["work_wh"]

                # Side-by-side: original | posterized (K-means colors)
                _post = _cen_rgb[_lbl_w]
                _ic1, _ic2 = st.columns(2)
                with _ic1:
                    st.image(
                        str(st.session_state.satmap_path),
                        caption="SatMap originale",
                        use_container_width=True,
                    )
                with _ic2:
                    st.image(
                        _post,
                        caption=f"Segmentation K-means — {_nc} clusters",
                        use_container_width=True,
                    )

                # Cluster table: # | swatch | RGB | % | Zone | Texture
                st.markdown("#### Clusters → Textures")
                _hdr = st.columns([0.3, 0.5, 1.4, 0.6, 1.9, 2.1])
                for _hc, _ht in zip(_hdr, ["**#**", "", "**RGB**", "**%**", "**Zone probable**", "**Texture**"]):
                    _hc.markdown(_ht)

                _cluster_roles = {}
                for _ci in range(_nc):
                    _clr = _cen_rgb[_ci]
                    _r, _g, _b = int(_clr[0]), int(_clr[1]), int(_clr[2])
                    _zlabel, _zrole = _zones[_ci]

                    _row = st.columns([0.3, 0.5, 1.4, 0.6, 1.9, 2.1])
                    _row[0].markdown(f"**{_ci + 1}**")
                    _row[1].markdown(
                        f'<div style="width:26px;height:26px;'
                        f'background:#{_r:02X}{_g:02X}{_b:02X};'
                        f'border-radius:4px;border:1px solid #666;margin-top:4px"></div>',
                        unsafe_allow_html=True,
                    )
                    _row[2].markdown(f"`{_r}, {_g}, {_b}`")
                    _row[3].markdown(f"{_cov_sat[_ci]:.1f}%")
                    _row[4].markdown(_zlabel)
                    _def_idx = SATMAP_TEXTURE_ORDER.index(_zrole) if _zrole in SATMAP_TEXTURE_ORDER else 4
                    _cluster_roles[_ci] = _row[5].selectbox(
                        "",
                        SATMAP_TEXTURE_ORDER,
                        index=_def_idx,
                        format_func=lambda _x: TEXTURE_LABELS.get(_x, _x),
                        key=f"cluster_role_{_ci}",
                        label_visibility="collapsed",
                    )

                st.markdown("---")

                if st.button("Générer masques SatMap", key="gen_satmap_masks"):
                    try:
                        with st.spinner("Génération des masques SatMap..."):
                            # Upsample label map to target resolution
                            _lbl_full = np.array(
                                Image.fromarray(_lbl_w).resize((tgt_w, tgt_h), Image.NEAREST)
                            )
                            _biome_cfg = (
                                st.session_state.tex_reforger.get("biome_config", {})
                                if st.session_state.get("tex_reforger") else {}
                            )
                            _out_dir = Path(get_output_dir()) / f"masks_satmap_{format_timestamp()}"
                            _out_dir.mkdir(parents=True, exist_ok=True)

                            # Un masque par cluster (pas par rôle) pour conserver
                            # toutes les nuances — plusieurs clusters → même emat possible
                            _generated = []
                            for _ci2, _role in sorted(_cluster_roles.items()):
                                _mask = (_lbl_full == _ci2).astype(np.float32)
                                if float(np.max(_mask)) < 0.001:
                                    continue
                                _emat  = _biome_cfg.get(_role, _role)
                                _slug  = _emat.replace(".emat", "").replace("CUSTOM_", "custom_")
                                _fname = f"{_ci2 + 1:02d}_cluster{_ci2 + 1}_{_role}_{_slug}_satmap.png"
                                _pth   = _out_dir / _fname
                                Image.fromarray(
                                    (_mask * 65535).clip(0, 65535).astype(np.uint16)
                                ).save(str(_pth))
                                _generated.append((
                                    _role, _emat, str(_pth),
                                    float(np.mean(_mask > 0.005)) * 100,
                                    _ci2,
                                ))

                            _proj_masks_dir = st.session_state.last_generated.get(
                                "masks", {}
                            ).get("proj_dir")
                            if _proj_masks_dir:
                                import shutil as _sh_sat
                                for _, _, _pp, _, _ in _generated:
                                    _sh_sat.copy2(_pp, Path(_proj_masks_dir) / Path(_pp).name)

                            st.session_state.last_generated["masks_satmap"] = {
                                "files":        _generated,
                                "dir":          str(_out_dir),
                                "labels_work":  _lbl_w,
                                "cluster_roles": dict(_cluster_roles),
                            }
                        st.success(f"{len(_generated)} masques SatMap générés dans {_out_dir}")
                    except Exception as _ex_gen:
                        st.error(f"Erreur : {_ex_gen}")
                        st.exception(_ex_gen)

                if "masks_satmap" in st.session_state.last_generated:
                    _sat_info  = st.session_state.last_generated["masks_satmap"]
                    _files_sat = _sat_info["files"]
                    _lbl_disp  = _sat_info.get("labels_work")

                    st.markdown("#### Masques générés")
                    _ncols = 5
                    for _rr in range(0, len(_files_sat), _ncols):
                        _cs = st.columns(_ncols)
                        for _jj, (_rl, _em, _pp, _cv, _cid) in enumerate(
                            _files_sat[_rr: _rr + _ncols]
                        ):
                            with _cs[_jj]:
                                if _lbl_disp is not None:
                                    _md = ((_lbl_disp == _cid) * 255).astype(np.uint8)
                                else:
                                    _md = np.zeros((4, 4), dtype=np.uint8)
                                st.image(
                                    _md,
                                    caption=f"#{_cid+1} {TEXTURE_LABELS.get(_rl, _rl)}\n{_cv:.0f}%",
                                    use_container_width=True,
                                )
                                with open(_pp, "rb") as _fh:
                                    st.download_button(
                                        "PNG", _fh.read(),
                                        file_name=Path(_pp).name,
                                        mime="image/png",
                                        key=f"dl_satmask_c{_cid}",
                                        use_container_width=True,
                                    )

                    _zip = io.BytesIO()
                    with zipfile.ZipFile(_zip, "w", zipfile.ZIP_DEFLATED) as _zf:
                        for _, _, _pp, _, _ in _files_sat:
                            _zf.write(_pp, Path(_pp).name)
                    _zip.seek(0)
                    st.download_button(
                        "Télécharger masques SatMap (.zip)",
                        _zip.getvalue(),
                        file_name=f"masks_satmap_{format_timestamp()}.zip",
                        mime="application/zip",
                        key="dl_satmasks_zip",
                        use_container_width=True,
                    )

                    # ── Diagnostic QTRE SatMap ──────────────────────────────
                    st.markdown("#### Diagnostic QTRE")
                    st.caption(
                        "Vérifie que chaque bloc 32m n'a pas plus de 4 textures actives. "
                        "La correction conserve les 4 clusters dominants par bloc et annule les autres."
                    )
                    _sdiag_key = f"_qtre_sat_{_sat_info['dir']}"
                    _sdir = Path(_sat_info["dir"])

                    if st.button("Vérifier les masques QTRE (SatMap)", key="btn_diag_sat_qtre"):
                        with st.spinner(f"Analyse de {len(_files_sat)} masques…"):
                            _STHOLD = 1.0 / 65535 * 128   # ~0.5px sur 32px bloc
                            _sda = []
                            for _, _, _pp, _, _ in _files_sat:
                                _a = np.array(Image.open(_pp), dtype=np.float32)
                                _sda.append(_a / (65535.0 if _a.max() > 255 else 255.0))
                            _sH, _sW = _sda[0].shape
                            _sbpx = 32 if _sH <= 9000 else 127
                            _sny  = (_sH + _sbpx - 1) // _sbpx
                            _snx  = (_sW + _sbpx - 1) // _sbpx
                            _stot = _sny * _snx
                            _sstk = np.stack(_sda, axis=0)
                            _sph  = _sny * _sbpx - _sH
                            _spw  = _snx * _sbpx - _sW
                            _ssp  = np.pad(_sstk, ((0, 0), (0, _sph), (0, _spw)))
                            _sbm  = _ssp.reshape(len(_sda), _sny, _sbpx, _snx, _sbpx).mean(axis=(2, 4))
                            _scnt = (_sbm > _STHOLD).sum(axis=0)
                            _svyx = np.argwhere(_scnt > 4).tolist()
                            _svdrops = []
                            _sfnames = [Path(_pp).name for _, _, _pp, _, _ in _files_sat]
                            for _sby, _sbx in _svyx:
                                _ssidx = np.argsort(_sbm[:, _sby, _sbx])[::-1]
                                _saidx = [i for i in _ssidx if _sbm[i, _sby, _sbx] > _STHOLD]
                                _svdrops.append((_sby, _sbx, [_sfnames[i] for i in _saidx[4:]]))
                            st.session_state[_sdiag_key] = {
                                "nv": len(_svyx), "pct": len(_svyx) / _stot * 100,
                                "total": _stot, "block_px": _sbpx,
                                "H": _sH, "W": _sW, "vdrops": _svdrops,
                            }

                    if _sdiag_key in st.session_state:
                        _sdg = st.session_state[_sdiag_key]
                        _sqc1, _sqc2, _sqc3 = st.columns(3)
                        _sqc1.metric("Blocs 32m analysés", f"{_sdg['total']:,}")
                        _sqc2.metric(
                            "Violations (>4 tex./bloc)", str(_sdg["nv"]),
                            delta="OK" if _sdg["nv"] == 0 else f"{_sdg['pct']:.2f}%",
                            delta_color="normal" if _sdg["nv"] == 0 else "inverse",
                        )
                        _sqc3.metric("Taux", f"{_sdg['pct']:.3f}%")

                        if _sdg["nv"] == 0:
                            st.success("Aucune violation QTRE — masques prêts pour l'import Workbench.")
                        else:
                            st.warning(
                                f"{_sdg['nv']} blocs en conflit ({_sdg['pct']:.2f}%). "
                                "La correction conserve les 4 clusters dominants par bloc."
                            )
                            if st.button("Corriger et re-sauvegarder", key="btn_fix_sat_qtre"):
                                with st.spinner("Correction en cours…"):
                                    _scn, _sca = [], []
                                    for _sfp in sorted(_sdir.glob("*.png")):
                                        _sa2 = np.array(Image.open(_sfp), dtype=np.float32)
                                        _scn.append(_sfp.name)
                                        _sca.append(_sa2 / (65535.0 if _sa2.max() > 255 else 255.0))
                                    _scr = {n: a.copy() for n, a in zip(_scn, _sca)}
                                    _sbpx2 = _sdg["block_px"]
                                    _sH2, _sW2 = _sdg["H"], _sdg["W"]
                                    for _sby2, _sbx2, _sdrop in _sdg["vdrops"]:
                                        _sy0 = _sby2 * _sbpx2; _sy1 = min(_sy0 + _sbpx2, _sH2)
                                        _sx0 = _sbx2 * _sbpx2; _sx1 = min(_sx0 + _sbpx2, _sW2)
                                        for _sn in _sdrop:
                                            if _sn in _scr:
                                                _scr[_sn][_sy0:_sy1, _sx0:_sx1] = 0.0
                                    for _sn, _sa in _scr.items():
                                        Image.fromarray(
                                            (_sa * 65535).clip(0, 65535).astype(np.uint16)
                                        ).save(str(_sdir / _sn))
                                    del st.session_state[_sdiag_key]
                                    st.success(f"{len(_scr)} masques corrigés dans {_sdir.name}/")
                                    st.rerun()

    with _e_recon:
        import io
        import zipfile
        st.markdown("### 🗺️ Carte de reconstitution — blend de masques")
        st.caption(
            "Charge tous les masques PNG d'un dossier et génère une vue aérienne colorée. "
            "Pour chaque pixel : couleur = moyenne pondérée des couleurs de matériaux par leur valeur de masque."
        )

        # ── Couleurs aériennes par mot-clé (ordre : priorité décroissante) ──
        _RECON_KW_COLORS = [
            (["seabed", "fond_marin", "sea", "ocean"],          ( 55, 100, 155)),
            (["snow", "neige", "ice", "glace"],                  (218, 224, 232)),
            (["rock", "roche", "debrisrock", "debris"],          (108, 105,  98)),
            (["asphalt", "concrete", "cobblestone",
              "groundsport", "sport"],                           (118, 115, 110)),
            (["sand", "sable"],                                  (178, 162, 128)),
            (["pebble", "pebbles", "galet"],                     (155, 148, 130)),
            (["pine", "forestpine"],                             ( 28,  62,  32)),
            (["conifer"],                                        ( 32,  68,  36)),
            (["deciduous", "decidious", "forestdecid"],          ( 42,  78,  35)),
            (["clearing", "clairiere"],                          ( 68, 102,  52)),
            (["mountain", "montain", "montaingrass"],            ( 88, 108,  68)),
            (["coastal", "beachgrass", "beach"],                 (108, 142,  72)),
            (["heather", "heath"],                               (145, 102, 138)),
            (["crop", "cropfield", "field"],                     (138, 130,  68)),
            (["dirt", "terre", "soil"],                          (122, 105,  82)),
            (["grass", "prairie", "prairie"],                      ( 68, 125,  52)),
        ]
        _RECON_DEFAULT_COLOR = (120, 120, 120)

        def _recon_color_for(stem: str):
            s = stem.lower()
            # Retirer les préfixes génériques "mask", "mask_", "masl_"
            for pfx in ("masl_", "mask_", "mak ", "mask "):
                if s.startswith(pfx):
                    s = s[len(pfx):]
            for keywords, color in _RECON_KW_COLORS:
                if any(kw in s for kw in keywords):
                    return color
            return _RECON_DEFAULT_COLOR

        # ── Sélection dossier ────────────────────────────────────────────────
        _recon_proj_path = st.session_state.get("current_project_path", "")
        _recon_default = (
            str(Path(_recon_proj_path) / "sources" / "export mask text")
            if _recon_proj_path else ""
        )
        _recon_folder = st.text_input(
            "📁 Dossier des masques PNG",
            value=_recon_default,
            key="recon_folder",
            placeholder="ex: H:/…/sources/export mask text",
        ).strip().strip('"').strip("'")

        _recon_res = st.select_slider(
            "Résolution de sortie (px)",
            options=[512, 1024, 2048, 4096],
            value=2048,
            key="recon_res",
        )

        # ── Scan du dossier ─────────────────────────────────────────────────
        if _recon_folder and Path(_recon_folder).is_dir():
            _recon_pngs = sorted(Path(_recon_folder).glob("*.png"))
            if not _recon_pngs:
                st.warning("Aucun fichier PNG trouvé dans ce dossier.")
            else:
                st.caption(f"{len(_recon_pngs)} masque(s) détecté(s).")

                # Tableau de correspondance couleur → matériau
                _recon_rows = []
                for _rf in _recon_pngs:
                    _rc = _recon_color_for(_rf.stem)
                    _recon_rows.append({
                        "Fichier": _rf.name,
                        "Couleur R": _rc[0], "Couleur G": _rc[1], "Couleur B": _rc[2],
                    })
                with st.expander("Correspondances couleur ↔ matériau", expanded=False):
                    _pd_recon = __import__("pandas")
                    _df_recon = _pd_recon.DataFrame(_recon_rows)
                    st.dataframe(_df_recon, use_container_width=True, hide_index=True)

                if st.button("🗺️ Générer la carte de reconstitution", key="btn_recon_gen"):
                    try:
                        with st.spinner(f"⏳ Chargement de {len(_recon_pngs)} masques…"):
                            Image.MAX_IMAGE_PIXELS = None  # masques > 179 Mpx (ex. 16257²)
                            _R = _recon_res
                            _acc_rgb  = np.zeros((_R, _R, 3), dtype=np.float64)
                            _acc_w    = np.zeros((_R, _R),    dtype=np.float64)

                            for _rf in _recon_pngs:
                                _col = _recon_color_for(_rf.stem)
                                _col_arr = np.array(_col, dtype=np.float64)

                                _img_raw = Image.open(str(_rf)).convert("L")
                                _img_r   = _img_raw.resize((_R, _R), Image.LANCZOS)
                                _arr     = np.array(_img_r, dtype=np.float64) / 255.0

                                _acc_rgb += _arr[:, :, np.newaxis] * _col_arr
                                _acc_w   += _arr

                            # Division par le poids total (évite division par zéro)
                            _acc_w_safe = np.where(_acc_w > 1e-6, _acc_w, 1.0)
                            _result_rgb = (_acc_rgb / _acc_w_safe[:, :, np.newaxis]).clip(0, 255)

                            # Pixels sans aucun masque → gris neutre
                            _no_data = _acc_w < 1e-6
                            _result_rgb[_no_data] = 80.0

                            _result_u8 = _result_rgb.astype(np.uint8)
                            _result_img = Image.fromarray(_result_u8, mode="RGB")

                            # Sauvegarde
                            _recon_out_dir = Path(get_output_dir())
                            _recon_out_dir.mkdir(parents=True, exist_ok=True)
                            _recon_fname = f"reconstruction_{_R}px_{format_timestamp()}.png"
                            _recon_out_path = _recon_out_dir / _recon_fname
                            _result_img.save(str(_recon_out_path))

                            st.session_state["recon_result"] = {
                                "img": _result_u8,
                                "path": str(_recon_out_path),
                                "fname": _recon_fname,
                            }

                        st.success(f"Carte générée — {_R}×{_R} px")
                    except Exception as _ex_recon:
                        st.error(f"Erreur : {_ex_recon}")
                        st.exception(_ex_recon)

                if "recon_result" in st.session_state:
                    _rr = st.session_state["recon_result"]
                    st.image(_rr["img"], caption=_rr["fname"], use_container_width=True)
                    _recon_buf = io.BytesIO()
                    Image.fromarray(_rr["img"]).save(_recon_buf, format="PNG")
                    st.download_button(
                        "⬇️ Télécharger la carte PNG",
                        _recon_buf.getvalue(),
                        file_name=_rr["fname"],
                        mime="image/png",
                        key="dl_recon_png",
                        use_container_width=True,
                    )

                # ── Overlay de zones ─────────────────────────────────────────
                if "recon_result" in st.session_state and _recon_pngs:
                    st.markdown("---")
                    st.markdown("#### 🔍 Overlay de zones")
                    st.caption(
                        "Détecte automatiquement les grandes catégories de zones "
                        "et les superpose en couleur sur la carte de base."
                    )

                    # Définition des zones : (nom, mots-clés fichier, couleur RGB, description)
                    _ZONE_DEFS = [
                        ("Urbain",       ["asphalt", "cobblestone", "concrete", "groundsport"],
                         (230,  60,  30), "Routes, béton, pavés"),
                        ("Agriculture",  ["crop", "cropfield", "field", "zicrop"],
                         (220, 190,   0), "Champs cultivés"),
                        ("Forêt dense",  ["pine", "forestpine", "conifer", "deciduous",
                                          "decidious", "forestdecid"],
                         ( 20,  90,  20), "Forêt de pins et feuillus"),
                        ("Clairière",    ["clearing", "clairiere"],
                         ( 80, 160,  50), "Lisières et clairières"),
                        ("Bruyère",      ["heather", "heath"],
                         (180,  60, 180), "Landes / bruyère"),
                        ("Plage/Galets", ["sand", "sable", "pebble", "pebbles", "beach",
                                          "beachgrass", "coastal"],
                         (210, 185,  90), "Plages, galets, herbe côtière"),
                        ("Roche",        ["rock", "roche", "debrisrock", "debris"],
                         (160, 148, 135), "Rochers et débris"),
                        ("Eau",          ["seabed", "sea", "ocean"],
                         ( 40,  90, 200), "Fond marin / eau"),
                        ("Herbe/Prairie",["grass", "prairie", "prairie", "montain",
                                          "mountain", "montaingrass"],
                         ( 60, 180,  60), "Herbe et prairie"),
                    ]

                    # Contrôles
                    _ov_col1, _ov_col2 = st.columns([3, 1])
                    with _ov_col1:
                        _ov_opacity = st.slider(
                            "Opacité de l'overlay",
                            min_value=10, max_value=220, value=130, step=10,
                            key="recon_overlay_opacity",
                        )
                    with _ov_col2:
                        _ov_seuil = st.number_input(
                            "Seuil masque (0–1)",
                            min_value=0.01, max_value=0.5, value=0.08, step=0.01,
                            key="recon_overlay_seuil",
                            help="Valeur minimale dans le masque pour considérer un pixel comme actif.",
                        )

                    # Checkboxes par zone (2 colonnes)
                    st.markdown("**Zones à afficher :**")
                    _ov_zone_cols = st.columns(3)
                    _ov_active = {}
                    for _zi, (_zn, _zkw, _zc, _zdesc) in enumerate(_ZONE_DEFS):
                        with _ov_zone_cols[_zi % 3]:
                            _color_hex = "#{:02X}{:02X}{:02X}".format(*_zc)
                            _ov_active[_zn] = st.checkbox(
                                f"● {_zn}",
                                value=True,
                                key=f"recon_zone_{_zi}",
                                help=f"{_zdesc} — couleur {_color_hex}",
                            )

                    if st.button("🔍 Générer l'overlay", key="btn_recon_overlay"):
                        try:
                            with st.spinner("⏳ Analyse des zones…"):
                                Image.MAX_IMAGE_PIXELS = None
                                _R2 = st.session_state["recon_result"]["img"].shape[0]

                                # Accumuler les masques par zone
                                _zone_masks = {zn: np.zeros((_R2, _R2), np.float32)
                                               for zn, _, _, _ in _ZONE_DEFS}

                                for _rf2 in _recon_pngs:
                                    _stem2 = _rf2.stem.lower()
                                    for pfx in ("masl_", "mask_", "mak ", "mask "):
                                        if _stem2.startswith(pfx):
                                            _stem2 = _stem2[len(pfx):]
                                    _img2 = Image.open(str(_rf2)).convert("L")
                                    _img2 = _img2.resize((_R2, _R2), Image.LANCZOS)
                                    _arr2 = np.array(_img2, dtype=np.float32) / 255.0

                                    for _zn2, _zkw2, _, _ in _ZONE_DEFS:
                                        if any(kw in _stem2 for kw in _zkw2):
                                            _zone_masks[_zn2] = np.clip(
                                                _zone_masks[_zn2] + _arr2, 0.0, 1.0
                                            )

                                # Construire l'overlay RGBA
                                _base_img2 = Image.fromarray(
                                    st.session_state["recon_result"]["img"]
                                ).convert("RGBA")
                                _overlay2 = Image.new("RGBA", (_R2, _R2), (0, 0, 0, 0))

                                _legend = []
                                for _zn2, _, _zc2, _zdesc2 in _ZONE_DEFS:
                                    if not _ov_active.get(_zn2, True):
                                        continue
                                    _zm = _zone_masks[_zn2] > float(_ov_seuil)
                                    if not np.any(_zm):
                                        continue
                                    _layer = np.zeros((_R2, _R2, 4), dtype=np.uint8)
                                    _layer[_zm] = (*_zc2, int(_ov_opacity))
                                    _overlay2 = Image.alpha_composite(
                                        _overlay2,
                                        Image.fromarray(_layer, "RGBA"),
                                    )
                                    _legend.append((_zn2, _zc2, _zdesc2,
                                                    int(np.sum(_zm) / (_R2 * _R2) * 100)))

                                _composite = Image.alpha_composite(_base_img2, _overlay2)
                                _composite_rgb = np.array(_composite.convert("RGB"))

                                st.session_state["recon_overlay"] = {
                                    "img": _composite_rgb,
                                    "legend": _legend,
                                }

                        except Exception as _ex_ov:
                            st.error(f"Erreur : {_ex_ov}")
                            st.exception(_ex_ov)

                    if "recon_overlay" in st.session_state:
                        _rov = st.session_state["recon_overlay"]
                        st.image(_rov["img"], use_container_width=True)

                        # Légende
                        st.markdown("**Légende :**")
                        _leg_cols = st.columns(3)
                        for _li, (_lzn, _lzc, _lzdesc, _lpct) in enumerate(_rov["legend"]):
                            with _leg_cols[_li % 3]:
                                _lhex = "#{:02X}{:02X}{:02X}".format(*_lzc)
                                st.markdown(
                                    f'<span style="background:{_lhex};padding:2px 8px;'
                                    f'border-radius:3px;color:#fff;font-size:0.8em">&nbsp;</span> '
                                    f'**{_lzn}** — {_lpct}%',
                                    unsafe_allow_html=True,
                                )

                        _ov_buf = io.BytesIO()
                        Image.fromarray(_rov["img"]).save(_ov_buf, format="PNG")
                        st.download_button(
                            "⬇️ Télécharger la carte avec overlay",
                            _ov_buf.getvalue(),
                            file_name=f"reconstruction_overlay_{format_timestamp()}.png",
                            mime="image/png",
                            key="dl_recon_overlay_png",
                            use_container_width=True,
                        )


        elif _recon_folder:
            st.warning("Dossier introuvable.")

    # ── Analyse ──────────────────────────────────────────────────────────────
    with _t_analyse:
        st.markdown("### 📈 Analyse Heightmap")

        base_map = st.session_state.base_map

        # Métriques de base (toujours disponibles via BaseMap)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Dimensions", f"{base_map.width}×{base_map.height}px")
        with col2:
            st.metric("Alt. Min", f"{base_map.altitude_min:.0f}m")
        with col3:
            st.metric("Alt. Max", f"{base_map.altitude_max:.0f}m")
        with col4:
            st.metric("Dénivellation", f"{(base_map.altitude_max - base_map.altitude_min):.0f}m")

        st.divider()

        # Données terrain_stats depuis nat_gen (disponibles après génération aperçu texture)
        _nat_an = st.session_state.get("nat_gen")
        _ts     = getattr(_nat_an, "terrain_stats", {}) if _nat_an else {}

        if _ts:
            st.markdown("#### Calibration automatique auto-matériau")
            st.caption(
                "Ces valeurs sont calculées sur les **pixels terrestres** uniquement "
                "(pixels eau exclus). Elles servent à calibrer les zones de texture "
                "en fonction de la topographie réelle de votre carte."
            )

            # ── Altitudes ─────────────────────────────────────────────────────
            st.markdown("**Percentiles d'altitude (terrain ferme)**")
            _alt_rows = [
                {"Percentile": "P2 (plancher)", "Altitude (m)": f"{_ts['alt_p2_m']:.1f}", "Fraction": "0.00"},
                {"Percentile": "P25 (Q1)",      "Altitude (m)": f"{_ts['alt_p25_m']:.1f}", "Fraction": f"{_ts['frac_p25']:.2f}"},
                {"Percentile": "P50 (médiane)", "Altitude (m)": f"{_ts['alt_p50_m']:.1f}", "Fraction": f"{_ts['frac_p50']:.2f}"},
                {"Percentile": "P75 (Q3)",      "Altitude (m)": f"{_ts['alt_p75_m']:.1f}", "Fraction": f"{_ts['frac_p75']:.2f}"},
                {"Percentile": "P90",           "Altitude (m)": f"{_ts.get('alt_p90_m', 0):.1f}", "Fraction": f"{_ts['frac_p90']:.2f}"},
                {"Percentile": "P98 (plafond)", "Altitude (m)": f"{_ts['alt_p98_m']:.1f}", "Fraction": "1.00"},
            ]
            st.dataframe(_alt_rows, use_container_width=False, hide_index=True)

            # ── Pentes ────────────────────────────────────────────────────────
            st.markdown("**Percentiles de pente — degrés réels (terrain ferme)**")
            st.caption(
                "⚠️ Les pentes affichées dans l'onglet *Hypsométrique* viennent de BaseMap "
                "et sont visuelles (exagérées). Ces valeurs sont calculées en **degrés physiques réels** "
                "depuis la heightmap métrique."
            )
            _slp_rows = [
                {"Percentile": "Moyenne",  "Pente (°)": f"{_ts['slope_mean_deg']:.1f}"},
                {"Percentile": "P50",      "Pente (°)": f"{_ts['slope_p50_deg']:.1f}"},
                {"Percentile": "P75",      "Pente (°)": f"{_ts['slope_p75_deg']:.1f}"},
                {"Percentile": "P85",      "Pente (°)": f"{_ts['slope_p85_deg']:.1f}"},
                {"Percentile": "P90",      "Pente (°)": f"{_ts['slope_p90_deg']:.1f}"},
                {"Percentile": "P95",      "Pente (°)": f"{_ts['slope_p95_deg']:.1f}"},
            ]
            st.dataframe(_slp_rows, use_container_width=False, hide_index=True)

            # ── Zones texture déduites ────────────────────────────────────────
            st.markdown("**Zones texture déduites (biome actif)**")
            _biome_sel = st.session_state.get("biome_choice", "Tempéré")
            try:
                from map_generator.domain.services.terrain_score_service import CLIMATE_TABLE
                _cp_an  = CLIMATE_TABLE.get(_biome_sel, CLIMATE_TABLE["Tempéré"])
                _hum_an = float(_cp_an["humidity"])
                _rs_an  = float(_cp_an["rock_slope_base"])
                _rs_base_an = float(np.clip(_rs_an * (1.0 + (1.0 - _hum_an) * 0.15), 25.0, 55.0))
                _s90_an = _ts.get("slope_p90_deg", _rs_base_an)
                _scale_an = float(np.clip(_s90_an / max(_rs_base_an, 1.0), 0.35, 2.0))
                _rock_s_an = float(np.clip(_rs_base_an * _scale_an, 12.0, 65.0))
                _h2m_an = lambda f: f"{_ts['alt_p2_m'] + f * _ts['alt_range_m']:.0f}m"
                _zone_rows = [
                    {"Zone": "Prairie",                "Altitude":  f"0 – {_h2m_an(_ts['frac_p50'])}",  "Pente": "0 – 22°"},
                    {"Zone": "Lande (chevauchement)",  "Altitude":  f"{_h2m_an(_ts['frac_p25'])} – {_h2m_an(min(_ts['frac_p75'], 0.85))}", "Pente": "0 – 28°"},
                    {"Zone": "Lande dominante",        "Altitude":  f"{_h2m_an(_ts['frac_p50'])} – {_h2m_an(_ts['frac_p90'])}", "Pente": "0 – 28°"},
                    {"Zone": "Roche (altitude)",       "Altitude":  f"{_h2m_an(_ts['frac_p90'])} +",    "Pente": f"> {_rock_s_an * 0.5:.0f}°"},
                    {"Zone": "Roche (pente)",          "Altitude":  "toutes",                            "Pente": f"> {_rock_s_an:.1f}°  (seuil calibré)"},
                    {"Zone": "Érosion",                "Altitude":  f"0 – {_h2m_an(0.55)}",             "Pente": f"{_rock_s_an * 0.35:.0f}° – {_rock_s_an * 0.78:.0f}°"},
                ]
                st.dataframe(_zone_rows, use_container_width=True, hide_index=True)
                st.caption(
                    f"Biome : **{_biome_sel}** — seuil roche calibré : "
                    f"base {_rs_base_an:.1f}° × {_scale_an:.2f} (slope_p90={_s90_an:.1f}°) "
                    f"→ **{_rock_s_an:.1f}°**"
                )
            except Exception as _ez:
                st.warning(f"Impossible de calculer les zones texture : {_ez}")

        else:
            st.info(
                "⚠️ Générez d'abord l'**Aperçu Texture** (onglet 🎨 Génération) "
                "pour afficher la calibration automatique (percentiles altitude/pente, zones texture)."
            )
            # Fallback : histogrammes BaseMap (matplotlib — évite les warnings Vega-Lite)
            import matplotlib.pyplot as _plt_h
            st.markdown("#### Distribution des altitudes (BaseMap)")
            altitude_data = base_map.heightmap_uint8.flatten()
            _alt_counts, _alt_edges = np.histogram(altitude_data, bins=100)
            if _alt_counts.sum() > 0:
                _fig_a, _ax_a = _plt_h.subplots(figsize=(8, 2))
                _ax_a.bar(_alt_edges[:-1], _alt_counts, width=np.diff(_alt_edges), align="edge", color="#4a7fb5")
                _ax_a.set_xlabel("Valeur (0-255)")
                _ax_a.set_ylabel("Pixels")
                _ax_a.tick_params(labelsize=7)
                _fig_a.tight_layout()
                st.pyplot(_fig_a, use_container_width=True)
                _plt_h.close(_fig_a)

            st.markdown("#### Distribution des pentes (BaseMap — valeurs visuelles, non physiques)")
            if hasattr(base_map, "slopes") and base_map.slopes is not None:
                slopes_data = base_map.slopes.flatten()
                slopes_data = slopes_data[~np.isnan(slopes_data)]
                _sl_counts, _sl_edges = np.histogram(slopes_data, bins=50)
                if _sl_counts.sum() > 0:
                    _fig_s, _ax_s = _plt_h.subplots(figsize=(8, 2))
                    _ax_s.bar(_sl_edges[:-1], _sl_counts, width=np.diff(_sl_edges), align="edge", color="#6aaa64")
                    _ax_s.set_xlabel("Pente (valeur brute)")
                    _ax_s.set_ylabel("Pixels")
                    _ax_s.tick_params(labelsize=7)
                    _fig_s.tight_layout()
                    st.pyplot(_fig_s, use_container_width=True)
                    _plt_h.close(_fig_s)
            else:
                st.info("Pentes non calculées dans BaseMap")
    
    # ── Végétation ───────────────────────────────────────────────────────────
    with _g_veg:
        import io as _io_veg
        from vegetation_generator import VegetationGenerator, VEG_TYPES, VEG_COLORS, VEG_LABELS

        st.markdown("### 🌱 Carte de Végétation Potentielle")
        st.caption(
            "Génère une carte 2D des types de végétation probables "
            "à partir des signaux morphologiques du terrain."
        )

        _nat_veg = st.session_state.get("nat_gen")
        _tr_veg  = st.session_state.get("tex_reforger")

        if _nat_veg is None:
            st.info(
                "⚠️ Générez d'abord l'**Aperçu Texture** (onglet 🎨 Génération) "
                "pour charger les signaux terrain."
            )
        else:
            # ── Options ──────────────────────────────────────────────────────
            _veg_c1, _veg_c2 = st.columns(2)
            with _veg_c1:
                _veg_blend = st.toggle(
                    "Dégradé aux frontières",
                    value=True, key="veg_blend",
                    help="Activé : mélange pondéré des couleurs. Désactivé : couleur franche.",
                )
                _veg_min_score = st.slider(
                    "Score minimum d'apparition",
                    0.05, 0.50, 0.15, 0.05, key="veg_min_score",
                )
            with _veg_c2:
                _veg_res = st.select_slider(
                    "Résolution de sortie (px)",
                    options=[512, 1024, 2048, 4096],
                    value=1024, key="veg_res",
                )
                _veg_use_lock = st.toggle(
                    "Exclure zones verrouillées (champs/urbain)",
                    value=False, key="veg_use_lock",
                    help="Si activé, sélectionnez le dossier des masques exportés.",
                )

            _veg_lock_masks = None
            if _veg_use_lock:
                _veg_lock_folder = st.text_input(
                    "📁 Dossier masques exportés",
                    value=str(Path(st.session_state.current_project_path) / "sources" / "export mask text")
                    if st.session_state.current_project_path else "",
                    key="veg_lock_folder",
                ).strip().strip('"').strip("'")
                if _veg_lock_folder and Path(_veg_lock_folder).is_dir():
                    _LOCK_STEMS = ["asphalt", "cobblestone", "concrete", "crop", "field", "sport"]
                    _veg_lock_masks = {}
                    Image.MAX_IMAGE_PIXELS = None
                    for _lp in Path(_veg_lock_folder).glob("*.png"):
                        if any(kw in _lp.stem.lower() for kw in _LOCK_STEMS):
                            _veg_lock_masks[_lp.stem] = np.array(
                                Image.open(str(_lp)).convert("L")
                            )
                    if _veg_lock_masks:
                        st.caption(f"{len(_veg_lock_masks)} masque(s) verrouillé(s) détecté(s).")
                    else:
                        st.caption("Aucun masque verrouillé trouvé.")

            # ── Génération ───────────────────────────────────────────────────
            if st.button("🌱 Générer la carte de végétation", key="btn_gen_veg"):
                try:
                    with st.spinner("⏳ Calcul des scores de végétation…"):
                        _vgen = VegetationGenerator(_nat_veg, _nat_veg.cellsize)

                        # Masque eau depuis heightmap directement
                        _mw_veg = (_nat_veg.heightmap_original < 0)

                        _veg_scores = _vgen.compute(_mw_veg, lock_masks=_veg_lock_masks)
                        _veg_rgb    = _vgen.render_rgb(
                            _veg_scores,
                            mask_water=_mw_veg,
                            min_score=_veg_min_score,
                            blend=_veg_blend,
                        )

                    # Redimensionner à la résolution choisie
                    _R = _veg_res
                    _veg_img_pil = Image.fromarray(_veg_rgb).resize((_R, _R), Image.LANCZOS)
                    _veg_arr_out = np.array(_veg_img_pil)

                    # Sauvegarder en session
                    st.session_state.veg_result = {
                        "image":  _veg_arr_out,
                        "scores": _veg_scores,
                        "res":    _R,
                    }

                    # Sauvegarder sur disque
                    _veg_out_dir = get_output_dir()
                    _veg_fname   = f"{_veg_out_dir}/vegetation_{format_timestamp()}.png"
                    _veg_img_pil.save(_veg_fname)
                    st.success(f"✅ Carte générée → {Path(_veg_fname).name}")

                except Exception as _e_veg:
                    st.error(f"❌ Erreur : {_e_veg}")
                    import traceback
                    st.code(traceback.format_exc())

            # ── Affichage résultat ────────────────────────────────────────────
            _vr = st.session_state.get("veg_result")
            if _vr is not None:
                st.image(_vr["image"], caption="Végétation potentielle", use_container_width=True)

                # Légende
                st.markdown("**Légende**")
                _leg_cols = st.columns(4)
                _legend_entries = [
                    {"color": ( 55,  90, 140), "label": "Eau",                  "linear": False},
                    {"color": ( 60,  55,  50), "label": "Sans végétation / roche", "linear": False},
                ] + [{"color": _vt["color"], "label": _vt["label"], "linear": _vt["linear"]} for _vt in VEG_TYPES]
                for _li, _vt in enumerate(_legend_entries):
                    _c = _vt["color"]
                    _hex = "#{:02X}{:02X}{:02X}".format(*_c)
                    _tag = " *(linéaire)*" if _vt["linear"] else ""
                    _leg_cols[_li % 4].markdown(
                        f'<span style="display:inline-block;width:14px;height:14px;'
                        f'background:{_hex};border-radius:3px;margin-right:4px;'
                        f'vertical-align:middle"></span>{_vt["label"]}{_tag}',
                        unsafe_allow_html=True,
                    )

                # Export PNG
                _veg_buf = _io_veg.BytesIO()
                Image.fromarray(_vr["image"]).save(_veg_buf, format="PNG")
                st.download_button(
                    "⬇️ Télécharger la carte végétation",
                    _veg_buf.getvalue(),
                    file_name=f"vegetation_{format_timestamp()}.png",
                    mime="image/png",
                    key="dl_veg_png",
                    use_container_width=True,
                )

    # ── Fusion masques ────────────────────────────────────────────────────────
    with _e_fusion:
        import io as _io_fus
        import zipfile as _zp_fus
        st.markdown("### 🔀 Fusion Masques")
        st.caption(
            "☑ un masque = le contenu Workbench l'emporte sur l'auto-material. "
            "☐ = l'auto-material gère seul. "
            "La priorité règle la force d'écrasement. "
            "Les zones non couvertes par aucun masque WB sont comblées par l'auto-material."
        )

        # Couleurs de rendu par rôle (aperçu split view)
        _FUS_ROLE_CLR = {
            "fond_marin":   ( 55, 100, 155), "sable":       (178, 162, 128),
            "cotier":       (108, 142,  72), "galets":      (155, 148, 130),
            "roche":        (108, 105,  98), "débris":      (120, 115, 108),
            "erosion":      (122, 105,  82), "prairie":       ( 68, 125,  52),
            "lande":       ( 88, 108,  68), "feuillus":       ( 42,  78,  35),
            "coniferes":  ( 28,  62,  32), "lisiere":( 68, 102,  52),
            "neige":        (218, 224, 232),
        }

        def _fus_render(masks, sz):
            _rgb = np.zeros((sz, sz, 3), np.float32)
            for _rl, _a in masks.items():
                _col = np.array(_FUS_ROLE_CLR.get(_rl, (120, 120, 120)), np.float32)
                _rs  = np.array(Image.fromarray(_a).resize((sz, sz), Image.BILINEAR)) if _a.shape[0] != sz else _a
                _rgb += _rs[:, :, np.newaxis] * _col
            return np.clip(_rgb, 0, 255).astype(np.uint8)

        def _fus_strip(stem):
            s = stem.lower()
            for pfx in ("masl_", "mask_", "mak ", "mask "):
                if s.startswith(pfx):
                    s = s[len(pfx):]
            return s

        # ── Sources ──────────────────────────────────────────────────────────
        _fus_tr = st.session_state.get("tex_reforger")
        _fus_ok = _fus_tr is not None and "constrained_scores" in _fus_tr

        _sc1, _sc2 = st.columns(2)
        (_sc1.success if _fus_ok else _sc1.error)(
            "✅ Aperçu Texture disponible" if _fus_ok else "❌ Générez d'abord l'Aperçu Texture"
        )

        _fus_proj = st.session_state.get("current_project_path", "")
        _fus_def  = str(Path(_fus_proj) / "sources" / "export mask text") if _fus_proj else ""
        _fus_folder = st.text_input(
            "📁 Masques Workbench exportés",
            value=st.session_state.get("fusion2_folder", _fus_def),
            key="fusion2_folder",
            placeholder="ex: H:/…/sources/export mask text",
        ).strip().strip('"').strip("'")

        if not _fus_ok:
            st.info("⚠️ Générez d'abord l'**Aperçu Texture** (onglet 🎨 Génération).")
        elif not _fus_folder:
            st.info("Indiquez le dossier contenant les masques exportés Workbench.")
        elif not Path(_fus_folder).is_dir():
            st.warning("Dossier introuvable.")
        else:
            _fus_pngs = sorted(Path(_fus_folder).glob("*.png"))
            if not _fus_pngs:
                st.warning("Aucun fichier PNG dans ce dossier.")
            else:
                from reforger_texture_budget import mat_to_role as _fus_m2r
                _cs = _fus_tr["constrained_scores"]  # {role: float32 arr HxW}

                # Associer chaque fichier à un rôle
                _fus_files = []
                for _pf in _fus_pngs:
                    _r = _fus_m2r(_fus_strip(_pf.stem))
                    _fus_files.append({"file": _pf, "role": _r, "in_auto": _r in _cs})

                st.caption(f"{len(_fus_files)} masque(s) Workbench — "
                           f"{sum(1 for f in _fus_files if f['in_auto'])} avec rôle auto-material")

                # ── Tableau masques + priorité ────────────────────────────────
                st.markdown("#### Masques — ☑ = Workbench l'emporte")
                _PRIOS  = ["Haute", "Moyen", "Basse"]
                _PRIO_W = {"Haute": 1.0, "Moyen": 0.55, "Basse": 0.2}

                # Rôles disponibles = auto-material + bibliothèque de matériaux + zones spéciales
                _lib_roles = [
                    r["id"] for r in
                    st.session_state.get("material_library", {}).get("roles", [])
                ]
                _extra_roles = [
                    "urbain", "champs", "route", "asphalte", "cobblestone",
                    "sport", "industrie", "eau",
                ]
                _cs_roles_list = sorted(
                    set(list(_cs.keys()) + _lib_roles + _extra_roles)
                )

                _hdr = st.columns([0.4, 2.2, 2.4, 1.6])
                for _hc, _ht in zip(_hdr, ["**☑**", "**Fichier**", "**Rôle**", "**Priorité**"]):
                    _hc.markdown(_ht)

                _fus_sel = {}
                for _fi in _fus_files:
                    _row = st.columns([0.4, 2.2, 2.4, 1.6])
                    _chk = _row[0].checkbox(
                        "Actif", value=True, key=f"fus_chk_{_fi['file'].name}",
                        label_visibility="collapsed",
                    )
                    _row[1].caption(_fi["file"].name)
                    _role_opts = (
                        _cs_roles_list if _fi["role"] in _cs_roles_list
                        else [_fi["role"]] + _cs_roles_list
                    )
                    _role_sel = _row[2].selectbox(
                        "Rôle", options=_role_opts,
                        index=_role_opts.index(_fi["role"]),
                        key=f"fus_role_{_fi['file'].name}",
                        label_visibility="collapsed",
                    )
                    _prio = _row[3].select_slider(
                        "Priorité", options=_PRIOS, value="Haute",
                        key=f"fus_prio_{_fi['file'].name}",
                        label_visibility="collapsed", disabled=not _chk,
                    )
                    _fus_sel[_fi["file"].name] = {
                        "checked":  _chk,
                        "role":     _role_sel,
                        "priority": _prio,
                    }

                _warn_roles = [
                    f["file"].name for f in _fus_files
                    if _fus_sel[f["file"].name]["checked"]
                    and _fus_sel[f["file"].name]["role"] not in _cs
                ]
                if _warn_roles:
                    st.caption(
                        f"⚠️ {len(_warn_roles)} masque(s) avec rôle absent de l'auto-material "
                        "→ utilisé tel quel sans blend."
                    )

                # ── Options ──────────────────────────────────────────────────
                st.markdown("---")
                _oc1, _oc2, _oc3 = st.columns(3)
                _fus_smooth = _oc1.slider(
                    "Douceur des bords (px)", 0, 20, 3, key="fusion2_smooth",
                    help="Flou gaussien aux bords des masques WB avant blend.",
                )
                _fus_bits = _oc2.radio(
                    "Format", ["8-bit", "16-bit"], index=1,
                    horizontal=True, key="fusion2_out_bits",
                )
                _fus_psz = _oc3.select_slider(
                    "Aperçu (px)", options=[512, 1024, 2048], value=1024,
                    key="fusion2_prev_sz",
                )

                # ── Génération ───────────────────────────────────────────────
                if st.button("🔀 Générer la fusion", key="btn_fusion2_gen"):
                    try:
                        from scipy.ndimage import gaussian_filter as _gauss
                        import shutil as _sh_fus
                        Image.MAX_IMAGE_PIXELS = None

                        # Résolution de travail = auto-material (petite)
                        _cs_h, _cs_w = next(iter(_cs.values())).shape
                        _WRK_H, _WRK_W = _cs_h, _cs_w

                        # Dimensions de sortie = masques WB originaux (grande)
                        _samp = Image.open(str(_fus_pngs[0]))
                        _EW, _EH = _samp.size
                        _samp.close()
                        _need_up = (_WRK_H, _WRK_W) != (_EH, _EW)

                        # Chargement WB à résolution de travail (évite OOM)
                        with st.spinner("Chargement des masques Workbench…"):
                            _wb_by_role = {}
                            for _fi in _fus_files:
                                _img_wb = Image.open(str(_fi["file"])).convert("L")
                                if (_img_wb.height, _img_wb.width) != (_WRK_H, _WRK_W):
                                    _img_wb = _img_wb.resize((_WRK_W, _WRK_H), Image.BILINEAR)
                                _a = np.array(_img_wb, dtype=np.float32) / 255.0
                                del _img_wb
                                _r = _fus_sel[_fi["file"].name]["role"]
                                _wb_by_role[_r] = np.maximum(
                                    _wb_by_role.get(_r, np.zeros((_WRK_H, _WRK_W), np.float32)), _a,
                                )
                                del _a

                        def _fus_auto(role):
                            if role not in _cs:
                                return np.zeros((_WRK_H, _WRK_W), np.float32)
                            return _cs[role].astype(np.float32)

                        _all_roles = sorted(set(list(_cs.keys()) + list(_wb_by_role.keys())))

                        with st.spinner(f"Fusion de {len(_all_roles)} rôles…"):
                            _fused = {}
                            for _role in _all_roles:
                                _auto = _fus_auto(_role)
                                _wb   = _wb_by_role.get(_role)
                                _fi_r = next(
                                    (_f for _f in _fus_files
                                     if _fus_sel[_f["file"].name]["role"] == _role), None
                                )
                                _sel  = _fus_sel.get(
                                    _fi_r["file"].name, {"checked": False}
                                ) if _fi_r else {"checked": False}

                                if _wb is None or not _sel["checked"]:
                                    _fused[_role] = _auto
                                else:
                                    _w  = _PRIO_W.get(_sel.get("priority", "Haute"), 1.0)
                                    _ws = (
                                        np.clip(
                                            _gauss(_wb.astype(np.float64), sigma=_fus_smooth),
                                            0.0, 1.0,
                                        ).astype(np.float32)
                                        if _fus_smooth > 0 else _wb
                                    )
                                    _fused[_role] = np.clip(_ws * _w + _auto * (1.0 - _w), 0.0, 1.0)

                            _tot = sum(_fused.values())
                            _tot_s = np.where(_tot > 1e-6, _tot, 1.0)
                            for _rl in _fused:
                                _fused[_rl] = (_fused[_rl] / _tot_s).astype(np.float32)
                            del _tot, _tot_s

                            # Remplissage des trous (pixels où aucune texture n'a de poids)
                            # → fallback sur l'auto-material qui couvre toujours 100%
                            _tot2 = sum(_fused.values())
                            _holes = _tot2 < 1e-4
                            if _holes.any():
                                for _rl in _fused:
                                    _fb = _fus_auto(_rl)
                                    _fused[_rl] = np.where(_holes, _fb, _fused[_rl])
                                    del _fb
                                # Re-normaliser après remplissage
                                _tot3 = sum(_fused.values())
                                _tot3_s = np.where(_tot3 > 1e-6, _tot3, 1.0)
                                for _rl in _fused:
                                    _fused[_rl] = (_fused[_rl] / _tot3_s).astype(np.float32)
                                del _tot3, _tot3_s
                            del _tot2, _holes

                        # Aperçu split view (à résolution de travail → rapide)
                        with st.spinner("Rendu aperçu…"):
                            _auto_only = {_rl: _fus_auto(_rl) for _rl in _all_roles}
                            _img_auto  = _fus_render(_auto_only, _fus_psz)
                            _img_fus   = _fus_render(_fused,     _fus_psz)
                            del _auto_only

                        # Sauvegarde — upsample à résolution WB un masque à la fois
                        with st.spinner("Sauvegarde…"):
                            _fus_out = Path(get_output_dir()) / f"fusion_{format_timestamp()}"
                            _fus_out.mkdir(parents=True, exist_ok=True)
                            _saved      = []
                            _roles_done = set()
                            _biome_cfg  = _fus_tr.get("biome_config", {})

                            def _save_fused(arr_wrk, fpath):
                                _a = (
                                    np.array(Image.fromarray(arr_wrk).resize(
                                        (_EW, _EH), Image.BILINEAR))
                                    if _need_up else arr_wrk
                                )
                                _o = (
                                    (_a * 65535).clip(0, 65535).astype(np.uint16)
                                    if _fus_bits == "16-bit"
                                    else (_a * 255).clip(0, 255).astype(np.uint8)
                                )
                                Image.fromarray(_o).save(str(fpath))
                                del _a, _o

                            for _fi in _fus_files:
                                _rl = _fus_sel[_fi["file"].name]["role"]
                                _fp = _fus_out / _fi["file"].name
                                _save_fused(
                                    _fused.get(_rl, np.zeros((_WRK_H, _WRK_W), np.float32)), _fp
                                )
                                _saved.append(_fp)
                                _roles_done.add(_rl)

                            for _rl in _all_roles:
                                if _rl in _roles_done:
                                    continue
                                _emat = _biome_cfg.get(_rl, _rl).replace(".emat", "")
                                _fp   = _fus_out / f"{_rl}_{_emat}_auto.png"
                                _save_fused(_fused[_rl], _fp)
                                _saved.append(_fp)

                            _proj_p = st.session_state.get("current_project_path")
                            _mdir   = None
                            if _proj_p:
                                _mdir = Path(_proj_p) / "masks" / "fusion"
                                _mdir.mkdir(parents=True, exist_ok=True)
                                for _sp in _saved:
                                    _sh_fus.copy2(str(_sp), str(_mdir / _sp.name))

                        # QTRE diagnostic — traitement masque par masque pour éviter OOM
                        with st.spinner("Diagnostic QTRE…"):
                            _THR = 1.0 / 65535 * 128
                            _sH, _sW = next(iter(_fused.values())).shape
                            _bpx = 32 if _sH <= 9000 else 127
                            _ny  = (_sH + _bpx - 1) // _bpx
                            _nx  = (_sW + _bpx - 1) // _bpx
                            _ph, _pw = _ny * _bpx - _sH, _nx * _bpx - _sW
                            # Réduire chaque masque à résolution bloc avant d'empiler
                            _bm_list = []
                            for _arr_q in _fused.values():
                                _p = np.pad(_arr_q, ((0, _ph), (0, _pw)))
                                _bm_list.append(
                                    _p.reshape(_ny, _bpx, _nx, _bpx).mean(axis=(1, 3))
                                )
                                del _p
                            _bm_stk = np.stack(_bm_list, axis=0)  # (n_roles, ny, nx) petit
                            _nviol  = int(((_bm_stk > _THR).sum(axis=0) > 4).sum())
                            del _bm_list, _bm_stk

                        st.session_state["fusion2_result"] = {
                            "dir":      str(_fus_out),
                            "proj_dir": str(_mdir) if _mdir else None,
                            "n_saved":  len(_saved),
                            "n_roles":  len(_all_roles),
                            "n_viol":   _nviol,
                            "img_auto": _img_auto,
                            "img_fus":  _img_fus,
                        }
                        st.success(
                            f"✓ {len(_saved)} masques ({len(_all_roles)} rôles)"
                            + (f" → `masks/fusion/`" if _mdir else "")
                        )

                    except Exception as _ex_fus:
                        st.error(f"Erreur : {_ex_fus}")
                        st.exception(_ex_fus)

                # ── Résultat ─────────────────────────────────────────────────
                if "fusion2_result" in st.session_state:
                    _fr = st.session_state["fusion2_result"]

                    st.markdown("#### Aperçu")
                    _vc1, _vc2 = st.columns(2)
                    _vc1.image(_fr["img_auto"], caption="Auto-material seul", use_container_width=True)
                    _vc2.image(_fr["img_fus"],  caption="Résultat fusionné",  use_container_width=True)

                    _qc1, _qc2, _qc3 = st.columns(3)
                    _qc1.metric("Rôles fusionnés",  _fr["n_roles"])
                    _qc2.metric("Fichiers exportés", _fr["n_saved"])
                    _qc3.metric(
                        "Violations QTRE", _fr["n_viol"],
                        delta="OK" if _fr["n_viol"] == 0 else f"{_fr['n_viol']} blocs",
                        delta_color="normal" if _fr["n_viol"] == 0 else "inverse",
                    )
                    if _fr["n_viol"] == 0:
                        st.success("✅ QTRE validé — masques prêts pour l'import Workbench.")
                    else:
                        st.warning(
                            f"⚠️ {_fr['n_viol']} blocs dépassent 4 textures. "
                            "Passez certains masques en Basse priorité ou décochez-les."
                        )

                    _fz = _io_fus.BytesIO()
                    with _zp_fus.ZipFile(_fz, "w", _zp_fus.ZIP_DEFLATED) as _zff:
                        for _fp3 in sorted(Path(_fr["dir"]).glob("*.png")):
                            _zff.write(str(_fp3), _fp3.name)
                    _fz.seek(0)
                    st.download_button(
                        "⬇️ Télécharger tous les masques fusionnés (.zip)",
                        _fz.getvalue(),
                        file_name=f"fusion_masks_{format_timestamp()}.zip",
                        mime="application/zip",
                        key="dl_fusion2_zip",
                        use_container_width=True,
                    )

# ── Auto-sauvegarde ───────────────────────────────────────────────────────────
if st.session_state.get("current_project_path") and st.session_state.get("current_project"):
    try:
        save_project()
    except Exception:
        pass

# ============================================================================
# FOOTER
# ============================================================================

st.divider()
st.markdown("""
<div style="text-align: center; color: gray; font-size: 0.9em;">
    <p>Map Generator Pro v3.0 — Architecture DDD — BaseMap Heightmap Loader</p>
    <p>© 2026 | Production-Ready</p>
</div>
""", unsafe_allow_html=True)
