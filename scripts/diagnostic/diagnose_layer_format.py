"""
Diagnostic approfondi du format layer.dds
"""

from pathlib import Path
import struct
import numpy as np

tile_id = 960
layer_path = Path(rf"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData\Terrain_{tile_id}_layer.dds")

print("="*80)
print(f"ANALYSE FORMAT LAYER.DDS TUILE {tile_id}")
print("="*80)
print()

with open(layer_path, 'rb') as f:
    # Lire header DDS (128 bytes)
    magic = f.read(4)
    print(f"Magic: {magic}")

    if magic != b'DDS ':
        print("ERREUR : Pas un fichier DDS valide !")
        exit(1)

    # DDS_HEADER (124 bytes)
    size = struct.unpack('<I', f.read(4))[0]
    flags = struct.unpack('<I', f.read(4))[0]
    height = struct.unpack('<I', f.read(4))[0]
    width = struct.unpack('<I', f.read(4))[0]
    pitch = struct.unpack('<I', f.read(4))[0]
    depth = struct.unpack('<I', f.read(4))[0]
    mipmap_count = struct.unpack('<I', f.read(4))[0]

    print(f"Taille header: {size}")
    print(f"Flags: 0x{flags:08X}")
    print(f"Dimensions: {width}x{height}")
    print(f"Pitch/LinearSize: {pitch}")
    print(f"Depth: {depth}")
    print(f"Mipmap count: {mipmap_count}")
    print()

    # Skip reserved (11 DWORDs = 44 bytes)
    f.read(44)

    # DDS_PIXELFORMAT (32 bytes)
    pf_size = struct.unpack('<I', f.read(4))[0]
    pf_flags = struct.unpack('<I', f.read(4))[0]
    pf_fourcc = f.read(4)
    pf_rgbbitcount = struct.unpack('<I', f.read(4))[0]
    pf_rbitmask = struct.unpack('<I', f.read(4))[0]
    pf_gbitmask = struct.unpack('<I', f.read(4))[0]
    pf_bbitmask = struct.unpack('<I', f.read(4))[0]
    pf_abitmask = struct.unpack('<I', f.read(4))[0]

    print("### PIXEL FORMAT ###")
    print(f"Size: {pf_size}")
    print(f"Flags: 0x{pf_flags:08X}")
    print(f"FourCC: {pf_fourcc}")
    print(f"RGB bit count: {pf_rgbbitcount}")
    print(f"R bitmask: 0x{pf_rbitmask:08X}")
    print(f"G bitmask: 0x{pf_gbitmask:08X}")
    print(f"B bitmask: 0x{pf_bbitmask:08X}")
    print(f"A bitmask: 0x{pf_abitmask:08X}")
    print()

    # Caps (16 bytes)
    caps1 = struct.unpack('<I', f.read(4))[0]
    caps2 = struct.unpack('<I', f.read(4))[0]
    caps3 = struct.unpack('<I', f.read(4))[0]
    caps4 = struct.unpack('<I', f.read(4))[0]

    # Reserved2 (4 bytes)
    f.read(4)

    # Si DX10 header (fourcc = 'DX10')
    if pf_fourcc == b'DX10':
        print("### DX10 HEADER ###")
        dx10_format = struct.unpack('<I', f.read(4))[0]
        dx10_dimension = struct.unpack('<I', f.read(4))[0]
        dx10_misc = struct.unpack('<I', f.read(4))[0]
        dx10_arraysize = struct.unpack('<I', f.read(4))[0]
        dx10_misc2 = struct.unpack('<I', f.read(4))[0]

        print(f"DXGI Format: {dx10_format}")
        print(f"Dimension: {dx10_dimension}")
        print(f"Misc: {dx10_misc}")
        print(f"Array size: {dx10_arraysize}")
        print(f"Misc2: {dx10_misc2}")
        print()

        # DXGI_FORMAT enum
        dxgi_formats = {
            0: "UNKNOWN",
            41: "R32_TYPELESS",
            42: "D32_FLOAT",
            43: "R32_FLOAT",
            44: "R32_UINT",
            45: "R32_SINT",
            71: "BC1_UNORM",
            74: "BC2_UNORM",
            77: "BC3_UNORM",
            98: "BC7_UNORM",
        }

        format_name = dxgi_formats.get(dx10_format, f"Format {dx10_format}")
        print(f"Format identifié: {format_name}")
        print()

    # Position actuelle = début des données
    data_offset = f.tell()
    print(f"Offset données: {data_offset}")

    # Lire premiers bytes
    f.seek(data_offset)
    sample_data = f.read(64)

    print("### ÉCHANTILLON DONNÉES (64 premiers bytes) ###")
    print(" ".join([f"{b:02X}" for b in sample_data]))
    print()

    # Si R32_UINT, analyser premiers pixels
    if pf_fourcc == b'DX10':
        f.seek(data_offset)

        print("### ANALYSE PREMIERS PIXELS (R32_UINT) ###")
        for i in range(16):
            pixel_val = struct.unpack('<I', f.read(4))[0]

            # Extraire poids
            w1 = (pixel_val >> 0) & 0x1F
            w2 = (pixel_val >> 5) & 0x1F
            w3 = (pixel_val >> 10) & 0x1F
            w4 = (pixel_val >> 15) & 0x1F
            w5 = (pixel_val >> 20) & 0x1F
            w6 = (pixel_val >> 25) & 0x1F
            w0 = 31 - (w1 + w2 + w3 + w4 + w5 + w6)

            print(f"Pixel {i:2d}: 0x{pixel_val:08X} → w0={w0:2d} w1={w1:2d} w2={w2:2d} w3={w3:2d} w4={w4:2d} w5={w5:2d} w6={w6:2d}")

print()
print("="*80)
