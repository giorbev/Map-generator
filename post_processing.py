# -*- coding: utf-8 -*-
"""
Post-Processing — Fusion Géographique Mappeur + Pipeline
=========================================================

Principe fondamental :
- Mappeur a peint sa carte → on garde ses zones importantes
- Pipeline_v2 → remplace uniquement les zones naturelles
- Zones géographiquement exclusives → 0% chevauchement

Workflow :
1. Upload + Preview coloré (avec légende)
2. Sélection tuiles interactive (grille 32×32)
3. Analyse textures dans zones sélectionnées
4. Juxtaposition géographique stricte
5. Nettoyage QTRE + Export PNG 16-bit

VERSION : v7.0 — Refonte complète avec sélection visuelle
"""

import numpy as np
from pathlib import Path
import cv2
import plotly.graph_objects as go


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — MAPPING PIPELINE → TEXTURES VANILLA
# ══════════════════════════════════════════════════════════════════════════════

# Renommage masks pipeline pour correspondre aux noms de textures Reforger
# Préfixes numérotés préservés pour ordre layering
PIPELINE_RENAME = {
    '01_seabed': '01_seabed',
    '02_coastal_pebbles': '02_pebbles_02',        # Galets côtiers
    '03_coastal_grass': '03_coastal_grass',
    '04_rock': '04_rock',                         # Rock unifié (coastal + alpine fusionnés)
    '05_debris_rock': '05_debris_rock',
    '06_dirt_erosion': '06_dirt_03',
    '07_mud_river': '07_dirt_02',
    '08_grass_low': '08_grass_01',
    '09_grass_mid': '09_grass_02',
    '10_grass_high': '10_grass_03',
    '11_mountain_grass_low': '11_mountain_grass_01',
    '12_mountain_grass_high': '12_mountaingrass_03',
    '13_heather': '13_heather',
    '14_forest_floor_deciduous': '14_forest_floor_deciduous',
    '15_forest_floor_coniferous': '15_forest_floor_coniferous',
    'pebbles': '01_pebbles_01',  # Si existe (terres)
}

# Masks mappeur à ignorer (remplacés par nouvelles textures pipeline)
MAPPEUR_IGNORE = [
    'rock_01',    # Remplacé par rock_coastal + rock_alpine
    'rock_02',    # Remplacé par rock_coastal + rock_alpine
]

# Textures urbaines du mappeur à conserver (le reste est remplacé par pipeline)
TEXTURES_URBAINES_MAPPEUR = [
    'asphalt',
    'concrete',
    'cobblestone',
    'cropfield',
    'zi_',          # Toutes les textures ZI custom
    'dirt_01',      # Routes/chemins urbains
    'pebbles_01',   # Chemins galets urbains
]


# ══════════════════════════════════════════════════════════════════════════════
# ÉTAPE 1 — APERÇU COLORÉ
# ══════════════════════════════════════════════════════════════════════════════

