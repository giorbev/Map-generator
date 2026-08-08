# -*- coding: utf-8 -*-
"""
tab_pipeline_v5.py — Onglet Pipeline V5
========================================
Interface Streamlit pour pipeline_v5.py avec mapping masque → texture.

Structure :
  1. Sources (fichiers d'entrée avec Browse tkinter)
  2. Mapping masque → texture (st.data_editor)
  3. Paramètres pipeline (expanders)
  4. Bouton "Générer preview"
  5. Boutons export (PNG / .ttile) — visibles après preview
"""

import streamlit as st
import numpy as np
import cv2
from pathlib import Path
from PIL import Image
import json
import tempfile


# ============================================================================
# HELPER — Browse file dialog (tkinter)
# ============================================================================

def browse_file(title="Sélectionner un fichier", filetypes=None):
    """Ouvre un dialog tkinter pour sélectionner un fichier."""
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        if filetypes is None:
            filetypes = [("Tous les fichiers", "*.*")]
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        return path if path else None
    except Exception:
        return None


def browse_directory(title="Sélectionner un dossier"):
    """Ouvre un dialog tkinter pour sélectionner un dossier."""
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory(title=title)
        root.destroy()
        return path if path else None
    except Exception:
        return None


# ============================================================================
# RENDU PRINCIPAL
# ============================================================================

