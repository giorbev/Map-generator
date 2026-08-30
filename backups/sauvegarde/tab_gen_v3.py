# -*- coding: utf-8 -*-
"""
tab_gen_v3.py — Onglet Génération Pipeline V3
==============================================
Intégré dans app.py → with _g_textures: render_tab_gen_v3()

Utilise :
  - terrain_data déjà calculé (slope Z&T, heightmap, cellsize)
  - Masques Gaea depuis dossier projet ou upload direct
  - pipeline_v3 pour la génération des masques
  - Export vers sources/reforger/export_masks/ du projet (4K PNG 16-bit)
"""

import streamlit as st
import numpy as np
import cv2
from pathlib import Path
from PIL import Image
import io
import tempfile


# ============================================================================
# DÉTECTION DOSSIER GAEA
# ============================================================================

def _detect_gaea_dir(project_path: str) -> Path | None:
    """Cherche le dossier gaea dans la structure du projet."""
    if not project_path:
        return None
    p = Path(project_path)
    for candidate in ["gaea", "sources/gaea", "data/gaea", "masks/gaea"]:
        d = p / candidate
        if d.exists() and d.is_dir():
            return d
    return None


def _list_png(folder: Path) -> list[str]:
    """Liste les PNG dans un dossier, triés."""
    if not folder or not folder.exists():
        return []
    return sorted([f.name for f in folder.glob("*.png")])


# ============================================================================
# HELPERS AFFICHAGE
# ============================================================================

def _mask_preview(mask_f32: np.ndarray, title: str, width: int = 200):
    """Affiche un aperçu d'un masque float32 [0..1] en niveaux de gris."""
    preview = (np.clip(mask_f32, 0, 1) * 255).astype(np.uint8)
    # Redimensionner pour aperçu
    h, w = preview.shape
    ratio = width / max(w, 1)
    new_h = max(1, int(h * ratio))
    preview = cv2.resize(preview, (width, new_h), interpolation=cv2.INTER_AREA)
    st.image(preview, caption=title, width=width)


def _load_uploaded_or_path(uploaded_file, fallback_path: Path | None) -> np.ndarray | None:
    """
    Charge un masque depuis un st.file_uploader ou un fichier sur disque.
    Retourne float32 [0..1] ou None.
    """
    import cv2
    import numpy as np

    if uploaded_file is not None:
        # Depuis uploader → bytes en mémoire
        data = np.frombuffer(uploaded_file.read(), dtype=np.uint8)
        raw = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    elif fallback_path and fallback_path.exists():
        raw = cv2.imread(str(fallback_path), cv2.IMREAD_UNCHANGED)
    else:
        return None

    if raw is None:
        return None
    if raw.ndim == 3:
        raw = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    if raw.dtype == np.uint8:
        return raw.astype(np.float32) / 255.0
    elif raw.dtype == np.uint16:
        return raw.astype(np.float32) / 65535.0
    elif raw.dtype == np.float32:
        m = raw.max()
        return raw / m if m > 1.0 else raw
    return raw.astype(np.float32) / max(raw.max(), 1.0)


# ============================================================================
# RENDU PRINCIPAL
# ============================================================================

