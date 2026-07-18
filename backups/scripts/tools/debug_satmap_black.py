"""
Debug satmap noire - Verifier tints, poids, correspondances
"""

import json
import numpy as np
from pathlib import Path
from layer_dds_reader import read_layer_dds, extract_all_weights
from lrs2_parser import load_lrs2_from_ttile
from terrain_materials_parser import load_surfaces_list_from_world

# Chemins
terrain_dir = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain")
catalog_file = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")
editor_data_dir = terrain_dir / ".EditorData"
data_dir = terrain_dir / ".Data"

print("="*80)
print("DIAGNOSTIC SATMAP NOIRE")
print("="*80)

# 1. Charger catalogue
with open(catalog_file, 'r', encoding='utf-8') as f:
    catalog = json.load(f)

print(f"\n1. CATALOGUE : {len(catalog)} surfaces")

# Compter combien ont des tints
tints_count = sum(1 for entry in catalog.values() if 'tint_srgb' in entry and entry['tint_srgb'])
print(f"   Surfaces avec tint_srgb : {tints_count}/{len(catalog)}")

# Afficher quelques tints
print("\n   Exemples de tints :")
count = 0
for name, entry in catalog.items():
    if 'tint_srgb' in entry and entry['tint_srgb']:
        print(f"      {name}: {entry['tint_srgb']}")
        count += 1
        if count >= 5:
            break

# 2. Charger liste surfaces
print("\n2. LISTE SURFACES (terrain_materials_list.txt)")
surfaces_list = load_surfaces_list_from_world(terrain_dir)
if surfaces_list:
    print(f"   OK {len(surfaces_list)} surfaces")
    print(f"   Premieres 5 : {surfaces_list[:5]}")
else:
    print("   ERREUR Impossible de charger !")

# 3. Tester lecture layer.dds (tuile 0)
print("\n3. TEST LAYER.DDS (Tuile 0)")
layer_path = editor_data_dir / "Terrain_0_layer.dds"
if layer_path.exists():
    layer_img = read_layer_dds(layer_path)
    if layer_img is not None:
        print(f"   OK Decode : {layer_img.shape}")
        print(f"   Min pixel : 0x{layer_img.min():08X}")
        print(f"   Max pixel : 0x{layer_img.max():08X}")

        # Extraire poids
        weights = extract_all_weights(layer_img)
        print(f"   Poids shape : {weights.shape}")

        # Verifier si poids non nuls
        for i in range(7):
            non_zero = (weights[:, :, i] > 0).sum()
            print(f"      w{i} > 0 : {non_zero} pixels")
    else:
        print("   ERREUR Decodage echoue")
else:
    print(f"   ERREUR Fichier absent : {layer_path}")

# 4. Tester LRS2 (tuile 0)
print("\n4. TEST LRS2 (Tuile 0)")
ttile_path = data_dir / "Terrain_0.ttile"
print(f"   Chemin : {ttile_path}")
print(f"   Existe : {ttile_path.exists()}")
if ttile_path.exists():
    lrs2_blocks = load_lrs2_from_ttile(ttile_path)
    print(f"   Retour : {lrs2_blocks is not None}")
    if lrs2_blocks:
        print(f"   OK {len(lrs2_blocks)} blocs")

        # Afficher bloc (0, 0)
        mat_ids = lrs2_blocks.get((0, 0), [])
        print(f"\n   Bloc (0,0) : {len(mat_ids)} materiaux")
        print(f"   IDs : {mat_ids}")

        # Verifier correspondance avec surfaces_list
        if surfaces_list:
            print(f"\n   Correspondance IDs -> Surfaces :")
            for mat_id in mat_ids[:5]:
                if mat_id < len(surfaces_list):
                    surface_name = surfaces_list[mat_id]
                    print(f"      ID {mat_id} -> {surface_name}")

                    # Verifier tint
                    if surface_name in catalog:
                        tint = catalog[surface_name].get('tint_srgb', None)
                        print(f"         Tint : {tint}")
                else:
                    print(f"      ID {mat_id} -> HORS LIMITES (max={len(surfaces_list)-1})")
    else:
        print("   ERREUR Parsing LRS2 echoue")
else:
    print(f"   ERREUR Fichier absent : {ttile_path}")

# 5. Test de generation d'un petit bloc
print("\n5. TEST GENERATION BLOC (0,0) de Tuile 0")
if layer_img is not None and lrs2_blocks and surfaces_list:
    # Zone du bloc (0, 0) = 128x128 pixels
    weights_bloc = weights[0:128, 0:128, :]
    mat_ids_bloc = lrs2_blocks.get((0, 0), [])

    # Canvas test
    result = np.zeros((128, 128, 3), dtype=np.float32)

    for i, mat_id in enumerate(mat_ids_bloc):
        if i >= 7:
            break

        if mat_id >= len(surfaces_list):
            continue

        surface_name = surfaces_list[mat_id]

        if surface_name not in catalog:
            continue

        entry = catalog[surface_name]

        # Couleur
        if 'tint_srgb' in entry and entry['tint_srgb']:
            r, g, b = entry['tint_srgb']
            color = np.array([r, g, b], dtype=np.uint8)
        else:
            color = np.array([128, 128, 128], dtype=np.uint8)

        # Poids
        w = weights_bloc[:, :, i]

        # Accumuler
        result += w[:, :, None] * color[None, None, :]

    # Convertir
    result = np.clip(result, 0, 255).astype(np.uint8)

    # Statistiques
    print(f"   Result shape : {result.shape}")
    print(f"   Min RGB : {result.min()}")
    print(f"   Max RGB : {result.max()}")
    print(f"   Mean RGB : {result.mean():.1f}")

    # Pixels non noirs
    non_black = ((result[:, :, 0] > 0) | (result[:, :, 1] > 0) | (result[:, :, 2] > 0)).sum()
    print(f"   Pixels non-noirs : {non_black}/{128*128} ({non_black/(128*128)*100:.1f}%)")

print("\n" + "="*80)
