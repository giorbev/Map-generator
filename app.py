# -*- coding: utf-8 -*-
"""
Map Generator Pro v5.1 — Streamlit Application
Interface complète de génération de cartes topographiques
"""

import streamlit as st
import numpy as np
import cv2
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
import pipeline_validation as pv

# ============================================================================
# CONFIGURATION STREAMLIT
# ============================================================================

st.set_page_config(
    page_title="Map Generator Pro v5.1",
    page_icon="",
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
# COULEURS TEXTURES — Vanilla + ZI Zimnitrita
# ============================================================================


# ============================================================================
# GESTION DE PROJETS
# ============================================================================

PROJECTS_DIR = Path("data/projects")
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_VERSION = "1.1"

CONFIG_FILE = Path(__file__).parent / "config.json"

def normalize_path(path_str: str) -> str:
    """Nettoie un chemin collé depuis l'explorateur Windows.
    Retire guillemets, espaces, et corrige les séparateurs."""
    if not path_str:
        return ""
    # Retirer guillemets simples et doubles en début/fin
    cleaned = path_str.strip().strip('"').strip("'").strip()
    # Auto-corriger : si dossier pointant vers catalog.json
    p = Path(cleaned)
    if p.is_dir() and (p / "catalog.json").exists():
        cleaned = str(p / "catalog.json")
    return cleaned

def save_config():
    """Sauvegarde les paramètres globaux (persistants entre sessions)"""
    config = {
        "addon_path":          st.session_state.get("terr_project_path", ""),
        "catalog_path":        st.session_state.get("catalog_path_global", ""),
        "gaea_slope_path":     st.session_state.get("gaea_slope_path", ""),
        "gaea_flow_path":      st.session_state.get("gaea_flow_path", ""),
        "gaea_deposit_path":   st.session_state.get("gaea_deposit_path", ""),
        "gaea_exclusion_path": st.session_state.get("gaea_exclusion_path", ""),
        "gaea_output_dir":     st.session_state.get("gaea_output_dir", ""),
    }
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Erreur save_config: {e}")

def load_config() -> dict:
    """Charge les paramètres globaux au démarrage"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}

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
    for sub in [
        "sources",
        "sources/reforger",
        "sources/reforger/export_masks",
        "generated",
        "generated/previews",
        "generated/terrain_masks",
        "pipeline_temp",
        "reports",
        "snapshots",
    ]:
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
    # Support ancien format (assets) ET nouveau (sources)
    hm_rel = data.get("sources", {}).get("heightmap")
    if not hm_rel:
        # Fallback ancien format
        hm_rel = data.get("assets", {}).get("heightmap", {}).get("filename", "")

    if hm_rel:
        # Normaliser : toujours chercher dans sources/
        if not hm_rel.startswith("sources/") and not hm_rel.startswith("sources\\"):
            hm_rel = f"sources/{hm_rel}"
        hm_path = p / hm_rel
    else:
        hm_path = None
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

            # Calculer toutes les données terrain (centralisé)
            if 'terrain_data' not in st.session_state or st.session_state.get('terrain_data_path') != str(hm_path):
                # Essayer de charger depuis cache d'abord
                terrain_data = load_terrain_data_cache(p, str(hm_path))

                if terrain_data:
                    # Cache valide → chargement instantané
                    st.session_state['terrain_data'] = terrain_data
                    st.session_state['terrain_data_path'] = str(hm_path)
                    st.session_state['_terrain_from_cache'] = True

                    # Message de confirmation
                    cache_size = (p / "cache" / "terrain_data.npz").stat().st_size / 1024 / 1024
                    st.session_state['_load_message'] = (
                        f"⚡ Projet chargé : heightmap + terrain_data depuis cache "
                        f"({cache_size:.1f} MB)"
                    )
                else:
                    # Pas de cache → calcul complet
                    try:
                        from terrain_analysis import compute_terrain_data

                        # Callback pour stocker progression
                        def store_progress(step, pct):
                            st.session_state['_terrain_progress'] = (step, pct)

                        # Calcul avec progress callback
                        terrain_data = compute_terrain_data(str(hm_path), progress_callback=store_progress)
                        st.session_state['terrain_data'] = terrain_data
                        st.session_state['terrain_data_path'] = str(hm_path)
                        st.session_state['_terrain_just_computed'] = True
                        st.session_state.pop('_terrain_progress', None)

                        # Sauvegarder en cache pour prochaine fois
                        save_terrain_data_cache(terrain_data, p)

                        # Message de confirmation
                        st.session_state['_load_message'] = (
                            f"✅ Projet chargé : heightmap + terrain_data calculés "
                            f"en {terrain_data['computation_time']:.1f}s"
                        )

                    except Exception as e_terrain:
                        # Erreur lors du calcul terrain_data
                        st.session_state['terrain_data'] = None
                        st.session_state['_terrain_error'] = str(e_terrain)
                        import traceback
                        st.session_state['_terrain_error_trace'] = traceback.format_exc()

        except Exception as e:
            st.session_state.base_map = None
            st.session_state.terrain_data = None
            st.session_state['_load_error'] = str(e)
    else:
        st.session_state.heightmap_path = None
        st.session_state.base_map = None

    # Satmap
    sat_rel = data.get("sources", {}).get("satmap") or data.get("assets", {}).get("satmap", {}).get("filename", "")
    if sat_rel:
        sat_path = p / sat_rel if not Path(sat_rel).is_absolute() else Path(sat_rel)
        st.session_state.satmap_path = str(sat_path) if sat_path.exists() else None
    else:
        st.session_state.satmap_path = None

    # IT masks directory
    it_dir_rel = data.get("sources", {}).get("it_masks_dir")
    if it_dir_rel:
        it_dir = p / it_dir_rel if not Path(it_dir_rel).is_absolute() else Path(it_dir_rel)
        st.session_state.it_masks_dir = str(it_dir) if it_dir.exists() else None
    else:
        st.session_state.it_masks_dir = None

    # Masques Instant Terra (curvature, sediment)
    _it_cfg = data.get("assets", {}).get("it_masks", {})
    # Mise à jour différée : on ne peut pas modifier les clés de widget après leur instanciation.
    # On écrit dans _pending_widget_it_* ; le haut du script les transfère avant la création des widgets.
    for _role in ("curvature", "sediment"):
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

        # ── Migration ancien format -> nouveau ────────────────────────────────
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

    # ── Pipeline V2 ────────────────────────────────────────────────────────
    pipeline_v2 = data.get("pipeline_v2", {})

    # Paramètres sliders
    params = pipeline_v2.get("params", {})
    st.session_state.pipeline_v2_coastal_distance = params.get("coastal_distance_max_m", 60.0)
    st.session_state.pipeline_v2_debris_min = params.get("debris_min_deg", 18.0)
    st.session_state.pipeline_v2_rock_min = params.get("rock_min_deg", 28.0)
    st.session_state.pipeline_v2_feather_coastal = params.get("feather_coastal_m", 20.0)
    st.session_state.pipeline_v2_feather_grass = params.get("feather_grass_m", 20.0)
    st.session_state.pipeline_v2_feather_rock = params.get("feather_rock_m", 20.0)
    st.session_state.pipeline_v2_debris_gradient = params.get("debris_gradient_distance_m", 100.0)
    st.session_state.pipeline_v2_dirt_slope_min = params.get("dirt_slope_min_deg", 5.0)
    st.session_state.pipeline_v2_feather_dirt = params.get("feather_dirt_m", 20.0)
    st.session_state.pipeline_v2_flow_mud_pct = params.get("flow_mud_percentile", 85)
    st.session_state.pipeline_v2_tpi_mud_pct = params.get("tpi_mud_percentile", 40)
    st.session_state.pipeline_v2_feather_mud = params.get("feather_mud_m", 15.0)
    st.session_state.pipeline_v2_tpi_local = params.get("tpi_local_radius_m", 100.0)
    st.session_state.pipeline_v2_tpi_macro = params.get("tpi_macro_radius_m", 500.0)

    # Paramètres auto-calibrés
    params_auto = pipeline_v2.get("params_auto", {})
    if params_auto:
        st.session_state.params_auto_v2 = params_auto

    # Dossier output
    output_dir_rel = pipeline_v2.get("output_dir")
    if output_dir_rel:
        output_abs = p / output_dir_rel if not Path(output_dir_rel).is_absolute() else Path(output_dir_rel)
        if output_abs.exists():
            st.session_state.pipeline_v2_masks_dir = str(output_abs)
            st.session_state.masks_dir_v2 = str(output_abs)  # Alias pour TAB 3


    # ── Post-Processing ────────────────────────────────────────────────────
    post_proc = data.get("post_processing", {})

    st.session_state.urban_radius = post_proc.get("urban_radius_m", 0.0)
    st.session_state.conflict_threshold_post = post_proc.get("conflict_threshold", 0.05)

    if post_proc.get("categories"):
        st.session_state.post_categories = post_proc["categories"]

    pipeline_dir_rel = post_proc.get("pipeline_dir")
    if pipeline_dir_rel:
        pipeline_abs = p / pipeline_dir_rel if not Path(pipeline_dir_rel).is_absolute() else Path(pipeline_dir_rel)
        if pipeline_abs.exists():
            st.session_state.post_pipeline_dir = str(pipeline_abs)

    fusion_dir_rel = post_proc.get("output_dir")
    if fusion_dir_rel:
        fusion_abs = p / fusion_dir_rel if not Path(fusion_dir_rel).is_absolute() else Path(fusion_dir_rel)
        if fusion_abs.exists():
            st.session_state.post_final_masks_dir = str(fusion_abs)

    # ── Validation ─────────────────────────────────────────────────────────
    validation = data.get("validation", {})
    st.session_state.validation_conflict_threshold = validation.get("conflict_threshold", 0.15)

    corrected_dir_rel = validation.get("masks_corrected_dir")
    if corrected_dir_rel:
        corrected_abs = p / corrected_dir_rel if not Path(corrected_dir_rel).is_absolute() else Path(corrected_dir_rel)
        if corrected_abs.exists():
            st.session_state.val_corrected_dir = str(corrected_abs)

    # Projet .terr
    st.session_state.terr_project_path = data.get("terr_project_path", "")
    # Delete the widget key so it re-reads value= on the next rerun.
    # Setting it directly raises StreamlitAPIException if the widget is already rendered.
    if "terr_project_input" in st.session_state:
        del st.session_state["terr_project_input"]
    st.session_state.terr_materials = []

    # Chemin .terr du monde (pour export masques / satmap)
    st.session_state.world_terrain_path = data.get("world_terrain_path", "")

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
        ("veg_min_score",   "min_score",   0.05),
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


def save_project():
    """Sauvegarde l'état courant dans project.json."""
    if not st.session_state.get("current_project_path"):
        return  # Pas de projet chargé

    p = Path(st.session_state.current_project_path)
    data = st.session_state.current_project.copy()

    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    data["last_modified"] = datetime.now().strftime("%Y-%m-%d")

    # Lire depuis la clé widget en priorité
    data["terr_project_path"] = st.session_state.get(
        "terr_project_input", st.session_state.get("terr_project_path", "")
    )

    # Chemin .terr du monde (export masques / satmap)
    data["world_terrain_path"] = st.session_state.get("world_terrain_path", "")

    # ── SOURCES ─────────────────────────────────────────────────────────────
    data.setdefault("sources", {})

    # Heightmap
    bm = st.session_state.get("base_map")
    if bm:
        hm_path = Path(st.session_state.heightmap_path)
        dest = p / "sources" / hm_path.name
        if not dest.exists():
            import shutil
            (p / "sources").mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(hm_path), str(dest))

        # Chemin relatif
        try:
            rel_hm = hm_path.relative_to(p)
            data["sources"]["heightmap"] = str(rel_hm).replace("\\", "/")
        except ValueError:
            data["sources"]["heightmap"] = str(hm_path).replace("\\", "/")

        # Métadonnées heightmap (legacy support)
        data.setdefault("assets", {})
        data["assets"]["heightmap"] = {
            "filename": hm_path.name,
            "format": hm_path.suffix.lstrip("."),
            "cellsize": float(getattr(bm, "cellsize", 1.0)),
            "width": int(bm.width),
            "height": int(bm.height),
            "alt_min": float(bm.altitude_min),
            "alt_max": float(bm.altitude_max),
        }

        # Stocker cellsize dans session_state si pas déjà fait
        st.session_state.setdefault("cellsize", float(getattr(bm, "cellsize", 1.0)))

    # Satmap
    satmap_path = st.session_state.get("satmap_path")
    if satmap_path:
        try:
            rel_sat = Path(satmap_path).relative_to(p)
            data["sources"]["satmap"] = str(rel_sat).replace("\\", "/")
        except ValueError:
            data["sources"]["satmap"] = str(satmap_path).replace("\\", "/")

    # IT masks directory
    it_masks_dir = st.session_state.get("it_masks_dir")
    if it_masks_dir:
        try:
            rel_it = Path(it_masks_dir).relative_to(p)
            data["sources"]["it_masks_dir"] = str(rel_it).replace("\\", "/")
        except ValueError:
            data["sources"]["it_masks_dir"] = str(it_masks_dir).replace("\\", "/")

    # Masques IT individuels (legacy support)
    _it_paths = {}
    for _role in ("curvature", "sediment"):
        _path_str = st.session_state.get(f"it_path_{_role}", "").strip()
        if _path_str:
            _abs_it = Path(_path_str)
            try:
                _rel_it = _abs_it.relative_to(p)
                _it_paths[_role] = str(_rel_it).replace("\\", "/")
            except ValueError:
                _it_paths[_role] = str(_abs_it).replace("\\", "/")
    if _it_paths:
        data["assets"]["it_masks"] = _it_paths

    # ── REFORGER ────────────────────────────────────────────────────────────
    data.setdefault("reforger", {})

    if st.session_state.get("reforger_data"):
        data["reforger"]["grid_data"] = st.session_state.reforger_data
        # Legacy support
        data["reforger_grid"] = st.session_state.reforger_data

    if st.session_state.get("terr_project_path"):
        data["reforger"]["project_path"] = st.session_state.terr_project_path

    # ── PIPELINE V2 ─────────────────────────────────────────────────────────
    data.setdefault("pipeline_v2", {})

    # Paramètres sliders (récupérés depuis session_state)
    pipeline_params = {
        "coastal_distance_max_m": st.session_state.get("pipeline_v2_coastal_distance", 60.0),
        "debris_min_deg": st.session_state.get("pipeline_v2_debris_min", 18.0),
        "rock_min_deg": st.session_state.get("pipeline_v2_rock_min", 28.0),
        "feather_coastal_m": st.session_state.get("pipeline_v2_feather_coastal", 20.0),
        "feather_grass_m": st.session_state.get("pipeline_v2_feather_grass", 20.0),
        "feather_rock_m": st.session_state.get("pipeline_v2_feather_rock", 20.0),
        "debris_gradient_distance_m": st.session_state.get("pipeline_v2_debris_gradient", 100.0),
        "dirt_slope_min_deg": st.session_state.get("pipeline_v2_dirt_slope_min", 5.0),
        "feather_dirt_m": st.session_state.get("pipeline_v2_feather_dirt", 20.0),
        "flow_mud_percentile": st.session_state.get("pipeline_v2_flow_mud_pct", 85),
        "tpi_mud_percentile": st.session_state.get("pipeline_v2_tpi_mud_pct", 40),
        "feather_mud_m": st.session_state.get("pipeline_v2_feather_mud", 15.0),
        "tpi_local_radius_m": st.session_state.get("pipeline_v2_tpi_local", 100.0),
        "tpi_macro_radius_m": st.session_state.get("pipeline_v2_tpi_macro", 500.0),
    }
    data["pipeline_v2"]["params"] = pipeline_params

    # Paramètres auto-calibrés
    if "params_auto_v2" in st.session_state and st.session_state.params_auto_v2:
        data["pipeline_v2"]["params_auto"] = {
            "coastal_alt_max_m": st.session_state.params_auto_v2.get("coastal_alt_max_m"),
            "grass_low_max_m": st.session_state.params_auto_v2.get("grass_low_max_m"),
            "grass_mid_max_m": st.session_state.params_auto_v2.get("grass_mid_max_m"),
            "grass_high_max_m": st.session_state.params_auto_v2.get("grass_high_max_m"),
            "debris_min_deg": st.session_state.params_auto_v2.get("debris_min_deg"),
            "rock_min_deg": st.session_state.params_auto_v2.get("rock_min_deg"),
        }

    # Résultats dernière génération
    if "pipeline_v2_results" in st.session_state:
        results = st.session_state.pipeline_v2_results
        data["pipeline_v2"]["base_texture"] = results.get("base_texture")
        data["pipeline_v2"]["qtre_verdict"] = results.get("qtre_verdict")
        data["pipeline_v2"]["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Dossier output
    if "pipeline_v2_masks_dir" in st.session_state:
        try:
            rel_out = Path(st.session_state.pipeline_v2_masks_dir).relative_to(p)
            data["pipeline_v2"]["output_dir"] = str(rel_out).replace("\\", "/")
        except ValueError:
            data["pipeline_v2"]["output_dir"] = str(st.session_state.pipeline_v2_masks_dir).replace("\\", "/")


    # ── POST-PROCESSING ─────────────────────────────────────────────────────
    data.setdefault("post_processing", {})

    # Paramètres sliders post-processing
    data["post_processing"]["urban_radius_m"] = st.session_state.get("urban_radius", 0.0)
    data["post_processing"]["conflict_threshold"] = st.session_state.get("conflict_threshold_post", 0.05)

    # Catégories mappeur (déjà sauvegardé ailleurs mais centralisé ici)
    if "post_categories" in st.session_state:
        data["post_processing"]["categories"] = st.session_state.post_categories

    # Dossier masks pipeline sélectionné
    if "post_pipeline_dir" in st.session_state:
        try:
            rel_pp = Path(st.session_state.post_pipeline_dir).relative_to(p)
            data["post_processing"]["pipeline_dir"] = str(rel_pp).replace("\\", "/")
        except ValueError:
            data["post_processing"]["pipeline_dir"] = str(st.session_state.post_pipeline_dir).replace("\\", "/")

    # Dossier output fusion
    if "post_final_masks_dir" in st.session_state:
        try:
            rel_fusion = Path(st.session_state.post_final_masks_dir).relative_to(p)
            data["post_processing"]["output_dir"] = str(rel_fusion).replace("\\", "/")
        except ValueError:
            data["post_processing"]["output_dir"] = str(st.session_state.post_final_masks_dir).replace("\\", "/")

    # ── VALIDATION ──────────────────────────────────────────────────────────
    data.setdefault("validation", {})

    data["validation"]["conflict_threshold"] = st.session_state.get("validation_conflict_threshold", 0.15)
    data["validation"]["meters_per_pixel"] = st.session_state.get("cellsize", 1.0)

    if "val_corrected_dir" in st.session_state:
        try:
            rel_corr = Path(st.session_state.val_corrected_dir).relative_to(p)
            data["validation"]["masks_corrected_dir"] = str(rel_corr).replace("\\", "/")
        except ValueError:
            data["validation"]["masks_corrected_dir"] = str(st.session_state.val_corrected_dir).replace("\\", "/")

    # ── MODULES (legacy) ────────────────────────────────────────────────────
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
        "min_score":   st.session_state.get("veg_min_score",   0.05),
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

    # ── SAUVEGARDE ──────────────────────────────────────────────────────────
    st.session_state.current_project = data
    (p / "project.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def auto_save():
    """
    Sauvegarde automatique du projet si chargé.
    À appeler après chaque modification importante dans l'UI.
    """
    if st.session_state.get("current_project_path"):
        try:
            save_project()
        except Exception as e:
            # Silencieux pour éviter d'interrompre l'UI
            pass


# ============================================================================
# SESSION STATE MANAGEMENT
# ============================================================================

def save_terrain_data_cache(terrain_data, project_path):
    """Sauvegarde terrain_data en cache NPZ."""
    try:
        cache_dir = Path(project_path) / "cache"
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / "terrain_data.npz"

        # Extraire arrays numpy
        np.savez_compressed(
            cache_file,
            heightmap=terrain_data['heightmap'],
            heightmap_smooth=terrain_data['heightmap_smooth'],
            slope=terrain_data['slope'],
            curvature=terrain_data['curvature'],
            curvature_plan=terrain_data.get('curvature_plan', terrain_data['curvature']),
            curvature_profile=terrain_data.get('curvature_profile', np.zeros_like(terrain_data['curvature'])),
            tpi_local=terrain_data['tpi_local'],
            tpi_macro=terrain_data['tpi_macro'],
            flow=terrain_data['flow'],
            distance_cote=terrain_data['distance_cote'],
            aspect=terrain_data['aspect'],
            roughness=terrain_data['roughness'],
            # Métadonnées en pickle séparé
        )

        # Sauvegarder métadonnées JSON (avec version pipeline)
        import json
        meta_file = cache_dir / "terrain_meta.json"
        meta_file.write_text(json.dumps({
            'meta': terrain_data['meta'],
            'cellsize': terrain_data['cellsize'],
            'params': terrain_data['params'],
            'computation_time': terrain_data['computation_time'],
            'timestamp': terrain_data['timestamp'],
            'heightmap_path': terrain_data['heightmap_path'],
            'pipeline_version': terrain_data.get('pipeline_version', '1.0.0')  # Inclure version
        }, indent=2), encoding='utf-8')

        return True
    except Exception as e:
        return False


def load_terrain_data_cache(project_path, heightmap_path):
    """Charge terrain_data depuis cache NPZ si valide."""
    try:
        from terrain_analysis import TERRAIN_PIPELINE_VERSION

        cache_dir = Path(project_path) / "cache"
        cache_file = cache_dir / "terrain_data.npz"
        meta_file = cache_dir / "terrain_meta.json"

        if not cache_file.exists() or not meta_file.exists():
            return None

        # Vérifier que cache plus récent que heightmap
        hm_mtime = Path(heightmap_path).stat().st_mtime
        cache_mtime = cache_file.stat().st_mtime

        if cache_mtime < hm_mtime:
            # Heightmap modifiée depuis cache → invalide
            return None

        # Charger métadonnées pour vérifier version
        import json
        meta_data = json.loads(meta_file.read_text(encoding='utf-8'))

        # VALIDATION VERSION PIPELINE
        cached_version = meta_data.get('pipeline_version', '1.0.0')
        if cached_version != TERRAIN_PIPELINE_VERSION:
            # Version pipeline changée → invalider cache
            # Supprimer cache obsolète
            cache_file.unlink(missing_ok=True)
            meta_file.unlink(missing_ok=True)
            return None

        # Charger arrays
        npz = np.load(cache_file)

        # Reconstruire terrain_data
        terrain_data = {
            'heightmap': npz['heightmap'],
            'heightmap_smooth': npz['heightmap_smooth'],
            'slope': npz['slope'],
            'curvature': npz['curvature'],
            'curvature_plan': npz.get('curvature_plan', npz['curvature']),  # Fallback cache ancien
            'curvature_profile': npz.get('curvature_profile', np.zeros_like(npz['curvature'])),
            'tpi_local': npz['tpi_local'],
            'tpi_macro': npz['tpi_macro'],
            'flow': npz['flow'],
            'distance_cote': npz['distance_cote'],
            'aspect': npz['aspect'],
            'roughness': npz['roughness'],
            **meta_data
        }

        return terrain_data

    except Exception as e:
        return None


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

    # Charger config globale au premier run uniquement
    if "config_loaded" not in st.session_state:
        config = load_config()
        st.session_state.terr_project_path    = config.get("addon_path", "")
        st.session_state.catalog_path_global  = config.get("catalog_path", "")
        st.session_state.gaea_slope_path      = config.get("gaea_slope_path", "")
        st.session_state.gaea_flow_path       = config.get("gaea_flow_path", "")
        st.session_state.gaea_deposit_path    = config.get("gaea_deposit_path", "")
        st.session_state.gaea_exclusion_path  = config.get("gaea_exclusion_path", "")
        st.session_state.gaea_output_dir      = config.get("gaea_output_dir", "")
        st.session_state.config_loaded        = True

initialize_session()

# Vérifier que le projet courant existe vraiment
if st.session_state.current_project_path:
    from pathlib import Path
    project_path = Path(st.session_state.current_project_path)
    if not project_path.exists() or not (project_path / "project.json").exists():
        # Projet invalide ou supprimé — réinitialiser
        st.session_state.current_project_path = None
        st.session_state.current_project = None
        st.session_state.heightmap_path = None
        st.session_state.base_map = None
        st.session_state.terrain_data = None

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
    """Retourne le dossier generated du projet courant, ou 'generated/' local si aucun projet chargé."""
    proj = st.session_state.get("current_project_path")
    output_dir = str(Path(proj) / "generated") if proj else "generated"
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

def load_image(path):
    """Charge une image en mémoire complète (force le chargement des pixels)."""
    try:
        img = Image.open(path)
        img.load()   # force full decode — évite les problèmes de file handle fermé
        return img
    except Exception as e:
        st.error(f"[ERR] Erreur chargement image: {e}")
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
    - Materials: union vanilla + custom ; même stem -> custom remplace vanilla
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
    st.sidebar.markdown(f"###  {proj_info['name']}")
    st.sidebar.caption(proj_info.get("description", ""))
    col_save, col_close = st.sidebar.columns(2)
    if col_save.button(" Sauvegarder", use_container_width=True):
        save_project()
        st.sidebar.success("Sauvegardé")
    if col_close.button("✖ Fermer", use_container_width=True):
        st.session_state.current_project_path = None
        st.session_state.current_project      = None
        st.session_state.heightmap_path       = None
        st.session_state.base_map             = None
        st.session_state.reforger_data        = None
        st.session_state.terr_materials       = []
        st.session_state.terrain_data         = None
        st.rerun()

    # Afficher statut terrain_data
    terrain_data = st.session_state.get('terrain_data')
    terrain_error = st.session_state.get('_terrain_error')

    if terrain_data:
        # Message de succès si vient d'être calculé
        if st.session_state.get('_terrain_just_computed'):
            st.sidebar.success(
                f"✓ Terrain analysé : {terrain_data['meta']['ncols']}×{terrain_data['meta']['nrows']} px | "
                f"{terrain_data['cellsize']} m/px | {terrain_data['computation_time']:.1f}s"
            )
            st.session_state['_terrain_just_computed'] = False
        elif st.session_state.get('_terrain_from_cache'):
            # Chargé depuis cache
            st.sidebar.success(
                f"⚡ Terrain chargé (cache) : {terrain_data['cellsize']} m/px | "
                f"Calcul initial : {terrain_data['computation_time']:.1f}s"
            )
            st.session_state['_terrain_from_cache'] = False
        else:
            # Affichage compact sinon
            st.sidebar.info(
                f"📊 Terrain : {terrain_data['cellsize']} m/px | "
                f"{terrain_data['computation_time']:.1f}s"
            )
    elif terrain_error:
        # Erreur lors du calcul
        st.sidebar.error(f"❌ Erreur calcul terrain : {terrain_error}")
        with st.sidebar.expander("🔍 Détails erreur"):
            st.code(st.session_state.get('_terrain_error_trace', 'Pas de trace disponible'))
            if st.button("🔄 Réessayer", key="retry_terrain"):
                # Nettoyer erreur et forcer recalcul
                st.session_state.pop('_terrain_error', None)
                st.session_state.pop('_terrain_error_trace', None)
                st.session_state.pop('terrain_data', None)
                st.session_state.pop('terrain_data_path', None)
                st.rerun()
    elif st.session_state.get('heightmap_path') and not st.session_state.get('_terrain_progress'):
        # Heightmap chargée mais terrain_data absent (et pas en cours de calcul)
        st.sidebar.warning("⚠️ Terrain non analysé — rechargez la heightmap")

    st.sidebar.divider()

    # ── DIAGNOSTIC PROJET ────────────────────────────────────────────────
    with st.sidebar.expander("🔍 État du projet", expanded=False):
        st.markdown("**Diagnostic chargement**")

        # Heightmap
        hm_path = st.session_state.get('heightmap_path')
        if hm_path and Path(hm_path).exists():
            st.success(f"✓ Heightmap : {Path(hm_path).name}")
        elif hm_path:
            st.error(f"✗ Heightmap manquante : {hm_path}")
        else:
            st.warning("⚠ Heightmap non définie")

        # BaseMap
        base_map = st.session_state.get('base_map')
        if base_map:
            st.success(f"✓ BaseMap : {base_map.width}×{base_map.height}px")
        else:
            st.warning("⚠ BaseMap non chargée")

        # Terrain Data
        terrain_data = st.session_state.get('terrain_data')
        if terrain_data:
            st.success(f"✓ Terrain Data : {terrain_data['cellsize']} m/px")
        else:
            st.warning("⚠ Terrain Data absent")

        # Cache
        if st.session_state.current_project_path:
            cache_file = Path(st.session_state.current_project_path) / "cache" / "terrain_data.npz"
            if cache_file.exists():
                st.info(f"💾 Cache : {cache_file.stat().st_size / 1024 / 1024:.1f} MB")
            else:
                st.caption("Pas de cache terrain")

else:
    # Aucun projet ouvert — afficher guide
    st.sidebar.info("ℹ️ **Aucun projet ouvert**  \nCréez ou ouvrez un projet ci-dessous ⬇️")
    st.sidebar.divider()

st.sidebar.markdown("## 📂 **Chargement & Export**")
st.sidebar.divider()

# Section Chargement Heightmap
st.sidebar.markdown("###  Heightmap")
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

    st.sidebar.success(f"[OK] Heightmap chargée: {uploaded_heightmap.name}")
    st.sidebar.metric("Taille", f"{get_file_size_mb(temp_heightmap):.2f} MB")

    # Charger ou mettre à jour BaseMap
    try:
        with st.spinner("Analyse heightmap..."):
            bm = BaseMap(temp_heightmap)
            st.session_state.base_map = bm

        st.sidebar.success("[OK] BaseMap créée")
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

        # Calculer TOUTES les données terrain (centralisé)
        if 'terrain_data' not in st.session_state or st.session_state.get('terrain_data_path') != temp_heightmap:
            with st.spinner("Calcul des dérivés terrain (slope, curvature, TPI, flow, aspect...)"):
                from terrain_analysis import compute_terrain_data

                # Progress bar
                progress_bar = st.sidebar.progress(0)
                progress_text = st.sidebar.empty()

                def update_progress(step, pct):
                    progress_bar.progress(pct)
                    progress_text.caption(f"⏳ {step}...")

                terrain_data = compute_terrain_data(
                    temp_heightmap,
                    progress_callback=update_progress
                )

                st.session_state['terrain_data'] = terrain_data
                st.session_state['terrain_data_path'] = temp_heightmap

                progress_bar.empty()
                progress_text.empty()

                st.sidebar.success(
                    f"[OK] Terrain analysé en {terrain_data['computation_time']:.1f}s  \n"
                    f"Résolution : {terrain_data['cellsize']} m/px"
                )

                # ✅ SAUVEGARDER LE CACHE pour ne jamais recalculer !
                if st.session_state.current_project_path:
                    cache_ok = save_terrain_data_cache(
                        terrain_data,
                        st.session_state.current_project_path
                    )
                    if cache_ok:
                        cache_file = Path(st.session_state.current_project_path) / "cache" / "terrain_data.npz"
                        cache_size = cache_file.stat().st_size / 1024 / 1024
                        st.sidebar.info(f"💾 Cache sauvegardé : {cache_size:.1f} MB")

        # Mise à jour du projet courant si ouvert
        if st.session_state.current_project_path:
            save_project()

    except Exception as e:
        st.sidebar.error(f"[ERR] Erreur: {e}")
        import traceback
        st.sidebar.code(traceback.format_exc())

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
    st.sidebar.success(f"[OK] SatMap chargée: {uploaded_satmap.name}")

# ── Section Projet Reforger (.terr) ──────────────────────────────────────────
st.sidebar.markdown("###  Projet Reforger")

terr_path_input = st.sidebar.text_input(
    "Chemin dossier addon",
    value=st.session_state.terr_project_path,
    placeholder=r"I:\Reforger_addons travail\ZBK_repo",
    key="terr_project_input",
)

terr_path_clean = normalize_path(terr_path_input)
if terr_path_clean != st.session_state.terr_project_path or "resolved_paths" not in st.session_state:
    st.session_state.terr_project_path = terr_path_clean
    st.session_state.terr_materials = []
    if terr_path_clean and Path(terr_path_clean).exists():
        from app_config import resolve_paths
        rp = resolve_paths(terr_path_clean)
        st.session_state.resolved_paths = rp
    else:
        st.session_state.resolved_paths = {"valid": False}
    if st.session_state.current_project_path:
        save_project()
    save_config()

# Champ catalog path
catalog_input = st.sidebar.text_input(
    "Chemin catalog.json",
    value=st.session_state.get("catalog_path_global", ""),
    placeholder=r"H:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json",
    key="catalog_path_global_input"
)
catalog_input_clean = normalize_path(catalog_input)
if catalog_input_clean != st.session_state.get("catalog_path_global", ""):
    st.session_state.catalog_path_global = catalog_input_clean
    save_config()
    st.rerun()

# Validation visuelle
if catalog_input_clean and Path(catalog_input_clean).exists():
    st.sidebar.caption("✅ catalog.json trouvé")
elif catalog_input_clean:
    st.sidebar.error("❌ catalog.json introuvable")

rp = st.session_state.get("resolved_paths", {})
if rp.get("valid"):
    # Afficher infos du monde
    st.sidebar.success(f"✅ {rp['world_name']} ({rp['grid_size']}×{rp['grid_size']} tuiles)")

    # Charger matériaux depuis terr_file
    if rp.get("terr_file") and not st.session_state.terr_materials:
        from reforger_texture_budget import parse_terr_materials as _parse_terr
        st.session_state.terr_materials = _parse_terr(rp["terr_file"])

    if st.session_state.terr_materials:
        st.sidebar.caption(f"📋 {len(st.session_state.terr_materials)} matériaux chargés")
        with st.sidebar.expander("Matériaux disponibles"):
            for i, m in enumerate(st.session_state.terr_materials):
                st.caption(f"[{i:2d}] {m}")
elif terr_path_input:
    error_msg = rp.get("error", "Dossier introuvable")
    st.sidebar.error(f"❌ {error_msg}")

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
                with open(f"{output_dir}/heightmap_export_{timestamp}_16bit_metadata.json", "w", encoding="utf-8") as f:
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
                with open(f"{output_dir}/heightmap_export_{timestamp}_16bit_raw_metadata.json", "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)

            # ASC export — TODO: implémenter selon format ASC

            st.sidebar.success(f"[OK] Exporté: {Path(output_path).name}")
        except Exception as e:
            st.sidebar.error(f"[ERR] Erreur export: {e}")


# ============================================================================
# MAIN CONTENT — ONGLETS
# ============================================================================

st.markdown('<h1 class="main-header"> Map Generator Pro v5.1</h1>', unsafe_allow_html=True)

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
                    # Vérifier si heightmap existe
                    hm_exists = False
                    if proj["heightmap"]:
                        hm_path = Path(proj["path"]) / "sources" / proj["heightmap"]
                        hm_exists = hm_path.exists()

                    # Icône d'état
                    status_icon = "✅" if hm_exists else "⚠️"
                    st.markdown(f"{status_icon} **{proj['name']}**")

                    if proj["description"]:
                        st.caption(proj["description"])
                    if proj["heightmap"]:
                        if hm_exists:
                            st.caption(f"Heightmap : {proj['heightmap']}")
                        else:
                            st.caption(f"⚠️ Heightmap manquante : {proj['heightmap']}")
                    else:
                        st.caption("⚠️ Pas de heightmap configurée")
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

# Message de chargement si présent
if st.session_state.get('_load_message'):
    st.success(st.session_state['_load_message'])
    # Effacer après affichage pour ne pas le répéter
    st.session_state.pop('_load_message', None)

if st.session_state.base_map is None:
    st.warning("[WARN] Veuillez d'abord charger une heightmap dans la barre latérale (gauche)")
else:
    # Onglets principaux
    tab_terrain, tab_satmap, tab_gen, tab_validation = st.tabs([
        " Terrain",
        "🛰️ Satmap Export",
        " Génération",
        "[INFO] Validation Masks",
    ])

    # ========================================================================
    # ONGLET TERRAIN — sous-onglets : Hypsométrique / NatureMap / Analyse
    # ========================================================================

    with tab_terrain:
        _t_hypso, _t_masques, _t_atlas = st.tabs([
            " Hypsométrique", "🏔️ Masques Terrain", "📊 Atlas Métrique"
        ])

        with _t_hypso:
            st.markdown("###  Colormap Hypsométrique")

            st.info(
                "ℹ️ Cette carte utilise **BaseMap** (données visuelles). "
                "Pour voir les **vraies zones d'altitude calibrées** (coastal/lowland/highland), "
                "allez dans **Terrain -> Analyse** après avoir généré le Pipeline Complet."
            )

            st.markdown("""
            Génère une carte colorée basée **uniquement** sur l'altitude, sans texture complexe.

            **Palette:** Vert (bas) -> Jaune -> Orange -> Rouge -> Marron (haut)
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
                            st.success("[OK] Hypsométrique générée")
                    except Exception as e:
                        st.error(f"[ERR] Erreur: {e}")

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

                        # Lire le fichier en mémoire pour download_button
                        with open(hyp_path, "rb") as f:
                            img_bytes = f.read()

                        st.download_button(
                            "📥 Télécharger PNG",
                            data=img_bytes,
                            file_name=Path(hyp_path).name,
                            mime="image/png",
                        )
                except Exception as e:
                    st.error(f"[ERR] Erreur affichage: {e}")

        # ========================================================================
        # ONGLET ANALYSE — Analyse Terrain + Slope Auto
        # ========================================================================

        with _t_masques:
            st.markdown("### 🏔️ Masques Terrain — Import Gaea + Correctif Pente")
            st.caption("Détection automatique du dossier gaea/ — assignez chaque fichier à son rôle")

            rp = st.session_state.get("resolved_paths", {})
            proj_path = st.session_state.get("current_project_path")

            if not proj_path:
                st.warning("⚠️ Aucun projet chargé — ouvrez ou créez un projet d'abord")
            else:
                from mask_utils import scan_gaea_folder, apply_mask_profile, load_and_normalize_mask, MASK_PROFILES

                gaea_dir = Path(proj_path) / "gaea"
                gaea_dir.mkdir(parents=True, exist_ok=True)

                # Bandeau statut
                col_scan1, col_scan2 = st.columns([3, 1])
                with col_scan1:
                    st.success(f"📁 `{gaea_dir}` détecté")
                with col_scan2:
                    if st.button("🔄 Rafraîchir", key="btn_refresh_gaea"):
                        st.session_state.pop("gaea_scan", None)

                if "gaea_scan" not in st.session_state:
                    with st.spinner("Scan du dossier gaea/..."):
                        st.session_state["gaea_scan"] = scan_gaea_folder(gaea_dir)

                scan = st.session_state["gaea_scan"]
                png_files = scan.get("png_files", [])

                if scan.get("converted"):
                    st.info(f"🔄 {len(scan['converted'])} fichier(s) float32 convertis : {', '.join(scan['converted'])}")
                if scan.get("errors"):
                    for e in scan["errors"]:
                        st.warning(f"⚠️ {e}")

                if not png_files:
                    st.warning("Aucun fichier PNG dans gaea/ — copiez vos exports Gaea ici")
                else:
                    st.caption(f"{len(png_files)} fichier(s) : {', '.join(png_files)}")
                    st.divider()

                    # Assignation des rôles
                    st.markdown("#### 🎯 Assignation des masques")
                    ROLES = {
                        "Slope (roche)":              "gaea_slope_file",
                        "Flow (érosion / talwegs)":   "gaea_flow_file",
                        "Deposit (alluvions)":         "gaea_deposit_file",
                        "Exclusion (zones manuelles)": "gaea_exclusion_file",
                    }
                    ROLE_DESCRIPTIONS = {
                        "Slope (roche)":              "blanc=roche, noir=herbe — rampe pente appliquée",
                        "Flow (érosion / talwegs)":   "blanc=talwegs, noir=neutre",
                        "Deposit (alluvions)":         "blanc=zones alluviales",
                        "Exclusion (zones manuelles)": "noir=zones protégées",
                    }
                    options = ["— non assigné —"] + png_files
                    col_a1, col_a2 = st.columns(2)
                    role_items = list(ROLES.items())
                    for idx, (role_label, state_key) in enumerate(role_items):
                        col = col_a1 if idx % 2 == 0 else col_a2
                        with col:
                            current = st.session_state.get(state_key, "— non assigné —")
                            if current not in options:
                                current = "— non assigné —"
                            selected = st.selectbox(
                                role_label,
                                options=options,
                                index=options.index(current),
                                key=f"select_{state_key}",
                                help=ROLE_DESCRIPTIONS[role_label]
                            )
                            st.session_state[state_key] = selected
                            if selected != "— non assigné —":
                                st.caption(f"✅ `{selected}`")

                    st.divider()

                    # Paramètres rampe
                    st.markdown("#### ⚙️ Rampe de Pente (depuis .bterr)")
                    atlas = st.session_state.get("terrain_atlas_df")
                    if atlas is not None:
                        import pandas as pd
                        p90 = float(atlas["slope_p90"].quantile(0.9))
                        s_mean = float(atlas["slope_mean"].mean())
                        st.caption(f"Atlas : pente moy {s_mean:.1f}° | p90 {p90:.1f}°")

                    col_p1, col_p2, col_p3 = st.columns(3)
                    with col_p1:
                        slope_min = st.slider("Seuil bas (°)", 0, 45,
                            st.session_state.get("gaea_slope_min", 15), 1, key="gaea_slope_min")
                    with col_p2:
                        slope_max_val = st.slider("Seuil haut (°)", 10, 60,
                            st.session_state.get("gaea_slope_max", 35), 1, key="gaea_slope_max")
                    with col_p3:
                        blur_radius = st.slider("Blur global (px)", 0, 50,
                            st.session_state.get("gaea_blur_radius", 8), 1, key="gaea_blur_radius")

                    st.info(f"Rampe : 0% à {slope_min}° → 100% à {slope_max_val}° | transition {slope_max_val - slope_min}°")
                    st.divider()

                    # Dossier de sortie
                    st.markdown("#### 💾 Sortie")
                    default_out = str(gaea_dir / "processed")
                    output_gaea_dir = st.text_input(
                        "Dossier de sortie",
                        value=st.session_state.get("gaea_output_dir", default_out),
                        key="gaea_output_dir"
                    )
                    output_gaea_dir_clean = normalize_path(output_gaea_dir)
                    if output_gaea_dir_clean != st.session_state.get("gaea_output_dir", ""):
                        st.session_state.gaea_output_dir = output_gaea_dir_clean
                        save_config()
                    st.divider()

                    # Génération
                    st.markdown("#### 🚀 Génération")
                    slope_assigned = st.session_state.get("gaea_slope_file", "— non assigné —") != "— non assigné —"
                    if not slope_assigned:
                        st.warning("Assignez au minimum le masque Slope pour générer")

                    if st.button("🔄 Générer masques corrigés", type="primary", disabled=not slope_assigned):
                        with st.spinner("Traitement en cours..."):
                            try:
                                import numpy as np
                                import cv2
                                import struct

                                errors  = []
                                results = {}
                                native  = rp["grid_size"] * 512
                                CELL_SIZE = 4.0

                                # 1. Masque d'exclusion
                                excl_mask = None
                                excl_file = st.session_state.get("gaea_exclusion_file", "— non assigné —")
                                if excl_file != "— non assigné —":
                                    excl_path = gaea_dir / excl_file
                                    if excl_path.exists():
                                        excl_raw = cv2.imread(str(excl_path), cv2.IMREAD_GRAYSCALE)
                                        if excl_raw is not None:
                                            excl_mask = cv2.resize(excl_raw, (native, native), interpolation=cv2.INTER_NEAREST)
                                            excl_mask = (excl_mask > 127).astype(np.float32)
                                            st.info(f"Exclusion : {100*(excl_mask==0).mean():.1f}% protégé")

                                # 2. Rampe de pente
                                slope_ramp = None
                                editor_dir = Path(rp["editor_dir"])
                                bterr_files = sorted(
                                    [f for f in editor_dir.glob("Terrain_*.bterr")
                                     if f.stem.replace("Terrain_","").isdigit()],
                                    key=lambda f: int(f.stem.replace("Terrain_",""))
                                )
                                if bterr_files:
                                    slope_map = np.zeros((native, native), np.float32)
                                    prog = st.progress(0, text="Calcul rampe pente...")
                                    for idx, bterr in enumerate(bterr_files):
                                        tid  = int(bterr.stem.replace("Terrain_",""))
                                        tx   = tid % rp["grid_size"]
                                        ty_v = tid // rp["grid_size"]
                                        ty_r = (rp["grid_size"] - 1) - ty_v
                                        data = open(bterr,"rb").read()
                                        i    = data.find(b"DATA")
                                        if i < 0: continue
                                        sz   = struct.unpack_from(">I", data, i+4)[0]
                                        hm   = np.frombuffer(data[i+8:i+8+sz], np.float32).reshape(129,129).astype(np.float64)
                                        gy, gx = np.gradient(hm, CELL_SIZE)
                                        sl   = np.degrees(np.arctan(np.hypot(gx,gy)))[:128,:128].astype(np.float32)
                                        sl_up = cv2.resize(sl, (512,512), interpolation=cv2.INTER_LINEAR)
                                        y0 = ty_r * 512
                                        x0 = tx   * 512
                                        slope_map[y0:y0+512, x0:x0+512] = sl_up
                                        prog.progress((idx+1)/len(bterr_files), text=f"Tuile {idx+1}/{len(bterr_files)}")
                                    slope_ramp = np.clip((slope_map - slope_min) / max(1, slope_max_val - slope_min), 0, 1)
                                    st.success(f"Rampe : {100*(slope_ramp>0.5).mean():.1f}% > 50%")

                                # 3. Traiter chaque masque
                                mask_configs = [
                                    ("gaea_slope_file",   "Rock_Slope",      "slope"),
                                    ("gaea_flow_file",    "Flow_Erosion",    "flow"),
                                    ("gaea_deposit_file", "Deposit_Alluvial","deposit"),
                                ]
                                out_dir = Path(output_gaea_dir_clean)
                                out_dir.mkdir(parents=True, exist_ok=True)

                                for state_key, out_name, mask_type in mask_configs:
                                    assigned = st.session_state.get(state_key, "— non assigné —")
                                    if assigned == "— non assigné —": continue
                                    mask_path = gaea_dir / assigned
                                    if not mask_path.exists():
                                        errors.append(f"{out_name} : introuvable"); continue
                                    try:
                                        mask_f = load_and_normalize_mask(mask_path, (native, native))
                                        mask_f = apply_mask_profile(mask_f, mask_type=mask_type,
                                                                     slope_ramp=slope_ramp, excl_mask=excl_mask)
                                        out_path = out_dir / f"{out_name}.png"
                                        cv2.imwrite(str(out_path), (mask_f * 65535).astype(np.uint16))
                                        results[out_name] = out_path
                                        profile = MASK_PROFILES[mask_type]
                                        st.success(f"✅ {out_name} ({profile['description']}) : {100*(mask_f>0).mean():.1f}% actif")
                                    except Exception as e:
                                        errors.append(f"{out_name} : {e}")

                                if results:
                                    st.markdown(f"**{len(results)} masque(s) exportés dans `{out_dir}`**")
                                for e in errors:
                                    st.warning(e)
                                if st.session_state.get("current_project_path"):
                                    save_project()

                            except Exception as e:
                                st.error(f"[ERR] {e}")
                                import traceback
                                st.code(traceback.format_exc())

        with _t_atlas:
            st.markdown("### 📊 Atlas Métrique — Analyse Complète Terrain")
            st.caption("Statistiques et métriques terrain calculées depuis heightmap")

            terrain_data = st.session_state.get('terrain_data')

            if not terrain_data:
                st.warning("⚠️ Données terrain non calculées. Chargez une heightmap depuis la sidebar.")
            else:
                # ── SECTION 1 : VUE D'ENSEMBLE ────────────────────────────
                st.markdown("####  Vue d'ensemble")

                heightmap = terrain_data['heightmap']
                slope = terrain_data['slope']
                params = terrain_data['params']

                # Stats altitude
                land_mask = heightmap > 0
                alt_land = heightmap[land_mask]
                alt_min = float(alt_land.min())
                alt_max = float(alt_land.max())
                denivele = alt_max - alt_min

                # Stats surface
                total_px = heightmap.size
                land_px = land_mask.sum()
                sea_px = total_px - land_px
                land_pct = (land_px / total_px) * 100
                sea_pct = (sea_px / total_px) * 100

                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("Dénivellation", f"{denivele:.0f}m")
                with c2:
                    st.metric("Terre", f"{land_pct:.1f}%")
                with c3:
                    st.metric("Mer", f"{sea_pct:.1f}%")
                with c4:
                    st.metric("Cellsize", f"{terrain_data['cellsize']} m/px")

                st.divider()

                # ── SECTION 2 : PARAMÈTRES AUTO-CALIBRÉS ──────────────────
                st.markdown("#### ⚙️ Paramètres Auto-Calibrés")
                st.caption("Seuils calculés automatiquement depuis la distribution terrain")

                col_p1, col_p2 = st.columns(2)

                with col_p1:
                    st.markdown("**Altitudes**")
                    st.text(f"Coastal max    : {params.get('coastal_alt_max_m', 'N/A')} m")
                    st.text(f"Grass Low max  : {params.get('grass_low_max_m', 'N/A')} m")
                    st.text(f"Grass Mid max  : {params.get('grass_mid_max_m', 'N/A')} m")
                    st.text(f"Grass High max : {params.get('grass_high_max_m', 'N/A')} m")

                with col_p2:
                    st.markdown("**Pentes**")
                    st.text(f"Debris min     : {params.get('debris_min_deg', 'N/A')}°")
                    st.text(f"Rock min       : {params.get('rock_min_deg', 'N/A')}°")
                    st.text(f"")
                    st.text(f"TPI local      : {params.get('tpi_local_radius_m', 'N/A')} m")

                st.divider()

            st.divider()

        # ========================================================================
        # ONGLET SATMAP EXPORT — Catalogue textures + Export masques
        # ========================================================================

    with tab_satmap:
        st.markdown("### 🛰️ Satmap Export Reforger")

        # Sous-onglets : Satmap v2
        subtab_satmap_v2 = st.tabs([
            "🚀 Satmap v2.0 (Layer.dds)"
        ])[0]

        with subtab_satmap_v2:
            st.markdown("### 🚀 Satmap v2.0 — Pipeline Layer.dds + LRS2")

            st.success(
                "✨ **Nouveau pipeline optimisé** (100% couverture, blocs 1-7 textures)  \n"
                "📂 Lit les `.edds` bruts depuis `.EditorData` (pas de décompression LZ4)  \n"
                "📋 Parse le chunk `LRS2` depuis `.Data/.ttile` (liste matériaux par bloc)  \n"
                "🎨 **Mode couleurs** : rapide | **Mode texturé** : qualité avec textures middle BCR"
            )

            st.markdown("---")

            # Vérification et régénération du catalogue
            rp_v2 = st.session_state.get("resolved_paths", {})
            catalog_str = st.session_state.get("catalog_path_global", "")
            catalog_ok = Path(catalog_str).exists() if catalog_str else False

            col_cat1, col_cat2 = st.columns([3, 1])
            with col_cat1:
                if catalog_ok:
                    st.success(f"✅ Catalogue : `{Path(catalog_str).name}` ({Path(catalog_str).stat().st_size // 1024} Ko)")
                else:
                    st.error("❌ Catalogue introuvable — configurez le chemin dans la sidebar")

            with col_cat2:
                if st.button("🔄 Scan .emat", key="btn_scan_emat_v2",
                              disabled=not catalog_ok,
                              help="Régénère les couleurs du catalogue depuis les fichiers .emat"):
                    try:
                        from emat_scanner_simple import scan_emat_directory
                        emat_dir = Path(catalog_str).parent / "emat"
                        if not emat_dir.exists():
                            st.error(f"❌ Dossier emat introuvable : {emat_dir}")
                        else:
                            result = scan_emat_directory(emat_dir, Path(catalog_str))
                            st.success(f"✅ {result['updated_count']} surfaces enrichies")
                            if result['warnings']:
                                with st.expander(f"⚠️ {len(result['warnings'])} avertissements"):
                                    for w in result['warnings']:
                                        st.text(w)
                    except Exception as e:
                        st.error(f"❌ Erreur : {e}")
                        import traceback
                        st.code(traceback.format_exc())

            st.markdown("---")

            # Configuration
            st.markdown("#### ⚙️ Configuration")

            rp = st.session_state.get("resolved_paths", {})

            if not rp.get("valid"):
                st.warning("⚠️ Configurez le chemin addon dans la sidebar")
            else:
                col_config1, col_config2 = st.columns(2)

                with col_config1:
                    terrain_dir_v2 = rp.get("terrain_dir", "")
                    st.text_input(
                        "📁 Dossier Terrain/",
                        value=terrain_dir_v2,
                        disabled=True,
                        help="Dossier racine du terrain (depuis resolved_paths)"
                    )

                with col_config2:
                    resolution_v2 = st.selectbox(
                        "📐 Résolution finale",
                        options=["4k (4097×4097)", "8k (8193×8193)", "16k (16385×16385)"],
                        index=0,
                        help="Résolution de la satmap finale (downscale depuis résolution native)"
                    )

                # Mode génération — forcé sur "Texturé" (mode couleur désactivé)
                mode_v2 = "Texturé (qualité)"

                # Chemin vers les textures middle
                middles_dir_str = st.text_input(
                    "📁 Dossier textures middle (optionnel)",
                    value="data/Textures_ArmaReforger/texture_Middle",
                    help="Chemin vers le dossier contenant les PNG middle pour le rendu tuilé. Laisser vide pour mode couleurs plates.",
                    key="middles_dir_v2"
                )

                st.markdown("---")

                # Génération
                st.markdown("#### 🚀 Génération Satmap v2.0")

                # Bouton génération
                generate_v2_btn = st.button(
                    "🎨 Générer Satmap v2.0",
                    use_container_width=True,
                    type="primary"
                )

                if generate_v2_btn:
                    with st.spinner("⏳ Génération en cours..."):
                        try:
                            from satmap_v2_generator import generate_satmap_v2
                            from pathlib import Path

                            # Chemins
                            terrain_dir = Path(terrain_dir_v2)

                            # Récupérer catalog_path depuis session_state
                            catalog_path_str = st.session_state.get("catalog_path_global", "")
                            if not catalog_path_str:
                                st.error("❌ Chemin catalog.json manquant ou invalide — configurez-le dans la sidebar (section '📦 Projet Reforger')")
                                st.stop()
                            catalog_path = Path(catalog_path_str)

                            # Vérifier que le dossier Terrain existe
                            if not terrain_dir.exists():
                                st.error(f"❌ Dossier Terrain introuvable : `{terrain_dir}`")
                                st.info("💡 Vérifiez la configuration du projet dans la sidebar")
                                st.stop()

                            # Vérifier que catalog.json existe
                            if not catalog_path.exists():
                                st.error(f"❌ catalog.json introuvable : `{catalog_path}`")
                                st.info("💡 Vérifiez le chemin dans la sidebar (section '📦 Projet Reforger')")
                                st.stop()

                            # Charger liste surfaces depuis terr_file
                            surfaces_list = st.session_state.get("terr_materials", [])
                            if not surfaces_list:
                                st.error("❌ Liste des matériaux vide - chargez un fichier .terr d'abord")
                            else:
                                # Résolution
                                res_map = {
                                    "4k (4097×4097)": 4097,
                                    "8k (8193×8193)": 8193,
                                    "16k (16385×16385)": 16385
                                }
                                target_res = res_map[resolution_v2]

                                # Mode
                                mode = "colors" if "Couleurs" in mode_v2 else "textured"

                                # Sortie
                                output_dir = Path(get_output_dir()) / "satmap_v2"
                                output_dir.mkdir(parents=True, exist_ok=True)
                                output_path = output_dir / f"satmap_v2_{mode}_{target_res}.png"

                                # Générer
                                st.info(f"📊 {len(surfaces_list)} matériaux | {rp['grid_size']}×{rp['grid_size']} tuiles")

                                # Appeler la version complète avec vérification
                                if mode == "textured":
                                    from satmap_v2_textured import generate_satmap_v2_textured_complete
                                    print(f"DEBUG: Lancement génération vers {output_path}")

                                    # Préparer middles_dir si configuré
                                    middles_dir = None
                                    if middles_dir_str and middles_dir_str.strip():
                                        middles_path = Path(middles_dir_str)
                                        if middles_path.exists():
                                            middles_dir = middles_path
                                        else:
                                            st.warning(f"⚠️ Dossier middles introuvable : {middles_dir_str} — mode couleurs plates utilisé")

                                    stats = generate_satmap_v2_textured_complete(
                                        terrain_dir,
                                        catalog_path,
                                        output_path,
                                        terr_file=rp.get("terr_file"),
                                        mode=mode,
                                        target_resolution=target_res,
                                        verbose=True,  # 🔍 DIAGNOSTIC ACTIF
                                        middles_dir=middles_dir
                                    )
                                    print(f"DEBUG: Génération terminée, stats={stats}")
                                    print(f"DEBUG: Fichier existe ? {output_path.exists()}")
                                    if stats:
                                        st.success(f"✅ {stats['size']} générée")
                                        if stats['missing_layers'] > 0:
                                            st.warning(f"⚠️ {stats['missing_layers']} layers manquants reconstruits")
                                        if stats['material_issues'] > 0:
                                            st.warning(f"⚠️ {stats['material_issues']} matériaux sans couleur (fallback Grass_03)")
                                    else:
                                        st.success(f"✅ Satmap v2.0 générée : `{output_path}`")
                                else:
                                    generate_satmap_v2(
                                        terrain_dir,
                                        catalog_path,
                                        surfaces_list,
                                        output_path,
                                        mode=mode,
                                        target_resolution=target_res
                                    )
                                    st.success(f"✅ Satmap v2.0 générée : `{output_path}`")

                                # Afficher
                                if output_path.exists():
                                    from PIL import Image
                                    img = Image.open(output_path)
                                    st.image(img, caption=f"Satmap v2.0 ({img.width}×{img.height})", use_container_width=True)

                                    # Download
                                    with open(output_path, "rb") as f:
                                        st.download_button(
                                            "📥 Télécharger Satmap v2.0",
                                            data=f.read(),
                                            file_name=output_path.name,
                                            mime="image/png"
                                        )

                        except Exception as e:
                            st.error(f"❌ Erreur : {e}")
                            import traceback
                            st.code(traceback.format_exc())
                            print(f"ERREUR COMPLETE: {traceback.format_exc()}")


        # ========================================================================
        # ONGLET GÉNÉRATION — Nouvelle structure: Textures / Végétation
        # ========================================================================

    with tab_gen:
        _g_textures, _g_vegetation = st.tabs([
            " Textures Terrain",
            "🌲 Végétation"
        ])

        # ══════════════════════════════════════════════════════════════════════════════
        # TEXTURES TERRAIN — Aperçu + Biome + Génération Masques
        # ══════════════════════════════════════════════════════════════════════════════

        with _g_textures:
            st.markdown("### 🎨 Génération Masques Terrain")
            st.info(
                "Pipeline V2 (génération slope/curvature depuis heightmap) retiré le 2026-07-08 — "
                "jugé peu fiable. Remplacement prévu : import direct des masques Gaea "
                "(slope, deposit, flow, exclusion) avec normalisation 4096×4097.  \n"
                "Le correctif QTRE (check_qtre) a été sauvegardé dans "
                "scripts/tools/qtre_correctif_pipeline_v2_backup.py."
            )

        # ══════════════════════════════════════════════════════════════════════════════
        # VÉGÉTATION — Aperçu + Génération Masques Végétation
        # ══════════════════════════════════════════════════════════════════════════════

        with _g_vegetation:
            st.markdown("### 🌲 Carte Végétation Potentielle")
            st.caption("Carte générée automatiquement depuis les signaux terrain")

            # Vérifier que terrain_data existe
            terrain_data = st.session_state.get('terrain_data')

            if not terrain_data:
                st.warning("⚠️ **Chargez une heightmap** depuis la sidebar pour générer la carte de végétation")
            else:
                from vegetation_map import (
                    VEGETATION_TYPES,
                    compute_vegetation_scores,
                    render_vegetation_rgb,
                    export_vegetation_png,
                    compute_vegetation_stats
                )

                st.divider()

                # ── Paramètres ─────────────────────────────────────────────────
                st.subheader("⚙️ Paramètres")

                col_v1, col_v2 = st.columns(2)

                with col_v1:
                    min_score = st.slider(
                        "Seuil minimum affichage",
                        0.0, 0.5, 0.05, 0.01,
                        key="veg_min_score",
                        help="Score minimum pour qu'un type de végétation soit visible"
                    )

                with col_v2:
                    blend_mode = st.checkbox(
                        "Mode mélange",
                        value=True,
                        key="veg_blend_mode",
                        help="True=mélange pondéré des couleurs, False=type dominant uniquement"
                    )

                # ── Génération automatique ────────────────────────────────────
                # Générer si pas encore fait OU si params ont changé
                need_regen = (
                    'veg_scores' not in st.session_state or
                    st.session_state.get('veg_params', {}).get('min_score') != min_score or
                    st.session_state.get('veg_params', {}).get('blend') != blend_mode
                )

                if need_regen:
                    try:
                        # Calculer scores (utilise terrain_data directement)
                        scores = compute_vegetation_scores(
                            heightmap=terrain_data['heightmap'],
                            slope=terrain_data['slope'],
                            curvature=terrain_data['curvature'],
                            tpi_local=terrain_data['tpi_local'],
                            tpi_macro=terrain_data['tpi_macro'],
                            flow=terrain_data['flow'],
                            aspect=terrain_data['aspect'],
                            distance_cote=terrain_data['distance_cote'],
                            params=terrain_data['params'],
                            cellsize=terrain_data['cellsize']
                        )

                        # Rendu RGB
                        rgb = render_vegetation_rgb(
                            scores,
                            heightmap=terrain_data['heightmap'],
                            min_score=min_score,
                            blend=blend_mode
                        )

                        # Statistiques
                        stats = compute_vegetation_stats(scores, terrain_data['cellsize'], min_score)

                        # Sauvegarder dans session_state
                        st.session_state['veg_scores'] = scores
                        st.session_state['veg_rgb'] = rgb
                        st.session_state['veg_stats'] = stats
                        st.session_state['veg_params'] = {
                            'min_score': min_score,
                            'blend': blend_mode,
                            'cellsize': terrain_data['cellsize']
                        }

                    except Exception as e:
                        st.error(f"[ERR] Erreur génération : {e}")
                        import traceback
                        st.code(traceback.format_exc())

                # ── Affichage résultats ────────────────────────────────────────
                if 'veg_rgb' in st.session_state:
                    st.divider()
                    st.subheader("📊 Résultats")

                    # Aperçu carte
                    col_r1, col_r2 = st.columns([2, 1])

                    with col_r1:
                        st.markdown("**Carte de végétation**")
                        st.image(st.session_state.veg_rgb, use_container_width=True)

                    with col_r2:
                        st.markdown("**Légende**")
                        for veg_type, info in VEGETATION_TYPES.items():
                            color_hex = "#{:02x}{:02x}{:02x}".format(*info['color'])
                            st.markdown(
                                f"<div style='display: flex; align-items: center;'>"
                                f"<div style='width: 20px; height: 20px; background-color: {color_hex}; "
                                f"border: 1px solid #ccc; margin-right: 8px;'></div>"
                                f"<span style='font-size: 0.85em;'>{info['label']}</span>"
                                f"</div>",
                                unsafe_allow_html=True
                            )

                    # Statistiques
                    st.divider()
                    st.markdown("**📈 Statistiques par type**")

                    stats = st.session_state.veg_stats

                    # Tri par couverture décroissante
                    sorted_stats = sorted(
                        stats.items(),
                        key=lambda x: x[1]['coverage_pct'],
                        reverse=True
                    )

                    # Afficher top types
                    for veg_type, stat in sorted_stats:
                        if stat['coverage_pct'] > 0.1:  # Au moins 0.1%
                            col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
                            with col_s1:
                                st.text(f"{stat['label']}")
                            with col_s2:
                                st.metric("Surface", f"{stat['area_ha']:.1f} ha")
                            with col_s3:
                                st.metric("Couverture", f"{stat['coverage_pct']:.1f}%")

                    # Export
                    st.divider()
                    st.markdown("**💾 Export**")

                    col_e1, col_e2, col_e3 = st.columns(3)

                    with col_e1:
                        # Export PNG aperçu
                        if st.button("📥 Exporter Aperçu PNG"):
                            try:
                                project_path = st.session_state.get('current_project_path')
                                if project_path:
                                    from datetime import datetime
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    output_dir = Path(project_path) / "generated" / f"vegetation_{timestamp}"
                                    output_dir.mkdir(parents=True, exist_ok=True)
                                    output_path = output_dir / "vegetation_map.png"

                                    export_vegetation_png(st.session_state.veg_rgb, output_path)
                                    st.success(f"[OK] Exporté : {output_path}")
                                else:
                                    st.error("[ERR] Aucun projet chargé")
                            except Exception as e:
                                st.error(f"[ERR] {e}")

                    with col_e2:
                        # Export 16 masques 16-bit
                        if st.button("🎯 Exporter Masques 16-bit"):
                            try:
                                project_path = st.session_state.get('current_project_path')
                                if project_path and 'veg_scores' in st.session_state:
                                    from datetime import datetime
                                    from vegetation_map import export_vegetation_masks

                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    output_dir = Path(project_path) / "generated" / f"vegetation_masks_{timestamp}"

                                    min_score = st.session_state.get('veg_params', {}).get('min_score', 0.1)

                                    with st.spinner("Export des 16 masques en cours..."):
                                        exported_files = export_vegetation_masks(
                                            st.session_state.veg_scores,
                                            output_dir,
                                            min_score=min_score
                                        )

                                    st.success(f"✅ {len(exported_files)} masques exportés dans :")
                                    st.code(str(output_dir), language="")

                                    # Liste des fichiers exportés
                                    with st.expander("📋 Fichiers générés"):
                                        for veg_type, filepath in exported_files.items():
                                            st.text(f"✓ {Path(filepath).name}")
                                else:
                                    st.error("[ERR] Aucun projet ou scores végétation non générés")
                            except Exception as e:
                                st.error(f"[ERR] {e}")
                                import traceback
                                st.code(traceback.format_exc())

                    with col_e3:
                        # Téléchargement direct aperçu
                        from io import BytesIO
                        import cv2

                        success, buffer = cv2.imencode('.png', cv2.cvtColor(st.session_state.veg_rgb, cv2.COLOR_RGB2BGR))
                        if success:
                            st.download_button(
                                "⬇️ Télécharger Aperçu",
                                data=buffer.tobytes(),
                                file_name="vegetation_map.png",
                                mime="image/png"
                            )

        # ========================================================================
        # ONGLET VALIDATION MASKS
        # ========================================================================

    with tab_validation:
        st.markdown("### Validation Masks Terrain")

        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        # Initialisation session state
        if "val_masks" not in st.session_state:
            st.session_state.val_masks = []
        if "val_paths" not in st.session_state:
            st.session_state.val_paths = []

        # ═══════════════════════════════════════════════════════════════════
        # 📂 CHARGEMENT MASKS (pour tous les outils)
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("## 📂 Chargement Masks")
        st.caption("Chargez vos masks pour utiliser tous les outils ci-dessous")

        col_load1, col_load2 = st.columns([2, 1])

        with col_load1:
            # Paramètre RAM : redimensionner si trop grand
            reduce_size = st.checkbox(
                "💾 Réduire résolution (économie RAM)",
                value=False,
                help="Redimensionne les masques > 4096px pour éviter les erreurs de mémoire. Recommandé si vous avez peu de RAM.",
                key="reduce_masks_ram"
            )

            max_size = 4096 if reduce_size else None

            # Option 1: Récupérer depuis pipeline_v2
            if "masks_dir_v2" in st.session_state and st.session_state.masks_dir_v2:
                st.info(f"📁 Dossier masks Pipeline V2: `{st.session_state.masks_dir_v2}`")
                if st.button("📥 Charger masks depuis Pipeline V2", key="load_pipeline_util"):
                    from pathlib import Path
                    masks_dir = Path(st.session_state.masks_dir_v2)
                    if masks_dir.exists():
                        file_paths = sorted(masks_dir.glob("*.png"))
                        if file_paths:
                            with st.spinner("Chargement des masks..."):
                                result = pv.load_masks_from_paths(file_paths, max_size=max_size)
                            if result['masks']:
                                st.session_state.val_masks = result['masks']
                                st.session_state.val_paths = result['paths']
                                st.success(f"✅ {len(result['masks'])} masks chargés depuis Pipeline V2")
                                if result['warnings']:
                                    with st.expander("⚠️ Avertissements", expanded=False):
                                        for w in result['warnings']:
                                            st.caption(f"• {w}")
                            else:
                                st.error("❌ Aucun mask valide")
                                if result['errors']:
                                    st.error("Erreurs: " + ", ".join(result['errors'][:5]))
                        else:
                            st.error(f"❌ Aucun fichier PNG dans {masks_dir}")
                    else:
                        st.error(f"❌ Dossier inexistant: {masks_dir}")

            # Option 2: Upload manuel
            uploaded_files_util = st.file_uploader(
                "📤 OU upload manuel masks PNG 16-bit",
                type=["png"],
                accept_multiple_files=True,
                key="val_upload_util"
            )

            if uploaded_files_util:
                if st.button("📥 Charger masks uploadés", key="load_upload_util"):
                    import tempfile
                    temp_paths = []
                    try:
                        for uf in uploaded_files_util:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                                tmp.write(uf.read())
                                temp_paths.append(tmp.name)

                        with st.spinner("Chargement des masks..."):
                            result = pv.load_masks_from_paths(temp_paths, max_size=max_size)
                        if result['masks']:
                            st.session_state.val_masks = result['masks']
                            st.session_state.val_paths = [uf.name for uf in uploaded_files_util]
                            st.success(f"✅ {len(result['masks'])} masks chargés")
                            if result['warnings']:
                                st.warning("⚠️ Conversions: " + ", ".join(result['warnings'][:3]))
                        else:
                            st.error("❌ Aucun mask valide")
                            if result['errors']:
                                st.error("Erreurs: " + ", ".join(result['errors'][:5]))
                    except Exception as e:
                        st.error(f"❌ Erreur chargement: {e}")

        with col_load2:
            # Statut chargement
            if st.session_state.val_masks:
                st.success(f"✅ {len(st.session_state.val_masks)} masks chargés")

                # Aperçu liste
                with st.expander("📋 Liste des masks", expanded=False):
                    for i, path in enumerate(st.session_state.val_paths[:20]):
                        name = Path(path).stem if isinstance(path, str) else f"mask_{i}"
                        st.caption(f"{i+1}. {name}")
                    if len(st.session_state.val_paths) > 20:
                        st.caption(f"... et {len(st.session_state.val_paths) - 20} autres")

                # Bouton réinitialiser
                if st.button("🗑️ Réinitialiser", key="reset_masks_util"):
                    st.session_state.val_masks = []
                    st.session_state.val_paths = []
                    st.rerun()
            else:
                st.info("ℹ️ Aucun mask chargé")

        # ═══════════════════════════════════════════════════════════════════
        # 🔧 ZONE 1 : UTILITAIRES
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("## 🔧 Utilitaires Masks")
        st.caption("Outils indépendants pour manipulation de masks")

        # ───────────────────────────────────────────────────────────────────
        # Assemblage de Masks
        # ───────────────────────────────────────────────────────────────────

        with st.expander("⚙️ Assemblage de Masks (fusion de textures identiques)", expanded=False):
            st.info(
                "**Usage** : Assembler plusieurs masks de **même texture** provenant de sources différentes.\n\n"
                "**Exemple** : Fusionner `grass_01` + `grass_02` + `grass_03` en un seul masque blanc uniforme.\n\n"
                "💡 **Recommandé** : Mode **Union Blanc** pour créer un masque unique en blanc pur (65535)."
            )

            if len(st.session_state.val_masks) >= 2:
                # Sélection des masques à assembler
                mask_names = [Path(p).stem if isinstance(p, str) else f"mask_{i}"
                              for i, p in enumerate(st.session_state.val_paths)]

                st.success(f"✅ {len(st.session_state.val_masks)} masks disponibles pour assemblage")

                selected_names = st.multiselect(
                    "🎯 Sélectionner les masks à assembler",
                    options=mask_names,
                    default=mask_names,  # Tous sélectionnés par défaut
                    help="Choisissez les masks à fusionner ensemble (au moins 2)",
                    key="assembly_mask_select"
                )

                if len(selected_names) < 2:
                    st.warning("⚠️ Sélectionnez au moins 2 masks pour l'assemblage")
                else:
                    col_b1, col_b2 = st.columns([1, 1])

                    with col_b1:
                        assembly_mode = st.radio(
                            "Mode assemblage",
                            ["union_white", "max", "add", "homogeneous", "priority"],
                            index=0,
                            help=(
                                "• union_white = toutes les zones → blanc pur (65535) — **RECOMMANDÉ pour fusionner textures identiques**\n"
                                "• max = valeur maximale\n"
                                "• add = somme (sature à 65535)\n"
                                "• homogeneous = moyenne\n"
                                "• priority = ordre 01→XX"
                            ),
                            format_func=lambda x: {
                                "union_white": "🎯 Union Blanc (zones fusionnées → blanc)",
                                "max": "Maximum",
                                "add": "Addition",
                                "homogeneous": "Moyenne",
                                "priority": "Priorité"
                            }.get(x, x)
                        )

                        if st.button("Assembler masks", key="btn_assemble_util"):
                            with st.spinner("Assemblage..."):
                                try:
                                    # Filtrer les masks sélectionnés
                                    selected_indices = [i for i, name in enumerate(mask_names) if name in selected_names]
                                    selected_masks = [st.session_state.val_masks[i] for i in selected_indices]
                                    selected_paths = [st.session_state.val_paths[i] for i in selected_indices]

                                    # Diagnostic avant assemblage
                                    st.info(f"🔍 Diagnostic pré-assemblage : {len(selected_masks)} masks sélectionnés")
                                    for i, (idx, name) in enumerate(zip(selected_indices, selected_names)):
                                        mask = selected_masks[i]
                                        non_zero = np.count_nonzero(mask)
                                        coverage = (non_zero / mask.size) * 100 if mask.size > 0 else 0
                                        st.caption(
                                            f"  • {name}: {mask.shape} {mask.dtype} | "
                                            f"{non_zero:,} px actifs ({coverage:.2f}%) | "
                                            f"min={np.min(mask)}, max={np.max(mask)}, mean={np.mean(mask[mask>0]) if non_zero > 0 else 0:.0f}"
                                        )

                                    ordered_indices = pv._compute_ordered_indices(selected_paths) if assembly_mode == "priority" else None

                                    assembled = pv.assemble_masks(
                                        selected_masks,
                                        mode=assembly_mode,
                                        ordered_indices=ordered_indices
                                    )
                                    st.session_state.val_assembled = assembled

                                    non_zero = np.count_nonzero(assembled)
                                    coverage = (non_zero / assembled.size) * 100
                                    mean_val = np.mean(assembled[assembled > 0]) if non_zero > 0 else 0
                                    size_mb = (assembled.nbytes / 1024 / 1024)

                                    st.success(
                                        f"✅ Assemblage de {len(selected_masks)} masks (mode '{assembly_mode}'):\n\n"
                                        f"• Taille: {assembled.shape[1]}×{assembled.shape[0]} px ({size_mb:.1f} MB)\n\n"
                                        f"• Couverture: {non_zero:,} px actifs ({coverage:.2f}%)\n\n"
                                        f"• Valeurs: min={np.min(assembled)}, max={np.max(assembled)}, mean={mean_val:.0f}"
                                    )

                                except Exception as e:
                                    st.error(f"[ERR] {e}")
                                    import traceback
                                    st.code(traceback.format_exc())

                    with col_b2:
                        if "val_assembled" in st.session_state:
                            assembled = st.session_state.val_assembled

                            # Visualisation du masque assemblé
                            st.markdown("**Aperçu assemblé**")

                            # Créer un affichage normalisé pour visualisation
                            if np.max(assembled) > 0:
                                # Redimensionner pour aperçu si trop grand (éviter DecompressionBombError)
                                max_preview_size = 2048
                                h, w = assembled.shape

                                if h > max_preview_size or w > max_preview_size:
                                    # Calculer ratio de redimensionnement
                                    ratio = min(max_preview_size / h, max_preview_size / w)
                                    new_h = int(h * ratio)
                                    new_w = int(w * ratio)

                                    # Redimensionner pour aperçu uniquement
                                    display_img = cv2.resize(assembled, (new_w, new_h), interpolation=cv2.INTER_NEAREST)
                                    display_img = ((display_img.astype(np.float32) / 65535.0) * 255).astype(np.uint8)

                                    st.image(
                                        display_img,
                                        caption=f"Aperçu assemblé (original: {w}×{h}, aperçu: {new_w}×{new_h})",
                                        use_container_width=True
                                    )
                                else:
                                    # Image assez petite pour affichage direct
                                    display_img = ((assembled.astype(np.float32) / 65535.0) * 255).astype(np.uint8)
                                    st.image(display_img, caption=f"Mask assemblé ({w}×{h})", use_container_width=True)
                            else:
                                st.warning("⚠️ Masque vide (tous les pixels = 0)")

                            # Histogramme
                            fig, ax = plt.subplots(figsize=(6, 3))
                            data = assembled[assembled > 0]
                            if data.size > 0:
                                ax.hist(data, bins=50, color='steelblue', alpha=0.7, edgecolor='black')
                                ax.set_title(f"Distribution valeurs non-nulles")
                                ax.set_xlabel(f"Intensité (0-65535)")
                                ax.set_ylabel("Pixels")
                                ax.grid(alpha=0.3, linestyle='--')
                                ax.axvline(np.mean(data), color='red', linestyle='--', linewidth=2, label=f'Moyenne: {np.mean(data):.0f}')
                                ax.legend()
                            else:
                                ax.text(0.5, 0.5, 'Aucune donnée', ha='center', va='center', fontsize=14)
                            st.pyplot(fig)
                            plt.close()

                            # Export
                            success, buffer = cv2.imencode('.png', assembled)
                            if success:
                                st.download_button(
                                    "🔽 Télécharger mask assemblé (PNG 16-bit)",
                                    data=buffer.tobytes(),
                                    file_name=f"assembled_{assembly_mode}.png",
                                    mime="image/png",
                                    key="dl_assembled_util"
                                )
            else:
                st.warning("⚠️ Chargez au moins 2 masks dans la section **📂 Chargement Masks** ci-dessus pour utiliser l'assemblage")

        # ═══════════════════════════════════════════════════════════════════
        # ✓ ZONE 2 : WORKFLOW VALIDATION QTRE
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("## ✓ Workflow Validation QTRE")
        st.caption("Processus linéaire : Chargement → Analyse → Correction → Export")

        # ───────────────────────────────────────────────────────────────────
        # A — Chargement et Analyse Conflits
        # ───────────────────────────────────────────────────────────────────

        st.divider()
        st.markdown("#### A — Chargement et Analyse Conflits")

        # Récupérer depuis pipeline_v2 ou upload manuel
        col_a1, col_a2 = st.columns([2, 1])

        with col_a1:
            # Option 1: Récupérer depuis pipeline_v2
            if "masks_dir_v2" in st.session_state:
                st.info(f"Dossier masks Pipeline V2: `{st.session_state.masks_dir_v2}`")
                if st.button("Charger masks depuis Pipeline V2"):
                    from pathlib import Path
                    masks_dir = Path(st.session_state.masks_dir_v2)
                    if masks_dir.exists():
                        file_paths = sorted(masks_dir.glob("*.png"))
                        if file_paths:
                            result = pv.load_masks_from_paths(file_paths)
                            if result['masks']:
                                st.session_state.val_masks = result['masks']
                                st.session_state.val_paths = result['paths']
                                st.success(f"[OK] {len(result['masks'])} masks chargés depuis Pipeline V2")
                                if result['warnings']:
                                    st.warning("Conversions: " + ", ".join(result['warnings'][:3]))
                            else:
                                st.error("[ERR] Aucun mask valide")
                                if result['errors']:
                                    st.error("Erreurs: " + ", ".join(result['errors'][:5]))

            # Option 2: Upload manuel
            uploaded_files = st.file_uploader(
                "OU upload manuel masks PNG 16-bit",
                type=["png"],
                accept_multiple_files=True,
                key="val_upload"
            )

            if uploaded_files:
                if st.button("Charger masks uploadés"):
                    import tempfile
                    temp_paths = []
                    try:
                        for uf in uploaded_files:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                                tmp.write(uf.read())
                                temp_paths.append(tmp.name)

                        result = pv.load_masks_from_paths(temp_paths)
                        if result['masks']:
                            st.session_state.val_masks = result['masks']
                            st.session_state.val_paths = [uf.name for uf in uploaded_files]
                            st.success(f"[OK] {len(result['masks'])} masks chargés")
                        else:
                            st.error("[ERR] Aucun mask valide")
                            if result['errors']:
                                st.error("Erreurs: " + ", ".join(result['errors'][:5]))
                    finally:
                        for p in temp_paths:
                            try:
                                Path(p).unlink()
                            except:
                                pass

        with col_a2:
            if st.session_state.val_masks:
                st.metric("Masks chargés", len(st.session_state.val_masks))
                shape = st.session_state.val_masks[0].shape
                st.caption(f"Résolution: {shape[1]}x{shape[0]}")

        # Analyse conflits QTRE
        if len(st.session_state.val_masks) >= 2:
            st.markdown("**Paramètres analyse QTRE**")

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                conflict_threshold = st.slider(
                    "Seuil émergence texture",
                    0.01, 0.20, 0.05, 0.01,
                    help="Texture active si moyenne bloc > seuil (défaut 0.05 = 5%)"
                )
            with col_p2:
                cellsize_val = st.number_input(
                    "Résolution (m/px)",
                    value=st.session_state.get("cellsize", 4.0),
                    min_value=1.0,
                    max_value=10.0,
                    step=0.5,
                    format="%.1f"
                )

            if st.button("Analyser conflits QTRE (blocs 32m)", type="primary"):
                with st.spinner("Analyse QTRE par blocs 32m..."):
                    stats = pv.analyze_conflicts_qtre(
                        st.session_state.val_masks,
                        cellsize=cellsize_val,
                        threshold=conflict_threshold
                    )
                    st.session_state.val_qtre_stats = stats

                    # Afficher métriques QTRE
                    st.markdown("### 📊 Résultats QTRE")

                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    with col_m1:
                        st.metric(
                            "Blocs critiques (≥6)",
                            f"{stats['critical_blocs']}",
                            f"{stats['critical_pct']:.2f}%",
                            delta_color="inverse"
                        )
                    with col_m2:
                        st.metric(
                            "Blocs limite (4-5)",
                            f"{stats['limit_blocs']}",
                            f"{stats['limit_pct']:.2f}%"
                        )
                    with col_m3:
                        st.metric(
                            "Blocs OK (≤3)",
                            f"{stats['ok_blocs']}",
                            f"{stats['ok_pct']:.2f}%"
                        )
                    with col_m4:
                        verdict_color = "🟢" if stats['verdict'] == "OK" else "🔴"
                        st.metric("Verdict", f"{verdict_color} {stats['verdict']}")

                    # Top paires critiques
                    if stats['top_pairs']:
                        st.markdown("**Top paires co-actives (blocs critiques):**")
                        for tex_a, tex_b, count in stats['top_pairs']:
                            st.text(f"• {tex_a} + {tex_b}: {count} blocs")

                    # Heatmap QTRE
                    st.markdown("**Heatmap densité textures par bloc 32m**")
                    fig, ax = plt.subplots(1, 1, figsize=(10, 8))

                    # Colormap : vert → jaune → orange → rouge
                    cmap = mcolors.LinearSegmentedColormap.from_list(
                        'qtre',
                        ['#1a1a1a', '#2a4a2a', '#4a6a2a', '#ffaa00', '#ff4400', '#ff0000']
                    )
                    im = ax.imshow(stats['heatmap'], cmap=cmap, vmin=0, vmax=8, interpolation='nearest')
                    ax.set_title(f"Heatmap QTRE — {stats['total_blocs']} blocs analysés")
                    ax.axis('off')
                    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
                    cbar.set_label('Nb textures/bloc', rotation=270, labelpad=15)

                    st.pyplot(fig)
                    plt.close()

        # ───────────────────────────────────────────────────────────────────
        # B — Correction par ordre de priorité
        # ───────────────────────────────────────────────────────────────────

        if len(st.session_state.val_masks) >= 2:
            st.divider()
            st.markdown("#### B — Correction par Priorité Stricte")
            st.caption("Texture prioritaire gagne + normalisation intelligente")

            # Ordre de priorité basé sur noms numériques (inversé : haute priorité d'abord)
            # IMPORTANT: utiliser SEULEMENT les masques effectivement chargés (val_paths peut contenir plus d'entrées si certains masques ont échoué)
            mask_names = [Path(p).stem for p in st.session_state.val_paths[:len(st.session_state.val_masks)]]
            priority_order = list(reversed(sorted(mask_names)))  # Ordre inversé (32→01)

            st.info(f"📋 Ordre de priorité : {' → '.join(priority_order[:5])}{'...' if len(priority_order) > 5 else ''} (haute priorité en premier)")

            if st.button("Appliquer nettoyage par priorité", type="primary"):
                with st.spinner("Nettoyage par priorité stricte..."):
                    # Préparer dict masks
                    masks_dict = {name: mask for name, mask in zip(mask_names, st.session_state.val_masks)}

                    # Appliquer nettoyage
                    result = pv.clean_masks_by_priority(
                        masks_dict,
                        priority_order,
                        cellsize=cellsize_val,
                        threshold=conflict_threshold
                    )

                    st.session_state.val_cleaned = list(result['masks'].values())
                    st.session_state.val_clean_stats = result['stats']

                    # Synchroniser val_paths avec l'ordre de result['masks']
                    # Créer mapping name->path
                    name_to_path = {Path(p).stem: p for p in st.session_state.val_paths}
                    # Reconstruire val_paths dans l'ordre de result['masks']
                    st.session_state.val_cleaned_paths = [
                        name_to_path.get(name, f"mask_{name}.png")
                        for name in result['masks'].keys()
                    ]

                    # Afficher stats avant/après
                    st.success("✅ Nettoyage terminé")

                    st.markdown("### 📊 Stats Avant / Après")
                    col_s1, col_s2, col_s3 = st.columns(3)

                    stats_before = result['stats']['blocs_avant']
                    stats_after = result['stats']['blocs_apres']

                    with col_s1:
                        st.metric(
                            "Blocs critiques",
                            f"{stats_after['critical']}",
                            f"{stats_after['critical'] - stats_before['critical']}"
                        )
                    with col_s2:
                        st.metric(
                            "Blocs limite",
                            f"{stats_after['limit']}",
                            f"{stats_after['limit'] - stats_before['limit']}"
                        )
                    with col_s3:
                        st.metric(
                            "Réduction critiques",
                            f"{result['stats']['reduction_critique_pct']:.2f}%",
                            delta_color="normal"
                        )

                    st.info(f"🔧 {result['stats']['pixels_modifies']:,} pixels modifiés")

            # Visualisation avant/après (heatmaps)
            if "val_qtre_stats" in st.session_state and "val_cleaned" in st.session_state:
                st.markdown("### 🗺️ Comparaison Heatmaps")

                # Recalculer stats après nettoyage
                masks_cleaned_dict = {name: mask for name, mask in zip(mask_names, st.session_state.val_cleaned)}
                stats_after_viz = pv.analyze_conflicts_qtre(
                    masks_cleaned_dict,
                    cellsize=cellsize_val,
                    threshold=conflict_threshold
                )

                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

                cmap = mcolors.LinearSegmentedColormap.from_list(
                    'qtre',
                    ['#1a1a1a', '#2a4a2a', '#4a6a2a', '#ffaa00', '#ff4400', '#ff0000']
                )

                # Avant
                im1 = ax1.imshow(st.session_state.val_qtre_stats['heatmap'], cmap=cmap, vmin=0, vmax=8)
                ax1.set_title(f"Avant — {st.session_state.val_qtre_stats['critical_blocs']} blocs critiques")
                ax1.axis('off')
                plt.colorbar(im1, ax=ax1, fraction=0.046)

                # Après
                im2 = ax2.imshow(stats_after_viz['heatmap'], cmap=cmap, vmin=0, vmax=8)
                ax2.set_title(f"Après — {stats_after_viz['critical_blocs']} blocs critiques")
                ax2.axis('off')
                plt.colorbar(im2, ax=ax2, fraction=0.046)

                st.pyplot(fig)
                plt.close()

            # Export
            if "val_cleaned" in st.session_state:
                st.markdown("**Export masks corrigés**")

                # Dossier par défaut
                default_dir = st.session_state.get("masks_dir_v2", "generated/validation")
                if default_dir and Path(default_dir).exists():
                    default_export = str(Path(default_dir).parent / "masks_noconflict")
                else:
                    default_export = "generated/validation/masks_noconflict"

                export_dir_clean = st.text_input(
                    "Dossier de destination",
                    value=default_export,
                    help="Chemin où sauvegarder les masks corrigés par ordre",
                    key="export_dir_clean"
                )

                if st.button("Exporter masks corrigés", type="primary"):
                    try:
                        output_path = Path(export_dir_clean)
                        output_path.mkdir(parents=True, exist_ok=True)

                        # Utiliser val_cleaned_paths si disponible (synchronisé avec val_cleaned)
                        # Sinon fallback sur val_paths (compatibilité ancien code)
                        paths_to_use = st.session_state.get('val_cleaned_paths', st.session_state.val_paths)

                        # Vérifier cohérence longueur
                        if len(st.session_state.val_cleaned) != len(paths_to_use):
                            st.error(f"[ERR] Incohérence : {len(st.session_state.val_cleaned)} masks mais {len(paths_to_use)} chemins")
                            raise ValueError(f"Nombre de masks ({len(st.session_state.val_cleaned)}) != nombre de paths ({len(paths_to_use)})")

                        saved = pv.export_masks_png(
                            st.session_state.val_cleaned,
                            paths_to_use,
                            output_path,
                            suffix='_noconflict'
                        )

                        if saved:
                            st.success(f"[OK] {len(saved)} masks exportés dans `{output_path.absolute()}`")

                            # Afficher liste
                            with st.expander("📂 Fichiers exportés"):
                                for path in saved:
                                    st.text(f"• {Path(path).name}")

                    except Exception as e:
                        st.error(f"[ERR] Erreur export : {e}")

        # ───────────────────────────────────────────────────────────────────
        # C — Masks erreur Reforger
        # ───────────────────────────────────────────────────────────────────


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
    <p><strong>Map Generator Pro v5.1</strong> — Pipeline Textures Terrain v2.1</p>
    <p>🌿 Pipeline terrain 13 masks | Priority-flood | Curvature Z&T | Auto-calibration | Cache terrain</p>
    <p>© 2026 | Production-Ready</p>
</div>
""", unsafe_allow_html=True)
