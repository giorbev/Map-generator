"""
Test workflow complet Zimnitrita
Version non-interactive avec chemin fixe
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


def main():
    print("\n" + "="*80)
    print("TEST WORKFLOW COMPLET — SATMAP ZIMNITRITA")
    print("="*80 + "\n")

    # ── Configuration ───────────────────────────────────────────────────────

    world_terr_path = r"I:\reforger_travail\Zimnitrita_map\World\Zimnitrita\Terrain\Terrain.terr"
    world_path = Path(world_terr_path)

    if not world_path.exists():
        print(f"\n[ERREUR] Fichier introuvable : {world_path}")
        return 1

    print(f"[INFO] Monde Reforger : {world_path}")
    print()

    # Dossier sortie
    output_root = Path("output/satmap_zimnitrita")
    output_root.mkdir(parents=True, exist_ok=True)

    # Note : export_all_masks() crée automatiquement masks/{timestamp}
    masks_export_root = output_root
    preview_dir = output_root / "preview"
    satmap_dir = output_root / "satmap"

    preview_dir.mkdir(exist_ok=True)
    satmap_dir.mkdir(exist_ok=True)

    # ── Étape 1 : Enrichir catalogue ───────────────────────────────────────

    print("─"*80)
    print("ETAPE 1/4 : ENRICHISSEMENT CATALOGUE")
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
        for w in result['warnings'][:3]:
            print(f"       {w}")

    # ── Étape 2 : Export masques ───────────────────────────────────────────

    print("\n" + "─"*80)
    print("ETAPE 2/4 : EXPORT MASQUES PNG (RESOLUTION REDUITE)")
    print("─"*80 + "\n")

    print(f"[INFO] Export masques depuis : {world_path.parent}")
    print(f"[INFO] Vers : {masks_export_root}/masks/{{timestamp}}")
    print(f"[INFO] Resolution : 4096x4096 (reduite pour economiser RAM)")
    print(f"[WARN] Export pleine resolution (16k) necessite 60GB RAM !")
    print()

    def progress_callback(msg, pct):
        if int(pct * 100) % 10 == 0:  # Afficher tous les 10%
            print(f"  [{int(pct*100):3d}%] {msg}")

    start_time = time.time()

    try:
        export_result = mask_export.export_all_masks(
            world_dir=str(world_path.parent),
            out_dir=str(masks_export_root),
            progress_callback=progress_callback
        )

        elapsed = time.time() - start_time

        # Récupérer le vrai chemin d'export (avec timestamp)
        masks_dir = Path(export_result['output_dir'])

        print()
        print(f"[OK] Export termine en {elapsed:.1f}s")
        print(f"     Surfaces exportees : {export_result['masks_exported']}")
        print(f"     Resolution globale : {export_result['resolution']}")
        print(f"     Dossier : {masks_dir}")

        if export_result.get('warnings'):
            n_warnings = len(export_result['warnings'])
            print(f"[WARN] {n_warnings} avertissements")
            if n_warnings > 0:
                print(f"       Premiers avertissements :")
                for w in export_result['warnings'][:5]:
                    print(f"         {w}")

    except Exception as e:
        print(f"\n[ERREUR] Export masques : {e}")
        import traceback
        traceback.print_exc()
        return 1

    # ── Étape 3 : Preview couleurs ─────────────────────────────────────────

    print("\n" + "─"*80)
    print("ETAPE 3/4 : GENERATION PREVIEW COULEURS")
    print("─"*80 + "\n")

    # Charger catalogue
    with open(catalog_file, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    # Charger masques
    print("[INFO] Chargement masques depuis PNG...")
    masks = satmap_gen.load_masks_from_directory(masks_dir)
    print(f"[OK] {len(masks)} masques charges")

    # Générer preview (résolution réduite)
    resolution_ppm = 0.5  # 0.5 px/m = rapide
    output_preview = preview_dir / "preview_colors.png"

    print(f"[INFO] Generation preview couleurs ({resolution_ppm} px/m)...")

    start_time = time.time()

    result = satmap_gen.generate_satmap_colors(
        masks=masks,
        catalog=catalog,
        output_path=output_preview,
        resolution_ppm=resolution_ppm,
        progress_callback=None
    )

    elapsed = time.time() - start_time

    print(f"[OK] Preview generee : {result['resolution']} en {elapsed:.1f}s")
    print(f"     Fichier : {output_preview}")

    # ── Étape 4 : Satmap texturée ──────────────────────────────────────────

    print("\n" + "─"*80)
    print("ETAPE 4/4 : GENERATION SATMAP TEXTUREE")
    print("─"*80 + "\n")

    resolution_ppm = 1.0  # 1 px/m = standard (16384×16384 pour Zimnitrita)
    output_satmap = satmap_dir / f"satmap_textured_{resolution_ppm}ppm.png"

    print(f"[INFO] Generation satmap texturee ({resolution_ppm} px/m)...")
    print("[INFO] Cela peut prendre 2-5 minutes...")
    print()

    start_time = time.time()

    def progress_cb_satmap(msg, pct):
        if int(pct * 100) % 5 == 0:  # Afficher tous les 5%
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
        print(f"[OK] Satmap generee : {result['resolution']} en {elapsed:.1f}s ({elapsed/60:.1f} min)")
        print(f"     Fichier : {output_satmap}")
        print(f"     Bandes : {result['n_bands']}")
        print(f"     Surfaces : {result['n_surfaces']}")

        if result.get('warnings'):
            print(f"[WARN] {len(result['warnings'])} avertissements")

    except Exception as e:
        print(f"\n[ERREUR] Satmap texturee : {e}")
        import traceback
        traceback.print_exc()
        return 1

    # ── Résumé ──────────────────────────────────────────────────────────────

    print("\n" + "="*80)
    print("WORKFLOW TERMINE !")
    print("="*80 + "\n")

    print("Fichiers generes :")
    print(f"  Masques PNG       : {masks_dir}")
    print(f"  Preview couleurs  : {output_preview}")
    print(f"  Satmap texturee   : {output_satmap}")
    print()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n[INFO] Interrompu par utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERREUR] Fatale : {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
