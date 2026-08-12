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
    # SECTION 1 — SOURCES (depuis configuration centralisée)
    # ========================================================================

    st.divider()
    st.markdown("### 📁 Sources — depuis la configuration centralisée")

    proj_path = Path(st.session_state.get("current_project_path", ""))
    paths = st.session_state.get("paths", {})

    def resolve_path(rel_or_abs: str):
        """Résout un chemin relatif ou absolu."""
        if not rel_or_abs:
            return None
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p if p.exists() else None
        full = proj_path / rel_or_abs
        return full if full.exists() else None

    # Résoudre et afficher les chemins disponibles
    asc_path = resolve_path(paths.get("heightmap", ""))
    excl_path = resolve_path(paths.get("exclusion_mask", ""))
    flow_path = resolve_path(paths.get("gaea_flow", ""))
    deposit_path = resolve_path(paths.get("gaea_deposit", ""))
    data_dir = resolve_path(paths.get("data_dir", ""))
    catalog_path = resolve_path(paths.get("catalog_json", ""))
    satmap_path = resolve_path(paths.get("satmap_v2", ""))

    # Vérifier si heightmap mémoire disponible
    terrain_data = st.session_state.get("terrain_data")
    use_mem_heightmap = terrain_data is not None

    # Afficher tableau de statut des chemins
    cols = st.columns(4)
    items = [
        ("Heightmap", asc_path if not use_mem_heightmap else "✅ mémoire"),
        ("Exclusion", excl_path),
        ("Flow", flow_path),
        ("Deposit", deposit_path),
        ("Data dir", data_dir),
        ("Catalog", catalog_path),
        ("Satmap V2", satmap_path),
    ]
    for i, (label, pval) in enumerate(items):
        with cols[i % 4]:
            if pval == "✅ mémoire":
                st.metric(label, "✅ mémoire")
            else:
                st.metric(label, "✅" if pval else "⚠️")

    if not asc_path and not use_mem_heightmap:
        st.error("❌ Heightmap manquante — configurez dans Heightmap → Chemins & fichiers")
        return

    st.caption("💡 Pour modifier les chemins : **Heightmap → Chemins & fichiers**")

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

    # Charger dynamiquement la liste des textures depuis surfaces.json
    project_path = st.session_state.get("current_project_path")
    print(f"[SURFACES] project_path = {project_path}")

    if project_path:
        p = Path(project_path)
        surfaces_json = p / "surfaces.json"
        print(f"[SURFACES] Chemin surfaces.json : {surfaces_json}")
        print(f"[SURFACES] Fichier existe ? {surfaces_json.exists()}")

        if surfaces_json.exists():
            import json as _json
            data = _json.loads(surfaces_json.read_text(encoding='utf-8'))
            mat_id_map = data.get("materials", {})  # {nom: id}
            available_textures = list(mat_id_map.keys())
            print(f"[SURFACES] Chargé depuis surfaces.json : {len(available_textures)} textures")
            print(f"[SURFACES] Premières textures : {available_textures[:5]}")
        else:
            # Fallback : générer surfaces.json depuis .terr
            print(f"[SURFACES] surfaces.json absent - tentative génération depuis .terr")
            from project_manager import load_or_update_surfaces
            from app_config import resolve_paths

            # Récupérer addon_path depuis current_project (pas depuis paths qui est obsolète)
            current_project = st.session_state.get("current_project", {})
            addon_path = current_project.get("paths", {}).get("addon_reforger", "")
            print(f"[SURFACES] addon_path depuis current_project : {addon_path}")

            if addon_path:
                try:
                    rp = resolve_paths(addon_path)
                    print(f"[SURFACES] resolve_paths() OK : {rp.get('valid', False)}")
                    terr_file = Path(rp.get("terr_file", ""))
                    print(f"[SURFACES] terr_file : {terr_file}")
                    print(f"[SURFACES] terr_file existe ? {terr_file.exists()}")

                    if terr_file.exists():
                        print(f"[SURFACES] Appel load_or_update_surfaces({p}, {terr_file})")
                        mat_id_map, _ = load_or_update_surfaces(p, terr_file)
                        available_textures = list(mat_id_map.keys())
                        print(f"[SURFACES] Généré : {len(available_textures)} textures")
                        print(f"[SURFACES] Premières textures : {available_textures[:5]}")
                    else:
                        print(f"[SURFACES] ERREUR : terr_file introuvable")
                        mat_id_map = {}
                        available_textures = []
                except Exception as e:
                    import traceback
                    print(f"[SURFACES] EXCEPTION dans fallback : {type(e).__name__}: {e}")
                    traceback.print_exc()
                    mat_id_map = {}
                    available_textures = []
            else:
                print(f"[SURFACES] ERREUR : addon_path vide")
                mat_id_map = {}
                available_textures = []
    else:
        print(f"[SURFACES] ERREUR : project_path est None")
        mat_id_map = {}
        available_textures = []

    print(f"[SURFACES] FINAL : {len(available_textures)} textures disponibles")
    if not available_textures:
        print(f"[SURFACES] WARNING : Liste vide - selectbox affichera 'default' uniquement")

    # Initialiser la config depuis session_state ou défauts
    if "v5_mask_config" not in st.session_state:
        import pipeline_v5 as pv5
        df_data = []
        for i, (name, texture_name, color) in enumerate(pv5.DEFAULT_MASK_CONFIG, start=1):
            # texture_name est un str (nom texture), pas un int
            # Résoudre nom → ID via mat_id_map
            texture_id = mat_id_map.get(texture_name, 0)
            df_data.append({
                "Masque": name.replace("mask_", ""),
                "Priorité": i,
                "Texture": texture_name,
                "ID": texture_id,
            })
        st.session_state["v5_mask_config"] = df_data

    # Liste des textures pour le selectbox
    texture_options = [f"{name} (ID{i})" for i, name in enumerate(available_textures)]
    texture_map = {f"{name} (ID{i})": i for i, name in enumerate(available_textures)}

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
        import pipeline_v5 as pv5
        df_data = []
        for i, (name, texture_name, color) in enumerate(pv5.DEFAULT_MASK_CONFIG, start=1):
            # texture_name est un str (nom texture), pas un int
            # Résoudre nom → ID via mat_id_map
            texture_id = mat_id_map.get(texture_name, 0)
            df_data.append({
                "Masque": name.replace("mask_", ""),
                "Priorité": i,
                "Texture": texture_name,
                "ID": texture_id,
            })
        st.session_state["v5_mask_config"] = df_data
        st.success("✅ Configuration réinitialisée")
        st.rerun()

    # ========================================================================
    # SECTION 2.5 — CONFIGURATION TEXTURES PAR MASQUE (par projet)
    # ========================================================================

    st.divider()

    with st.expander("⚙️ Configuration textures par masque (par projet)", expanded=False):
        st.caption("Personnalisez la texture assignée à chaque masque pour ce projet")

        # Charger config actuelle du projet
        if "project_mask_config" not in st.session_state:
            from project_manager import load_mask_config
            project_path = st.session_state.get("current_project_path")
            if project_path:
                st.session_state["project_mask_config"] = load_mask_config(project_path)
            else:
                st.session_state["project_mask_config"] = {}

        project_config = st.session_state.get("project_mask_config", {})

        # Afficher selectbox pour chaque masque
        import pipeline_v5 as pv5

        st.markdown("**Assignation texture → masque**")

        # Créer 2 colonnes pour layout compact
        col_left, col_right = st.columns(2)

        new_config = {}

        for idx, (mask_name, default_texture, color) in enumerate(pv5.DEFAULT_MASK_CONFIG):
            # Alterner entre colonnes
            col = col_left if idx % 2 == 0 else col_right

            with col:
                # Valeur actuelle (depuis config projet ou défaut)
                current_texture = project_config.get(mask_name, default_texture)

                # Vérifier si texture existe dans surfaces.json
                if current_texture not in available_textures and current_texture != "default":
                    st.warning(f"⚠️ '{current_texture}' absente du .terr")
                    current_texture = "default"

                # Selectbox
                sorted_textures = sorted(available_textures) if available_textures else ["default"]
                try:
                    current_index = sorted_textures.index(current_texture)
                except ValueError:
                    # Fallback sur "default" ou premier
                    try:
                        current_index = sorted_textures.index("default")
                    except ValueError:
                        current_index = 0

                selected = st.selectbox(
                    mask_name.replace("mask_", "").replace("_", " ").title(),
                    options=sorted_textures,
                    index=current_index,
                    key=f"mask_texture_{mask_name}"
                )

                new_config[mask_name] = selected

        # Boutons action
        col_save, col_reset = st.columns(2)

        with col_save:
            if st.button("💾 Sauvegarder configuration", use_container_width=True, key="save_project_mask_config"):
                from project_manager import save_mask_config
                project_path = st.session_state.get("current_project_path")
                if project_path:
                    try:
                        save_mask_config(project_path, new_config)
                        st.session_state["project_mask_config"] = new_config
                        st.success("✅ Configuration sauvegardée")
                        st.rerun()
                    except Exception as e:
                        import traceback
                        print("[MASK_CONFIG] ERREUR lors de la sauvegarde:")
                        print(f"  project_path = {project_path}")
                        print(f"  Exception: {type(e).__name__}: {e}")
                        print("  Traceback complet:")
                        traceback.print_exc()
                        st.error(f"❌ Erreur sauvegarde : {e}")
                else:
                    st.error("Aucun projet chargé")

        with col_reset:
            if st.button("🔄 Réinitialiser défauts", use_container_width=True, key="reset_project_mask_config"):
                # Recharger depuis DEFAULT_MASK_CONFIG
                reset_config = {}
                for name, texture_name, _ in pv5.DEFAULT_MASK_CONFIG:
                    reset_config[name] = texture_name

                st.session_state["project_mask_config"] = reset_config
                st.info("Configuration réinitialisée aux défauts")
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

