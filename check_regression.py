#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_regression.py - Script de non-regression Map Generator Pro

Commandes :
  python check_regression.py valider-script --projet <nom>
  python check_regression.py enregistrer --projet <nom>
  python check_regression.py comparer --projet <nom>
  python check_regression.py comparer --projet tous
  python check_regression.py tester-detection --projet <nom>

Usage :
  - valider-script : Compare les sorties du script aux sorties actuelles de l'app (test)
  - enregistrer : Enregistre une reference dans data/projects/<nom>/test/
  - comparer : Compare la generation actuelle a la reference
  - tester-detection : Auto-test de la detection (falsifie la reference et verifie detection KO)
"""

import sys
import json
import hashlib
import tempfile
import subprocess
import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

# Imports modules existants
from catalog_config import get_catalog_path, TEXTURES_USER_DIR
import project_reader
from terrain_terr_reader import build_id_to_name
from tile_inspector import export_json as tile_inspector_export_json
from satmap_v2_textured_v2 import generate_satmap_v2_textured_complete

# Racine du projet
REPO_ROOT = Path(__file__).resolve().parent
PROJECTS_DIR = REPO_ROOT / "data" / "projects"


# ===============================================================================
# UTILITAIRES STANDALONE (COPIES TEMPORAIRES DE main.py)
# ===============================================================================

def get_project_grid(project_path: Path) -> dict:
    """
    Lit la configuration grille depuis project.json via project_reader.

    Returns:
        {"ok": True, "grid_w": int, "num_blk": int, "surface_tile_px": int, "tile_size_m": int}
        ou {"ok": False, "missing": [str], "error": str}
    """
    result = project_reader.get_grid(project_path)

    if result.get("ok"):
        # Retourner seulement les 4 clés (comme avant)
        return {
            "ok": True,
            "grid_w": result["grid_w"],
            "num_blk": result["num_blk"],
            "surface_tile_px": result["surface_tile_px"],
            "tile_size_m": result["tile_size_m"],
        }

    return result


def get_terrain_dirs(project_path: Path) -> dict:
    """
    Retourne les dossiers terrain (.Data, .EditorData) et surfaces depuis le projet via project_reader.
    """
    # Résolution des chemins terrain via project_reader
    result = project_reader.get_terrain_dirs(project_path)
    if not result.get("ok"):
        return result

    terr_file = result.get("terr_file")
    if not terr_file:
        return {"ok": False, "error": f"Aucun fichier .terr trouve dans {result.get('terrain_dir')}"}

    # Charger table materiaux depuis .terr
    terr_path = Path(terr_file)
    try:
        mat_id_to_name = build_id_to_name(terr_path)
    except Exception as e:
        return {"ok": False, "error": f"Erreur lecture .terr : {e}"}

    if not mat_id_to_name:
        return {"ok": False, "error": "Table materiaux vide"}

    max_id = max(mat_id_to_name.keys())
    surfaces = [mat_id_to_name.get(i, f"MAT_{i}") for i in range(max_id + 1)]

    return {
        "ok": True,
        "terrain_dir": result["terrain_dir"],
        "data_dir": result["data_dir"],
        "editor_dir": result["editor_dir"],
        "surfaces": surfaces,
        "terr_file": terr_file,
    }


def get_tile_grid(project_path: Path) -> dict:
    """
    Retourne la configuration grille + detection du prefixe des .ttile via project_reader.

    Returns:
        {"ok": True, "grid_w", "num_blk", "surface_tile_px", "tile_size_m", "tile_prefix": str, "dirs": dict}
        ou {"ok": False, "error": str}
    """
    # Lire grille depuis project_reader
    grid = get_project_grid(project_path)
    if not grid.get("ok"):
        return grid

    # Obtenir dirs terrain
    dirs = get_terrain_dirs(project_path)
    if not dirs["ok"]:
        return {"ok": False, "error": dirs["error"]}

    # Détecter préfixe via project_reader
    prefix_result = project_reader.get_tile_prefix(Path(dirs["data_dir"]))
    if not prefix_result.get("ok"):
        return prefix_result

    return {
        "ok": True,
        "grid_w": grid["grid_w"],
        "num_blk": grid["num_blk"],
        "surface_tile_px": grid["surface_tile_px"],
        "tile_size_m": grid["tile_size_m"],
        "tile_prefix": prefix_result["tile_prefix"],
        "dirs": dirs,
    }


def get_middles_dir() -> Optional[Path]:
    """
    COPIE TEMPORAIRE de main.py:generate_satmap_v2() logique middles_dir - a remplacer par le module commun (prompt A)

    Resolution middles_dir avec fallback.
    """
    # Pour le moment, pas de middles_dir_str configure -> fallback direct
    fallback = TEXTURES_USER_DIR / "texture_Middle"
    if fallback.exists():
        return fallback
    return None


def get_block_budget(project_path: Path) -> dict:
    """
    Lit pipeline.reforger_block_limit depuis project.json via project_reader.

    Returns:
        {"ok": True, "value": int} ou {"ok": False, "error": str}
    """
    budget = project_reader.get_block_budget(project_path)

    if budget is None:
        return {"ok": False, "error": "Budget de textures par bloc non defini : choisissez 5 ou 7 dans la configuration du projet."}
    if budget not in (5, 7):
        return {"ok": False, "error": f"Budget invalide : {budget} (attendu : 5 ou 7)"}

    return {"ok": True, "value": budget}


# ===============================================================================
# GENERATION
# ===============================================================================

def generate_satmap_in_temp(project_path: Path, temp_dir: Path) -> dict:
    """
    Genere la satmap Native dans un dossier temporaire.

    Returns:
        {"ok": True, "output_path": Path} ou {"ok": False, "error": str}
    """
    grid = get_tile_grid(project_path)
    if not grid.get("ok"):
        return {"ok": False, "error": grid["error"]}

    terrain_dir = Path(grid["dirs"]["terrain_dir"])
    terr_file = grid["dirs"]["terr_file"]

    catalog_path = get_catalog_path()
    if not catalog_path.exists():
        return {"ok": False, "error": f"catalog.json introuvable : {catalog_path}"}

    # Calculer echelle
    echelle_m_per_px = grid["tile_size_m"] / grid["surface_tile_px"]

    # middles_dir
    middles_dir = get_middles_dir()

    # emat_dir
    emat_dir = TEXTURES_USER_DIR / "emat"

    # Chemin sortie temporaire
    temp_output = temp_dir / "satmap_temp.png"

    try:
        stats = generate_satmap_v2_textured_complete(
            terrain_dir, catalog_path, temp_output,
            grid["grid_w"], grid["num_blk"],
            terr_file=terr_file, mode="textured",
            target_resolution=None, verbose=False,
            middles_dir=middles_dir,
            emat_dir=emat_dir,
            echelle_m_per_px=echelle_m_per_px
        )
    except Exception as e:
        return {"ok": False, "error": f"Erreur generation satmap : {e}"}

    if not stats or "output_path" not in stats:
        return {"ok": False, "error": "Fichier satmap non genere"}

    output_path = Path(stats["output_path"])
    if not output_path.exists():
        return {"ok": False, "error": f"Fichier non trouve : {output_path}"}

    return {"ok": True, "output_path": output_path}


def generate_scan_in_temp(project_path: Path, temp_dir: Path) -> dict:
    """
    Genere le scan QTRE dans un dossier temporaire.

    Returns:
        {"ok": True, "output_path": Path} ou {"ok": False, "error": str}
    """
    grid = get_tile_grid(project_path)
    if not grid.get("ok"):
        return {"ok": False, "error": grid["error"]}

    budget = get_block_budget(project_path)
    if not budget.get("ok"):
        return {"ok": False, "error": budget["error"]}

    data_dir = Path(grid["dirs"]["data_dir"])
    cache_json = temp_dir / "qtre_scan_temp.json"

    try:
        tile_inspector_export_json(
            data_dir, cache_json,
            grid["grid_w"], grid["num_blk"], grid["tile_prefix"],
            budget["value"]
        )
    except Exception as e:
        return {"ok": False, "error": f"Erreur scan QTRE : {e}"}

    if not cache_json.exists():
        return {"ok": False, "error": f"Fichier scan non genere : {cache_json}"}

    return {"ok": True, "output_path": cache_json}


# ===============================================================================
# COMPARAISON
# ===============================================================================

def hash_png_pixels(png_path: Path) -> dict:
    """
    Calcule SHA256 des pixels DECODES d'un PNG.

    Returns:
        {"hash": str, "shape": tuple, "dtype": str}
    """
    import cv2

    img = cv2.imread(str(png_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Impossible de lire {png_path}")

    # Hash des bytes bruts des pixels
    pixel_hash = hashlib.sha256(img.tobytes()).hexdigest()

    return {
        "hash": pixel_hash,
        "shape": img.shape,
        "dtype": str(img.dtype)
    }


def compare_scan_json(json1_path: Path, json2_path: Path) -> dict:
    """
    Compare deux fichiers qtre_scan.json en ignorant generated_at.

    Structure attendue :
    {
      "tiles": [{"tid": int, "tx": int, "ty": int, "max_tex_per_block": int, ...}, ...],
      "generated_at": str,
      "project": str
    }

    Returns:
        {
            "identical": bool,
            "diff_tiles": [{"tid": int, "fields": [str]}] ou None,  # Max 30 tuiles
            "total_diff_tiles": int,
            "tiles_only_in_ref": [int] ou None,     # tids absents de current
            "tiles_only_in_current": [int] ou None, # tids absents de ref
            "diff_project": {"ref": str, "current": str} ou None,
            "diff_toplevel": [str] ou None,  # Cles de premier niveau ajoutees/supprimees
            "error": str ou None
        }
    """
    try:
        data1 = json.loads(json1_path.read_text(encoding="utf-8"))
        data2 = json.loads(json2_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"identical": False, "error": f"Erreur lecture JSON : {e}"}

    # Retirer generated_at
    data1.pop("generated_at", None)
    data2.pop("generated_at", None)

    if data1 == data2:
        return {
            "identical": True,
            "diff_tiles": None,
            "total_diff_tiles": 0,
            "tiles_only_in_ref": None,
            "tiles_only_in_current": None,
            "diff_project": None,
            "diff_toplevel": None,
            "error": None
        }

    result = {
        "identical": False,
        "diff_tiles": [],
        "total_diff_tiles": 0,
        "tiles_only_in_ref": None,
        "tiles_only_in_current": None,
        "diff_project": None,
        "diff_toplevel": [],
        "error": None
    }

    # Comparer cles de premier niveau (hors tiles, generated_at)
    keys1 = set(data1.keys()) - {"tiles"}
    keys2 = set(data2.keys()) - {"tiles"}

    added = keys2 - keys1
    removed = keys1 - keys2
    if added or removed:
        for k in sorted(added):
            result["diff_toplevel"].append(f"+{k}")
        for k in sorted(removed):
            result["diff_toplevel"].append(f"-{k}")

    # Comparer project
    if "project" in data1 and "project" in data2:
        if data1["project"] != data2["project"]:
            result["diff_project"] = {"ref": data1["project"], "current": data2["project"]}

    # Comparer tiles
    tiles1 = data1.get("tiles", [])
    tiles2 = data2.get("tiles", [])

    if not isinstance(tiles1, list) or not isinstance(tiles2, list):
        result["error"] = f"Format tiles invalide : attendu list, recu {type(tiles1).__name__} vs {type(tiles2).__name__}"
        return result

    # Indexer par tid
    tiles1_by_tid = {}
    for t in tiles1:
        if isinstance(t, dict) and "tid" in t:
            tiles1_by_tid[t["tid"]] = t

    tiles2_by_tid = {}
    for t in tiles2:
        if isinstance(t, dict) and "tid" in t:
            tiles2_by_tid[t["tid"]] = t

    tids1 = set(tiles1_by_tid.keys())
    tids2 = set(tiles2_by_tid.keys())

    only_in_ref = sorted(tids1 - tids2)
    only_in_current = sorted(tids2 - tids1)
    common = sorted(tids1 & tids2)

    if only_in_ref:
        result["tiles_only_in_ref"] = only_in_ref[:30]
    if only_in_current:
        result["tiles_only_in_current"] = only_in_current[:30]

    # Comparer tuiles communes
    diff_tiles_full = []
    for tid in common:
        t1 = tiles1_by_tid[tid]
        t2 = tiles2_by_tid[tid]

        if t1 != t2:
            # Trouver les champs differents
            all_keys = set(t1.keys()) | set(t2.keys())
            diff_fields = []
            for k in sorted(all_keys):
                if t1.get(k) != t2.get(k):
                    diff_fields.append(k)

            diff_tiles_full.append({"tid": tid, "fields": diff_fields})

    result["total_diff_tiles"] = len(diff_tiles_full) + len(only_in_ref) + len(only_in_current)
    result["diff_tiles"] = diff_tiles_full[:30]  # Max 30 pour affichage

    return result


def create_diff_thumbnail(ref_thumb_path: Path, current_satmap_path: Path, output_path: Path, grid_w: int = 32) -> dict:
    """
    Cree une miniature de difference entre la reference et la satmap actuelle.

    Args:
        ref_thumb_path: Miniature de reference (test/satmap_thumb.png)
        current_satmap_path: Satmap actuelle (full resolution)
        output_path: Chemin de sortie (test/diff_thumb.png)
        grid_w: Largeur grille (pour calculer rectangle englobant)

    Returns:
        {
            "ok": bool,
            "bbox_tiles": {"x_min": int, "x_max": int, "y_min": int, "y_max": int} ou None,
            "error": str ou None
        }
    """
    import cv2
    import numpy as np

    try:
        # Lire reference
        ref = cv2.imread(str(ref_thumb_path), cv2.IMREAD_UNCHANGED)
        if ref is None:
            return {"ok": False, "bbox_tiles": None, "error": "Miniature reference illisible"}

        # Lire satmap actuelle et redimensionner a la taille de ref
        current = cv2.imread(str(current_satmap_path), cv2.IMREAD_UNCHANGED)
        if current is None:
            return {"ok": False, "bbox_tiles": None, "error": "Satmap actuelle illisible"}

        h_ref, w_ref = ref.shape[:2]
        current_resized = cv2.resize(current, (w_ref, h_ref), interpolation=cv2.INTER_AREA)

        # Calculer difference absolue
        diff = cv2.absdiff(ref, current_resized)

        # Amplifier pour visibilite (x5)
        diff_amp = np.clip(diff.astype(np.float32) * 5.0, 0, 255).astype(np.uint8)

        cv2.imwrite(str(output_path), diff_amp)

        # Calculer rectangle englobant de la difference (seuil: 10)
        if len(diff.shape) == 3:
            diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        else:
            diff_gray = diff

        mask = diff_gray > 10
        if not mask.any():
            # Pas de difference visible
            return {"ok": True, "bbox_tiles": None, "error": None}

        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]

        # Convertir en coordonnees de tuiles
        tile_h = h_ref / grid_w
        tile_w = w_ref / grid_w

        bbox_tiles = {
            "x_min": int(x_min / tile_w),
            "x_max": int(x_max / tile_w),
            "y_min": int(y_min / tile_h),
            "y_max": int(y_max / tile_h)
        }

        return {"ok": True, "bbox_tiles": bbox_tiles, "error": None}

    except Exception as e:
        return {"ok": False, "bbox_tiles": None, "error": str(e)}


def get_tile_coords_approximate(grid_w: int, diff_tiles: list) -> str:
    """
    Convertit les IDs de tuiles differentes en coordonnees approximatives.

    Args:
        grid_w: Largeur de la grille (ex: 32)
        diff_tiles: Liste d'IDs de tuiles (ex: [0, 1, 33])

    Returns:
        Chaine descriptive des zones (ex: "zone (0,0)-(1,1)")
    """
    if not diff_tiles:
        return "aucune"

    coords = []
    for tid in diff_tiles[:10]:  # Max 10 pour l'affichage
        try:
            tile_id = int(tid)
            x = tile_id % grid_w
            y = tile_id // grid_w
            coords.append(f"({x},{y})")
        except (ValueError, TypeError):
            continue

    if len(diff_tiles) > 10:
        coords.append(f"... +{len(diff_tiles)-10} autres")

    return ", ".join(coords)


# ===============================================================================
# UTILITAIRES ENREGISTREMENT
# ===============================================================================

def create_satmap_thumbnail(png_path: Path, output_path: Path, max_size: int = 2048) -> bool:
    """
    Cree une miniature d'une satmap avec cv2.resize (pas de limite taille).

    Args:
        png_path: Chemin PNG source
        output_path: Chemin PNG destination
        max_size: Taille maximale du plus grand cote

    Returns:
        True si succes, False sinon
    """
    import cv2

    try:
        img = cv2.imread(str(png_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            return False

        h, w = img.shape[:2]
        if max(h, w) <= max_size:
            # Deja assez petit, copie directe
            cv2.imwrite(str(output_path), img)
            return True

        # Calculer nouvelles dimensions
        if h > w:
            new_h = max_size
            new_w = int(w * max_size / h)
        else:
            new_w = max_size
            new_h = int(h * max_size / w)

        # Resize avec INTER_AREA (meilleur pour downscale)
        thumb = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(output_path), thumb)
        return True

    except Exception as e:
        print(f"      Erreur creation miniature : {e}")
        return False


def get_git_commit() -> Optional[str]:
    """
    Retourne le commit git courant (HEAD).

    Returns:
        SHA du commit ou None si erreur
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


