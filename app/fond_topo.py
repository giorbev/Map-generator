# -*- coding: utf-8 -*-
"""
fond_topo.py — Fond de la carte du jeu (topo) à partir de la satmap du projet

L'image sert de « Satellite background image » à SCR_MapEntity : le jeu l'affiche sous la carte
(routes, eau, courbes de niveau, quadrillage par-dessus). Réglages validés sur ZBK (05/11/2026) :

  mer         terrain sous 0 m (altitudes Workbench) recoloré à la couleur exacte de la mer de la
              carte du jeu (RVB 95 126 132, mesurée hors image) : raccord sans couture au bord ;
              transition douce sur 1 m autour de la côte
  terre       satmap, tons moyens éclaircis (gamma), contraste, saturation, voile blanc optionnel
  taille      multiple de 4 (compression DXT de Workbench : 4097 ou 8193 px sont refusés à l'import)

Import dans Workbench : Import Settings > Color Space = ToSRGB (le défaut ToLinear des textures
« Unspecified » éclaircit toute l'image, gamma ≈ 2,2) Tiled Texture décoché (sinon aucun fond en jeu) et Generate Mips décoché (sinon
la carte n'affiche qu'une version très réduite, environ 1/32).
"""

import time
from pathlib import Path

import numpy as np
from PIL import Image

SEA_RGB = (95, 126, 132)          # mer de la carte du jeu (Reforger 1.9)
DEFAULTS = {"gamma": 0.7, "contrast": 1.2, "saturation": 1.15, "white": 0.12}


def find_satmap(generated_dir: Path):
    """Satmap la plus récente du projet (satmap_v2_textured_*.png), hors fichiers temporaires."""
    cands = [p for p in Path(generated_dir).glob("satmap_v2_textured_*.png") if "temp" not in p.stem]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def _resize(arr: np.ndarray, size: int, resample) -> np.ndarray:
    return np.asarray(Image.fromarray(arr).resize((size, size), resample))


def colorer_eau(f, heights, water=None, terrain_size_m=None, sea_rgb=SEA_RGB, log=print):
    """Mer (terrain sous 0 m) et lacs et rivières à la couleur de la mer du jeu sur l'image f (float, size x size x 3).

    Renvoie (f, sea_pct, water_ha) ; heights : altitudes nord en haut, ou None (rien n'est recoloré).
    """
    size = f.shape[0]
    sea_pct = 0.0
    if heights is not None:
        h = _resize(np.asarray(heights, dtype=np.float32), size, Image.BILINEAR)
        w = np.clip((0.5 - h) / 1.0, 0.0, 1.0)[..., None]       # 0 au-dessus de 0,5 m, 1 sous -0,5 m
        f = f * (1.0 - w) + np.asarray(sea_rgb, np.float32) * w
        sea_pct = round(float((h < 0).mean()) * 100, 1)
    else:
        log("[TOPO] Altitudes absentes : mer non recolorée")
    water_ha = 0.0
    if water and heights is not None and terrain_size_m:
        from PIL import ImageFilter
        from water_layers import water_mask
        m = water_mask(water, heights, float(terrain_size_m), size)
        water_ha = round(float(m.sum()) * (float(terrain_size_m) / size) ** 2 / 1e4, 1)
        a = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7)),
                       dtype=np.float32)[..., None] / 255.0           # bords adoucis
        f = f * (1.0 - a) + np.asarray(sea_rgb, np.float32) * a
        log(f"[TOPO] Lacs et rivières : {len(water)} formes, {water_ha} ha d'eau")
    return f, sea_pct, water_ha