def render_tab_gen_v3():
    """Point d'entrée appelé depuis app.py dans with _g_textures:"""

    st.markdown("### 🎨 Pipeline V3 — Génération Masques Terrain")

    # ── Vérification projet + heightmap ──────────────────────────────────────
    project_path = st.session_state.get("current_project_path")
    terrain_data = st.session_state.get("terrain_data")

    if not project_path:
        st.warning("⚠️ Chargez un projet depuis la sidebar.")
        return

    if not terrain_data:
        st.warning("⚠️ Heightmap non chargée — ouvrez le projet avec une heightmap.")
        return

    cellsize  = float(terrain_data.get("cellsize", 4.0))
    heightmap = terrain_data["heightmap"]   # float32
    slope_zt  = terrain_data["slope"]       # slope Z&T, float32 en degrés
    flow_td   = terrain_data.get("flow")    # flow accumulation, peut être None

    p = Path(project_path)
    gaea_dir = _detect_gaea_dir(project_path)
    gaea_pngs = _list_png(gaea_dir) if gaea_dir else []

    st.caption(
        f"Heightmap : {heightmap.shape[1]}×{heightmap.shape[0]} px  |  "
        f"Cellsize : {cellsize}m  |  "
        f"Altitude : [{np.nanmin(heightmap):.0f}m … {np.nanmax(heightmap):.0f}m]"
    )

    # ── 1. SOURCES GAEA ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("📂 Sources")

    if gaea_dir:
        st.success(f"✅ Dossier Gaea détecté : `{gaea_dir.relative_to(p)}`  ({len(gaea_pngs)} PNG)")
    else:
        st.info("ℹ️ Pas de dossier Gaea détecté — upload manuel.")

    col_f, col_d, col_e = st.columns(3)

    # Helper : sélecteur PNG Gaea + uploader de remplacement
    def _source_selector(col, label, key_sel, key_up, default_names):
        with col:
            st.markdown(f"**{label}**")
            auto_path = None
            if gaea_pngs:
                options = ["— uploader un fichier —"] + gaea_pngs
                # Pré-sélectionner si nom trouvé
                default_idx = 0
                for name in default_names:
                    if name in gaea_pngs:
                        default_idx = gaea_pngs.index(name) + 1
                        break
                sel = st.selectbox(
                    "Depuis dossier Gaea", options,
                    index=default_idx, key=key_sel,
                    label_visibility="collapsed"
                )
                if sel != "— uploader un fichier —":
                    auto_path = gaea_dir / sel
                    st.caption(f"📄 {sel}")

            if auto_path is None:
                uploaded = st.file_uploader(
                    f"Uploader {label}", type=["png"],
                    key=key_up, label_visibility="collapsed"
                )
            else:
                uploaded = None
            return uploaded, auto_path

    flow_up,    flow_auto    = _source_selector(col_f, "🌊 Flow",    "sel_flow",    "up_flow",    ["flow.png", "Flow.png"])
    deposit_up, deposit_auto = _source_selector(col_d, "💧 Deposit", "sel_deposit", "up_deposit", ["deposit.png", "Deposit.png", "sediment.png"])
    excl_up,    excl_auto    = _source_selector(col_e, "🚫 Exclusion (opt.)", "sel_excl", "up_excl", ["exclusion.png", "masque_exclusion.png", "masque_exclusion_clean.png", "exclusion_clean.png", "mask_exclusion.png"])

    # Persister les chemins auto dans session_state pour survivre au rerun du bouton
    if flow_auto:    st.session_state["v3_flow_auto"]    = str(flow_auto)
    if deposit_auto: st.session_state["v3_deposit_auto"] = str(deposit_auto)
    if excl_auto:    st.session_state["v3_excl_auto"]    = str(excl_auto)
    else:            st.session_state["v3_excl_auto"]    = None

    # Fallback flow depuis terrain_data
    flow_source_label = "fichier Gaea"
    if flow_up is None and flow_auto is None:
        if flow_td is not None:
            st.info("ℹ️ Flow : utilisation du flow calculé depuis heightmap (fallback).")
            flow_source_label = "terrain_data (fallback)"
        else:
            st.warning("⚠️ Aucun masque flow — les zones de rivière ne seront pas générées.")

    # ── 2. PARAMÈTRES ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("⚙️ Paramètres")

    col_p1, col_p2 = st.columns(2)

    with col_p1:
        with st.expander("🏔️ Enrichissement slope (fBm)", expanded=False):
            roughness_mode = st.selectbox(
                "Mode", ["slope_perturb", "domain_warp", "additive", "Désactivé"],
                key="v3_roughness_mode"
            )
            roughness_mode = None if roughness_mode == "Désactivé" else roughness_mode
            amplitude = st.slider("Amplitude (°)", 0.0, 20.0, 8.0, 0.5, key="v3_amplitude")
            scale     = st.slider("Échelle fBm", 0.001, 0.02, 0.008, 0.001, key="v3_scale", format="%.3f")
            octaves   = st.slider("Octaves", 2, 8, 6, 1, key="v3_octaves")

        with st.expander("📐 Seuils de pente", expanded=False):
            st.caption("Laisser à 0 = auto depuis percentiles")
            t_gentle = st.slider("Gentle (°)", 0.0, 30.0, 0.0, 0.5, key="v3_gentle",
                                  help="0 = auto p70")
            t_landes = st.slider("Landes (°)", 0.0, 40.0, 0.0, 0.5, key="v3_landes",
                                  help="0 = auto p85")
            t_rock   = st.slider("Rock (°)",   0.0, 45.0, 22.0, 0.5, key="v3_rock")
            t_cliff  = st.slider("Cliff (°)",  0.0, 60.0, 26.0, 0.5, key="v3_cliff")
            trans_w  = st.slider("Zone neutre (°)", 1.0, 10.0, 5.0, 0.5, key="v3_trans")

        with st.expander("🌊 Masques côtiers", expanded=False):
            coastal_flat_w  = st.slider("Largeur flat (m)",  10.0, 200.0, 40.0, 5.0, key="v3_cf_width")
            coastal_slope_w = st.slider("Largeur slope (m)", 10.0, 200.0, 60.0, 5.0, key="v3_cs_width")
            cf_max_slope    = st.slider("Flat : pente max (°)",   1.0, 20.0, 10.0, 0.5, key="v3_cf_slope")
            cs_min_slope    = st.slider("Slope : pente min (°)",  5.0, 30.0, 15.0, 0.5, key="v3_cs_slope")

    with col_p2:
        with st.expander("🎚️ Post-processing", expanded=False):
            stretch_auto = st.checkbox("Stretch auto (p2-p98)", value=True, key="v3_stretch")
            weight_min   = st.slider("Weight min", 0.0, 0.3, 0.10, 0.01, key="v3_wmin",
                                      help="Poids minimum visible dans Workbench")
            flow_cut     = st.slider("Flow cut_low", 0.0, 0.8, 0.45, 0.05, key="v3_flow_cut",
                                      help="Coupe les valeurs faibles du masque flow")
            dep_cut      = st.slider("Deposit cut_low", 0.0, 0.8, 0.15, 0.05, key="v3_dep_cut")
            flow_gamma   = st.slider("Flow gamma", 0.1, 2.0, 0.5, 0.05, key="v3_flow_gamma")
            dep_gamma    = st.slider("Deposit gamma", 0.1, 2.0, 1.0, 0.05, key="v3_dep_gamma")

        with st.expander("🌿 Végétation", expanded=False):
            enable_veg  = st.checkbox("Générer masques végétation", value=True, key="v3_veg")
            veg_min_score = st.slider("Score minimum végétation", 0.05, 0.5, 0.15, 0.01, key="v3_veg_score")

        with st.expander("📊 QTRE", expanded=False):
            qtre_thresh = st.slider("Seuil présence QTRE", 0.01, 0.30, 0.10, 0.01, key="v3_qtre_thresh")

    # ── 3. DOSSIER DE SORTIE ─────────────────────────────────────────────────
    st.divider()
    default_out = str(p / "exports_mask")
    output_dir_str = st.text_input(
        "📁 Dossier de sortie",
        value=st.session_state.get("v3_output_dir", default_out),
        key="v3_output_dir_input",
        help="Les masques seront exportés ici en PNG 16-bit 4K"
    )
    st.session_state["v3_output_dir"] = output_dir_str

    # ── 4. LANCEMENT ─────────────────────────────────────────────────────────
    st.divider()
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run = st.button("🚀 Générer les masques", type="primary", use_container_width=True)
    with col_info:
        st.caption(
            "Génère : landes · rock · seabed · coastal_flat · coastal_slope · "
            "flow · deposit · végétation (×7) → normalisation QTRE"
        )

    if run:
        # Récupérer les chemins persistés depuis session_state
        _flow_auto    = Path(st.session_state["v3_flow_auto"])    if st.session_state.get("v3_flow_auto")    else flow_auto
        _deposit_auto = Path(st.session_state["v3_deposit_auto"]) if st.session_state.get("v3_deposit_auto") else deposit_auto
        _excl_auto    = Path(st.session_state["v3_excl_auto"])    if st.session_state.get("v3_excl_auto")    else None

        _run_pipeline_v3(
            heightmap=heightmap,
            slope_zt=slope_zt,
            flow_td=flow_td,
            cellsize=cellsize,
            flow_up=flow_up, flow_auto=_flow_auto,
            deposit_up=deposit_up, deposit_auto=_deposit_auto,
            excl_up=excl_up, excl_auto=_excl_auto,
            roughness_mode=roughness_mode,
            amplitude=amplitude, scale=scale, octaves=octaves,
            t_gentle=t_gentle, t_landes=t_landes, t_rock=t_rock,
            t_cliff=t_cliff, trans_w=trans_w,
            coastal_flat_w=coastal_flat_w, coastal_slope_w=coastal_slope_w,
            cf_max_slope=cf_max_slope, cs_min_slope=cs_min_slope,
            stretch_auto=stretch_auto, weight_min=weight_min,
            flow_cut=flow_cut, dep_cut=dep_cut,
            flow_gamma=flow_gamma, dep_gamma=dep_gamma,
            enable_veg=enable_veg, veg_min_score=veg_min_score,
            qtre_thresh=qtre_thresh,
            output_dir=Path(output_dir_str),
            project_path=p,
        )

    # ── 5. RÉSULTATS (si déjà générés) ───────────────────────────────────────
    if st.session_state.get("v3_results"):
        _render_results()


