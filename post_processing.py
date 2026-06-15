# -*- coding: utf-8 -*-
"""
Post-Processing — Fusion masks pipeline_v2 + mappeur
====================================================

PHASE 1 : Fusion automatique selon catégories de textures
PHASE 2 : Ajout polygones manuels (futur)

Usage:
    from post_processing import generate_urban_zone_mask, merge_masks, apply_qtre_and_export
"""

import numpy as np
from pathlib import Path
import cv2
from scipy.ndimage import binary_dilation


# ══════════════════════════════════════════════════════════════════════════════
# CATÉGORIES DE TEXTURES
# ══════════════════════════════════════════════════════════════════════════════

TEXTURE_CATEGORIES = {
    "sol_naturel": "Priorité pipeline_v2",
    "commune": "Max(pipeline_v2, mappeur)",
    "mappeur": "Priorité mappeur",
    "foret_custom": "Addition intelligente",
    "ignorer": "Ignoré"
}

# Textures terrain pipeline_v2 (sol naturel par défaut)
TEXTURES_TERRAIN_V2 = [
    "seabed", "coastal_pebbles", "coastal_grass",
    "rock_walls", "debris_rock", "dirt_erosion",
    "mud_river", "forest_floor", "mountain_grass_high",
    "mountain_grass_low", "grass_high", "grass_mid", "grass_low"
]

# Textures communes (présentes dans pipeline_v2 ET mappeur)
TEXTURES_COMMUNES = [
    "pebbles", "grass_01", "grass_02", "grass_03"
]


# ══════════════════════════════════════════════════════════════════════════════
# FONCTION 1 : GÉNÉRATION ZONE URBAINE
# ══════════════════════════════════════════════════════════════════════════════

def generate_urban_zone_mask(
    urbain_masks: dict,     # {nom: array uint16}
    shape: tuple,           # (H, W)
    radius_m: float = 0.0,  # dilatation en mètres (0 = pas de dilatation)
    cellsize: float = 4.0,
    threshold: float = 0.05
) -> np.ndarray:
    """
    Génère un mask binaire de zone urbaine
    depuis l'union de tous les masks catégorie Urbain/Mappeur.

    Args:
        urbain_masks: Dict {nom_fichier: array uint16}
        shape: (height, width) de la heightmap
        radius_m: Rayon de dilatation en mètres (0 = pas de dilatation)
        cellsize: Résolution en m/px
        threshold: Seuil de présence (0.05 = 5%)

    Returns:
        Mask binaire (bool) de la zone urbaine

    Notes:
        radius_m > 0 → dilate légèrement la zone urbaine
        pour éviter que l'herbe apparaisse en bordure de route.
    """
    zone = np.zeros(shape, dtype=bool)

    for name, mask in urbain_masks.items():
        mask_norm = mask.astype(np.float32) / 65535.0
        zone |= (mask_norm > threshold)

    # Dilatation optionnelle
    if radius_m > 0:
        radius_px = max(1, int(radius_m / cellsize))
        struct = np.ones((radius_px * 2 + 1,) * 2, dtype=bool)
        zone = binary_dilation(zone, structure=struct)

    return zone


# ══════════════════════════════════════════════════════════════════════════════
# FONCTION 2 : FUSION MASKS
# ══════════════════════════════════════════════════════════════════════════════