def generate_fond_topo(satmap_path, heights, output_path, size: int = 4096, gamma: float = DEFAULTS["gamma"],
                       contrast: float = DEFAULTS["contrast"], saturation: float = DEFAULTS["saturation"],
                       white: float = DEFAULTS["white"], sea_rgb=SEA_RGB, water=None, terrain_size_m=None,
                       log=print) -> dict:
    """Écrit le fond de carte (PNG RGB, nord en haut) ; heights : altitudes nord en haut, ou None (pas de mer).

    water : lacs et rivières (water_layers.load_water()["bodies"]) colorés comme la mer, ou None ;
    terrain_size_m : côté du terrain en mètres (obligatoire avec water).
    Renvoie {"ok", "path", "size", "sea_pct", "water_ha", "seconds"} ou {"ok": False, "error"}.
    """
    t0 = time.time()
    size = max(4, int(size) // 4 * 4)                       # multiple de 4 (DXT)
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(satmap_path) as im:
        src = im.convert("RGB")
        log(f"[TOPO] Satmap {Path(satmap_path).name} : {src.size[0]} x {src.size[1]} px")
        f = np.asarray(src.resize((size, size), Image.LANCZOS), dtype=np.float32)
    gray = f.mean(axis=2, keepdims=True)
    f = gray + (f - gray) * float(saturation)
    f = 255.0 * np.clip(f / 255.0, 0.0, 1.0) ** float(gamma)    # tons moyens
    f = (f - 140.0) * float(contrast) + 140.0
    f = f * (1.0 - float(white)) + 255.0 * float(white)
    f, sea_pct, water_ha = colorer_eau(f, heights, water, terrain_size_m, sea_rgb, log)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(f, 0, 255).astype(np.uint8)).save(out)
    secs = round(time.time() - t0, 1)
    log(f"[TOPO] Fond de carte écrit : {out.name} ({size} px, mer {sea_pct} %, {secs} s)")
    return {"ok": True, "path": str(out), "size": size, "sea_pct": sea_pct, "water_ha": water_ha, "seconds": secs}


# ── Config de carte : courbes de niveau (validée en jeu sur ZBK le 05/11/2026) ──
# Hérite de la config plein écran du jeu de base (GUID de Configs/Map/MapFullscreen.conf du jeu) ;
# seuls l'écart des courbes et des maîtresses par couche de zoom, les épaisseurs et la couleur terre
# changent, et la courbe de côte (0 m) est rendue invisible : le jeu la trace en segments grossiers qui
# coupent les baies (vu en jeu sur Zimnitrita le 13/11), le fond dessine déjà une côte précise.
# Jeu de base : 20 / 50 / 100 / 125 m, maîtresses 100 m.
MAP_CONFIG_NAME = "MGP_MapFullscreen_courbes.conf"
MAP_CONFIG = """SCR_MapConfig : "{1B8AC767E06A0ACD}Configs/Map/MapFullscreen.conf" {
 m_LayersConfig SCR_MapLayersBase "{58C8DDC97E580BED}" : "{3CAC09C3E89190F7}Configs/Map/MapLayersDefault.conf" {
  m_aLayers {
   SCR_LayerConfiguration "{54D50001FDCE8F33}" {
    m_fContourDensity 5
    m_fMajorContourDensity 25
   }
   SCR_LayerConfiguration "{54D50001FDAC5B34}" {
    m_fContourDensity 10
    m_fMajorContourDensity 50
   }
   SCR_LayerConfiguration "{54D50001C2EE1562}" {
    m_fContourDensity 20
    m_fMajorContourDensity 100
   }
   SCR_LayerConfiguration "{54D50001C3C8B072}" {
    m_fContourDensity 50
    m_fMajorContourDensity 250
   }
  }
 }
 m_MapPropsConfig SCR_MapPropsBase "{58C89E75E1BB275D}" : "{AF65563F653FED68}Configs/Map/MapPropsDefault.conf" {
  m_aMapPropConfigs {
   SCR_ContourPropsConfig "{55948AFEC4F12B7D}" {
    m_fContourWidth 1.3
    m_fMajorContourWidth 2.6
    m_LandColor 0.28 0.12 0.05 0.95
    m_CoastalColor 0.202 0.064 0.031 0
   }
  }
 }
}
"""


def write_map_config(output_dir) -> Path:
    """Écrit la config de carte des courbes de niveau (MGP_MapFullscreen_courbes.conf) dans output_dir."""
    out = Path(output_dir) / MAP_CONFIG_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(MAP_CONFIG, encoding="utf-8", newline="\n")
    return out
