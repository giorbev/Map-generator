#!/usr/bin/env python3
"""
merge_bathymetry.py
Fusionne une heightmap Reforger avec des données bathymétriques EMODNET.

Usage:
    python merge_bathymetry.py

Fichiers requis dans le même répertoire :
    - normandie_t.asc : heightmap Reforger
    - Mean_depth_natural_colour__with_land_.asc : données EMODNET
"""

import ast
import sys
from pathlib import Path
import numpy as np
from scipy.interpolate import RegularGridInterpolator


# Configuration
INPUT_REFORGER = "normandie_t.asc"
INPUT_EMODNET = "Mean_depth_natural_colour__with_land_.asc"
OUTPUT_FILE = "normandie_batho.asc"

# Bounds géographiques de normandie_t.asc
SW_LON = -1.2000
SW_LAT = 49.3167
CELLSIZE_M = 6.221514
# Conversion en degrés
CELL_LAT_DEG = CELLSIZE_M / 111320.0  # 0.0000559°
CELL_LON_DEG = CELLSIZE_M / (111320.0 * np.cos(np.radians(49.36)))  # 0.0000858°


def syntax_check():
    """Vérifie la syntaxe du script lui-même."""
    print("[INIT] Vérification syntaxe du script...")
    try:
        with open(__file__, 'r', encoding='utf-8') as f:
            ast.parse(f.read())
        print("[OK] Syntaxe valide\n")
    except SyntaxError as e:
        print(f"[ERREUR] Syntaxe invalide : {e}")
        sys.exit(1)


def parse_emodnet(filepath):
    """
    Parse le fichier EMODNET au format OPeNDAP ASCII.

    Returns:
        tuple: (latitudes, longitudes, elevation_data)
            - latitudes: array 1D (230,)
            - longitudes: array 1D (649,)
            - elevation_data: array 2D (230, 649)
    """
    print(f"[PARSE] Lecture EMODNET : {filepath}")

    with open(filepath, 'r') as f:
        content = f.read()

    lines = content.split('\n')

    # Trouver les sections
    lat_start = None
    lon_start = None
    elev_start = None
    elev_end = None

    for i, line in enumerate(lines):
        if 'elevation.latitude[230]' in line:
            lat_start = i + 1
        elif 'elevation.longitude[649]' in line:
            lon_start = i + 1
        elif 'elevation.elevation[230][649]' in line:
            elev_start = i + 1
        elif 'value_count.value_count' in line and elev_start is not None:
            elev_end = i
            break

    if None in (lat_start, lon_start, elev_start, elev_end):
        raise ValueError("Structure EMODNET non reconnue")

    # Parser latitudes
    lat_data = []
    i = lat_start
    while i < lon_start - 1:
        line = lines[i].strip()
        if line and not line.startswith('['):
            lat_data.extend([float(x.strip()) for x in line.replace(',', ' ').split() if x.strip()])
        i += 1
    latitudes = np.array(lat_data[:230])
    print(f"[OK] Latitudes : {len(latitudes)} points, range [{latitudes.min():.4f}, {latitudes.max():.4f}]")

    # Parser longitudes
    lon_data = []
    i = lon_start
    while i < elev_start - 1:
        line = lines[i].strip()
        if line and not line.startswith('['):
            lon_data.extend([float(x.strip()) for x in line.replace(',', ' ').split() if x.strip()])
        i += 1
    longitudes = np.array(lon_data[:649])
    print(f"[OK] Longitudes : {len(longitudes)} points, range [{longitudes.min():.4f}, {longitudes.max():.4f}]")

    # Parser elevation (230 rows × 649 cols)
    elev_data = []
    for i in range(elev_start, elev_end):
        line = lines[i].strip()
        if line.startswith('['):
            # Supprimer le préfixe [N],
            line = line.split(',', 1)[1] if ',' in line else ''
        if line:
            values = [float(x.strip()) for x in line.replace(',', ' ').split() if x.strip()]
            elev_data.extend(values)

    elevation = np.array(elev_data).reshape(230, 649)
    print(f"[OK] Elevation : shape {elevation.shape}, range [{elevation.min():.2f}, {elevation.max():.2f}] m")
    print()

    return latitudes, longitudes, elevation


def read_asc_header(filepath):
    """Lit le header d'un fichier ASC."""
    header = {}
    with open(filepath, 'r') as f:
        for i in range(6):
            line = f.readline().strip()
            key, value = line.split(None, 1)
            header[key.lower()] = float(value) if '.' in value or 'e' in value.lower() else int(value)
    return header