# ===============================================================================
# COMMANDES
# ===============================================================================

def cmd_valider_script(project_name: str) -> int:
    """
    Commande valider-script : compare les sorties du script aux sorties actuelles de l'app.
    Traitement independant satmap / scan.

    Returns:
        0 si OK, 1 si KO
    """
    project_path = PROJECTS_DIR / project_name
    if not project_path.exists():
        print(f"[KO] Projet introuvable : {project_path}")
        return 1

    print(f"=== Validation script sur projet : {project_name} ===")
    print(f"    Projet : {project_path}")
    print()

    # Chemins sorties app
    app_satmap = project_path / "outputs" / "generated" / "satmap_v2_textured_native.png"
    app_scan = project_path / "outputs" / "cache" / "qtre_scan.json"

    # Generer avec le script (traitement independant)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        satmap_ok = None
        scan_ok = None

        # === SATMAP ===
        if app_satmap.exists():
            print(f"[OK] Satmap app : {app_satmap}")
            print("     Generation satmap avec le script...")
            result = generate_satmap_in_temp(project_path, temp_path)
            if not result["ok"]:
                print(f"     [KO] Erreur generation : {result['error']}")
                satmap_ok = False
            else:
                script_satmap = result["output_path"]
                print(f"     [OK] Genere : {script_satmap.name}")

                print("     Comparaison satmap (pixels decodes)...")
                try:
                    app_hash = hash_png_pixels(app_satmap)
                    script_hash = hash_png_pixels(script_satmap)

                    satmap_ok = (app_hash["hash"] == script_hash["hash"] and
                                app_hash["shape"] == script_hash["shape"])

                    if satmap_ok:
                        print(f"     [OK] IDENTIQUES (hash: {app_hash['hash'][:16]}...)")
                    else:
                        print(f"     [KO] DIFFERENTES")
                        print(f"          App    : {app_hash['hash'][:16]}... | shape: {app_hash['shape']}")
                        print(f"          Script : {script_hash['hash'][:16]}... | shape: {script_hash['shape']}")
                except Exception as e:
                    print(f"     [KO] Erreur comparaison : {e}")
                    satmap_ok = False
        else:
            print(f"[!!] Satmap app absente : {app_satmap}")
            print("     -> Generez d'abord la satmap Native depuis l'app")

        print()

        # === SCAN ===
        if app_scan.exists():
            print(f"[OK] Scan app   : {app_scan}")
            print("     Generation scan avec le script...")
            result = generate_scan_in_temp(project_path, temp_path)
            if not result["ok"]:
                print(f"     [KO] Erreur generation : {result['error']}")
                scan_ok = False
            else:
                script_scan = result["output_path"]
                print(f"     [OK] Genere : {script_scan.name}")

                print("     Comparaison scan (JSON sans generated_at)...")
                try:
                    cmp = compare_scan_json(app_scan, script_scan)
                    if cmp.get("error"):
                        print(f"     [KO] Erreur : {cmp['error']}")
                        scan_ok = False
                    else:
                        scan_ok = cmp["identical"]
                        if scan_ok:
                            print(f"     [OK] IDENTIQUES")
                        else:
                            print(f"     [KO] DIFFERENTS")
                except Exception as e:
                    print(f"     [KO] Erreur comparaison : {e}")
                    scan_ok = False
        else:
            print(f"[!!] Scan app absent : {app_scan}")
            print("     -> Lancez d'abord le scan QTRE depuis l'app")

        print()
        print("=" * 70)

        # Bilan
        if satmap_ok is None and scan_ok is None:
            print("[KO] VALIDATION IMPOSSIBLE - Aucune sortie app disponible")
            print("=" * 70)
            return 1
        elif satmap_ok and scan_ok:
            print("[OK] VALIDATION OK - Le script genere les memes sorties que l'app")
            print("=" * 70)
            return 0
        elif satmap_ok is False or scan_ok is False:
            print("[KO] VALIDATION KO - Differences ou erreurs detectees")
            if satmap_ok is False:
                print("     Satmap : [KO]")
            if scan_ok is False:
                print("     Scan   : [KO]")
            print("=" * 70)
            return 1
        else:
            print("[!!] VALIDATION PARTIELLE")
            if satmap_ok:
                print("     Satmap : [OK]")
            if scan_ok:
                print("     Scan   : [OK]")
            print("=" * 70)
            return 0


