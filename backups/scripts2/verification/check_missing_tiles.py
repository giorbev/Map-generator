from pathlib import Path

terrain_dir = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain")
editor_data_dir = terrain_dir / ".EditorData"
data_dir = terrain_dir / ".Data"

missing_layer = [20, 21, 53, 84, 85, 114, 115, 116, 117, 146, 147, 148, 149, 150, 178, 181, 182]

print("Verification fichiers pour tuiles manquantes:")
print("="*70)

for tile_id in missing_layer:
    layer_dds = editor_data_dir / f"Terrain_{tile_id}_layer.dds"
    layer_edds = data_dir / f"Terrain_{tile_id}_layer.edds"
    ttile = data_dir / f"Terrain_{tile_id}.ttile"
    super_dds = editor_data_dir / f"Terrain_{tile_id}_supertexture.dds"

    exists = {
        "layer.dds": layer_dds.exists(),
        "layer.edds": layer_edds.exists(),
        ".ttile": ttile.exists(),
        "supertexture.dds": super_dds.exists()
    }

    if any(exists.values()):
        print(f"\nTuile {tile_id} ({tile_id % 32}, {tile_id // 32}):")
        for name, exist in exists.items():
            if exist:
                print(f"  {name:20s} : OUI")

# Compter totaux
print(f"\n{'='*70}")
print("Statistiques:")

for check_id in missing_layer:
    ttile = data_dir / f"Terrain_{check_id}.ttile"
    if ttile.exists():
        print(f"  Tuile {check_id}: a un .ttile MAIS pas de layer.dds!")
