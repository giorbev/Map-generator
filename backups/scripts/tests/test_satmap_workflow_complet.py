"""
Test workflow complet : Export masques → Génération satmap
Pour Zimnitrita (16km, 128×128 blocs)
"""

import sys
import io
from pathlib import Path
import json
import time

# Force UTF-8 console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import reforger_mask_export as mask_export
import reforger_emat_parser as emat_parser
import reforger_satmap_generator as satmap_gen


def test_workflow_complet():
    """Test workflow complet satmap"""

    print("\n" + "="*80)
    print("TEST WORKFLOW COMPLET — SATMAP ZIMNITRITA")
    print("="*80 + "\n")

    # ── Configuration ───────────────────────────────────────────────────────

    # Chemin monde Zimnitrita
    world_terr_path = input(
        "Entrez le chemin du fichier .terr de Zimnitrita\n"
        "(ex: I:/reforger_travail/Zimnitrita_map/World/Zimnitrita/Terrain/Terrain.terr)\n"
        "> "
    ).strip().strip('"').strip("'")

    if not world_terr_path:
        print("Utilisation chemin par défaut (exemple)")
        world_terr_path = "I:/reforger_travail/Zimnitrita_map/World/Zimnitrita/Terrain/Terrain.terr"

    world_path = Path(world_terr_path)

    if not world_path.exists():
        print(f"\n❌ Fichier introuvable : {world_path}")
        print("Modifiez le chemin dans le script ou entrez le bon chemin.")
        return

    print(f"\n✅ Monde Reforger : {world_path}")

    # Dossier sortie
    output_root = Path("output/satmap_test")
    output_root.mkdir(parents=True, exist_ok=True)

    masks_dir = output_root / "masks"
    preview_dir = output_root / "preview"
    satmap_dir = output_root / "satmap"

    masks_dir.mkdir(exist_ok=True)
    preview_dir.mkdir(exist_ok=True)
    satmap_dir.mkdir(exist_ok=True)

    # ── Étape 1 : Enrichir catalogue avec parseur .emat ────────────────────

    print("\n" + "─"*80)
    print("ÉTAPE 1 : ENRICHISSEMENT CATALOGUE")
    print("─"*80 + "\n")

    catalog_root = Path("data/Textures_ArmaReforger")
    catalog_file = catalog_root / "catalog.json"
    vanilla = catalog_root / "Vanilla"
    customs = catalog_root / "Customs"

    print("[INFO] Scan .emat et enrichissement catalogue...")

    result = emat_parser.enrich_catalog_with_emat_data(
        catalog_file,
        vanilla,
        customs
    )

    print(f"[OK] {result['updated_count']} surfaces enrichies")

    if result['warnings']:
        print(f"[WARN] {len(result['warnings'])} avertissements")

    # ── Étape 2 : Export masques PNG ───────────────────────────────────────

    print("\n" + "─"*80)
    print("ÉTAPE 2 : EXPORT MASQUES PNG")
    print("─"*80 + "\n")

    print(f"[INFO] Export masques depuis : {world_path.parent}")
    print(f"[INFO] Vers : {masks_dir}")
    print()

    def progress_callback(msg, pct):
        print(f"  [{int(pct*100):3d}%] {msg}")

    start_time = time.time()

    try:
        export_result = mask_export.export_all_masks(
            world_dir=str(world_path.parent),
            out_dir=str(masks_dir),
            progress_callback=progress_callback
        )

        elapsed = time.time() - start_time

        print()
        print(f"[OK] Export terminé en {elapsed:.1f}s")
        print(f"     Surfaces exportées : {export_result['n_surfaces']}")
        print(f"     Résolution globale : {export_result['resolution']}")

        if export_result['warnings']:
            print(f"[WARN] {len(export_result['warnings'])} avertissements")
            # Afficher seulement les 10 premiers
            for w in export_result['warnings'][:10]:
                print(f"       {w}")
            if len(export_result['warnings']) > 10:
                print(f"       ... et {len(export_result['warnings']) - 10} autres")

    except Exception as e:
        print(f"\n❌ Erreur export masques : {e}")
        import traceback
        traceback.print_exc()
        return

    # ── Étape 3 : Preview couleurs (rapide) ────────────────────────────────

    print("\n" + "─"*80)
    print("ÉTAPE 3 : GÉNÉRATION PREVIEW COULEURS")
    print("─"*80 + "\n")

    # Charger catalogue
    with open(catalog_file, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    # Charger masques
    print("[INFO] Chargement masques depuis PNG...")
    masks = satmap_gen.load_masks_from_directory(masks_dir)
    print(f"[OK] {len(masks)} masques chargés")

    # Générer preview (résolution réduite pour rapidité)
    resolution_ppm = 0.5  # 0.5 px/m = moitié résolution
    output_preview = preview_dir / "preview_colors.png"

    print(f"[INFO] Génération preview couleurs ({resolution_ppm} px/m)...")

    start_time = time.time()

    result = satmap_gen.generate_satmap_colors(
        masks=masks,
        catalog=catalog,
        output_path=output_preview,
        resolution_ppm=resolution_ppm,
        progress_callback=None
    )

    elapsed = time.time() - start_time

    print(f"[OK] Preview générée : {result['resolution']} en {elapsed:.1f}s")
    print(f"     Fichier : {output_preview}")

    if result['warnings']:
        print(f"[WARN] {len(result['warnings'])} avertissements :")
        for w in result['warnings'][:5]:
            print(f"       {w}")

    # ── Étape 4 : Satmap texturée (qualité) ────────────────────────────────

    print("\n" + "─"*80)
    print("ÉTAPE 4 : GÉNÉRATION SATMAP TEXTURÉE")
    print("─"*80 + "\n")

    # Demander confirmation (peut être long)
    resolution_choice = input(
        "Quelle résolution pour la satmap finale ?\n"
        "  1 - 0.5 px/m (rapide, test)\n"
        "  2 - 1.0 px/m (standard)\n"
        "  3 - 2.0 px/m (haute qualité)\n"
        "> "
    ).strip()

    resolution_map = {
        "1": 0.5,
        "2": 1.0,
        "3": 2.0,
    }

    resolution_ppm = resolution_map.get(resolution_choice, 1.0)

    output_satmap = satmap_dir / f"satmap_textured_{resolution_ppm}ppm.png"

    print(f"\n[INFO] Génération satmap texturée ({resolution_ppm} px/m)...")
    print("[INFO] Cela peut prendre plusieurs minutes selon la résolution...")
    print()

    start_time = time.time()

    def progress_cb_satmap(msg, pct):
        print(f"  [{int(pct*100):3d}%] {msg}")

    try:
        result = satmap_gen.generate_satmap_textured(
            masks=masks,
            catalog=catalog,
            textures_root=catalog_root,
            output_path=output_satmap,
            resolution_ppm=resolution_ppm,
            band_height=512,
            progress_callback=progress_cb_satmap
        )

        elapsed = time.time() - start_time

        print()
        print(f"[OK] Satmap générée : {result['resolution']} en {elapsed:.1f}s")
        print(f"     Fichier : {output_satmap}")
        print(f"     Bandes : {result['n_bands']}")
        print(f"     Surfaces : {result['n_surfaces']}")

        if result['warnings']:
            print(f"[WARN] {len(result['warnings'])} avertissements :")
            for w in result['warnings'][:5]:
                print(f"       {w}")

    except Exception as e:
        print(f"\n❌ Erreur satmap texturée : {e}")
        import traceback
        traceback.print_exc()
        return

    # ── Résumé final ────────────────────────────────────────────────────────

    print("\n" + "="*80)
    print("WORKFLOW COMPLET TERMINÉ")
    print("="*80 + "\n")

    print("Fichiers générés :")
    print(f"  Masques PNG       : {masks_dir}")
    print(f"  Preview couleurs  : {output_preview}")
    print(f"  Satmap texturée   : {output_satmap}")
    print()


if __name__ == "__main__":
    try:
        test_workflow_complet()
    except KeyboardInterrupt:
        print("\n\n[INFO] Interrompu par l'utilisateur")
    except Exception as e:
        print(f"\n\n❌ Erreur fatale : {e}")
        import traceback
        traceback.print_exc()
