# -*- coding: utf-8 -*-
"""
Auto-calibration des seuils de biome selon les caractéristiques de la carte

Analyse le terrain (altitude, slope) et calibre automatiquement :
- Zone côtière (0-20m par défaut)
- Lowland/Midland/Highland (stratification 1/3)
- Conversion mètres -> normalisé selon carte

Usage:
    from biome_calibration import auto_calibrate_biome

    calibration = auto_calibrate_biome('data/projects/Zbk_island')
    print(calibration['coastal'])  # Seuils zone côtière
"""

import json
import numpy as np
import cv2
from pathlib import Path


def load_project_data(project_path):
    """Charge les données du projet (heightmap, slope, stats)"""
    project_path = Path(project_path)

    # Charger project.json
    project_json = project_path / "project.json"
    if not project_json.exists():
        raise FileNotFoundError(f"project.json non trouvé : {project_json}")

    with open(project_json, 'r', encoding='utf-8') as f:
        project_data = json.load(f)

    # Charger heightmap
    heightmap_filename = project_data['assets']['heightmap']['filename']
    heightmap_path = project_path / "sources" / heightmap_filename
    if heightmap_path.suffix == '.asc':
        heightmap = np.loadtxt(heightmap_path, skiprows=6).astype(np.float32)
    else:
        heightmap = cv2.imread(str(heightmap_path), cv2.IMREAD_UNCHANGED)
        if heightmap is None:
            raise FileNotFoundError(f"Heightmap non trouvée : {heightmap_path}")
        heightmap = heightmap.astype(np.float32)

    # Charger slope
    slope_path = project_path / "sources" / "slope.png"
    if slope_path.exists():
        slope = cv2.imread(str(slope_path), cv2.IMREAD_UNCHANGED)
        if slope.shape != heightmap.shape:
            slope = cv2.resize(slope, (heightmap.shape[1], heightmap.shape[0]), interpolation=cv2.INTER_LINEAR)
        slope_deg = slope.astype(np.float32) / 65535.0 * 90.0
    else:
        slope_deg = None

    return heightmap, slope_deg, project_data


def analyze_terrain(heightmap, slope_deg=None):
    """Analyse le terrain et retourne les statistiques"""
    stats = {}

    # Stats altitude
    stats['altitude'] = {
        'min': float(np.min(heightmap)),
        'max': float(np.max(heightmap)),
        'mean': float(np.mean(heightmap)),
        'p10': float(np.percentile(heightmap, 10)),
        'p25': float(np.percentile(heightmap, 25)),
        'p50': float(np.percentile(heightmap, 50)),
        'p75': float(np.percentile(heightmap, 75)),
        'p90': float(np.percentile(heightmap, 90)),
        'p95': float(np.percentile(heightmap, 95)),
    }

    stats['altitude']['range'] = stats['altitude']['max'] - stats['altitude']['min']

    # Détecter niveau mer (P50)
    sea_level = stats['altitude']['p50']
    stats['sea_level'] = float(sea_level)

    # Analyser terre émergée
    land_mask = heightmap > sea_level
    if np.sum(land_mask) > 0:
        land_altitudes = heightmap[land_mask]
        stats['land'] = {
            'min': float(np.min(land_altitudes)),
            'max': float(np.max(land_altitudes)),
            'p10': float(np.percentile(land_altitudes, 10)),
            'p33': float(np.percentile(land_altitudes, 33)),
            'p50': float(np.percentile(land_altitudes, 50)),
            'p66': float(np.percentile(land_altitudes, 66)),
            'p90': float(np.percentile(land_altitudes, 90)),
        }
    else:
        # Pas de terre émergée (carte sous-marine)
        stats['land'] = stats['altitude'].copy()

    # Analyser terre AU-DESSUS de 0m absolu (pour zone côtière auto)
    land_above_0 = heightmap[heightmap > 0]
    if len(land_above_0) > 0:
        stats['land_above_0'] = {
            'min': float(np.min(land_above_0)),
            'max': float(np.max(land_above_0)),
            'p10': float(np.percentile(land_above_0, 10)),
            'p15': float(np.percentile(land_above_0, 15)),
            'p20': float(np.percentile(land_above_0, 20)),
        }
    else:
        # Carte entièrement sous l'eau (très rare)
        stats['land_above_0'] = None

    # Stats slope
    if slope_deg is not None:
        stats['slope'] = {
            'min': float(np.min(slope_deg)),
            'max': float(np.max(slope_deg)),
            'mean': float(np.mean(slope_deg)),
            'p10': float(np.percentile(slope_deg, 10)),
            'p25': float(np.percentile(slope_deg, 25)),
            'p50': float(np.percentile(slope_deg, 50)),
            'p75': float(np.percentile(slope_deg, 75)),
            'p90': float(np.percentile(slope_deg, 90)),
            'p95': float(np.percentile(slope_deg, 95)),
        }

    return stats


