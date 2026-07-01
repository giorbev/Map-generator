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
from texture_layer_generator import TextureLayerGenerator
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

TEXTURE_COLORS = {
    # ═══ VANILLA GÉNÉRIQUE ═══
    "seabed"        : (55,  100, 155),
    "sulfur"        : (180, 70,  30),
    "beachgrass"    : (108, 142, 72),
    "coastal"       : (108, 142, 72),
    "pebble"        : (155, 148, 130),
    "grass_01"      : (68,  125, 52),
    "grass_02"      : (68,  125, 52),
    "grass_03"      : (75,  110, 48),
    "mountaingrass" : (88,  108, 68),
    "mountain"      : (88,  108, 68),
    "heather"       : (115, 90,  82),
    "deciduous"     : (42,  78,  35),
    "conifer"       : (22,  55,  20),
    "pine"          : (22,  55,  20),
    "clearing"      : (68,  102, 52),
    "dirt_01"       : (139, 105, 70),
    "dirt_02"       : (139, 105, 70),
    "dirt_03"       : (122, 105, 82),
    "debris_rock"   : (122, 105, 82),
    "debris_coal"   : (115, 108, 98),
    "rock"          : (108, 105, 98),
    "crop_field_01" : (138, 130, 68),
    "crop_field_02" : (148, 138, 72),
    "asphalt"       : (90,  90,  90),
    "concrete"      : (90,  90,  90),
    "cobblestone"   : (90,  90,  90),

    # ═══ ZI ZIMNITRITA SPÉCIFIQUE ═══
    # Urbain ZI
    "asphalt1"             : (58,  58,  60),
    "concrete1"            : (112, 110, 108),
    "concrete2"            : (132, 130, 128),

    # Champs ZI
    "zi_crop_field_01"     : (140, 130, 95),
    "zi_crop_field_02"     : (135, 132, 90),
    "zi_crop_field_04"     : (122, 135, 105),
    "zi_crop_field_cut_01" : (78,  75,  68),
    "zi_crop_field_cut_02" : (105, 98,  82),

    # Sols spéciaux ZI
    "zi_ground"            : (62,  48,  58),
    "image_af93e7"         : (62,  48,  58),

    # Défaut
    "default"              : (128, 128, 128),
}


def get_texture_color(fname: str) -> tuple:
    """
    Retourne la couleur RGB d'une texture avec gestion fautes de frappe.

    Ordre de priorité : du plus spécifique au plus générique
    Gère les fautes courantes : montain/mountain, decidious/deciduous, etc.

    Args:
        fname: Nom de la texture (avec ou sans extension)

    Returns:
        Tuple RGB (r, g, b)
    """
    # Nettoyer le nom
    fname_clean = fname.lower()
    fname_clean = fname_clean.replace('.png', '')
    fname_clean = fname_clean.replace('mask_', '')
    fname_clean = fname_clean.replace('mask ', '')

    # Retirer préfixes forest communs
    fname_clean = fname_clean.replace('forest_floor_', '')
    fname_clean = fname_clean.replace('forest_base_', '')
    fname_clean = fname_clean.replace('forest_', '')
    fname_clean = fname_clean.replace('forestfloor', '')
    fname_clean = fname_clean.replace('forestbase', '')

    fname_clean = fname_clean.replace(' ', '_')
    fname_clean = fname_clean.strip('_ ')

    # Règles de détection par mots-clés
    # Ordre : du plus spécifique au plus générique

    # ZI spécifiques
    if 'zi_crop_field_cut' in fname_clean:
        return (78, 75, 68)
    if 'zi_crop_field_04' in fname_clean:
        return (122, 135, 105)
    if 'zi_crop_field' in fname_clean:
        return (140, 130, 95)
    if 'zi_ground' in fname_clean:
        return (62, 48, 58)
    if 'groundsport' in fname_clean:
        return (62, 48, 58)

    # Urbain
    if 'asphalt' in fname_clean:
        return (58, 58, 60)
    if 'concrete' in fname_clean:
        return (112, 110, 108)
    if 'cobblestone' in fname_clean or 'cobble' in fname_clean:
        return (82, 80, 76)

    # Champs
    if 'crop_field_cut' in fname_clean or 'cropfieldcut' in fname_clean:
        return (78, 75, 68)
    if 'crop_field' in fname_clean or 'cropfield' in fname_clean:
        return (138, 130, 68)

    # Fond marin
    if 'seabed' in fname_clean or 'sea_bed' in fname_clean:
        return (55, 100, 155)

    # Volcanique
    if 'sulfur' in fname_clean or 'volcan' in fname_clean:
        return (180, 70, 30)

    # Côtier
    if 'beachgrass' in fname_clean or 'beach_grass' in fname_clean:
        return (108, 142, 72)
    if 'coastal' in fname_clean:
        return (108, 142, 72)

    # Galets
    if 'pebble' in fname_clean or 'peeble' in fname_clean:
        return (155, 148, 130)

    # Forêt feuillue
    if 'deciduous' in fname_clean or 'decidious' in fname_clean \
       or 'decidous' in fname_clean or 'feuillus' in fname_clean \
       or 'feuillue' in fname_clean:
        return (42, 78, 35)

    # Forêt conifères
    if 'coniferous' in fname_clean or 'conifer' in fname_clean \
       or 'conifere' in fname_clean:
        return (22, 55, 20)
    if 'pine' in fname_clean or 'pin_' in fname_clean:
        return (22, 55, 20)

    # Lisière / Clairière
    if 'clearing' in fname_clean or 'lisiere' in fname_clean \
       or 'clairiere' in fname_clean:
        return (68, 102, 52)

    # Heather / Bruyère
    if 'heather' in fname_clean:
        return (115, 90, 82)

    # Mountain grass / Lande
    # Gérer faute "montain" aussi
    if 'mountaingrass' in fname_clean \
       or 'mountain_grass' in fname_clean \
       or 'montaingrass' in fname_clean \
       or 'montain_grass' in fname_clean \
       or 'mountain' in fname_clean \
       or 'montain' in fname_clean:
        return (88, 108, 68)

    # Herbe prairie
    if 'grass_03_aut' in fname_clean or 'grass3_aut' in fname_clean:
        return (75, 110, 48)
    if 'grass_03' in fname_clean or 'grass3' in fname_clean:
        return (75, 110, 48)
    if 'grass_02' in fname_clean or 'grass2' in fname_clean:
        return (68, 125, 52)
    if 'grass_01' in fname_clean or 'grass1' in fname_clean:
        return (68, 125, 52)
    if 'grass' in fname_clean:
        return (68, 125, 52)

    # Érosion / Débris
    if 'debris_rock' in fname_clean or 'debrisrock' in fname_clean:
        return (122, 105, 82)
    if 'debris_coal' in fname_clean or 'debriscoal' in fname_clean:
        return (115, 108, 98)
    if 'coal' in fname_clean:  # Variante debris_coal
        return (115, 108, 98)

    # Terre
    if 'dirt' in fname_clean:
        return (139, 105, 70)

    # Roche
    if 'rock' in fname_clean:
        return (108, 105, 98)

    # Défaut
    if 'forest' in fname.lower() or 'foret' in fname.lower():
        print(f"[FOREST NON RECONNU] '{fname}' → nettoyé: '{fname_clean}' → GRIS")
    else:
        print(f"[WARNING] Texture non reconnue: '{fname}' (nettoyé: '{fname_clean}') → gris")
    return (128, 128, 128)


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

    # Carte végétation MODE 2
    vegetation_map_rel = pipeline_v2.get("vegetation_map")
    if vegetation_map_rel:
        veg_abs = p / vegetation_map_rel if not Path(vegetation_map_rel).is_absolute() else Path(vegetation_map_rel)
        st.session_state.vegetation_map = str(veg_abs) if veg_abs.exists() else None
    else:
        st.session_state.vegetation_map = None

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

    # Carte végétation MODE 2
    vegetation_map = st.session_state.get("vegetation_map")
    if vegetation_map:
        try:
            rel_veg = Path(vegetation_map).relative_to(p)
            data["pipeline_v2"]["vegetation_map"] = str(rel_veg).replace("\\", "/")
        except ValueError:
            data["pipeline_v2"]["vegetation_map"] = str(vegetation_map).replace("\\", "/")
    else:
        data["pipeline_v2"]["vegetation_map"] = None

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


