"""
Script de test satmap avec logs debug visibles
"""

from pathlib import Path
import satmap_v2_textured

# Chemins
terrain_dir = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
catalog_path = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")
output_path = Path(r"h:\logiciel perso\Map generator\output\satmap_debug.png")

print("="*80)
print("GÉNÉRATION SATMAP AVEC DEBUG")
print("="*80)
print()

# Générer satmap en mode colors avec verbose
try:
    satmap_v2_textured.generate_satmap_v2_textured_complete(
        terrain_dir=terrain_dir,
        catalog_path=catalog_path,
        output_path=output_path,
        mode="textured",  # Mode textured pour vraies couleurs !
        target_resolution=4097,
        verbose=True  # VERBOSE = True pour logs !
    )
    print()
    print("="*80)
    print("✅ GÉNÉRATION TERMINÉE !")
    print(f"Satmap sauvegardée : {output_path}")
    print("="*80)
except Exception as e:
    print()
    print("="*80)
    print(f"❌ ERREUR : {e}")
    print("="*80)
    import traceback
    traceback.print_exc()