def _get_paths_from_config(project_path: Path):
    """Récupère et résout tous les chemins depuis st.session_state["paths"]."""
    paths = st.session_state.get("paths", {})

    def resolve_path(rel_or_abs: str):
        if not rel_or_abs:
            return None
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p if p.exists() else None
        if not project_path:
            return None
        full = project_path / rel_or_abs
        return full if full.exists() else None

    return {
        "asc_raw": resolve_path(paths.get("heightmap", "")),
        "excl": resolve_path(paths.get("exclusion_mask", "")),
        "flow": resolve_path(paths.get("gaea_flow", "")),
        "deposit": resolve_path(paths.get("gaea_deposit", "")),
        "data_dir": resolve_path(paths.get("data_dir", "")),
        "catalog": resolve_path(paths.get("catalog_json", "")),
        "satmap": resolve_path(paths.get("satmap_v2", "")),
    }


def _run_preview(project_path: Path):
    """Lance le pipeline en mode preview."""
    import sys, os
    _root = os.path.dirname(os.path.abspath(__file__))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import pipeline_v5 as pv5

    # Patcher les globals
    _patch_pipeline_v5(pv5)

    # Récupérer chemins depuis config centralisée
    p = _get_paths_from_config(project_path)

    # Préparer ASC (terrain_data ou fichier)
    asc_path = _get_asc_path(p["asc_raw"])
    if not asc_path:
        st.error("❌ Heightmap manquante — configurez dans Heightmap → Chemins & fichiers")
        return

    output_dir = project_path / "outputs" / "generated" / "pipeline_preview"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Construire mask_config
    mask_config = _build_mask_config(pv5)

    # Charger surfaces_map pour affichage noms textures
    surfaces_map = _load_surfaces_map()

    # Récupérer grid_w et num_blk depuis reforger_grid
    project = st.session_state.get("current_project") or {}
    reforger_grid = project.get("reforger_grid") or {}
    grid_w = reforger_grid.get("tiles_x", 32)
    num_blk = reforger_grid.get("blocks_per_tile_x", 4)

    # Lancer pipeline
    with st.spinner("⏳ Génération preview en cours..."):
        try:
            result = pv5.run_pipeline(
                asc_path=asc_path,
                output_dir=output_dir,
                exclusion_path=p["excl"],
                gaea_flow=p["flow"],
                gaea_deposit=p["deposit"],
                data_dir=p["data_dir"],
                catalog_path=p["catalog"],
                satmap_path=p["satmap"],
                mask_config=mask_config,
                surfaces_map=surfaces_map,
                mode='preview',
                dry_run=True,
                grid_w=grid_w,
                num_blk=num_blk,
            )

            # Preview composite masques
            if 'masques' in result and 'dem' in result:
                from pipeline_preview import generate_mask_preview
                preview_rgb = generate_mask_preview(
                    result['masques'],
                    result['dem'],
                    result['cfg'],
                    output_size=1024
                )
                import cv2
                preview_path = output_dir / "preview_composite.png"
                cv2.imwrite(str(preview_path), cv2.cvtColor(preview_rgb, cv2.COLOR_RGB2BGR))
                with open(preview_path, 'rb') as f:
                    st.image(f.read(), caption="Preview masques", use_container_width=True)

            # Stats budget
            stats = result.get('stats', {})
            if stats:
                col1, col2, col3 = st.columns(3)
                col1.metric("Blocs OK (≤6 textures)", stats.get('n_ok', 0))
                col2.metric("Blocs dépassement (>6)", stats.get('n_over', 0))
                col3.metric("Total blocs", stats.get('total', 0))

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

    # Récupérer chemins depuis config centralisée
    p = _get_paths_from_config(project_path)

    asc_path = _get_asc_path(p["asc_raw"])
    if not asc_path:
        st.error("❌ Heightmap manquante")
        return

    output_dir = project_path / "outputs" / "masks" / "latest"
    output_dir.mkdir(parents=True, exist_ok=True)

    mask_config = _build_mask_config(pv5)
    surfaces_map = _load_surfaces_map()

    # Récupérer grid_w et num_blk depuis reforger_grid
    project = st.session_state.get("current_project") or {}
    reforger_grid = project.get("reforger_grid") or {}
    grid_w = reforger_grid.get("tiles_x", 32)
    num_blk = reforger_grid.get("blocks_per_tile_x", 4)

    with st.spinner("⏳ Export masques PNG..."):
        try:
            result = pv5.run_pipeline(
                asc_path=asc_path,
                output_dir=output_dir,
                exclusion_path=p["excl"],
                gaea_flow=p["flow"],
                gaea_deposit=p["deposit"],
                data_dir=p["data_dir"],
                mask_config=mask_config,
                surfaces_map=surfaces_map,
                mode='masks',
                dry_run=False,
                grid_w=grid_w,
                num_blk=num_blk,
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

    # Récupérer chemins depuis config centralisée
    p = _get_paths_from_config(project_path)

    asc_path = _get_asc_path(p["asc_raw"])
    if not asc_path:
        st.error("❌ Heightmap manquante")
        return

    if not p["data_dir"] or not p["data_dir"].exists():
        st.error("❌ Dossier .Data introuvable — configurez-le dans Heightmap → Chemins & fichiers")
        return

    output_dir = project_path / "outputs" / "latest"
    mask_config = _build_mask_config(pv5)
    surfaces_map = _load_surfaces_map()

    # Récupérer grid_w et num_blk depuis reforger_grid
    project = st.session_state.get("current_project") or {}
    reforger_grid = project.get("reforger_grid") or {}
    grid_w = reforger_grid.get("tiles_x", 32)
    num_blk = reforger_grid.get("blocks_per_tile_x", 4)

    prog_bar = st.progress(0)
    prog_text = st.empty()

    def progress_cb(tile_id):
        prog_text.text(f"Tuile {tile_id}...")
        # Estimation dynamique basée sur grid_w réel
        total_tiles = grid_w * grid_w
        prog_bar.progress(min(tile_id / total_tiles, 1.0))

    with st.spinner("⏳ Écriture .ttile en cours..."):
        try:
            print(f"[DEBUG] data_dir dans p = '{p.get('data_dir')}'")
            result = pv5.run_pipeline(
                asc_path=asc_path,
                output_dir=output_dir,
                exclusion_path=p["excl"],
                gaea_flow=p["flow"],
                gaea_deposit=p["deposit"],
                data_dir=p["data_dir"],
                mask_config=mask_config,
                surfaces_map=surfaces_map,
                mode='ttile',
                dry_run=False,
                progress_cb=progress_cb,
                grid_w=grid_w,
                num_blk=num_blk,
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

def _get_asc_path(asc_path_from_paths: Path | None):
    """Retourne le chemin ASC ou crée un tempfile depuis terrain_data."""
    terrain_data = st.session_state.get("terrain_data")

    # Si heightmap en mémoire, l'utiliser en priorité
    if terrain_data:
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
    elif asc_path_from_paths and asc_path_from_paths.exists():
        return asc_path_from_paths
    else:
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


def _load_surfaces_map():
    """Charge id_to_name depuis surfaces.json du projet actif."""
    project_path = st.session_state.get("current_project_path")
    if not project_path:
        return {}

    from pathlib import Path
    import json as _json

    p = Path(project_path)
    surfaces_json = p / "surfaces.json"

    if not surfaces_json.exists():
        return {}

    try:
        data = _json.loads(surfaces_json.read_text(encoding='utf-8'))
        mat_id_map = data.get("materials", {})  # {nom: id}
        # Inverser pour obtenir {id: nom}
        id_to_name = {v: k for k, v in mat_id_map.items()}
        return id_to_name
    except Exception as e:
        print(f"[SURFACES_MAP] Erreur chargement surfaces.json: {e}")
        return {}


def _build_mask_config(pv5):
    """Construit mask_config depuis la configuration projet."""
    from project_manager import load_mask_config, resolve_mask_config

    # Charger config projet (assignation masque → texture)
    project_path = st.session_state.get("current_project_path")
    if project_path:
        project_config = load_mask_config(project_path)
    else:
        project_config = {}

    # Charger mat_id_map depuis surfaces.json
    if project_path:
        from pathlib import Path
        p = Path(project_path)
        surfaces_json = p / "surfaces.json"
        if surfaces_json.exists():
            import json as _json
            data = _json.loads(surfaces_json.read_text(encoding='utf-8'))
            mat_id_map = data.get("materials", {})  # {nom: id}
        else:
            mat_id_map = {}
    else:
        mat_id_map = {}

    # Construire mask_config depuis DEFAULT_MASK_CONFIG + config projet
    mask_config_with_names = []
    for name, default_texture, color in pv5.DEFAULT_MASK_CONFIG:
        # Utiliser texture du projet si définie, sinon défaut
        texture_name = project_config.get(name, default_texture)
        mask_config_with_names.append((name, texture_name, color))

    # Résoudre noms → IDs via resolve_mask_config
    mask_config = resolve_mask_config(mat_id_map, mask_config_with_names)

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

        # Charger les paramètres (chemins maintenant dans paths centralisé)
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
    if not project_path:
        return
    json_path = Path(project_path) / "project.json"
    if not json_path.exists():
        return

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data.setdefault("pipeline_v5", {})

        # Sauvegarder les paramètres (chemins maintenant dans paths centralisé)
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