def normalize_texture_name(filename: str) -> str:
    """
    Normalise nom de fichier texture pour éviter doublons.

    Exemples:
        mask Cropfield1.png       → cropfield
        mask_Crop_Field_01.png    → crop_field
        ZI_Crop_Field_03.png      → zi_crop_field
        error heather.png         → heather
        Concrete_02.png           → concrete
    """
    import re

    name = Path(filename).stem

    # Retirer préfixes communs
    prefixes = ["mask ", "mask_", "masl_", "error ", "error_"]
    for prefix in prefixes:
        if name.lower().startswith(prefix.lower()):
            name = name[len(prefix):]

    # Retirer suffixes numérotés (_01, _02, 1, 2, etc.)
    name = re.sub(r'[_\s]*\d+$', '', name)           # Fin : _1, _2, 1, 2
    name = re.sub(r'_0\d+$', '', name)                # Fin : _01, _02
    name = re.sub(r'[_\s]+0\d+$', '', name)          # Fin : _01, 01

    # Normaliser casse et espaces
    name = name.lower()
    name = name.replace(" ", "_")

    # Nettoyer underscores multiples
    name = re.sub(r'_+', '_', name)
    name = name.strip('_')

    return name if name else "texture"


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
    tab_terrain, tab_gen, tab_validation = st.tabs([
        " Terrain",
        " Génération",
        "[INFO] Validation Masks",
    ])
    
    # ========================================================================
    # ONGLET TERRAIN — sous-onglets : Hypsométrique / NatureMap / Analyse
    # ========================================================================

    with tab_terrain:
        _t_hypso, _t_analyse, _t_signaux, _t_debug = st.tabs([
            " Hypsométrique", "📈 Analyse", "🗺️ Signaux Terrain", "🐛 Masques Debug"
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
    # ONGLET MASQUES DEBUG — Visualisation curvature pour calibration seuils
    # ========================================================================

    with _t_debug:
        st.markdown("### 🐛 Masques Debug — Curvature")
        st.caption("Visualisation curvature pour calibrer les seuils sans regénérer tout le pipeline")

        terrain_data = st.session_state.get('terrain_data')

        if not terrain_data:
            st.warning("⚠️ Chargez une heightmap depuis la sidebar")
        else:
            st.divider()

            # Sliders pour percentiles
            st.markdown("#### ⚙️ Percentiles de détection")

            col_s1, col_s2 = st.columns(2)
            with col_s1:
                pct_concave = st.slider(
                    "Percentile concave (creux légers)",
                    min_value=5,
                    max_value=40,
                    value=20,
                    step=1,
                    help="Les X% de zones les plus concaves → dirt_erosion (P20 = 20%)"
                )
            with col_s2:
                pct_deep = st.slider(
                    "Percentile deep (creux profonds)",
                    min_value=5,
                    max_value=70,
                    value=10,
                    step=1,
                    help="Les X% de zones les plus concaves → debris_rock (P10 = 10%)"
                )

            st.divider()

            # Génération automatique en temps réel (pas de bouton)
            try:
                from pathlib import Path
                from PIL import Image
                import numpy as np
                from io import BytesIO

                curvature = terrain_data['curvature']

                # Calculer seuils percentiles
                curv_valid = curvature[~np.isnan(curvature)]
                seuil_concave = float(np.percentile(curv_valid, pct_concave))
                seuil_deep = float(np.percentile(curv_valid, pct_deep))

                # Stats temps réel
                total_px = curvature.size
                concave_px = int(np.sum(curvature < seuil_concave))
                deep_px = int(np.sum(curvature < seuil_deep))

                st.info(
                    f"**📊 Couverture temps réel :**  \n"
                    f"• Concave P{pct_concave} (≤ {seuil_concave:.4f}) : {concave_px:,} px ({concave_px/total_px*100:.1f}%)  \n"
                    f"• Deep P{pct_deep} (≤ {seuil_deep:.4f}) : {deep_px:,} px ({deep_px/total_px*100:.1f}%)"
                )

                st.divider()
                st.markdown("#### 🖼️ Aperçu (temps réel)")

                # Générer images en mémoire (pas de fichier)
                # 1. Curvature complète
                p1  = np.percentile(curv_valid, 1)
                p99 = np.percentile(curv_valid, 99)
                curv_viz = np.clip(
                    (curvature - p1) / (p99 - p1) * 255, 0, 255
                ).astype(np.uint8)

                # 2. Concave
                concave = (curvature < seuil_concave).astype(np.uint8) * 255

                # 3. Deep
                deep = (curvature < seuil_deep).astype(np.uint8) * 255

                # Afficher en colonnes
                col_v1, col_v2, col_v3 = st.columns(3)

                with col_v1:
                    st.caption("**Curvature complète**  \n(P1-P99 normalisé)")
                    st.image(curv_viz, use_column_width=True)

                with col_v2:
                    st.caption(f"**Concave P{pct_concave}**  \n≤ {seuil_concave:.4f}")
                    st.image(concave, use_column_width=True)

                with col_v3:
                    st.caption(f"**Deep P{pct_deep}**  \n≤ {seuil_deep:.4f}")
                    st.image(deep, use_column_width=True)

                # Boutons export et sauvegarde
                st.divider()
                col_btn1, col_btn2 = st.columns(2)

                with col_btn1:
                    if st.button("💾 Exporter PNG", help="Sauvegarder les masques dans debug/"):
                        project_path = st.session_state.get('current_project_path')
                        if project_path:
                            debug_dir = Path(project_path) / "debug"
                            debug_dir.mkdir(exist_ok=True)

                            Image.fromarray(curv_viz, mode='L').save(str(debug_dir / "curvature_full.png"))
                            Image.fromarray(concave, mode='L').save(str(debug_dir / f"curvature_concave_P{pct_concave}.png"))
                            Image.fromarray(deep, mode='L').save(str(debug_dir / f"curvature_deep_P{pct_deep}.png"))

                            st.success(f"✅ PNG exportés dans {debug_dir}")
                        else:
                            st.error("❌ Aucun projet chargé")

                with col_btn2:
                    if st.button("⚙️ Sauvegarder pour Pipeline", type="primary",
                                help="Sauvegarder ces percentiles - le pipeline les utilisera automatiquement"):
                        project_path = st.session_state.get('current_project_path')
                        if project_path:
                            import json
                            project_file = Path(project_path) / "project.json"

                            # Charger project.json
                            if project_file.exists():
                                with open(project_file, 'r', encoding='utf-8') as f:
                                    project = json.load(f)
                            else:
                                project = {}

                            # Sauvegarder percentiles curvature
                            if 'pipeline_v2' not in project:
                                project['pipeline_v2'] = {}

                            project['pipeline_v2']['curvature_percentiles'] = {
                                'debris_deep': pct_deep,
                                'dirt_concave': pct_concave
                            }

                            # Écrire project.json
                            with open(project_file, 'w', encoding='utf-8') as f:
                                json.dump(project, f, indent=2, ensure_ascii=False)

                            st.success(
                                f"✅ **Percentiles sauvegardés !**  \n"
                                f"• Debris (deep) : P{pct_deep}  \n"
                                f"• Dirt (concave) : P{pct_concave}  \n"
                                f"Le pipeline utilisera ces valeurs lors de la prochaine génération."
                            )
                        else:
                            st.error("❌ Aucun projet chargé")

            except Exception as e:
                st.error(f"❌ Erreur : {e}")
                import traceback
                st.code(traceback.format_exc())

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

        # ── Choix du mode ──────────────────────────────────────────────────
        mode_generation = st.radio(
            "Mode de génération",
            options=["mode1", "mode2"],
            format_func=lambda x: {
                "mode1": "🏔️ Mode 1 — Terrain pur (13 masks topographiques)",
                "mode2": "🌿 Mode 2 — Terrain + Végétation (15 masks enrichis biomes)"
            }[x],
            help="MODE 1 : Génération classique basée uniquement sur topographie\n"
                 "MODE 2 : Enrichit la topographie avec une carte de végétation"
        )

        if mode_generation == "mode1":
            st.caption("Génère 13 masks PNG 16-bit avec auto-calibration terrain")
            st.session_state['vegetation_map'] = None  # ← MODE 1 : pas de végétation
        else:
            st.caption("Génère 15 masks PNG 16-bit (forêts feuillus/conifères, heather) enrichis par carte végétation")

        st.divider()

        # ── MODE 2 : Source carte végétation ───────────────────────────────
        vegetation_map = None

        if mode_generation == "mode2":
            st.subheader("🌿 Source Carte Végétation")

            # ── AUTO-DÉTECTION carte végétation ──
            from pathlib import Path
            project_path = st.session_state.get('current_project_path')

            auto_detected = None
            auto_source = None

            if project_path:
                project_path = Path(project_path)
                veg_png_auto = project_path / "vegetation_map.png"
                veg_dir_auto = project_path / "vegetation_masks"

                # Priorité 1 : PNG coloré (plus simple)
                if veg_png_auto.exists():
                    auto_detected = str(veg_png_auto)
                    auto_source = "png_couleur"
                    st.info(f"ℹ️ Carte végétation détectée : `{veg_png_auto.name}`")
                # Priorité 2 : Dossier masks
                elif veg_dir_auto.exists() and veg_dir_auto.is_dir():
                    auto_detected = str(veg_dir_auto)
                    auto_source = "dossier_masks"
                    st.info(f"ℹ️ Dossier masks détecté : `{veg_dir_auto.name}/`")
                else:
                    st.warning(
                        "⚠️ Aucune carte végétation détectée  \n"
                        "💡 Générez-la dans l'onglet **Carte végétation potentielle**"
                    )

            # Radio button avec sélection auto
            default_source = auto_source if auto_source else "png_couleur"
            veg_source = st.radio(
                "Type de source végétation",
                options=["png_couleur", "dossier_masks"],
                index=0 if default_source == "png_couleur" else 1,
                format_func=lambda x: {
                    "dossier_masks": "📁 Dossier masks PNG extraits (7 zones)",
                    "png_couleur": "🎨 Carte PNG colorée (extraction automatique)"
                }[x],
                help="PNG coloré (recommandé) : 7 couleurs → 7 zones  \n"
                     "Dossier masks : 7 PNG pré-extraits"
            )

            if veg_source == "png_couleur":
                # Valeur par défaut : auto-détecté ou session_state
                default_png = auto_detected if auto_source == "png_couleur" else st.session_state.get('veg_png_path', '')

                veg_png = st.text_input(
                    "Chemin carte végétation PNG",
                    value=default_png,
                    placeholder="data/projects/[NOM]/vegetation_map.png",
                    help="PNG coloré généré par l'app ou manuel"
                )

                if veg_png:
                    veg_file = Path(veg_png)

                    if veg_file.exists() and veg_file.suffix.lower() == '.png':
                        st.session_state['veg_png_path'] = veg_png
                        st.session_state['vegetation_map'] = veg_png  # ← MODE 2 activé
                        st.success(f"✓ Fichier valide : {veg_file.name}")
                    else:
                        st.error("❌ Fichier PNG inexistant ou invalide")
                        st.session_state['vegetation_map'] = None  # Pas de MODE 2

            else:  # dossier_masks
                # Valeur par défaut : auto-détecté ou session_state
                default_dir = auto_detected if auto_source == "dossier_masks" else st.session_state.get('veg_masks_dir', '')

                veg_dir = st.text_input(
                    "Dossier masks végétation (7 PNG)",
                    value=default_dir,
                    placeholder="data/projects/[NOM]/vegetation_masks/",
                    help="Dossier contenant : eau.png, foret_mixte.png, etc."
                )

                if veg_dir:
                    veg_path = Path(veg_dir)

                    if veg_path.exists() and veg_path.is_dir():
                        st.session_state['veg_masks_dir'] = veg_dir
                        st.session_state['vegetation_map'] = veg_dir  # ← MODE 2 activé
                        veg_files = list(veg_path.glob("*.png"))
                        st.success(f"✓ Dossier valide : {len(veg_files)} fichiers PNG détectés")
                    else:
                        st.error("❌ Dossier inexistant ou invalide")
                        st.session_state['vegetation_map'] = None  # Pas de MODE 2

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

        # Afficher valeurs auto-calibrées vs recalculées
        if params_auto:
            st.markdown("**📊 Valeurs auto-calibrées depuis heightmap**")

            col_auto, col_recalc = st.columns(2)

            with col_auto:
                st.markdown("**AUTO (heightmap)**")
                st.info(
                    f"• Altitude côtière : {params_auto.get('coastal_alt_max_m', 0):.1f} m  \n"
                    f"• Grass low max : {params_auto.get('grass_low_max_m', 0):.1f} m  \n"
                    f"• Grass mid max : {params_auto.get('grass_mid_max_m', 0):.1f} m  \n"
                    f"• Grass high max : {params_auto.get('grass_high_max_m', 0):.1f} m  \n"
                    f"• Pente debris min : {params_auto.get('debris_min_deg', 0):.1f}°  \n"
                    f"• Pente roche min : {params_auto.get('rock_min_deg', 0):.1f}°"
                )

            with col_recalc:
                st.markdown("**RECALCULÉ (sliders)**")

                # Récupérer valeurs actuelles des sliders
                debris_current = st.session_state.get('pipeline_v2_debris_min', params_auto.get('debris_min_deg', 0))
                rock_current = st.session_state.get('pipeline_v2_rock_min', params_auto.get('rock_min_deg', 0))
                gradient_current = st.session_state.get('pipeline_v2_debris_gradient', 100)

                # Détecter changements
                debris_changed = abs(debris_current - params_auto.get('debris_min_deg', 0)) > 0.1
                rock_changed = abs(rock_current - params_auto.get('rock_min_deg', 0)) > 0.1

                st.success(
                    f"• Altitude côtière : {params_auto.get('coastal_alt_max_m', 0):.1f} m  \n"
                    f"• Grass low max : {params_auto.get('grass_low_max_m', 0):.1f} m  \n"
                    f"• Grass mid max : {params_auto.get('grass_mid_max_m', 0):.1f} m  \n"
                    f"• Grass high max : {params_auto.get('grass_high_max_m', 0):.1f} m  \n"
                    f"• Pente debris min : {debris_current:.1f}° {'⚡' if debris_changed else ''}  \n"
                    f"• Pente roche min : {rock_current:.1f}° {'⚡' if rock_changed else ''}  \n"
                    f"• Gradient debris : {gradient_current}m ⭐"
                )

            # Boutons
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("🔄 Recalculer valeurs AUTO", help="Recalculer les valeurs auto depuis la heightmap et réinitialiser sliders"):
                    if 'params_auto_v2' in st.session_state:
                        del st.session_state['params_auto_v2']
                    st.rerun()
            with col_btn2:
                if st.button("✅ Appliquer valeurs sliders", help="Mettre à jour l'affichage RECALCULÉ avec les valeurs actuelles des sliders"):
                    st.rerun()

        # ── Génération Pipeline V2 ─────────────────────────────────────────
        st.subheader("⚙️ Paramètres Pipeline V2")

        # COASTAL (côte)
        st.markdown("**🌊 Coastal**")
        col1, col2 = st.columns(2)
        with col1:
            coastal_distance = st.slider(
                "Distance côtière (m)",
                20, 200,
                value=int(st.session_state.get('pipeline_v2_coastal_distance', 60)),
                key="pipeline_v2_coastal_distance"
            )
        with col2:
            feather_coastal = st.slider(
                "Feather côtier (m)",
                5, 50,
                value=int(st.session_state.get('pipeline_v2_feather_coastal', 20)),
                key="pipeline_v2_feather_coastal"
            )

        # DEBRIS (débris rocheux)
        st.markdown("**🗻 Debris rock**")
        col1, col2 = st.columns(2)
        with col1:
            debris_min = st.slider(
                "Pente debris min (°)",
                5.0, 30.0,
                value=float(st.session_state.get('pipeline_v2_debris_min', params_auto.get('debris_min_deg', 18.0))),
                help="Valeur auto-calibrée depuis la heightmap (ajustable)",
                key="pipeline_v2_debris_min"
            )
        with col2:
            debris_gradient = st.slider(
                "Gradient debris (m)",
                50, 200,
                value=int(st.session_state.get('pipeline_v2_debris_gradient', 100)),
                step=10,
                key="pipeline_v2_debris_gradient",
                help="Distance max gradient érosion depuis rock"
            )

        # DIRT (érosion douce)
        st.markdown("**🌧️ Dirt erosion**")
        col1, col2 = st.columns(2)
        with col1:
            # Valeur par défaut = debris_min * 0.5
            default_dirt = float(st.session_state.get('pipeline_v2_debris_min', params_auto.get('debris_min_deg', 18.0))) * 0.5
            dirt_slope_min = st.slider(
                "Pente dirt min (°)",
                3.0, 20.0,
                value=float(st.session_state.get('pipeline_v2_dirt_slope_min', default_dirt)),
                help="Pente minimum pour dirt erosion (par défaut = debris_min * 0.5)",
                key="pipeline_v2_dirt_slope_min"
            )
        with col2:
            feather_dirt = st.slider(
                "Feather dirt (m)",
                5, 50,
                value=int(st.session_state.get('pipeline_v2_feather_dirt', 20)),
                key="pipeline_v2_feather_dirt"
            )

        # ROCK (parois rocheuses)
        st.markdown("**⛰️ Rock walls**")
        col1, col2 = st.columns(2)
        with col1:
            rock_min = st.slider(
                "Pente roche min (°)",
                15.0, 45.0,
                value=float(st.session_state.get('pipeline_v2_rock_min', params_auto.get('rock_min_deg', 28.0))),
                help="Valeur auto-calibrée depuis la heightmap (ajustable)",
                key="pipeline_v2_rock_min"
            )
        with col2:
            feather_rock = st.slider(
                "Feather roche (m)",
                5, 40,
                value=int(st.session_state.get('pipeline_v2_feather_rock', 20)),
                key="pipeline_v2_feather_rock"
            )

        # MUD/RIVER (rivières et boue)
        st.markdown("**💧 Mud/River**")
        col1, col2 = st.columns(2)
        with col1:
            flow_mud_pct = st.slider(
                "Flow mud (percentile)",
                70, 95,
                value=int(st.session_state.get('pipeline_v2_flow_mud_pct', 85)),
                help="Percentile écoulement pour mud (P85 = défaut)",
                key="pipeline_v2_flow_mud_pct"
            )
            tpi_mud_pct = st.slider(
                "TPI mud (percentile)",
                20, 60,
                value=int(st.session_state.get('pipeline_v2_tpi_mud_pct', 40)),
                help="Percentile TPI pour fonds de ravins (P40 = défaut)",
                key="pipeline_v2_tpi_mud_pct"
            )
        with col2:
            feather_mud = st.slider(
                "Feather mud (m)",
                5, 30,
                value=int(st.session_state.get('pipeline_v2_feather_mud', 15)),
                key="pipeline_v2_feather_mud"
            )

        # GRASS (herbe)
        st.markdown("**🌿 Grass**")
        feather_grass = st.slider(
            "Feather herbe (m)",
            5, 60,
            value=int(st.session_state.get('pipeline_v2_feather_grass', 20)),
            key="pipeline_v2_feather_grass"
        )

        # TPI (relief)
        st.markdown("**📐 TPI (relief)**")
        col1, col2 = st.columns(2)
        with col1:
            tpi_local = st.slider(
                "TPI local radius (m)",
                50, 300,
                value=int(st.session_state.get('pipeline_v2_tpi_local', 100)),
                key="pipeline_v2_tpi_local"
            )
        with col2:
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

                # Charger percentiles curvature depuis project.json (si sauvegardés via Debug)
                curv_pcts = {}
                project_file = Path(project_path) / "project.json"
                if project_file.exists():
                    import json
                    with open(project_file, 'r', encoding='utf-8') as f:
                        proj_data = json.load(f)
                        curv_pcts = proj_data.get('pipeline_v2', {}).get('curvature_percentiles', {})

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
                    "feather_dirt_m": feather_dirt,  # ← Feather dirt
                    "feather_forest_m": 40.0,
                    "feather_mud_m": feather_mud,  # ← Feather mud
                    "debris_gradient_distance_m": debris_gradient,  # ← Gradient érosion
                    "dirt_slope_min_deg": dirt_slope_min,  # ← Pente dirt
                    "flow_mud_percentile": flow_mud_pct,  # ← Flow mud
                    "tpi_mud_percentile": tpi_mud_pct,  # ← TPI mud
                    "curvature_percentiles": curv_pcts,  # ← Percentiles depuis Debug
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

                    # Récupérer vegetation_map depuis session_state
                    vegetation_map = st.session_state.get('vegetation_map', None)

                    _start = _time.time()
                    results = run_pipeline(
                        str(heightmap_path),
                        str(output_dir),
                        params,
                        terrain_data=terrain_data,  # ZÉRO recalcul si déjà calculé
                        vegetation_map=vegetation_map  # None=MODE1 / chemin=MODE2
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
                    n_masks = results.get('n_masks', 13)
                    mode = results.get('mode', 1)
                    st.success(
                        f"✅ **MODE {mode}** : {n_masks} masks générés  \n"
                        f"📁 {output_dir}"
                    )
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

    # ══════════════════════════════════════════════════════════════════════════════
    # POST-TRAITEMENT — Fusion Géographique Mappeur + Pipeline
    # ══════════════════════════════════════════════════════════════════════════════

    with _g_post:
        st.markdown("### 🗺️ Post-Traitement — Fusion Géographique")
        st.caption("**Principe** : Zones mappeur intactes | Zones naturelles = pipeline_v2 | 0% chevauchement")

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 1 : UPLOAD + APERÇU COLORÉ
        # ═══════════════════════════════════════════════════════════════════

        st.divider()
        st.markdown("#### 1️⃣ Upload Masks Reforger + Aperçu")

        uploaded_files = st.file_uploader(
            "📂 Masks PNG 16-bit exportés depuis Reforger",
            accept_multiple_files=True,
            type=['png'],
            key="post_upload_mappeur_v2"
        )

        if uploaded_files:
            mappeur_masks = {}

            with st.spinner("Chargement masks..."):
                for f in uploaded_files:
                    try:
                        arr = np.frombuffer(f.read(), np.uint8)
                        mask = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)

                        if mask is not None and mask.ndim == 2:
                            # Downsampling >4K
                            max_dim = 4096
                            h, w = mask.shape
                            if h > max_dim or w > max_dim:
                                scale = min(max_dim / h, max_dim / w)
                                new_h, new_w = int(h * scale), int(w * scale)
                                mask = cv2.resize(mask, (new_w, new_h), interpolation=cv2.INTER_AREA)

                            mappeur_masks[f.name] = mask

                    except Exception as e:
                        st.error(f"❌ {f.name}: {str(e)}")

            st.session_state['post_mappeur_masks'] = mappeur_masks
            st.success(f"✓ {len(mappeur_masks)} masks chargés")

            # Liste textures
            with st.expander("📋 Textures chargées"):
                for fname in sorted(mappeur_masks.keys()):
                    st.text(f"  → {fname}")

            # Aperçu optionnel (peut être lent avec beaucoup de textures)
            col_preview, col_boost = st.columns([3, 1])
            with col_preview:
                generate_preview = st.checkbox("Générer aperçu coloré", value=False, help="Peut être lent avec >20 textures")
            with col_boost:
                boost_dark = st.checkbox("Éclaircir couleurs", value=True, help="Rend les couleurs sombres plus visibles")

            if generate_preview:
                try:
                    from post_processing import generate_colored_preview

                    with st.spinner("Génération aperçu..."):
                        preview_rgb, legend = generate_colored_preview(
                            mappeur_masks,
                            get_texture_color,
                            boost_dark_colors=boost_dark
                        )

                        st.session_state['preview_rgb'] = preview_rgb
                        st.session_state['legend'] = legend

                    st.image(preview_rgb, caption="Aperçu textures", use_column_width=True)

                    # Légende avec carrés de couleur
                    st.markdown("#### 🎨 Légende couleurs")
                    cols = st.columns(4)
                    for idx, (tex_name, color) in enumerate(sorted(legend.items())):
                        with cols[idx % 4]:
                            # Carré de couleur
                            st.markdown(
                                f'<div style="display:flex;align-items:center;margin:3px 0;">'
                                f'<div style="width:15px;height:15px;background-color:rgb{color};border:1px solid #000;margin-right:5px;flex-shrink:0;"></div>'
                                f'<span style="font-size:11px;">{tex_name}</span>'
                                f'</div>',
                                unsafe_allow_html=True
                            )

                    # Debug : compter pixels par couleur
                    st.caption(f"**Debug:** {len(legend)} textures détectées")

                    # Compter noir
                    black_pixels = np.sum(np.all(preview_rgb == [0, 0, 0], axis=2))
                    gray_pixels = np.sum(np.all(preview_rgb == [128, 128, 128], axis=2))
                    total_pixels = preview_rgb.shape[0] * preview_rgb.shape[1]

                    if black_pixels > 0:
                        st.warning(f"⚠️ {black_pixels:,} pixels NOIRS ({black_pixels/total_pixels*100:.1f}%)")
                    if gray_pixels > 0:
                        st.info(f"ℹ️ {gray_pixels:,} pixels GRIS par défaut ({gray_pixels/total_pixels*100:.1f}%)")

                except Exception as e:
                    st.error(f"Erreur: {str(e)}")
            else:
                # Créer preview vide pour skip
                if 'preview_rgb' not in st.session_state:
                    h, w = list(mappeur_masks.values())[0].shape
                    st.session_state['preview_rgb'] = np.zeros((h, w, 3), dtype=np.uint8)
                    st.session_state['legend'] = {}

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 2 : SÉLECTION ZONES (Mode Simplifié)
        # ═══════════════════════════════════════════════════════════════════

        if st.session_state.get('post_mappeur_masks'):
            st.divider()
            st.markdown("#### 2️⃣ Sélection Zones à Garder")

            # Mode simple : Tout garder ou Auto-détection
            mode = st.radio(
                "Méthode de sélection",
                ["Fusion auto", "Fusion avec marge", "Fusion manuelle"],
                help="Choisissez comment combiner mappeur et pipeline"
            )

            # Descriptions selon mode sélectionné
            if mode == "Fusion auto":
                st.caption("💡 Garde tout le mappeur (urbain/champs/routes) + complète avec pipeline (nature)")
            elif mode == "Fusion avec marge":
                st.caption("💡 Détecte les zones mappeur + ajoute une marge autour, puis complète avec pipeline")
            else:
                st.caption("💡 Upload un masque zone PNG (blanc = mappeur, noir = pipeline)")

            h, w = list(st.session_state['post_mappeur_masks'].values())[0].shape

            if mode == "Fusion auto":
                # Tout en blanc = garder tout mappeur
                zone_mask = np.full((h, w), 255, dtype=np.uint8)
                st.session_state['zone_mask'] = zone_mask

                # DEBUG : Vérifier le masque
                blanc_pct = (np.sum(zone_mask == 255) / zone_mask.size) * 100
                st.success(f"✓ Zone : 100% mappeur gardé (shape={zone_mask.shape}, blanc={blanc_pct:.1f}%)")

            elif mode == "Fusion avec marge":
                # Union de tous les masks
                union = np.zeros((h, w), dtype=np.float32)
                for mask in st.session_state['post_mappeur_masks'].values():
                    mask_norm = mask.astype(np.float32) / 65535.0
                    union = np.maximum(union, mask_norm)

                # Seuil + dilatation optionnelle
                col1, col2 = st.columns(2)
                with col1:
                    seuil = st.slider("Seuil détection", 0.01, 0.20, 0.05, step=0.01)
                with col2:
                    dilation_px = st.slider("Dilatation (px)", 0, 50, 10)

                zone_mask = ((union > seuil) * 255).astype(np.uint8)

                if dilation_px > 0:
                    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilation_px, dilation_px))
                    zone_mask = cv2.dilate(zone_mask, kernel)

                st.session_state['zone_mask'] = zone_mask
                pct_garder = np.sum(zone_mask > 128) / zone_mask.size * 100
                st.success(f"✓ Zone : {pct_garder:.1f}% mappeur | {100-pct_garder:.1f}% pipeline")

            else:  # Manuel
                zone_file = st.file_uploader(
                    "Upload masque zone (PNG noir/blanc)",
                    type=['png'],
                    key="zone_manual_v2"
                )
                if zone_file:
                    arr = np.frombuffer(zone_file.read(), np.uint8)
                    zone_mask = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)

                    if zone_mask.shape != (h, w):
                        zone_mask = cv2.resize(zone_mask, (w, h), interpolation=cv2.INTER_NEAREST)

                    st.session_state['zone_mask'] = zone_mask
                    st.success(f"✓ Zone chargée : {zone_mask.shape}")
                else:
                    st.info("⬆️ Uploadez un masque PNG noir/blanc")

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 3 : ANALYSE TEXTURES
        # ═══════════════════════════════════════════════════════════════════

        if st.session_state.get('zone_mask') is not None and st.session_state.get('post_mappeur_masks'):
            st.divider()
            st.markdown("#### 3️⃣ Analyse Textures dans Zones Sélectionnées")

            # DEBUG : Vérifier zone_mask avant analyse
            zone_debug = st.session_state['zone_mask']
            blanc_count = int(np.sum(zone_debug == 255))
            noir_count = int(np.sum(zone_debug == 0))
            total_count = zone_debug.size

            st.caption(f"🔍 Debug zone_mask: {blanc_count:,} blancs ({blanc_count/total_count*100:.1f}%) | {noir_count:,} noirs ({noir_count/total_count*100:.1f}%)")

            # DEBUG : Vérifier intensités premier mask
            first_mask_name = list(st.session_state['post_mappeur_masks'].keys())[0]
            first_mask = st.session_state['post_mappeur_masks'][first_mask_name]
            st.caption(f"🔍 Debug {first_mask_name}: min={np.min(first_mask)}, max={np.max(first_mask)}, mean={np.mean(first_mask):.0f}")

            from post_processing import analyze_selected_tiles_textures

            analysis = analyze_selected_tiles_textures(
                st.session_state['post_mappeur_masks'],
                st.session_state['zone_mask']
            )

            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**✓ Gardées ({len(analysis['textures_gardees'])}):**")
                for tex in analysis['textures_gardees'][:15]:
                    pct = analysis['stats'][tex]['pct_in_zone']
                    st.text(f"  {tex} ({pct:.0f}%)")
                if len(analysis['textures_gardees']) > 15:
                    st.caption(f"  ... +{len(analysis['textures_gardees']) - 15} autres")

            with col2:
                st.markdown(f"**— Absentes ({len(analysis['textures_absentes'])}):**")
                for tex in analysis['textures_absentes'][:15]:
                    st.text(f"  {tex}")
                if len(analysis['textures_absentes']) > 15:
                    st.caption(f"  ... +{len(analysis['textures_absentes']) - 15} autres")

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 4-5 : JUXTAPOSITION + EXPORT
        # ═══════════════════════════════════════════════════════════════════

        if st.session_state.get('zone_mask') is not None:
            st.divider()
            st.markdown("#### 4️⃣ Sélection Pipeline V2 + Fusion")

            # Dossier pipeline
            default_pipeline_dir = st.session_state.get('masks_dir_v2', '')

            validated_suggestion = None
            if default_pipeline_dir:
                base = Path(default_pipeline_dir)
                validated_path = base.parent / (base.name + '_validated')
                if validated_path.exists():
                    validated_suggestion = str(validated_path)
                    st.info(f"💡 Dossier validé QTRE : `{validated_path.name}/`")

            pipeline_dir_input = st.text_input(
                "Dossier masks terrain (pipeline_v2)",
                value=st.session_state.get('post_pipeline_dir', default_pipeline_dir),
                placeholder="generated/masks_YYYYMMDD_HHMMSS_validated/",
                key="post_pipeline_dir_v2"
            )

            if validated_suggestion and pipeline_dir_input != validated_suggestion:
                if st.button("✅ Utiliser validé QTRE"):
                    st.session_state['post_pipeline_dir'] = validated_suggestion
                    st.rerun()

            pipeline_dir_valid = False
            if pipeline_dir_input:
                pipeline_path = Path(pipeline_dir_input)
                if pipeline_path.exists() and pipeline_path.is_dir():
                    n_masks = len(list(pipeline_path.glob("*.png")))
                    st.success(f"✅ {n_masks} masks pipeline détectés")
                    st.session_state['post_pipeline_dir'] = pipeline_dir_input
                    pipeline_dir_valid = True
                else:
                    st.error("❌ Dossier inexistant")

            # Paramètres export
            st.markdown("#### 5️⃣ Paramètres Export")

            col1, col2 = st.columns(2)
            with col1:
                presence_threshold = st.slider(
                    "Seuil présence texture",
                    0.03, 0.20, 0.05,
                    step=0.01,
                    format="%.2f",
                    help="Élimine valeurs < 5%"
                )
            with col2:
                project_path = st.session_state.get('current_project_path')
                if project_path:
                    default_out = str(Path(project_path) / "generated" / "final_merged")
                else:
                    default_out = "generated/final_merged"

                output_dir = st.text_input("Dossier export", value=default_out)

            # Lancement fusion
            if not pipeline_dir_valid:
                st.info("⬆️ Sélectionnez le dossier pipeline ci-dessus")
            else:
                if st.button("🚀 Générer Masks Finaux", type="primary", key="fusion_btn"):
                    from post_processing import juxtapose_masks, redefine_and_export

                    terrain_data = st.session_state.get('terrain_data')
                    cellsize = terrain_data['cellsize'] if terrain_data else 4.0

                    with st.spinner("⏳ Chargement pipeline..."):
                        v2_masks = {}
                        for png in Path(st.session_state['post_pipeline_dir']).glob("*.png"):
                            arr = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
                            if arr is not None:
                                v2_masks[png.stem] = arr.astype(np.float32) / 65535.0

                        if not v2_masks:
                            st.error("❌ Aucun mask pipeline")
                            st.stop()

                    with st.spinner("⏳ Juxtaposition géographique..."):
                        shape = list(v2_masks.values())[0].shape
                        mappeur_resized = {}
                        for fname, mask in st.session_state['post_mappeur_masks'].items():
                            if mask.shape != shape:
                                interp = cv2.INTER_AREA if mask.shape[0] > shape[0] else cv2.INTER_LINEAR
                                mappeur_resized[fname] = cv2.resize(mask, (shape[1], shape[0]), interpolation=interp)
                            else:
                                mappeur_resized[fname] = mask

                        zone_mask_resized = st.session_state['zone_mask']
                        if zone_mask_resized.shape != shape:
                            zone_mask_resized = cv2.resize(zone_mask_resized, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)

                        juxtaposed = juxtapose_masks(
                            mappeur_masks=mappeur_resized,
                            v2_masks=v2_masks,
                            zone_mask=zone_mask_resized
                        )
                        st.info(f"✓ {len(juxtaposed)} textures juxtaposées")

                    with st.spinner("⏳ Nettoyage QTRE + Export..."):
                        qtre = redefine_and_export(
                            juxtaposed_masks=juxtaposed,
                            output_dir=output_dir,
                            cellsize=cellsize,
                            presence_threshold=presence_threshold
                        )

                    # ── Résultats ──
                    st.markdown("---")
                    st.markdown("### ✅ Résultats Fusion")

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("QTRE OK", f"{qtre['ok_pct']:.1f}%", help="≤3 textures/bloc")
                    col2.metric("Limite", f"{qtre['limit_pct']:.1f}%", help="4-5 textures/bloc")
                    col3.metric("Critique", f"{qtre['critical_pct']:.2f}%", help="≥6 textures/bloc")
                    col4.metric("Masks", qtre['n_masks'])

                    # Heatmap
                    st.image(
                        qtre['qtre_heatmap'],
                        caption="QTRE Heatmap : Vert=OK | Orange=Limite | Rouge=Critique",
                        use_column_width=True
                    )

                    if qtre['verdict'] == "OK":
                        st.success(f"✅ {qtre['verdict']} — Terrain QTRE compatible")
                    else:
                        st.warning(f"⚠️ {qtre['verdict']} — Vérifier zones critiques")

                    st.info(f"📁 {qtre['n_masks']} masks → `{output_dir}/`")

                    with st.expander("📂 Fichiers exportés"):
                        for fpath in qtre['exported']:
                            st.text(f"• {Path(fpath).name}")

                    # Sauvegarde project.json
                    if st.session_state.get('current_project_path'):
                        st.session_state.setdefault('current_project', {})
                        st.session_state.current_project['post_output_dir'] = output_dir
                        save_project()
                        st.caption("✓ Sauvegardé dans project.json")

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
    <p><strong>Map Generator Pro v5.1</strong> — Pipeline MODE 2 & Végétation Enrichie</p>
    <p>🌿 Nouveau : MODE 2 (15 masks biomes) | Carte végétation | Debris/Dirt révisé | Post-Traitement | Cache terrain</p>
    <p>© 2026 | Production-Ready</p>
</div>
""", unsafe_allow_html=True)