def cmd_enregistrer(project_name: str) -> int:
    """
    Commande enregistrer : enregistre une reference dans data/projects/<nom>/test/
    Traitement independant satmap / scan.

    Returns:
        0 si OK, 1 si erreurs
    """
    project_path = PROJECTS_DIR / project_name
    if not project_path.exists():
        print(f"[KO] Projet introuvable : {project_path}")
        return 1

    print(f"=== Enregistrement reference pour projet : {project_name} ===")
    print(f"    Projet : {project_path}")
    print()

    test_dir = project_path / "test"

    # Verification si test/ existe deja
    if test_dir.exists():
        manifest_path = test_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                print(f"[!!] Reference existante detectee :")
                print(f"     Date : {manifest.get('date', 'inconnue')}")
                print(f"     Commit : {manifest.get('commit', 'inconnu')[:16]}...")
                print(f"     Fichiers dans test/ : {list(test_dir.glob('*'))}")
            except Exception:
                print(f"[!!] Dossier test/ existe (manifest.json illisible)")
        else:
            print(f"[!!] Dossier test/ existe sans manifest.json")

        print()
        reponse = input("     Ecraser la reference existante ? (o/N) : ").strip().lower()
        if reponse != 'o':
            print("[--] Annule")
            return 0
        print()

    # Creer test/
    test_dir.mkdir(parents=True, exist_ok=True)

    # Preparer manifest
    manifest = {
        "date": datetime.now().isoformat(),
        "commit": get_git_commit(),
        "project": project_name,
        "elements": {}
    }

    # Generer avec le script (traitement independant)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        satmap_success = False
        scan_success = False

        # === SATMAP ===
        print("=== SATMAP ===")
        result = generate_satmap_in_temp(project_path, temp_path)
        if not result["ok"]:
            print(f"[KO] Erreur generation : {result['error']}")
            manifest["elements"]["satmap"] = {"status": "error", "error": result["error"]}
        else:
            satmap_temp = result["output_path"]
            print(f"[OK] Genere : {satmap_temp.name}")

            # Hash
            try:
                satmap_hash_data = hash_png_pixels(satmap_temp)
                hash_json = test_dir / "satmap_hash.json"
                hash_json.write_text(json.dumps(satmap_hash_data, indent=2), encoding="utf-8")
                print(f"     [OK] Hash enregistre : {hash_json}")

                # Miniature
                thumb_path = test_dir / "satmap_thumb.png"
                if create_satmap_thumbnail(satmap_temp, thumb_path, max_size=2048):
                    print(f"     [OK] Miniature enregistree : {thumb_path}")
                    satmap_success = True
                    # CORRECTION PHASE 2A : ne pas dupliquer le hash dans manifest
                    manifest["elements"]["satmap"] = {"status": "ok"}
                else:
                    print(f"     [KO] Erreur creation miniature")
                    manifest["elements"]["satmap"] = {"status": "error", "error": "Erreur creation miniature"}
            except Exception as e:
                print(f"     [KO] Erreur traitement : {e}")
                manifest["elements"]["satmap"] = {"status": "error", "error": str(e)}

        print()

        # === SCAN ===
        print("=== SCAN ===")
        result = generate_scan_in_temp(project_path, temp_path)
        if not result["ok"]:
            print(f"[KO] Erreur generation : {result['error']}")
            manifest["elements"]["scan"] = {"status": "error", "error": result["error"]}
        else:
            scan_temp = result["output_path"]
            print(f"[OK] Genere : {scan_temp.name}")

            try:
                # Copie complete
                scan_json = test_dir / "qtre_scan.json"
                scan_json.write_text(scan_temp.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"     [OK] Scan enregistre : {scan_json}")

                scan_success = True
                manifest["elements"]["scan"] = {"status": "ok"}
            except Exception as e:
                print(f"     [KO] Erreur copie : {e}")
                manifest["elements"]["scan"] = {"status": "error", "error": str(e)}

        print()

    # Ecrire manifest
    manifest_path = test_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Manifest enregistre : {manifest_path}")

    print()
    print("=" * 70)

    # Bilan (un seul message selon le cas)
    if satmap_success and scan_success:
        print("[OK] ENREGISTREMENT TERMINE")
        print("     Satmap : [OK]")
        print("     Scan   : [OK]")
    else:
        print("[!!] ENREGISTREMENT PARTIEL")
        if satmap_success:
            print("     Satmap : [OK]")
        else:
            print("     Satmap : [KO]")
        if scan_success:
            print("     Scan   : [OK]")
        else:
            print("     Scan   : [KO]")

    print("=" * 70)
    return 0 if (satmap_success and scan_success) else 1


