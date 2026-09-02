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
from naturemap_biomes_generator import NatureMapBiomesGenerator
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
# SESSION STATE MANAGEMENT
# ============================================================================

def initialize_session():
    """Initialise les variables de session."""
    if 'heightmap_path' not in st.session_state:
        st.session_state.heightmap_path = None
    if 'base_map' not in st.session_state:
        st.session_state.base_map = None
    if 'satmap_path' not in st.session_state:
        st.session_state.satmap_path = None
    if 'last_generated' not in st.session_state:
        st.session_state.last_generated = {}

initialize_session()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_output_dir():
    """Crée et retourne le dossier output."""
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

@st.cache_data
def load_image(path):
    """Charge une image et la met en cache."""
    try:
        return Image.open(path)
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

# ============================================================================
# SIDEBAR — CHARGEMENT ET EXPORT
# ============================================================================

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
            st.session_state.base_map = BaseMap(temp_heightmap)
        
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

st.sidebar.divider()

# Section Export heightmap
if st.session_state.heightmap_path is not None:
    st.sidebar.markdown("### 📥 Export Heightmap")
    
    export_format = st.sidebar.radio(
        "Format export",
        ["PNG 16-bit", "PNG 8-bit", "ASC"],
        horizontal=True
    )
    
    if st.sidebar.button("📥 Exporter", key="export_heightmap"):
        try:
            output_dir = get_output_dir()
            timestamp = format_timestamp()
            
            base_map = st.session_state.base_map
            
            if export_format == "PNG 16-bit":
                # Normaliser 0-65535
                heightmap_16 = (base_map.heightmap_uint8.astype(np.float32) / 255.0 * 65535).astype(np.uint16)
                output_path = f"{output_dir}/heightmap_export_{timestamp}_16bit.png"
                Image.fromarray(heightmap_16, mode='I;16').save(output_path)
                
                # Sauvegarder metadata
                metadata = {
                    "altitude_min": float(base_map.altitude_min),
                    "altitude_max": float(base_map.altitude_max),
                    "width": base_map.width,
                    "height": base_map.height,
                    "timestamp": timestamp
                }
                with open(f"{output_dir}/heightmap_export_{timestamp}_16bit_metadata.json", "w") as f:
                    json.dump(metadata, f, indent=2)
            
            elif export_format == "PNG 8-bit":
                output_path = f"{output_dir}/heightmap_export_{timestamp}_8bit.png"
                Image.fromarray(base_map.heightmap_uint8).save(output_path)
            
            # ASC export — TODO: implémenter selon format ASC
            
            st.sidebar.success(f"✅ Exporté: {Path(output_path).name}")
        except Exception as e:
            st.sidebar.error(f"❌ Erreur export: {e}")

# ============================================================================
# MAIN CONTENT — ONGLETS
# ============================================================================

st.markdown('<h1 class="main-header">🗺️ Map Generator Pro v3.0</h1>', unsafe_allow_html=True)

if st.session_state.base_map is None:
    st.warning("⚠️ Veuillez d'abord charger une heightmap dans la barre latérale (gauche)")