def merge_masks(
    v2_masks: dict,          # {nom_texture: array float32 0-1}
    mappeur_masks: dict,     # {nom_fichier: array uint16}
    categories: dict,        # {nom_fichier: categorie}
    urban_zone: np.ndarray,  # mask binaire zone urbaine (non utilisé en Phase 1)
    cellsize: float = 4.0,
    threshold: float = 0.05
) -> dict:
    """
    Fusionne masks pipeline_v2 et masks mappeur selon catégories.

    LOGIQUE PHASE 1 :
    - sol_naturel  : Pipeline_v2, SAUF zone urbaine → 0 (pas d'herbe en ville)
    - mappeur      : Mappeur uniquement (routes, bâtiments)
    - commune      : Max(pipeline_v2, mappeur)
    - foret_custom : Addition clampée
    - ignorer      : Masque vide (0)

    Args:
        v2_masks: Masks pipeline_v2 {nom_texture: array float32 0-1}
        mappeur_masks: Masks mappeur {nom_fichier: array uint16}
        categories: {nom_fichier: categorie} parmi TEXTURE_CATEGORIES
        urban_zone: Mask binaire zone urbaine (efface sol_naturel)
        cellsize: Résolution m/px
        threshold: Seuil présence texture

    Returns:
        Dict {nom_texture: array float32 0-1} fusionné
    """
    final_masks = {}
    shape = list(v2_masks.values())[0].shape

    # Normaliser masks mappeur en float32 0-1
    mappeur_norm = {}
    for fname, mask in mappeur_masks.items():
        mappeur_norm[fname] = mask.astype(np.float32) / 65535.0

    # ── Traiter chaque texture pipeline_v2 ──
    for tex_name, v2_mask in v2_masks.items():

        # Chercher correspondance dans mappeur
        mappeur_match = None
        mappeur_cat = None

        for fname, cat in categories.items():
            # Correspondance par nom de texture dans nom de fichier
            if tex_name.lower() in fname.lower() or fname.lower() in tex_name.lower():
                if cat != "ignorer":
                    mappeur_match = mappeur_norm.get(fname)
                    mappeur_cat = cat
                    break

        # Fusion selon catégorie
        if mappeur_match is not None:
            if mappeur_cat == "sol_naturel":
                # Priorité pipeline_v2
                # SAUF zone urbaine → 0 (pas d'herbe en ville)
                result = v2_mask.copy()
                result[urban_zone] = 0.0
                final_masks[tex_name] = result

            elif mappeur_cat == "mappeur":
                # Priorité mappeur uniquement
                final_masks[tex_name] = mappeur_match

            elif mappeur_cat == "commune":
                # Max des deux
                final_masks[tex_name] = np.maximum(v2_mask, mappeur_match)

            elif mappeur_cat == "foret_custom":
                # Addition clampée
                final_masks[tex_name] = np.clip(v2_mask + mappeur_match, 0, 1)

            else:  # ignorer
                # Masque vide
                final_masks[tex_name] = np.zeros(shape, np.float32)
        else:
            # Pas de correspondance mappeur
            # Si sol naturel → effacer dans zone urbaine
            if tex_name in TEXTURES_TERRAIN_V2:
                result = v2_mask.copy()
                result[urban_zone] = 0.0
                final_masks[tex_name] = result
            else:
                final_masks[tex_name] = v2_mask

    # ── Textures mappeur uniquement (pas dans pipeline_v2) ──
    # Ajouter SEULEMENT les masks catégorie "mappeur" (routes, bâtiments)
    # Les autres catégories (sol_naturel, commune, foret_custom) modifient
    # uniquement les textures existantes, elles ne créent PAS de nouvelles textures
    for fname, cat in categories.items():
        if cat == "ignorer":
            continue

        # SEULEMENT catégorie "mappeur" peut ajouter de nouvelles textures
        if cat != "mappeur":
            continue

        # Vérifier si déjà traité
        already_processed = any(
            fname.lower() in tex.lower() or tex.lower() in fname.lower()
            for tex in final_masks.keys()
        )
        if not already_processed:
            tex_name = Path(fname).stem
            final_masks[tex_name] = mappeur_norm.get(fname,
                                     np.zeros(shape, np.float32))

    # ── Normalisation somme <= 1.0 par pixel ──
    total = np.zeros(shape, dtype=np.float32)
    for mask in final_masks.values():
        total += mask

    overflow = total > 1.0
    if np.any(overflow):
        for key in final_masks:
            final_masks[key] = np.where(
                overflow,
                final_masks[key] / (total + 1e-6),
                final_masks[key]
            )

    return final_masks


# ══════════════════════════════════════════════════════════════════════════════
# FONCTION 3 : QTRE ET EXPORT
# ══════════════════════════════════════════════════════════════════════════════

