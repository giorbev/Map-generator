"""
Diagnostiquer pourquoi SeaBed donne du noir
"""

from pathlib import Path
import json
import numpy as np
from PIL import Image

# Chemins
catalog_path = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")
textures_root = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger")
surfaces_path = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\terrain_materials_list.txt")

# Charger catalogue
with open(catalog_path, 'r') as f:
    catalog = json.load(f)

# Charger surfaces
with open(surfaces_path, 'r') as f:
    surfaces = [line.strip() for line in f if line.strip() and not line.startswith('#')]

print("="*80)
print("DIAGNOSTIC SEABED")
print("="*80)
print()

# SeaBed est ID 1
mat_id = 1
surface_name = surfaces[mat_id] if mat_id < len(surfaces) else None

print(f"Matériau ID {mat_id}: {surface_name}")
print()

if surface_name not in catalog:
    print(f"ERREUR : {surface_name} PAS DANS CATALOGUE !")
    exit(1)

entry = catalog[surface_name]

print("### CATALOGUE ###")
print(f"  MiddleColor: {entry.get('MiddleColor', 'ABSENT')}")
print(f"  Color: {entry.get('Color', 'ABSENT')}")
print(f"  Tiling scale: {entry.get('tiling_scale', 'ABSENT')}")
print()

# Chercher texture Middle
base_name = surface_name.replace('.emat', '')

# Essayer différents chemins
possible_paths = [
    textures_root / "texture_Middle" / "textures" / f"{base_name}.png",
    textures_root / "texture_Middle" / "textures" / f"{base_name}.jpg",
    textures_root / "Vanilla" / "texture_Middle" / "textures" / f"{base_name}.png",
    textures_root / "Vanilla" / "texture_Middle" / "textures" / f"{base_name}.jpg",
]

print("### RECHERCHE TEXTURE ###")
texture_found = None
for p in possible_paths:
    print(f"  Test: {p.relative_to(textures_root) if p.exists() else str(p)}")
    if p.exists():
        texture_found = p
        print(f"    -> TROUVEE !")
        break

print()

if texture_found:
    # Charger et analyser texture
    img = Image.open(texture_found).convert('RGB')
    arr = np.array(img)

    print(f"### TEXTURE CHARGEE : {texture_found.name} ###")
    print(f"  Dimensions: {img.size}")
    print(f"  Couleur moyenne RGB: ({arr[:,:,0].mean():.1f}, {arr[:,:,1].mean():.1f}, {arr[:,:,2].mean():.1f})")
    print()

    # Calculer couleur finale avec tint
    middle = entry.get('MiddleColor', [255, 255, 255])
    color_tint = entry.get('Color', [255, 255, 255])

    r = (arr[:,:,0].mean() / 255.0) * (middle[0] / 255.0) * (color_tint[0] / 255.0)
    g = (arr[:,:,1].mean() / 255.0) * (middle[1] / 255.0) * (color_tint[1] / 255.0)
    b = (arr[:,:,2].mean() / 255.0) * (middle[2] / 255.0) * (color_tint[2] / 255.0)

    # Linear to sRGB
    def linear_to_srgb(c):
        return int(255 * (c ** (1/2.2)))

    final_r = linear_to_srgb(r)
    final_g = linear_to_srgb(g)
    final_b = linear_to_srgb(b)

    print(f"### COULEUR FINALE AVEC TINT ###")
    print(f"  RGB: ({final_r}, {final_g}, {final_b})")

    if final_r < 10 and final_g < 10 and final_b < 10:
        print()
        print("  PROBLEME : COULEUR QUASI-NOIRE !")
        print("  -> Vérifier MiddleColor et Color dans catalogue")
else:
    print("ERREUR : TEXTURE INTROUVABLE !")
    print()
    print("-> Fallback couleur unie sera utilisé")
    print(f"   MiddleColor: {entry.get('MiddleColor', [255,255,255])}")

print()
print("="*80)
