"""
Tile Border Fixer - Correction des discontinuités entre tiles adjacentes

Permet de mixer les poids matériaux du bord d'une tile avec ceux de sa voisine,
en fonction de la pente du terrain.

Modes :
- dry-run : preview PNG + affichage terminal (défaut)
- write : réécriture du _layer.edds avec backup
"""

import json
import numpy as np
import cv2
import struct
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import sys
import shutil

# Ajouter le répertoire parent au path pour imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import modules existants
from lrs2_parser import load_lrs2_from_ttile
from scripts.edds_decoder import decode_edds_layer, extract_all_weights, pack_weights_to_pixel
from terrain_terr_reader import read_mats_from_terr


def load_bterr_heightmap(bterr_path: Path) -> Optional[np.ndarray]:
    """Charge la heightmap depuis un fichier .bterr."""
    if not bterr_path.exists():
        return None

    try:
        data = open(bterr_path, "rb").read()
        i = data.find(b"DATA")
        if i < 0:
            return None

        sz = struct.unpack_from(">I", data, i + 4)[0]
        hm = np.frombuffer(data[i + 8:i + 8 + sz], np.float32).reshape(129, 129)
        return hm.astype(np.float64)
    except Exception:
        return None


def calculate_slope_for_block(heightmap: np.ndarray, bx: int, by: int, cellsize: float = 4.0) -> float:
    """Calcule la pente moyenne (en degrés) pour un bloc 32×32."""
    x0 = bx * 32
    y0 = by * 32
    x1 = x0 + 33
    y1 = y0 + 33

    block_hm = heightmap[y0:y1, x0:x1]

    gy, gx = np.gradient(block_hm, cellsize)
    slope_rad = np.arctan(np.hypot(gx, gy))
    slope_deg = np.degrees(slope_rad)

    return float(slope_deg.mean())


def get_border_blocks(direction: str) -> List[Tuple[int, int]]:
    """
    Retourne les 4 blocs du bord selon la direction.

    Args:
        direction: 'N', 'S', 'E', 'O'

    Returns:
        Liste de (bx, by) pour les 4 blocs du bord
    """
    if direction == 'N':
        return [(0, 0), (1, 0), (2, 0), (3, 0)]
    elif direction == 'S':
        return [(0, 3), (1, 3), (2, 3), (3, 3)]
    elif direction == 'E':
        return [(3, 0), (3, 1), (3, 2), (3, 3)]
    elif direction == 'O':
        return [(0, 0), (0, 1), (0, 2), (0, 3)]
    else:
        raise ValueError(f"Direction invalide: {direction}")


def get_opposite_direction(direction: str) -> str:
    """Retourne la direction opposée."""
    opposites = {'N': 'S', 'S': 'N', 'E': 'O', 'O': 'E'}
    return opposites[direction]


def extract_border_weights(
    weights: np.ndarray,
    bx: int, by: int,
    direction: str,
    border_width: int = 4
) -> np.ndarray:
    """
    Extrait les poids du bord d'un bloc.

    Args:
        weights: Array (512, 512, 7)
        bx, by: Position du bloc (0..3)
        direction: 'N', 'S', 'E', 'O'
        border_width: Largeur du bord en pixels (4 par défaut)

    Returns:
        Array (border_width, 128, num_mats) ou (128, border_width, num_mats)
    """
    block_x0 = bx * 128
    block_y0 = by * 128

    if direction == 'N':
        # Première rangée du bloc
        return weights[block_y0:block_y0 + border_width, block_x0:block_x0 + 128, :]
    elif direction == 'S':
        # Dernière rangée du bloc
        return weights[block_y0 + 128 - border_width:block_y0 + 128, block_x0:block_x0 + 128, :]
    elif direction == 'E':
        # Dernière colonne du bloc
        return weights[block_y0:block_y0 + 128, block_x0 + 128 - border_width:block_x0 + 128, :]
    elif direction == 'O':
        # Première colonne du bloc
        return weights[block_y0:block_y0 + 128, block_x0:block_x0 + border_width, :]


