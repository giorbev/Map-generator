"""
Vegetation Polyline Exporter
Converts VPN biome masks to Enfusion Workbench PolylineShapeEntity .layer files.

Usage:
    from naturemap_biomes_generator import NatureMapBiomesGenerator
    from vegetation_polyline_exporter import VegetationPolylineExporter

    gen = NatureMapBiomesGenerator("input/mymap.asc")
    gen.generate_vpn(profile='europe_temperee')  # stocke gen.vpn_masks

    exporter = VegetationPolylineExporter(gen, output_dir="output/vegetation")
    report = exporter.export_all(
        min_area=500,        # filtre contours < 500 px² (~500 m²)
        epsilon_factor=0.005 # simplification Douglas-Peucker
    )

Output:
    output/vegetation/
        Foret_mixte_de_plaine.layer
        Hetraie_chenaie_ubac.layer
        ...
        vegetation_export_report.json
"""

import os
import json
import random
import cv2
import numpy as np
from datetime import datetime


# Biomes purement cartographiques — pas de polylines utiles pour la végétation
_SKIP_BIOMES = {"Eau interieure", "Ocean / hors emprise"}


class VegetationPolylineExporter:
    """
    Génère des fichiers .layer Enfusion à partir des masks VPN.
    Chaque biome → 1 fichier .layer contenant N PolylineShapeEntity fermées.
    """

    def __init__(self, biome_generator, output_dir="output/vegetation"):
        """
        Args:
            biome_generator : instance NatureMapBiomesGenerator
                              (generate_vpn() doit avoir été appelé avant)
            output_dir      : répertoire de sortie pour les fichiers .layer
        """
        self.gen        = biome_generator
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # Résolution spatiale : mètres par pixel
        self.cell_size = float(getattr(biome_generator, 'cellsize', 1.0))

    # ──────────────────────────────────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────────────────────────────────

    def export_all(self, min_area=500, epsilon_factor=0.005):
        """
        Exporte tous les biomes VPN disponibles en fichiers .layer.

        Args:
            min_area       : surface minimale d'un contour en pixels²
                             (défaut 500 px = ~500 m² pour cellsize=1m)
            epsilon_factor : facteur de simplification Douglas-Peucker
                             (0.005 = 0.5% du périmètre du contour)

        Returns:
            dict  rapport complet (biomes traités, stats par biome)
        """
        if not hasattr(self.gen, 'vpn_masks') or not self.gen.vpn_masks:
            raise RuntimeError(
                "vpn_masks non disponibles. Appelez d'abord generate_vpn()."
            )

        vpn_masks = self.gen.vpn_masks
        profile   = getattr(self.gen, 'vpn_profile', 'unknown')

        report = {
            'profile':     profile,
            'cell_size_m': self.cell_size,
            'min_area_px': min_area,
            'epsilon_factor': epsilon_factor,
            'exported_at': datetime.now().isoformat(timespec='seconds'),
            'biomes': {}
        }

        total_splines = 0
        for biome_name, mask in vpn_masks.items():
            if biome_name in _SKIP_BIOMES:
                continue

            contours = self._extract_contours(mask, min_area, epsilon_factor)
            if not contours:
                print(f"[VPE] {biome_name}: aucun contour valide (ignoré)")
                continue

            layer_text = self._build_layer_file(contours)
            safe_name  = _safe_filename(biome_name)
            layer_path = os.path.join(self.output_dir, f"{safe_name}.layer")

            with open(layer_path, 'w', encoding='utf-8') as f:
                f.write(layer_text)

            total_splines += len(contours)
            report['biomes'][biome_name] = {
                'file':         f"{safe_name}.layer",
                'num_splines':  len(contours),
                'areas_px2':    [int(cv2.contourArea(c)) for c in contours],
            }
            print(f"[VPE] {biome_name}: {len(contours)} splines → {layer_path}")

        report['total_splines'] = total_splines

        # Rapport JSON
        report_path = os.path.join(self.output_dir, 'vegetation_export_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n[VPE] Export terminé : {total_splines} splines dans {self.output_dir}")
        return report

    def export_single(self, biome_name, min_area=500, epsilon_factor=0.005):
        """
        Exporte un seul biome par son nom.

        Returns:
            (str chemin fichier .layer, int nb splines)
        """
        if not hasattr(self.gen, 'vpn_masks') or biome_name not in self.gen.vpn_masks:
            raise ValueError(f"Biome '{biome_name}' non disponible dans vpn_masks.")

        mask     = self.gen.vpn_masks[biome_name]
        contours = self._extract_contours(mask, min_area, epsilon_factor)

        layer_text = self._build_layer_file(contours)
        safe_name  = _safe_filename(biome_name)
        layer_path = os.path.join(self.output_dir, f"{safe_name}.layer")

        with open(layer_path, 'w', encoding='utf-8') as f:
            f.write(layer_text)

        print(f"[VPE] {biome_name}: {len(contours)} splines → {layer_path}")
        return layer_path, len(contours)

    # ──────────────────────────────────────────────────────────────────────
    # Extraction de contours
    # ──────────────────────────────────────────────────────────────────────

    def _extract_contours(self, mask_bool, min_area, epsilon_factor):
        """
        Extrait les contours d'un mask booléen.

        Steps:
          1. Fermeture morphologique pour boucher les petits trous
          2. cv2.findContours (contours extérieurs seulement)
          3. Filtre par surface minimale
          4. Simplification Douglas-Peucker

        Returns:
            list de np.ndarray (N, 1, 2) — format OpenCV
        """
        # uint8 pour OpenCV
        img = (mask_bool.astype(np.uint8)) * 255

        # Fermeture morphologique: comble les petits trous internes
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        img    = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(
            img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        result = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue

            # Douglas-Peucker : epsilon = epsilon_factor * périmètre
            perimeter = cv2.arcLength(cnt, closed=True)
            epsilon   = epsilon_factor * perimeter
            simplified = cv2.approxPolyDP(cnt, epsilon, closed=True)

            # Minimum 3 points pour former un polygone fermé
            if len(simplified) >= 3:
                result.append(simplified)

        # Trier du plus grand au plus petit (esthétique dans Workbench)
        result.sort(key=lambda c: cv2.contourArea(c), reverse=True)
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Génération du format Enfusion .layer
    # ──────────────────────────────────────────────────────────────────────

    def _build_layer_file(self, contours):
        """
        Construit le texte complet d'un fichier .layer Enfusion
        à partir d'une liste de contours OpenCV.
        """
        entities = [self._polyline_entity(cnt) for cnt in contours]
        return '\n'.join(entities) + '\n'

    def _polyline_entity(self, contour):
        """
        Génère 1 PolylineShapeEntity fermée depuis un contour OpenCV.

        Coordonnées Enfusion :
          world_x = pixel_col * cell_size
          world_z = pixel_row * cell_size
          world_y = 0  (Workbench drape sur le terrain)

        Le premier point est l'ORIGINE absolue.
        Tous les autres points sont RELATIFS à l'origine.
        Le dernier point duplique le premier pour fermer la polyline.
        """
        pts = contour.reshape(-1, 2)  # (N, 2) — (col, row)

        origin_col, origin_row = float(pts[0][0]), float(pts[0][1])
        origin_x = origin_col * self.cell_size
        origin_z = origin_row * self.cell_size

        lines = []
        lines.append('PolylineShapeEntity {')
        lines.append(f' coords {origin_x:.3f} 0 {origin_z:.3f}')
        lines.append(' Points {')

        # Premier point à l'origine (position 0 0 0)
        lines.append(f'  ShapePoint "{_random_id()}" {{')
        lines.append('   Position 0 0 0')
        lines.append('  }')

        # Points suivants — relatifs à l'origine
        for pt in pts[1:]:
            dx = (float(pt[0]) - origin_col) * self.cell_size
            dz = (float(pt[1]) - origin_row) * self.cell_size
            lines.append(f'  ShapePoint "{_random_id()}" {{')
            lines.append(f'   Position {dx:.3f} 0 {dz:.3f}')
            lines.append('  }')

        # Fermeture : répéter le premier point (Position 0 0 0)
        lines.append(f'  ShapePoint "{_random_id()}" {{')
        lines.append('   Position 0 0 0')
        lines.append('  }')

        lines.append(' }')
        lines.append('}')

        return '\n'.join(lines)


# ──────────────────────────────────────────────────────────────────────────
# Helpers module-level
# ──────────────────────────────────────────────────────────────────────────

def _random_id():
    """Génère un ID hexadécimal aléatoire 16 chiffres pour ShapePoint."""
    return "{%016X}" % random.randint(0, 2**64 - 1)


def _safe_filename(name):
    """Convertit un nom de biome en nom de fichier safe (ASCII, underscores)."""
    safe = name.strip()
    safe = safe.replace('/', '_').replace('\\', '_').replace(' ', '_')
    safe = safe.replace('(', '').replace(')', '').replace('.', '')
    # Remplacer les caractères non-ASCII par équivalents courants
    replacements = {
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'î': 'i', 'ï': 'i',
        'ô': 'o', 'ö': 'o',
        'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c', 'ñ': 'n',
    }
    for src, dst in replacements.items():
        safe = safe.replace(src, dst)
    # Garder seulement alphanum + underscore
    safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in safe)
    # Éviter les doubles underscores
    while '__' in safe:
        safe = safe.replace('__', '_')
    return safe.strip('_')
