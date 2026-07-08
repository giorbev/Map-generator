from pathlib import Path
import struct

for tile_id in [0, 1, 2]:
    ttile = Path(rf"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.Data\Terrain_{tile_id}.ttile")
    with open(ttile, 'rb') as f:
        data = f.read()

    # Trouver LRS2
    pos = 12
    while pos + 8 <= len(data):
        cid = data[pos:pos+4].decode('ascii', errors='ignore')
        csz = struct.unpack_from('>I', data, pos+4)[0]

        if cid == 'LRS2':
            print(f"Tuile {tile_id}: LRS2 size={csz} bytes")
            lrs2_data = data[pos+8:pos+8+csz]
            print(f"  Premiers 32 bytes: {lrs2_data[:32].hex(' ')}")

            # Parser premier enregistrement
            if len(lrs2_data) >= 6:
                index = struct.unpack_from('<I', lrs2_data, 0)[0]
                n = struct.unpack_from('<H', lrs2_data, 4)[0]
                print(f"  Premier enreg: index={index}, n={n}")

                # Si n > 0, lire les IDs
                if n > 0 and len(lrs2_data) >= 6 + n*2:
                    ids = []
                    for i in range(min(n, 5)):
                        mat_id = struct.unpack_from('<H', lrs2_data, 6 + i*2)[0]
                        ids.append(mat_id)
                    print(f"  IDs: {ids}")
            break

        pos = pos + 8 + csz + (csz % 2)
    print()
