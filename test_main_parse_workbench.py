#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test parsing Workbench info depuis main.py
Vérifie que la fonction reportée fonctionne identique à la version testée
"""

import sys
from pathlib import Path

# Ajouter le dossier parent au path pour importer main
sys.path.insert(0, str(Path(__file__).parent))

# Importer main pour accéder à _session et MapGeneratorApp
import main as main_module

# Textes de test
text_a = """
Blocks and Tiles
Tiles:
32 x 32
Blocks per tile:
4 x 4

Height Map:
Tile: 129 x 129 vertices (512 x 512 m2)
Block: 33 x 33 vertices (128 x 128 m2)
Total: 16257 x 16257 vertices (16384 x 16384 m2)

Planar resolution:
4 m

Surface Map:
Tile resolution: 512 x 512 px
Total resolution: 16384 x 16384 px

Satellite Texture:
Tile resolution: 1024 x 1024 px

Normal Map:
Tile resolution: 512 x 512 px
"""

text_c = """
Blocks and Tiles
Tiles:
32 x 32
Blocks per tile:
4 x 4

Height Map:
Tile: 129 x 129 vertices (512 x 512 m2)
Block: 33 x 33 vertices (128 x 128 m2)

Planar resolution:
4 m

Satellite Texture:
Tile resolution: 1024 x 1024 px
"""

text_d = text_a.replace('\n', '\r\n')


def test_case(name: str, app, text: str, expected: dict):
    """Teste un cas et affiche le résultat."""
    print()
    print("="*80)
    print(f"TEST {name}")
    print("="*80)
    print()

    # Appeler la méthode
    result = app.parse_workbench_info(text)

    print()
    print("-"*80)
    print("RESULTAT :")
    print(f"  ok: {result['ok']}")
    if result['ok']:
        print(f"  grid_w: {result['grid_w']}")
        print(f"  num_blk: {result['num_blk']}")
        print(f"  cell_size: {result['cell_size']}")
        print(f"  tile_size_m: {result.get('tile_size_m')}")
        print(f"  surface_tile_px: {result.get('surface_tile_px')}")
        print(f"  echelle_m_per_px: {result.get('echelle_m_per_px')}")
        if result.get('warnings'):
            print(f"  warnings: {result['warnings']}")
    else:
        print(f"  error: {result.get('error')}")
    print("-"*80)
    print()

    # Vérifier
    success = True
    for key, expected_val in expected.items():
        actual_val = result.get(key)
        if actual_val != expected_val:
            print(f"[ERREUR] {key}: attendu {expected_val}, obtenu {actual_val}")
            success = False

    if success:
        print(f"[OK] Test {name} REUSSI")
    else:
        print(f"[ECHEC] Test {name} ECHOUE")
    print()
    return success


if __name__ == "__main__":
    print("="*80)
    print("TEST IMPORT parse_workbench_info DEPUIS main.py")
    print("="*80)
    print()

    # Créer une instance de Api (sans session réelle)
    # On va juste tester la méthode parse_workbench_info sans sauvegarder

    # Mock _session pour éviter erreur
    main_module._session = {
        "current_project_path": None,  # Pas de sauvegarde pour test
        "current_project": None,
        "session_log": []  # Pour _log
    }

    app = main_module.Api()

    # Exécuter tests
    results = []

    # Test (a)
    results.append(test_case(
        "A - Texte reel Workbench",
        app,
        text_a,
        {
            "ok": True,
            "grid_w": 32,
            "num_blk": 4,
            "cell_size": 4.0,
            "tile_size_m": 512,
            "surface_tile_px": 512,
            "echelle_m_per_px": 1.0
        }
    ))

    # Test (b) - même texte (déjà Satellite 1024)
    results.append(test_case(
        "B - Satellite 1024 (preuve bornage)",
        app,
        text_a,
        {
            "ok": True,
            "tile_size_m": 512,
            "surface_tile_px": 512,
            "echelle_m_per_px": 1.0
        }
    ))

    # Test (c)
    results.append(test_case(
        "C - Sans Surface Map",
        app,
        text_c,
        {
            "ok": True,
            "grid_w": 32,
            "num_blk": 4,
            "cell_size": 4.0,
            "tile_size_m": 512,
            "surface_tile_px": None,
            "echelle_m_per_px": None
        }
    ))

    # Test (d)
    results.append(test_case(
        "D - Avec \\r\\n (normalisation)",
        app,
        text_d,
        {
            "ok": True,
            "tile_size_m": 512,
            "surface_tile_px": 512,
            "echelle_m_per_px": 1.0
        }
    ))

    # Résumé
    print("="*80)
    print("RESUME TESTS")
    print("="*80)
    print()
    for i, success in enumerate(results, 1):
        status = "REUSSI" if success else "ECHOUE"
        print(f"Test {chr(64+i)} : {status}")
    print()

    all_success = all(results)
    if all_success:
        print("[OK] TOUS LES TESTS REUSSIS - main.py import OK")
    else:
        print("[ERREUR] CERTAINS TESTS ECHOUES - Corriger main.py")