def cmd_comparer_project(project_name: str, project_path: Path, ref_dir: Optional[Path] = None) -> dict:
    """
    Compare un projet a sa reference.

    Args:
        project_name: Nom du projet
        project_path: Chemin du projet
        ref_dir: Dossier de reference a utiliser (par defaut: project_path/test)

    Returns:
        {
            "project": str,
            "has_test": bool,
            "satmap_status": "ok" | "ko" | "skip" | "error",
            "satmap_detail": str,
            "scan_status": "ok" | "ko" | "skip" | "error",
            "scan_detail": str
        }
    """
    test_dir = ref_dir if ref_dir else (project_path / "test")
    if not test_dir.exists():
        return {
            "project": project_name,
            "has_test": False,
            "satmap_status": "skip",
            "satmap_detail": "Pas de reference (dossier test/ absent)",
            "scan_status": "skip",
            "scan_detail": "Pas de reference (dossier test/ absent)",
        }

    # Lire manifest
    manifest_path = test_dir / "manifest.json"
    if not manifest_path.exists():
        return {
            "project": project_name,
            "has_test": True,
            "satmap_status": "skip",
            "satmap_detail": "Manifest absent",
            "scan_status": "skip",
            "scan_detail": "Manifest absent",
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "project": project_name,
            "has_test": True,
            "satmap_status": "skip",
            "satmap_detail": f"Erreur lecture manifest : {e}",
            "scan_status": "skip",
            "scan_detail": f"Erreur lecture manifest : {e}",
        }

    elements = manifest.get("elements", {})

    # Lire grille pour les coordonnees
    grid = get_project_grid(project_path)
    grid_w = grid.get("grid_w", 32) if grid.get("ok") else 32

    result = {
        "project": project_name,
        "has_test": True,
        "satmap_status": "skip",
        "satmap_detail": "",
        "scan_status": "skip",
        "scan_detail": "",
    }

    # === SATMAP ===
    satmap_ref = elements.get("satmap", {})
    if satmap_ref.get("status") == "error":
        result["satmap_status"] = "skip"
        result["satmap_detail"] = f"Reference en erreur : {satmap_ref.get('error', 'inconnue')}"
    else:
        # CORRECTION PHASE 2A : lire hash depuis satmap_hash.json (source unique)
        hash_json = test_dir / "satmap_hash.json"
        if not hash_json.exists():
            result["satmap_status"] = "error"
            result["satmap_detail"] = "Fichier satmap_hash.json absent"
        else:
            # Generer satmap actuelle
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                gen_result = generate_satmap_in_temp(project_path, temp_path)

                if not gen_result["ok"]:
                    result["satmap_status"] = "ko"
                    result["satmap_detail"] = f"Erreur generation : {gen_result['error']}"
                else:
                    current_satmap = gen_result["output_path"]

                    # Comparer hash
                    try:
                        ref_hash_data = json.loads(hash_json.read_text(encoding="utf-8"))
                        current_hash = hash_png_pixels(current_satmap)
                        ref_hash = ref_hash_data.get("hash", "")

                        if current_hash["hash"] == ref_hash:
                            result["satmap_status"] = "ok"
                            result["satmap_detail"] = "Identique a la reference"
                        else:
                            result["satmap_status"] = "ko"
                            result["satmap_detail"] = f"Difference detectee (hash: {current_hash['hash'][:16]}... vs ref: {ref_hash[:16]}...)"

                            # Creer diff_thumb.png avec rectangle englobant
                            ref_thumb = test_dir / "satmap_thumb.png"
                            diff_thumb = test_dir / "diff_thumb.png"
                            if ref_thumb.exists():
                                diff_result = create_diff_thumbnail(ref_thumb, current_satmap, diff_thumb, grid_w)
                                if diff_result["ok"]:
                                    result["satmap_detail"] += f" | diff_thumb.png cree"
                                    if diff_result["bbox_tiles"]:
                                        bbox = diff_result["bbox_tiles"]
                                        result["satmap_detail"] += f" | zone tuiles: ({bbox['x_min']},{bbox['y_min']})-({bbox['x_max']},{bbox['y_max']})"
                                    else:
                                        result["satmap_detail"] += " | difference plus fine que la resolution de la miniature"

                    except Exception as e:
                        result["satmap_status"] = "error"
                        result["satmap_detail"] = f"[ERREUR] Comparaison : {e}"

    # === SCAN ===
    scan_ref = elements.get("scan", {})
    if scan_ref.get("status") == "error":
        result["scan_status"] = "skip"
        result["scan_detail"] = f"Reference en erreur : {scan_ref.get('error', 'inconnue')}"
    else:
        ref_scan = test_dir / "qtre_scan.json"
        if not ref_scan.exists():
            result["scan_status"] = "skip"
            result["scan_detail"] = "Fichier de reference absent"
        else:
            # Generer scan actuel
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                gen_result = generate_scan_in_temp(project_path, temp_path)

                if not gen_result["ok"]:
                    result["scan_status"] = "ko"
                    result["scan_detail"] = f"Erreur generation : {gen_result['error']}"
                else:
                    current_scan = gen_result["output_path"]

                    # Comparer
                    try:
                        cmp = compare_scan_json(ref_scan, current_scan)

                        # CORRECTION PHASE 2B : distinguer erreur de vraie difference
                        if cmp.get("error"):
                            result["scan_status"] = "error"
                            result["scan_detail"] = f"[ERREUR] {cmp['error']}"
                        elif cmp["identical"]:
                            result["scan_status"] = "ok"
                            result["scan_detail"] = "Identique a la reference"
                        else:
                            result["scan_status"] = "ko"
                            details = []

                            # Tuiles differentes
                            if cmp["diff_tiles"]:
                                total = cmp["total_diff_tiles"]
                                tiles_str = ", ".join(f"tid={t['tid']}({','.join(t['fields'])})" for t in cmp["diff_tiles"][:10])
                                if total > 10:
                                    tiles_str += f" ... +{total-10} autres"
                                tids = [t["tid"] for t in cmp["diff_tiles"]]
                                coords = get_tile_coords_approximate(grid_w, tids)
                                details.append(f"{total} tuile(s) modifiee(s) : {tiles_str} | zones: {coords}")

                            # Tuiles presentes d'un seul cote
                            if cmp["tiles_only_in_ref"]:
                                n = len(cmp["tiles_only_in_ref"])
                                tids_str = ", ".join(str(t) for t in cmp["tiles_only_in_ref"][:10])
                                if n > 10:
                                    tids_str += f" ... +{n-10} autres"
                                details.append(f"{n} tuile(s) absente(s) de l'actuel : {tids_str}")

                            if cmp["tiles_only_in_current"]:
                                n = len(cmp["tiles_only_in_current"])
                                tids_str = ", ".join(str(t) for t in cmp["tiles_only_in_current"][:10])
                                if n > 10:
                                    tids_str += f" ... +{n-10} autres"
                                details.append(f"{n} tuile(s) nouvelle(s) : {tids_str}")

                            # Chemin project
                            if cmp["diff_project"]:
                                details.append(f"Chemin du terrain scanne different : {cmp['diff_project']['ref']} -> {cmp['diff_project']['current']}")

                            # Cles de premier niveau
                            if cmp["diff_toplevel"]:
                                details.append(f"Cles de premier niveau : {', '.join(cmp['diff_toplevel'])}")

                            result["scan_detail"] = " | ".join(details)

                    except Exception as e:
                        result["scan_status"] = "error"
                        result["scan_detail"] = f"[ERREUR] Comparaison : {e}"

    return result