def generate_colored_preview(
    mappeur_masks: dict,
    get_color_func: callable,
    boost_dark_colors: bool = False
) -> tuple:
    """
    Génère aperçu 2D coloré des masks mappeur avec couleurs vanilla + ZI.

    Optimisé : Winner-takes-all (texture dominante par pixel)

    Args:
        mappeur_masks: {nom_fichier: array uint16}
        get_color_func: Fonction get_texture_color(texture_name) -> (r, g, b)

    Returns:
        (preview_rgb, legend)
        - preview_rgb: np.ndarray (H, W, 3) RGB uint8 0-255
        - legend: dict {texture_name: (r, g, b)}
    """
    if not mappeur_masks:
        return np.zeros((100, 100, 3), dtype=np.uint8), {}

    print(f"[PREVIEW] Génération aperçu pour {len(mappeur_masks)} textures...")

    # Obtenir shape
    shape = list(mappeur_masks.values())[0].shape
    preview_rgb = np.zeros((*shape, 3), dtype=np.uint8)
    legend = {}

    # Downsampling pour accélérer si >2048px
    max_preview = 2048
    scale = 1.0
    if shape[0] > max_preview or shape[1] > max_preview:
        scale = min(max_preview / shape[0], max_preview / shape[1])
        preview_shape = (int(shape[0] * scale), int(shape[1] * scale))
        preview_rgb = np.zeros((*preview_shape, 3), dtype=np.uint8)
        print(f"[PREVIEW] Downsampling {shape} → {preview_shape}")

    # Normaliser et downsampler masks
    masks_norm = {}
    for fname, mask in mappeur_masks.items():
        tex_name = Path(fname).stem.lower()
        mask_f32 = mask.astype(np.float32) / 65535.0

        if scale < 1.0:
            mask_f32 = cv2.resize(mask_f32, (preview_rgb.shape[1], preview_rgb.shape[0]), interpolation=cv2.INTER_AREA)

        masks_norm[tex_name] = mask_f32

    # Winner-takes-all : pour chaque pixel, texture la plus forte
    max_intensity = np.zeros(preview_rgb.shape[:2], dtype=np.float32)
    winner_map = np.full(preview_rgb.shape[:2], -1, dtype=np.int32)

    tex_list = list(masks_norm.keys())
    colors_array = []

    for idx, (tex_name, mask) in enumerate(masks_norm.items()):
        color = get_color_func(tex_name)
        legend[tex_name] = color
        colors_array.append(color)

        print(f"[PREVIEW] {tex_name}: RGB{color}")

        # Mettre à jour winner
        is_winner = mask > max_intensity
        max_intensity = np.maximum(max_intensity, mask)
        winner_map[is_winner] = idx

    # Appliquer couleurs
    for idx, tex_name in enumerate(tex_list):
        color = colors_array[idx]
        is_this_texture = (winner_map == idx)

        # Booster les couleurs sombres si demandé
        if boost_dark_colors:
            brightness = sum(color) / 3
            if brightness < 80:  # Couleur sombre
                # Multiplier par facteur pour éclaircir
                boost_factor = 80 / (brightness + 1)
                color = tuple(min(255, int(c * boost_factor)) for c in color)
                print(f"[PREVIEW] {tex_name}: {colors_array[idx]} → {color} (boosted)")

        # Vérifier si couleur noire/grise par défaut
        if colors_array[idx] == (128, 128, 128):
            print(f"[WARNING] {tex_name} utilise couleur DÉFAUT (gris)")
        elif sum(colors_array[idx]) < 50:
            print(f"[WARNING] {tex_name} couleur TRÈS SOMBRE: {colors_array[idx]} → {color}")

        preview_rgb[is_this_texture] = color

    # Pixels sans texture = gris clair (au lieu de noir)
    no_texture = (winner_map == -1)
    if np.any(no_texture):
        count_no_tex = int(np.sum(no_texture))
        print(f"[PREVIEW] {count_no_tex:,} pixels SANS TEXTURE → gris clair")
        preview_rgb[no_texture] = (200, 200, 200)  # Gris clair au lieu de noir

    print(f"[PREVIEW] Aperçu généré")
    return preview_rgb, legend


# ══════════════════════════════════════════════════════════════════════════════
# ÉTAPE 2 — SÉLECTION TUILES INTERACTIVE
# ══════════════════════════════════════════════════════════════════════════════

def create_tile_selector_plotly(
    preview_rgb: np.ndarray,
    tile_size_px: int,
    selected_tiles: set = None
) -> go.Figure:
    """
    Crée figure Plotly interactive avec grille de tuiles cliquables.

    Args:
        preview_rgb: Image aperçu (H, W, 3) uint8
        tile_size_px: Taille tuile en pixels
        selected_tiles: Set de tuples (x, y) déjà sélectionnées

    Returns:
        Figure Plotly avec image + grille rectangles
    """
    if selected_tiles is None:
        selected_tiles = set()

    h, w = preview_rgb.shape[:2]
    n_tiles_x = w // tile_size_px
    n_tiles_y = h // tile_size_px

    # Créer figure avec image de fond
    fig = go.Figure()

    # Ajouter image de fond
    fig.add_trace(go.Image(z=preview_rgb))

    # Ajouter rectangles pour chaque tuile
    shapes = []
    for ty in range(n_tiles_y):
        for tx in range(n_tiles_x):
            x0 = tx * tile_size_px
            y0 = ty * tile_size_px
            x1 = x0 + tile_size_px
            y1 = y0 + tile_size_px

            # Tuile sélectionnée = rectangle bleu semi-transparent
            if (tx, ty) in selected_tiles:
                color = 'rgba(0, 120, 255, 0.4)'
                width = 2
            else:
                color = 'rgba(128, 128, 128, 0.1)'
                width = 1

            shapes.append(dict(
                type='rect',
                x0=x0, y0=y0, x1=x1, y1=y1,
                line=dict(color=color, width=width),
                fillcolor=color if (tx, ty) in selected_tiles else 'rgba(0,0,0,0)'
            ))

    fig.update_layout(
        shapes=shapes,
        xaxis=dict(visible=False, range=[0, w]),
        yaxis=dict(visible=False, range=[h, 0], scaleanchor='x'),
        margin=dict(l=0, r=0, t=30, b=0),
        height=min(800, h),
        title="Cliquez sur les tuiles pour sélectionner les zones à garder (mappeur)",
        hovermode='closest'
    )

    return fig