def auto_calibrate_biome(project_path, coastal_max_meters=20, lowland_percentile=33, midland_percentile=66):
    """
    Auto-calibre les seuils de biome selon la carte.

    Analyse le terrain et retourne des seuils adaptés :
    - Zone côtière : 0-20m (ou personnalisé)
    - Lowland : 0-P33 terre émergée
    - Midland : P33-P66 terre émergée
    - Highland : >P66 terre émergée

    Args:
        project_path: Chemin vers le projet
        coastal_max_meters: Altitude max zone côtière en mètres (défaut 20m)
        lowland_percentile: Percentile pour seuil lowland/midland (défaut 33%)
        midland_percentile: Percentile pour seuil midland/highland (défaut 66%)

    Returns:
        dict: Seuils calibrés avec :
            - altitude_min/max_meters (mètres absolus)
            - altitude_min/max_norm (normalisé 0-1)
            - metadata (stats terrain)
    """
    print("=" * 80)
    print("AUTO-CALIBRATION BIOME")
    print("=" * 80)

    # Charger données
    heightmap, slope_deg, project_data = load_project_data(project_path)
    print(f"\nCarte chargee : {heightmap.shape}")

    # Analyser
    stats = analyze_terrain(heightmap, slope_deg)

    print(f"\nSTATISTIQUES TERRAIN")
    print(f"   Altitude min : {stats['altitude']['min']:.2f}m")
    print(f"   Altitude max : {stats['altitude']['max']:.2f}m")
    print(f"   Range        : {stats['altitude']['range']:.2f}m")
    print(f"   Niveau mer   : {stats['sea_level']:.2f}m (P50)")

    if 'land' in stats:
        print(f"\nTERRE EMERGEE (> niveau mer)")
        print(f"   Min          : {stats['land']['min']:.2f}m")
        print(f"   Max          : {stats['land']['max']:.2f}m")
        print(f"   P10          : {stats['land']['p10']:.2f}m")
        print(f"   P33          : {stats['land']['p33']:.2f}m")
        print(f"   P66          : {stats['land']['p66']:.2f}m")

    if stats.get('land_above_0'):
        print(f"\nTERRE > 0m (pour zone cotiere)")
        print(f"   P10          : {stats['land_above_0']['p10']:.2f}m")
        print(f"   P15          : {stats['land_above_0']['p15']:.2f}m")
        print(f"   P20          : {stats['land_above_0']['p20']:.2f}m")

    if 'slope' in stats:
        print(f"\nPENTES")
        print(f"   P75          : {stats['slope']['p75']:.1f} deg")
        print(f"   P90          : {stats['slope']['p90']:.1f} deg")

    # Calibrer seuils
    calibration = {
        'metadata': {
            'project': str(project_path),
            'terrain_stats': stats,
            'parameters': {
                'coastal_max_meters': coastal_max_meters,
                'lowland_percentile': lowland_percentile,
                'midland_percentile': midland_percentile,
            }
        }
    }

    min_alt = stats['altitude']['min']
    alt_range = stats['altitude']['range']

    # Helper pour convertir mètres -> normalisé
    def meters_to_norm(meters):
        return (meters - min_alt) / alt_range

    # Zone côtière : AUTO-CALIBRÉE via P10 terre > 0m
    # (10% terre la plus basse AU-DESSUS de 0m = zone côtière naturelle)
    coastal_min = max(0, stats['sea_level'])  # Au-dessus niveau mer

    if stats['land_above_0'] is not None:
        coastal_max = stats['land_above_0']['p10']  # P10 terre > 0m (auto selon carte)
    else:
        # Fallback : carte sous l'eau, utiliser seuil fixe
        coastal_max = 20.0

    calibration['coastal'] = {
        'altitude_min_meters': coastal_min,
        'altitude_max_meters': coastal_max,
        'altitude_min_norm': meters_to_norm(coastal_min),
        'altitude_max_norm': meters_to_norm(coastal_max),
        'auto_calibrated': True,  # Marqueur auto-calibration
    }

    # Zones herbeuses (stratification TERRE AU-DESSUS DE 0m)
    # On ne veut pas stratifier les zones sous l'eau
    land_above_0 = heightmap[heightmap > 0]
    if len(land_above_0) > 0:
        lowland_max = float(np.percentile(land_above_0, lowland_percentile))
        midland_max = float(np.percentile(land_above_0, midland_percentile))
        highland_min = midland_max
    else:
        # Fallback si pas de terre > 0m
        lowland_max = stats['land'][f'p{lowland_percentile}']
        midland_max = stats['land'][f'p{midland_percentile}']
        highland_min = midland_max

    calibration['lowland'] = {
        'altitude_min_meters': coastal_min,
        'altitude_max_meters': lowland_max,
        'altitude_min_norm': meters_to_norm(coastal_min),
        'altitude_max_norm': meters_to_norm(lowland_max),
    }

    calibration['midland'] = {
        'altitude_min_meters': lowland_max,
        'altitude_max_meters': midland_max,
        'altitude_min_norm': meters_to_norm(lowland_max),
        'altitude_max_norm': meters_to_norm(midland_max),
    }

    calibration['highland'] = {
        'altitude_min_meters': highland_min,
        'altitude_max_meters': stats['land']['max'],
        'altitude_min_norm': meters_to_norm(highland_min),
        'altitude_max_norm': meters_to_norm(stats['land']['max']),
    }

    print(f"\nSEUILS CALIBRES")
    print(f"\n   CÔTE")
    print(f"   {calibration['coastal']['altitude_min_meters']:.1f}-{calibration['coastal']['altitude_max_meters']:.1f}m")
    print(f"   ({calibration['coastal']['altitude_min_norm']:.3f}-{calibration['coastal']['altitude_max_norm']:.3f} norm)")

    print(f"\n   LOWLAND")
    print(f"   {calibration['lowland']['altitude_min_meters']:.1f}-{calibration['lowland']['altitude_max_meters']:.1f}m")
    print(f"   ({calibration['lowland']['altitude_min_norm']:.3f}-{calibration['lowland']['altitude_max_norm']:.3f} norm)")

    print(f"\n   MIDLAND")
    print(f"   {calibration['midland']['altitude_min_meters']:.1f}-{calibration['midland']['altitude_max_meters']:.1f}m")
    print(f"   ({calibration['midland']['altitude_min_norm']:.3f}-{calibration['midland']['altitude_max_norm']:.3f} norm)")

    print(f"\n   HIGHLAND")
    print(f"   {calibration['highland']['altitude_min_meters']:.1f}-{calibration['highland']['altitude_max_meters']:.1f}m")
    print(f"   ({calibration['highland']['altitude_min_norm']:.3f}-{calibration['highland']['altitude_max_norm']:.3f} norm)")

    print("\n" + "=" * 80)

    return calibration


if __name__ == "__main__":
    # Test sur ZBK
    calibration = auto_calibrate_biome('data/projects/Zbk_island')

    # Sauvegarder
    output = Path('data/projects/Zbk_island/calibration.json')
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(calibration, f, indent=2, ensure_ascii=False)

    print(f"\nCalibration sauvegardee : {output}")