def cmd_comparer(project_name: str) -> int:
    """
    Commande comparer : compare la generation actuelle a la reference.

    Args:
        project_name: Nom du projet ou "tous"

    Returns:
        0 si aucun KO, 1 sinon
    """
    if project_name == "tous":
        # Mode tous : iterer sur tous les projets avec test/
        print("=== Comparaison tous les projets ===")
        print()

        projects_with_test = []
        for p in PROJECTS_DIR.iterdir():
            if p.is_dir() and (p / "test").exists():
                projects_with_test.append(p.name)

        if not projects_with_test:
            print("[!!] Aucun projet avec reference (dossier test/)")
            return 0

        print(f"Projets avec reference : {', '.join(projects_with_test)}")
        print()

        results = []
        for pname in sorted(projects_with_test):
            ppath = PROJECTS_DIR / pname
            result = cmd_comparer_project(pname, ppath)
            results.append(result)

        # Affichage par projet
        print("=" * 70)
        for res in results:
            print(f"[{res['project']}]")

            # Satmap
            if res["satmap_status"] == "ok":
                print(f"  Satmap : [OK] {res['satmap_detail']}")
            elif res["satmap_status"] == "ko":
                print(f"  Satmap : [KO] {res['satmap_detail']}")
            elif res["satmap_status"] == "error":
                print(f"  Satmap : [ERREUR] {res['satmap_detail']}")
            else:
                print(f"  Satmap : [SKIP] {res['satmap_detail']}")

            # Scan
            if res["scan_status"] == "ok":
                print(f"  Scan   : [OK] {res['scan_detail']}")
            elif res["scan_status"] == "ko":
                print(f"  Scan   : [KO] {res['scan_detail']}")
            elif res["scan_status"] == "error":
                print(f"  Scan   : [ERREUR] {res['scan_detail']}")
            else:
                print(f"  Scan   : [SKIP] {res['scan_detail']}")

            print()

        # CORRECTION PHASE 2C : bilan global correct (OK / PARTIEL / KO)
        print("=" * 70)
        ok_count = 0
        partiel_count = 0
        ko_count = 0

        for r in results:
            has_ok = (r["satmap_status"] == "ok" or r["scan_status"] == "ok")
            has_skip = (r["satmap_status"] == "skip" or r["scan_status"] == "skip")
            has_ko = (r["satmap_status"] == "ko" or r["scan_status"] == "ko")
            has_error = (r["satmap_status"] == "error" or r["scan_status"] == "error")

            if has_ko or has_error:
                ko_count += 1
            elif r["satmap_status"] == "ok" and r["scan_status"] == "ok":
                ok_count += 1
            elif has_ok and has_skip:
                partiel_count += 1
            elif r["satmap_status"] == "skip" and r["scan_status"] == "skip":
                partiel_count += 1

        print(f"BILAN GLOBAL : {ok_count} OK, {partiel_count} PARTIEL, {ko_count} KO")
        print("=" * 70)

        return 0 if ko_count == 0 else 1

    else:
        # Mode projet unique
        project_path = PROJECTS_DIR / project_name
        if not project_path.exists():
            print(f"[KO] Projet introuvable : {project_path}")
            return 1

        print(f"=== Comparaison projet : {project_name} ===")
        print(f"    Projet : {project_path}")
        print()

        result = cmd_comparer_project(project_name, project_path)

        if not result["has_test"]:
            print(f"[!!] Pas de reference pour ce projet")
            print(f"     -> Lancez d'abord : python check_regression.py enregistrer --projet {project_name}")
            print()
            return 0

        print("=" * 70)

        # Satmap
        if result["satmap_status"] == "ok":
            print(f"Satmap : [OK] {result['satmap_detail']}")
        elif result["satmap_status"] == "ko":
            print(f"Satmap : [KO] {result['satmap_detail']}")
        elif result["satmap_status"] == "error":
            print(f"Satmap : [ERREUR] {result['satmap_detail']}")
        else:
            print(f"Satmap : [SKIP] {result['satmap_detail']}")

        print()

        # Scan
        if result["scan_status"] == "ok":
            print(f"Scan   : [OK] {result['scan_detail']}")
        elif result["scan_status"] == "ko":
            print(f"Scan   : [KO] {result['scan_detail']}")
        elif result["scan_status"] == "error":
            print(f"Scan   : [ERREUR] {result['scan_detail']}")
        else:
            print(f"Scan   : [SKIP] {result['scan_detail']}")

        print()
        print("=" * 70)

        # Bilan
        has_ko = (result["satmap_status"] == "ko" or result["scan_status"] == "ko")
        has_error = (result["satmap_status"] == "error" or result["scan_status"] == "error")

        if has_ko or has_error:
            print("[KO] DIFFERENCES OU ERREURS DETECTEES")
        else:
            print("[OK] AUCUNE DIFFERENCE")

        print("=" * 70)

        return 1 if (has_ko or has_error) else 0