else:
    # Onglets principaux
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🎨 Hypsométrique PURE",
        "🌿 NatureMap Biomes",
        "🖼️ Aperçu Texture",
        "📊 Calques Textures",
        "📈 Analyse Heightmap",
        "🌱 Végétation"
    ])
    
    # ========================================================================
    # ONGLET 1: HYPSOMÉTRIQUE PURE
    # ========================================================================
    
    with tab1:
        st.markdown("### 🎨 Colormap Hypsométrique")
        st.markdown("""
        Génère une carte colorée basée **uniquement** sur l'altitude, sans texture complexe.
        
        **Palette:** Vert (bas) → Jaune → Orange → Rouge → Marron (haut)
        """)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            enable_hillshade = st.checkbox("☀️ Hillshading", value=False)
        with col2:
            hillshade_strength = st.slider(
                "Force ombrage",
                0.0, 1.0, 0.5,
                help="Intensité de l'ombrage directionnel"
            )
        with col3:
            if st.button("🚀 Générer Hypsométrique", key="gen_hypsometric"):
                try:
                    with st.spinner("⏳ Génération colormap hypsométrique..."):
                        output_dir = get_output_dir()
                        hypsometric_gen = HypsometricColormapGenerator(
                            st.session_state.heightmap_path,
                            output_dir=output_dir
                        )
                        
                        # Génération retourne (Image PIL, array)
                        pil_img, colormap_array = hypsometric_gen.generate(smooth=True)
                        
                        # Sauvegarder en PNG
                        timestamp = format_timestamp()
                        colormap_path = f"{output_dir}/color_map_hypsometric_{timestamp}.png"
                        pil_img.save(colormap_path)
                        
                        st.session_state.last_generated['hypsometric'] = colormap_path
                        st.success("✅ Hypsométrique générée")
                except Exception as e:
                    st.error(f"❌ Erreur: {e}")
        
        # Affichage résultat
        if 'hypsometric' in st.session_state.last_generated:
            try:
                img = load_image(st.session_state.last_generated['hypsometric'])
                if img:
                    st.image(img, caption="Colormap Hypsométrique", use_container_width=True)
                    
                    # Bouton téléchargement
                    with open(st.session_state.last_generated['hypsometric'], "rb") as f:
                        st.download_button(
                            "📥 Télécharger PNG",
                            f.read(),
                            file_name=Path(st.session_state.last_generated['hypsometric']).name,
                            mime="image/png"
                        )
            except Exception as e:
                st.error(f"❌ Erreur affichage: {e}")
    
    # ========================================================================
    # ONGLET 2: NATUREMAP BIOMES
    # ========================================================================
    
    with tab2:
        st.markdown("### 🌿 NatureMap - Occupation des Sols")
        st.markdown("""
        Carte d'occupation avec **8 biomes** basée sur altitude et pentes:
        - 🌊 Eau | ❄️ Neige | 🪨 Roche | 🏔️ Toundra
        - 🌲 Forêt dense | 🌱 Prairie | 🏖️ Sable
        """)
        
        if st.button("🚀 Générer NatureMap", key="gen_naturemap"):
            try:
                with st.spinner("⏳ Génération NatureMap..."):
                    output_dir = get_output_dir()
                    naturemap_gen = NatureMapBiomesGenerator(
                        st.session_state.heightmap_path,
                        output_dir=output_dir
                    )
                    
                    # Générer retourne PIL Image
                    pil_img = naturemap_gen.generate()
                    
                    # Sauvegarder en PNG
                    timestamp = format_timestamp()
                    nature_map_path = f"{output_dir}/nature_map_biomes_{timestamp}.png"
                    pil_img.save(nature_map_path)
                    
                    st.session_state.last_generated['naturemap'] = nature_map_path
                    st.success("✅ NatureMap générée")
            except Exception as e:
                st.error(f"❌ Erreur: {e}")
        
        # Affichage résultat
        if 'naturemap' in st.session_state.last_generated:
            try:
                img = load_image(st.session_state.last_generated['naturemap'])
                if img:
                    st.image(img, caption="Carte Biomes (NatureMap)", use_container_width=True)
                    
                    # Bouton téléchargement
                    with open(st.session_state.last_generated['naturemap'], "rb") as f:
                        st.download_button(
                            "📥 Télécharger PNG",
                            f.read(),
                            file_name=Path(st.session_state.last_generated['naturemap']).name,
                            mime="image/png"
                        )
            except Exception as e:
                st.error(f"❌ Erreur affichage: {e}")
    
    # ========================================================================
    # ONGLET 3: APERÇU TEXTURE
    # ========================================================================
    
    with tab3:
        st.markdown("### 🖼️ Aperçu Texture Terrain 2D")
        st.markdown("""
        Prévisualisation des textures terrain:
        - **Roche** (RGB 160,160,160)
        - **Sol/Terre** (RGB 139,94,60)
        - **Herbe** (RGB 76,170,78)
        - **Eau** (RGB 50,120,220)
        - **Neige** (RGB 245,245,245)
        """)
        
        col1, col2 = st.columns(2)
        with col1:
            climate_profile = st.selectbox(
                "Profil climatique",
                ["Tempéré", "Aride", "Continental", "Tropical", "Subarctique", "Alpin"]
            )
        with col2:
            if st.button("🚀 Générer Aperçu", key="gen_texture_preview"):
                st.info("⏳ À implémenter - Utiliser TextureLayerGenerator")
    
    # ========================================================================
    # ONGLET 4: CALQUES TEXTURES
    # ========================================================================
    
    with tab4:
        st.markdown("### 📊 Calques Textures par Pente")
        st.markdown("""
        Génère des masques PNG noir/blanc par tranche de pente:
        - **Herbe/Prairie:** 0–3°
        - **Terre/Sol:** 3–12°
        - **Roche Légère:** 12–25°
        - **Roche Forte:** 25–45°
        - **Escarpement:** 45°+
        """)
        
        if st.button("🚀 Générer Calques", key="gen_texture_layers"):
            try:
                with st.spinner("⏳ Génération calques textures..."):
                    output_dir = get_output_dir()
                    texture_gen = TextureLayerGenerator(
                        st.session_state.heightmap_path,
                        output_dir=output_dir
                    )
                    
                    # Générer calques de slopes adaptatifs
                    layers = texture_gen.generate_slope_masks()
                    st.session_state.last_generated['texture_layers'] = layers
                    st.success("✅ Calques textures générés")
            except Exception as e:
                st.error(f"❌ Erreur: {e}")
        
        # Affichage résultats
        if 'texture_layers' in st.session_state.last_generated:
            st.markdown("#### Calques générés:")
            layers = st.session_state.last_generated['texture_layers']
            
            output_dir = get_output_dir()
            cols = st.columns(2)
            
            for idx, (layer_name, layer_data) in enumerate(layers.items()):
                with cols[idx % 2]:
                    st.markdown(f"**{layer_name}**")
                    try:
                        # Convertir array numpy en image PIL
                        if isinstance(layer_data, np.ndarray):
                            img = Image.fromarray(layer_data)
                            
                            # Sauvegarder pour download
                            layer_path = f"{output_dir}/{layer_name}_mask.png"
                            img.save(layer_path)
                            
                            st.image(img, use_container_width=True)
                        else:
                            st.warning(f"Format inattendu pour {layer_name}")
                    except Exception as e:
                        st.warning(f"Impossible d'afficher {layer_name}: {e}")
    
    # ========================================================================
    # ONGLET 5: ANALYSE HEIGHTMAP
    # ========================================================================
    
    with tab5:
        st.markdown("### 📈 Analyse Heightmap")
        
        base_map = st.session_state.base_map
        
        # Statistiques
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Dimensions", f"{base_map.width}×{base_map.height}px")
        with col2:
            st.metric("Alt. Min", f"{base_map.altitude_min:.0f}m")
        with col3:
            st.metric("Alt. Max", f"{base_map.altitude_max:.0f}m")
        with col4:
            st.metric("Dénivellation", f"{(base_map.altitude_max - base_map.altitude_min):.0f}m")
        
        # Histogramme altitudes
        st.markdown("#### Distribution des altitudes")
        altitude_data = base_map.heightmap_uint8.flatten()
        st.bar_chart({
            "Fréquence": np.histogram(altitude_data, bins=100)[0]
        })
        
        # Pentes
        st.markdown("#### Distribution des pentes")
        if hasattr(base_map, 'slopes') and base_map.slopes is not None:
            slopes_data = base_map.slopes.flatten()
            slopes_data = slopes_data[~np.isnan(slopes_data)]
            st.bar_chart({
                "Fréquence": np.histogram(slopes_data, bins=50)[0]
            })
        else:
            st.info("Pentes non calculées dans BaseMap")
    
    # ========================================================================
    # ONGLET 6: VÉGÉTATION
    # ========================================================================
    
    with tab6:
        st.markdown("### 🌱 Potentiel de Végétation")
        st.markdown("""
        Génère des masques de probabilité de végétation basés sur:
        - Altitude (zone de végétation)
        - Pente (stabilité du sol)
        - Exposition (versants nord = plus humide)
        - Accumulation de flux (zones humides)
        """)
        
        if st.button("🚀 Générer Végétation", key="gen_vegetation"):
            st.info("⏳ À implémenter - Créer VegetationGenerator")

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