def tiles_to_zone_mask(
    selected_tiles: set,
    tile_size_px: int,
    image_shape: tuple
) -> np.ndarray:
    """
    Convertit sélection tuiles en masque binaire zone_mask.

    Args:
        selected_tiles: Set de (x, y) tuples
        tile_size_px: Taille tuile en pixels
        image_shape: (H, W) de l'image finale

    Returns:
        zone_mask: np.ndarray uint8 (H, W)
                   255 = garder mappeur
                   0   = pipeline_v2
    """
    h, w = image_shape[:2]
    zone_mask = np.zeros((h, w), dtype=np.uint8)

    for (tx, ty) in selected_tiles:
        x0 = tx * tile_size_px
        y0 = ty * tile_size_px
        x1 = min(x0 + tile_size_px, w)
        y1 = min(y0 + tile_size_px, h)

        zone_mask[y0:y1, x0:x1] = 255

    return zone_mask


def click_to_tile(click_x: float, click_y: float, tile_size_px: int) -> tuple:
    """
    Convertit coordonnées clic Plotly en indices tuile.

    Args:
        click_x, click_y: Coordonnées pixel du clic
        tile_size_px: Taille tuile

    Returns:
        (tile_x, tile_y)
    """
    tx = int(click_x // tile_size_px)
    ty = int(click_y // tile_size_px)
    return (tx, ty)


# ══════════════════════════════════════════════════════════════════════════════
# ÉTAPE 3 — ANALYSE TEXTURES SÉLECTIONNÉES
# ══════════════════════════════════════════════════════════════════════════════

def analyze_selected_tiles_textures(
    mappeur_masks: dict,
    zone_mask: np.ndarray,
    threshold: float = 0.05
) -> dict:
    """
    Analyse quelles textures mappeur sont présentes dans les tuiles sélectionnées.

    Args:
        mappeur_masks: {nom_fichier: array uint16}
        zone_mask: Masque binaire (255=garder / 0=pipeline)
        threshold: Seuil de présence (0.05 = 5%)

    Returns:
        {
            'textures_gardees': list,
            'textures_absentes': list,
            'stats': dict {texture: {'px_in_zone', 'px_total', 'pct_in_zone'}}
        }
    """
    garder = zone_mask > 128
    textures_gardees = []
    textures_absentes = []
    stats = {}

    for fname, mask in mappeur_masks.items():
        tex_name = Path(fname).stem.lower()

        # Détection automatique 8-bit vs 16-bit
        max_val = np.max(mask)
        if max_val <= 255:
            # 8-bit
            mask_norm = mask.astype(np.float32) / 255.0
        else:
            # 16-bit
            mask_norm = mask.astype(np.float32) / 65535.0

        # Pixels présents dans zone gardée
        px_in_zone = int(np.sum((mask_norm > threshold) & garder))
        px_total = int(np.sum(mask_norm > threshold))

        stats[tex_name] = {
            'px_in_zone': px_in_zone,
            'px_total': px_total,
            'pct_in_zone': float(px_in_zone / (px_total + 1e-6) * 100)
        }

        if px_in_zone > 0:
            textures_gardees.append(tex_name)
        else:
            textures_absentes.append(tex_name)

    return {
        'textures_gardees': sorted(textures_gardees),
        'textures_absentes': sorted(textures_absentes),
        'stats': stats
    }


# ══════════════════════════════════════════════════════════════════════════════
# ÉTAPE 4 — JUXTAPOSITION GÉOGRAPHIQUE
# ══════════════════════════════════════════════════════════════════════════════

def juxtapose_masks(
    mappeur_masks: dict,
    v2_masks: dict,
    zone_mask: np.ndarray
) -> dict:
    """
    Juxtapose masks mappeur et pipeline_v2 selon zone_mask.

    Principe :
    - Zone gardée (255)  → masks mappeur intacts
    - Zone pipeline (0)  → masks pipeline_v2
    - Zones exclusives   → 0% chevauchement

    Args:
        mappeur_masks: {nom_fichier: array uint16}
        v2_masks: {nom_texture: array float32 0-1}
        zone_mask: Masque binaire uint8 (255=mappeur / 0=pipeline)

    Returns:
        dict {nom_texture: array float32 0-1}
    """
    garder = (zone_mask > 128).astype(np.float32)
    pipeline = 1.0 - garder

    # ═══════════════════════════════════════════════════════════════════
    # 1. RENOMMER MASKS PIPELINE
    # ═══════════════════════════════════════════════════════════════════
    v2_renamed = {}
    for old_name, mask in v2_masks.items():
        new_name = PIPELINE_RENAME.get(old_name, old_name)
        v2_renamed[new_name] = mask
        if old_name != new_name:
            print(f"  [RENAME] {old_name} → {new_name}")

    # ═══════════════════════════════════════════════════════════════════
    # 2. NORMALISER MASKS MAPPEUR (ignorer ceux remplacés)
    # ═══════════════════════════════════════════════════════════════════
    mappeur_norm = {}
    for fname, mask in mappeur_masks.items():
        tex_name = Path(fname).stem.lower()

        # Ignorer si dans liste MAPPEUR_IGNORE
        if tex_name in MAPPEUR_IGNORE:
            print(f"  [IGNORE] {tex_name} (remplacé par pipeline)")
            continue

        # Normalisation 8-bit vs 16-bit
        max_val = np.max(mask)
        if max_val <= 255:
            # 8-bit
            mappeur_norm[tex_name] = mask.astype(np.float32) / 255.0
        else:
            # 16-bit
            mappeur_norm[tex_name] = mask.astype(np.float32) / 65535.0

    # ═══════════════════════════════════════════════════════════════════
    # 3. FUSION SÉLECTIVE : Urbain mappeur + Nature pipeline
    # ═══════════════════════════════════════════════════════════════════
    all_textures = set(mappeur_norm.keys()) | set(v2_renamed.keys())

    juxtaposed = {}

    def is_texture_urbaine(tex_name: str) -> bool:
        """Vérifie si texture est urbaine (à garder du mappeur)"""
        for pattern in TEXTURES_URBAINES_MAPPEUR:
            if pattern in tex_name:
                return True
        return False

    for tex_name in all_textures:
        has_mappeur = tex_name in mappeur_norm
        has_pipeline = tex_name in v2_renamed
        is_urbain = is_texture_urbaine(tex_name)

        if has_mappeur and is_urbain:
            # CAS 1 : Texture URBAINE mappeur → garder dans zone gardée
            if has_pipeline:
                # Si pipeline a aussi cette texture, l'utiliser en zone pipeline
                print(f"  [URBAIN] {tex_name} (mappeur zone gardée, pipeline ailleurs)")
                juxtaposed[tex_name] = (
                    mappeur_norm[tex_name] * garder +
                    v2_renamed[tex_name] * pipeline
                )
            else:
                # Mappeur uniquement
                print(f"  [URBAIN] {tex_name} (mappeur uniquement)")
                juxtaposed[tex_name] = mappeur_norm[tex_name] * garder

        elif has_pipeline:
            # CAS 2 : Texture NATURELLE ou pipeline seul → utiliser pipeline partout
            if has_mappeur and not is_urbain:
                print(f"  [NATURE] {tex_name} (mappeur REMPLACÉ par pipeline)")
            else:
                print(f"  [PIPELINE] {tex_name} (pipeline ajouté)")
            juxtaposed[tex_name] = v2_renamed[tex_name]

        elif has_mappeur and not is_urbain:
            # CAS 3 : Texture NATURELLE mappeur SANS pipeline → ignorer
            print(f"  [IGNORE] {tex_name} (texture naturelle mappeur sans pipeline)")
            # Ne pas ajouter au résultat

    return juxtaposed


# ══════════════════════════════════════════════════════════════════════════════
# ÉTAPE 5 — NETTOYAGE QTRE + EXPORT
# ══════════════════════════════════════════════════════════════════════════════

def redefine_and_export(
    juxtaposed_masks: dict,
    output_dir: str,
    cellsize: float = 4.0,
    presence_threshold: float = 0.05
) -> dict:
    """
    Nettoie et exporte les masks finaux avec validation QTRE.

    Pipeline :
    1. Seuil 5% — éliminer valeurs insignifiantes
    2. Normalisation somme <= 1.0 par pixel
    3. Analyse QTRE par blocs 32m
    4. Export PNG 16-bit — 1 fichier par texture
    5. Export heatmap QTRE (vert/orange/rouge)

    Args:
        juxtaposed_masks: {nom_texture: float32 0-1}
        output_dir: Chemin dossier export
        cellsize: Taille cellule (m) pour calcul blocs QTRE
        presence_threshold: Seuil présence texture (0.05 = 5%)

    Returns:
        {
            'ok_pct': float,
            'limit_pct': float,
            'critical_pct': float,
            'n_masks': int,
            'exported': list,
            'qtre_heatmap': np.ndarray,
            'verdict': str
        }
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── 1. Seuil présence ──
    cleaned = {}
    for tex_name, mask in juxtaposed_masks.items():
        mask_clean = np.where(mask < presence_threshold, 0.0, mask)
        if np.any(mask_clean > 0):
            cleaned[tex_name] = mask_clean

    if not cleaned:
        print("[WARNING] Aucun mask après seuillage")
        return {
            'ok_pct': 100.0,
            'limit_pct': 0.0,
            'critical_pct': 0.0,
            'n_masks': 0,
            'exported': [],
            'qtre_heatmap': np.zeros((1, 1, 3), dtype=np.uint8),
            'verdict': 'VIDE'
        }

    # ── 2. Normalisation somme <= 1.0 ──
    total = np.zeros(list(cleaned.values())[0].shape, dtype=np.float32)
    for mask in cleaned.values():
        total += mask

    overflow = total > 1.0
    overflow_count = int(np.sum(overflow))

    if overflow_count > 0:
        print(f"  [NORM] Overflow : {overflow_count:,} pixels → normalisation")
        for key in cleaned:
            cleaned[key] = np.where(
                overflow,
                cleaned[key] / (total + 1e-6),
                cleaned[key]
            )

    # ── 3. QTRE analyse blocs 32m ──
    bloc_px = max(1, int(32.0 / cellsize))
    shape = list(cleaned.values())[0].shape
    h_blocs = shape[0] // bloc_px
    w_blocs = shape[1] // bloc_px

    qtre_map = np.zeros((h_blocs, w_blocs), dtype=np.uint8)
    critical = 0
    limit = 0
    ok = 0

    for y in range(h_blocs):
        for x in range(w_blocs):
            count = 0
            for mask in cleaned.values():
                bloc = mask[
                    y * bloc_px:(y + 1) * bloc_px,
                    x * bloc_px:(x + 1) * bloc_px
                ]
                if np.mean(bloc) > presence_threshold:
                    count += 1

            qtre_map[y, x] = count

            if count >= 6:
                critical += 1
            elif count >= 4:
                limit += 1
            else:
                ok += 1

    total_blocs = h_blocs * w_blocs

    # ── 4. Export PNG 16-bit ──
    exported = []
    for tex_name, mask in cleaned.items():
        mask_uint16 = (mask * 65535).astype(np.uint16)
        out_path = output_path / f"{tex_name}.png"
        cv2.imwrite(str(out_path), mask_uint16)
        exported.append(str(out_path))

    print(f"  [EXPORT] {len(exported)} masks → {output_dir}")

    # ── 5. Export heatmap QTRE ──
    qtre_heatmap = np.zeros((*qtre_map.shape, 3), dtype=np.uint8)
    qtre_heatmap[qtre_map <= 3] = [0, 200, 0]      # Vert OK
    qtre_heatmap[qtre_map == 4] = [255, 165, 0]    # Orange limite
    qtre_heatmap[qtre_map == 5] = [255, 100, 0]    # Orange foncé
    qtre_heatmap[qtre_map >= 6] = [255, 0, 0]      # Rouge critique

    cv2.imwrite(
        str(output_path / "qtre_heatmap.png"),
        cv2.cvtColor(qtre_heatmap, cv2.COLOR_RGB2BGR)
    )

    # Verdict
    critical_pct = critical / total_blocs * 100 if total_blocs > 0 else 0
    verdict = "OK" if critical_pct < 1.0 else "ATTENTION"

    return {
        'ok_pct': ok / total_blocs * 100 if total_blocs > 0 else 0,
        'limit_pct': limit / total_blocs * 100 if total_blocs > 0 else 0,
        'critical_pct': critical_pct,
        'n_masks': len(cleaned),
        'exported': exported,
        'qtre_heatmap': qtre_heatmap,
        'verdict': verdict
    }
