"""
write_ttile_block.py
--------------------
Modifie la texture dominante d'un bloc terrain dans le .ttile Reforger.
Modifie LRS2 (liste matériaux du bloc) et GCTD (index local par pixel).

Usage :
    python write_ttile_block.py --ttile <path> --bx <int> --by <int>
                                --old-mat <int> --new-mat <int>
                                [--dry-run] [--no-confirm]

Coordonnées bx, by : globales (pas locales à la tuile)
old-mat, new-mat   : IDs globaux depuis terrain.terr (0-60)

Exemple :
    python write_ttile_block.py
        --ttile "I:/.../Terrain/.Data/Terrain_616.ttile"
        --bx 34 --by 79 --old-mat 8 --new-mat 26
"""

import argparse, shutil, struct, sys
from pathlib import Path

SURFACES = {
    0:'Grass_03_default', 1:'SeaBed_01', 2:'Dirt_01', 3:'Grass_03',
    4:'ForestDeciduous_02', 5:'Crop_Field_01', 6:'Crop_Field_02',
    7:'Debris_Rock_01', 8:'Rock_01', 9:'Dirt_02', 10:'Pebbles_01',
    11:'Pebbles_02', 12:'Asphalt_01', 13:'Concrete_01', 14:'Grass_01',
    15:'Grass_02', 16:'Grass_04', 17:'MountainGrass_01', 18:'MountainGrass_02',
    19:'MountainGrass_03', 20:'MountainGrass_04', 21:'ForestDeciduous_01',
    22:'Dirt_03', 23:'Sand_01', 24:'Snow_01', 25:'Ice_01',
    26:'ForestConiferous_01_Base',
}

# ─── IFF helpers ──────────────────────────────────────────────────────────────

def find_chunk(data, tag):
    pos = data.find(tag)
    if pos < 0:
        return None, 0, b''
    size = struct.unpack_from('>I', data, pos+4)[0]
    return pos, size, data[pos+8:pos+8+size]

def replace_chunk(data: bytearray, tag: bytes, new_payload: bytes) -> bytearray:
    pos = data.find(tag)
    if pos < 0:
        raise ValueError(f"Chunk {tag} introuvable")
    old_size = struct.unpack_from('>I', data, pos+4)[0]
    delta    = len(new_payload) - old_size
    struct.pack_into('>I', data, pos+4, len(new_payload))
    data[pos+8 : pos+8+old_size] = new_payload
    form_size = struct.unpack_from('>I', data, 4)[0]
    struct.pack_into('>I', data, 4, form_size + delta)
    return data

# ─── LRS2 ─────────────────────────────────────────────────────────────────────

def parse_lrs2(raw):
    entries, pos = {}, 0
    while pos < len(raw) - 6:
        idx  = struct.unpack_from('<I', raw, pos)[0]
        cnt  = struct.unpack_from('<H', raw, pos+4)[0]
        mats = list(struct.unpack_from(f'<{cnt}H', raw, pos+6))
        entries[(idx & 0x7F, (idx >> 7) & 0x7F)] = mats
        pos += 6 + cnt*2
    return entries

def build_lrs2(entries):
    parts = []
    for (bx, by), mats in sorted(entries.items()):
        parts.append(struct.pack('<IH', bx | (by<<7), len(mats)))
        parts.append(struct.pack(f'<{len(mats)}H', *mats))
    return b''.join(parts)

# ─── GCTD ─────────────────────────────────────────────────────────────────────