def mix_weights_by_slope(
    weights_source: np.ndarray,
    weights_target: np.ndarray,
    slope: float
) -> np.ndarray:
    """
    Mixe les poids source et cible selon la pente.

    Args:
        weights_source: Poids du bord source (border_width, 128, num_mats)
        weights_target: Poids du bord cible (border_width, 128, num_mats)
        slope: Pente moyenne du bloc en degrés

    Returns:
        Poids mixés (même shape que weights_target)
    """
    # Déterminer ratio selon pente
    if slope > 20.0:
        alpha = 0.7  # 70% source, 30% cible
    elif slope > 10.0:
        alpha = 0.4  # 40% source, 60% cible
    else:
        alpha = 0.2  # 20% source, 80% cible

    # Mixer
    mixed = alpha * weights_source + (1 - alpha) * weights_target

    return mixed


def renormalize_weights(weights: np.ndarray, target_sum: int = 31) -> np.ndarray:
    """
    Renormalise les poids pour que chaque pixel somme à target_sum.

    Args:
        weights: Array (..., num_mats)
        target_sum: Somme cible (31 par défaut)

    Returns:
        Poids renormalisés
    """
    current_sum = weights.sum(axis=-1, keepdims=True)
    # Éviter division par zéro
    current_sum = np.where(current_sum > 0, current_sum, 1.0)

    normalized = (weights / current_sum) * target_sum

    # Arrondir
    normalized = np.round(normalized)

    # Clipper chaque matériau individuellement à 31
    normalized = np.clip(normalized, 0, 31)

    # Vérifier que la somme ne dépasse pas 31 et réajuster si nécessaire
    for idx in np.ndindex(normalized.shape[:-1]):
        pixel_weights = normalized[idx]
        pixel_sum = pixel_weights.sum()

        if pixel_sum > target_sum:
            # Réduire proportionnellement pour atteindre exactement target_sum
            scale_factor = target_sum / pixel_sum
            pixel_weights = np.floor(pixel_weights * scale_factor)

            # Ajuster l'arrondi pour atteindre exactement target_sum
            remainder = target_sum - pixel_weights.sum()
            if remainder > 0:
                # Distribuer le reste sur les matériaux avec les plus gros poids
                sorted_indices = np.argsort(pixel_weights)[::-1]
                for i in range(int(remainder)):
                    pixel_weights[sorted_indices[i % len(sorted_indices)]] += 1

            normalized[idx] = pixel_weights

    return normalized


def apply_border_correction(
    weights_target: np.ndarray,
    weights_source: np.ndarray,
    border_blocks: List[Tuple[int, int]],
    slopes: Dict[Tuple[int, int], float],
    direction_target: str
) -> np.ndarray:
    """
    Applique la correction de bord sur les poids de la tile cible.

    Args:
        weights_target: Poids cible (512, 512, 7)
        weights_source: Poids source (512, 512, 7)
        border_blocks: Liste des blocs à corriger
        slopes: Dict des pentes par bloc
        direction_target: Direction du bord cible ('N', 'S', 'E', 'O')

    Returns:
        Poids corrigés (512, 512, 7)
    """
    weights_corrected = weights_target.copy()
    direction_source = get_opposite_direction(direction_target)

    for bx, by in border_blocks:
        # Extraire poids du bord cible
        weights_target_border = extract_border_weights(weights_target, bx, by, direction_target)

        # Extraire poids du bord source (côté opposé)
        weights_source_border = extract_border_weights(weights_source, bx, by, direction_source)

        # Vérifier compatibilité shape
        if weights_target_border.shape[:2] != weights_source_border.shape[:2]:
            print(f"[WARN]  Bloc ({bx},{by}): shapes incompatibles, skip")
            continue

        # Mixer selon pente
        slope = slopes.get((bx, by), 0.0)
        weights_mixed = mix_weights_by_slope(weights_source_border, weights_target_border, slope)

        # Renormaliser
        weights_mixed = renormalize_weights(weights_mixed)

        # Réécrire dans weights_corrected
        block_x0 = bx * 128
        block_y0 = by * 128

        if direction_target == 'N':
            weights_corrected[block_y0:block_y0 + 4, block_x0:block_x0 + 128, :] = weights_mixed
        elif direction_target == 'S':
            weights_corrected[block_y0 + 124:block_y0 + 128, block_x0:block_x0 + 128, :] = weights_mixed
        elif direction_target == 'E':
            weights_corrected[block_y0:block_y0 + 128, block_x0 + 124:block_x0 + 128, :] = weights_mixed
        elif direction_target == 'O':
            weights_corrected[block_y0:block_y0 + 128, block_x0:block_x0 + 4, :] = weights_mixed

    # Vérification finale : s'assurer qu'aucune cellule ne dépasse 31
    print("[CHECK] Vérification somme des poids...")
    max_sum = weights_corrected.sum(axis=2).max()
    violations = (weights_corrected.sum(axis=2) > 31).sum()

    if violations > 0:
        print(f"   [WARN]  {violations} cellules dépassent 31 (max={max_sum:.1f}) — renormalisation globale")
        # Renormaliser toutes les cellules qui dépassent
        pixel_sums = weights_corrected.sum(axis=2, keepdims=True)
        mask = pixel_sums > 31
        weights_corrected = np.where(mask, weights_corrected * 31.0 / pixel_sums, weights_corrected)
        weights_corrected = np.round(weights_corrected)

        # Vérification post-correction
        max_sum_after = weights_corrected.sum(axis=2).max()
        violations_after = (weights_corrected.sum(axis=2) > 31).sum()
        print(f"   [OK] Après correction : {violations_after} violations, max={max_sum_after:.1f}")
    else:
        print(f"   [OK] Toutes les cellules ≤ 31 (max={max_sum:.1f})")

    return weights_corrected


