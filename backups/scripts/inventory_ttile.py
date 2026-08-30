"""
inventory_ttile.py — Inventaire matériaux terrain depuis .ttile

Lit tous les .ttile d'un dossier .Data et agrège les statistiques d'utilisation
des matériaux (mat_ids) par bloc.

Usage:
    # Mode inventaire (défaut)
    python inventory_ttile.py --data-dir "I:/addon/World/Map/Terrain/.Data"
    python inventory_ttile.py --data-dir "I:/addon/.Data" --mask exclusion.png

    # Mode --list-mat (liste blocs avec mat_id spécifique)
    python inventory_ttile.py --data-dir "I:/addon/.Data" --list-mat 0 --min-coverage 10.0
    python inventory_ttile.py --data-dir "I:/addon/.Data" --list-mat 0 --mask exclusion.png --output blocs.txt
"""

import argparse
import csv
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    import numpy as np
    from PIL import Image
    HAS_IMAGE = True
except ImportError:
    HAS_IMAGE = False


# ─── IFF + LRS2 ───────────────────────────────────────────────────────────────

def parse_ttile(data: bytes) -> Dict[bytes, Tuple[int, int, bytes]]:
    """Parse chunks IFF → {tag: (pos, size, payload)}"""
    chunks = {}
    pos = 12
    while pos < len(data) - 8:
        tag = bytes(data[pos:pos+4])
        size = struct.unpack_from('>I', data, pos+4)[0]
        if size > len(data):
            break
        chunks[tag] = (pos, size, bytes(data[pos+8:pos+8+size]))
        pos += 8 + size + (size % 2)
    return chunks


def parse_lrs2(payload: bytes) -> Dict[Tuple[int, int], List[int]]:
    """Parse LRS2 → {(bx,by): [mat_ids]}"""
    entries = {}
    p = 0
    while p < len(payload) - 6:
        index = struct.unpack_from('<I', payload, p)[0]
        count = struct.unpack_from('<H', payload, p+4)[0]
        if count == 0 or count > 7:
            break
        mats = list(struct.unpack_from(f'<{count}H', payload, p+6))
        bx = index & 0x7F
        by = (index >> 7) & 0x7F
        entries[(bx, by)] = mats
        p += 6 + count * 2
    return entries