def cmd_tester_detection(project_name: str) -> int:
    """
    CORRECTION : Commande tester-detection
    Auto-test de la detection : falsifie la reference et verifie que la comparaison detecte bien les KO.
    Ne touche JAMAIS au vrai dossier test/.

    Returns:
        0 si detection OK, 1 si defaillante
    """
    project_path = PROJECTS_DIR / project_name
    if not project_path.exists():
        print(f"[KO] Projet introuvable : {project_path}")
        return 1

    test_dir = project_path / "test"
    if not test_dir.exists():
        print(f"[KO] Pas de reference pour ce projet")
        print(f"     -> Lancez d'abord : python check_regression.py enregistrer --projet {project_name}")
        return 1

    print(f"=== Test de detection sur projet : {project_name} ===")
    print(f"    Projet : {project_path}")
    print()

    # Creer copie temporaire de la reference
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_test = Path(temp_dir) / "test"
        shutil.copytree(test_dir, temp_test)

        print("[1/3] Falsification satmap_hash.json...")
        hash_json = temp_test / "satmap_hash.json"
        if hash_json.exists():
            hash_data = json.loads(hash_json.read_text(encoding="utf-8"))
            hash_data["hash"] = "0" * 64  # Hash invalide
            hash_json.write_text(json.dumps(hash_data, indent=2), encoding="utf-8")
            print("      [OK] Hash remplace par 64 zeros")
        else:
            print("      [SKIP] satmap_hash.json absent")

        print()
        print("[2/3] Falsification qtre_scan.json...")
        scan_json = temp_test / "qtre_scan.json"
        if scan_json.exists():
            scan_data = json.loads(scan_json.read_text(encoding="utf-8"))
            if scan_data.get("tiles") and len(scan_data["tiles"]) > 0:
                # Modifier premiere tuile
                scan_data["tiles"][0]["n_active_mats"] = 9999
            # Ajouter cle de premier niveau
            scan_data["test_faux"] = "valeur_test"
            scan_json.write_text(json.dumps(scan_data, indent=2), encoding="utf-8")
            print("      [OK] Tuile 0 modifiee + cle test_faux ajoutee")
        else:
            print("      [SKIP] qtre_scan.json absent")

        print()
        print("[3/3] Comparaison contre reference falsifiee...")

        # CORRECTION : Appeler cmd_comparer_project avec ref_dir=temp_test
        # Ne JAMAIS toucher au vrai test_dir
        result = cmd_comparer_project(project_name, project_path, ref_dir=temp_test)

        print()
        print("=" * 70)
        print("RESULTATS")
        print("=" * 70)

        satmap_detected = (result["satmap_status"] == "ko")
        scan_detected = (result["scan_status"] == "ko")

        print(f"Satmap : {'[OK] KO detecte' if satmap_detected else '[DEFAUT] Non detecte'}")
        if result["satmap_detail"]:
            print(f"         {result['satmap_detail']}")

        print(f"Scan   : {'[OK] KO detecte' if scan_detected else '[DEFAUT] Non detecte'}")
        if result["scan_detail"]:
            print(f"         {result['scan_detail']}")

        print()
        print("=" * 70)

        if satmap_detected and scan_detected:
            print("[OK] DETECTION OK - Les deux falsifications ont ete detectees")
            print("=" * 70)
            return 0
        else:
            print("[KO] DETECTION DEFAILLANTE")
            if not satmap_detected:
                print("     Satmap : falsification NON detectee")
            if not scan_detected:
                print("     Scan   : falsification NON detectee")
            print("=" * 70)
            return 1


# ===============================================================================
# MAIN
# ===============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Script de non-regression Map Generator Pro"
    )
    parser.add_argument(
        "commande",
        choices=["valider-script", "enregistrer", "comparer", "tester-detection"],
        help="Commande a executer"
    )
    parser.add_argument(
        "--projet",
        required=True,
        help="Nom du projet (dossier dans data/projects/) ou 'tous' pour comparer"
    )

    args = parser.parse_args()

    if args.commande == "valider-script":
        return cmd_valider_script(args.projet)
    elif args.commande == "enregistrer":
        return cmd_enregistrer(args.projet)
    elif args.commande == "comparer":
        return cmd_comparer(args.projet)
    elif args.commande == "tester-detection":
        if args.projet == "tous":
            print("[KO] tester-detection ne supporte pas --projet tous")
            return 1
        return cmd_tester_detection(args.projet)

    return 0


if __name__ == "__main__":
    sys.exit(main())
