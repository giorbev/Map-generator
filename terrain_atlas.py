"""
Atlas Métrique des fichiers .bterr
Analyse altitudes et pentes pour calibration Gaea
"""

import struct
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional, Callable


# Taille cellule heightmap (mètres réels)
CELL_SIZE = 4.0  # Confirmé sur Zimnitrita : 32×128×4 = 16384 m


def build_terrain_atlas(
    editor_dir: Path,
    grid_size: int,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> pd.DataFrame:
    """
    Lit tous les Terrain_N.bterr et calcule pour chaque tuile :
    - altitude min/max/moyenne
    - pente min/max/moyenne (à 4 m/cellule)
    - % surface par paliers de pente

    Args:
        editor_dir: Dossier .EditorData (Path ou str)
        grid_size: Taille de la grille (32 pour 1024 tuiles)
        progress_callback: Fonction appelée avec (current, total) pour progression

    Returns:
        DataFrame avec les métriques par tuile
    """
    # Convertir en Path si nécessaire
    if isinstance(editor_dir, str):
        editor_dir = Path(editor_dir)

    records = []

    # Lister fichiers .bterr avec numéro
    bterr_files = sorted(editor_dir.glob("Terrain_*.bterr"))
    bterr_files = [
        f for f in bterr_files
        if f.stem != "Terrain" and f.stem.split("_")[-1].isdigit()
    ]

    total = len(bterr_files)

    for idx, bterr in enumerate(bterr_files):
        # Extraire tile_id
        try:
            tid = int(bterr.stem.split("_")[1])
        except (IndexError, ValueError):
            continue

        # Calculer position dans la grille
        tx = tid % grid_size
        ty_visual = tid // grid_size
        # Origine bas-gauche → inverser Y
        ty_real = (grid_size - 1) - ty_visual

        # Lire .bterr
        try:
            with open(bterr, 'rb') as f:
                data = f.read()

            # Chercher chunk DATA
            i = data.find(b"DATA")
            if i < 0:
                continue

            # Lire taille (big-endian)
            sz = struct.unpack_from(">I", data, i + 4)[0]

            # Lire heightmap (129×129 float32)
            hm = np.frombuffer(data[i + 8:i + 8 + sz], np.float32).reshape(129, 129)

        except Exception as e:
            print(f"  Erreur lecture {bterr.name}: {e}")
            continue

        # Calculer pentes (degrés, 4 m/cellule)
        gy, gx = np.gradient(hm.astype(np.float64), CELL_SIZE)
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))

        # 1. Percentile 90 de la pente (seuil de calibration Gaea)
        slope_p90 = float(np.percentile(slope, 90))

        # 2. Courbure moyenne (laplacien) — positif = crête, négatif = talweg
        curvature = np.gradient(np.gradient(hm.astype(np.float64), CELL_SIZE, axis=0), CELL_SIZE, axis=0) + \
                    np.gradient(np.gradient(hm.astype(np.float64), CELL_SIZE, axis=1), CELL_SIZE, axis=1)
        curv_mean = float(curvature.mean())
        curv_convex = float((curvature < -0.01).mean() * 100)  # % crêtes convexes
        curv_concave = float((curvature > 0.01).mean() * 100)  # % talwegs concaves

        # 3. % surface sous 0 m (zone marine)
        pct_underwater = float((hm < 0).mean() * 100)

        # Métriques
        records.append({
            "tile_id": tid,
            "col": tx,
            "row_real": ty_real,
            "alt_min": float(hm.min()),
            "alt_max": float(hm.max()),
            "alt_mean": float(hm.mean()),
            "slope_mean": float(slope.mean()),
            "slope_max": float(slope.max()),
            "slope_p90": slope_p90,
            "pct_0_5": float((slope < 5).mean() * 100),
            "pct_5_15": float(((slope >= 5) & (slope < 15)).mean() * 100),
            "pct_15_25": float(((slope >= 15) & (slope < 25)).mean() * 100),
            "pct_25_35": float(((slope >= 25) & (slope < 35)).mean() * 100),
            "pct_35_plus": float((slope >= 35).mean() * 100),
            "curv_mean": curv_mean,
            "curv_convex": curv_convex,
            "curv_concave": curv_concave,
            "pct_underwater": pct_underwater,
            "has_sea": bool(hm.min() < 0),
        })

        # Callback progression
        if progress_callback:
            progress_callback(idx + 1, total)

    return pd.DataFrame(records)


