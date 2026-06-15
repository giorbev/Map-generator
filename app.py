# -*- coding: utf-8 -*-
"""
Map Generator Pro v4.0 — Streamlit Application
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
from texture_layer_generator import TextureLayerGenerator
import pipeline_validation as pv

# ============================================================================
# CONFIGURATION STREAMLIT
# ============================================================================

st.set_page_config(
    page_title="Map Generator Pro v4.0",
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
            tpi_local=terrain_data['tpi_local'],
            tpi_macro=terrain_data['tpi_macro'],
            flow=terrain_data['flow'],
            distance_cote=terrain_data['distance_cote'],
            aspect=terrain_data['aspect'],
            roughness=terrain_data['roughness'],
            # Métadonnées en pickle séparé
        )

        # Sauvegarder métadonnées JSON
        import json
        meta_file = cache_dir / "terrain_meta.json"
        meta_file.write_text(json.dumps({
            'meta': terrain_data['meta'],
            'cellsize': terrain_data['cellsize'],
            'params': terrain_data['params'],
            'computation_time': terrain_data['computation_time'],
            'timestamp': terrain_data['timestamp'],
            'heightmap_path': terrain_data['heightmap_path']
        }, indent=2), encoding='utf-8')

        return True
    except Exception as e:
        return False


def load_terrain_data_cache(project_path, heightmap_path):
    """Charge terrain_data depuis cache NPZ si valide."""
    try:
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

        # Charger arrays
        npz = np.load(cache_file)

        # Charger métadonnées
        import json
        meta_data = json.loads(meta_file.read_text(encoding='utf-8'))

        # Reconstruire terrain_data
        terrain_data = {
            'heightmap': npz['heightmap'],
            'heightmap_smooth': npz['heightmap_smooth'],
            'slope': npz['slope'],
            'curvature': npz['curvature'],
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


def _build_tmat_legend_image(rgb_array: np.ndarray, rows: list) -> bytes:
    """Compose image TMAT + panneau légende latéral -> bytes PNG."""
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

# ── Section Masques Instant Terra ────────────────────────────────────────────
st.sidebar.markdown("###  Masques Instant Terra")
st.sidebar.caption("Slope calculé automatiquement depuis heightmap")
_IT_ROLES = {
    "curvature": ("Curvature crêtes/creux", ["curvature.raw", "curvature.png"]),
    "sediment":  ("Sediment (dépôts)",  ["sediment.png"]),
}
_it_proj_dir = Path(st.session_state.current_project_path) \
               if st.session_state.current_project_path else None
for _it_role, (_it_label, _it_fnames) in _IT_ROLES.items():
    # Chercher le premier fichier existant
    _it_dst = None
    _it_fname_found = None
    if _it_proj_dir:
        for _fname in (_it_fnames if isinstance(_it_fnames, list) else [_it_fnames]):
            _candidate = _it_proj_dir / "sources" / _fname
            if _candidate.exists():
                _it_dst = _candidate
                _it_fname_found = _fname
                break
        # Si aucun trouvé, utiliser le premier comme destination par défaut
        if not _it_dst:
            _it_dst = _it_proj_dir / "sources" / (_it_fnames[0] if isinstance(_it_fnames, list) else _it_fnames)

    _it_ok  = bool(_it_dst and _it_dst.exists())
    st.sidebar.markdown(
        f"{'[OK]' if _it_ok else '[WARN]'} **{_it_label}**"
        + (f"  \n`{_it_fname_found or 'absent'}`" if _it_ok else "")
    )
    _it_up = st.sidebar.file_uploader(
        _it_label, type=["raw", "png", "tif", "tiff"],
        key=f"it_upload_{_it_role}", label_visibility="collapsed",
    )
    if _it_up and _it_dst:
        _sig = f"{_it_up.name}_{_it_up.size}"
        if _sig != st.session_state.get(f"it_upload_done_{_it_role}"):
            _it_dst.parent.mkdir(parents=True, exist_ok=True)
            _it_dst.write_bytes(_it_up.read())
            st.session_state[f"it_path_{_it_role}"] = str(_it_dst)
            st.session_state[f"it_upload_done_{_it_role}"] = _sig
            save_project()
            st.rerun()
    elif _it_ok and not st.session_state.get(f"it_path_{_it_role}"):
        st.session_state[f"it_path_{_it_role}"] = str(_it_dst)

if st.sidebar.button(" Charger/Recharger masques IT", key="btn_reload_it"):
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
                st.sidebar.success(f"[OK] {len(_loaded)} masque(s) IT chargé(s)")
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
st.sidebar.markdown("###  Projet Reforger")

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
        st.sidebar.success(f"[OK] {len(st.session_state.terr_materials)} matériaux chargés")
        with st.sidebar.expander("Matériaux disponibles"):
            for i, m in enumerate(st.session_state.terr_materials):
                st.caption(f"[{i:2d}] {m}")
    else:
        st.sidebar.warning("Aucun .terr trouvé dans ce dossier.")
elif terr_path_input:
    st.sidebar.error("Dossier introuvable.")

st.sidebar.divider()

# ── Section Données Reforger ─────────────────────────────────────────────────
st.sidebar.markdown("###  Données Reforger")

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
    if st.button("[INFO] Analyser", key="btn_parse_reforger"):
        if reforger_raw.strip():
            try:
                data = parse_reforger_world_data(reforger_raw)
                st.session_state.reforger_data = data
                st.success("[OK] Données importées")
            except ValueError as e:
                st.error(f"[ERR] {e}")
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

# ── Bibliothèque de matériaux ────────────────────────────────────────────────
st.sidebar.divider()
with st.sidebar.expander("📚 Bibliothèque de matériaux", expanded=False):
    import pandas as _pd_lib

    _lib_state = st.session_state.get("material_library")
    _proj_path = st.session_state.get("current_project_path")

    if _lib_state is None:
        st.info("Ouvrez un projet pour accéder à la bibliothèque.")
    else:
        _lib_tab_v, _lib_tab_c = st.tabs(["🌐 Vanilla", " Custom projet"])

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
                _col_vm.markdown(f'`{_vm["stem"]}` -> **{_vm["role"]}** — {_vm["label"]}')
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
                    col_cm.markdown(f'`{_cm["stem"]}` -> **{_cm["role"]}** — {_cm["label"]}')
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

st.markdown('<h1 class="main-header"> Map Generator Pro v4.0</h1>', unsafe_allow_html=True)

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
    tab_terrain, tab_gen, tab_validation = st.tabs([
        " Terrain",
        " Génération",
        "[INFO] Validation Masks",
    ])
    
    # ========================================================================
    # ONGLET TERRAIN — sous-onglets : Hypsométrique / NatureMap / Analyse
    # ========================================================================

    with tab_terrain:
        _t_hypso, _t_analyse, _t_signaux = st.tabs([
            " Hypsométrique", "📈 Analyse", "🗺️ Signaux Terrain"
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

    with _t_analyse:
        # Onglet unique : toutes les analyses directement ici
        # (Curvature et Slope Auto obsolètes → remplacés par auto-calibration pipeline_v2)

        # ── ANALYSE COMPLÈTE TERRAIN ──────────────────────────────────────
        if True:  # Garde l'indentation
            st.markdown("### 📈 Analyse Complète Terrain")

            base_map = st.session_state.base_map

            # ══════════════════════════════════════════════════════════════
            # NOUVELLE SECTION : ANALYSE TERRAIN DEPUIS HEIGHTMAP
            # ══════════════════════════════════════════════════════════════

            st.markdown("#### [INFO] Statistiques Terrain")
            st.caption("Statistiques calculées depuis terrain_data (auto-calibration)")

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

                # ── SECTION 3 : STATISTIQUES SIGNAUX ──────────────────────
                st.markdown("#### 📊 Statistiques Signaux Terrain")

                from terrain_analysis import get_terrain_stats
                stats = get_terrain_stats(terrain_data)

                # Tableau récapitulatif
                import pandas as pd
                stats_rows = []
                for signal_name, stat in stats.items():
                    stats_rows.append({
                        'Signal': signal_name,
                        'Min': f"{stat['min']:.2f}",
                        'Max': f"{stat['max']:.2f}",
                        'Moyenne': f"{stat['mean']:.2f}",
                        'Écart-type': f"{stat['std']:.2f}"
                    })

                st.dataframe(stats_rows, use_container_width=True, hide_index=True)

                st.divider()

                # ── SECTION 4 : RECOMMANDATION ────────────────────────────
                st.markdown("#### 💡 Recommandation Pipeline")

                st.success("**Pipeline V2 : 13 masques** recommandés")

                st.info(
                    "✓ Auto-calibration activée — seuils optimaux calculés  \n"
                    "✓ TPI local/macro pour relief fin  \n"
                    "✓ Flow accumulation pour rivières/talwegs  \n"
                    "✓ Distance côtière pour transitions mer-terre"
                )

                # Warnings selon terrain
                slope_land = slope[land_mask]
                slope_mean = float(slope_land.mean())
                slope_max = float(slope_land.max())

                if slope_mean > 15:
                    st.warning(f"⚠️ Terrain très pentu (pente moyenne {slope_mean:.1f}°) → prévoir masques Debris/Rock importants")
                if denivele < 50:
                    st.warning(f"⚠️ Faible dénivelé ({denivele:.0f}m) → zones altitudinales réduites")
                if land_pct < 30:
                    st.info(f"ℹ️ Terrain majoritairement aquatique ({sea_pct:.0f}% mer) → focus transitions côtières")

            st.divider()

    # ── SIGNAUX TERRAIN : Visualisation des dérivés terrain ──────────────
    with _t_signaux:
        st.markdown("### 🗺️ Signaux Terrain — Dérivés morphologiques")
        st.caption("Visualisation des signaux calculés depuis heightmap")

        terrain_data = st.session_state.get('terrain_data')

        if not terrain_data:
            st.warning("⚠️ Chargez une heightmap depuis la sidebar")
        else:
            # Infos générales
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.metric("Résolution", f"{terrain_data['meta']['ncols']}×{terrain_data['meta']['nrows']} px")
            with col_info2:
                st.metric("Cellsize", f"{terrain_data['cellsize']} m/px")
            with col_info3:
                st.metric("Temps calcul", f"{terrain_data['computation_time']:.1f}s")

            st.divider()

            # Sélection signal
            signal_choice = st.selectbox(
                "Signal à visualiser",
                ["heightmap", "slope", "curvature", "tpi_local", "tpi_macro",
                 "flow", "distance_cote", "aspect", "roughness"]
            )

            # Colormap par signal
            colormap_map = {
                "heightmap": "terrain",
                "slope": "hot",
                "curvature": "RdBu_r",
                "tpi_local": "RdBu_r",
                "tpi_macro": "RdBu_r",
                "flow": "Blues",
                "distance_cote": "viridis",
                "aspect": "hsv",
                "roughness": "gray"
            }

            if st.button("🎨 Générer Carte", type="primary"):
                with st.spinner(f"Génération {signal_choice}..."):
                    try:
                        import matplotlib.pyplot as plt
                        import numpy as np
                        from io import BytesIO

                        signal_data = terrain_data[signal_choice]

                        fig, ax = plt.subplots(figsize=(12, 10))

                        # Masquer eau pour heightmap/slope
                        if signal_choice in ["heightmap", "slope"]:
                            heightmap = terrain_data['heightmap']
                            water_mask = heightmap <= 0
                            display_data = np.ma.masked_where(water_mask, signal_data)
                        else:
                            display_data = signal_data

                        im = ax.imshow(display_data, cmap=colormap_map[signal_choice], interpolation='bilinear')
                        ax.set_title(f"{signal_choice.upper()}", fontsize=16, fontweight='bold')
                        ax.axis('off')

                        cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
                        units = {"heightmap": "m", "slope": "°", "curvature": "norm", "tpi_local": "norm",
                                "tpi_macro": "norm", "flow": "norm", "distance_cote": "m", "aspect": "°", "roughness": "norm"}
                        cbar.set_label(units.get(signal_choice, ""), rotation=270, labelpad=20)

                        plt.tight_layout()

                        buf = BytesIO()
                        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
                        buf.seek(0)
                        st.session_state[f'signal_viz_{signal_choice}'] = buf.getvalue()
                        plt.close()

                        st.success(f"[OK] Carte {signal_choice} générée")

                    except Exception as e:
                        st.error(f"[ERR] {e}")
                        import traceback
                        st.code(traceback.format_exc())

            # Afficher carte
            if f'signal_viz_{signal_choice}' in st.session_state:
                st.divider()
                st.image(st.session_state[f'signal_viz_{signal_choice}'], use_column_width=True)

                # Stats
                st.divider()
                st.markdown("**📊 Statistiques**")

                from terrain_analysis import get_terrain_stats
                stats = get_terrain_stats(terrain_data)

                if signal_choice in stats:
                    stat = stats[signal_choice]
                    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                    with col_s1:
                        st.metric("Min", f"{stat['min']:.2f}")
                    with col_s2:
                        st.metric("Max", f"{stat['max']:.2f}")
                    with col_s3:
                        st.metric("Moyenne", f"{stat['mean']:.2f}")
                    with col_s4:
                        st.metric("Écart-type", f"{stat['std']:.2f}")

                    st.caption(f"P05: {stat['p05']:.2f} | P95: {stat['p95']:.2f}")

            # Histogramme
            st.divider()
            if st.checkbox("📈 Afficher histogramme"):
                try:
                    import matplotlib.pyplot as plt
                    import numpy as np
                    from io import BytesIO

                    signal_data = terrain_data[signal_choice]

                    if signal_choice in ["heightmap", "slope"]:
                        heightmap = terrain_data['heightmap']
                        water_mask = heightmap > 0
                        data_clean = signal_data[water_mask]
                    else:
                        data_clean = signal_data.ravel()

                    fig, ax = plt.subplots(figsize=(10, 4))
                    ax.hist(data_clean, bins=100, color='steelblue', alpha=0.7, edgecolor='black')
                    ax.set_xlabel(signal_choice)
                    ax.set_ylabel('Fréquence')
                    ax.set_title(f'Distribution {signal_choice}')
                    ax.grid(True, alpha=0.3)
                    plt.tight_layout()

                    buf = BytesIO()
                    plt.savefig(buf, format='png', dpi=100)
                    buf.seek(0)
                    st.image(buf.getvalue(), use_column_width=True)
                    plt.close()

                except Exception as e:
                    st.error(f"[ERR] {e}")

    # ========================================================================
    # ONGLET GÉNÉRATION — Nouvelle structure: Textures / Végétation / Post-Traitement
    # ========================================================================

    with tab_gen:
        _g_textures, _g_vegetation, _g_post = st.tabs([
            " Textures Terrain",
            "🌲 Végétation",
            "🛠️ Post-Traitement"
        ])

    # ══════════════════════════════════════════════════════════════════════════════
    # TEXTURES TERRAIN — Aperçu + Biome + Génération Masques
    # ══════════════════════════════════════════════════════════════════════════════

    with _g_textures:
        st.markdown("### 🎨 Génération Masques Terrain — Pipeline V2")
        st.caption("Génère 13 masks PNG 16-bit avec auto-calibration terrain")

        st.divider()

        # ── Auto-calibration depuis heightmap ──────────────────────────────
        heightmap_path = st.session_state.get('heightmap_path')

        # Récupérer valeurs auto-calibrées depuis terrain_data
        terrain_data = st.session_state.get('terrain_data')
        if heightmap_path and 'params_auto_v2' not in st.session_state:
            if terrain_data:
                # Utiliser params auto-calibrés déjà calculés (OPTIMISÉ)
                st.session_state['params_auto_v2'] = terrain_data['params']
            else:
                # Fallback : calcul si terrain_data absent (ne devrait pas arriver)
                try:
                    from pipeline_v2 import load_asc, calculate_slope, auto_calibrate
                    import numpy as np

                    with st.spinner("⚙️ Auto-calibration depuis heightmap..."):
                        heightmap, meta = load_asc(str(heightmap_path))
                        cellsize = meta['cellsize']
                        slope = calculate_slope(heightmap, cellsize)

                        # Flow factice pour éviter calcul long D8
                        flow = np.ones_like(heightmap) * 0.5

                    # Paramètres par défaut pour auto-calibration
                    params_default = {
                        "coastal_distance_max_m": 60.0,
                        "coastal_alt_max_m": None,
                        "grass_low_max_m": None,
                        "grass_mid_max_m": None,
                        "grass_high_max_m": None,
                        "debris_min_deg": None,
                        "rock_min_deg": None,
                        "tpi_local_radius_m": 100.0,
                        "tpi_macro_radius_m": 500.0,
                        "flow_threshold": None,
                        "feather_coastal_m": 20.0,
                        "feather_grass_m": 20.0,
                        "feather_rock_m": 20.0,
                        "feather_debris_m": 25.0,
                        "feather_forest_m": 40.0,
                        "feather_river_m": 15.0,
                    }

                    params_auto = auto_calibrate(heightmap, slope, flow, params_default)
                    st.session_state['params_auto_v2'] = params_auto
                    st.session_state['cellsize'] = cellsize
                    st.success("✓ Valeurs auto-calibrées depuis la heightmap")
                except Exception as e:
                    st.warning(f"⚠️ Impossible d'auto-calibrer : {e}")
                    st.session_state['params_auto_v2'] = {}

        # Récupérer valeurs auto ou utiliser défauts
        params_auto = st.session_state.get('params_auto_v2', {})

        # Afficher valeurs auto-calibrées
        if params_auto:
            col_info, col_reset = st.columns([4, 1])
            with col_info:
                st.info(
                    f"**📊 Valeurs auto-calibrées depuis heightmap :**  \n"
                    f"• Altitude côtière max : {params_auto.get('coastal_alt_max_m', 0):.1f} m  \n"
                    f"• Grass low max : {params_auto.get('grass_low_max_m', 0):.1f} m  \n"
                    f"• Grass mid max : {params_auto.get('grass_mid_max_m', 0):.1f} m  \n"
                    f"• Grass high max : {params_auto.get('grass_high_max_m', 0):.1f} m  \n"
                    f"• Pente érosion min : {params_auto.get('debris_min_deg', 0):.1f}°  \n"
                    f"• Pente roche min : {params_auto.get('rock_min_deg', 0):.1f}°  \n"
                    f"*(Sliders ajustables ci-dessous)*"
                )
            with col_reset:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔄 Recalculer", help="Recalculer les valeurs auto depuis la heightmap"):
                    if 'params_auto_v2' in st.session_state:
                        del st.session_state['params_auto_v2']
                    st.rerun()

        # ── Génération Pipeline V2 ─────────────────────────────────────────
        st.subheader("⚙️ Paramètres Pipeline V2")

        col1, col2 = st.columns(2)
        with col1:
            coastal_distance = st.slider(
                "Distance côtière (m)",
                20, 200,
                value=int(st.session_state.get('pipeline_v2_coastal_distance', 60)),
                key="pipeline_v2_coastal_distance"
            )
            debris_min = st.slider(
                "Pente érosion min (°)",
                5.0, 30.0,
                value=float(st.session_state.get('pipeline_v2_debris_min', params_auto.get('debris_min_deg', 18.0))),
                help="Valeur auto-calibrée depuis la heightmap (ajustable)",
                key="pipeline_v2_debris_min"
            )
            rock_min = st.slider(
                "Pente roche min (°)",
                15.0, 45.0,
                value=float(st.session_state.get('pipeline_v2_rock_min', params_auto.get('rock_min_deg', 28.0))),
                help="Valeur auto-calibrée depuis la heightmap (ajustable)",
                key="pipeline_v2_rock_min"
            )
            tpi_local = st.slider(
                "TPI local radius (m)",
                50, 300,
                value=int(st.session_state.get('pipeline_v2_tpi_local', 100)),
                key="pipeline_v2_tpi_local"
            )

        with col2:
            feather_coastal = st.slider(
                "Feather côtier (m)",
                5, 50,
                value=int(st.session_state.get('pipeline_v2_feather_coastal', 20)),
                key="pipeline_v2_feather_coastal"
            )
            feather_grass = st.slider(
                "Feather herbe (m)",
                5, 60,
                value=int(st.session_state.get('pipeline_v2_feather_grass', 20)),
                key="pipeline_v2_feather_grass"
            )
            feather_rock = st.slider(
                "Feather roche (m)",
                5, 40,
                value=int(st.session_state.get('pipeline_v2_feather_rock', 20)),
                key="pipeline_v2_feather_rock"
            )
            tpi_macro = st.slider(
                "TPI macro radius (m)",
                200, 1000,
                value=int(st.session_state.get('pipeline_v2_tpi_macro', 500)),
                key="pipeline_v2_tpi_macro"
            )

        # Avertissement temps de calcul
        st.warning(
            "⏱️ **Temps de calcul estimé** :  \n"
            "- Heightmap 2048x2048 : ~2-5 min  \n"
            "- Heightmap 4096x4096 : ~5-15 min  \n"
            "- Heightmap 8192x8192 : ~15-30 min  \n"
            "*(calcul flow accumulation D8 très long)*"
        )

        # Bouton lancement
        if st.button("🚀 Générer Masques Terrain (Pipeline V2 - 13 masques)", key="btn_generate_v2"):
            # Récupérer chemin heightmap depuis session_state
            heightmap_path = st.session_state.get('heightmap_path')
            project_path = st.session_state.get('current_project_path')

            if heightmap_path and project_path:
                # Dossier output avec timestamp
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_dir = Path(project_path) / "generated" / f"masks_{timestamp}"
                output_dir.mkdir(parents=True, exist_ok=True)

                # Paramètres pipeline
                params = {
                    "coastal_distance_max_m": coastal_distance,
                    "coastal_alt_max_m": None,
                    "grass_low_max_m": None,
                    "grass_mid_max_m": None,
                    "grass_high_max_m": None,
                    "debris_min_deg": debris_min,
                    "rock_min_deg": rock_min,
                    "tpi_local_radius_m": tpi_local,
                    "tpi_macro_radius_m": tpi_macro,
                    "flow_threshold": None,
                    "feather_coastal_m": feather_coastal,
                    "feather_grass_m": feather_grass,
                    "feather_rock_m": feather_rock,
                    "feather_debris_m": feather_rock,
                    "feather_forest_m": 40.0,
                    "feather_river_m": 15.0,
                }

                # Placeholder pour logs progressifs
                log_placeholder = st.empty()
                progress_bar = st.progress(0)

                try:
                    from pipeline_v2 import run_pipeline
                    import time as _time

                    log_placeholder.info("🔄 Démarrage Pipeline V2...")
                    progress_bar.progress(5)

                    # Récupérer terrain_data pré-calculé (évite recalcul)
                    terrain_data = st.session_state.get('terrain_data')

                    _start = _time.time()
                    results = run_pipeline(
                        str(heightmap_path),
                        str(output_dir),
                        params,
                        terrain_data=terrain_data  # ZÉRO recalcul si déjà calculé
                    )
                    _elapsed = _time.time() - _start

                    progress_bar.progress(100)
                    log_placeholder.empty()

                    # Sauvegarder résultats en session_state
                    st.session_state['pipeline_v2_results'] = results
                    st.session_state['pipeline_v2_masks_dir'] = str(output_dir)
                    st.session_state['masks_dir_v2'] = str(output_dir)  # Alias pour TAB 3

                    # Sauvegarder dans project.json
                    auto_save()

                    # Afficher résultats
                    st.success(f"[OK] 13 masks générés : {output_dir}")
                    st.success(f"[OK] Verdict QTRE : {results['qtre_verdict']}")
                    st.info(f"💡 Texture de base recommandée : **{results['base_texture']}**")
                    st.info(f"⏱️ Temps total : {_elapsed:.1f}s")

                    # Log détaillé dans expander
                    with st.expander("📊 Détails génération"):
                        st.json(results['params'])

                except Exception as e:
                    progress_bar.empty()
                    log_placeholder.empty()
                    st.error(f"Erreur génération : {e}")
                    import traceback
                    st.code(traceback.format_exc())
            else:
                st.error("❌ Heightmap ou projet non défini. Chargez d'abord une heightmap dans la sidebar.")

        st.divider()

        # ══════════════════════════════════════════════════════════════════════
        # ANCIEN CODE SUPPRIMÉ (Aperçu + Pipeline Complet)
        # -> Remplacé par nouveau système: biome_library + pipeline simple
        # ══════════════════════════════════════════════════════════════════════

        # [~280 lignes supprimées: ancien aperçu texture + génération masques complets PNG]
        # Le nouveau workflow est plus simple:
        # 1. Choisir biome (ci-dessus)
        # 2. Clic "🚀 Générer Masques Terrain" -> 7 PNG + texture_mapping.json
        # 3. Import direct dans Workbench

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
                    0.0, 0.5, 0.15, 0.01,
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

                col_e1, col_e2 = st.columns(2)

                with col_e1:
                    # Export PNG
                    if st.button("📥 Exporter PNG"):
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
                    # Téléchargement direct
                    from io import BytesIO
                    import cv2

                    success, buffer = cv2.imencode('.png', cv2.cvtColor(st.session_state.veg_rgb, cv2.COLOR_RGB2BGR))
                    if success:
                        st.download_button(
                            "⬇️ Télécharger PNG",
                            data=buffer.tobytes(),
                            file_name="vegetation_map.png",
                            mime="image/png"
                        )

    # ══════════════════════════════════════════════════════════════════════════════
    # POST-TRAITEMENT — Fusion masks pipeline_v2 + mappeur
    # ══════════════════════════════════════════════════════════════════════════════

    with _g_post:
        st.markdown("### 🔀 Post-Traitement — Fusion Masks")
        st.caption("Fusionne masks pipeline_v2 et masks mappeur avec gestion priorités")

        from post_processing import TEXTURE_CATEGORIES

        # ═══════════════════════════════════════════════════════════════════
        # SECTION A : CHARGEMENT MASKS MAPPEUR
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("#### 📂 A — Chargement Masks Mappeur")

        uploaded_files = st.file_uploader(
            "Upload masks Reforger exportés (PNG 16-bit)",
            accept_multiple_files=True,
            type=['png'],
            key="post_upload_mappeur"
        )

        if uploaded_files:
            st.markdown("#### 🏷️ Catégorisation des Masks")
            st.caption("Définir la priorité de fusion pour chaque mask")

            categories = st.session_state.get('post_categories', {})
            mappeur_masks = {}

            for f in uploaded_files:
                col1, col2, col3 = st.columns([2.5, 3, 0.8], gap="small")

                with col1:
                    # Utiliser markdown avec padding pour aligner verticalement
                    st.markdown(f"**{f.name}**")

                with col2:
                    cat = st.selectbox(
                        "Catégorie",
                        options=list(TEXTURE_CATEGORIES.keys()),
                        format_func=lambda x: TEXTURE_CATEGORIES[x],
                        key=f"cat_{f.name}",
                        label_visibility="collapsed",
                        index=list(TEXTURE_CATEGORIES.keys()).index(
                            categories.get(f.name, "mappeur")
                        )
                    )
                    categories[f.name] = cat

                with col3:
                    # Ajouter espacement vertical pour aligner checkbox
                    st.write("")  # Spacer
                    inclure = st.checkbox("✓", value=True, key=f"inc_{f.name}", label_visibility="collapsed")
                    if not inclure:
                        categories[f.name] = "ignorer"

                # Charger mask
                if categories[f.name] != "ignorer":
                    arr = np.frombuffer(f.read(), np.uint8)
                    mask = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                    if mask is not None and mask.ndim == 2:
                        mappeur_masks[f.name] = mask

            # Sauvegarder dans session_state
            st.session_state['post_mappeur_masks'] = mappeur_masks
            st.session_state['post_categories'] = categories

            st.success(f"✓ {len(mappeur_masks)} masks mappeur chargés")

        # ═══════════════════════════════════════════════════════════════════
        # SECTION B : PARAMÈTRES FUSION
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("#### ⚙️ B — Paramètres Fusion")

        col1, col2 = st.columns(2)
        with col1:
            urban_radius = st.slider(
                "Dilatation zone urbaine (m)",
                0, 50, 10,
                help="Élargit légèrement les zones urbaines pour éviter l'herbe en bordure"
            )
        with col2:
            conflict_threshold = st.slider(
                "Seuil présence texture",
                0.03, 0.20, 0.05,
                step=0.01,
                format="%.2f"
            )

        # ═══════════════════════════════════════════════════════════════════
        # SECTION B2 : POLYGONES MANUELS (PHASE 2) — DÉSACTIVÉE
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("#### 🎨 B2 — Zones Manuelles (Phase 2)")
        st.warning(
            "⚠️ **Phase 2 temporairement désactivée**  \n\n"
            "**Raison** : Incompatibilité `streamlit-drawable-canvas` avec Streamlit 1.57  \n\n"
            "**Alternative** : Utilisez QGIS ou Instant Terra pour créer des masques de zones manuelles, "
            "puis uploadez-les comme masks mappeur (catégorie 'mappeur' pour exclure, 'sol_naturel' pour protéger)  \n\n"
            "**Phase 1 disponible** : Fusion automatique masks pipeline_v2 + mappeur avec zones urbaines"
        )

        # Phase 2 désactivée - ne rien faire
        if False:  # Désactivé
            # Créer image de fond (hillshade)
            terrain_data = st.session_state.get('terrain_data')
            if terrain_data is not None:
                heightmap = terrain_data['heightmap']
                cellsize = terrain_data['cellsize']
    
                # Hillshade simple
                gy, gx = np.gradient(heightmap, cellsize)
                shade = np.cos(np.radians(315)) * np.cos(np.arctan(np.sqrt(gx**2+gy**2))) + \
                        np.sin(np.radians(45)) * np.sin(np.arctan(np.sqrt(gx**2+gy**2)))
                shade = np.clip(shade, 0.2, 1.0)
                bg_image = (shade * 255).astype(np.uint8)
                bg_image_rgb = np.stack([bg_image]*3, axis=-1)
    
                # Redimensionner pour canvas (max 800px)
                H, W = heightmap.shape
                max_dim = 800
                scale = min(max_dim/W, max_dim/H)
                display_w = int(W * scale)
                display_h = int(H * scale)
    
                bg_resized = cv2.resize(bg_image_rgb, (display_w, display_h))
                bg_pil = Image.fromarray(bg_resized)
    
                # Stocker scale pour utilisation dans fusion
                st.session_state['poly_display_scale'] = scale
            else:
                display_w, display_h = 800, 600
                scale = 1.0
                bg_pil = None
                st.session_state['poly_display_scale'] = 1.0
    
            # Mode polygone
            col1, col2 = st.columns([1, 2])
            with col1:
                poly_mode = st.radio(
                    "Mode",
                    options=["proteger", "exclure"],
                    format_func=lambda x: {
                        "proteger": "🟢 PROTÉGER",
                        "exclure": "🔴 EXCLURE"
                    }[x],
                    horizontal=True
                )
            with col2:
                if poly_mode == "proteger":
                    st.info("**PROTÉGER** : zone naturelle mal détectée → forcer pipeline_v2")
                else:
                    st.info("**EXCLURE** : zone urbaine manquante → effacer pipeline_v2")
    
            # Canvas de dessin
            canvas_result = st_canvas(
                fill_color="rgba(0, 255, 0, 0.2)" if poly_mode == "proteger"
                           else "rgba(255, 0, 0, 0.2)",
                stroke_width=2,
                stroke_color="#00FF00" if poly_mode == "proteger" else "#FF0000",
                background_image=bg_pil,
                drawing_mode="polygon",
                height=display_h,
                width=display_w,
                key=f"canvas_{poly_mode}",
            )
    
            # Boutons gestion polygones
            col1, col2, col3 = st.columns(3)
    
            with col1:
                if st.button("➕ Ajouter polygone"):
                    if canvas_result.json_data is not None:
                        objects = canvas_result.json_data.get("objects", [])
                        for obj in objects:
                            if obj.get("type") == "path":
                                # Extraire points depuis path SVG
                                points = []
                                for cmd in obj.get("path", []):
                                    if cmd[0] in ["M", "L"]:
                                        points.append([cmd[1], cmd[2]])
    
                                if len(points) >= 3:
                                    polygons.append({
                                        "id": len(polygons) + 1,
                                        "mode": poly_mode,
                                        "points": points,
                                        "active": True,
                                        "label": f"Zone {len(polygons)+1} ({poly_mode})"
                                    })
    
                        st.session_state['polygons'] = polygons
                        if project_dir:
                            save_polygons(polygons, project_dir)
                        st.success(f"{len(polygons)} polygone(s) sauvegardé(s)")
    
            with col2:
                if st.button("🗑️ Effacer dernier"):
                    if polygons:
                        polygons.pop()
                        st.session_state['polygons'] = polygons
                        if project_dir:
                            save_polygons(polygons, project_dir)
                        st.rerun()
    
            with col3:
                if st.button("❌ Effacer tout"):
                    polygons = []
                    st.session_state['polygons'] = polygons
                    if project_dir:
                        save_polygons(polygons, project_dir)
                    st.rerun()
    
            # Afficher liste polygones actifs
            if polygons:
                st.markdown(f"**{len(polygons)} zone(s) définie(s)**")
                for i, poly in enumerate(polygons):
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.text(poly.get('label', f"Zone {i+1}"))
                    with col2:
                        color = "green" if poly['mode'] == 'proteger' else "red"
                        mode_text = 'PROTÉGER' if poly['mode'] == 'proteger' else 'EXCLURE'
                        st.markdown(f":{color}[{mode_text}]")
                    with col3:
                        if st.button("✗", key=f"del_poly_{i}"):
                            polygons.pop(i)
                            st.session_state['polygons'] = polygons
                            if project_dir:
                                save_polygons(polygons, project_dir)
                            st.rerun()
        else:
            # Canvas pas disponible → afficher polygones existants en lecture seule
            if polygons:
                st.info(f"ℹ️ {len(polygons)} zone(s) sauvegardée(s)")
                st.caption("Installez `streamlit-drawable-canvas` et redémarrez pour éditer")
                for i, poly in enumerate(polygons):
                    col1, col2 = st.columns([3, 2])
                    with col1:
                        st.text(poly.get('label', f"Zone {i+1}"))
                    with col2:
                        color = "green" if poly['mode'] == 'proteger' else "red"
                        mode_text = 'PROTÉGER' if poly['mode'] == 'proteger' else 'EXCLURE'
                        st.markdown(f":{color}[{mode_text}]")

        # ═══════════════════════════════════════════════════════════════════
        # SECTION C : FUSION ET EXPORT
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("#### 🚀 C — Fusion et Export")

        if not st.session_state.get('post_mappeur_masks'):
            st.info("⬆️ Uploadez d'abord les masks mappeur ci-dessus")
        else:
            if st.button("🔄 Générer Masks Finaux", type="primary"):

                # Vérifier pipeline_v2
                masks_dir_v2 = st.session_state.get('masks_dir_v2')
                terrain_data = st.session_state.get('terrain_data')

                if not masks_dir_v2:
                    st.error("❌ Lancez d'abord le pipeline V2 (onglet Textures ci-dessus)")
                    st.stop()

                with st.spinner("⏳ Fusion en cours..."):
                    from post_processing import (
                        generate_urban_zone_mask,
                        merge_masks,
                        apply_qtre_and_export
                    )

                    # ── Charger masks pipeline_v2 ──
                    v2_masks = {}
                    masks_dir = Path(masks_dir_v2)
                    if masks_dir.exists():
                        for png in masks_dir.glob("*.png"):
                            arr = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
                            if arr is not None:
                                v2_masks[png.stem] = arr.astype(np.float32) / 65535.0

                    if not v2_masks:
                        st.error(f"❌ Aucun mask trouvé dans {masks_dir_v2}")
                        st.stop()

                    # ── Récupérer résolution cible ──
                    shape = list(v2_masks.values())[0].shape
                    cellsize = terrain_data['cellsize'] if terrain_data else 4.0

                    # ── Redimensionner masks mappeur à la résolution pipeline_v2 ──
                    mappeur_masks_resized = {}
                    for fname, mask in st.session_state['post_mappeur_masks'].items():
                        if mask.shape != shape:
                            # Redimensionner (INTER_AREA pour downscale, INTER_LINEAR pour upscale)
                            interp = cv2.INTER_AREA if mask.shape[0] > shape[0] else cv2.INTER_LINEAR
                            mask_resized = cv2.resize(mask, (shape[1], shape[0]), interpolation=interp)
                            mappeur_masks_resized[fname] = mask_resized
                        else:
                            mappeur_masks_resized[fname] = mask

                    # ── Générer zone urbaine ──
                    urbain_masks = {
                        fname: mask
                        for fname, mask in mappeur_masks_resized.items()
                        if st.session_state['post_categories'].get(fname) == "mappeur"
                    }

                    urban_zone = generate_urban_zone_mask(
                        urbain_masks, shape, urban_radius, cellsize, conflict_threshold
                    )

                    # ── Appliquer polygones manuels (Phase 2) — DÉSACTIVÉ ──
                    # polygons = st.session_state.get('polygons', [])
                    # if polygons:
                    #     display_scale = st.session_state.get('poly_display_scale', 1.0)
                    #     urban_zone = apply_manual_polygons(
                    #         urban_zone=urban_zone,
                    #         polygons=polygons,
                    #         shape=shape,
                    #         display_scale=display_scale
                    #     )
                    #     st.info(f"✓ {len(polygons)} zone(s) manuelle(s) appliquée(s)")

                    # ── Fusion ──
                    final_masks = merge_masks(
                        v2_masks=v2_masks,
                        mappeur_masks=mappeur_masks_resized,
                        categories=st.session_state['post_categories'],
                        urban_zone=urban_zone,
                        cellsize=cellsize,
                        threshold=conflict_threshold
                    )

                    # ── Export ──
                    project_path = st.session_state.get('current_project_path')
                    if project_path:
                        output_dir = Path(project_path) / "generated" / "masks_fusion"
                    else:
                        output_dir = Path("generated") / "masks_fusion"

                    qtre_report = apply_qtre_and_export(
                        final_masks, str(output_dir), cellsize, conflict_threshold
                    )

                    st.session_state['post_final_masks_dir'] = str(output_dir)
                    st.session_state['post_qtre_report'] = qtre_report

                # ── Afficher résultats ──
                if 'post_qtre_report' in st.session_state:
                    qtre_report = st.session_state['post_qtre_report']

                    st.markdown("#### ✅ Résultats Fusion")

                    col1, col2, col3 = st.columns(3)
                    col1.metric("QTRE OK", f"{qtre_report['ok_pct']:.1f}%", help="Blocs avec ≤3 textures")
                    col2.metric("Limite", f"{qtre_report['limit_pct']:.1f}%", help="Blocs avec 4-5 textures")
                    col3.metric("Critique", f"{qtre_report['critical_pct']:.2f}%", help="Blocs avec ≥6 textures")

                    # Verdict
                    if qtre_report['verdict'] == "OK":
                        st.success(f"✅ Verdict : {qtre_report['verdict']} — Terrain compatible QTRE")
                    else:
                        st.warning(f"⚠️ Verdict : {qtre_report['verdict']} — Vérifier zones critiques")

                    st.info(f"📁 {len(qtre_report['exported'])} masks exportés → `{output_dir}`")

                    # Liste fichiers exportés
                    with st.expander("📂 Fichiers exportés"):
                        for fpath in qtre_report['exported']:
                            st.text(f"• {Path(fpath).name}")

                    # Sauvegarder chemin dans project.json
                    if st.session_state.get('current_project_path'):
                        st.session_state.setdefault('current_project', {})
                        st.session_state.current_project.setdefault('post_processing', {})
                        st.session_state.current_project['post_processing']['last_output'] = str(output_dir)
                        st.session_state.current_project['post_processing']['categories'] = st.session_state['post_categories']
                        save_project()
                        st.caption("✓ Configuration sauvegardée dans project.json")

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 2 FUTURE
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("#### 🚧 Phase 2 (À venir)")
        st.caption("• Polygones manuels GeoJSON")
        st.caption("• Peinture directe dans zones définies")
        st.caption("• Import/Export zones personnalisées")

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
                "Exemple : fusionner 3 masks `grass_dry` en un seul."
            )

            if len(st.session_state.val_masks) >= 2:
                col_b1, col_b2 = st.columns([1, 1])

                with col_b1:
                    assembly_mode = st.radio(
                        "Mode assemblage",
                        ["max", "add", "homogeneous", "priority"],
                        index=2,
                        help="max=valeur max, add=somme, homogeneous=moyenne, priority=ordre 01->XX"
                    )

                    if st.button("Assembler masks", key="btn_assemble_util"):
                        with st.spinner("Assemblage..."):
                            try:
                                ordered_indices = pv._compute_ordered_indices(st.session_state.val_paths) if assembly_mode == "priority" else None

                                assembled = pv.assemble_masks(
                                    st.session_state.val_masks,
                                    mode=assembly_mode,
                                    ordered_indices=ordered_indices
                                )
                                st.session_state.val_assembled = assembled

                                non_zero = np.count_nonzero(assembled)
                                coverage = (non_zero / assembled.size) * 100
                                st.success(f"[OK] Assemblage mode '{assembly_mode}': {non_zero:,} px actifs ({coverage:.2f}%)")

                            except Exception as e:
                                st.error(f"[ERR] {e}")

                with col_b2:
                    if "val_assembled" in st.session_state:
                        assembled = st.session_state.val_assembled

                        # Histogramme
                        fig, ax = plt.subplots(figsize=(6, 4))
                        data = assembled[assembled > 0]
                        if data.size > 0:
                            ax.hist(data, bins=50, color='steelblue', alpha=0.7)
                            ax.set_title(f"Distribution valeurs (max={np.max(data)})")
                            ax.set_xlabel("Intensité")
                            ax.set_ylabel("Pixels")
                            ax.grid(alpha=0.3)
                        st.pyplot(fig)
                        plt.close()

                        # Export
                        success, buffer = cv2.imencode('.png', assembled)
                        if success:
                            st.download_button(
                                "Télécharger mask assemblé",
                                data=buffer.tobytes(),
                                file_name=f"assembled_{assembly_mode}.png",
                                mime="image/png",
                                key="dl_assembled_util"
                            )
            else:
                st.warning("⚠️ Chargez au moins 2 masks dans le workflow ci-dessous pour utiliser l'assemblage")

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

        # Analyse conflits
        if len(st.session_state.val_masks) >= 2:
            st.markdown("**Paramètres analyse**")

            conflict_threshold = st.slider(
                "Seuil conflit (0-1)",
                0.05, 0.30, 0.15, 0.01,
                help="Pixel actif si intensité > seuil"
            )

            if st.button("Analyser conflits", type="primary"):
                with st.spinner("Analyse conflits..."):
                    conflicts = pv.analyze_conflicts(st.session_state.val_masks, threshold=conflict_threshold)
                    st.session_state.val_conflicts = conflicts

                    # Afficher résultats
                    col_m1, col_m2, col_m3 = st.columns(3)
                    with col_m1:
                        st.metric("Pixels conflit", f"{np.count_nonzero(conflicts['conflict_zone']):,}")
                    with col_m2:
                        st.metric("% Surface", f"{conflicts['conflict_pct']:.2f}%")
                    with col_m3:
                        st.metric("Seuil", f"{conflicts['threshold']:.2f}")

                    # Top paires
                    if conflicts['pair_summary']:
                        st.markdown("**Top paires en conflit:**")
                        for line in conflicts['pair_summary']:
                            st.text(f"• {line}")

                    # Heatmap
                    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

                    # Overlap count
                    cmap = mcolors.ListedColormap(['#1a1a1a', '#3a3a3a', '#ff0000', '#ff4444', '#ff8888'])
                    im1 = ax1.imshow(conflicts['overlap_count'], cmap=cmap, vmin=0, vmax=max(2, len(st.session_state.val_masks)))
                    ax1.set_title(f"Heatmap overlap (seuil {conflicts['threshold']:.2f})")
                    ax1.axis('off')
                    plt.colorbar(im1, ax=ax1, fraction=0.046)

                    # Conflict zone
                    ax2.imshow(conflicts['conflict_zone'], cmap='hot')
                    ax2.set_title(f"Zone conflit ({conflicts['conflict_pct']:.2f}%)")
                    ax2.axis('off')

                    st.pyplot(fig)
                    plt.close()

        # ───────────────────────────────────────────────────────────────────
        # B — Correction par ordre de priorité
        # ───────────────────────────────────────────────────────────────────

        if len(st.session_state.val_masks) >= 2:
            st.divider()
            st.markdown("#### B — Correction par Ordre de Priorité")

            blend_mode = st.checkbox("Mode fondu gris", value=True, help="True=fondu progressif, False=binaire strict")

            col_c1, col_c2 = st.columns(2)

            with col_c1:
                if st.button("Prévisualiser correction"):
                    with st.spinner("Nettoyage..."):
                        cleaned = pv.clean_masks_by_order(
                            st.session_state.val_masks,
                            st.session_state.val_paths,
                            blend_mode=blend_mode
                        )
                        st.session_state.val_cleaned = cleaned

                        # Stats avant/après
                        if "val_conflicts" in st.session_state:
                            orig_conflicts = st.session_state.val_conflicts['conflict_pct']
                            new_conflicts = pv.analyze_conflicts(cleaned, threshold=conflict_threshold)
                            new_pct = new_conflicts['conflict_pct']

                            st.success(f"[OK] Nettoyage terminé")
                            st.metric("Conflits avant", f"{orig_conflicts:.2f}%")
                            st.metric("Conflits après", f"{new_pct:.2f}%", delta=f"{new_pct - orig_conflicts:.2f}%")

            with col_c2:
                if "val_cleaned" in st.session_state and "val_conflicts" in st.session_state:
                    # Visualisation avant/après
                    orig_overlap = st.session_state.val_conflicts['overlap_count']
                    cleaned_analysis = pv.analyze_conflicts(st.session_state.val_cleaned, threshold=conflict_threshold)

                    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

                    cmap = mcolors.ListedColormap(['#1a1a1a', '#3a3a3a', '#ff0000', '#ff4444'])
                    ax1.imshow(orig_overlap, cmap=cmap, vmin=0, vmax=4)
                    ax1.set_title("Avant correction")
                    ax1.axis('off')

                    ax2.imshow(cleaned_analysis['overlap_count'], cmap=cmap, vmin=0, vmax=4)
                    ax2.set_title("Après correction")
                    ax2.axis('off')

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

                        saved = pv.export_masks_png(
                            st.session_state.val_cleaned,
                            st.session_state.val_paths,
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

        if st.session_state.val_masks:
            st.divider()
            st.markdown("#### C — Masks Erreur Reforger")

            col_d1, col_d2 = st.columns([1, 1])

            with col_d1:
                uploaded_errors = st.file_uploader(
                    "Upload masks erreur Reforger (PNG)",
                    type=["png"],
                    accept_multiple_files=True,
                    key="val_reforger_upload"
                )

                meter_per_px = st.number_input(
                    "Résolution (m/px)",
                    value=st.session_state.get("cellsize", 1.0),
                    min_value=0.1,
                    max_value=10.0,
                    step=0.1,
                    format="%.2f"
                )

                if uploaded_errors:
                    if st.button("Charger masks erreur"):
                        import tempfile
                        temp_paths = []
                        try:
                            for uf in uploaded_errors:
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                                    tmp.write(uf.read())
                                    temp_paths.append(tmp.name)

                            target_shape = st.session_state.val_masks[0].shape
                            error_mask = pv.load_reforger_errors(temp_paths, target_shape)
                            st.session_state.val_error_mask = error_mask

                            error_px = np.count_nonzero(error_mask)
                            st.success(f"[OK] {len(temp_paths)} masks erreur combinés")
                            st.metric("Pixels erreur", f"{error_px:,}")

                        finally:
                            for p in temp_paths:
                                try:
                                    Path(p).unlink()
                                except:
                                    pass

            with col_d2:
                if "val_error_mask" in st.session_state and "val_conflicts" in st.session_state:
                    if st.button("Superposer sur QTRE"):
                        with st.spinner("Génération heatmap combinée..."):
                            heatmap_result = pv.compute_combined_heatmap(
                                st.session_state.val_masks,
                                st.session_state.val_error_mask,
                                threshold=conflict_threshold
                            )
                            st.session_state.val_heatmap = heatmap_result

                            # Métriques
                            col_h1, col_h2, col_h3 = st.columns(3)
                            with col_h1:
                                st.metric("QTRE seul", heatmap_result['qtre_only_px'], help="Rouge")
                            with col_h2:
                                st.metric("Les deux", heatmap_result['magenta_px'], help="Magenta")
                            with col_h3:
                                st.metric("Reforger seul", heatmap_result['cyan_px'], help="Cyan")

                            # Visualisation
                            fig, ax = plt.subplots(figsize=(8, 6))
                            ax.imshow(heatmap_result['heatmap_rgb'])
                            ax.set_title("QTRE (rouge) | Les deux (magenta) | Reforger seul (cyan)")
                            ax.axis('off')
                            st.pyplot(fig)
                            plt.close()

            # Export heatmap
            if "val_heatmap" in st.session_state:
                heatmap_rgb = st.session_state.val_heatmap['heatmap_rgb']
                success, buffer = cv2.imencode('.png', cv2.cvtColor(heatmap_rgb, cv2.COLOR_RGB2BGR))
                if success:
                    st.download_button(
                        "Télécharger heatmap combinée",
                        data=buffer.tobytes(),
                        file_name="heatmap_qtre_reforger.png",
                        mime="image/png"
                    )

                # Export zones cyan CSV
                if st.button("Exporter zones cyan CSV"):
                    cyan_mask = st.session_state.val_heatmap['cyan_mask']
                    csv_content = pv.export_cyan_coords_csv(cyan_mask, meter_per_px)
                    st.download_button(
                        "Télécharger zones cyan (CSV)",
                        data=csv_content,
                        file_name="zones_cyan_meters.csv",
                        mime="text/csv"
                    )
                    st.success("[OK] CSV généré")

        # ───────────────────────────────────────────────────────────────────
        # D — Correction zones Reforger
        # ───────────────────────────────────────────────────────────────────

        if "val_heatmap" in st.session_state:
            st.divider()
            st.markdown("#### D — Correction Zones Reforger")

            st.info("Corrige pixels magenta (QTRE + Reforger) en gardant mask dominant uniquement")

            if st.button("Corriger zones magenta", type="primary"):
                with st.spinner("Correction magenta..."):
                    heatmap_rgb = st.session_state.val_heatmap['heatmap_rgb']
                    corrected_masks = pv.correct_magenta_zones(st.session_state.val_masks, heatmap_rgb)
                    st.session_state.val_corrected_reforger = corrected_masks

                    # Stats avant/après
                    if "val_conflicts" in st.session_state:
                        orig_count = np.count_nonzero(st.session_state.val_conflicts['conflict_zone'])
                        new_analysis = pv.analyze_conflicts(corrected_masks, threshold=conflict_threshold)
                        new_count = np.count_nonzero(new_analysis['conflict_zone'])
                        delta = orig_count - new_count

                        col_e1, col_e2, col_e3 = st.columns(3)
                        with col_e1:
                            st.metric("Conflits avant", f"{orig_count:,}")
                        with col_e2:
                            st.metric("Conflits après", f"{new_count:,}")
                        with col_e3:
                            st.metric("Réduction", f"{delta:,}", delta=f"-{delta}")

                        magenta_px = st.session_state.val_heatmap['magenta_px']
                        st.success(f"[OK] {magenta_px:,} pixels magenta corrigés")

            # Export masks corrigés Reforger
            if "val_corrected_reforger" in st.session_state:
                st.markdown("**Export masks corrigés**")

                # Dossier par défaut : récupérer depuis masks_dir_v2 ou proposer output/
                default_dir = st.session_state.get("masks_dir_v2", "generated/validation")
                if default_dir and Path(default_dir).exists():
                    default_export = str(Path(default_dir).parent / "masks_reforgerfix")
                else:
                    default_export = "generated/validation/masks_reforgerfix"

                export_dir = st.text_input(
                    "Dossier de destination",
                    value=default_export,
                    help="Chemin absolu ou relatif où sauvegarder les masks corrigés",
                    key="export_dir_reforger"
                )

                if st.button("Exporter masks corrigés Reforger", type="primary"):
                    try:
                        output_path = Path(export_dir)

                        # Créer le dossier si nécessaire
                        output_path.mkdir(parents=True, exist_ok=True)

                        # Exporter
                        saved = pv.export_masks_png(
                            st.session_state.val_corrected_reforger,
                            st.session_state.val_paths,
                            output_path,
                            suffix='_reforgerfix'
                        )

                        if saved:
                            st.success(f"[OK] {len(saved)} masks exportés dans `{output_path.absolute()}`")

                            # Mettre à jour session pour utiliser versions corrigées
                            st.session_state.val_masks = st.session_state.val_corrected_reforger
                            st.session_state.masks_dir_v2 = str(output_path)  # Mettre à jour pour prochaine utilisation

                            st.info("✓ Masks chargés remplacés par versions corrigées")

                            # Afficher liste des fichiers
                            with st.expander("📂 Fichiers exportés"):
                                for path in saved:
                                    st.text(f"• {Path(path).name}")

                    except Exception as e:
                        st.error(f"[ERR] Erreur export : {e}")

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
    <p><strong>Map Generator Pro v4.0</strong> — Post-Traitement & Cache Terrain</p>
    <p>✨ Nouveau : Fusion masks pipeline_v2 + mappeur | Cache terrain_data | Zones urbaines automatiques</p>
    <p>© 2026 | Production-Ready</p>
</div>
""", unsafe_allow_html=True)