def read_asc_data(filepath):
    """
    Lit un fichier ASC Reforger.

    Returns:
        tuple: (header, data)
    """
    print(f"[READ] Lecture heightmap Reforger : {filepath}")

    header = read_asc_header(filepath)
    print(f"[OK] Dimensions : {header['ncols']} × {header['nrows']}")
    print(f"[OK] Cellsize : {header['cellsize']} m")
    print(f"[OK] Origin : ({header['xllcorner']}, {header['yllcorner']})")
    print(f"[OK] Nodata : {header['nodata_value']}")

    # Charger les données (skip 6 lignes de header)
    data = np.loadtxt(filepath, skiprows=6, dtype=np.float32)

    # Statistiques
    valid_mask = data != header['nodata_value']
    sea_mask = (data == 0.0) & valid_mask
    land_mask = (data > 0.0) & valid_mask

    print(f"[OK] Pixels mer (=0) : {sea_mask.sum():,}")
    print(f"[OK] Pixels terre (>0) : {land_mask.sum():,}, range [{data[land_mask].min():.2f}, {data[land_mask].max():.2f}] m")
    print(f"[OK] Pixels nodata : {(~valid_mask).sum():,}")
    print()

    return header, data


def create_reforger_coords(header):
    """
    Crée les grilles de coordonnées géographiques pour chaque pixel.

    Returns:
        tuple: (lons, lats) - arrays 2D de même shape que la heightmap
    """
    print("[COORDS] Création grille géographique Reforger...")

    ncols = header['ncols']
    nrows = header['nrows']

    # Grilles de longitude et latitude (coin inférieur gauche = xllcorner, yllcorner)
    # En ASC, row 0 = top (nord), donc on inverse lat
    lon_1d = SW_LON + np.arange(ncols) * CELL_LON_DEG
    lat_1d = SW_LAT + np.arange(nrows) * CELL_LAT_DEG
    lat_1d = lat_1d[::-1]  # Inverser : row 0 = nord

    lons, lats = np.meshgrid(lon_1d, lat_1d)

    print(f"[OK] Lon range : [{lons.min():.4f}, {lons.max():.4f}]")
    print(f"[OK] Lat range : [{lats.min():.4f}, {lats.max():.4f}]")
    print()

    return lons, lats


def interpolate_emodnet(emodnet_lats, emodnet_lons, emodnet_elev, target_lons, target_lats):
    """
    Interpole les données EMODNET sur la grille cible.

    Returns:
        np.ndarray: données interpolées, même shape que target_lons/lats
    """
    print("[INTERP] Interpolation EMODNET sur grille Reforger...")

    # Vérifier l'ordre des axes (croissant requis pour RegularGridInterpolator)
    if emodnet_lats[0] > emodnet_lats[-1]:
        print("[INFO] EMODNET lat décroissant, inversion...")
        emodnet_lats = emodnet_lats[::-1]
        emodnet_elev = emodnet_elev[::-1, :]

    if emodnet_lons[0] > emodnet_lons[-1]:
        print("[INFO] EMODNET lon décroissant, inversion...")
        emodnet_lons = emodnet_lons[::-1]
        emodnet_elev = emodnet_elev[:, ::-1]

    # Créer l'interpolateur (lat, lon) -> elevation
    interpolator = RegularGridInterpolator(
        (emodnet_lats, emodnet_lons),
        emodnet_elev,
        method='linear',
        bounds_error=False,
        fill_value=None  # Extrapolation
    )

    # Points cibles (N × 2 array)
    points = np.stack([target_lats.ravel(), target_lons.ravel()], axis=-1)

    # Interpoler
    interpolated = interpolator(points).reshape(target_lats.shape)

    valid_count = np.isfinite(interpolated).sum()
    print(f"[OK] Interpolation complète : {valid_count:,} / {interpolated.size:,} pixels valides")

    if valid_count > 0:
        valid_vals = interpolated[np.isfinite(interpolated)]
        print(f"[OK] Valeurs interpolées : range [{valid_vals.min():.2f}, {valid_vals.max():.2f}] m")
    print()

    return interpolated