def apply_qtre_and_export(
    final_masks: dict,      # {nom_texture: array float32 0-1}
    output_dir: str,
    cellsize: float = 4.0,
    presence_threshold: float = 0.05
) -> dict:
    """
    Applique seuil 5%, vérifie QTRE et exporte PNG 16 bits.

    Args:
        final_masks: {nom_texture: array float32 0-1}
        output_dir: Dossier de sortie
        cellsize: Résolution m/px
        presence_threshold: Seuil émergence texture (0.05 = 5%)

    Returns:
        Dict rapport QTRE:
        {
            "ok_pct": float,
            "limit_pct": float,
            "critical_pct": float,
            "exported": list[str],
            "verdict": str
        }
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exported = []
    masks_uint16 = {}

    # ── Export PNG 16-bit ──
    for tex_name, mask in final_masks.items():
        # Seuil 5% — éliminer valeurs insignifiantes
        mask_clean = np.where(mask < presence_threshold, 0.0, mask)

        # Convertir en uint16
        mask_uint16 = (mask_clean * 65535).astype(np.uint16)
        masks_uint16[tex_name] = mask_uint16

        # Exporter PNG 16 bits
        out_path = output_dir / f"{tex_name}.png"
        cv2.imwrite(str(out_path), mask_uint16)
        exported.append(str(out_path))

    # ── Analyse QTRE (vectorisé) ──
    bloc_px = max(1, int(32 / cellsize))
    shape = list(masks_uint16.values())[0].shape
    h_blocs = shape[0] // bloc_px
    w_blocs = shape[1] // bloc_px

    critical = 0
    limit = 0
    ok = 0

    for y in range(h_blocs):
        for x in range(w_blocs):
            count = 0
            for mask in masks_uint16.values():
                bloc = mask[y*bloc_px:(y+1)*bloc_px,
                            x*bloc_px:(x+1)*bloc_px]
                if np.mean(bloc) / 65535.0 > presence_threshold:
                    count += 1

            if count >= 6:
                critical += 1
            elif count >= 4:
                limit += 1
            else:
                ok += 1

    total_blocs = h_blocs * w_blocs
    qtre_report = {
        "ok_pct": ok / total_blocs * 100 if total_blocs > 0 else 0,
        "limit_pct": limit / total_blocs * 100 if total_blocs > 0 else 0,
        "critical_pct": critical / total_blocs * 100 if total_blocs > 0 else 0,
        "exported": exported,
        "verdict": "OK" if critical / total_blocs < 0.01 else "ATTENTION"
    }

    return qtre_report


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 : POLYGONES MANUELS
# ══════════════════════════════════════════════════════════════════════════════

def points_to_mask(points, shape) -> np.ndarray:
    """
    Convertit une liste de points [[x,y],...]
    en mask binaire numpy via cv2.fillPoly.

    Args:
        points: Liste de points [[x,y], [x,y], ...]
        shape: (height, width) du mask

    Returns:
        Mask binaire (bool)
    """
    mask = np.zeros(shape, dtype=np.uint8)
    pts = np.array(points, dtype=np.int32)
    cv2.fillPoly(mask, [pts], 1)
    return mask.astype(bool)


def apply_manual_polygons(
    urban_zone: np.ndarray,   # mask binaire zone urbaine
    polygons: list,           # liste depuis project.json
    shape: tuple,             # (H, W) heightmap
    display_scale: float = 1.0  # ratio affichage/réel
) -> np.ndarray:
    """
    Applique les polygones manuels sur le mask zone urbaine.

    PROTÉGER → urban_zone = False (pipeline_v2 garde la main)
    EXCLURE  → urban_zone = True  (pipeline_v2 mis à 0)

    Args:
        urban_zone: Mask binaire zone urbaine initial
        polygons: Liste de polygones depuis project.json
        shape: (height, width) heightmap
        display_scale: Ratio entre taille affichage canvas et taille réelle heightmap

    Returns:
        Mask zone urbaine modifié avec polygones manuels
    """
    result = urban_zone.copy()

    for poly in polygons:
        if not poly.get('active', True):
            continue

        # Rescaler les points vers coordonnées réelles
        points_real = [
            [int(p[0] / display_scale),
             int(p[1] / display_scale)]
            for p in poly['points']
        ]

        if len(points_real) < 3:
            continue

        poly_mask = points_to_mask(points_real, shape)

        if poly['mode'] == 'proteger':
            # Zone protégée → pipeline_v2 garde la main
            result[poly_mask] = False

        elif poly['mode'] == 'exclure':
            # Zone exclue → pipeline_v2 mis à 0
            result[poly_mask] = True

    return result


def save_polygons(polygons: list, project_dir: str):
    """Sauvegarder polygones dans project.json"""
    import json
    project_file = Path(project_dir) / "project.json"

    if project_file.exists():
        with open(project_file, 'r', encoding='utf-8') as f:
            project = json.load(f)
    else:
        project = {}

    project['manual_polygons'] = polygons

    with open(project_file, 'w', encoding='utf-8') as f:
        json.dump(project, f, indent=2, ensure_ascii=False)


def load_polygons(project_dir: str) -> list:
    """Charger polygones depuis project.json"""
    import json
    project_file = Path(project_dir) / "project.json"

    if not project_file.exists():
        return []

    with open(project_file, 'r', encoding='utf-8') as f:
        project = json.load(f)

    return project.get('manual_polygons', [])


# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("post_processing.py — Module de fusion masks")
    print("=" * 60)
    print("\nFonctions disponibles :")
    print("  - generate_urban_zone_mask()")
    print("  - merge_masks()")
    print("  - apply_qtre_and_export()")
    print("  - points_to_mask()")
    print("  - apply_manual_polygons()")
    print("  - save_polygons() / load_polygons()")
    print("\nCatégories de textures :")
    for cat, desc in TEXTURE_CATEGORIES.items():
        print(f"  {cat:15s} : {desc}")
