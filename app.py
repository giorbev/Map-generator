# -*- coding: utf-8 -*-
"""
Map Generator Pro v6.0 — Streamlit Application
Interface complète de génération de cartes topographiques

CHANGELOG v6.0 (2026-08-02):
- Navigation par cartes cliquables (6 onglets thématiques)
- Chemins centralisés dans project.json
- Migration pipeline_v2 → pipeline_unified
- Drag & drop natif pour fichiers
- Sliders avec aide inline + sauvegarde auto
- Structure bilingue FR/EN (préparation)
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
# TEXTES BILINGUES — Structure préparatoire pour FR/EN
# ============================================================================

TEXTS = {
    "fr": {
        # TODO: Ajouter tous les textes français (v6.1+)
    },
    "en": {
        # TODO: Ajouter tous les textes anglais (v6.1+)
    }
}

# ============================================================================
# NAVIGATION PAR CARTES v6.0
# ============================================================================

def render_navigation_cards():
    """Affiche la page de navigation par cartes (6 onglets thématiques)."""
    st.markdown("## 🗺️ Navigation — Choisissez un module")

    # Grille 2×3 cartes
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📊 Heightmap\nVisualisation • Atlas • Chemins", key="nav_heightmap", use_container_width=True):
            st.session_state["active_tab"] = "heightmap"
            st.rerun()

    with col2:
        if st.button("⚙️ Pipeline\nParamètres • Lancer • Résultats", key="nav_pipeline", use_container_width=True):
            st.session_state["active_tab"] = "pipeline"
            st.rerun()

    with col3:
        if st.button("🛰️ Satmap\nMode texturé • Mode couleurs", key="nav_satmap", use_container_width=True):
            st.session_state["active_tab"] = "satmap"
            st.rerun()

    col4, col5, col6 = st.columns(3)

    with col4:
        if st.button("🗺️ Terrain binaire\nInspect • Scan • QTRE", key="nav_terrain", use_container_width=True):
            st.session_state["active_tab"] = "terrain"
            st.rerun()

    with col5:
        if st.button("🔧 Corrections\nScan zone • Clean • Force-mat", key="nav_corrections", use_container_width=True):
            st.session_state["active_tab"] = "corrections"
            st.rerun()

    with col6:
        if st.button("✅ Validation\nSimulate • Conflits • Rapport", key="nav_validation", use_container_width=True):
            st.session_state["active_tab"] = "validation"
            st.rerun()

    st.divider()
    st.markdown("💡 **Astuce** : Les modules sont sauvegardés automatiquement dans votre projet.")


def init_navigation():
    """Initialise la navigation si nécessaire."""
    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = None  # None = page de navigation


# ============================================================================
# CONFIGURATION STREAMLIT
# ============================================================================

st.set_page_config(
    page_title="Map Generator Pro v6.0",
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

    /* Navigation cartes v6.0 */
    .nav-card {
        padding: 1.5em;
        border-radius: 10px;
        cursor: pointer;
        transition: transform 0.2s, box-shadow 0.2s;
        text-align: center;
        color: white;
        font-weight: bold;
        font-size: 1.2em;
        margin: 0.5em 0;
    }
    .nav-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
    }
    .nav-card-heightmap { background: linear-gradient(135deg, #2d8a4e 0%, #3ba55c 100%); }
    .nav-card-pipeline { background: linear-gradient(135deg, #6b46c1 0%, #8454d6 100%); }
    .nav-card-satmap { background: linear-gradient(135deg, #1a6fa8 0%, #2287c4 100%); }
    .nav-card-terrain { background: linear-gradient(135deg, #c47a1e 0%, #d98b2b 100%); }
    .nav-card-corrections { background: linear-gradient(135deg, #b83232 0%, #d34444 100%); }
    .nav-card-validation { background: linear-gradient(135deg, #1a8a7a 0%, #22a693 100%); }
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

# save_config() et load_config() supprimées v6.0 — chemins centralisés dans project.json

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

    # Arborescence standard v6.0
    subdirs = [
        "inputs",
        "outputs/masks",
        "outputs/satmap",
        "outputs/reports",
        "outputs/generated",
        "outputs/cache",
        "backups",
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
            "heightmap":       "inputs/heightmap/",
            "satmap":          "inputs/satmap/",
            "exclusion_mask":  "inputs/masks/",
            "gaea_flow":       "inputs/gaea/",
            "gaea_deposit":    "inputs/gaea/",
            "exports_mask":    "outputs/masks/latest/",
            "addon_reforger":  "",
            "catalog_json":    ""
        },
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

    # ── Pipeline V2 supprimé v6.0 (remplacé par pipeline_unified) ──────────


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

    # Chemins centralisés v6.0
    paths = data.get("paths", {})
    st.session_state["paths"] = {
        "heightmap":       paths.get("heightmap", ""),
        "satmap":          paths.get("satmap", ""),
        "exclusion_mask":  paths.get("exclusion_mask", ""),
        "gaea_flow":       paths.get("gaea_flow", ""),
        "gaea_deposit":    paths.get("gaea_deposit", ""),
        "exports_mask":    paths.get("exports_mask", "exports_mask/"),
        "addon_reforger":  paths.get("addon_reforger", ""),
        "catalog_json":    paths.get("catalog_json", "")
    }

    # Migration douce — signaler anciens dossiers si nouvelle structure absente
    proj_path = Path(st.session_state.current_project_path)
    if not (proj_path / "inputs").exists() and (proj_path / "sources").exists():
        st.session_state["migration_needed"] = True
    # Créer arborescence manquante sans toucher aux fichiers existants
    for subdir in ["inputs",
                   "outputs/masks","outputs/satmap","outputs/reports",
                   "outputs/generated","outputs/cache","backups"]:
        (proj_path / subdir).mkdir(parents=True, exist_ok=True)


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
            if hm_path.exists():
                shutil.copy2(str(hm_path), str(dest))
            else:
                pass  # Fichier source absent — pas de copie

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

    # ── PIPELINE V2 + POST-PROCESSING supprimés v6.0 ───────────────────────
    # Remplacés par pipeline_unified (section paths)



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

    # ── CHEMINS CENTRALISÉS v6.0 ────────────────────────────────────────────
    paths = st.session_state.get("paths", {})
    data["paths"] = {
        "heightmap":       paths.get("heightmap", ""),
        "satmap":          paths.get("satmap", ""),
        "exclusion_mask":  paths.get("exclusion_mask", ""),
        "gaea_flow":       paths.get("gaea_flow", ""),
        "gaea_deposit":    paths.get("gaea_deposit", ""),
        "exports_mask":    paths.get("exports_mask", "exports_mask/"),
        "addon_reforger":  paths.get("addon_reforger", ""),
        "catalog_json":    paths.get("catalog_json", "")
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
            deposit=terrain_data.get('deposit', np.zeros_like(terrain_data['flow'])),
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
            'deposit': npz.get('deposit', np.zeros_like(npz['flow'])),
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
    if 'cw_scan_done' not in st.session_state:
        st.session_state.cw_scan_done = False
    if 'cw_clean_done' not in st.session_state:
        st.session_state.cw_clean_done = False
    if 'cw_confirm_pending' not in st.session_state:
        st.session_state.cw_confirm_pending = False

    # (Ancien chargement config.json supprimé v6.0 — chemins dans project.json)

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

# ============================================================================
# SIDEBAR v6.0 — Sélecteur langue + Statistiques rapides
# ============================================================================

st.sidebar.divider()

# Sélecteur langue (préparation bilingue)
lang = st.sidebar.selectbox(
    "🌐 Langue / Language",
    options=["Français", "English"],
    index=0,
    key="lang_selector"
)
st.session_state["lang"] = "fr" if lang == "Français" else "en"

st.sidebar.divider()
st.sidebar.caption("💡 Utilisez **Heightmap → Chemins & fichiers** pour configurer vos chemins")

# ============================================================================
# FIN SIDEBAR v6.0 — Sidebar simplifiée
# ============================================================================

# (Ancien code sidebar supprimé ici - lignes 1400-1636)

# ============================================================================
# MAIN CONTENT — ONGLETS
# ============================================================================

st.markdown('<h1 class="main-header"> Map Generator Pro v6.0</h1>', unsafe_allow_html=True)

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
    # Initialiser la navigation v6.0
    init_navigation()

    # Si aucun onglet actif → afficher navigation par cartes
    if st.session_state.get("active_tab") is None:
        render_navigation_cards()
        st.stop()  # Arrêter le rendu ici

    # Sinon, afficher le contenu de l'onglet actif
    active_tab = st.session_state["active_tab"]

    # Bouton retour navigation
    if st.button("← Retour navigation", key="back_nav"):
        st.session_state["active_tab"] = None
        st.rerun()

    st.divider()

    # ========================================================================
    # ONGLET HEIGHTMAP — Visualisation / Atlas / Chemins & fichiers
    # ========================================================================

    if active_tab == "heightmap":
        st.markdown("## 📊 Heightmap — Visualisation et configuration")

        _t_hypso, _t_atlas, _t_paths = st.tabs([
            "📊 Visualisation", "📈 Atlas métrique", "📁 Chemins & fichiers"
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

        # (Bloc _t_masques supprimé v6.0 — déplacé vers Pipeline)

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

        with _t_paths:
            st.markdown("### 📁 Chemins & fichiers — Configuration centralisée")
            st.caption("Tous les chemins sont sauvegardés dans project.json → section paths")

            if st.session_state.get("migration_needed"):
                st.warning("⚠️ Projet ancien détecté — dossiers `sources/`, `masks/`, `gaea/` trouvés. "
                           "Déplacez manuellement vos fichiers vers `inputs/` pour utiliser la nouvelle structure. "
                           "Aucun fichier n'a été modifié automatiquement.")

            if "paths" not in st.session_state:
                st.session_state["paths"] = {
                    "heightmap": "", "satmap": "", "exclusion_mask": "",
                    "gaea_flow": "", "gaea_deposit": "",
                    "exports_mask": "exports_mask/",
                    "addon_reforger": "", "catalog_json": ""
                }

            paths = st.session_state["paths"]

            st.markdown("#### 📂 Fichiers sources")
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Heightmap** (.asc / .png)")
                uploaded_hm = st.file_uploader(
                    "Glissez-déposez votre heightmap",
                    type=["asc", "png", "tif"],
                    key="upload_heightmap",
                    help="Format .asc recommandé"
                )
                if uploaded_hm:
                    proj_path = Path(st.session_state.current_project_path)
                    dest = proj_path / "inputs" / uploaded_hm.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(uploaded_hm.getvalue())
                    paths["heightmap"] = f"inputs/{uploaded_hm.name}"
                    st.success(f"✅ {uploaded_hm.name} copié dans inputs/")
                    auto_save()

                st.markdown("**Satmap** (.png)")
                uploaded_sat = st.file_uploader(
                    "Glissez-déposez votre satmap",
                    type=["png", "jpg", "jpeg"],
                    key="upload_satmap"
                )
                if uploaded_sat:
                    proj_path = Path(st.session_state.current_project_path)
                    dest = proj_path / "inputs" / uploaded_sat.name
                    dest.write_bytes(uploaded_sat.getvalue())
                    paths["satmap"] = f"inputs/{uploaded_sat.name}"
                    st.success(f"✅ {uploaded_sat.name} copié")
                    auto_save()

            with col2:
                st.markdown("**Masque exclusion** (.png)")
                uploaded_excl = st.file_uploader(
                    "Zone B (blanc = actif)",
                    type=["png"],
                    key="upload_exclusion"
                )
                if uploaded_excl:
                    proj_path = Path(st.session_state.current_project_path)
                    dest = proj_path / "inputs" / uploaded_excl.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(uploaded_excl.getvalue())
                    paths["exclusion_mask"] = f"inputs/{uploaded_excl.name}"
                    st.success(f"✅ {uploaded_excl.name} copié")
                    auto_save()

            st.divider()
            st.markdown("#### 🌊 Masques Gaea (optionnels)")
            col3, col4 = st.columns(2)

            with col3:
                uploaded_flow = st.file_uploader(
                    "Flow (érosion)", type=["png"], key="upload_flow"
                )
                if uploaded_flow:
                    proj_path = Path(st.session_state.current_project_path)
                    dest = proj_path / "inputs" / uploaded_flow.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(uploaded_flow.getvalue())
                    paths["gaea_flow"] = f"inputs/{uploaded_flow.name}"
                    st.success(f"✅ {uploaded_flow.name}")
                    auto_save()

            with col4:
                uploaded_deposit = st.file_uploader(
                    "Deposit (sédiments)", type=["png"], key="upload_deposit"
                )
                if uploaded_deposit:
                    proj_path = Path(st.session_state.current_project_path)
                    dest = proj_path / "inputs" / uploaded_deposit.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(uploaded_deposit.getvalue())
                    paths["gaea_deposit"] = f"inputs/{uploaded_deposit.name}"
                    st.success(f"✅ {uploaded_deposit.name}")
                    auto_save()

            st.divider()
            st.markdown("#### 📁 Dossiers")

            addon_path = st.text_input(
                "📁 Addon Reforger",
                value=paths.get("addon_reforger", ""),
                key="input_addon",
                help="Chemin vers le dossier racine addon (ex: I:/Reforger_addons/Zimnitrita_map)",
                placeholder=r"I:\Reforger_addons\Zimnitrita_map"
            )
            if addon_path and addon_path != paths.get("addon_reforger", ""):
                paths["addon_reforger"] = addon_path
                auto_save()

            catalog_path = st.text_input(
                "📋 Catalog.json",
                value=paths.get("catalog_json", ""),
                key="input_catalog",
                help="Fichier catalog.json Reforger",
                placeholder=r"H:\data\catalog.json"
            )
            if catalog_path and catalog_path != paths.get("catalog_json", ""):
                paths["catalog_json"] = catalog_path
                auto_save()

            st.divider()
            st.markdown("#### 📋 État actuel des chemins")
            with st.expander("Voir tous les chemins", expanded=False):
                for key, value in paths.items():
                    status = "✅" if value else "⚠️"
                    st.text(f"{status} {key}: {value if value else '(vide)'}")

    # ========================================================================
    # ONGLET SATMAP — Mode texturé / Mode couleurs
    # ========================================================================

    if active_tab == "satmap":
        st.markdown("### 🛰️ Satmap Export Reforger")

        # Sous-onglets : Satmap v2
        subtab_satmap_v2, subtab_classifier = st.tabs([
            "🚀 Satmap v2.0 (Layer.dds)",
            "🎯 Classificateur K-means"
        ])

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
            paths = st.session_state.get("paths", {})
            catalog_str = paths.get("catalog_json", "")
            catalog_ok = Path(catalog_str).exists() if catalog_str else False

            col_cat1, col_cat2 = st.columns([3, 1])
            with col_cat1:
                if catalog_ok:
                    st.success(f"✅ Catalogue : `{Path(catalog_str).name}` ({Path(catalog_str).stat().st_size // 1024} Ko)")
                else:
                    st.error("❌ Catalogue introuvable — configurez le chemin dans **Heightmap → Chemins & fichiers**")

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

            paths = st.session_state.get("paths", {})
            addon_reforger = paths.get("addon_reforger", "")
            if not addon_reforger:
                st.info("📁 Configurez le chemin addon dans Heightmap → Chemins & fichiers")
                rp = {}
            else:
                from app_config import resolve_paths
                rp = resolve_paths(addon_reforger)
                if rp.get("valid"):
                    st.session_state["resolved_paths"] = rp
                    if not st.session_state.get("terr_materials") and rp.get("terr_file"):
                        try:
                            from terrain_terr_reader import read_mats_from_terr
                            mats = read_mats_from_terr(rp["terr_file"])
                            st.session_state["terr_materials"] = mats
                        except Exception as e:
                            st.warning(f"⚠️ Impossible de lire le .terr : {e}")
                else:
                    st.error(f"❌ Chemin addon invalide : {rp.get('error')}")
                    rp = {}
            if rp.get("valid"):
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

                            # Récupérer catalog_path depuis paths (v6.0)
                            paths = st.session_state.get("paths", {})
                            catalog_path_str = paths.get("catalog_json", "")
                            if not catalog_path_str:
                                st.error("❌ Chemin catalog.json manquant — configurez-le dans Heightmap → Chemins & fichiers")
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
                                    if middles_dir_str:
                                        app_dir = Path(__file__).parent
                                        middles_dir_path = Path(middles_dir_str) if Path(middles_dir_str).is_absolute() else app_dir / middles_dir_str
                                        if middles_dir_path.exists():
                                            middles_dir = middles_dir_path
                                        else:
                                            st.warning(f"⚠️ Dossier textures middle introuvable : {middles_dir_path}")

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

        with subtab_classifier:
            st.markdown("### 🎯 Classificateur K-means — Satmap → Masks")
            st.caption("Classifie une satmap en familles de couleurs K-means → export masks PNG par classe")

            proj_path = Path(st.session_state.get("current_project_path", "."))
            paths = st.session_state.get("paths", {})

            uploaded_sat_cls = st.file_uploader(
                "Satmap à classifier (.png / .jpg / .tif)",
                type=["png", "jpg", "jpeg", "tif"],
                key="upload_sat_classifier",
                help="Image satmap source à classifier"
            )

            col1, col2 = st.columns(2)
            with col1:
                n_clusters = st.slider(
                    "Nombre de classes K-means", 5, 40, 20, 1,
                    key="cls_n_clusters",
                    help="Nombre de familles de couleurs à détecter. 20 recommandé pour une satmap complexe."
                )
            with col2:
                reuse_classif = st.checkbox(
                    "Réutiliser classification.json existante",
                    key="cls_reuse",
                    help="Si coché, charge la classification précédente sans relancer K-means"
                )

            classif_json = proj_path / "outputs" / "satmap" / "classification.json"
            masks_out_dir = proj_path / "outputs" / "satmap" / "masks_classifier"

            st.info(f"📁 Sortie → `outputs/satmap/masks_classifier/`")

            if st.button("▶️ Lancer classification", key="btn_run_classifier"):
                if not uploaded_sat_cls and not reuse_classif:
                    st.error("❌ Chargez une satmap ou activez 'Réutiliser classification.json'")
                else:
                    try:
                        import satmap_classifier as sc
                        import importlib, io, contextlib
                        importlib.reload(sc)

                        sat_path = None
                        if uploaded_sat_cls:
                            sat_save = proj_path / "inputs" / "satmap" / uploaded_sat_cls.name
                            sat_save.parent.mkdir(parents=True, exist_ok=True)
                            sat_save.write_bytes(uploaded_sat_cls.getvalue())
                            sat_path = sat_save

                        masks_out_dir.mkdir(parents=True, exist_ok=True)

                        buf = io.StringIO()
                        with st.spinner("Classification K-means en cours..."):
                            with contextlib.redirect_stdout(buf):
                                result = sc.run_classification(
                                    input_path=sat_path,
                                    output_dir=masks_out_dir,
                                    n_clusters=n_clusters,
                                    classif_json=classif_json if reuse_classif else None,
                                    save_classif_json=classif_json,
                                    interactive=False
                                )
                        st.session_state["cls_log"] = buf.getvalue()
                        st.session_state["cls_result"] = result
                        st.success("✅ Classification terminée")
                        st.rerun()
                    except Exception as e:
                        import traceback
                        st.error(f"❌ Erreur : {e}")
                        st.code(traceback.format_exc())

            if st.session_state.get("cls_result"):
                r = st.session_state["cls_result"]
                masks_generated = list(masks_out_dir.glob("*.png")) if masks_out_dir.exists() else []
                st.metric("Masks générés", len(masks_generated))
                if masks_generated:
                    with st.expander("Liste masks", expanded=False):
                        for f in masks_generated:
                            st.text(f"  • {f.name}")

            if st.session_state.get("cls_log"):
                with st.expander("📋 Log classification", expanded=False):
                    st.code(st.session_state["cls_log"][-3000:])


    # ========================================================================
    # ONGLET PIPELINE — Paramètres / Lancer / Résultats
    # ========================================================================

    if active_tab == "pipeline":
        st.markdown("### ⚙️ Pipeline Unifié — Génération masques terrain")

        paths = st.session_state.get("paths", {})
        proj_path = Path(st.session_state.get("current_project_path", "."))

        _p_params, _p_run, _p_results = st.tabs([
            "⚙️ Paramètres", "▶️ Lancer", "📊 Résultats"
        ])

        with _p_params:
            st.markdown("#### Chemins")

            hm_path = paths.get("heightmap", "")
            st.text_input("Heightmap (.asc)", value=hm_path, disabled=True,
                          help="Configurez dans Heightmap → Chemins & fichiers")

            excl_path = paths.get("exclusion_mask", "")
            st.text_input("Masque exclusion", value=excl_path, disabled=True)

            flow_path = paths.get("gaea_flow", "")
            st.text_input("Flow Gaea (optionnel)", value=flow_path, disabled=True)

            deposit_path = paths.get("gaea_deposit", "")
            st.text_input("Deposit Gaea (optionnel)", value=deposit_path, disabled=True)

            st.divider()
            st.markdown("#### Paramètres — Terrain")

            # Charger params sauvegardés
            saved = st.session_state.get("pipeline_params", {})

            col1, col2 = st.columns(2)
            with col1:
                roughness_amplitude = st.slider(
                    "Roughness amplitude (°)", 0.0, 20.0,
                    float(saved.get("roughness_amplitude", 8.0)), 0.5,
                    key="p_roughness_amplitude",
                    help="Perturbation max du slope par le bruit fBm. Plus haut = terrain plus rugueux."
                )
                roughness_scale = st.slider(
                    "Roughness scale", 0.001, 0.02,
                    float(saved.get("roughness_scale", 0.008)), 0.001,
                    key="p_roughness_scale",
                    help="Fréquence spatiale du bruit. Bas = grandes ondulations, haut = détail fin."
                )
                coastal_width = st.slider(
                    "Largeur bande côtière (m)", 10.0, 200.0,
                    float(saved.get("coastal_width", 40.0)), 10.0,
                    key="p_coastal_width",
                    help="Largeur totale de la zone côtière en mètres."
                )
            with col2:
                threshold_rock = st.slider(
                    "Seuil Rock (°)", 15.0, 35.0,
                    float(saved.get("threshold_rock", 22.0)), 0.5,
                    key="p_threshold_rock",
                    help="Pente à partir de laquelle le masque Rock s'active. Validé Workbench : 22°."
                )
                threshold_cliff = st.slider(
                    "Seuil Cliff (°)", 20.0, 45.0,
                    float(saved.get("threshold_cliff", 26.0)), 0.5,
                    key="p_threshold_cliff",
                    help="Pente à partir de laquelle le masque Cliff s'active. Validé Workbench : 26°."
                )
                deposit_cut_low = st.slider(
                    "Deposit cut_low", 0.0, 0.9,
                    float(saved.get("deposit_cut_low", 0.55)), 0.05,
                    key="p_deposit_cut_low",
                    help="Coupe les zones de faible dépôt (percentile). 0.55 = garder seulement les 45% les plus forts."
                )

            st.divider()
            st.markdown("#### Paramètres — Export")
            col3, col4 = st.columns(2)
            with col3:
                weight_min = st.slider(
                    "Weight min", 0.05, 0.30,
                    float(saved.get("weight_min", 0.10)), 0.01,
                    key="p_weight_min",
                    help="Valeur minimale après normalisation. Evite les masques quasi-nuls."
                )
                budget_max = st.slider(
                    "Budget max slots", 4, 7,
                    int(saved.get("budget_max", 6)), 1,
                    key="p_budget_max",
                    help="Nombre max de matériaux par bloc 32×32. Reforger supporte 7 slots LRS2."
                )
            with col4:
                stretch_auto = st.checkbox(
                    "Stretch auto",
                    value=bool(saved.get("stretch_auto", True)),
                    key="p_stretch_auto",
                    help="Étire automatiquement chaque masque sur [0, 65535] avant export."
                )

            col_save, col_reset = st.columns(2)
            with col_save:
                if st.button("💾 Sauvegarder paramètres", key="btn_save_pipeline_params"):
                    st.session_state["pipeline_params"] = {
                        "roughness_amplitude": roughness_amplitude,
                        "roughness_scale":     roughness_scale,
                        "coastal_width":       coastal_width,
                        "threshold_rock":      threshold_rock,
                        "threshold_cliff":     threshold_cliff,
                        "deposit_cut_low":     deposit_cut_low,
                        "weight_min":          weight_min,
                        "budget_max":          budget_max,
                        "stretch_auto":        stretch_auto,
                    }
                    auto_save()
                    st.success("✅ Paramètres sauvegardés dans project.json")
            with col_reset:
                if st.button("🔄 Réinitialiser", key="btn_reset_pipeline_params"):
                    st.session_state.pop("pipeline_params", None)
                    st.rerun()

        with _p_run:
            st.markdown("#### Lancer le pipeline")

            params = st.session_state.get("pipeline_params", {})
            hm = paths.get("heightmap", "")

            if not hm:
                st.warning("⚠️ Heightmap non configurée — allez dans Heightmap → Chemins & fichiers")
            else:
                # Dossier de sortie horodaté
                from datetime import datetime
                run_ts = datetime.now().strftime("%Y-%m-%d_%Hh%M")
                output_run_dir = proj_path / "outputs" / "masks" / run_ts
                latest_dir = proj_path / "outputs" / "masks" / "latest"
                st.info(f"📁 Sortie → `outputs/masks/{run_ts}/`")

                if st.button("▶️ Lancer le pipeline", key="btn_run_pipeline", type="primary"):
                    try:
                        import pipeline_unified as pu
                        import importlib
                        importlib.reload(pu)

                        # Injecter paramètres
                        pu.ROUGHNESS_AMPLITUDE = params.get("roughness_amplitude", 8.0)
                        pu.ROUGHNESS_SCALE     = params.get("roughness_scale", 0.008)
                        pu.COASTAL_WIDTH       = params.get("coastal_width", 40.0)
                        pu.THRESHOLD_ROCK      = params.get("threshold_rock", 22.0)
                        pu.THRESHOLD_CLIFF     = params.get("threshold_cliff", 26.0)
                        pu.DEPOSIT_CUT_LOW     = params.get("deposit_cut_low", 0.55)
                        pu.WEIGHT_MIN          = params.get("weight_min", 0.10)
                        pu.BUDGET_MAX          = int(params.get("budget_max", 6))
                        pu.STRETCH_AUTO        = params.get("stretch_auto", True)
                        hm_resolved = Path(hm) if Path(hm).is_absolute() else proj_path / hm
                        pu.ASC_PATH = hm_resolved
                        pu.OUTPUT_DIR          = output_run_dir
                        pu.EXCLUSION_MASK      = Path(proj_path / paths["exclusion_mask"]) if paths.get("exclusion_mask") else None
                        pu.GAEA_FLOW           = Path(proj_path / paths["gaea_flow"]) if paths.get("gaea_flow") else None
                        pu.GAEA_DEPOSIT        = Path(proj_path / paths["gaea_deposit"]) if paths.get("gaea_deposit") else None

                        output_run_dir.mkdir(parents=True, exist_ok=True)

                        with st.spinner("Pipeline en cours..."):
                            import io, contextlib
                            buf = io.StringIO()
                            with contextlib.redirect_stdout(buf):
                                pu.main()
                            log_output = buf.getvalue()

                        # Mettre à jour latest/
                        import shutil
                        if latest_dir.exists():
                            shutil.rmtree(latest_dir)
                        shutil.copytree(output_run_dir, latest_dir)

                        st.session_state["pipeline_last_run"] = str(run_ts)
                        st.session_state["pipeline_log"] = log_output
                        st.success(f"✅ Pipeline terminé — {output_run_dir.name}")
                        st.rerun()

                    except Exception as e:
                        import traceback
                        st.error(f"❌ Erreur pipeline : {e}")
                        st.code(traceback.format_exc())

        with _p_results:
            st.markdown("#### Résultats du dernier run")
            last_run = st.session_state.get("pipeline_last_run")
            if not last_run:
                st.info("Aucun run effectué dans cette session.")
            else:
                st.success(f"Dernier run : `{last_run}`")
                run_dir = proj_path / "outputs" / "masks" / last_run
                if run_dir.exists():
                    masks_files = sorted(run_dir.glob("*.png"))
                    st.write(f"{len(masks_files)} masques générés :")
                    for f in masks_files:
                        st.text(f"  • {f.name}")
                if st.session_state.get("pipeline_log"):
                    with st.expander("📋 Log pipeline", expanded=False):
                        st.code(st.session_state["pipeline_log"][-5000:])

    # ========================================================================
    # ========================================================================
    # ONGLET VALIDATION — Simulate / Conflits / Rapport
    # ========================================================================

    if active_tab == "validation":
        st.markdown("### ✅ Validation")
        _v_simulate, _v_conflicts, _v_report = st.tabs([
            "🔬 Simulate masks", "⚠️ Conflits", "📊 Rapport"
        ])
        with _v_simulate:
            st.markdown("#### 🔬 Simulation budget slots")
            st.caption("Lecture seule — simule l'empilement des masques sur l'état actuel des .edds")

            paths = st.session_state.get("paths", {})
            proj_path = Path(st.session_state.get("current_project_path", "."))
            addon_reforger = paths.get("addon_reforger", "")

            if not addon_reforger:
                st.info("📁 Configurez le chemin addon dans Heightmap → Chemins & fichiers")
            else:
                from app_config import resolve_paths
                rp_v = resolve_paths(addon_reforger)
                if not rp_v.get("valid"):
                    st.error(f"❌ Chemin addon invalide : {rp_v.get('error')}")
                else:
                    # Dossier masques — latest ou sélection manuelle
                    latest_dir = proj_path / "outputs" / "masks" / "latest"
                    masks_runs = sorted(
                        [d for d in (proj_path / "outputs" / "masks").iterdir()
                         if d.is_dir() and d.name != "latest"],
                        reverse=True
                    ) if (proj_path / "outputs" / "masks").exists() else []

                    run_options = ["latest"] + [d.name for d in masks_runs]
                    selected_run = st.selectbox(
                        "Run à simuler", run_options, key="sim_run_select",
                        help="Sélectionner le run de masques à simuler"
                    )
                    masks_dir_sim = latest_dir if selected_run == "latest" else proj_path / "outputs" / "masks" / selected_run

                    threshold_sim = st.slider(
                        "Seuil coverage (%)", 1, 30, 10, 1,
                        key="sim_threshold",
                        help="Coverage minimum d'un bloc pour compter +1 slot"
                    ) / 100.0

                    terrain_dir_v = Path(rp_v["terrain_dir"])
                    data_dir_v    = terrain_dir_v / ".Data"
                    editor_dir_v  = terrain_dir_v / ".EditorData"

                    output_sim = proj_path / "outputs" / "reports" / "simulate_masks.png"

                    if st.button("▶️ Lancer simulation", key="btn_simulate"):
                        if not masks_dir_sim.exists():
                            st.error(f"❌ Dossier masques introuvable : {masks_dir_sim}")
                        else:
                            with st.spinner("Simulation en cours..."):
                                import simulate_masks as sm
                                import importlib, io, contextlib
                                importlib.reload(sm)
                                sm.DATA_DIR         = data_dir_v
                                sm.EDITOR_DATA_DIR  = editor_dir_v
                                sm.TTILE_DIR        = data_dir_v
                                output_sim.parent.mkdir(parents=True, exist_ok=True)
                                buf = io.StringIO()
                                with contextlib.redirect_stdout(buf):
                                    slots_actuels = sm.read_current_slots()
                                    total_slots, contributions = sm.simulate_masks_stacking(
                                        masks_dir_sim, slots_actuels, threshold=threshold_sim
                                    )
                                    img = sm.generate_budget_image(total_slots)
                                    import cv2
                                    cv2.imwrite(str(output_sim), img)
                                    sm.print_statistics(total_slots, contributions)
                                st.session_state["sim_log"] = buf.getvalue()
                                st.session_state["sim_output"] = str(output_sim)
                            st.success("✅ Simulation terminée")
                            st.rerun()

                    if st.session_state.get("sim_output") and Path(st.session_state["sim_output"]).exists():
                        st.image(st.session_state["sim_output"], caption="Budget slots par bloc", use_container_width=True)
                    if st.session_state.get("sim_log"):
                        with st.expander("📋 Log simulation", expanded=False):
                            st.code(st.session_state["sim_log"][-3000:])
        with _v_conflicts:
            st.markdown("#### ⚠️ Analyse des conflits")
            st.caption("Lecture seule — analyse l'état actuel des .edds + simule l'empilement des masques")

            paths = st.session_state.get("paths", {})
            proj_path = Path(st.session_state.get("current_project_path", "."))
            addon_reforger = paths.get("addon_reforger", "")

            if not addon_reforger:
                st.info("📁 Configurez le chemin addon dans Heightmap → Chemins & fichiers")
            else:
                from app_config import resolve_paths
                rp_ac = resolve_paths(addon_reforger)
                if not rp_ac.get("valid"):
                    st.error(f"❌ Chemin addon invalide : {rp_ac.get('error')}")
                else:
                    terrain_dir_ac = Path(rp_ac["terrain_dir"])
                    data_dir_ac    = terrain_dir_ac / ".Data"
                    editor_dir_ac  = terrain_dir_ac / ".EditorData"
                    terr_path_ac   = terrain_dir_ac / "terrain.terr"

                    # Sélection run masques
                    masks_runs = sorted(
                        [d for d in (proj_path / "outputs" / "masks").iterdir()
                         if d.is_dir() and d.name != "latest"],
                        reverse=True
                    ) if (proj_path / "outputs" / "masks").exists() else []
                    run_options = ["latest"] + [d.name for d in masks_runs]
                    selected_run_ac = st.selectbox(
                        "Run à analyser", run_options, key="ac_run_select"
                    )
                    latest_dir_ac = proj_path / "outputs" / "masks" / "latest"
                    masks_dir_ac = latest_dir_ac if selected_run_ac == "latest" else proj_path / "outputs" / "masks" / selected_run_ac

                    output_png_ac  = proj_path / "outputs" / "reports" / "conflicts.png"
                    output_json_ac = proj_path / "outputs" / "reports" / "conflicts.json"

                    if st.button("▶️ Analyser conflits", key="btn_analyse_conflicts"):
                        if not masks_dir_ac.exists():
                            st.error(f"❌ Dossier masques introuvable : {masks_dir_ac}")
                        elif not terr_path_ac.exists():
                            st.error(f"❌ terrain.terr introuvable : {terr_path_ac}")
                        else:
                            with st.spinner("Analyse en cours..."):
                                import analyse_conflicts as ac
                                import importlib, io, contextlib
                                importlib.reload(ac)
                                ac.DATA_DIR        = data_dir_ac
                                ac.EDITOR_DATA_DIR = editor_dir_ac
                                ac.TERR_PATH       = terr_path_ac
                                output_png_ac.parent.mkdir(parents=True, exist_ok=True)
                                buf = io.StringIO()
                                with contextlib.redirect_stdout(buf):
                                    surfaces_ac = ac.read_mats_from_terr(terr_path_ac)
                                    slots_act, mats_act = ac.read_current_state(surfaces_ac)
                                    masks_ac = ac.load_masks(masks_dir_ac)
                                    slots_masks, masks_per_bloc = ac.compute_masks_slots(masks_ac)
                                    analysis = ac.analyze_conflicts(slots_act, slots_masks, mats_act, masks_per_bloc, surfaces_ac)
                                    ac.generate_image(slots_act, slots_masks, output_png_ac)
                                    import json
                                    with open(output_json_ac, 'w', encoding='utf-8') as jf:
                                        json.dump(analysis, jf, indent=2, ensure_ascii=False)
                                st.session_state["ac_log"]      = buf.getvalue()
                                st.session_state["ac_summary"]  = analysis.get("summary", {})
                                st.session_state["ac_conflicts"] = analysis.get("conflits", [])
                                st.session_state["ac_output"]   = str(output_png_ac)
                            st.success("✅ Analyse terminée")
                            st.rerun()

                    # Résultats
                    if st.session_state.get("ac_summary"):
                        s = st.session_state["ac_summary"]
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("✅ OK", s.get("ok", 0))
                        col2.metric("🟦 OK existant", s.get("ok_existing", 0))
                        col3.metric("⚠️ Limite", s.get("limite", 0))
                        col4.metric("❌ Conflit", s.get("conflit", 0))

                    if st.session_state.get("ac_output") and Path(st.session_state["ac_output"]).exists():
                        st.image(st.session_state["ac_output"], caption="Carte des conflits", use_container_width=True)

                    conflicts_list = st.session_state.get("ac_conflicts", [])
                    only_conflicts = [c for c in conflicts_list if c.get("strategie", "").startswith("conflit")]
                    if only_conflicts:
                        with st.expander(f"🔍 Détail {len(only_conflicts)} blocs en conflit", expanded=False):
                            for c in only_conflicts[:50]:
                                st.text(
                                    f"Tuile ({c['tx']},{c['ty']}) T{c['tile_id']} "
                                    f"bloc ({c['lrs_x']},{c['lrs_y']}) — "
                                    f"{c['total']} slots "
                                    f"[{c['slots_actuels']} existants + {c['slots_masques']} masques] "
                                    f"mats: {', '.join(c['mats_existants'][:3])}"
                                )
                            if len(only_conflicts) > 50:
                                st.caption(f"... et {len(only_conflicts)-50} autres (voir conflicts.json)")

                    if st.session_state.get("ac_log"):
                        with st.expander("📋 Log analyse", expanded=False):
                            st.code(st.session_state["ac_log"][-3000:])
        with _v_report:
            st.markdown("#### 📊 Rapport projet — Vue synthétique")

            proj_path = Path(st.session_state.get("current_project_path", "."))
            paths = st.session_state.get("paths", {})

            # ── Statut projet ──────────────────────────────────────────────
            st.markdown("##### 🗺️ Heightmap")
            bm = st.session_state.get("base_map")
            if bm is not None:
                col1, col2, col3 = st.columns(3)
                col1.metric("Résolution", f"{getattr(bm, 'cellsize', '?')} m/px")
                col2.metric("Altitude min", f"{getattr(bm, 'dem_min', 0):.0f} m")
                col3.metric("Altitude max", f"{getattr(bm, 'dem_max', 0):.0f} m")
            else:
                st.warning("⚠️ Heightmap non chargée")

            st.divider()

            # ── Dernier run pipeline ───────────────────────────────────────
            st.markdown("##### ⚙️ Dernier run Pipeline")
            last_run = st.session_state.get("pipeline_last_run")
            if last_run:
                run_dir = proj_path / "outputs" / "masks" / last_run
                masks_files = sorted(run_dir.glob("*.png")) if run_dir.exists() else []
                col1, col2 = st.columns(2)
                col1.metric("Run", last_run)
                col2.metric("Masques générés", len(masks_files))
                if masks_files:
                    with st.expander("Liste masques", expanded=False):
                        for f in masks_files:
                            st.text(f"  • {f.name}")
            else:
                st.info("Aucun run pipeline effectué dans cette session.")

            st.divider()

            # ── Résumé Simulate ────────────────────────────────────────────
            st.markdown("##### 🔬 Simulation budget slots")
            sim_log = st.session_state.get("sim_log")
            if sim_log:
                # Extraire stats depuis log
                lines = sim_log.splitlines()
                stats_lines = [l for l in lines if any(x in l for x in ["OK", "Limite", "Dépassement", "Critique", "%"])]
                if stats_lines:
                    st.code("\n".join(stats_lines[-8:]))
                else:
                    st.code(sim_log[-500:])
            else:
                st.info("Aucune simulation effectuée dans cette session.")

            st.divider()

            # ── Résumé Conflits ────────────────────────────────────────────
            st.markdown("##### ⚠️ Analyse conflits")
            ac_summary = st.session_state.get("ac_summary")
            if ac_summary:
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("✅ OK", ac_summary.get("ok", 0))
                col2.metric("🟦 OK existant", ac_summary.get("ok_existing", 0))
                col3.metric("⚠️ Limite", ac_summary.get("limite", 0))
                col4.metric("❌ Conflit", ac_summary.get("conflit", 0))
            else:
                st.info("Aucune analyse de conflits effectuée dans cette session.")

            st.divider()

            # ── État chemins ───────────────────────────────────────────────
            st.markdown("##### 📁 État des chemins")
            path_labels = {
                "heightmap":      "Heightmap",
                "exclusion_mask": "Masque exclusion",
                "gaea_flow":      "Flow Gaea",
                "gaea_deposit":   "Deposit Gaea",
                "exports_mask":   "Exports masques",
                "addon_reforger": "Addon Reforger",
                "catalog_json":   "Catalog.json",
            }
            col1, col2 = st.columns(2)
            for i, (key, label) in enumerate(path_labels.items()):
                val = paths.get(key, "")
                status = "✅" if val else "⚠️"
                (col1 if i % 2 == 0 else col2).text(f"{status} {label}: {val if val else '(non configuré)'}")

            st.divider()

            # ── Export rapport JSON ────────────────────────────────────────
            st.markdown("##### 💾 Export rapport")
            if st.button("📥 Exporter rapport JSON", key="btn_export_rapport"):
                import json
                from datetime import datetime
                rapport = {
                    "generated_at": datetime.now().isoformat(),
                    "project": st.session_state.get("current_project_name", ""),
                    "heightmap": {
                        "cellsize": getattr(bm, "cellsize", None) if bm else None,
                        "dem_min":  getattr(bm, "dem_min", None) if bm else None,
                        "dem_max":  getattr(bm, "dem_max", None) if bm else None,
                    },
                    "pipeline_last_run": last_run,
                    "masks_generated": len(masks_files) if last_run and run_dir.exists() else 0,
                    "simulate_summary": st.session_state.get("sim_log", "")[-500:],
                    "conflicts_summary": ac_summary or {},
                    "paths": paths,
                }
                rapport_path = proj_path / "outputs" / "reports" / "rapport_projet.json"
                rapport_path.parent.mkdir(parents=True, exist_ok=True)
                with open(rapport_path, "w", encoding="utf-8") as f:
                    json.dump(rapport, f, indent=2, ensure_ascii=False)
                st.success(f"✅ Rapport exporté → outputs/reports/rapport_projet.json")

    # ========================================================================
    # ONGLET TERRAIN BINAIRE — Inspect / Scan / QTRE
    # ========================================================================

    if active_tab == "terrain":
        st.markdown("### 🗺️ Terrain Binaire — Grille QTRE 32×32")

        # Chemins depuis session_state (configurés dans la sidebar)
        rp = st.session_state.get("resolved_paths", {})
        terrain_dir = Path(rp["terrain_dir"]) if rp.get("valid") and rp.get("terrain_dir") else None
        data_dir = terrain_dir / ".Data" if terrain_dir else None
        # Cache JSON scopé par projet courant
        proj_path = st.session_state.get("current_project_path")
        cache_json = Path(proj_path) / "cache" / "qtre_scan.json" if proj_path else None

        # Budget QTRE
        budget = st.radio(
            "Budget textures",
            options=[5, 7],
            index=1,
            format_func=lambda x: f"{x} — {'Reforger défaut' if x == 5 else 'Zimnitrita'}",
            horizontal=True,
            key="ttile_budget"
        )

        # Bloc scan
        if data_dir and data_dir.exists():
            n_ttiles = len(list(data_dir.glob("Terrain_*.ttile")))
            st.caption(f"📦 {n_ttiles} fichiers .ttile détectés dans `.Data`")

            col_scan1, col_scan2 = st.columns([2, 3])
            with col_scan1:
                if cache_json and cache_json.exists():
                    import json as _json
                    _meta = _json.load(open(cache_json, encoding="utf-8"))
                    st.success(f"✅ Cache : {len(_meta['tiles'])} tuiles — {_meta['generated_at'][:10]}")
                    if st.button("🔄 Rescanner", key="ttile_rescan"):
                        cache_json.unlink()
                        st.rerun()
                else:
                    st.warning("⚠️ Pas de cache — lancer le scan")
                    if st.button("🔍 Scanner toutes les tuiles", key="ttile_scan"):
                        tile_inspector_path = Path(__file__).parent / "tile_inspector.py"
                        if not tile_inspector_path.exists():
                            st.error(f"❌ tile_inspector.py introuvable : {tile_inspector_path}")
                        else:
                            cache_json.parent.mkdir(parents=True, exist_ok=True)
                            import subprocess, os
                            with st.spinner(f"Scan de {n_ttiles} tuiles en cours..."):
                                result = subprocess.run(
                                    [sys.executable, str(tile_inspector_path),
                                     "--tiles-dir", str(data_dir),
                                     "--export-json", str(cache_json)],
                                    capture_output=True, text=True,
                                    env={**os.environ, "PYTHONIOENCODING": "utf-8"}
                                )
                            if result.returncode == 0:
                                st.success("✅ Scan terminé")
                                st.rerun()
                            else:
                                st.error(f"❌ Erreur :\n{result.stderr[:500]}")
        else:
            st.warning("⚠️ Dossier .Data introuvable — vérifier le chemin terrain dans la sidebar")

        # ═══════════════════════════════════════════════════════════════════
        # Affichage satmap avec quadrillage SVG
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("#### 🗺️ Satmap avec quadrillage 32×32")

        import base64

        # Chemin satmap depuis le projet courant
        proj_path = st.session_state.get("current_project_path")
        satmap_path = Path(proj_path) / "sources" / "satmap_fond_512.png" if proj_path else None

        # Charger JSON scan si disponible
        scan_tiles_js = "null"
        scan_info = ""
        if cache_json and cache_json.exists():
            import json as _json
            scan_data = _json.load(open(cache_json, encoding="utf-8"))
            scan_tiles_js = _json.dumps(scan_data["tiles"])
            scan_info = f"{len(scan_data['tiles'])} tuiles scannées — {scan_data['generated_at'][:10]}"
            st.caption(f"✅ Cache : {scan_info}")

        if satmap_path and satmap_path.exists():
            # Encoder en base64 pour embarquer dans le HTML
            with open(satmap_path, "rb") as f:
                satmap_b64 = base64.b64encode(f.read()).decode()

            satmap_ext = satmap_path.suffix.lower().replace(".", "")  # "png" ou "jpg"

            GRID_HTML = f"""