def merge_bathymetry(reforger_data, emodnet_interp, nodata_value):
    """
    Fusionne les données : remplace les pixels mer (=0) par EMODNET.

    Returns:
        tuple: (merged_data, stats_dict)
    """
    print("[MERGE] Fusion bathymétrie...")

    merged = reforger_data.copy()

    # Masque mer = pixels à 0.0 (et pas nodata)
    sea_mask = (reforger_data == 0.0) & (reforger_data != nodata_value)

    # Sur les pixels mer, injecter EMODNET
    sea_emodnet = emodnet_interp[sea_mask]
    valid_emodnet = np.isfinite(sea_emodnet)

    # Remplacer
    merged[sea_mask] = emodnet_interp[sea_mask]

    # Sécurité : forcer les valeurs positives sur mer à -1.0
    positive_on_sea = sea_mask & (merged >= 0.0)
    if positive_on_sea.sum() > 0:
        print(f"[WARN] {positive_on_sea.sum():,} pixels mer avec EMODNET >=0, forcés à -1.0")
        merged[positive_on_sea] = -1.0

    # Statistiques
    replaced_count = sea_mask.sum()
    valid_replaced = valid_emodnet.sum()
    depths = merged[sea_mask & np.isfinite(merged)]

    stats = {
        'replaced_count': replaced_count,
        'valid_replaced': valid_replaced,
        'min_depth': depths.min() if len(depths) > 0 else 0.0,
        'max_depth': depths.max() if len(depths) > 0 else 0.0,
    }

    print(f"[OK] Pixels mer remplacés : {replaced_count:,}")
    print(f"[OK] Pixels avec EMODNET valide : {valid_replaced:,}")
    if len(depths) > 0:
        print(f"[OK] Profondeurs injectées : [{stats['min_depth']:.2f}, {stats['max_depth']:.2f}] m")
    print()

    return merged, stats


def write_asc(filepath, header, data):
    """Écrit un fichier ASC."""
    print(f"[WRITE] Écriture fichier : {filepath}")

    with open(filepath, 'w') as f:
        # Header
        f.write(f"ncols        {header['ncols']}\n")
        f.write(f"nrows        {header['nrows']}\n")
        f.write(f"xllcorner    {header['xllcorner']}\n")
        f.write(f"yllcorner    {header['yllcorner']}\n")
        f.write(f"cellsize     {header['cellsize']}\n")
        f.write(f"NODATA_value {header['nodata_value']}\n")

        # Data (3 décimales)
        for row in data:
            line = ' '.join(f"{val:.3f}" for val in row)
            f.write(line + '\n')

    abs_path = Path(filepath).resolve()
    print(f"[OK] Fichier écrit : {abs_path}")
    print()


def main():
    """Point d'entrée principal."""
    syntax_check()

    # Vérifier la présence des fichiers d'entrée
    if not Path(INPUT_REFORGER).exists():
        print(f"[ERREUR] Fichier introuvable : {INPUT_REFORGER}")
        sys.exit(1)
    if not Path(INPUT_EMODNET).exists():
        print(f"[ERREUR] Fichier introuvable : {INPUT_EMODNET}")
        sys.exit(1)

    print("=" * 70)
    print("FUSION BATHYMÉTRIE EMODNET → REFORGER")
    print("=" * 70)
    print()

    # 1. Parser EMODNET
    emodnet_lats, emodnet_lons, emodnet_elev = parse_emodnet(INPUT_EMODNET)

    # 2. Lire Reforger
    header, reforger_data = read_asc_data(INPUT_REFORGER)

    # 3. Créer grille géographique Reforger
    target_lons, target_lats = create_reforger_coords(header)

    # 4. Interpoler EMODNET
    emodnet_interp = interpolate_emodnet(emodnet_lats, emodnet_lons, emodnet_elev, target_lons, target_lats)

    # 5. Fusion
    merged_data, stats = merge_bathymetry(reforger_data, emodnet_interp, header['nodata_value'])

    # 6. Dry-run + confirmation
    print("=" * 70)
    print("DRY-RUN : RÉCAPITULATIF")
    print("=" * 70)
    print(f"Pixels mer remplacés      : {stats['replaced_count']:,}")
    print(f"EMODNET valides injectés  : {stats['valid_replaced']:,}")
    print(f"Profondeurs min/max       : [{stats['min_depth']:.2f}, {stats['max_depth']:.2f}] m")
    print(f"Fichier de sortie         : {OUTPUT_FILE}")
    print()

    response = input("Écrire le fichier ? (y/n) : ").strip().lower()
    if response != 'y':
        print("[ANNULÉ] Aucun fichier écrit.")
        sys.exit(0)

    print()

    # 7. Écrire
    write_asc(OUTPUT_FILE, header, merged_data)

    print("=" * 70)
    print("FUSION TERMINÉE")
    print("=" * 70)


if __name__ == '__main__':
    main()