def parse_gctd(payload: bytes, n_blocs: int) -> Dict[Tuple[int, int], bytes]:
    """Parse GCTD → {(bx,by): gctd_data}"""
    header = payload[:2]
    payload_size = ((len(payload) - 2) // n_blocs) - 4 if n_blocs > 0 else 2025
    sections = {}
    section_size = 4 + payload_size
    p = 2
    while p + section_size <= len(payload):
        bx = struct.unpack_from('<H', payload, p)[0]
        by = struct.unpack_from('<H', payload, p+2)[0]
        sections[(bx, by)] = bytes(payload[p+4:p+4+payload_size])
        p += section_size
    return sections


# ─── Masque exclusion ─────────────────────────────────────────────────────────

def load_exclusion_mask(mask_path: Path) -> Optional[np.ndarray]:
    """
    Charge masque exclusion PNG.
    Retourne array bool (H, W) : True = Zone A (noir), False = Zone B (blanc)
    """
    if not HAS_IMAGE:
        print("WARN: PIL/numpy non disponibles, masque ignoré")
        return None

    img = Image.open(mask_path).convert('L')
    arr = np.array(img, dtype=np.uint8)
    # Noir (0-127) = Zone A (True), Blanc (128-255) = Zone B (False)
    return arr < 128


def get_block_zone(bx: int, by: int, mask: Optional[np.ndarray],
                   grid_w: int = 128) -> str:
    """
    Retourne 'A' ou 'B' selon la zone du bloc.
    Si pas de masque, retourne 'A' par défaut.
    """
    if mask is None:
        return 'A'

    h, w = mask.shape
    # Coordonnées pixel centre du bloc
    px = int((bx + 0.5) / grid_w * w)
    py = int((by + 0.5) / grid_w * h)

    # Clamp
    px = max(0, min(w - 1, px))
    py = max(0, min(h - 1, py))

    return 'A' if mask[py, px] else 'B'


# ─── Chargement noms matériaux ────────────────────────────────────────────────

def load_material_names(txt_path: Path) -> Dict[int, str]:
    """
    Charge terrain_materials_list.txt → {mat_id: name}
    Format attendu : "id:name" par ligne
    """
    names = {}
    if not txt_path.exists():
        return names

    for line in txt_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        parts = line.split(':', 1)
        try:
            mat_id = int(parts[0].strip())
            name = parts[1].strip()
            names[mat_id] = name
        except (ValueError, IndexError):
            continue

    return names


# ─── Mode --list-mat ──────────────────────────────────────────────────────────

def calculate_mat_coverage(
    gctd_data: bytes,
    lrs2_mats: List[int],
    target_mat_id: int
) -> float:
    """
    Calcule le coverage % d'un mat_id dans un bloc.

    Args:
        gctd_data: Données GCTD brutes (2025 bytes pour 45×45)
        lrs2_mats: Liste mat_ids du bloc depuis LRS2
        target_mat_id: mat_id recherché

    Returns:
        Coverage en % (0.0-100.0)
    """
    if target_mat_id not in lrs2_mats:
        return 0.0

    target_slot = lrs2_mats.index(target_mat_id)
    total_cells = len(gctd_data)
    matching_cells = 0

    for idx in gctd_data:
        slot = idx // 4  # bits 7-4
        if slot == target_slot:
            matching_cells += 1

    return (matching_cells / total_cells) * 100.0 if total_cells > 0 else 0.0


def list_mat_blocks(
    data_dir: Path,
    target_mat_id: int,
    min_coverage: float,
    mask: Optional[np.ndarray],
    output_path: Path,
    grid_w: int = 32
):
    """
    Liste tous les blocs contenant target_mat_id avec coverage >= min_coverage.

    Args:
        data_dir: Dossier .Data
        target_mat_id: mat_id recherché
        min_coverage: Coverage minimum en %
        mask: Masque exclusion (si fourni, filtre Zone B uniquement)
        output_path: Fichier de sortie
        grid_w: Nombre de tuiles par axe (défaut 32)
    """
    results = []  # [(tile_id, tx, ty, bx, by, coverage)]

    ttile_files = sorted(data_dir.glob('*.ttile'))
    if not ttile_files:
        print(f"ERREUR: Aucun .ttile trouvé dans {data_dir}")
        return

    print(f"Scan de {len(ttile_files)} fichiers .ttile...")
    print(f"Recherche mat_id={target_mat_id}, coverage >= {min_coverage:.1f}%")
    if mask is not None:
        print("Filtre : Zone B uniquement (blanc)")

    for ttile_path in ttile_files:
        try:
            # Extraire tile_id depuis nom fichier Terrain_XXX.ttile
            tile_id = int(ttile_path.stem.split('_')[1])
            tx = tile_id % grid_w
            ty = tile_id // grid_w

            data = ttile_path.read_bytes()
            chunks = parse_ttile(data)

            if b'LRS2' not in chunks or b'GCTD' not in chunks:
                continue

            _, _, lrs2_payload = chunks[b'LRS2']
            _, _, gctd_payload = chunks[b'GCTD']

            lrs2_entries = parse_lrs2(lrs2_payload)
            gctd_sections = parse_gctd(gctd_payload, len(lrs2_entries))

            for (bx, by), mats in lrs2_entries.items():
                # Filtre Zone B si masque fourni
                if mask is not None:
                    zone = get_block_zone(bx, by, mask)
                    if zone != 'B':  # Garder seulement Zone B (blanc)
                        continue

                if (bx, by) not in gctd_sections:
                    continue

                coverage = calculate_mat_coverage(
                    gctd_sections[(bx, by)],
                    mats,
                    target_mat_id
                )

                if coverage >= min_coverage:
                    results.append((tile_id, tx, ty, bx, by, coverage))

        except Exception as e:
            print(f"WARN: Erreur lecture {ttile_path.name}: {e}")
            continue

    # Tri par coverage décroissant
    results.sort(key=lambda x: x[5], reverse=True)

    # Affichage console
    print(f"\n{'='*70}")
    print(f"Blocs avec mat_id={target_mat_id} (coverage >= {min_coverage:.1f}%)")
    print(f"{'='*70}")
    print(f"Total: {len(results)} blocs")
    print(f"{'Tile':<15} {'Bloc':<15} {'Coverage %':<12}")
    print("-" * 70)

    for tile_id, tx, ty, bx, by, coverage in results:
        print(f"T{tile_id:<5} ({tx:2},{ty:2})  bloc ({bx:3},{by:3})  →  {coverage:>6.1f}%")

    # Export fichier
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# Blocs avec mat_id={target_mat_id} (coverage >= {min_coverage:.1f}%)\n")
        f.write(f"# Total: {len(results)} blocs\n")
        f.write(f"# Format: T<tile_id> (<tx>,<ty>) bloc (<bx>,<by>) → <coverage>%\n\n")

        for tile_id, tx, ty, bx, by, coverage in results:
            f.write(f"T{tile_id} ({tx},{ty}) bloc ({bx},{by}) → {coverage:.1f}%\n")

    print(f"\nFichier exporté : {output_path}")


# ─── Inventaire ───────────────────────────────────────────────────────────────

def inventory_data_dir(
    data_dir: Path,
    mask: Optional[np.ndarray] = None
) -> Dict[str, Dict[int, int]]:
    """
    Inventorie tous les .ttile du dossier .Data.

    Returns:
        {
            'A': {mat_id: nb_blocs, ...},
            'B': {mat_id: nb_blocs, ...}
        }
    """
    stats = {'A': Counter(), 'B': Counter()}

    ttile_files = sorted(data_dir.glob('*.ttile'))
    if not ttile_files:
        print(f"WARN: Aucun .ttile trouvé dans {data_dir}")
        return stats

    print(f"Scan de {len(ttile_files)} fichiers .ttile...")

    for ttile_path in ttile_files:
        try:
            data = ttile_path.read_bytes()
            chunks = parse_ttile(data)

            if b'LRS2' not in chunks:
                continue

            _, _, lrs2_payload = chunks[b'LRS2']
            lrs2_entries = parse_lrs2(lrs2_payload)

            for (bx, by), mats in lrs2_entries.items():
                zone = get_block_zone(bx, by, mask)
                for mat_id in mats:
                    stats[zone][mat_id] += 1

        except Exception as e:
            print(f"WARN: Erreur lecture {ttile_path.name}: {e}")
            continue

    return stats


# ─── Sortie ───────────────────────────────────────────────────────────────────

def print_stats(
    stats: Dict[str, Dict[int, int]],
    names: Dict[int, str],
    total_blocks: Dict[str, int]
):
    """Affiche stats sur console"""

    for zone in ['A', 'B']:
        if not stats[zone]:
            continue

        total = total_blocks[zone]
        if total == 0:
            continue

        print(f"\n{'='*70}")
        print(f"ZONE {zone} — {total} blocs total")
        print(f"{'='*70}")
        print(f"{'ID':<5} {'Nom':<40} {'Blocs':<8} {'Coverage %':<10}")
        print("-" * 70)

        # Tri par nb_blocs décroissant
        sorted_items = sorted(stats[zone].items(), key=lambda x: x[1], reverse=True)

        for mat_id, nb_blocs in sorted_items:
            name = names.get(mat_id, f"mat_{mat_id}")
            coverage = (nb_blocs / total) * 100
            print(f"{mat_id:<5} {name:<40} {nb_blocs:<8} {coverage:<10.2f}")


def export_csv(
    stats: Dict[str, Dict[int, int]],
    names: Dict[int, str],
    total_blocks: Dict[str, int],
    output_path: Path
):
    """Exporte stats en CSV"""

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['zone', 'mat_id', 'name', 'nb_blocs', 'coverage_pct'])

        for zone in ['A', 'B']:
            if not stats[zone]:
                continue

            total = total_blocks[zone]
            if total == 0:
                continue

            # Tri par nb_blocs décroissant
            sorted_items = sorted(stats[zone].items(), key=lambda x: x[1], reverse=True)

            for mat_id, nb_blocs in sorted_items:
                name = names.get(mat_id, f"mat_{mat_id}")
                coverage = (nb_blocs / total) * 100
                writer.writerow([zone, mat_id, name, nb_blocs, f"{coverage:.2f}"])

    print(f"\nCSV exporté : {output_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Inventaire matériaux terrain depuis .ttile"
    )
    parser.add_argument(
        '--data-dir',
        type=Path,
        required=True,
        help="Chemin vers dossier .Data contenant les .ttile"
    )
    parser.add_argument(
        '--mask',
        type=Path,
        default=None,
        help="Masque exclusion PNG (noir=Zone A, blanc=Zone B)"
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help="Fichier de sortie (défaut: inventory.csv ou mat_<ID>_blocs.txt)"
    )
    parser.add_argument(
        '--list-mat',
        type=int,
        default=None,
        metavar='MAT_ID',
        help="Mode : liste blocs contenant ce mat_id avec coverage"
    )
    parser.add_argument(
        '--min-coverage',
        type=float,
        default=0.0,
        help="Coverage minimum en %% pour --list-mat (défaut: 0.0)"
    )

    args = parser.parse_args()

    # Vérifications
    if not args.data_dir.exists():
        print(f"ERREUR: Dossier introuvable : {args.data_dir}")
        sys.exit(1)

    if args.mask and not args.mask.exists():
        print(f"ERREUR: Masque introuvable : {args.mask}")
        sys.exit(1)

    if args.mask and not HAS_IMAGE:
        print("ERREUR: PIL et numpy requis pour --mask")
        sys.exit(1)

    # Chargement masque
    mask = None
    if args.mask:
        print(f"Chargement masque : {args.mask}")
        mask = load_exclusion_mask(args.mask)
        print(f"  → Résolution : {mask.shape[1]}×{mask.shape[0]}")

    # ─── MODE --list-mat ──────────────────────────────────────────────────────
    if args.list_mat is not None:
        output_path = args.output or Path(f"mat_{args.list_mat}_blocs.txt")
        list_mat_blocks(
            args.data_dir,
            args.list_mat,
            args.min_coverage,
            mask,
            output_path
        )
        return

    # ─── MODE INVENTAIRE (défaut) ────────────────────────────────────────────

    # Chargement noms matériaux
    names_file = Path(__file__).parent / 'terrain_materials_list.txt'
    names = load_material_names(names_file)
    if names:
        print(f"Noms matériaux chargés : {len(names)} entrées")
    else:
        print("WARN: terrain_materials_list.txt non trouvé, IDs uniquement")

    # Inventaire
    stats = inventory_data_dir(args.data_dir, mask)

    # Calcul totaux
    total_blocks = {
        'A': sum(stats['A'].values()),
        'B': sum(stats['B'].values())
    }

    # Affichage
    print_stats(stats, names, total_blocks)

    # Export CSV
    output_path = args.output or Path('inventory.csv')
    if stats['A'] or stats['B']:
        export_csv(stats, names, total_blocks, output_path)
    else:
        print("\nAucune donnée à exporter")


if __name__ == '__main__':
    main()
