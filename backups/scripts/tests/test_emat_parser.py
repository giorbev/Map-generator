"""
Test du parseur .emat
Affiche les paramètres extraits pour vérifier le parsing et l'héritage
"""

import sys
import io
from pathlib import Path
import json

# Force UTF-8 pour console Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import reforger_emat_parser as parser


def test_single_emat(emat_name: str, search_dirs, show_details=True):
    """Test parsing d'un .emat unique avec détails"""

    print(f"\n{'='*80}")
    print(f"TEST : {emat_name}")
    print('='*80)

    # Chercher le fichier
    emat_path = parser.find_emat_file(search_dirs, emat_name)

    if not emat_path:
        print(f"❌ Fichier introuvable : {emat_name}")
        return

    print(f"📁 Fichier : {emat_path.relative_to(Path('data/Textures_ArmaReforger'))}")
    print()

    # Parser avec héritage
    params = parser.parse_emat_params(emat_path, search_dirs)

    # Afficher paramètres bruts
    if show_details:
        print("📋 PARAMÈTRES EXTRAITS :")
        print("-" * 80)
        for param, value in params.items():
            if value:
                print(f"  {param:20s} : {value}")
            else:
                print(f"  {param:20s} : (absent)")
        print()

    # Calcul tint
    middle_color = params.get("MiddleColor", "1 1 1 1")
    color = params.get("Color", "1 1 1 1")
    tint_rgb = parser.compute_tint_srgb(middle_color, color)
    tint_hex = "#{:02x}{:02x}{:02x}".format(*tint_rgb)

    print("🎨 TEINTE CALCULÉE :")
    print("-" * 80)
    print(f"  MiddleColor (linear) : {middle_color}")
    print(f"  Color (linear)       : {color}")
    print(f"  Tint (sRGB)          : RGB{tint_rgb} = {tint_hex}")
    print()

    # Texture middle
    middle_map = params.get("BCRMiddleMap")
    if middle_map:
        middle_filename = parser.extract_filename_from_resource_name(middle_map)
        print("🖼️ TEXTURE MIDDLE :")
        print("-" * 80)
        print(f"  BCRMiddleMap         : {middle_map}")
        print(f"  Filename extrait     : {middle_filename}.jpg")
        print()
    else:
        bcr_map = params.get("BCRMap")
        if bcr_map:
            bcr_filename = parser.extract_filename_from_resource_name(bcr_map)
            print("🖼️ TEXTURE (FALLBACK BCRMap) :")
            print("-" * 80)
            print(f"  BCRMap               : {bcr_map}")
            print(f"  Filename extrait     : {bcr_filename}.jpg")
            print()
        else:
            print("⚠️ Aucune texture middle trouvée")
            print()

    # Tiling scale
    tiling_scale = params.get("MiddleScaleUV", "100")
    print("📏 TILING :")
    print("-" * 80)
    print(f"  MiddleScaleUV        : {tiling_scale} mètres")
    print()

    return params


def test_catalog_enrichment():
    """Test enrichissement complet du catalogue"""

    print("\n" + "="*80)
    print("TEST ENRICHISSEMENT CATALOGUE COMPLET")
    print("="*80 + "\n")

    catalog_root = Path("data/Textures_ArmaReforger")
    catalog_file = catalog_root / "catalog.json"
    vanilla = catalog_root / "Vanilla"
    customs = catalog_root / "Customs"

    # Charger catalogue avant
    with open(catalog_file, 'r', encoding='utf-8') as f:
        catalog_before = json.load(f)

    print(f"📊 Catalogue avant : {len(catalog_before)} surfaces")
    print()

    # Enrichir
    result = parser.enrich_catalog_with_emat_data(catalog_file, vanilla, customs)

    print(f"✅ Surfaces mises à jour : {result['updated_count']}")
    print()

    # Afficher warnings
    if result['warnings']:
        print(f"⚠️ AVERTISSEMENTS ({len(result['warnings'])}) :")
        print("-" * 80)
        for w in result['warnings']:
            print(f"  {w}")
        print()

    # Charger catalogue après
    with open(catalog_file, 'r', encoding='utf-8') as f:
        catalog_after = json.load(f)

    # Comparer quelques entrées
    print("📋 EXEMPLES D'ENRICHISSEMENT :")
    print("-" * 80)

    samples = [
        "Grass_01.emat",
        "Dirt_01.emat",
        "ForestConiferous_01_Base.emat",
        "ZI_Crop_Field_01.emat",
    ]

    for emat in samples:
        if emat in catalog_after:
            entry = catalog_after[emat]
            print(f"\n  {emat}")
            print(f"    middle_bcr    : {entry.get('middle_bcr', 'N/A')}")
            print(f"    tiling_scale  : {entry.get('tiling_scale', 'N/A')} m")
            print(f"    tint          : {entry.get('tint', 'N/A')}")
            print(f"    resolved      : {entry.get('resolved', 'N/A')}")

    print()

    return result


if __name__ == "__main__":
    catalog_root = Path("data/Textures_ArmaReforger")
    vanilla = catalog_root / "Vanilla"
    customs = catalog_root / "Customs"
    search_dirs = [vanilla, customs]

    print("\n" + "█"*80)
    print("█" + " "*78 + "█")
    print("█" + "  TEST PARSEUR .EMAT — Arma Reforger".center(78) + "█")
    print("█" + " "*78 + "█")
    print("█"*80)

    # ── Test 1 : Surfaces vanilla simples ──────────────────────────────────────

    print("\n\n┌─ TEST 1 : SURFACES VANILLA SIMPLES")
    print("└" + "─"*78)

    test_single_emat("Grass_01.emat", search_dirs)
    test_single_emat("Dirt_01.emat", search_dirs)
    test_single_emat("Concrete_01.emat", search_dirs)

    # ── Test 2 : Surfaces avec héritage parent ─────────────────────────────────

    print("\n\n┌─ TEST 2 : SURFACES AVEC HÉRITAGE PARENT")
    print("└" + "─"*78)

    test_single_emat("ForestConiferous_01_Base.emat", search_dirs)
    test_single_emat("ForestDeciduous_02.emat", search_dirs)
    test_single_emat("Grass_02_aut.emat", search_dirs)

    # ── Test 3 : Customs zi_ convention ────────────────────────────────────────

    print("\n\n┌─ TEST 3 : CUSTOMS ZI_ CONVENTION")
    print("└" + "─"*78)

    test_single_emat("ZI_Crop_Field_01.emat", search_dirs)
    test_single_emat("ZI_Ground_Sport_01.emat", search_dirs)

    # ── Test 4 : Surfaces avec teintes custom ──────────────────────────────────

    print("\n\n┌─ TEST 4 : SURFACES AVEC TEINTES CUSTOM")
    print("└" + "─"*78)

    test_single_emat("SulfurStream_01_bed.emat", search_dirs)

    # ── Test 5 : Enrichissement catalogue complet ───────────────────────────────

    print("\n\n┌─ TEST 5 : ENRICHISSEMENT CATALOGUE COMPLET")
    print("└" + "─"*78)

    test_catalog_enrichment()

    # ── Résumé final ────────────────────────────────────────────────────────────

    print("\n\n" + "█"*80)
    print("█" + " "*78 + "█")
    print("█" + "  FIN DES TESTS".center(78) + "█")
    print("█" + " "*78 + "█")
    print("█"*80 + "\n")