# ============================================================================
# EXÉCUTION PIPELINE
# ============================================================================

def _run_pipeline_v3(**kw):
    """Lance le pipeline v3 avec les paramètres de l'interface."""
    import sys, os
    _root = os.path.dirname(os.path.abspath(__file__))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    import pipeline_v3 as pv3

    output_dir: Path = kw["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    log_area  = st.empty()
    prog_bar  = st.progress(0)
    logs: list[str] = []

    def log(msg: str):
        logs.append(msg)
        log_area.code("\n".join(logs[-20:]), language="")

    def prog(pct: float):
        prog_bar.progress(min(pct, 1.0))

    try:
        # ── Patcher la config du pipeline v3 à la volée ──────────────────────
        pv3.ROUGHNESS_MODE      = kw["roughness_mode"]
        pv3.ROUGHNESS_AMPLITUDE = kw["amplitude"]
        pv3.ROUGHNESS_SCALE     = kw["scale"]
        pv3.ROUGHNESS_OCTAVES   = kw["octaves"]
        pv3.STRETCH_AUTO        = kw["stretch_auto"]
        pv3.WEIGHT_MIN          = kw["weight_min"]
        pv3.TRANSITION_WIDTH    = kw["trans_w"]
        pv3.THRESHOLD_ROCK      = kw["t_rock"]
        pv3.THRESHOLD_CLIFF     = kw["t_cliff"]
        pv3.THRESHOLD_GENTLE    = kw["t_gentle"] if kw["t_gentle"] > 0 else None
        pv3.THRESHOLD_LANDES    = kw["t_landes"] if kw["t_landes"] > 0 else None
        pv3.COASTAL_FLAT_WIDTH      = kw["coastal_flat_w"]
        pv3.COASTAL_SLOPE_WIDTH     = kw["coastal_slope_w"]
        pv3.COASTAL_FLAT_MAX_SLOPE  = kw["cf_max_slope"]
        pv3.COASTAL_SLOPE_MIN_SLOPE = kw["cs_min_slope"]
        pv3.ENABLE_VEGETATION   = kw["enable_veg"]
        pv3.VEG_MIN_SCORE       = kw["veg_min_score"]
        pv3.QTRE_PRESENCE_THRESH = kw["qtre_thresh"]
        pv3.OUTPUT_SIZE         = 4096
        pv3.CELL_SIZE           = kw["cellsize"]

        OUT = kw["output_dir"]
        H   = kw["heightmap"]
        S   = kw["slope_zt"]
        cs  = kw["cellsize"]
        n   = 4096

        # Resize heightmap et slope à 4096
        log("📐 Redimensionnement heightmap → 4096×4096…")
        dem_r   = cv2.resize(H, (n, n), interpolation=cv2.INTER_LINEAR)
        slope_r = cv2.resize(S, (n, n), interpolation=cv2.INTER_LINEAR)
        prog(0.05)

        # ── Enrichissement slope fBm ──────────────────────────────────────────
        log(f"🏔️ Enrichissement slope ({pv3.ROUGHNESS_MODE or 'désactivé'})…")
        if pv3.ROUGHNESS_MODE == "slope_perturb":
            noise = pv3.generate_fbm(n, n, scale=kw["scale"],
                                     octaves=kw["octaves"], seed=42)
            slope_r = slope_r + noise * kw["amplitude"]
        prog(0.10)

        # ── Seuils ───────────────────────────────────────────────────────────
        t = pv3.compute_thresholds(slope_r)
        log(f"📐 Seuils : gentle={t['gentle']}°  landes={t['landes']}°  "
            f"rock={t['rock']}°  cliff={t['cliff']}°")
        prog(0.12)

        # ── Masque d'exclusion ───────────────────────────────────────────────
        log("🚫 Chargement exclusion…")
        log(f"   excl_auto={kw['excl_auto']}  excl_up={kw['excl_up'] is not None}")
        excl_raw = _load_uploaded_or_path(kw["excl_up"], kw["excl_auto"])
        if excl_raw is not None:
            excl_r   = cv2.resize(excl_raw, (n, n), interpolation=cv2.INTER_NEAREST)
            exclusion = (excl_r > 0.5).astype(np.uint8)
            log(f"   Exclusion : {exclusion.mean()*100:.1f}% actif")
        else:
            exclusion = np.ones((n, n), dtype=np.uint8)
            log("   Pas d'exclusion — toute la carte active")
        prog(0.15)

        # ── Masques pente ─────────────────────────────────────────────────────
        log("📐 Génération landes + rock…")
        pv3.generate_slope_masks(slope_r, t, exclusion, n, OUT)
        log("   ✅ mask_landes_rocheuses.png  mask_rock.png")
        prog(0.25)

        # ── Seabed ───────────────────────────────────────────────────────────
        log("🌊 Seabed…")
        pv3.generate_seabed_mask(dem_r, n, OUT, sea_level=0.0, transition=0.0)
        log("   ✅ mask_seabed.png")
        prog(0.30)

        # ── Côtiers ──────────────────────────────────────────────────────────
        log("🏖️ Masques côtiers…")
        pv3.generate_coastal_masks(dem_r, slope_r, n, OUT)
        log("   ✅ mask_coastal_flat.png  mask_coastal_slope.png")
        prog(0.38)

        # ── Végétation ───────────────────────────────────────────────────────
        veg_masks = {}
        if kw["enable_veg"]:
            log("🌿 Génération végétation…")
            veg_masks = pv3.generate_vegetation_masks(
                dem_r, slope_r, exclusion, cs, n, OUT)
            for name, mask in veg_masks.items():
                mask = pv3.apply_output_curve(mask)
                pv3.save_mask_16bit(mask, OUT / f"{name}.png")
            log(f"   ✅ {len(veg_masks)} masques végétation")
        prog(0.54)

        # ── Flow ─────────────────────────────────────────────────────────────
        log("🌊 Chargement flow…")
        flow_raw = _load_uploaded_or_path(kw["flow_up"], kw["flow_auto"])
        if flow_raw is None and kw["flow_td"] is not None:
            flow_raw = kw["flow_td"].astype(np.float32)
            mx = flow_raw.max()
            if mx > 0:
                flow_raw /= mx
            log("   Flow depuis terrain_data (fallback)")
        if flow_raw is not None:
            flow_r = cv2.resize(flow_raw, (n, n), interpolation=cv2.INTER_LINEAR)
            flow_r[exclusion == 0] = 0.0
            flow_r = pv3.apply_output_curve(flow_r, gamma=kw["flow_gamma"],
                                            cut_low=kw["flow_cut"])

            # Effacer flow et deposit là où la végétation domine
            veg_sum = np.zeros_like(flow_r)
            for _veg_name in ["mask_foret_coniferes", "mask_foret_feuillue", "mask_maquis_landes",
                               "mask_landes_plateau", "mask_prairie_humide", "mask_prairie_seche",
                               "mask_alpages"]:
                _veg_path = OUT / f"{_veg_name}.png"
                if _veg_path.exists():
                    _veg_arr = cv2.imread(str(_veg_path), cv2.IMREAD_UNCHANGED)
                    if _veg_arr is not None:
                        veg_sum += _veg_arr.astype(np.float32) / 65535.0
            veg_dominant = veg_sum > 0.4
            flow_r[veg_dominant] = 0.0

            pv3.save_mask_16bit(flow_r, OUT / "mask_flow.png")
            log("   ✅ mask_flow.png")
        else:
            log("   ⚠️ Pas de flow — masque ignoré")
        prog(0.64)

        # ── Deposit ──────────────────────────────────────────────────────────
        log("💧 Chargement deposit…")
        dep_raw = _load_uploaded_or_path(kw["deposit_up"], kw["deposit_auto"])
        if dep_raw is not None:
            dep_r = cv2.resize(dep_raw, (n, n), interpolation=cv2.INTER_LINEAR)
            dep_r[exclusion == 0] = 0.0
            dep_r = pv3.apply_output_curve(dep_r, gamma=kw["dep_gamma"],
                                           cut_low=kw["dep_cut"])

            # Effacer deposit là où la végétation domine
            if 'veg_dominant' in locals():
                dep_r[veg_dominant] = 0.0

            pv3.save_mask_16bit(dep_r, OUT / "mask_deposit.png")
            log("   ✅ mask_deposit.png")
        else:
            log("   ⚠️ Pas de deposit — masque ignoré")
        prog(0.72)

        # ── Normalisation exclusive ───────────────────────────────────────────
        log("⚖️ Normalisation exclusive…")
        pv3.normalize_exclusive(veg_masks, pv3.MASK_PRIORITY, n, OUT)
        log("   ✅ Normalisation terminée")
        prog(0.85)

        # ── QTRE ─────────────────────────────────────────────────────────────
        log("📊 Analyse QTRE…")
        pv3.check_qtre(OUT, pv3.MASK_PRIORITY, cs)
        prog(0.95)

        # ── Renommer avec préfixe ordre d'insertion ───────────────────────────
        log("🔢 Numérotation masques par ordre de priorité…")
        _rename_with_priority(OUT, pv3.MASK_PRIORITY)
        prog(1.0)

        log("✅ Pipeline V3 terminé !")
        st.success(f"✅ {len(pv3.MASK_PRIORITY)} masques générés → `{OUT}`")

        # Sauvegarder résultats dans session_state
        st.session_state["v3_results"] = {
            "output_dir": str(OUT),
            "masks": pv3.MASK_PRIORITY,
            "thresholds": t,
        }
        # Sauvegarder dans project.json
        _save_v3_to_project(kw["project_path"], str(OUT))

    except Exception as e:
        import traceback
        st.error(f"❌ Erreur : {e}")
        st.code(traceback.format_exc())
    finally:
        prog_bar.empty()


# ============================================================================
# RENOMMAGE AVEC PRÉFIXE ORDRE D'INSERTION
# ============================================================================

def _rename_with_priority(output_dir: Path, priority: list[str]):
    """
    Renomme les masques avec un préfixe numérique selon l'ordre de priorité.
    Ex: mask_seabed.png → 01_mask_seabed.png
    """
    for i, name in enumerate(priority, start=1):
        src = output_dir / f"{name}.png"
        dst = output_dir / f"{i:02d}_{name}.png"
        if src.exists():
            # Supprimer l'ancienne version numérotée si elle existe
            if dst.exists():
                dst.unlink()
            src.rename(dst)


# ============================================================================
# AFFICHAGE RÉSULTATS
# ============================================================================

def _render_results():
    """Affiche les résultats de la dernière génération."""
    results = st.session_state["v3_results"]
    out_dir = Path(results["output_dir"])

    st.divider()
    st.subheader("📊 Résultats")

    # ── QTRE map ─────────────────────────────────────────────────────────────
    qtre_path = out_dir / "qtre_map.png"
    if qtre_path.exists():
        st.markdown("**Carte QTRE**")
        img = Image.open(qtre_path)
        st.image(img, width='stretch', caption="Densité textures par bloc 32m")

    # ── Aperçu masques ───────────────────────────────────────────────────────
    st.markdown("**Aperçu masques générés**")
    masks = results["masks"]
    # Afficher en grille 4 colonnes
    cols = st.columns(4)
    col_idx = 0
    for i, name in enumerate(masks, start=1):
        mask_path = out_dir / f"{i:02d}_{name}.png"
        if not mask_path.exists():
            mask_path = out_dir / f"{name}.png"
        if mask_path.exists():
            with cols[col_idx % 4]:
                img = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
                if img is not None:
                    # Convertir en uint8 pour affichage
                    if img.dtype == np.uint16:
                        img = (img / 256).astype(np.uint8)
                    # Redimensionner pour aperçu
                    preview = cv2.resize(img, (256, 256), interpolation=cv2.INTER_AREA)
                    st.image(preview, caption=f"{i:02d} {name.replace('mask_','')}", width=200)
            col_idx += 1

    # ── Infos export ─────────────────────────────────────────────────────────
    st.info(
        f"📁 Masques exportés dans :\n`{out_dir}`\n\n"
        f"Format : PNG 16-bit 4096×4096 px\n"
        f"Nommage : `01_mask_seabed.png`, `02_mask_coastal_flat.png`…"
    )


# ============================================================================
# SAUVEGARDE DANS PROJECT.JSON
# ============================================================================

def _save_v3_to_project(project_path: Path, output_dir: str):
    """Sauvegarde les paramètres pipeline v3 dans project.json."""
    import json
    json_path = project_path / "project.json"
    if not json_path.exists():
        return
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data.setdefault("pipeline_v3", {})
        data["pipeline_v3"]["output_dir"] = output_dir
        data["pipeline_v3"]["params"] = {
            "roughness_mode":     st.session_state.get("v3_roughness_mode", "slope_perturb"),
            "amplitude":          st.session_state.get("v3_amplitude", 8.0),
            "scale":              st.session_state.get("v3_scale", 0.008),
            "stretch_auto":       st.session_state.get("v3_stretch", True),
            "weight_min":         st.session_state.get("v3_wmin", 0.10),
            "flow_cut_low":       st.session_state.get("v3_flow_cut", 0.45),
            "deposit_cut_low":    st.session_state.get("v3_dep_cut", 0.15),
            "t_rock":             st.session_state.get("v3_rock", 22.0),
            "t_cliff":            st.session_state.get("v3_cliff", 26.0),
            "coastal_flat_width": st.session_state.get("v3_cf_width", 40.0),
            "coastal_slope_width":st.session_state.get("v3_cs_width", 60.0),
            "qtre_thresh":        st.session_state.get("v3_qtre_thresh", 0.10),
        }
        from datetime import datetime
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        st.warning(f"⚠️ Sauvegarde project.json échouée : {e}")