def render_tab_pipeline_v5():
    """Point d'entrée appelé depuis app.py."""

    st.markdown("### 🎨 Pipeline V5 — Mapping masque → texture")
    st.caption("Pipeline unifié avec écriture directe .ttile et gestion budget par bloc")

    # ── Vérification projet ──────────────────────────────────────────────────
    project_path = st.session_state.get("current_project_path")
    if not project_path:
        st.warning("⚠️ Chargez un projet depuis la sidebar.")
        return

    p = Path(project_path)

    # Charger config pipeline_v5 depuis project.json
    _load_v5_config(p)

    # ========================================================================
    # SECTION 1 — SOURCES
    # ========================================================================

    st.divider()
    st.subheader("📂 Sources")

    # ── ASC Heightmap ────────────────────────────────────────────────────────
    st.markdown("**Heightmap**")
    terrain_data = st.session_state.get("terrain_data")

    if terrain_data:
        use_mem = st.checkbox(
            "✅ Utiliser heightmap déjà chargée en mémoire",
            value=st.session_state.get("v5_use_mem_heightmap", True),
            key="v5_use_mem_heightmap_cb"
        )
        st.session_state["v5_use_mem_heightmap"] = use_mem
        if use_mem:
            st.success(f"Heightmap mémoire : {terrain_data['heightmap'].shape[1]}×{terrain_data['heightmap'].shape[0]} px")
    else:
        st.session_state["v5_use_mem_heightmap"] = False

    if not st.session_state.get("v5_use_mem_heightmap"):
        col_asc1, col_asc2 = st.columns([4, 1])
        with col_asc1:
            asc_path = st.text_input(
                "Chemin heightmap .asc",
                value=st.session_state.get("v5_asc_path", ""),
                key="v5_asc_input"
            )
        with col_asc2:
            if st.button("📁 Browse", key="browse_asc"):
                path = browse_file("Heightmap .asc", [("ASC files", "*.asc"), ("All files", "*.*")])
                if path:
                    st.session_state["v5_asc_path"] = path
                    st.rerun()
        if asc_path:
            st.session_state["v5_asc_path"] = asc_path

    # ── Masque exclusion ─────────────────────────────────────────────────────
    st.markdown("**Masque exclusion (optionnel)**")
    col_ex1, col_ex2 = st.columns([4, 1])
    with col_ex1:
        excl_path = st.text_input(
            "Zone B (blanc = actif, noir = préservé)",
            value=st.session_state.get("v5_exclusion_path", ""),
            key="v5_excl_input"
        )
    with col_ex2:
        if st.button("📁 Browse", key="browse_excl"):
            path = browse_file("Masque exclusion", [("PNG files", "*.png"), ("All files", "*.*")])
            if path:
                st.session_state["v5_exclusion_path"] = path
                st.rerun()
    if excl_path:
        st.session_state["v5_exclusion_path"] = excl_path

    # ── Flow Gaea ────────────────────────────────────────────────────────────
    st.markdown("**Flow Gaea (optionnel)**")
    col_fl1, col_fl2 = st.columns([4, 1])
    with col_fl1:
        flow_path = st.text_input(
            "Masque flow (rivières)",
            value=st.session_state.get("v5_flow_path", ""),
            key="v5_flow_input"
        )
    with col_fl2:
        if st.button("📁 Browse", key="browse_flow"):
            path = browse_file("Flow Gaea", [("PNG files", "*.png"), ("All files", "*.*")])
            if path:
                st.session_state["v5_flow_path"] = path
                st.rerun()
    if flow_path:
        st.session_state["v5_flow_path"] = flow_path

    # ── Deposit Gaea ─────────────────────────────────────────────────────────
    st.markdown("**Deposit Gaea (optionnel)**")
    col_dp1, col_dp2 = st.columns([4, 1])
    with col_dp1:
        dep_path = st.text_input(
            "Masque deposit (sédiments)",
            value=st.session_state.get("v5_deposit_path", ""),
            key="v5_dep_input"
        )
    with col_dp2:
        if st.button("📁 Browse", key="browse_dep"):
            path = browse_file("Deposit Gaea", [("PNG files", "*.png"), ("All files", "*.*")])
            if path:
                st.session_state["v5_deposit_path"] = path
                st.rerun()
    if dep_path:
        st.session_state["v5_deposit_path"] = dep_path

    # ── DATA_DIR Reforger ────────────────────────────────────────────────────
    st.markdown("**Dossier .Data Reforger**")
    col_dt1, col_dt2 = st.columns([4, 1])
    with col_dt1:
        data_dir = st.text_input(
            "Chemin vers .Data/",
            value=st.session_state.get("v5_data_dir", ""),
            key="v5_data_input",
            help="Requis pour mode .ttile et lecture slots Zone B"
        )
    with col_dt2:
        if st.button("📁 Browse", key="browse_data"):
            path = browse_directory("Dossier .Data Reforger")
            if path:
                st.session_state["v5_data_dir"] = path
                st.rerun()
    if data_dir:
        st.session_state["v5_data_dir"] = data_dir

    # ── Catalog.json (optionnel pour satmap) ─────────────────────────────────
    st.markdown("**Catalog.json (optionnel)**")
    col_ct1, col_ct2 = st.columns([4, 1])
    with col_ct1:
        catalog_path = st.text_input(
            "Catalog matériaux Reforger",
            value=st.session_state.get("v5_catalog_path", ""),
            key="v5_catalog_input"
        )
    with col_ct2:
        if st.button("📁 Browse", key="browse_catalog"):
            path = browse_file("catalog.json", [("JSON files", "*.json"), ("All files", "*.*")])
            if path:
                st.session_state["v5_catalog_path"] = path
                st.rerun()
    if catalog_path:
        st.session_state["v5_catalog_path"] = catalog_path

    # ── Satmap PNG (optionnel) ───────────────────────────────────────────────
    st.markdown("**Satmap PNG (optionnel)**")
    col_st1, col_st2 = st.columns([4, 1])
    with col_st1:
        satmap_path = st.text_input(
            "Satmap source pour overlay",
            value=st.session_state.get("v5_satmap_path", ""),
            key="v5_satmap_input"
        )
    with col_st2:
        if st.button("📁 Browse", key="browse_satmap"):
            path = browse_file("Satmap PNG", [("PNG files", "*.png"), ("All files", "*.*")])
            if path:
                st.session_state["v5_satmap_path"] = path
                st.rerun()
    if satmap_path:
        st.session_state["v5_satmap_path"] = satmap_path

    # ========================================================================
    # SECTION 2 — MAPPING MASQUE → TEXTURE
    # ========================================================================

    st.divider()
    st.subheader("🎨 Mapping masque → texture")

    # Charger DEFAULT_MASK_CONFIG depuis pipeline_v5
    import sys, os
    _root = os.path.dirname(os.path.abspath(__file__))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import pipeline_v5 as pv5

    # Initialiser la config depuis session_state ou défauts
    if "v5_mask_config" not in st.session_state:
        df_data = []
        for i, (name, mat_id, color) in enumerate(pv5.DEFAULT_MASK_CONFIG, start=1):
            mat_name = pv5.SURFACES.get(mat_id, f"ID{mat_id}")
            df_data.append({
                "Masque": name.replace("mask_", ""),
                "Priorité": i,
                "Texture": mat_name,
                "ID": mat_id,
            })
        st.session_state["v5_mask_config"] = df_data

    # Liste des textures pour le selectbox
    texture_options = [f"{pv5.SURFACES[i]} (ID{i})" for i in sorted(pv5.SURFACES.keys())]
    texture_map = {f"{pv5.SURFACES[i]} (ID{i})": i for i in pv5.SURFACES.keys()}

    # Data editor
    edited_df = st.data_editor(
        st.session_state["v5_mask_config"],
        column_config={
            "Masque": st.column_config.TextColumn("Masque", disabled=True),
            "Priorité": st.column_config.NumberColumn("Priorité", min_value=1, max_value=13, step=1),
            "Texture": st.column_config.SelectboxColumn("Texture", options=texture_options),
            "ID": st.column_config.NumberColumn("ID", disabled=True, help="ID global matériau"),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key="v5_mask_editor"
    )

    # Mettre à jour session_state
    st.session_state["v5_mask_config"] = edited_df

    # Bouton réinitialiser
    if st.button("🔄 Réinitialiser aux défauts", key="v5_reset_mapping"):
        df_data = []
        for i, (name, mat_id, color) in enumerate(pv5.DEFAULT_MASK_CONFIG, start=1):
            mat_name = pv5.SURFACES.get(mat_id, f"ID{mat_id}")
            df_data.append({
                "Masque": name.replace("mask_", ""),
                "Priorité": i,
                "Texture": mat_name,
                "ID": mat_id,
            })
        st.session_state["v5_mask_config"] = df_data
        st.success("✅ Configuration réinitialisée")
        st.rerun()

    # ========================================================================
    # SECTION 3 — PARAMÈTRES PIPELINE
    # ========================================================================

    st.divider()
    st.subheader("⚙️ Paramètres")

    col_p1, col_p2 = st.columns(2)

    with col_p1:
        with st.expander("🏔️ Enrichissement slope (fBm)", expanded=False):
            roughness_mode = st.selectbox(
                "Mode", ["slope_perturb", "domain_warp", "additive", "Désactivé"],
                index=0, key="v5_roughness_mode"
            )
            amplitude = st.slider("Amplitude (°)", 0.0, 20.0, 8.0, 0.5, key="v5_amplitude")
            scale = st.slider("Échelle fBm", 0.001, 0.02, 0.008, 0.001, key="v5_scale", format="%.3f")
            octaves = st.slider("Octaves", 2, 8, 6, 1, key="v5_octaves")

        with st.expander("📐 Seuils de pente", expanded=False):
            st.caption("0 = auto depuis percentiles")
            t_gentle = st.slider("Gentle (°)", 0.0, 30.0, 0.0, 0.5, key="v5_gentle")
            t_landes = st.slider("Landes (°)", 0.0, 40.0, 0.0, 0.5, key="v5_landes")
            t_rock = st.slider("Rock (°)", 0.0, 45.0, 22.0, 0.5, key="v5_rock")
            t_cliff = st.slider("Cliff (°)", 0.0, 60.0, 26.0, 0.5, key="v5_cliff")

    with col_p2:
        with st.expander("🎚️ Post-processing", expanded=False):
            stretch_auto = st.checkbox("Stretch auto (p2-p98)", value=True, key="v5_stretch")
            weight_min = st.slider("Weight min", 0.0, 0.3, 0.10, 0.01, key="v5_wmin")
            flow_cut = st.slider("Flow cut_low", 0.0, 0.8, 0.45, 0.05, key="v5_flow_cut")
            dep_cut = st.slider("Deposit cut_low", 0.0, 0.8, 0.30, 0.05, key="v5_dep_cut")
            flow_gamma = st.slider("Flow gamma", 0.1, 2.0, 0.5, 0.05, key="v5_flow_gamma")
            dep_gamma = st.slider("Deposit gamma", 0.1, 2.0, 1.0, 0.05, key="v5_dep_gamma")

        with st.expander("📊 QTRE", expanded=False):
            qtre_thresh = st.slider("Seuil présence QTRE", 0.01, 0.30, 0.05, 0.01, key="v5_qtre_thresh")

    # ========================================================================
    # SECTION 4 — BOUTON PREVIEW
    # ========================================================================

    st.divider()
    st.subheader("🔍 Prévisualisation")

    if st.button("🚀 Générer preview", type="primary", use_container_width=True):
        _run_preview(p)

    # Affichage résultats preview
    if st.session_state.get("v5_preview_done"):
        _render_preview_results(p)

    # ========================================================================
    # SECTION 5 — BOUTONS EXPORT (visibles après preview)
    # ========================================================================

    if st.session_state.get("v5_preview_done"):
        st.divider()
        st.subheader("📦 Export")

        col_exp1, col_exp2 = st.columns(2)

        with col_exp1:
            if st.button("📁 Exporter masques PNG", use_container_width=True):
                _export_masks_png(p)

        with col_exp2:
            if st.button("✍️ Écrire sur les .ttile", use_container_width=True):
                st.session_state["v5_show_ttile_confirm"] = True

        # Confirmation écriture .ttile
        if st.session_state.get("v5_show_ttile_confirm"):
            st.warning("⚠️ **Cette action modifie directement les fichiers terrain.**")
            backup_done = st.checkbox(
                "✅ J'ai fait un backup git (commit ou branche)",
                key="v5_backup_confirm"
            )
            if backup_done:
                if st.button("🔒 Confirmer l'écriture .ttile", type="primary"):
                    _write_ttile(p)
                    st.session_state["v5_show_ttile_confirm"] = False
            else:
                st.info("Cochez la case pour activer le bouton de confirmation.")

    # Sauvegarder config dans project.json
    _save_v5_config(p)


# ============================================================================
# FONCTIONS RUN
# ============================================================================

def _run_preview(project_path: Path):
    """Lance le pipeline en mode preview."""
    import sys, os
    _root = os.path.dirname(os.path.abspath(__file__))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import pipeline_v5 as pv5

    # Patcher les globals
    _patch_pipeline_v5(pv5)

    # Préparer les chemins
    asc_path = _get_asc_path(project_path)
    if not asc_path:
        st.error("❌ Heightmap manquante — fournissez un ASC ou chargez terrain_data")
        return

    excl_path = Path(st.session_state.get("v5_exclusion_path", "")) if st.session_state.get("v5_exclusion_path") else None
    flow_path = Path(st.session_state.get("v5_flow_path", "")) if st.session_state.get("v5_flow_path") else None
    dep_path = Path(st.session_state.get("v5_deposit_path", "")) if st.session_state.get("v5_deposit_path") else None
    data_dir = Path(st.session_state.get("v5_data_dir", "")) if st.session_state.get("v5_data_dir") else None
    catalog_path = Path(st.session_state.get("v5_catalog_path", "")) if st.session_state.get("v5_catalog_path") else None
    satmap_path = Path(st.session_state.get("v5_satmap_path", "")) if st.session_state.get("v5_satmap_path") else None

    output_dir = project_path / "outputs" / "latest"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Construire mask_config
    mask_config = _build_mask_config(pv5)

    # Lancer pipeline
    with st.spinner("⏳ Génération preview en cours..."):
        try:
            result = pv5.run_pipeline(
                asc_path=asc_path,
                output_dir=output_dir,
                exclusion_path=excl_path,
                gaea_flow=flow_path,
                gaea_deposit=dep_path,
                data_dir=data_dir,
                catalog_path=catalog_path,
                satmap_path=satmap_path,
                mask_config=mask_config,
                mode='preview',
                dry_run=True,
            )
            st.session_state["v5_preview_result"] = result
            st.session_state["v5_preview_done"] = True
            st.success("✅ Preview générée")
            st.rerun()
        except Exception as e:
            import traceback
            st.error(f"❌ Erreur : {e}")
            st.code(traceback.format_exc())


def _export_masks_png(project_path: Path):
    """Exporte les masques PNG."""
    import sys, os
    _root = os.path.dirname(os.path.abspath(__file__))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import pipeline_v5 as pv5

    _patch_pipeline_v5(pv5)

    asc_path = _get_asc_path(project_path)
    if not asc_path:
        st.error("❌ Heightmap manquante")
        return

    excl_path = Path(st.session_state.get("v5_exclusion_path", "")) if st.session_state.get("v5_exclusion_path") else None
    flow_path = Path(st.session_state.get("v5_flow_path", "")) if st.session_state.get("v5_flow_path") else None
    dep_path = Path(st.session_state.get("v5_deposit_path", "")) if st.session_state.get("v5_deposit_path") else None
    data_dir = Path(st.session_state.get("v5_data_dir", "")) if st.session_state.get("v5_data_dir") else None

    output_dir = project_path / "outputs" / "masks" / "latest"
    output_dir.mkdir(parents=True, exist_ok=True)

    mask_config = _build_mask_config(pv5)

    with st.spinner("⏳ Export masques PNG..."):
        try:
            result = pv5.run_pipeline(
                asc_path=asc_path,
                output_dir=output_dir,
                exclusion_path=excl_path,
                gaea_flow=flow_path,
                gaea_deposit=dep_path,
                data_dir=data_dir,
                mask_config=mask_config,
                mode='masks',
                dry_run=False,
            )
            st.success(f"✅ {len(result.get('masks', {}))} masques exportés → `{output_dir}`")
            # Lister les fichiers
            masks_files = sorted(output_dir.glob("*.png"))
            with st.expander("📋 Liste des masques", expanded=True):
                for f in masks_files:
                    st.text(f"  • {f.name}")
        except Exception as e:
            import traceback
            st.error(f"❌ Erreur : {e}")
            st.code(traceback.format_exc())


def _write_ttile(project_path: Path):
    """Écriture directe .ttile."""
    import sys, os
    _root = os.path.dirname(os.path.abspath(__file__))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import pipeline_v5 as pv5

    _patch_pipeline_v5(pv5)

    asc_path = _get_asc_path(project_path)
    if not asc_path:
        st.error("❌ Heightmap manquante")
        return

    data_dir = Path(st.session_state.get("v5_data_dir", ""))
    if not data_dir.exists():
        st.error("❌ Dossier .Data introuvable — configurez-le dans Sources")
        return

    excl_path = Path(st.session_state.get("v5_exclusion_path", "")) if st.session_state.get("v5_exclusion_path") else None
    flow_path = Path(st.session_state.get("v5_flow_path", "")) if st.session_state.get("v5_flow_path") else None
    dep_path = Path(st.session_state.get("v5_deposit_path", "")) if st.session_state.get("v5_deposit_path") else None

    output_dir = project_path / "outputs" / "latest"
    mask_config = _build_mask_config(pv5)

    prog_bar = st.progress(0)
    prog_text = st.empty()

    def progress_cb(tile_id):
        prog_text.text(f"Tuile {tile_id}...")
        # Estimation simplifiée (32×32 tuiles)
        prog_bar.progress(min(tile_id / 1024, 1.0))

    with st.spinner("⏳ Écriture .ttile en cours..."):
        try:
            result = pv5.run_pipeline(
                asc_path=asc_path,
                output_dir=output_dir,
                exclusion_path=excl_path,
                gaea_flow=flow_path,
                gaea_deposit=dep_path,
                data_dir=data_dir,
                mask_config=mask_config,
                mode='ttile',
                dry_run=False,
                progress_cb=progress_cb,
            )
            prog_bar.empty()
            prog_text.empty()
            st.success("✅ Écriture .ttile terminée")
        except Exception as e:
            import traceback
            prog_bar.empty()
            prog_text.empty()
            st.error(f"❌ Erreur : {e}")
            st.code(traceback.format_exc())


# ============================================================================
# HELPERS
# ============================================================================

def _get_asc_path(project_path: Path):
    """Retourne le chemin ASC ou crée un tempfile depuis terrain_data."""
    if st.session_state.get("v5_use_mem_heightmap"):
        terrain_data = st.session_state.get("terrain_data")
        if not terrain_data:
            return None
        # Créer tempfile ASC
        dem = terrain_data["heightmap"]
        cellsize = terrain_data["cellsize"]
        h, w = dem.shape

        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.asc', delete=False)
        tf.write(f"ncols {w}\n")
        tf.write(f"nrows {h}\n")
        tf.write(f"xllcorner 0.0\n")
        tf.write(f"yllcorner 0.0\n")
        tf.write(f"cellsize {cellsize}\n")
        tf.write(f"NODATA_value -9999\n")
        tf.close()

        # Écrire données
        np.savetxt(tf.name, dem, fmt="%.2f", delimiter=" ")
        st.session_state["v5_temp_asc"] = tf.name
        return Path(tf.name)
    else:
        asc_str = st.session_state.get("v5_asc_path", "")
        if asc_str and Path(asc_str).exists():
            return Path(asc_str)
        return None


def _patch_pipeline_v5(pv5):
    """Patcher les globals de pipeline_v5 depuis les valeurs UI."""
    mode = st.session_state.get("v5_roughness_mode", "slope_perturb")
    pv5.ROUGHNESS_MODE = None if mode == "Désactivé" else mode
    pv5.ROUGHNESS_AMPLITUDE = st.session_state.get("v5_amplitude", 8.0)
    pv5.ROUGHNESS_SCALE = st.session_state.get("v5_scale", 0.008)
    pv5.ROUGHNESS_OCTAVES = st.session_state.get("v5_octaves", 6)
    pv5.STRETCH_AUTO = st.session_state.get("v5_stretch", True)
    pv5.WEIGHT_MIN = st.session_state.get("v5_wmin", 0.10)

    t_gentle = st.session_state.get("v5_gentle", 0.0)
    t_landes = st.session_state.get("v5_landes", 0.0)
    pv5.THRESHOLD_GENTLE = None if t_gentle == 0 else t_gentle
    pv5.THRESHOLD_LANDES = None if t_landes == 0 else t_landes
    pv5.THRESHOLD_ROCK = st.session_state.get("v5_rock", 22.0)
    pv5.THRESHOLD_CLIFF = st.session_state.get("v5_cliff", 26.0)

    pv5.DEPOSIT_CUT_LOW = st.session_state.get("v5_dep_cut", 0.30)
    pv5.MASK_PRESENCE_THRESH = st.session_state.get("v5_qtre_thresh", 0.05)


def _build_mask_config(pv5):
    """Construit mask_config depuis st.session_state["v5_mask_config"]."""
    mask_config_raw = st.session_state.get("v5_mask_config", [])

    # Convertir en liste si nécessaire
    if isinstance(mask_config_raw, list):
        import pandas as pd
        mask_config_df = pd.DataFrame(mask_config_raw)
    else:
        mask_config_df = mask_config_raw

    # Trier par priorité
    mask_config_df = mask_config_df.sort_values("Priorité").reset_index(drop=True)

    # Reconstruire (nom_masque, mat_id, color_rgb)
    color_map_default = {name: color for name, _, color in pv5.DEFAULT_MASK_CONFIG}

    mask_config = []
    for _, row in mask_config_df.iterrows():
        name = "mask_" + row["Masque"]
        mat_id = int(row["ID"])
        color = color_map_default.get(name, (128, 128, 128))
        mask_config.append((name, mat_id, color))

    return mask_config


def _render_preview_results(project_path: Path):
    """Affiche les résultats du preview."""
    result = st.session_state.get("v5_preview_result")
    if not result:
        return

    st.divider()
    st.subheader("📊 Résultats Preview")

    # Stats
    stats = result.get("stats", {})
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Blocs OK", stats.get("n_ok", 0))
    with col2:
        st.metric("Dépassements", stats.get("n_over", 0))
    with col3:
        st.metric("Frontières A/B", stats.get("n_frontier", 0))
    with col4:
        st.metric("Total blocs", stats.get("total", 0))

    # Visualisation
    visu_path = result.get("visu_path")
    if visu_path and Path(visu_path).exists():
        st.markdown("**Carte de visualisation**")
        img = Image.open(visu_path)
        st.image(img, caption="Texture dominante par bloc + quadrillage tuiles", use_container_width=True)


def _load_v5_config(project_path: Path):
    """Charge la config pipeline_v5 depuis project.json."""
    json_path = project_path / "project.json"
    if not json_path.exists():
        return

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        v5_cfg = data.get("pipeline_v5", {})

        # Charger les chemins
        for key in ["asc_path", "exclusion_path", "flow_path", "deposit_path", "data_dir", "catalog_path", "satmap_path"]:
            if key in v5_cfg:
                st.session_state[f"v5_{key}"] = v5_cfg[key]

        # Charger les paramètres
        params = v5_cfg.get("params", {})
        for key, default in [
            ("roughness_mode", "slope_perturb"),
            ("amplitude", 8.0),
            ("scale", 0.008),
            ("octaves", 6),
            ("gentle", 0.0),
            ("landes", 0.0),
            ("rock", 22.0),
            ("cliff", 26.0),
            ("stretch", True),
            ("wmin", 0.10),
            ("flow_cut", 0.45),
            ("dep_cut", 0.30),
            ("flow_gamma", 0.5),
            ("dep_gamma", 1.0),
            ("qtre_thresh", 0.05),
        ]:
            if key in params:
                st.session_state[f"v5_{key}"] = params[key]

    except Exception:
        pass


def _save_v5_config(project_path: Path):
    """Sauvegarde la config pipeline_v5 dans project.json."""
    json_path = project_path / "project.json"
    if not json_path.exists():
        return

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data.setdefault("pipeline_v5", {})

        # Sauvegarder les chemins
        for key in ["asc_path", "exclusion_path", "flow_path", "deposit_path", "data_dir", "catalog_path", "satmap_path"]:
            val = st.session_state.get(f"v5_{key}", "")
            if val:
                data["pipeline_v5"][key] = val

        # Sauvegarder les paramètres
        data["pipeline_v5"]["params"] = {
            "roughness_mode": st.session_state.get("v5_roughness_mode", "slope_perturb"),
            "amplitude": st.session_state.get("v5_amplitude", 8.0),
            "scale": st.session_state.get("v5_scale", 0.008),
            "octaves": st.session_state.get("v5_octaves", 6),
            "gentle": st.session_state.get("v5_gentle", 0.0),
            "landes": st.session_state.get("v5_landes", 0.0),
            "rock": st.session_state.get("v5_rock", 22.0),
            "cliff": st.session_state.get("v5_cliff", 26.0),
            "stretch": st.session_state.get("v5_stretch", True),
            "wmin": st.session_state.get("v5_wmin", 0.10),
            "flow_cut": st.session_state.get("v5_flow_cut", 0.45),
            "dep_cut": st.session_state.get("v5_dep_cut", 0.30),
            "flow_gamma": st.session_state.get("v5_flow_gamma", 0.5),
            "dep_gamma": st.session_state.get("v5_dep_gamma", 1.0),
            "qtre_thresh": st.session_state.get("v5_qtre_thresh", 0.05),
        }

        from datetime import datetime
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")

        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