<style>
.wrap{{position:relative;display:inline-block;line-height:0;border:1px solid #333;border-radius:4px;overflow:hidden}}
.wrap img{{width:576px;height:576px;display:block;image-rendering:pixelated}}
.overlay{{position:absolute;top:0;left:0;width:576px;height:576px;display:grid;grid-template-columns:repeat(32,18px);grid-template-rows:repeat(32,18px)}}
.cell{{width:18px;height:18px;box-sizing:border-box;cursor:pointer;border:0.5px solid rgba(255,255,255,0.08)}}
.cell:hover{{border:1.5px solid rgba(255,255,255,0.9);z-index:10;position:relative}}
#det{{margin-top:8px;padding:10px;background:#1e1e1e;border-radius:4px;color:#eee;font-size:13px;min-height:48px;font-family:monospace}}
</style>

<div class="wrap">
  <img src="data:image/{satmap_ext};base64,{satmap_b64}"/>
  <div class="overlay" id="grid"></div>
</div>
<div id="det">Cliquer sur une tuile.</div>

<script>
const BUDGET = {budget};
const RAW = {scan_tiles_js};

const byTid = {{}};
if (RAW) RAW.forEach(t => byTid[t.tid] = t);

function col(t) {{
  if (!t) return 'rgba(120,120,120,0.18)';
  const v = t.max_tex_per_block;
  if (v < BUDGET)     return 'rgba(74,222,128,0.45)';
  if (v === BUDGET)   return 'rgba(250,204,21,0.55)';
  if (v === BUDGET+1) return 'rgba(249,115,22,0.65)';
  return 'rgba(239,68,68,0.75)';
}}

const grid = document.getElementById('grid');
// ty=31 en haut (row 0), ty=0 en bas (row 31)
for (let row = 0; row < 32; row++) {{
  const ty = 31 - row;
  for (let tx = 0; tx < 32; tx++) {{
    const tid = ty * 32 + tx;
    const t = byTid[tid] || null;
    const el = document.createElement('div');
    el.className = 'cell';
    el.style.background = col(t);
    el.title = 'T' + tid + ' (' + tx + ',' + ty + ')' + (t ? ' — max=' + t.max_tex_per_block : ' — non scanné');
    el.onclick = () => {{
      document.querySelectorAll('.cell').forEach(c => c.style.outline='');
      el.style.outline = '2px solid #fff';
      if (!t) {{
        document.getElementById('det').textContent = 'Tuile ' + tid + ' (' + tx + ',' + ty + ') — non scannée';
      }} else {{
        const v = t.max_tex_per_block;
        const lb = v < BUDGET ? 'OK' : v === BUDGET ? 'Limite' : v === BUDGET+1 ? 'Critique' : 'Dépassement';
        document.getElementById('det').innerHTML =
          '<b>Tuile ' + tid + '</b> (' + tx + ',' + ty + ') &nbsp;→&nbsp; <b>' + lb + '</b>'
          + ' &nbsp;|&nbsp; max_tex=' + v
          + ' &nbsp;|&nbsp; budget=' + BUDGET
          + ' &nbsp;|&nbsp; matériaux=' + t.n_active_mats
          + '<br>Terrain_' + tid + '.ttile';
      }}
    }};
    grid.appendChild(el);
  }}
}}
</script>
"""

            import streamlit.components.v1 as components
            components.html(GRID_HTML, height=640, scrolling=False)
        else:
            st.info("Satmap non trouvée — placer `satmap_fond_512.png` dans `sources/` du projet.")

        # ═══════════════════════════════════════════════════════════════════
        # Inspect tuile
        # ═══════════════════════════════════════════════════════════════════

        st.markdown("---")
        st.markdown("#### 🔍 Inspect tuile")

        col_inp, col_btn = st.columns([2, 1])
        with col_inp:
            inspect_coords = st.text_input(
                "Coordonnées tuile (tx,ty)",
                placeholder="ex: 24,16",
                key="ttile_inspect_coords"
            )
        with col_btn:
            st.write("")
            do_inspect = st.button("Générer inspect", key="btn_inspect_tile")

        if do_inspect and inspect_coords:
            try:
                tx_i, ty_i = map(int, inspect_coords.strip().split(","))
                clean_weights_path = Path(__file__).parent / "clean_weights.py"
                import subprocess, os
                with st.spinner(f"Inspect tuile ({tx_i},{ty_i})..."):
                    result = subprocess.run(
                        [sys.executable, str(clean_weights_path),
                         "--inspect", f"{tx_i},{ty_i}"],
                        capture_output=True, text=True,
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
                    )
                # Debug : afficher stdout/stderr
                st.caption(f"Return code: {result.returncode}")
                if result.stdout:
                    with st.expander("📋 Stdout", expanded=False):
                        st.code(result.stdout[-2000:])
                if result.stderr:
                    with st.expander("⚠️ Stderr", expanded=False):
                        st.code(result.stderr[-2000:])

                # L'image est générée par clean_weights.py dans H:\logiciel perso\
                import shutil

                temp_img = Path(__file__).parent.parent / f"tile_{tx_i}_{ty_i}_cleanup.png"
                temp_img = temp_img.resolve()  # Convertir en chemin absolu

                st.caption(f"🔍 Chemin source : {temp_img}")
                st.caption(f"🔍 Fichier existe : {temp_img.exists()}")

                # Copier vers le dossier du projet
                proj_path = st.session_state.get("current_project_path")
                if proj_path:
                    dest_dir = Path(proj_path) / "outputs" / "generated" / "tiles"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_img = dest_dir / f"tile_{tx_i}_{ty_i}_cleanup.png"

                    if temp_img.exists():
                        shutil.copy2(temp_img, dest_img)
                        st.success(f"✅ Image sauvée : `{dest_img.relative_to(Path(proj_path))}`")
                        st.image(str(dest_img),
                                 caption=f"Tile {ty_i*32+tx_i} ({tx_i},{ty_i})",
                                 use_container_width=True)
                    else:
                        st.error(f"❌ Image source non trouvée : {temp_img}")
                        # Chercher l'image dans d'autres emplacements possibles
                        alt_paths = [
                            Path("H:/logiciel perso") / f"tile_{tx_i}_{ty_i}_cleanup.png",
                            Path(__file__).parent / f"tile_{tx_i}_{ty_i}_cleanup.png",
                        ]
                        for alt in alt_paths:
                            if alt.exists():
                                st.info(f"✅ Trouvée à : {alt}")
                                shutil.copy2(alt, dest_img)
                                st.image(str(dest_img),
                                         caption=f"Tile {ty_i*32+tx_i} ({tx_i},{ty_i})",
                                         use_container_width=True)
                                break
                else:
                    st.error("❌ Projet non chargé")
            except ValueError:
                st.error("Format invalide — entrer tx,ty (ex: 24,16)")

    # ========================================================================
    # ========================================================================
    # ONGLET CORRECTIONS — Scan zone / Clean / Force-mat
    # ========================================================================

    if active_tab == "corrections":
        st.markdown("### 🔧 Correction Terrain — Lecture & Diagnostic")

        paths = st.session_state.get("paths", {})
        addon_reforger = paths.get("addon_reforger", "")
        if not addon_reforger:
            st.info("📁 Configurez le chemin addon dans Heightmap → Chemins & fichiers")
            st.stop()

        from app_config import resolve_paths
        rp_c = resolve_paths(addon_reforger)
        if not rp_c.get("valid"):
            st.error(f"❌ Chemin addon invalide : {rp_c.get('error')}")
            st.stop()

        terrain_dir_c = Path(rp_c["terrain_dir"])
        data_dir_c    = terrain_dir_c / ".Data"
        editor_dir_c  = terrain_dir_c / ".EditorData"
        surfaces      = st.session_state.get("terr_materials", [])

        if not surfaces and rp_c.get("terr_file"):
            try:
                from terrain_terr_reader import read_mats_from_terr
                surfaces = read_mats_from_terr(rp_c["terr_file"])
                st.session_state["terr_materials"] = surfaces
            except Exception as e:
                st.warning(f"⚠️ Impossible de lire le .terr : {e}")

        from clean_weights import (
            mode_scan, mode_scan_zone,
            mode_inspect, mode_weights, mode_validate
        )

        _cw_scan, _cw_scan_zone, _cw_inspect = st.tabs([
            "🔍 Scan global", "🗺️ Scan zone", "🔎 Inspect tuile"
        ])

        with _cw_scan:
            st.markdown("#### Scan global — Détection slots négligeables")
            threshold = st.slider(
                "Seuil coverage (%)", 0.5, 5.0, 1.0, 0.5,
                key="cw_threshold",
                help="Slots dont la couverture est inférieure à ce seuil seront signalés"
            ) / 100.0
            if st.button("🔍 Lancer le scan", key="btn_cw_scan"):
                with st.spinner("Scan en cours..."):
                    import io, contextlib
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        mode_scan(data_dir_c, editor_dir_c, threshold)
                    st.session_state["cw_scan_output"] = buf.getvalue()
            if st.session_state.get("cw_scan_output"):
                with st.expander("📋 Résultat scan", expanded=True):
                    st.code(st.session_state["cw_scan_output"][-3000:])

        with _cw_scan_zone:
            st.markdown("#### Scan par zone (masque PNG)")
            uploaded_zone = st.file_uploader(
                "Masque de zone (blanc = zone active)",
                type=["png"], key="upload_zone_mask"
            )
            if uploaded_zone and st.button("🔍 Scan zone", key="btn_cw_scan_zone"):
                proj_path = Path(st.session_state.current_project_path)
                mask_path = proj_path / "masks" / uploaded_zone.name
                mask_path.parent.mkdir(parents=True, exist_ok=True)
                mask_path.write_bytes(uploaded_zone.getvalue())
                with st.spinner("Scan zone en cours..."):
                    import io, contextlib
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        mode_scan_zone(mask_path, data_dir_c, editor_dir_c, surfaces)
                    st.session_state["cw_zone_output"] = buf.getvalue()
            if st.session_state.get("cw_zone_output"):
                with st.expander("📋 Résultat", expanded=True):
                    st.code(st.session_state["cw_zone_output"][-3000:])

        with _cw_inspect:
            st.markdown("#### Inspection par tuile")
            col_i1, col_i2 = st.columns(2)
            with col_i1:
                inspect_coords = st.text_input(
                    "Coordonnées tuile (tx,ty)", placeholder="ex: 24,16",
                    key="cw_inspect_coords"
                )
            with col_i2:
                inspect_op = st.radio(
                    "Mode", ["Inspect", "Weights", "Validate"],
                    horizontal=True, key="cw_inspect_op"
                )
            if st.button("🔎 Lancer", key="btn_cw_inspect"):
                try:
                    tx_i, ty_i = map(int, inspect_coords.strip().split(","))
                    with st.spinner(f"{inspect_op} tuile ({tx_i},{ty_i})..."):
                        import io, contextlib
                        buf = io.StringIO()
                        with contextlib.redirect_stdout(buf):
                            if inspect_op == "Inspect":
                                mode_inspect(tx_i, ty_i, data_dir_c, editor_dir_c, surfaces, threshold=0.01)
                            elif inspect_op == "Weights":
                                mode_weights(tx_i, ty_i, data_dir_c, editor_dir_c, surfaces)
                            else:
                                mode_validate(tx_i, ty_i, data_dir_c, editor_dir_c, surfaces)
                        st.session_state["cw_inspect_output"] = buf.getvalue()
                except ValueError:
                    st.error("Format invalide — entrer tx,ty (ex: 24,16)")
            if st.session_state.get("cw_inspect_output"):
                with st.expander("📋 Résultat", expanded=True):
                    st.code(st.session_state["cw_inspect_output"][-3000:])


# ── Auto-sauvegarde ───────────────────────────────────────────────────────────
if st.session_state.get("current_project_path") and st.session_state.get("current_project"):
    try:
        save_project()
    except Exception:
        pass

    # ========================================================================
    # ========================================================================
    # ANCIEN ONGLET PIPELINE UNIFIÉ — Supprimé v6.0 (fusionné dans Pipeline)
    # ========================================================================

    if False:  # Désactivé - code conservé pour référence
        st.markdown("### ⚙️ Pipeline Unifié — Génération Masques Terrain")

        st.markdown("""
        **Pipeline unifié** combinant les fonctionnalités de `pipeline_v2`, `v3` et `v4` :
        - [1] Lecture heightmap .asc
        - [2] Calcul terrain (slope, fBm, coastal)
        - [3] Génération masques de base
        - [4] Végétation
        - [5] Application masque exclusion
        - [6] Normalisation exclusive
        - [7] Arbitrage budget (fusion textures existantes + masques)
        - [8] Export masques 4096×4096
        """)

        # Configuration fichiers
        st.markdown("#### Configuration Pipeline")

        col_p1, col_p2 = st.columns(2)

        with col_p1:
            st.text_input(
                "Heightmap .asc",
                key="_pipeline_asc_path",
                help="Chemin vers le fichier .asc de la heightmap"
            )
            st.text_input(
                "Dossier de sortie",
                key="_pipeline_output_dir",
                help="Dossier où exporter les masques 4096×4096"
            )
            st.text_input(
                "Masque exclusion (optionnel)",
                key="_pipeline_exclusion_mask",
                help="Masque Zone B PNG (blanc = exclusion)"
            )

        with col_p2:
            st.text_input(
                "Gaea Flow (optionnel)",
                key="_pipeline_gaea_flow",
                help="Masque flow depuis Gaea"
            )
            st.text_input(
                "Gaea Deposit (optionnel)",
                key="_pipeline_gaea_deposit",
                help="Masque deposit depuis Gaea"
            )
            st.number_input(
                "Budget max par bloc",
                min_value=1,
                max_value=8,
                value=6,
                key="_pipeline_budget_max",
                help="Nombre max de textures par bloc (QTRE limite = 6)"
            )

        # Bouton exécution
        if st.button("▶️ Exécuter Pipeline Unifié", type="primary"):
            asc_path = st.session_state.get("_pipeline_asc_path", "")
            output_dir = st.session_state.get("_pipeline_output_dir", "")

            if not asc_path or not output_dir:
                st.error("❌ Chemin heightmap et dossier de sortie obligatoires")
            else:
                asc_file = Path(asc_path)
                if not asc_file.exists():
                    st.error(f"❌ Fichier heightmap introuvable : {asc_file}")
                else:
                    with st.spinner("⚙️ Exécution pipeline unifié..."):
                        try:
                            # Import dynamique pour éviter de charger si non utilisé
                            import pipeline_unified as pu

                            # Configuration
                            pu.ASC_PATH = asc_file
                            pu.OUTPUT_DIR = Path(output_dir)
                            pu.BUDGET_MAX = st.session_state.get("_pipeline_budget_max", 6)

                            # Masque exclusion
                            excl_path = st.session_state.get("_pipeline_exclusion_mask", "")
                            pu.EXCLUSION_MASK = Path(excl_path) if excl_path else None

                            # Gaea
                            gaea_flow = st.session_state.get("_pipeline_gaea_flow", "")
                            pu.GAEA_FLOW = Path(gaea_flow) if gaea_flow else None

                            gaea_deposit = st.session_state.get("_pipeline_gaea_deposit", "")
                            pu.GAEA_DEPOSIT = Path(gaea_deposit) if gaea_deposit else None

                            # Logging en temps réel
                            log_container = st.empty()
                            logs = []

                            # Exécution modules
                            logs.append("[1/8] Chargement heightmap...")
                            log_container.text_area("Logs Pipeline", "\n".join(logs), height=300)
                            dem, cellsize = pu.load_heightmap_asc(pu.ASC_PATH)
                            logs.append(f"       Heightmap chargée : {dem.shape[0]}×{dem.shape[1]} pixels, cellsize={cellsize}m")

                            logs.append("[2/8] Calcul terrain...")
                            log_container.text_area("Logs Pipeline", "\n".join(logs), height=300)
                            terrain = pu.module_terrain(dem, cellsize)
                            logs.append(f"       Terrain calculé")

                            logs.append("[3/8] Génération masques de base...")
                            log_container.text_area("Logs Pipeline", "\n".join(logs), height=300)
                            masques = pu.module_masques_base(dem, terrain)
                            logs.append(f"       {len(masques)} masques de base générés")

                            logs.append("[4/8] Génération végétation...")
                            log_container.text_area("Logs Pipeline", "\n".join(logs), height=300)
                            masques_veg = pu.module_vegetation(dem, terrain)
                            masques.update(masques_veg)
                            logs.append(f"       {len(masques_veg)} masques végétation générés")

                            logs.append("[5/8] Application masque exclusion...")
                            log_container.text_area("Logs Pipeline", "\n".join(logs), height=300)
                            masques = pu.module_exclusion(masques, pu.EXCLUSION_MASK)
                            logs.append(f"       Masque exclusion appliqué")

                            logs.append("[6/8] Normalisation exclusive...")
                            log_container.text_area("Logs Pipeline", "\n".join(logs), height=300)
                            masques = pu.module_normalize(masques)
                            logs.append(f"       Normalisation terminée")

                            logs.append("[7/8] Arbitrage budget...")
                            log_container.text_area("Logs Pipeline", "\n".join(logs), height=300)
                            surfaces = pu.read_mats_from_terr(pu.TERR_PATH) if pu.TERR_PATH.exists() else []
                            masques, blocs_corriges = pu.module_budget(masques, surfaces)
                            logs.append(f"       {blocs_corriges} blocs corrigés")

                            logs.append("[8/8] Export masques...")
                            log_container.text_area("Logs Pipeline", "\n".join(logs), height=300)
                            warnings = pu.module_export(masques, pu.OUTPUT_DIR)
                            logs.append(f"       {len(masques)} masques exportés dans {pu.OUTPUT_DIR}")

                            logs.append("")
                            logs.append("=" * 70)
                            logs.append("✅ PIPELINE TERMINÉ")
                            logs.append("=" * 70)
                            log_container.text_area("Logs Pipeline", "\n".join(logs), height=300)

                            st.success(f"✅ Pipeline terminé : {len(masques)} masques exportés dans {pu.OUTPUT_DIR}")

                            # Afficher carte budget
                            st.markdown("#### Carte Budget (simulée)")
                            budget_map = np.random.randint(0, 8, (128, 128), dtype=np.uint8)
                            budget_img = np.zeros((128*32, 128*32, 3), dtype=np.uint8)

                            for by in range(128):
                                for bx in range(128):
                                    slots = budget_map[by, bx]
                                    if slots == 0:
                                        color = (60, 60, 60)
                                    elif slots <= 5:
                                        color = (0, 180, 0)
                                    elif slots == 6:
                                        color = (255, 160, 0)
                                    else:
                                        color = (220, 0, 0)

                                    by_png = 127 - by
                                    y0 = by_png * 32
                                    x0 = bx * 32
                                    budget_img[y0:y0+32, x0:x0+32] = color

                            st.image(budget_img, caption="Carte budget par bloc (vert=OK, orange=limite, rouge=conflit)", width=600)

                        except Exception as e:
                            st.error(f"❌ Erreur pipeline : {e}")
                            import traceback
                            st.code(traceback.format_exc())

        st.markdown("---")
        st.markdown("""
        **Légende carte budget** :
        - 🟢 Vert : 0-5 slots (OK)
        - 🟠 Orange : 6 slots (limite QTRE)
        - 🔴 Rouge : >6 slots (conflit)
        - ⬛ Gris : Pas de texture
        """)

# ============================================================================
# FOOTER
# ============================================================================

st.divider()
st.markdown("""
<div style="text-align: center; color: gray; font-size: 0.9em;">
    <p><strong>Map Generator Pro v6.0</strong> — Navigation par cartes | Chemins centralisés | Pipeline unifié</p>
    <p>🗺️ 6 onglets thématiques | 🎯 Drag & drop natif | 💾 Sauvegarde auto | 🌐 Bilingue FR/EN</p>
    <p>© 2026 | Refonte v6.0 — 2026-08-02</p>
</div>
""", unsafe_allow_html=True)