def compute_atlas_stats(df: pd.DataFrame) -> dict:
    """
    Calcule les statistiques globales pour calibration Gaea

    Args:
        df: DataFrame atlas

    Returns:
        Dictionnaire avec statistiques globales
    """
    if len(df) == 0:
        return {}

    # Percentile 90 des pentes max
    slope_max_p90 = float(df['slope_max'].quantile(0.90))

    # % surface globale > 25° (versants raides + falaises)
    pct_steep = float(df['pct_25_35'].mean() + df['pct_35_plus'].mean())

    # Stats courbure et zones marines
    slope_p90_global = float(df['slope_p90'].quantile(0.90))
    curv_convex_global = float(df['curv_convex'].mean())
    curv_concave_global = float(df['curv_concave'].mean())
    curv_mean_global = float(df['curv_mean'].mean())
    tiles_with_underwater = int((df['pct_underwater'] > 0).sum())
    tiles_100pct_marine = int((df['pct_underwater'] > 99).sum())
    pct_underwater_total = float(df['pct_underwater'].mean())

    return {
        "num_tiles": len(df),
        "alt_min_global": float(df['alt_min'].min()),
        "alt_max_global": float(df['alt_max'].max()),
        "alt_range": float(df['alt_max'].max() - df['alt_min'].min()),
        "tiles_with_sea": int(df['has_sea'].sum()),
        "slope_max_global": float(df['slope_max'].max()),
        "slope_max_p90": slope_max_p90,
        "slope_p90_global": slope_p90_global,
        "slope_mean_global": float(df['slope_mean'].mean()),
        "pct_0_5_global": float(df['pct_0_5'].mean()),
        "pct_5_15_global": float(df['pct_5_15'].mean()),
        "pct_15_25_global": float(df['pct_15_25'].mean()),
        "pct_25_35_global": float(df['pct_25_35'].mean()),
        "pct_35_plus_global": float(df['pct_35_plus'].mean()),
        "pct_steep_global": pct_steep,
        "curv_convex_global": curv_convex_global,
        "curv_concave_global": curv_concave_global,
        "curv_mean_global": curv_mean_global,
        "tiles_with_underwater": tiles_with_underwater,
        "tiles_100pct_marine": tiles_100pct_marine,
        "pct_underwater_total": pct_underwater_total,
    }


def display_atlas_stats(stats: dict) -> str:
    """
    Formate les statistiques globales en texte

    Args:
        stats: Dictionnaire statistiques

    Returns:
        Texte formaté
    """
    if not stats:
        return "Aucune donnée"

    lines = []
    lines.append("=== ATLAS MÉTRIQUE ===")
    lines.append(f"Tuiles analysées : {stats['num_tiles']}")
    lines.append("")
    lines.append("ALTITUDES (mètres réels, float32) :")
    lines.append(f"  min global  : {stats['alt_min_global']:.1f} m")
    lines.append(f"  max global  : {stats['alt_max_global']:.1f} m")
    lines.append(f"  amplitude   : {stats['alt_range']:.1f} m")
    lines.append(f"  tuiles marines (alt_min < 0) : {stats['tiles_with_sea']}")
    lines.append("")
    lines.append("PENTES — CALIBRATION GAEA :")
    lines.append(f"  pente max globale   : {stats['slope_max_global']:.1f}°")
    lines.append(f"  pente p90 globale   : {stats['slope_p90_global']:.1f}°  ← seuil haut Gaea recommandé")
    lines.append(f"  pente moy globale   : {stats['slope_mean_global']:.1f}°")
    lines.append(f"  % surface > 25°     : {stats['pct_steep_global']:.1f}%  ← surface rocheuse potentielle")
    lines.append("")
    lines.append("DISTRIBUTION GLOBALE DES PENTES :")

    for key, label in [
        ("pct_0_5_global", "  0°–5°   (plat)      "),
        ("pct_5_15_global", "  5°–15°  (collines)  "),
        ("pct_15_25_global", " 15°–25°  (versants)  "),
        ("pct_25_35_global", " 25°–35°  (raides)    "),
        ("pct_35_plus_global", " 35°+     (falaises)  "),
    ]:
        pct = stats[key]
        bar = "█" * int(pct / 2)
        lines.append(f"  {label}: {pct:5.1f}%  {bar}")

    lines.append("")
    lines.append("COURBURE (crêtes / talwegs) :")
    lines.append(f"  % crêtes convexes   : {stats['curv_convex_global']:.1f}%  ← zones d'affleurement rocheux")
    lines.append(f"  % talwegs concaves  : {stats['curv_concave_global']:.1f}%  ← zones Dirt/érosion")
    lines.append(f"  courbure moy carte  : {stats['curv_mean_global']:.4f}")
    lines.append("")
    lines.append("ZONES MARINES :")
    lines.append(f"  tuiles avec mer     : {stats['tiles_with_underwater']} tuiles")
    lines.append(f"  tuiles 100% marines : {stats['tiles_100pct_marine']} tuiles")
    lines.append(f"  % surface totale    : {stats['pct_underwater_total']:.1f}%")
    lines.append("")
    lines.append("=== CALIBRATION GAEA ===")
    lines.append(f"  Pente max globale      : {stats['slope_max_global']:.1f}°")
    lines.append(f"  Pente max P90          : {stats['slope_max_p90']:.1f}°")
    lines.append(f"  % surface raides (>25°): {stats['pct_steep_global']:.1f}%")

    return "\n".join(lines)