def find_gctd_section(gctd: bytes, bx: int, by: int, lrs2_entries: dict):
    """
    Retourne (header_offset, data_offset, data_size) de la section (bx,by).
    Stratégie : scan séquentiel par sauts de ~2030 bytes en cherchant (bx,by).
    """
    pos = 2  # skip 2-byte global header
    while pos < len(gctd) - 4:
        fx = struct.unpack_from('<H', gctd, pos)[0]
        fy = struct.unpack_from('<H', gctd, pos+2)[0]
        if (fx, fy) in lrs2_entries and fx < 128 and fy < 128:
            if fx == bx and fy == by:
                # Trouver fin : prochaine section connue
                next_off = len(gctd)
                probe = pos + 4
                while probe < len(gctd) - 4:
                    nx = struct.unpack_from('<H', gctd, probe)[0]
                    ny = struct.unpack_from('<H', gctd, probe+2)[0]
                    if (nx, ny) in lrs2_entries and nx < 128 and ny < 128 and (nx,ny) != (bx,by):
                        next_off = probe
                        break
                    probe += 1
                data_start = pos + 4
                data_size  = next_off - data_start
                return pos, data_start, data_size
            pos += 2030
        else:
            pos += 1
    return None, None, None

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ttile',      required=True)
    ap.add_argument('--bx',         required=True, type=int)
    ap.add_argument('--by',         required=True, type=int)
    ap.add_argument('--old-mat',    required=True, type=int)
    ap.add_argument('--new-mat',    required=True, type=int)
    ap.add_argument('--dry-run',    action='store_true')
    ap.add_argument('--no-confirm', action='store_true')
    args = ap.parse_args()

    ttile_path = Path(args.ttile)
    if not ttile_path.exists():
        print(f"[ERREUR] Fichier introuvable : {ttile_path}"); sys.exit(1)

    bx, by   = args.bx, args.by
    old_mat  = args.old_mat
    new_mat  = args.new_mat
    print(f"Fichier  : {ttile_path.name}")
    print(f"Bloc     : ({bx}, {by})")
    print(f"Remplacement : {old_mat} ({SURFACES.get(old_mat,'?')}) "
          f"→ {new_mat} ({SURFACES.get(new_mat,'?')})")
    print()

    raw = bytearray(ttile_path.read_bytes())

    # ── LRS2 ──
    _, _, lrs2_raw = find_chunk(bytes(raw), b'LRS2')
    entries = parse_lrs2(lrs2_raw)

    if (bx, by) not in entries:
        print(f"[ERREUR] Bloc ({bx},{by}) absent du LRS2")
        print(f"  Blocs : {sorted(entries.keys())}"); sys.exit(1)

    old_list = entries[(bx, by)]
    print(f"LRS2 actuel  ({bx},{by}) : {old_list} = {[SURFACES.get(m,'?') for m in old_list]}")

    if old_mat not in old_list:
        print(f"[ERREUR] Matériau {old_mat} ({SURFACES.get(old_mat,'?')}) absent du bloc")
        sys.exit(1)

    old_local = old_list.index(old_mat)

    # Construire nouvelle liste
    new_list = old_list[:]
    if new_mat in new_list:
        new_list.remove(old_mat)           # new déjà présent → juste supprimer old
        new_local = new_list.index(new_mat)
    else:
        new_list[old_local] = new_mat      # remplacement en place
        new_local = old_local

    new_entries = dict(entries)
    new_entries[(bx, by)] = new_list
    print(f"LRS2 nouveau ({bx},{by}) : {new_list} = {[SURFACES.get(m,'?') for m in new_list]}")
    print(f"Index local  : old={old_local} → new={new_local}")

    # ── GCTD ──
    _, _, gctd_raw = find_chunk(bytes(raw), b'GCTD')
    hdr_off, data_off, data_size = find_gctd_section(gctd_raw, bx, by, entries)

    if hdr_off is None:
        print(f"[ERREUR] Section ({bx},{by}) introuvable dans GCTD"); sys.exit(1)

    print(f"\nGCTD section ({bx},{by}) @ {hdr_off}, data @ {data_off} ({data_size} bytes)")
    gctd_mut = bytearray(gctd_raw)
    px_count = 0
    for i in range(data_size):
        if gctd_mut[data_off + i] == old_local:
            gctd_mut[data_off + i] = new_local
            px_count += 1
    print(f"GCTD : {px_count} bytes modifiés (old={old_local} → new={new_local})")

    if args.dry_run:
        print("\n[DRY-RUN] Aucune écriture."); return

    if not args.no_confirm:
        rep = input("\nAppliquer ? [oui/non] : ").strip().lower()
        if rep != 'oui':
            print("Annulé."); return

    # ── Backup ──
    bak = ttile_path.with_suffix('.ttile.bak')
    if not bak.exists():
        shutil.copy2(ttile_path, bak)
        print(f"[OK] Backup : {bak.name}")

    # ── Écriture ──
    raw = replace_chunk(raw, b'LRS2', build_lrs2(new_entries))
    raw = replace_chunk(raw, b'GCTD', bytes(gctd_mut))

    form_size = struct.unpack_from('>I', raw, 4)[0]
    if form_size + 8 != len(raw):
        print(f"[WARN] FORM size mismatch: {form_size+8} vs {len(raw)}")

    ttile_path.write_bytes(bytes(raw))
    print(f"[OK] {ttile_path.name} écrit ({len(raw)} bytes)")
    print("\nOuvre Workbench, vérifie le bloc, puis Save pour régénérer les caches.")

if __name__ == '__main__':
    main()