def generate_preview_image(
    weights_before: np.ndarray,
    weights_after: np.ndarray,
    border_blocks: List[Tuple[int, int]],
    direction: str,
    output_path: Path
) -> bool:
    """
    Génère une image de preview montrant avant/après pour les 4 blocs du bord.

    Image finale : 1600×400 (4 blocs × 2 versions)
    """
    print("[RENDER] Génération preview PNG...")

    # Créer image 1600×400
    img = np.zeros((400, 1600, 3), dtype=np.uint8)

    # Fond gris
    img[:, :, :] = 40

    # Pour chaque bloc
    for i, (bx, by) in enumerate(border_blocks):
        # Position dans l'image preview (4 colonnes de 400px)
        col_x = i * 400

        # Extraire le bloc avant
        block_x0 = bx * 128
        block_y0 = by * 128
        block_before = weights_before[block_y0:block_y0 + 128, block_x0:block_x0 + 128, :].sum(axis=2)
        block_after = weights_after[block_y0:block_y0 + 128, block_x0:block_x0 + 128, :].sum(axis=2)

        # Normaliser pour affichage
        block_before_vis = (block_before / 31.0 * 255).astype(np.uint8)
        block_after_vis = (block_after / 31.0 * 255).astype(np.uint8)

        # Convertir en RGB
        block_before_rgb = cv2.cvtColor(block_before_vis, cv2.COLOR_GRAY2RGB)
        block_after_rgb = cv2.cvtColor(block_after_vis, cv2.COLOR_GRAY2RGB)

        # Redimensionner à 200×200
        block_before_resized = cv2.resize(block_before_rgb, (200, 200))
        block_after_resized = cv2.resize(block_after_rgb, (200, 200))

        # Placer dans l'image
        # Avant (haut)
        img[0:200, col_x:col_x + 200, :] = block_before_resized

        # Après (bas)
        img[200:400, col_x:col_x + 200, :] = block_after_resized

        # Labels
        cv2.putText(img, f"Bloc ({bx},{by})", (col_x + 10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(img, "AVANT", (col_x + 10, 190),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
        cv2.putText(img, "APRES", (col_x + 10, 390),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

    # Sauvegarder
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img)

    print(f"   [OK] Preview sauvegardée: {output_path}")
    return True


def print_weights_comparison(
    weights_before: np.ndarray,
    weights_after: np.ndarray,
    border_blocks: List[Tuple[int, int]],
    slopes: Dict[Tuple[int, int], float],
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    surfaces: List[str]
):
    """Affiche les poids avant/après dans le terminal pour chaque bloc."""
    print()
    print("=" * 80)
    print("COMPARAISON POIDS AVANT / APRÈS")
    print("=" * 80)

    for bx, by in border_blocks:
        slope = slopes.get((bx, by), 0.0)
        mat_ids = lrs2_blocks.get((bx, by), [])

        print(f"\nBloc ({bx},{by}) - Pente: {slope:.1f}° - {len(mat_ids)} matériaux")

        # Calculer poids moyens du bloc avant/après
        block_x0 = bx * 128
        block_y0 = by * 128

        weights_block_before = weights_before[block_y0:block_y0 + 128, block_x0:block_x0 + 128, :]
        weights_block_after = weights_after[block_y0:block_y0 + 128, block_x0:block_x0 + 128, :]

        avg_before = weights_block_before.mean(axis=(0, 1))
        avg_after = weights_block_after.mean(axis=(0, 1))

        print("  Poids moyens par matériau (sur 31):")
        for i, mat_id in enumerate(mat_ids[:7]):
            if avg_before[i] > 0.01 or avg_after[i] > 0.01:
                # Obtenir le nom du matériau
                mat_name = surfaces[mat_id] if mat_id < len(surfaces) else f"MAT_{mat_id}"
                delta = avg_after[i] - avg_before[i]
                sign = "+" if delta >= 0 else ""
                print(f"    [{i}] {mat_name:25s}: {avg_before[i]:5.2f} → {avg_after[i]:5.2f} ({sign}{delta:5.2f})")

    print()
    print("=" * 80)


def write_standard_dds_r32(pixels: np.ndarray, path: Path) -> bool:
    """
    Écrit un DDS standard R32_UINT (512×512, 10 mips).

    Args:
        pixels: Array (512, 512) uint32
        path: Chemin du fichier de sortie

    Returns:
        True si succès
    """
    try:
        height, width = pixels.shape

        # Header DDS (128 bytes)
        header = bytearray(128)
        header[0:4] = b'DDS '
        struct.pack_into('<I', header, 4, 124)
        struct.pack_into('<I', header, 8, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000)
        struct.pack_into('<I', header, 12, height)
        struct.pack_into('<I', header, 16, width)
        struct.pack_into('<I', header, 20, width * 4)
        struct.pack_into('<I', header, 24, 1)
        struct.pack_into('<I', header, 28, 10)
        struct.pack_into('<I', header, 76, 32)
        struct.pack_into('<I', header, 80, 0x00000004)
        header[84:88] = b'    '
        struct.pack_into('<I', header, 108, 0x1000 | 0x400000 | 0x8)

        with open(path, 'wb') as f:
            # Écrire header
            f.write(header)

            # Mip 0 (512×512)
            f.write(pixels.astype(np.uint32).tobytes())

            # Mips suivants (downsampled)
            mip = pixels
            for _ in range(9):
                mip = mip[::2, ::2]
                f.write(mip.astype(np.uint32).tobytes())

        return True
    except Exception as e:
        print(f"[ERR] Erreur écriture DDS: {e}")
        return False


def main():
    """Point d'entrée principal."""
    print("=" * 80)
    print("TILE BORDER FIXER - Correction discontinuités entre tiles")
    print("=" * 80)
    print()

    # Saisie interactive - coordonnées LRS2 globales
    print("Entrez les coordonnées LRS2 du bloc SOURCE adjacent au bord (ex: 6,55) :")
    src = input("Bloc source : ")
    lrs_src_x, lrs_src_y = map(int, src.strip().split(','))

    print("Entrez les coordonnées LRS2 du bloc CIBLE à corriger (ex: 6,56) :")
    tgt = input("Bloc cible : ")
    lrs_tgt_x, lrs_tgt_y = map(int, tgt.strip().split(','))

    print()

    # Déduire tiles et blocs depuis coordonnées LRS2 globales
    # Formule : lrs_x = tx*4 + bx, lrs_y = ty*4 + by
    src_tx, src_bx = lrs_src_x // 4, lrs_src_x % 4
    src_ty, src_by = lrs_src_y // 4, lrs_src_y % 4

    tgt_tx, tgt_bx = lrs_tgt_x // 4, lrs_tgt_x % 4
    tgt_ty, tgt_by = lrs_tgt_y // 4, lrs_tgt_y % 4

    tile_id_source = src_ty * 32 + src_tx
    tile_id_target = tgt_ty * 32 + tgt_tx

    print(f"[SOURCE] LRS2 ({lrs_src_x},{lrs_src_y}) -> Tile ({src_tx},{src_ty}) ID {tile_id_source}, bloc local ({src_bx},{src_by})")
    print(f"[CIBLE]  LRS2 ({lrs_tgt_x},{lrs_tgt_y}) -> Tile ({tgt_tx},{tgt_ty}) ID {tile_id_target}, bloc local ({tgt_bx},{tgt_by})")

    # Déduire direction automatiquement
    dy = tgt_ty - src_ty
    dx = tgt_tx - src_tx

    # Déterminer direction du bord cible à corriger
    if dy == 1 and dx == 0:
        # Source au Nord → corriger bord Nord de la cible (by=0)
        direction = 'N'
        border_blocks = [(i, 0) for i in range(4)]
    elif dy == -1 and dx == 0:
        # Source au Sud → corriger bord Sud de la cible (by=3)
        direction = 'S'
        border_blocks = [(i, 3) for i in range(4)]
    elif dx == 1 and dy == 0:
        # Source à l'Ouest → corriger bord Ouest de la cible (bx=0)
        direction = 'O'
        border_blocks = [(0, i) for i in range(4)]
    elif dx == -1 and dy == 0:
        # Source à l'Est → corriger bord Est de la cible (bx=3)
        direction = 'E'
        border_blocks = [(3, i) for i in range(4)]
    else:
        print(f"[ERR] Blocs non adjacents ou diagonaux : dx={dx}, dy={dy}")
        print("   Les blocs doivent être adjacents horizontalement ou verticalement")
        return 1

    print(f"[DIRECTION] {direction} detectee")
    print(f"   -> Correction du bord {direction} de la tile cible ({len(border_blocks)} blocs)")
    print()

    # Chemins projet
    PROJECT_ROOT = Path(__file__).parent.parent

    # Chemins données Zimnitrita
    TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
    DATA_DIR = TERRAIN_ROOT / ".Data"
    EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
    TERR_PATH = TERRAIN_ROOT / "terrain.terr"

    # Vérifications
    if not DATA_DIR.exists():
        print(f"[ERR] Dossier .Data introuvable: {DATA_DIR}")
        return 1

    if not EDITOR_DATA_DIR.exists():
        print(f"[ERR] Dossier .EditorData introuvable: {EDITOR_DATA_DIR}")
        return 1

    if not TERR_PATH.exists():
        print(f"[ERR] Fichier terrain.terr introuvable: {TERR_PATH}")
        return 1

    # Charger la liste des surfaces pour afficher les noms
    print("[LOAD] Chargement des surfaces depuis terrain.terr...")
    surfaces = [e["name"] for e in read_mats_from_terr(TERR_PATH)]
    print(f"   [OK] {len(surfaces)} surfaces chargées")
    print()

    # Charger LRS2 pour les deux tiles (besoin des matériaux par bloc)
    print(f"[LRS2] Chargement LRS2 tiles...")
    ttile_source = DATA_DIR / f"Terrain_{tile_id_source}.ttile"
    ttile_target = DATA_DIR / f"Terrain_{tile_id_target}.ttile"

    if not ttile_source.exists():
        print(f"[ERR] .ttile source non trouvé: {ttile_source}")
        return 1
    if not ttile_target.exists():
        print(f"[ERR] .ttile cible non trouvé: {ttile_target}")
        return 1

    lrs2_source = load_lrs2_from_ttile(ttile_source)
    lrs2_target = load_lrs2_from_ttile(ttile_target)

    if lrs2_source is None or lrs2_target is None:
        print(f"[ERR] Échec parsing LRS2")
        return 1

    print(f"   [OK] LRS2 chargés (source: {len(lrs2_source)} blocs, cible: {len(lrs2_target)} blocs)")
    print()

    # 1. Charger tile SOURCE
    print(f"[LOAD] Chargement tile source {tile_id_source}...")

    layer_source_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_source}_layer.edds"
    if not layer_source_path.exists():
        layer_source_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_source}_layer.dds"

    if not layer_source_path.exists():
        print(f"[ERR] Layer source non trouvé: {layer_source_path}")
        return 1

    layer_source_img = decode_edds_layer(layer_source_path)
    if layer_source_img is None:
        print(f"[ERR] Échec décodage layer source")
        return 1

    weights_source = extract_all_weights(layer_source_img)
    print(f"   [OK] Poids source extraits: {weights_source.shape}")

    # 2. Charger tile CIBLE
    print(f"[LOAD] Chargement tile cible {tile_id_target}...")

    layer_target_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_target}_layer.edds"
    if not layer_target_path.exists():
        layer_target_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_target}_layer.dds"

    if not layer_target_path.exists():
        print(f"[ERR] Layer cible non trouvé: {layer_target_path}")
        return 1

    layer_target_img = decode_edds_layer(layer_target_path)
    if layer_target_img is None:
        print(f"[ERR] Échec décodage layer cible")
        return 1

    weights_target = extract_all_weights(layer_target_img)
    print(f"   [OK] Poids cible extraits: {weights_target.shape}")

    # 3. Charger heightmap cible pour pentes
    bterr_target_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_target}.bterr"
    slopes = {}

    if bterr_target_path.exists():
        print(f"[HM]  Chargement heightmap cible...")
        heightmap = load_bterr_heightmap(bterr_target_path)

        if heightmap is not None:
            print("[SLOPE] Calcul pentes par bloc...")
            for by in range(4):
                for bx in range(4):
                    slope = calculate_slope_for_block(heightmap, bx, by)
                    slopes[(bx, by)] = slope
            print(f"   [OK] Pentes calculées")
        else:
            print("[WARN]  Échec chargement heightmap - pentes = 0°")
    else:
        print(f"[WARN]  Fichier .bterr cible non trouvé - pentes = 0°")

    # 4. Les blocs du bord ont déjà été déterminés lors de la détection de direction
    print(f"[TARGET] Blocs à corriger: {border_blocks}")

    # 5. Appliquer correction
    print("⚙️  Calcul poids corrigés...")
    weights_corrected = apply_border_correction(
        weights_target, weights_source, border_blocks, slopes, direction
    )
    print("   [OK] Correction appliquée")

    # 6. Mode DRY-RUN par défaut
    print()
    print("=" * 80)
    print("MODE DRY-RUN (aperçu)")
    print("=" * 80)

    # Preview PNG
    preview_path = PROJECT_ROOT / "tile_border_fix_preview.png"
    generate_preview_image(weights_target, weights_corrected, border_blocks, direction, preview_path)

    # Comparaison terminal
    print_weights_comparison(weights_target, weights_corrected, border_blocks, slopes, lrs2_target, surfaces)

    # 7. Demander confirmation pour écriture
    print()
    write_confirm = input("Écrire les modifications sur le fichier _layer.edds ? (oui/non) : ").strip().lower()

    if write_confirm in ['oui', 'o', 'yes', 'y']:
        print()
        print("=" * 80)
        print("MODE WRITE (écriture)")
        print("=" * 80)

        # Backup
        backup_path = layer_target_path.with_suffix('.edds.backup')
        print(f"[SAVE] Backup: {backup_path}")
        shutil.copy2(layer_target_path, backup_path)
        print("   [OK] Backup créé")

        # Reconstruire les pixels uint32 depuis les poids corrigés
        # Note: weights_corrected est (512, 512, 7) avec valeurs 0-31
        # pack_weights_to_pixel attend (H, W, 7) float32 [0, 1]
        print(f"[ENCODE] Reconstruction pixels DDS R32...")
        weights_normalized = weights_corrected / 31.0  # Normaliser 0-31 → 0-1
        new_pixels = pack_weights_to_pixel(weights_normalized)  # (512,512) uint32
        print(f"   [OK] Pixels reconstruits: {new_pixels.shape}")

        # Écrire DDS standard R32_UINT
        print(f"[SAVE] Écriture fichier DDS...")
        output_path = Path(layer_target_path)
        success = write_standard_dds_r32(new_pixels, output_path)

        if success:
            print(f"   [OK] DDS écrit : {output_path}")
            print()
            print("[OK] TERMINÉ - Fichier écrit avec succès")
            print(f"   Backup disponible: {backup_path}")
        else:
            print(f"   [ERR] Échec écriture DDS")
            print()
            print("[ERR] ÉCHEC - Le fichier n'a pas pu être écrit")
            return 1
    else:
        print()
        print("ℹ️  Modifications NON appliquées (dry-run seulement)")
        print(f"   Preview disponible: {preview_path}")

    print()
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
