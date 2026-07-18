"""
Test Satmap Simplifié - Workflow Priority 1
Lecture directe QTRE → Satmap 4k
"""

import sys
import io
from pathlib import Path

# Force UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import reforger_satmap_direct as satmap_direct


def main():
    print("\n" + "="*80)
    print("TEST SATMAP SIMPLE — LECTURE DIRECTE QTRE")
    print("="*80 + "\n")

    # Configuration
    world_terr = r"I:\reforger_travail\Zimnitrita_map\World\Zimnitrita\Terrain\Terrain.terr"
    output_dir = Path("output/satmap_simple")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Monde : {world_terr}")
    print(f"[INFO] Sortie : {output_dir}")
    print()

    # ── Test 1 : Mode couleurs (rapide) ────────────────────────────────────

    print("─"*80)
    print("TEST 1 : MODE COULEURS (rapide)")
    print("─"*80 + "\n")

    output_colors = output_dir / "satmap_colors.png"

    def progress_cb(msg, pct):
        print(f"  [{int(pct*100):3d}%] {msg}")

    result = satmap_direct.generate_satmap_from_world(
        world_terr_path=world_terr,
        output_path=output_colors,
        mode="colors",
        resolution=4097,
        progress_callback=progress_cb
    )

    print()
    print(f"[OK] Satmap couleurs : {result['resolution']} en {result['elapsed_sec']}s")
    print(f"     Fichier : {output_colors}")
    print(f"     Surfaces : {result['n_surfaces']}")
    print()

    # ── Test 2 : Mode texturé (qualité) ────────────────────────────────────

    print("─"*80)
    print("TEST 2 : MODE TEXTURE (qualite)")
    print("─"*80 + "\n")

    output_textured = output_dir / "satmap_textured.png"

    result = satmap_direct.generate_satmap_from_world(
        world_terr_path=world_terr,
        output_path=output_textured,
        mode="textured",
        resolution=4097,
        progress_callback=progress_cb
    )

    print()
    print(f"[OK] Satmap texturee : {result['resolution']} en {result['elapsed_sec']}s")
    print(f"     Fichier : {output_textured}")
    print(f"     Surfaces : {result['n_surfaces']}")
    print()

    # ── Résumé ──────────────────────────────────────────────────────────────

    print("="*80)
    print("TESTS TERMINES")
    print("="*80 + "\n")

    print("Fichiers generes :")
    print(f"  Satmap couleurs  : {output_colors}")
    print(f"  Satmap texturee  : {output_textured}")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERREUR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
