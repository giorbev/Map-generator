"""
Diagnostic : Vérifier quelles textures middle ne sont pas trouvées
"""

import sys
import io
import json
from pathlib import Path

# Force UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Copier la fonction find_texture_png CORRIGÉE
def find_texture_png(textures_root: Path, middle_bcr: str):
    """Cherche texture middle"""
    # Si middle_bcr contient déjà le chemin, l'extraire
    if "Vanilla/textures/" in middle_bcr or "Customs/Textures/" in middle_bcr:
        img_name = middle_bcr.split("/")[-1]
    else:
        img_name = middle_bcr

    base_name = img_name.replace('.jpg', '').replace('.png', '').replace('.edds', '')

    for ext in ['.jpg', '.png', '.jpeg']:
        final_name = base_name + ext

        search_paths = [
            textures_root / "Vanilla" / "textures" / final_name,
            textures_root / "Customs" / "Textures" / final_name,
        ]

        for p in search_paths:
            if p.exists():
                return p

        # Fallback récursif
        for subdir in ["Vanilla/textures", "Customs/Textures"]:
            search_dir = textures_root / subdir
            if search_dir.exists():
                matches = list(search_dir.rglob(final_name))
                if matches:
                    return matches[0]

    return None


def main():
    print("\n" + "="*80)
    print("DIAGNOSTIC TEXTURES MIDDLE")
    print("="*80 + "\n")

    textures_root = Path("data/Textures_ArmaReforger")
    catalog_path = textures_root / "catalog.json"

    # Charger catalogue
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog_dict = json.load(f)

    # Le catalogue est un dict {name.emat: {data}}
    surfaces = [(name, data) for name, data in catalog_dict.items()]

    print(f"[INFO] {len(surfaces)} surfaces dans le catalogue\n")

    found = []
    missing = []
    no_middle = []

    for name, entry in surfaces:
        middle_bcr = entry.get("middle_bcr")

        if not middle_bcr:
            no_middle.append(name)
            continue

        texture_path = find_texture_png(textures_root, middle_bcr)

        if texture_path:
            found.append((name, middle_bcr, str(texture_path)))
        else:
            missing.append((name, middle_bcr))

    # ── Résultats ──────────────────────────────────────────────────────

    print(f"✅ TROUVÉES : {len(found)}/{len(surfaces)}")
    print(f"❌ MANQUANTES : {len(missing)}/{len(surfaces)}")
    print(f"⚠️  PAS DE MIDDLE_BCR : {len(no_middle)}/{len(surfaces)}")
    print()

    if missing:
        print("─"*80)
        print("TEXTURES MANQUANTES")
        print("─"*80 + "\n")

        for name, middle_bcr in missing:
            print(f"  ❌ {name}")
            print(f"     Cherche : {middle_bcr}")

            # Vérifier où on a cherché
            base_name = middle_bcr.replace('.jpg', '').replace('.png', '').replace('.edds', '')
            print(f"     Chemins testés :")
            print(f"       • {textures_root}/Vanilla/textures/{base_name}.jpg")
            print(f"       • {textures_root}/Customs/Textures/{base_name}.jpg")
            print()

    if no_middle:
        print("─"*80)
        print("SURFACES SANS MIDDLE_BCR")
        print("─"*80 + "\n")
        for name in no_middle:
            print(f"  ⚠️  {name}")

    print()
    print("="*80)
    print("FIN DIAGNOSTIC")
    print("="*80)


if __name__ == "__main__":
    main()
