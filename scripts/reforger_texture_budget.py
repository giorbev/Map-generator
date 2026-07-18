"""
Reforger/Enfusion terrain texture budget system.

Converts morphological scores into block-constrained texture assignments
compatible with the Enfusion Surface Map (8-bit, max 4-5 textures per block,
weights summing to 1.0).

Texture roles are open-ended: add as many as needed globally.
The per-block budget (max_textures=4) remains the only hard engine constraint.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter, binary_dilation, binary_erosion, zoom


# ── Utilitaire mémoire ───────────────────────────────────────────────────────

def _edt_m(bool_mask: np.ndarray, cell: float, stride: int = 4) -> np.ndarray:
    """EDT en mètres calculée à résolution réduite (évite l'allocation float64 à pleine résolution).

    Pour chaque pixel, retourne la distance en mètres au pixel le plus proche
    où bool_mask == False (comportement identique à distance_transform_edt).
    stride=4 -> divise la consommation mémoire par 16.
    """
    small    = bool_mask[::stride, ::stride]
    dist_s   = distance_transform_edt(small).astype(np.float32) * (cell * stride)
    dist_up  = zoom(dist_s, stride, order=1)
    h, w     = bool_mask.shape
    return dist_up[:h, :w]


# ── Parseur .terr Enfusion ────────────────────────────────────────────────────

def find_terr_files(project_path: str) -> List[Path]:
    """Retourne tous les .terr trouvés dans le dossier projet."""
    root = Path(project_path)
    return sorted(root.rglob("*.terr"))


def parse_terr_materials(terr_path: str) -> List[str]:
    """
    Extrait la liste ordonnée des matériaux depuis un fichier .terr binaire.
    L'ordre de lecture = index matériau dans le moteur.
    Retourne des noms avec extension .emat (ex: "Grass_01.emat").
    """
    with open(terr_path, "rb") as f:
        data = f.read()

    seen = set()
    materials: List[str] = []
    for m in re.finditer(rb"[\w.-]+\.emat", data):
        name = m.group().decode("ascii", errors="ignore")
        if name not in seen:
            seen.add(name)
            materials.append(name)

    return materials


# ── Catalogue complet des textures vanilla Reforger ──────────────────────────

VANILLA_TEXTURES: List[str] = [
    "Grass_01.emat",
    "Grass_02.emat",
    "Grass_03.emat",
    "Grass_03_coastal.emat",
    "BeachGrass_01.emat",
    "Dirt_01.emat",
    "Dirt_02.emat",
    "Dirt_03.emat",
    "Rock_01.emat",
    "Pebbles_01.emat",
    "Pebbles_02.emat",
    "MountainGrass_01.emat",
    "MountainGrass_02.emat",
    "MountainGrass_03.emat",
    "Heather_01.emat",
    "ForestClearing_Deciduous_01.emat",
    "Debris_Rock.emat",
    "SeaBed_01.emat",
    "CUSTOM_SNOW",
    "CUSTOM_SAND",
]

# ── Textures suggérées par rôle (toujours depuis VANILLA_TEXTURES) ────────────

ROLE_TEXTURE_CATALOG: Dict[str, List[str]] = {
    "fond_marin": [
        "SeaBed_01.emat",
        "Dirt_01.emat",
    ],
    "sable": [
        "CUSTOM_SAND",
        "Grass_03_coastal.emat",
        "Pebbles_01.emat",
        "Dirt_01.emat",
    ],
    "cotier": [
        "Grass_03_coastal.emat",
        "BeachGrass_01.emat",
        "Pebbles_01.emat",
        "Pebbles_02.emat",
        "Dirt_01.emat",
        "Grass_01.emat",
        "Grass_02.emat",
    ],
    "galets": [
        "Pebbles_01.emat",
        "Pebbles_02.emat",
        "Dirt_01.emat",
        "Dirt_02.emat",
        "Rock_01.emat",
    ],
    "prairie": [
        "Grass_02.emat",
        "Grass_01.emat",
        "Grass_03.emat",
        "Heather_01.emat",
        "MountainGrass_01.emat",
        "MountainGrass_02.emat",
        "MountainGrass_03.emat",
    ],
    "herbe_dense": [
        "Grass_03.emat",
        "Grass_01.emat",
        "Grass_02.emat",
        "MountainGrass_01.emat",
    ],
    "lande": [
        "MountainGrass_01.emat",
        "MountainGrass_02.emat",
        "MountainGrass_03.emat",
        "Grass_03.emat",
    ],
    "heather": [
        "Heather_01.emat",
        "MountainGrass_01.emat",
        "Grass_03.emat",
    ],
    "feuillus": [
        "ForestClearing_Deciduous_01.emat",
        "Grass_01.emat",
        "Grass_02.emat",
        "Heather_01.emat",
    ],
    "coniferes": [
        "ForestClearing_Deciduous_01.emat",
        "Grass_01.emat",
    ],
    "lisiere": [
        "ForestClearing_Deciduous_01.emat",
        "Grass_02.emat",
        "Heather_01.emat",
    ],
    "debris_rock": [
        "Debris_Rock.emat",
        "Pebbles_02.emat",
        "Rock_01.emat",
        "Dirt_03.emat",
    ],
    "erosion": [
        "Dirt_03.emat",
        "Dirt_02.emat",
        "Dirt_01.emat",
        "Pebbles_01.emat",
    ],
    "débris": [
        "Pebbles_02.emat",
        "Pebbles_01.emat",
        "Rock_01.emat",
        "Dirt_03.emat",
    ],
    "roche": [
        "Rock_01.emat",
        "Pebbles_02.emat",
        "Dirt_03.emat",
    ],
    "neige": [
        "CUSTOM_SNOW",
        "MountainGrass_03.emat",
        "MountainGrass_01.emat",
        "Heather_01.emat",
        "ForestClearing_Deciduous_01.emat",
    ],
}

# ── Défauts par biome (= sélection initiale dans les dropdowns) ───────────────

BIOME_TEXTURES: Dict[str, Dict[str, str]] = {
    # Tempéré : Europe de l'ouest, îles atlantiques (ex: Bornholm, ZBK)
    "Tempéré": {
        "fond_marin":   "SeaBed_01.emat",
        "sable":        "CUSTOM_SAND",
        "cotier":       "Grass_03_coastal.emat",
        "galets":       "Pebbles_01.emat",
        "prairie":      "Grass_02.emat",
        "herbe_dense":  "Grass_03.emat",
        "lande":        "MountainGrass_01.emat",
        "heather":      "Heather_01.emat",
        "feuillus":     "ForestClearing_Deciduous_01.emat",
        "coniferes":    "ForestClearing_Deciduous_01.emat",
        "lisiere":      "ForestClearing_Deciduous_01.emat",
        "terre":        "Dirt_01.emat",
        "erosion":      "Dirt_03.emat",
        "debris_rock":  "Debris_Rock.emat",
        "débris":       "Pebbles_02.emat",
        "roche":        "Rock_01.emat",
        "neige":        "CUSTOM_SNOW",
    },
    # Aride : Méditerranée, steppe
    "Aride": {
        "fond_marin":   "SeaBed_01.emat",
        "sable":        "CUSTOM_SAND",
        "cotier":       "BeachGrass_01.emat",
        "galets":       "Pebbles_02.emat",
        "prairie":      "Grass_03.emat",
        "herbe_dense":  "Grass_01.emat",
        "lande":        "MountainGrass_03.emat",
        "heather":      "Heather_01.emat",
        "feuillus":     "ForestClearing_Deciduous_01.emat",
        "coniferes":    "ForestClearing_Deciduous_01.emat",
        "lisiere":      "ForestClearing_Deciduous_01.emat",
        "terre":        "Dirt_02.emat",
        "erosion":      "Dirt_01.emat",
        "debris_rock":  "Debris_Rock.emat",
        "débris":       "Dirt_03.emat",
        "roche":        "Rock_01.emat",
        "neige":        "MountainGrass_03.emat",
    },
    # Continental : Europe centrale, grandes plaines
    "Continental": {
        "fond_marin":   "SeaBed_01.emat",
        "sable":        "CUSTOM_SAND",
        "cotier":       "Grass_03_coastal.emat",
        "galets":       "Pebbles_01.emat",
        "prairie":      "Grass_01.emat",
        "herbe_dense":  "Grass_03.emat",
        "lande":        "MountainGrass_01.emat",
        "heather":      "Heather_01.emat",
        "feuillus":     "ForestClearing_Deciduous_01.emat",
        "coniferes":    "ForestClearing_Deciduous_01.emat",
        "lisiere":      "ForestClearing_Deciduous_01.emat",
        "terre":        "Dirt_01.emat",
        "erosion":      "Dirt_03.emat",
        "debris_rock":  "Debris_Rock.emat",
        "débris":       "Pebbles_02.emat",
        "roche":        "Rock_01.emat",
        "neige":        "CUSTOM_SNOW",
    },
    # Alpin : hautes montagnes — éboulis rocheux dominant
    "Alpin": {
        "fond_marin":   "SeaBed_01.emat",
        "sable":        "CUSTOM_SAND",
        "cotier":       "Grass_03_coastal.emat",
        "galets":       "Pebbles_02.emat",
        "prairie":      "MountainGrass_01.emat",
        "herbe_dense":  "MountainGrass_02.emat",
        "lande":        "MountainGrass_03.emat",
        "heather":      "Heather_01.emat",
        "feuillus":     "ForestClearing_Deciduous_01.emat",
        "coniferes":    "ForestClearing_Deciduous_01.emat",
        "lisiere":      "ForestClearing_Deciduous_01.emat",
        "terre":        "Dirt_03.emat",
        "erosion":      "Dirt_03.emat",
        "debris_rock":  "Debris_Rock.emat",
        "débris":       "Rock_01.emat",
        "roche":        "Rock_01.emat",
        "neige":        "CUSTOM_SNOW",
    },
    # Subarctique : Scandinavie, toundra — heather dominant
    "Subarctique": {
        "fond_marin":   "SeaBed_01.emat",
        "sable":        "CUSTOM_SAND",
        "cotier":       "Grass_03_coastal.emat",
        "galets":       "Pebbles_01.emat",
        "prairie":      "Heather_01.emat",
        "herbe_dense":  "Grass_03.emat",
        "lande":        "MountainGrass_03.emat",
        "heather":      "Heather_01.emat",
        "feuillus":     "ForestClearing_Deciduous_01.emat",
        "coniferes":    "ForestClearing_Deciduous_01.emat",
        "lisiere":      "ForestClearing_Deciduous_01.emat",
        "terre":        "Dirt_02.emat",
        "erosion":      "Dirt_02.emat",
        "debris_rock":  "Debris_Rock.emat",
        "débris":       "Pebbles_02.emat",
        "roche":        "Rock_01.emat",
        "neige":        "CUSTOM_SNOW",
    },
    # Tropical : jungle, savane humide
    "Tropical": {
        "fond_marin":   "SeaBed_01.emat",
        "sable":        "CUSTOM_SAND",
        "cotier":       "BeachGrass_01.emat",
        "galets":       "Pebbles_01.emat",
        "prairie":      "Grass_01.emat",
        "herbe_dense":  "Grass_03.emat",
        "lande":        "MountainGrass_02.emat",
        "heather":      "Heather_01.emat",
        "feuillus":     "ForestClearing_Deciduous_01.emat",
        "coniferes":    "ForestClearing_Deciduous_01.emat",
        "lisiere":      "ForestClearing_Deciduous_01.emat",
        "terre":        "Dirt_01.emat",
        "erosion":      "Dirt_01.emat",
        "debris_rock":  "Debris_Rock.emat",
        "débris":       "Dirt_03.emat",
        "roche":        "Rock_01.emat",
        "neige":        "ForestClearing_Deciduous_01.emat",
    },
}

# ── Altitude minimale pour la neige par biome (fraction 0-1 normalisée) ───────
# En dessous de ce seuil l'altitude normalisée, le score neige est forcé à 0.
# Biomes arctiques/alpins : seuil bas -> neige dès les mi-altitudes.
# Biomes tempérés/arides  : seuil haut -> neige uniquement aux sommets.

BIOME_SNOWLINE: Dict[str, float] = {
    "Tempéré":     0.80,
    "Aride":       0.92,
    "Continental": 0.75,
    "Alpin":       0.30,
    "Subarctique": 0.10,
    "Tropical":    0.95,
}

# ── Couleurs albédo réelles par rôle (moyenne BCR raw depuis captures Workbench)
# Sources : captures directes des textures BCR sans éclairage (PBR albedo brut).
# fond_marin : seabed01.jpg   sable : aerial_beach_01_BCR.png (proxy CUSTOM_SAND)
# cotier : grass03.jpg        galets : pebbles01.gif
# prairie : grass_lawn.jpg    lande : MountainGrass_01.jpg
# débris : pebbles02.jpg      sol : dirt02.jpg
# roche : ground_granit.jpg   neige : estimation (BCR snow trop sombre via AO)

TEXTURE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "fond_marin":    ( 71,  64,  53),   # SeaBed_01 detail BCR
    "cotier":        ( 73,  72,  52),   # Grass_03_coastal detail BCR
    "galets":        ( 92,  89,  81),   # Pebbles_01 detail BCR
    "prairie":       ( 58,  62,  39),   # Grass_02 (GrassLawn) detail BCR
    "herbe_dense":   ( 68,  78,  42),   # Grass_03 — herbe intermédiaire mi-altitude
    "lande":         ( 60,  74,  43),   # MountainGrass_01/02/03 haute altitude
    "heather":       ( 90,  72,  65),   # Heather_01 — bruyère décorative (touffe)
    "feuillus":      ( 93,  80,  65),   # ForestDeciduous_01_Base detail BCR
    "coniferes":   ( 35,  50,  25),   # ForestConiferous / ForestPine
    "lisiere":  ( 75,  90,  55),   # ForestClearing lisière
    "debris_rock":   (105,  90,  72),   # Debris_Rock (éboulis / fragments rocheux)
    "erosion":       ( 88,  78,  62),   # Dirt_03 (ravines / creux d'érosion)
    "roche":         ( 77,  76,  75),   # Rock_01
    "neige":         (240, 240, 245),   # snow
    # hors pipeline auto — pour SatMap et affichage uniquement
    "sable":         ( 77,  73,  52),
    "terre":         ( 98,  84,  63),   # Dirt_01/02 — sol nu générique (hors pipeline auto)
    "débris":        ( 87,  81,  76),
    "champs1":       ( 90,  72,  50),
    "champs2":       (125, 105,  72),
    "champs3":       ( 78, 100,  58),
    "urbain":        ( 90,  90,  90),
}

# Rôles du pipeline auto-texture — compute_texture_scores, apply_block_budget, aperçu
TEXTURE_ORDER: List[str] = [
    "fond_marin", "cotier", "galets",
    "prairie", "herbe_dense", "lande", "heather",
    "feuillus", "coniferes", "lisiere",
    "debris_rock", "erosion", "roche",
]

# Superset pour le mapping SatMap K-means uniquement (pas de signal terrain pour les variantes)
SATMAP_TEXTURE_ORDER: List[str] = [
    "fond_marin", "sable", "cotier", "galets",
    "prairie", "herbe_dense", "lande", "heather",
    "feuillus", "coniferes", "lisiere",
    "champs1", "champs2", "champs3",
    "terre", "debris_rock", "erosion", "débris", "roche", "neige",
]

TEXTURE_LABELS: Dict[str, str] = {
    "fond_marin":   "Fond marin",
    "sable":        "Sable / Plage",
    "cotier":       "Côtier",
    "galets":       "Galets (plage)",
    "prairie":      "Prairie / Herbe basse",
    "herbe_dense":  "Herbe intermédiaire (Grass_03)",
    "lande":        "Lande / MountainGrass haute altitude",
    "heather":      "Bruyère décorative (Heather_01)",
    "feuillus":     "Forêt / Sous-bois",
    "coniferes":  "Forêt dense",
    "lisiere": "Forêt clairsemée",
    "debris_rock":  "Débris rocheux / Éboulis",
    "terre":        "Sol nu / Terre (Dirt_01/02)",
    "champs1":      "Champs (brun / sol nu)",
    "champs2":      "Champs (ocre / chaume)",
    "champs3":      "Champs (vert / cultures)",
    "erosion":      "Érosion / Dirt_03",
    "débris":       "Débris / Éboulis",
    "roche":        "Roche nue",
    "urbain":       "Route / Urbain (béton, asphalte, pavés)",
    "neige":        "Neige / Haute altitude",
}


def get_role_options(biome_default: str) -> List[str]:
    """
    Retourne la liste ordonnée pour le selectbox d'un rôle.
    Utilise toujours VANILLA_TEXTURES comme catalogue — le .terr du mappeur
    n'influence pas les choix (il peut contenir des matériaux de test).
    Ordre : défaut biome -> reste du catalogue -> option personnalisée.
    """
    catalog = list(VANILLA_TEXTURES)
    if biome_default and biome_default in catalog:
        catalog.remove(biome_default)
    if biome_default:
        catalog.insert(0, biome_default)
    catalog.append("✏️ Personnalisé…")
    return catalog


# ── Lecteur TMAT (.ttile Enfusion) ───────────────────────────────────────────

import struct as _struct

# Correspondance stem .emat -> rôle visuel. Ordre important : les entrées plus
# spécifiques (ex: "Grass_03_coastal") doivent précéder les plus génériques ("Grass").
_MAT_STEM_TO_ROLE: Dict[str, str] = {
    # Eau / fond marin
    "SeaBed":             "fond_marin",
    "SulfurStream":       "fond_marin",
    # Côtier / plage
    "CUSTOM_SAND":        "sable",
    "BeachGrass":         "cotier",
    "Grass_03_coastal":   "cotier",
    "Pebbles":            "galets",
    # Herbe / végétation
    "Grass":              "prairie",
    "MountainGrass":      "lande",
    "Heather":            "heather",   # rôle décoratif dédié (pas lande)
    "ForestConiferous":   "coniferes",   # avant le catch-all Forest
    "ForestPine":         "coniferes",   # avant le catch-all Forest
    "ForestClearing":     "lisiere",     # clairière / lisière (was feuillus)
    "Forest":             "feuillus",   # catch-all forêt feuillue
    # Terrain de sport (herbe tondue)
    "ZI_Ground_Sport":    "prairie",
    "Ground_Sport":       "prairie",
    # Champs agricoles
    "ZI_Crop_Field":      "champs1",
    "Crop_Field":         "champs1",
    "Texture_Crop":       "champs2",
    # Érosion / terre — plus spécifique avant le catch-all
    "Dirt_03":            "erosion",     # Dirt_03 = érosion/ravines (Dirt_03.emat)
    "Dirt_01":            "terre",       # Dirt_01/02 = sol nu générique
    "Dirt_02":            "terre",
    "Dirt":               "terre",       # catch-all Dirt -> sol nu (pas érosion)
    # Routes / surfaces dures (cobblestone, asphalte, béton)
    "Cobblestone":        "urbain",
    "Asphalt":            "urbain",
    "Concrete":           "urbain",
    # Roche / débris — Debris_Rock avant le catch-all Debris
    "Debris_Rock":        "debris_rock",
    "Debris":             "débris",
    "Rock":               "roche",
    "ZI_Rock":            "roche",
    # Neige
    "CUSTOM_SNOW":        "neige",
    # ZI générique (catch-all pour textures ZI non listées ci-dessus)
    "ZI_":                "erosion",
}

_MAT_STEM_ORDER = list(_MAT_STEM_TO_ROLE.keys())

# ── Bibliothèque runtime (chargée depuis les JSON au load_project) ────────────
# Remplace _MAT_STEM_TO_ROLE quand set_runtime_library() a été appelé.
_rt_stem_to_role: dict = {}
_rt_stem_order:   list = []

# ── Paramètres écologiques par rôle (chargés depuis material_library_vanilla.json) ──
_ROLE_ECO: Dict[str, dict] = {}

def _load_role_eco() -> Dict[str, dict]:
    """Charge et met en cache les paramètres eco de chaque rôle depuis le JSON vanilla."""
    global _ROLE_ECO
    if _ROLE_ECO:
        return _ROLE_ECO
    try:
        import json as _json
        _lib_path = Path(__file__).parent / "data" / "material_library_vanilla.json"
        with open(_lib_path, encoding="utf-8") as _f:
            _lib = _json.load(_f)
        _ROLE_ECO = {r["id"]: r.get("eco", {}) for r in _lib.get("roles", [])}
    except Exception:
        pass
    return _ROLE_ECO


def set_runtime_library(materials: list, roles: list | None = None) -> None:
    """
    Charge la bibliothèque de matériaux fusionnée (vanilla + custom) dans le
    runtime de ce module. Appelé par app.py à chaque ouverture de projet.

    Args:
        materials : liste de dicts {"stem", "role", "label", "terrain_pipeline"}
                    dans l'ordre de priorité (custom en tête).
        roles     : liste de dicts {"id", "label", "color"} — met à jour
                    TEXTURE_COLORS et TEXTURE_LABELS si fourni.
    """
    global _rt_stem_to_role, _rt_stem_order

    _rt_stem_to_role = {m["stem"]: m["role"] for m in materials}
    _rt_stem_order   = list(_rt_stem_to_role.keys())

    if roles:
        for r in roles:
            rid   = r["id"]
            color = tuple(r["color"])
            if rid not in TEXTURE_COLORS:
                TEXTURE_COLORS[rid]  = color
                TEXTURE_LABELS[rid]  = r.get("label", rid)
                if rid not in TEXTURE_ORDER:
                    TEXTURE_ORDER.append(rid)
            else:
                TEXTURE_COLORS[rid] = color
                TEXTURE_LABELS[rid] = r.get("label", TEXTURE_LABELS.get(rid, rid))


def mat_to_role(mat_name: str) -> str:
    """Maps a .emat filename (with or without extension) to a texture role."""
    stem   = mat_name.replace(".emat", "")
    stem_l = stem.lower()
    table  = _rt_stem_to_role if _rt_stem_order else _MAT_STEM_TO_ROLE
    order  = _rt_stem_order   if _rt_stem_order else _MAT_STEM_ORDER
    for prefix in order:
        pl = prefix.lower()
        if stem_l == pl or stem_l.startswith(pl + "_") or stem_l.startswith(pl + "."):
            return table[prefix]
    return "erosion"


def find_ttile_files(project_path: str) -> List[Path]:
    """Retourne tous les .ttile trouvés récursivement dans project_path."""
    return sorted(Path(project_path).rglob("*.ttile"))


def _iter_tmat_bmats(data: bytes) -> List[Tuple]:
    """
    Parcourt les chunks IFF d'un fichier .ttile et retourne les BMAT du TMAT.
    Retourne liste de (bx_global, by_global, mat_ids_list, qtre_bytes_or_None).
    Compatible TMAT simple (256B) et TMAT large (variable).
    """
    result = []
    dlen = len(data)

    # Trouver le chunk TMAT
    pos = 12
    tmat_doff = tmat_sz = -1
    while pos + 8 <= dlen:
        cid = data[pos:pos+4]
        csz = _struct.unpack_from(">I", data, pos+4)[0]
        if pos + 8 + csz > dlen:
            break
        if cid == b"TMAT":
            tmat_doff = pos + 8
            tmat_sz   = csz
            break
        pos = pos + 8 + csz + (csz % 2)

    if tmat_doff < 0:
        return result

    # Parcourir les BMAT dans le TMAT
    pos = tmat_doff
    end = tmat_doff + tmat_sz
    while pos + 8 <= end:
        cid = data[pos:pos+4]
        csz = _struct.unpack_from(">I", data, pos+4)[0]
        if pos + 8 + csz > dlen:
            break
        if cid == b"BMAT" and csz >= 6:
            bd     = data[pos+8 : pos+8+csz]
            bx     = _struct.unpack_from("<H", bd, 0)[0]
            by     = _struct.unpack_from("<H", bd, 2)[0]
            n_mat  = _struct.unpack_from("<H", bd, 4)[0]
            if n_mat < 1 or csz < 6 + n_mat * 2:
                pos = pos + 8 + csz + (csz % 2)
                continue
            mats   = [_struct.unpack_from("<H", bd, 6 + i*2)[0] for i in range(n_mat)]
            hdr_sz = 6 + n_mat * 2
            qtre   = None
            if csz > hdr_sz + 8 and bd[hdr_sz:hdr_sz+4] == b"QTRE":
                qsz  = _struct.unpack_from(">I", bd, hdr_sz+4)[0]
                qtre = bytes(bd[hdr_sz+8 : hdr_sz+8+qsz])
            result.append((bx, by, mats, qtre))
        pos = pos + 8 + csz + (csz % 2)

    return result


def read_tmat_grid(
    ttile_files: List[Path],
    tiles_x: int,
    tiles_y: int,
    blocks_per_tile_x: int,
    blocks_per_tile_y: int,
) -> Tuple[np.ndarray, Dict[int, int]]:
    """
    Lit tous les .ttile et extrait le matériau dominant par bloc (TMAT).

    La grille est dimensionnée d'après les coordonnées bx/by réellement présentes
    dans les fichiers (pas d'hypothèse sur leur système de coordonnées), avec un
    minimum de tiles_x * tiles_y pour éviter les grilles vides.

    Returns:
        grid      : np.array (n_by, n_bx) int16 — index matériau (-1 = absent)
        mat_counts: {mat_index: nombre de blocs}
    """
    _idx_re = re.compile(r"_(\d+)$")
    max_tiles = tiles_x * tiles_y

    # Passe 1 : collecter tous les (bx, by, mat) valides
    entries: List[Tuple[int, int, int]] = []
    for ttile_path in ttile_files:
        m = _idx_re.search(ttile_path.stem)
        if not m:
            continue
        if int(m.group(1)) >= max_tiles:
            continue
        try:
            data = ttile_path.read_bytes()
        except OSError:
            continue
        for bx, by, mats, _ in _iter_tmat_bmats(data):
            if mats:
                entries.append((bx, by, mats[0]))

    # Déduire la taille réelle de la grille depuis les données
    if entries:
        max_bx = max(e[0] for e in entries)
        max_by = max(e[1] for e in entries)
        n_bx = max(max_bx + 1, tiles_x)
        n_by = max(max_by + 1, tiles_y)
    else:
        n_bx = tiles_x * blocks_per_tile_x
        n_by = tiles_y * blocks_per_tile_y

    grid: np.ndarray = np.full((n_by, n_bx), -1, dtype=np.int16)
    mat_counts: Dict[int, int] = {}
    for bx, by, mat in entries:
        grid[by, bx] = mat
        mat_counts[mat] = mat_counts.get(mat, 0) + 1

    return grid, mat_counts


# ── Décodeurs QTRE (fonctions internes) ──────────────────────────────────────

def _decode_qtre_3mat(qtre_bytes: bytes) -> np.ndarray:
    """Décode QTRE 3-mat (4156 B) -> array (32, 32, 4) uint8 [w0, w1, w2, alpha]."""
    if len(qtre_bytes) != 4156:
        return None
    raw = np.frombuffer(qtre_bytes[60:60+4096], dtype=np.uint8)
    return raw.reshape(32, 32, 4)


def _decode_qtre_4mat(qtre_bytes: bytes) -> np.ndarray:
    """
    Décode QTRE 4-mat ou 5-mat (6204 B) -> array (32, 32, 6) uint8.
    Canaux : [w0, w1, w2, w3, w4, alpha].
    Les poids ne sont pas normalisés à 255 — le moteur normalise les ratios.
    Pour n_mat=4, le canal 4 vaut toujours 0.
    """
    if len(qtre_bytes) != 6204:
        return None
    raw = np.frombuffer(qtre_bytes[60:60+6144], dtype=np.uint8)
    return raw.reshape(32, 32, 6)


def _decode_qtre_2mat(qtre_bytes: bytes) -> np.ndarray:
    """
    Décode QTRE 2-mat (quadtree) -> array (128, 128) float32, poids de mat_ids[0].
    NaN = pixels non couverts (héritent du matériau dominant).
    Masque feuille : 0xC0000000 (bit31 OU bit30).
    """
    if len(qtre_bytes) < 36:
        return None
    n_nodes = (len(qtre_bytes) - 32) // 4
    nodes   = np.frombuffer(qtre_bytes[32 : 32 + n_nodes*4], dtype=np.uint32)
    dim     = 128
    grid    = np.full((dim, dim), np.nan, dtype=np.float32)

    def fill(idx: int, x: int, y: int, size: int) -> None:
        if idx >= len(nodes):
            return
        node = int(nodes[idx])
        if node & 0xC0000000:
            grid[y:y+size, x:x+size] = (node & 0xFF) / 255.0
        else:
            half = size >> 1
            if half > 0 and node + 3 < len(nodes):
                fill(node,   x,      y,      half)
                fill(node+1, x+half, y,      half)
                fill(node+2, x,      y+half, half)
                fill(node+3, x+half, y+half, half)

    fill(0, 0, 0, dim)
    return grid


def _block_mat_coverage(mats: List[int], qtre: bytes | None) -> Dict[int, float]:
    """
    Retourne {mat_id: fraction_moyenne} pour un bloc.
    Gère les cas 1-mat, 2-mat, 3-mat, 4-mat et 5-mat (fallback pour QTRE variable).
    """
    n = len(mats)
    if n == 0:
        return {}
    if n == 1 or qtre is None:
        return {mats[0]: 1.0}

    if n == 2:
        grid = _decode_qtre_2mat(qtre)
        if grid is None:
            return {mats[0]: 1.0}
        valid = grid[~np.isnan(grid)]
        w0 = float(valid.mean()) if len(valid) else 0.0
        return {mats[0]: w0, mats[1]: 1.0 - w0}

    if n == 3 and len(qtre) == 4156:
        raw = _decode_qtre_3mat(qtre)
        if raw is None:
            return {mats[0]: 1.0}
        weights = raw[:, :, :3].astype(np.float32)
        totals  = weights.sum(axis=2, keepdims=True)
        totals  = np.where(totals == 0, 1.0, totals)
        norms   = (weights / totals).mean(axis=(0, 1))
        return {mats[i]: float(norms[i]) for i in range(3)}

    if n in (4, 5) and len(qtre) == 6204:
        raw = _decode_qtre_4mat(qtre)
        if raw is None:
            return {mats[0]: 1.0}
        weights = raw[:, :, :n].astype(np.float32)   # n canaux actifs
        totals  = weights.sum(axis=2, keepdims=True)
        totals  = np.where(totals == 0, 1.0, totals)
        norms   = (weights / totals).mean(axis=(0, 1))
        return {mats[i]: float(norms[i]) for i in range(n)}

    # QTRE variable (4-mat/5-mat) ou format inconnu : fallback dominant
    return {mats[0]: 1.0}


def read_ttile_all_materials(ttile_path: Path) -> Dict[Tuple[int,int], Dict]:
    """
    Lit tous les matériaux et leurs poids pour chaque bloc d'une tile.

    Returns : {(bx_global, by_global): {
        'mat_ids'  : list[int],
        'coverage' : {mat_id: fraction},   # somme ≈ 1.0
        'qtre_type': 'default'|'2mat'|'3mat'|'4mat+'
    }}
    """
    try:
        data = Path(ttile_path).read_bytes()
    except OSError:
        return {}

    result = {}
    for bx, by, mats, qtre in _iter_tmat_bmats(data):
        n = len(mats)
        if n >= 4:
            qtype = "4mat" if (qtre is not None and len(qtre) == 6204) else "4mat-fallback"
        elif n == 3:
            qtype = "3mat"
        elif n == 2:
            qtype = "2mat"
        else:
            qtype = "default"
        result[(bx, by)] = {
            "mat_ids":  mats,
            "coverage": _block_mat_coverage(mats, qtre),
            "qtre_type": qtype,
        }
    return result


def tmat_cleanup_scan(
    ttile_files: List[Path],
    materials: List[str],
    residual_threshold: float = 0.02,
) -> Dict:
    """
    Parcourt toutes les tiles et détecte les blocs avec un matériau résiduel
    (couverture < seuil, typiquement le matériau 'default' à index 0).

    Parameters
    ----------
    ttile_files          : liste des .ttile à analyser
    materials            : liste ordonnée des noms .emat (depuis parse_terr_materials)
    residual_threshold   : fraction en dessous de laquelle un mat est considéré résiduel

    Returns
    -------
    dict avec :
        'residual_blocks' : list de dicts {tile_idx, bx, by, mat_id, mat_name, coverage_pct}
        'mat_summary'     : {mat_id: nb blocs résiduel}  (trié par fréquence desc)
        'default_blocks'  : list de (bx, by) où mat 0 est dominant (vraie erreur)
    """
    _idx_re = re.compile(r"_(\d+)$")
    residual_blocks: List[Dict] = []
    mat_summary: Dict[int, int] = {}
    default_dominant: List[Tuple[int, int]] = []

    for ttile_path in ttile_files:
        m = _idx_re.search(ttile_path.stem)
        if not m:
            continue
        tile_idx = int(m.group(1))

        try:
            data = ttile_path.read_bytes()
        except OSError:
            continue

        for bx, by, mats, qtre in _iter_tmat_bmats(data):
            if not mats:
                continue
            coverage = _block_mat_coverage(mats, qtre)
            if mats[0] == 0:
                default_dominant.append((bx, by))
            for mat_id, frac in coverage.items():
                if frac < residual_threshold:
                    mat_name = materials[mat_id] if mat_id < len(materials) else f"mat_{mat_id}"
                    residual_blocks.append({
                        "tile_idx":    tile_idx,
                        "bx":          bx,
                        "by":          by,
                        "mat_id":      mat_id,
                        "mat_name":    mat_name,
                        "coverage_pct": round(frac * 100, 2),
                    })
                    mat_summary[mat_id] = mat_summary.get(mat_id, 0) + 1

    mat_summary = dict(sorted(mat_summary.items(), key=lambda x: -x[1]))
    return {
        "residual_blocks":  residual_blocks,
        "mat_summary":      mat_summary,
        "default_blocks":   default_dominant,
    }


def render_tmat_rgb(
    grid: np.ndarray,
    materials: List[str],
) -> np.ndarray:
    """
    Convertit la grille TMAT (H×W int16) en image RGB (H×W×3 uint8).
    Chaque index matériau -> rôle -> TEXTURE_COLORS.
    """
    _UNPAINTED = (40, 40, 40)
    h, w = grid.shape
    rgb = np.full((h, w, 3), _UNPAINTED, dtype=np.uint8)

    for mat_idx in np.unique(grid):
        if mat_idx < 0:
            continue
        mat_name = materials[mat_idx] if mat_idx < len(materials) else ""
        role  = mat_to_role(mat_name) if mat_name else "erosion"
        color = TEXTURE_COLORS.get(role, (128, 128, 128))
        rgb[grid == mat_idx] = color

    return rgb


def extract_tmat_block_coverage(
    ttile_files: List[Path],
    tiles_x: int,
    tiles_y: int,
    bpt_x: int,
    bpt_y: int,
    n_materials: int,
) -> np.ndarray:
    """
    Retourne (n_materials, blocks_y, blocks_x) float32 en coordonnées TMAT brutes.
    coverage[mat_idx, by, bx] = fraction [0,1] du matériau dans ce bloc.
    0.0 = bloc non peint ou matériau absent.
    """
    n_bx = tiles_x * bpt_x
    n_by = tiles_y * bpt_y
    cov  = np.zeros((n_materials, n_by, n_bx), dtype=np.float32)

    _idx_re = re.compile(r"_(\d+)$")

    for ttile_path in ttile_files:
        m = _idx_re.search(ttile_path.stem)
        if not m:
            continue
        tile_idx = int(m.group(1))
        if tile_idx >= tiles_x * tiles_y:
            continue
        try:
            data = ttile_path.read_bytes()
        except OSError:
            continue
        for bx, by, mats, qtre in _iter_tmat_bmats(data):
            if not mats or not (0 <= by < n_by and 0 <= bx < n_bx):
                continue
            for mat_id, frac in _block_mat_coverage(mats, qtre).items():
                if 0 <= mat_id < n_materials:
                    cov[mat_id, by, bx] = frac

    return cov


def render_tmat_rgb_blended(
    ttile_files: List[Path],
    tiles_x: int,
    tiles_y: int,
    blocks_per_tile_x: int,
    blocks_per_tile_y: int,
    materials: List[str],
) -> Tuple[np.ndarray, Dict[int, float]]:
    """
    Rendu TMAT avec mélange des couleurs par poids QTRE réels.
    Chaque bloc affiche un mix RGB pondéré par la couverture de chaque matériau.

    Returns:
        rgb       : np.array (n_by, n_bx, 3) uint8
        mat_fracs : {mat_idx: fraction_totale_moyenne} sur tous les blocs peints
    """
    _UNPAINTED = np.array([40, 40, 40], dtype=np.float32)
    n_bx = tiles_x * blocks_per_tile_x
    n_by = tiles_y * blocks_per_tile_y
    rgb  = np.zeros((n_by, n_bx, 3), dtype=np.float32)
    mask = np.zeros((n_by, n_bx),    dtype=bool)

    # Précalcul couleurs par matériau
    mat_colors: Dict[int, np.ndarray] = {}
    for i, name in enumerate(materials):
        role  = mat_to_role(name)
        color = TEXTURE_COLORS.get(role, (128, 128, 128))
        mat_colors[i] = np.array(color, dtype=np.float32)

    _idx_re = re.compile(r"_(\d+)$")
    mat_accum: Dict[int, float] = {}
    n_painted = 0

    for ttile_path in ttile_files:
        m = _idx_re.search(ttile_path.stem)
        if not m:
            continue
        tile_idx = int(m.group(1))
        if tile_idx >= tiles_x * tiles_y:
            continue
        try:
            data = ttile_path.read_bytes()
        except OSError:
            continue

        for bx, by, mats, qtre in _iter_tmat_bmats(data):
            if not mats or not (0 <= by < n_by and 0 <= bx < n_bx):
                continue
            coverage = _block_mat_coverage(mats, qtre)
            blended  = np.zeros(3, dtype=np.float32)
            for mat_id, frac in coverage.items():
                c = mat_colors.get(mat_id, np.array([128, 128, 128], dtype=np.float32))
                blended += c * frac
                mat_accum[mat_id] = mat_accum.get(mat_id, 0.0) + frac
            rgb[by, bx]  = blended
            mask[by, bx] = True
            n_painted   += 1

    # Blocs non peints -> gris foncé
    rgb[~mask] = _UNPAINTED

    # Normaliser mat_accum en fractions moyennes
    if n_painted:
        mat_fracs = {k: v / n_painted for k, v in mat_accum.items()}
    else:
        mat_fracs = {}

    return np.clip(rgb, 0, 255).astype(np.uint8), mat_fracs


# ── Score computation ─────────────────────────────────────────────────────────

def load_it_mask(path: str, target_shape: tuple) -> "np.ndarray":
    """Charge un masque 16-bit Instant Terra, le normalise en [0,1] float32
    et le redimensionne à target_shape (H, W) si nécessaire."""
    from PIL import Image as _PIL
    _PIL.MAX_IMAGE_PIXELS = None
    img = _PIL.open(path)
    arr = np.array(img).astype(np.float32)
    if arr.max() > 1.0:
        arr /= 65535.0
    if arr.shape != target_shape:
        _pil = _PIL.fromarray((arr * 255).astype(np.uint8))
        _pil = _pil.resize((target_shape[1], target_shape[0]), _PIL.BILINEAR)
        arr  = np.array(_pil).astype(np.float32) / 255.0
    return arr.astype(np.float32)


# ── Helpers module-level ─────────────────────────────────────────────────────

def _gate_fn(x: np.ndarray, lo: float, hi: float, w: float = 3.0) -> np.ndarray:
    """Fenêtre sigmoid : 1 dans [lo, hi], 0 hors zone, transition lisse."""
    r_lo = 1.0 / (1.0 + np.exp(-(x - lo) / max(w, 0.01)))
    r_hi = 1.0 / (1.0 + np.exp( (x - hi) / max(w, 0.01)))
    return (r_lo * r_hi).astype(np.float32)


def _eco_frac_fn(norm_val: float, ts: dict) -> float:
    """Fraction JSON alt_norm [0-1] -> fraction terrain réelle via terrain_stats."""
    if not ts:
        return float(norm_val)
    pts = [
        (0.00, 0.00),
        (0.25, ts.get("frac_p25", 0.25)),
        (0.50, ts.get("frac_p50", 0.50)),
        (0.75, ts.get("frac_p75", 0.75)),
        (0.90, ts.get("frac_p90", 0.90)),
        (1.00, 1.00),
    ]
    v = float(norm_val)
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]; x1, y1 = pts[i + 1]
        if x0 <= v <= x1:
            t = (v - x0) / max(x1 - x0, 1e-9)
            return float(y0 + t * (y1 - y0))
    return v


# ── Signaux terrain ───────────────────────────────────────────────────────────

def _build_terrain_signals(
    nat_gen,
    it_masks:           "dict | None",
    climate_profile:    str,
    coastal_distance_m: float,
    snow_pct:           int,
    flow_pct:           int,
) -> dict:
    """
    Calcule tous les signaux terrain communs aux deux passes.
    Retourne un dict utilisé par _score_base_textures et _score_erosion_textures.
    """
    from map_generator.domain.services.terrain_score_service import CLIMATE_TABLE

    cp         = CLIMATE_TABLE.get(climate_profile, CLIMATE_TABLE["Tempéré"])
    humidity   = float(cp["humidity"])
    rock_slope = float(cp["rock_slope_base"])
    snowline   = float(cp["snowline_m"])

    h      = nat_gen.heightmap_original.astype(np.float32)
    slopes = nat_gen.slopes.astype(np.float32)
    flow   = nat_gen.flow_accumulation.astype(np.float32)
    tpi    = nat_gen.tpi.astype(np.float32)
    cell   = float(nat_gen.cellsize)

    water_mask = (nat_gen.heightmap_original < 0.0) if nat_gen.h_min < -1.0 else nat_gen.water_mask
    land       = (~water_mask)
    not_water  = land.astype(np.float32)

    h_lo = float(np.percentile(h[land], 2))  if land.any() else float(h.min())
    h_hi = float(np.percentile(h[land], 98)) if land.any() else float(h.max())
    alt  = np.clip((h - h_lo) / max(h_hi - h_lo, 1.0), 0.0, 1.0).astype(np.float32) * not_water

    ts        = getattr(nat_gen, "terrain_stats", {})
    h_range_m = max(h_hi - h_lo, 1.0)

    _roughness = getattr(nat_gen, "roughness", None)
    _curvature = getattr(nat_gen, "curvature", None)
    roughness  = _roughness.astype(np.float32) if _roughness is not None else np.zeros_like(h)
    curvature  = _curvature.astype(np.float32) if _curvature is not None else np.zeros_like(h)

    _r_p95  = float(ts.get("roughness_p95_m",
                    float(np.percentile(roughness[land], 95)) if land.any() else 1.0))
    rough_n = np.clip(roughness / max(_r_p95, 0.01), 0.0, 1.0).astype(np.float32)

    _c_std    = float(np.std(curvature[land])) + 1e-9 if land.any() else 1e-9
    curv_n    = np.clip(curvature / (_c_std * 3.0), -1.0, 1.0).astype(np.float32)
    convex_n  = np.clip(-curv_n, 0.0, 1.0)
    concave_n = np.clip( curv_n, 0.0, 1.0)

    _it = it_masks or {}
    if 'curvature' in _it and _it['curvature'] is not None:
        _curv_it  = np.clip((_it['curvature'].astype(np.float32) - 0.5) * 2.0, -1.0, 1.0)
        convex_n  = np.clip( _curv_it, 0.0, 1.0)
        concave_n = np.clip(-_curv_it, 0.0, 1.0)

    f_p99  = float(np.percentile(flow[land], 99)) if land.any() else 1.0
    flow_n = np.clip(flow / (f_p99 + 1e-6), 0.0, 1.0).astype(np.float32)

    tpi_std = float(np.std(tpi)) + 1e-6
    tpi_n   = np.clip(tpi / tpi_std, -3.0, 3.0).astype(np.float32)
    valley  = np.clip(-tpi_n / 2.0, 0.0, 1.0)

    dist_m  = _edt_m(~water_mask, cell)
    thr_c   = max(float(coastal_distance_m), cell * 3.0)
    coastal = np.clip(1.0 - dist_m / thr_c, 0.0, 1.0) * not_water
    inland  = (1.0 - coastal) * not_water

    h_max        = float(np.max(h))
    snow_enabled = h_max >= (snowline - 120.0)
    snow_thr_pct = float(np.percentile(h, snow_pct)) if snow_enabled else 1e9
    snow_thr     = max(snowline, snow_thr_pct)
    if snow_enabled:
        mask_snow = (h >= snow_thr) & ((slopes >= 10.0) | (tpi_n > 2.0)) & land
    else:
        mask_snow = np.zeros_like(land)
    not_snow = (~mask_snow).astype(np.float32)

    rock_s_base = float(np.clip(rock_slope * (1.0 + (1.0 - humidity) * 0.15), 25.0, 55.0))
    if ts:
        _s90   = ts.get("slope_p90_deg", rock_s_base)
        _scale = float(np.clip(_s90 / max(rock_s_base, 1.0), 0.35, 2.0))
        rock_s = float(np.clip(rock_s_base * _scale, 12.0, 65.0))
    else:
        rock_s = rock_s_base

    if ts:
        alt_rock_frac = ts.get("frac_p90", 0.62)
    else:
        alt_rock_frac = 0.62

    flow_thr  = float(np.percentile(flow[land], flow_pct)) if land.any() else 1.0
    _slope_ef = _gate_fn(slopes, rock_s * 0.15, 60.0, w=5.0)
    # Rampes douces à la place des seuils binaires — évite les bords géométriques
    _flow_ramp  = np.clip((flow - flow_thr) / max(flow_thr * 0.30, 1e-6), 0.0, 1.0).astype(np.float32)
    _slope_ramp = np.clip((slopes - rock_s * 0.55) / 5.0, 0.0, 1.0).astype(np.float32)
    active_erosion = np.clip(
        _flow_ramp * _slope_ef * 0.6 + _slope_ramp,
        0.0, 1.0,
    )
    veg_density = (
        _gate_fn(slopes, 0.0, 28.0, w=4.0)
        * np.clip(1.0 - active_erosion * 0.7, 0.30, 1.0)
        * not_water * not_snow
    )
    no_veg = np.clip(1.0 - veg_density, 0.0, 1.0)

    _sed_src = _it.get('sediment')
    if _sed_src is not None:
        _sm = _sed_src.astype(np.float32)
        if _sm.shape != h.shape:
            from PIL import Image as _PIL
            _pil = _PIL.fromarray((np.clip(_sm, 0, 1) * 255).astype(np.uint8))
            _pil = _pil.resize((h.shape[1], h.shape[0]), _PIL.BILINEAR)
            _sm  = np.array(_pil).astype(np.float32) / 255.0
        _sm = np.clip(_sm, 0.0, 1.0)
        _sm = gaussian_filter(_sm.astype(np.float64), sigma=3.0).astype(np.float32)
        _sed_land = _sm[land & (_sm > 0.02)]
        _sed_thr  = float(np.percentile(_sed_land, 75)) if len(_sed_land) > 0 else 0.5
        sed = np.clip((_sm - _sed_thr) / max(1.0 - _sed_thr, 0.01), 0.0, 1.0) * not_water
    else:
        sed = np.clip(flow_n * valley * _gate_fn(slopes, 0.0, 12.0, w=3.0), 0.0, 1.0)

    _frac_p25 = float(ts.get("frac_p25", 0.25))
    _frac_p50 = float(ts.get("frac_p50", 0.50))
    _frac_p75 = float(ts.get("frac_p75", 0.75))

    _rock_steep_r = _gate_fn(slopes, rock_s * 0.90, 90.0, w=4.0)
    _rock_rough_r = _gate_fn(slopes, rock_s * 0.65, 90.0, w=4.0) * rough_n
    _reg_rock  = np.clip(_rock_steep_r + _rock_rough_r * 0.6, 0.0, 1.0) * not_water * not_snow

    _talus_steep_px = (slopes >= rock_s * 0.65).astype(bool)
    _talus_halo_r   = binary_dilation(_talus_steep_px, iterations=8)
    _reg_talus = (
        np.clip(_talus_halo_r.astype(np.float32) - _reg_rock, 0.0, 1.0)
        * _gate_fn(slopes, rock_s * 0.25, rock_s * 0.85, w=4.0)
        * not_snow
    )

    _reg_highland = (
        _gate_fn(alt, _frac_p75, 1.0, w=0.05)
        * _gate_fn(slopes, 0.0, rock_s * 0.65, w=4.0)
        * inland * not_snow * (1.0 - _reg_rock)
    )
    _reg_midland = (
        _gate_fn(alt, _frac_p25, _frac_p75, w=0.04)
        * _gate_fn(slopes, 0.0, rock_s * 0.70, w=4.0)
        * inland * not_snow * (1.0 - _reg_rock)
    )
    _reg_lowland = (
        _gate_fn(alt, 0.0, _frac_p50, w=0.05)
        * _gate_fn(slopes, 0.0, rock_s * 0.55, w=4.0)
        * inland * not_snow * (1.0 - _reg_rock)
    )
    _reg_valley = (
        valley * _gate_fn(flow_n, 0.25, 1.0, w=0.10)
        * _gate_fn(slopes, 0.0, rock_s * 0.55, w=4.0)
        * inland
    )

    return {
        "h": h, "alt": alt, "slopes": slopes,
        "flow_n": flow_n, "tpi_n": tpi_n,
        "coastal": coastal, "inland": inland,
        "valley": valley, "sed": sed,
        "rough_n": rough_n, "convex_n": convex_n, "concave_n": concave_n,
        "veg_density": veg_density, "no_veg": no_veg,
        "not_water": not_water, "not_snow": not_snow,
        "water_mask": water_mask, "land": land,
        "_reg_rock": _reg_rock, "_reg_talus": _reg_talus,
        "_reg_highland": _reg_highland, "_reg_midland": _reg_midland,
        "_reg_lowland": _reg_lowland, "_reg_valley": _reg_valley,
        "rock_s": rock_s, "alt_rock_frac": alt_rock_frac,
        "h_lo": h_lo, "h_range_m": h_range_m,
        "_frac_p25": _frac_p25, "_frac_p50": _frac_p50, "_frac_p75": _frac_p75,
        "ts": ts, "it_masks": _it, "cell": cell,
    }


# ── Passe 1 — textures de base ────────────────────────────────────────────────

def _score_base_textures(sig: dict, eco: dict) -> Dict[str, np.ndarray]:
    """
    Passe 1 : textures de base (fond marin, côtier, herbe, lande...).
    Les textures d'érosion (roche, debris_rock, erosion) sont absentes ici.
    """
    def _gate(x, lo, hi, w=3.0): return _gate_fn(x, lo, hi, w)
    ts = sig["ts"]
    def _eco_frac(v): return _eco_frac_fn(v, ts)

    alt         = sig["alt"]
    slopes      = sig["slopes"]
    h           = sig["h"]
    h_lo        = sig["h_lo"]
    coastal     = sig["coastal"]
    inland      = sig["inland"]
    valley      = sig["valley"]
    flow_n      = sig["flow_n"]
    tpi_n       = sig["tpi_n"]
    convex_n    = sig["convex_n"]
    concave_n   = sig["concave_n"]
    veg_density = sig["veg_density"]
    no_veg      = sig["no_veg"]
    not_water   = sig["not_water"]
    not_snow    = sig["not_snow"]
    water_mask  = sig["water_mask"]
    rock_s      = sig["rock_s"]
    _reg_rock     = sig["_reg_rock"]
    _reg_talus    = sig["_reg_talus"]
    _reg_highland = sig["_reg_highland"]
    _reg_midland  = sig["_reg_midland"]
    _reg_lowland  = sig["_reg_lowland"]
    rough_n       = sig["rough_n"]

    scores: Dict[str, np.ndarray] = {}
    _not_rock_regime = np.clip(1.0 - _reg_rock - _reg_talus, 0.0, 1.0)

    _water_core = binary_erosion(water_mask, iterations=2)
    scores["fond_marin"] = _water_core.astype(np.float32) * _gate(slopes, 0.0, 12.0, w=3.0)

    # Jitter organique sur le signal côtier -> bords irréguliers, pas de limite géométrique
    _coastal_j = np.clip(coastal + (rough_n - 0.5) * 0.40, 0.0, 1.0)

    _e_co = eco.get("cotier", {})
    _co_s = _e_co.get("slope_deg", [0, 15])
    scores["cotier"] = (
        _coastal_j
        * _gate(slopes, float(_co_s[0]), float(_co_s[1]), w=3.0)
        * _gate(h, h_lo, h_lo + float(_e_co.get("coastal_max_m", 15)), w=2.0)
    )

    _e_ga = eco.get("galets", {})
    _ga_s = _e_ga.get("slope_deg", [0, 45])
    # Décroissance exponentielle avec l'altitude (pas de seuil -> pas de marche nette)
    # rough_n jitte ±2m l'altitude effective -> suit le modelé du terrain
    _h_eff    = np.clip(h + (rough_n - 0.5) * 4.0 - h_lo, 0.0, None)
    _near_sea = np.exp(-_h_eff / 4.0).astype(np.float32)   # 100% à h_lo, ~37% à +4m, ~5% à +12m
    galets_coast   = _coastal_j * _gate(slopes, 0.0, 25.0, w=3.0) * _near_sea
    _galets_shallow = (
        water_mask.astype(np.float32)
        * _gate(h, -5.0, 0.5, w=1.0)
        * _gate(slopes, 0.0, float(_ga_s[1]), w=3.0)
        * 0.6
    )
    scores["galets"] = np.clip(galets_coast * 0.8 + _galets_shallow, 0.0, 1.0)

    _e_pr = eco.get("prairie", {})
    _pr_s = _e_pr.get("slope_deg", [0, 22])
    _pr_a = _e_pr.get("alt_norm") or [0.0, 0.50]
    scores["prairie"] = (
        _gate(slopes, float(_pr_s[0]), float(_pr_s[1]), w=3.0)
        * _gate(alt, _eco_frac(_pr_a[0]), _eco_frac(_pr_a[1]), w=0.05)
        * veg_density * inland
        * np.clip(_reg_lowland + _reg_midland, 0.0, 1.0)
        * _not_rock_regime
    )

    _e_hd = eco.get("herbe_dense", {})
    _hd_s = _e_hd.get("slope_deg", [0, 25])
    _hd_a = _e_hd.get("alt_norm") or [0.30, 0.65]
    scores["herbe_dense"] = (
        _gate(slopes, float(_hd_s[0]), float(_hd_s[1]), w=3.0)
        * _gate(alt, _eco_frac(_hd_a[0]), _eco_frac(_hd_a[1]), w=0.05)
        * veg_density * inland
        * np.clip(_reg_midland + _reg_lowland, 0.0, 1.0)
        * _not_rock_regime
    )

    _e_la = eco.get("lande", {})
    _la_s = _e_la.get("slope_deg", [0, 28])
    _la_a = _e_la.get("alt_norm") or [0.50, 0.95]
    scores["lande"] = (
        _gate(slopes, float(_la_s[0]), float(_la_s[1]), w=3.0)
        * _gate(alt, _eco_frac(_la_a[0]), _eco_frac(_la_a[1]), w=0.06)
        * veg_density * inland
        * np.clip(_reg_highland + _reg_midland, 0.0, 1.0)
        * _not_rock_regime
        * np.clip(1.0 - concave_n * 1.5, 0.0, 1.0)
    )

    _e_he = eco.get("heather", {})
    _he_s = _e_he.get("slope_deg", [0, 22])
    _he_a = _e_he.get("alt_norm") or [0.35, 0.90]
    _not_rocky_slope = np.clip(1.0 - _gate(slopes, rock_s * 0.5, 90.0, w=4.0), 0.0, 1.0)
    scores["heather"] = np.clip(
        _gate(slopes, float(_he_s[0]), float(_he_s[1]), w=4.0)
        * _gate(alt, _eco_frac(_he_a[0]), _eco_frac(_he_a[1]), w=0.06)
        * np.clip(tpi_n + 0.3, 0.0, 1.0)
        * np.clip(1.0 - flow_n * 2.0, 0.0, 1.0)
        * np.clip(0.5 + convex_n * 0.5, 0.0, 1.0)
        * veg_density * _not_rocky_slope * inland
        * np.clip(_reg_highland + _reg_midland, 0.0, 1.0)
        * _not_rock_regime
        * 0.45,
        0.0, 1.0,
    )

    _zero = np.zeros_like(alt)
    scores["feuillus"]  = _zero
    scores["coniferes"] = _zero
    scores["lisiere"]   = _zero

    return scores


# ── Passe 2 — pipeline érosion ────────────────────────────────────────────────

def _score_erosion_textures(sig: dict) -> Dict[str, np.ndarray]:
    """
    Passe 2 : roche, debris_rock, erosion.
    Pilotés directement par les IT masks bruts (slope, curvature, sediment).
    """
    from PIL import Image as _PIL

    def _resize_it(arr: np.ndarray, shape: tuple, smooth: bool = False) -> np.ndarray:
        if arr.shape == shape:
            return arr
        _pil = _PIL.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
        _pil = _pil.resize((shape[1], shape[0]), _PIL.BILINEAR)
        out = np.array(_pil).astype(np.float32) / 255.0
        if smooth:
            out = gaussian_filter(out.astype(np.float64), sigma=3.0).astype(np.float32)
        return out

    h           = sig["h"]
    rough_n     = sig["rough_n"]
    concave_n   = sig["concave_n"]
    sed         = sig["sed"]
    not_water   = sig["not_water"]
    not_snow    = sig["not_snow"]
    coastal     = sig["coastal"]
    no_veg      = sig["no_veg"]
    veg_density = sig["veg_density"]
    rock_s      = sig["rock_s"]
    slopes      = sig["slopes"]
    _it         = sig["it_masks"]
    h_lo        = sig["h_lo"]
    h_range_m   = sig["h_range_m"]
    _frac_p75   = sig["_frac_p75"]

    scores: Dict[str, np.ndarray] = {}
    _tgt         = h.shape
    _not_coastal = np.clip(1.0 - coastal * 4.0, 0.0, 1.0)
    _soft_no_veg = np.clip(1.0 - veg_density * 1.2, 0.0, 1.0)

    # ── Signaux IT primaires — photographie exacte du terrain ─────────────────
    # Fallback sur signaux heightmap si masque absent (carte sans IT masks)
    _slope_it = _it.get('slopes')
    _curv_it  = _it.get('curvature')
    _sed_it   = _it.get('sediment')

    # Pente : IT mask 0->1 (0°=0, 90°=1) ou Sobel heightmap en fallback
    if _slope_it is not None:
        _slope_raw = np.clip(_slope_it.astype(np.float32), 0.0, 1.0)
    else:
        _slope_raw = np.clip(slopes / 90.0, 0.0, 1.0)

    # Courbure : IT mask centré 0.5 (sombre=concave, clair=convexe) ou concave_n heightmap
    if _curv_it is not None:
        _curv      = _curv_it.astype(np.float32)
        _concave   = np.clip((0.5 - _curv) / 0.35, 0.0, 1.0)  # 1=fond de ravine
        _convex    = np.clip((_curv - 0.5) / 0.35, 0.0, 1.0)  # 1=crête/éperon
    else:
        _concave   = concave_n
        _convex    = np.clip(1.0 - concave_n, 0.0, 1.0)

    # Sédiment : IT mask 0->1 (blanc=accumulation) ou sed heightmap
    _sediment = _sed_it.astype(np.float32) if _sed_it is not None else sed

    # Jitter organique sur la pente (rough_n = micro-détail heightmap, irremplaçable)
    _slope_raw_j = np.clip(_slope_raw + rough_n * 0.05, 0.0, 1.0)

    # ── Roche : pente IT + boost convexité sommet ─────────────────────────────
    _alt        = np.clip((h - h_lo) / h_range_m, 0.0, 1.0).astype(np.float32)
    _rock_noise = np.clip(0.3 + rough_n * 0.7, 0.0, 1.0)

    # Seuil roche : 0.33 ≈ 30°, ramp sur 0.22 (≈20°) — ajustable par terrain
    _thr_rock   = 0.33
    _ramp_rock  = 0.22
    _roche_slope = np.clip((_slope_raw_j - _thr_rock) / _ramp_rock, 0.0, 1.0) * _rock_noise
    # Boost sommet via convexité IT : crêtes/dômes = convexe -> roche organique sans isolignes
    # _convex est déjà extrait de mask_curv (clair=convexe), pas d'artefact d'altitude
    _roche_convex = _convex * _rock_noise * 0.45
    scores["roche"] = np.clip(
        _roche_slope + _roche_convex, 0.0, 1.0,
    ) * no_veg * not_snow * np.clip(1.0 - coastal * 2.0, 0.0, 1.0)

    # ── Debris : frange pente + crevasses (concave IT) + flancs talweg ────────
    _debris_noise = np.clip(0.3 + rough_n * 0.7, 0.0, 1.0)
    # Frange herbe->roche : pic centré sur le seuil roche
    _slope_d = np.clip((_slope_raw - _thr_rock * 0.55) / (_thr_rock * 0.90), 0.0, 1.0)
    _fringe  = np.clip(_slope_d * (1.0 - _slope_d) * 4.0, 0.0, 1.0)
    # Crevasses dans face rocheuse : concave IT × pente forte
    _debris_creux = _concave * _roche_slope * _debris_noise * 0.55

    # ── Canal talweg : curvature IT × sediment IT -> fond de ravin précis ──────
    _creux_brut  = np.clip(_concave * _sediment, 0.0, 1.0)
    _creux_guide = np.power(_creux_brut, 1.5)

    _no_rock     = np.clip(1.0 - _roche_slope, 0.0, 1.0)
    _erosion_var = np.clip(0.25 + rough_n * 0.75, 0.0, 1.0)

    # Dirt core : centre du talweg (seuil abaissé pour plus de couverture)
    _dirt_core    = np.clip((_creux_guide - 0.08) / 0.25, 0.0, 1.0)
    # Debris flancs : couronne autour du talweg, s'efface au fond
    _debris_flancs = (
        np.clip(_creux_guide / 0.22, 0.0, 1.0)
        * np.clip(1.0 - _dirt_core, 0.0, 1.0)
        * _no_rock * _debris_noise * 0.35
    )

    scores["debris_rock"] = np.clip(
        _debris_creux + _fringe * _debris_noise * 0.50 + _debris_flancs, 0.0, 1.0,
    ) * _not_coastal * not_snow

    # ── Erosion : crevasses rocheuses + fond de talweg stratifié ─────────────
    # Crevasses : concave IT dans zone pentue (ravines sur pentes)
    _erosion_creux = (
        np.clip(_concave * 1.5 - 0.35, 0.0, 1.0)
        * np.clip(_slope_raw * 2.0, 0.0, 1.0)
        * not_water * not_snow * _not_coastal * 0.38
    )
    # Dirt fond talweg : dirt_core × hors-roche × variation organique
    _erosion_sed = (
        _dirt_core * _no_rock * _erosion_var * not_water * not_snow * _soft_no_veg * 0.45
    )
    scores["erosion"] = np.clip(_erosion_creux + _erosion_sed, 0.0, 1.0)

    return scores


# ── Combine ───────────────────────────────────────────────────────────────────

def _combine_passes(
    base_scores:    Dict[str, np.ndarray],
    erosion_scores: Dict[str, np.ndarray],
    sig:            dict,
) -> Dict[str, np.ndarray]:
    """
    Combine passe 1 (base) et passe 2 (érosion) + post-processing.
    L'érosion est un phénomène de second ordre : elle écrase les textures de base
    proportionnellement à son poids total sur chaque pixel.
    """
    not_water  = sig["not_water"]
    water_mask = sig["water_mask"]
    land       = sig["land"]

    erosion_weight = np.clip(sum(erosion_scores.values()), 0.0, 1.0)
    base_weight    = 1.0 - erosion_weight

    scores: Dict[str, np.ndarray] = {}
    for role, arr in base_scores.items():
        scores[role] = arr * base_weight
    for role, arr in erosion_scores.items():
        scores[role] = arr

    # QTRE prevention : supprimer herbe secondaire (lande, heather) dans le rayon
    # des zones rocheuses (≈1 bloc = 32m) pour éviter 5 textures/bloc en transition.
    _rock_sum = np.zeros(not_water.shape, dtype=np.float32)
    for _k in ("roche", "debris_rock"):
        if _k in scores:
            _rock_sum = _rock_sum + scores[_k]
    _rock_prox = gaussian_filter(_rock_sum.astype(np.float64), sigma=14.0).astype(np.float32)
    _grass_sup  = np.clip(1.0 - _rock_prox * 8.0, 0.0, 1.0)
    for _secondary in ("lande", "heather", "herbe_dense"):
        if _secondary in scores:
            scores[_secondary] = scores[_secondary] * _grass_sup

    _safety = not_water * 0.005
    for _k in ("prairie", "herbe_dense", "debris_rock", "erosion", "roche"):
        if _k in scores:
            scores[_k] = np.maximum(scores[_k], _safety)

    # Propagation roche/debris sur zones plates adjacentes — AVANT le contraste
    # sigma=40 (~40m) pour atteindre les plateaux au-delà des falaises.
    # Jitter rough_n sur les valeurs propagées pour casser les frontières rectilignes.
    _rough_n = sig["rough_n"]
    for _k in ("roche", "debris_rock"):
        if _k in scores:
            _spread  = gaussian_filter(scores[_k].astype(np.float64), sigma=40.0).astype(np.float32)
            _jitter  = np.clip(0.65 + _rough_n * 0.70, 0.0, 1.0)
            scores[_k] = np.maximum(scores[_k], _spread * _jitter)

    _CONTRAST = 1.5
    for _k in scores:
        if _k != "fond_marin":
            scores[_k] = np.power(np.clip(scores[_k], 0.0, 1.0), _CONTRAST)

    _sigmas = {
        "cotier": 3.0, "galets": 14.0, "prairie": 0.5, "herbe_dense": 0.8,
        "lande": 1.5, "heather": 1.0, "erosion": 2.0, "debris_rock": 10.0, "roche": 3.0,
    }
    for _k, _sig_val in _sigmas.items():
        if _k in scores:
            _arr = np.nan_to_num(scores[_k], nan=0.0, posinf=0.0, neginf=0.0)
            scores[_k] = gaussian_filter(_arr.astype(np.float64), sigma=_sig_val).astype(np.float32)

    for _k in scores:
        if _k == "fond_marin":
            scores[_k][land]       = 0.0
        else:
            scores[_k][water_mask] = 0.0

    _tot = sum(scores.values()) + 1e-8
    return {k: (v / _tot).astype(np.float32) for k, v in scores.items()}


# ── Point d'entrée public ─────────────────────────────────────────────────────

def compute_texture_scores(
    nat_gen,
    climate_profile:    str   = "Tempéré",
    coastal_distance_m: float = 60.0,
    snowline_alt_pct:   float = 0.75,
    snow_pct:           int   = 92,
    flow_pct:           int   = 88,
    sediment_mask:      "np.ndarray | None" = None,
    it_masks:           "dict | None" = None,
) -> Dict[str, np.ndarray]:
    """
    Pipeline texture 2 passes :
    - Passe 1 : textures de base (herbe, lande, côtier, fond marin...)
    - Passe 2 : pipeline érosion (roche, debris_rock, erosion) — écrase la passe 1
    Retourne des arrays float32 H×W normalisés (somme = 1 par pixel).
    """
    # Fusionner sediment_mask dans it_masks pour rétro-compatibilité (priorité à it_masks)
    _it = dict(it_masks) if it_masks else {}
    if sediment_mask is not None and 'sediment' not in _it:
        _it['sediment'] = sediment_mask

    sig     = _build_terrain_signals(
        nat_gen, _it,
        climate_profile, coastal_distance_m,
        snow_pct, flow_pct,
    )
    eco     = _load_role_eco()
    base    = _score_base_textures(sig, eco)
    erosion = _score_erosion_textures(sig)
    return _combine_passes(base, erosion, sig)


# ── Block budget ──────────────────────────────────────────────────────────────

def apply_block_budget(
    texture_scores:  Dict[str, np.ndarray],
    block_px:        int,
    max_textures:    int   = 4,
    base_role:       str | None = None,
) -> Tuple[Dict[str, np.ndarray], Dict]:
    """
    Apply per-block texture budget constraint (Reforger: max N textures/block,
    weights summing to 1.0).

    Algorithm per block
    -------------------
    1. Compute mean weight of each texture in the block
    2. Keep the top ``max_textures`` candidates (mean > 2%)
    3. Zero-out all other textures at pixel level in this block
    4. Restore original scores for orphan pixels (all selected = 0)
    5. Renormalise remaining scores pixel-by-pixel so sum = 1

    base_role
    ---------
    When set (e.g. "prairie"), this role is pre-painted on the entire terrain in
    Workbench and is NOT exported as a mask. It permanently occupies 1 QTRE slot,
    so non-base textures are limited to max_textures-1 per block. The base role's
    pixel values are kept in constrained (for correct preview rendering) but
    export code skips them.

    Returns
    -------
    constrained_scores  dict (same structure, budget-constrained)
    block_assignments   dict  (bx, by_reforger) -> [(role, normalised_weight)]
                        Reforger Y convention: 0 = bottom of terrain
    """
    # Seuil de sélection : on exclut seulement les textures vraiment absentes
    # d'un bloc (moyenne < 2%). Le top-4 par moyenne bloc fait le tri naturel.
    _MIN_SELECTION = 0.02

    keys = [k for k in TEXTURE_ORDER if k in texture_scores]
    h, w = next(iter(texture_scores.values())).shape

    constrained      = {k: texture_scores[k].copy() for k in keys}
    block_assignments: Dict = {}

    # Slots disponibles pour les textures non-base.
    # La texture de base occupe 1 slot permanent dans WB -> budget effectif réduit.
    _eff_max = max_textures - 1 if (base_role and base_role in keys) else max_textures

    n_blocks_y = (h + block_px - 1) // block_px
    n_blocks_x = (w + block_px - 1) // block_px

    for by_img in range(n_blocks_y):
        for bx in range(n_blocks_x):
            y0 = by_img * block_px
            y1 = min(y0 + block_px, h)
            x0 = bx    * block_px
            x1 = min(x0 + block_px, w)

            means = {
                k: float(np.mean(texture_scores[k][y0:y1, x0:x1]))
                for k in keys
            }

            sorted_t = sorted(means.items(), key=lambda x: x[1], reverse=True)

            # Sélectionner parmi les textures non-base uniquement (_eff_max slots).
            # La base est toujours "présente" via la peinture WB, pas via un masque.
            non_base_sorted = [(k, v) for k, v in sorted_t if k != base_role]
            top = [
                (k, v) for k, v in non_base_sorted
                if v >= _MIN_SELECTION
            ][:_eff_max]
            if not top:
                top = [non_base_sorted[0]] if non_base_sorted else [sorted_t[0]]

            selected = {k for k, _ in top}

            # Règles d'incompatibilité supprimées : elles créaient des frontières
            # carrées à 32m et excluaient des textures géographiquement correctes
            # (ex: roche exclue d'un bloc de transition heather/roche).
            # Les seuils d'émergence par texture (_EMERGENCE) suffisent à filtrer
            # les textures trop faibles pour être visibles — sans coupures brutales.

            for k in keys:
                if k not in selected:
                    constrained[k][y0:y1, x0:x1] = 0.0

            # Pixel-level safety pour les blocs mixtes eau/terre :
            # Après zeroing des non-sélectionnés, les pixels terrestres dans un bloc
            # dominé par fond_marin se retrouvent à 0 -> pixel noir -> texture default.
            # IMPORTANT : on restaure UNIQUEMENT les textures sélectionnées pour ce bloc
            # afin de ne pas dépasser le budget 4 textures/bloc (cause du crash Reforger).
            # Erreur précédente : "for k in keys" restaurait toutes les textures -> 5+/bloc.
            _blk_nonzero = sum(constrained[k][y0:y1, x0:x1] for k in keys)
            _orphan = _blk_nonzero < 1e-6
            if _orphan.any():
                for k in selected:
                    _orig = texture_scores[k][y0:y1, x0:x1]
                    constrained[k][y0:y1, x0:x1] = np.where(
                        _orphan, _orig, constrained[k][y0:y1, x0:x1]
                    )

            # Second pass : si des pixels sont encore orphelins (les scores originaux
            # étaient aussi à 0 pour toutes les textures sélectionnées — cas des pixels
            # terrestres isolés dans un bloc majoritairement sous-marin), on les force
            # sur la texture dominante du bloc. Sans ça, Reforger affiche "default".
            _blk_still = sum(constrained[k][y0:y1, x0:x1] for k in selected)
            _still_orphan = _blk_still < 1e-6
            if _still_orphan.any():
                fallback_k = top[0][0]   # texture avec la plus grande moyenne de bloc
                constrained[fallback_k][y0:y1, x0:x1] = np.where(
                    _still_orphan, 1.0, constrained[fallback_k][y0:y1, x0:x1]
                )

            blk_sum = sum(constrained[k][y0:y1, x0:x1] for k in selected) + 1e-8
            for k in selected:
                constrained[k][y0:y1, x0:x1] /= blk_sum

            top_sum = sum(v for _, v in top) or 1.0
            by_rf   = n_blocks_y - 1 - by_img
            block_assignments[(bx, by_rf)] = [(k, v / top_sum) for k, v in top]

    return constrained, block_assignments


# ── Rendering ─────────────────────────────────────────────────────────────────

_WATER_SHALLOW = np.array([ 80, 185, 220], dtype=np.float32)  # bleu-turquoise peu profond
_WATER_DEEP    = np.array([ 10,  35,  75], dtype=np.float32)  # bleu marine profond


def render_rgb(
    constrained_scores: Dict[str, np.ndarray],
    heightmap: "np.ndarray | None" = None,
    alt_min: float = 0.0,
) -> np.ndarray:
    """Blend texture colours by constrained weights -> RGB uint8 H×W×3.

    Si ``heightmap`` est fourni et ``alt_min`` < 0, les pixels sous-marins
    reçoivent une couleur interpolée entre bleu clair (surface) et bleu foncé
    (fond), proportionnelle à la profondeur normalisée.
    """
    h, w   = next(iter(constrained_scores.values())).shape
    result = np.zeros((h, w, 3), dtype=np.float32)
    for k in TEXTURE_ORDER:
        if k in constrained_scores:
            c       = np.array(TEXTURE_COLORS[k], dtype=np.float32)
            result += constrained_scores[k][..., np.newaxis] * c
    result = np.clip(result, 0, 255)

    if heightmap is not None and alt_min < 0:
        water_mask = heightmap < 0
        if np.any(water_mask):
            # depth_n : 0 = surface, 1 = point le plus profond
            depth_n = np.clip(heightmap / alt_min, 0.0, 1.0)
            water_rgb = (
                _WATER_SHALLOW * (1.0 - depth_n[..., np.newaxis])
                + _WATER_DEEP  *        depth_n[..., np.newaxis]
            )
            result[water_mask] = water_rgb[water_mask]

    return result.astype(np.uint8)


# ── Grid overlay ──────────────────────────────────────────────────────────────

def draw_grid_overlay(
    img_rgb:          np.ndarray,
    reforger_data:    dict,
    cell_m:           float,
    show_blocks:      bool = True,
    show_tile_labels: bool = True,
) -> np.ndarray:
    """
    Overlay tile (thick) and block (thin) grids with Reforger tile labels.
    Tile labels use Reforger convention: (0,0) = bottom-left of terrain.
    """
    import cv2

    img = np.ascontiguousarray(img_rgb.copy())
    h, w = img.shape[:2]

    _tsm = reforger_data.get("tile_size_m", 128)
    tile_size_m  = float(_tsm[0] if isinstance(_tsm, (list, tuple)) else _tsm)
    _bsm = reforger_data.get("block_size_m", 32)
    block_size_m = float(_bsm[0] if isinstance(_bsm, (list, tuple)) else _bsm)
    tile_px      = max(1, round(tile_size_m  / cell_m))
    block_px     = max(1, round(block_size_m / cell_m))
    n_tiles_y    = (h + tile_px - 1) // tile_px
    n_tiles_x    = (w + tile_px - 1) // tile_px

    if show_blocks and block_px >= 10:
        for x in range(0, w, block_px):
            cv2.line(img, (x, 0), (x, h - 1), (80, 80, 80), 1)
        for y in range(0, h, block_px):
            cv2.line(img, (0, y), (w - 1, y), (80, 80, 80), 1)

    for x in range(0, w, tile_px):
        cv2.line(img, (x, 0), (x, h - 1), (255, 220, 0), 2)
    for y in range(0, h, tile_px):
        cv2.line(img, (0, y), (w - 1, y), (255, 220, 0), 2)

    if show_tile_labels:
        font = cv2.FONT_HERSHEY_SIMPLEX
        for tx in range(n_tiles_x):
            for ty_img in range(n_tiles_y):
                ty_rf = n_tiles_y - 1 - ty_img
                xp    = tx     * tile_px + 3
                yp    = ty_img * tile_px + 14
                if xp + 55 < w and yp < h:
                    label = f"{tx},{ty_rf}"
                    cv2.putText(img, label, (xp, yp), font, 0.35,
                                (  0,   0,   0), 2, cv2.LINE_AA)
                    cv2.putText(img, label, (xp, yp), font, 0.35,
                                (255, 255, 255), 1, cv2.LINE_AA)

    return img


# ── Debug info ────────────────────────────────────────────────────────────────

def get_tile_debug_info(
    block_assignments: Dict,
    tile_x:            int,
    tile_y:            int,
    blocks_per_tile:   Tuple[int, int],
    biome_textures:    Dict[str, str],
) -> List[Dict]:
    """
    Return per-block texture assignments for a given Reforger tile.
    tile_x, tile_y   : Reforger coords (0,0 = bottom-left)
    blocks_per_tile  : (bx_count, by_count) from reforger_data['blocks_per_tile']
    biome_textures   : role -> emat name (editable by mapper)
    """
    bx0 = tile_x * blocks_per_tile[0]
    by0 = tile_y * blocks_per_tile[1]

    result = []
    for dby in range(blocks_per_tile[1]):
        for dbx in range(blocks_per_tile[0]):
            bx  = bx0 + dbx
            by  = by0 + dby
            asg = block_assignments.get((bx, by), [])
            result.append({
                "bloc_local":  (dbx, dby),
                "bloc_global": (bx,  by),
                "textures": [
                    {
                        "role":    k,
                        "label":   TEXTURE_LABELS.get(k, k),
                        "emat":    biome_textures.get(k, "???"),
                        "poids_%": round(weight * 100, 1),
                    }
                    for k, weight in asg
                ],
            })
    return result
