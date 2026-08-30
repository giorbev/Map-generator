"""
scan_ttile.py — Bilan état des .ttile Zimnitrita

Analyse toute la map et produit un rapport :
- Tuiles présentes / manquantes
- Tuiles avec/sans GCTD
- Tuiles avec Grass_03_default (mat=0) dans le LRS2
- Blocs avec Grass_03_default mais sans GCTD (non mergeable sans modif)

Usage:
    python scan_ttile.py
    python scan_ttile.py --mat 0          # scanner un mat_id spécifique
    python scan_ttile.py --output rapport.txt
"""

import struct, sys, argparse
from pathlib import Path

TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR     = TERRAIN_ROOT / ".Data"
GRID_W       = 32

def parse_lrs2(payload):
    entries = {}
    p = 0
    while p < len(payload) - 6:
        index = struct.unpack_from('<I', payload, p)[0]
        count = struct.unpack_from('<H', payload, p+4)[0]
        if count == 0 or count > 7: break
        mats = list(struct.unpack_from(f'<{count}H', payload, p+6))
        bx = index & 0x7F
        by = (index >> 7) & 0x7F
        entries[(bx, by)] = mats
        p += 6 + count * 2
    return entries

def parse_gctd_blocs(payload, n_blocs):
    if n_blocs == 0: return set()
    payload_size = ((len(payload) - 2) // n_blocs) - 4
    section_size = 4 + payload_size
    blocs = set()
    p = 2
    while p + section_size <= len(payload):
        bx = struct.unpack_from('<H', payload, p)[0]
        by = struct.unpack_from('<H', payload, p+2)[0]
        blocs.add((bx, by))
        p += section_size
    return blocs

def scan_tile(tile_id, mat_id):
    path = DATA_DIR / f"Terrain_{tile_id}.ttile"
    if not path.exists():
        return None  # tuile absente

    data = path.read_bytes()

    # LRS2
    pos = data.find(b'LRS2')
    if pos < 0:
        return {'present': True, 'has_lrs2': False, 'has_gctd': False,
                'blocs_with_mat': [], 'blocs_no_gctd': [], 'blocs_mergeable': []}

    size = struct.unpack_from('>I', data, pos+4)[0]
    lrs2 = parse_lrs2(data[pos+8:pos+8+size])

    # GCTD
    pos2 = data.find(b'GCTD')
    has_gctd = pos2 >= 0
    gctd_blocs = set()
    if has_gctd:
        size2 = struct.unpack_from('>I', data, pos2+4)[0]
        gctd_blocs = parse_gctd_blocs(data[pos2+8:pos2+8+size2], len(lrs2))

    # Blocs avec le mat_id cible
    blocs_with_mat = [(bx, by) for (bx, by), mats in lrs2.items() if mat_id in mats]
    blocs_no_gctd  = [(bx, by) for (bx, by) in blocs_with_mat if (bx, by) not in gctd_blocs]
    blocs_mergeable = [(bx, by) for (bx, by) in blocs_with_mat if (bx, by) in gctd_blocs]

    return {
        'present': True,
        'has_lrs2': True,
        'has_gctd': has_gctd,
        'blocs_with_mat': blocs_with_mat,
        'blocs_no_gctd': blocs_no_gctd,
        'blocs_mergeable': blocs_mergeable,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mat', type=int, default=0,
                        help='Mat ID à scanner (défaut: 0 = Grass_03_default)')
    parser.add_argument('--output', type=str, default=None)
    args = parser.parse_args()

    mat_id = args.mat
    lines = []

    def log(msg=''):
        print(msg)
        lines.append(msg)

    log(f"=== SCAN ZIMNITRITA — mat_id={mat_id} ===")
    log(f"Dossier: {DATA_DIR}")
    log()

    total = GRID_W * GRID_W
    present = 0
    absent = 0
    no_gctd = 0
    has_mat = 0
    mergeable = 0
    not_mergeable = 0

    tuiles_absent = []
    tuiles_no_gctd = []
    tuiles_with_mat = []
    blocs_not_mergeable = []

    for ty in range(GRID_W):
        for tx in range(GRID_W):
            tile_id = ty * GRID_W + tx
            result = scan_tile(tile_id, mat_id)

            if result is None:
                absent += 1
                tuiles_absent.append((tx, ty, tile_id))
                continue

            present += 1
            if not result['has_gctd']:
                no_gctd += 1
                tuiles_no_gctd.append((tx, ty, tile_id))

            if result['blocs_with_mat']:
                has_mat += 1
                tuiles_with_mat.append((tx, ty, tile_id, result))
                mergeable += len(result['blocs_mergeable'])
                not_mergeable += len(result['blocs_no_gctd'])
                for bloc in result['blocs_no_gctd']:
                    blocs_not_mergeable.append((tx, ty, tile_id, bloc))

    log(f"Tuiles totales     : {total}")
    log(f"Tuiles présentes   : {present}")
    log(f"Tuiles absentes    : {absent}")
    log(f"Tuiles sans GCTD   : {no_gctd}")
    log()
    log(f"Tuiles avec mat={mat_id}  : {has_mat}")
    log(f"Blocs mergeables   : {mergeable} (ont GCTD)")
    log(f"Blocs NON mergeable: {not_mergeable} (sans GCTD → Save WB requis)")
    log()

    if tuiles_with_mat:
        log("─── Tuiles avec mat_id à traiter ───")
        for tx, ty, tid, r in tuiles_with_mat:
            nb_m = len(r['blocs_mergeable'])
            nb_nm = len(r['blocs_no_gctd'])
            status = []
            if nb_m:  status.append(f"{nb_m} mergeable")
            if nb_nm: status.append(f"{nb_nm} sans GCTD")
            log(f"  ({tx:2d},{ty:2d}) T{tid:4d} : {', '.join(status)}")

    if blocs_not_mergeable:
        log()
        log("─── Blocs NON mergeables (GCTD manquant) ───")
        for tx, ty, tid, (bx, by) in blocs_not_mergeable:
            log(f"  ({tx:2d},{ty:2d}) T{tid:4d} bloc ({bx},{by})")

    if tuiles_absent:
        log()
        log(f"─── {len(tuiles_absent)} tuiles absentes ───")
        for tx, ty, tid in tuiles_absent[:20]:
            log(f"  ({tx:2d},{ty:2d}) T{tid:4d}")
        if len(tuiles_absent) > 20:
            log(f"  ... et {len(tuiles_absent)-20} autres")

    if args.output:
        Path(args.output).write_text('\n'.join(lines), encoding='utf-8')
        print(f"\nRapport sauvegardé : {args.output}")

if __name__ == '__main__':
    main()
