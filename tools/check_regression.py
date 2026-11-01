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
import time
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# Racine du projet (défini avant les imports)
REPO_ROOT = Path(__file__).resolve().parent.parent

# Projets de référence pour --projet tous
REFERENCE_PROJECTS = ["Zimnitrita", "Zbk_island"]

# Ajouter app/ au path pour pouvoir importer les modules
sys.path.insert(0, str(REPO_ROOT / "app"))

# Reconfiguration encodage AVANT tout affichage (fix UnicodeEncodeError avec redirection stdout)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Imports modules existants
from catalog_config import get_catalog_path, TEXTURES_USER_DIR, USER_DIR
import project_reader
from terrain_terr_reader import build_id_to_name
from tile_inspector import export_json as tile_inspector_export_json
from satmap_v2_textured_v2 import generate_satmap_v2_textured_complete
PROJECTS_DIR = REPO_ROOT / "data" / "projects"
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"

# Fichiers de configuration à protéger
SETTINGS_FILE = USER_DIR / "settings.json"

# Chemin du fichier surfaces.json de Zimnitrita à surveiller
ZIMNITRITA_SURFACES = Path("I:/Reforger_addons travail/Zimnitrita_map/World/Zimnitrita/Terrain/surfaces.json")

# Import lrs2_parser pour sélection des tuiles
from lrs2_parser import parse_iff_chunks, parse_lrs2_chunk


# ===============================================================================
# UTILITAIRES DE PROTECTION DES FICHIERS
# ===============================================================================

def get_file_hash(file_path: Path) -> str:
    """Retourne le hash SHA256 d'un fichier."""
    if not file_path.exists():
        return "ABSENT"
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def get_file_mtime(file_path: Path) -> Optional[float]:
    """Retourne la date de modification d'un fichier."""
    if not file_path.exists():
        return None
    return file_path.stat().st_mtime


def get_protected_files(project_names: list) -> list:
    """
    Liste des fichiers à protéger : settings.json et, pour chaque projet testé,
    project.json, project_mask_config.json, surfaces.json.
    """
    files = [SETTINGS_FILE]
    for pname in project_names:
        project_dir = PROJECTS_DIR / pname
        for fname in ("project.json", "project_mask_config.json", "surfaces.json"):
            files.append(project_dir / fname)
    return files


def get_tested_projects(project_name: str) -> list:
    """Projets concernés par la commande ('tous' = liste explicite REFERENCE_PROJECTS)."""
    if project_name == "tous":
        return REFERENCE_PROJECTS
    return [project_name]


def snapshot_protected_files(paths: list) -> dict:
    """
    Lit le contenu exact (octets) de chaque fichier protégé et calcule son SHA256.

    Returns:
        {Path: {"content": bytes | None, "hash": str}}  (content None = fichier absent)
    """
    snapshot = {}
    print("[PROTECTION] Sauvegarde des fichiers protégés :")
    for path in paths:
        if path.exists():
            content = path.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()
        else:
            content = None
            file_hash = "ABSENT"
        snapshot[path] = {"content": content, "hash": file_hash}
        print(f"      {path.resolve()}")
        print(f"        origine : {file_hash}")
    print()
    return snapshot


def restore_protected_files(snapshot: dict) -> bool:
    """
    Réécrit les octets d'origine de chaque fichier protégé, puis vérifie le SHA256.

    Returns:
        True si tous les fichiers sont identiques à l'origine, False sinon
    """
    # PHASE 1 : Restaurer TOUS les fichiers d'abord (aucune erreur d'affichage ne peut interrompre)
    restore_results = []
    for path, saved in snapshot.items():
        write_error = None
        try:
            if saved["content"] is not None:
                path.write_bytes(saved["content"])
            elif path.exists():
                # Le fichier n'existait pas : le supprimer s'il a été créé
                path.unlink()
        except Exception as e:
            write_error = str(e)

        current_hash = get_file_hash(path)
        restore_results.append({
            "path": path,
            "original_hash": saved["hash"],
            "current_hash": current_hash,
            "write_error": write_error
        })

    # PHASE 2 : Afficher le compte-rendu (chaque affichage dans son try/except)
    print()
    print("[PROTECTION] Restauration des fichiers protégés :")

    all_ok = True
    for result in restore_results:
        try:
            print(f"      {result['path'].resolve()}")
            print(f"        origine            : {result['original_hash']}")
            print(f"        apres restauration : {result['current_hash']}")

            if result["write_error"]:
                print(f"      [ERREUR] Ecriture : {result['write_error']}")
                all_ok = False
            elif result["current_hash"] == result["original_hash"]:
                print(f"      [OK] {result['path'].name} restaure (hash identique)")
            else:
                print(f"      [ECHEC] restauration {result['path'].name} : origine {result['original_hash']} / actuel {result['current_hash']}")
                all_ok = False
        except Exception as e:
            # Erreur d'affichage : ne pas interrompre la boucle, juste la noter
            try:
                print(f"      [ERREUR AFFICHAGE] {result['path'].name} : {e}")
            except:
                pass  # Même l'affichage de l'erreur échoue : continuer silencieusement
            all_ok = False

    return all_ok


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


def generate_masks_in_temp(project_path: Path, temp_dir: Path) -> dict:
    """
    Génère les masques du pipeline en lançant le worker dans un sous-processus.

    Returns:
        {"ok": True, "masks": [str]} ou {"ok": False, "error": str}
    """
    if not VENV_PYTHON.exists():
        return {"ok": False, "error": f"Interpréteur venv introuvable : {VENV_PYTHON}"}

    worker_script = REPO_ROOT / "tools" / "check_regression_masks_worker.py"
    if not worker_script.exists():
        return {"ok": False, "error": f"Worker introuvable : {worker_script}"}

    try:
        # Surveiller surfaces.json de Zimnitrita AVANT
        zimnitrita_mtime_before = get_file_mtime(ZIMNITRITA_SURFACES)

        try:
            # Lancer le worker
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"

            result = subprocess.run(
                [str(VENV_PYTHON), str(worker_script),
                 "--project-path", str(project_path),
                 "--out-dir", str(temp_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,  # 10 minutes max
                env=env
            )

            if result.returncode != 0:
                error_msg = f"Worker retourné code {result.returncode}"
                if result.stderr:
                    error_msg += f"\nStderr: {result.stderr[:500]}"
                return {"ok": False, "error": error_msg}

            # Lire result.json
            result_json = temp_dir / "result.json"
            if not result_json.exists():
                return {"ok": False, "error": "result.json non créé par le worker"}

            worker_result = json.loads(result_json.read_text(encoding="utf-8"))

            if not worker_result.get("ok"):
                return {"ok": False, "error": worker_result.get("error", "Erreur inconnue")}

            return {"ok": True, "masks": worker_result.get("masks", [])}

        finally:
            # Les fichiers protégés sont restaurés par main() une fois toutes les générations terminées

            # Surveiller surfaces.json de Zimnitrita APRÈS
            zimnitrita_mtime_after = get_file_mtime(ZIMNITRITA_SURFACES)
            if zimnitrita_mtime_before != zimnitrita_mtime_after:
                print(f"      [AVERTISSEMENT] {ZIMNITRITA_SURFACES} a été modifié pendant la génération !")
                if zimnitrita_mtime_before is None:
                    print(f"                      Avant: absent, Après: présent")
                elif zimnitrita_mtime_after is None:
                    print(f"                      Avant: présent, Après: absent")
                else:
                    before_str = datetime.fromtimestamp(zimnitrita_mtime_before).isoformat()
                    after_str = datetime.fromtimestamp(zimnitrita_mtime_after).isoformat()
                    print(f"                      Avant: {before_str}, Après: {after_str}")

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout (10 minutes) atteint"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def select_reference_tiles(project_path: Path, data_dir: Path, grid_w: int, num_blk: int, tile_prefix: str, verbose: bool = False) -> dict:
    """
    Sélectionne automatiquement les tuiles de référence en lisant les .ttile.

    Args:
        project_path: Chemin du projet
        data_dir: Dossier .Data du terrain
        grid_w: Nombre de tuiles par côté (depuis project_reader)
        num_blk: Nombre de blocs par tuile et par côté (depuis project_reader)
        tile_prefix: Préfixe des tuiles (depuis project_reader)
        verbose: Affichage diagnostic

    Returns:
        {"ok": True, "selected": {...}} ou {"ok": False, "error": str}
    """
    import re

    if verbose:
        print(f"     [DIAGNOSTIC] Dossier .Data : {data_dir}")
        print(f"     [DIAGNOSTIC] Préfixe : {tile_prefix}")
        print(f"     [DIAGNOSTIC] Grille : {grid_w}x{grid_w}")

    # Lister tous les .ttile
    pattern = re.compile(rf'^{re.escape(tile_prefix)}(\d+)\.ttile$')
    ttile_files = sorted([f for f in data_dir.glob("*.ttile") if pattern.match(f.name)])

    if verbose:
        print(f"     [DIAGNOSTIC] Nombre de .ttile trouvés : {len(ttile_files)}")
        if len(ttile_files) > 0:
            print(f"     [DIAGNOSTIC] Premiers .ttile : {[f.name for f in ttile_files[:5]]}")

    if not ttile_files:
        return {"ok": False, "error": f"Aucun .ttile trouvé avec préfixe '{tile_prefix}' dans {data_dir}"}

    # Analyser chaque tuile (échantillon pour diagnostic)
    tiles_info = []
    sample_tiles_analyzed = 0

    for ttile_path in ttile_files:
        match = pattern.match(ttile_path.name)
        if not match:
            continue

        try:
            tid = int(match.group(1))
            tx = tid % grid_w
            ty = tid // grid_w

            # Lire LRS2 pour compter les matériaux
            data = ttile_path.read_bytes()
            chunks = parse_iff_chunks(data)

            lrs2_chunk = chunks.get("LRS2")
            if not lrs2_chunk:
                if verbose and sample_tiles_analyzed < 3:
                    print(f"     [DIAGNOSTIC] Tuile {tid} : pas de chunk LRS2")
                    sample_tiles_analyzed += 1
                continue

            # Extraire les données LRS2
            lrs2_offset, lrs2_size = lrs2_chunk
            lrs2_data = data[lrs2_offset:lrs2_offset+lrs2_size]

            if verbose and sample_tiles_analyzed < 3:
                print(f"     [DIAGNOSTIC] Tuile {tid} : chunk LRS2 de {lrs2_size} octets")

            # Parser LRS2 avec le lecteur de l'app (lrs2_parser.py)
            block_materials = parse_lrs2_chunk(lrs2_data, grid_w=grid_w, num_blk=num_blk, filename=ttile_path.name)

            # Max de matériaux distincts dans un bloc
            num_blocks = len(block_materials)
            max_tex = max((len(mats) for mats in block_materials.values()), default=0)

            if verbose and sample_tiles_analyzed < 3:
                print(f"     [DIAGNOSTIC] Tuile {tid} ({tx},{ty}) : {num_blocks} blocs analysés, max {max_tex} matériaux/bloc")
                sample_tiles_analyzed += 1

            # Vérifier taille GCTD (impaire pour ZBK)
            gctd_chunk = chunks.get("GCTD")
            if gctd_chunk:
                gctd_offset, gctd_size = gctd_chunk
            else:
                gctd_size = 0

            # Déterminer si c'est une tuile en bord
            is_edge = (tx == 0 or ty == 0 or tx == grid_w-1 or ty == grid_w-1)

            # Distance au centre (pour tri déterministe)
            center = grid_w / 2.0
            dist_to_center = ((tx + 0.5 - center) ** 2 + (ty + 0.5 - center) ** 2) ** 0.5

            tiles_info.append({
                "tid": tid,
                "tx": tx,
                "ty": ty,
                "max_tex": max_tex,
                "is_edge": is_edge,
                "gctd_size": gctd_size,
                "dist_to_center": dist_to_center,
                "block_materials": block_materials  # Garder pour vérification détaillée
            })
        except Exception as e:
            if verbose and sample_tiles_analyzed < 3:
                print(f"     [DIAGNOSTIC] Erreur analyse tuile {ttile_path.name} : {e}")
            continue

    if not tiles_info:
        return {"ok": False, "error": "Aucune tuile analysée avec succès"}

    # ====================================================================
    # SÉLECTION DES TUILES DE RÉFÉRENCE (distinctes, choix déterministe)
    # ====================================================================
    # Règles de tri déterministe :
    # - "ordinaire" : tri par distance au centre (croissante), puis tid
    # - "high_count" : tri par max_tex (décroissant), puis tid
    # - "edge" : tri par tid (croissant)
    # - "odd_gctd" : tri par tid (croissant)
    # Les tuiles déjà sélectionnées sont exclues des sélections suivantes.
    # ====================================================================

    selected = {}
    selected_tids = set()  # Garder trace des tuiles déjà sélectionnées

    # Fonction helper pour vérifier si un bloc a 3-5 matériaux
    def has_block_with_3_to_5_materials(tile):
        """Vérifie si la tuile a au moins un bloc avec 3, 4 ou 5 matériaux."""
        for mat_list in tile["block_materials"].values():
            if 3 <= len(mat_list) <= 5:
                return True
        return False

    # 1. TUILE ORDINAIRE : au moins un bloc à 3-5 mat, PAS en bord, plus proche du centre
    ordinary_candidates = [
        t for t in tiles_info
        if not t["is_edge"]
        and has_block_with_3_to_5_materials(t)
        and t["tid"] not in selected_tids
    ]
    if ordinary_candidates:
        # Tri déterministe : distance au centre croissante, puis tid croissant
        ordinary_candidates.sort(key=lambda t: (t["dist_to_center"], t["tid"]))
        ordinary = ordinary_candidates[0]
        selected["ordinary"] = {
            "tid": ordinary["tid"],
            "tx": ordinary["tx"],
            "ty": ordinary["ty"],
            "max_tex": ordinary["max_tex"]
        }
        selected_tids.add(ordinary["tid"])

    # 2. TUILE 6-7 MATÉRIAUX : max_tex >= 6, distincte
    high_count_candidates = [
        t for t in tiles_info
        if t["max_tex"] >= 6
        and t["tid"] not in selected_tids
    ]
    if high_count_candidates:
        # Tri déterministe : max_tex décroissant, puis tid croissant
        high_count_candidates.sort(key=lambda t: (-t["max_tex"], t["tid"]))
        high_count = high_count_candidates[0]
        selected["high_count"] = {
            "tid": high_count["tid"],
            "tx": high_count["tx"],
            "ty": high_count["ty"],
            "max_tex": high_count["max_tex"]
        }
        selected_tids.add(high_count["tid"])

    # 3. TUILE EN BORD : en bord avec au moins 2 mat sur un bloc, distincte
    edge_candidates = [
        t for t in tiles_info
        if t["is_edge"]
        and t["max_tex"] >= 2
        and t["tid"] not in selected_tids
    ]
    if edge_candidates:
        # Tri déterministe : tid croissant
        edge_candidates.sort(key=lambda t: t["tid"])
        edge = edge_candidates[0]
        selected["edge"] = {
            "tid": edge["tid"],
            "tx": edge["tx"],
            "ty": edge["ty"],
            "max_tex": edge["max_tex"]
        }
        selected_tids.add(edge["tid"])

    # 4. TUILE GCTD IMPAIR (ZBK uniquement) : GCTD impair, distincte
    odd_gctd_candidates = [
        t for t in tiles_info
        if t["gctd_size"] > 0
        and t["gctd_size"] % 2 == 1
        and t["tid"] not in selected_tids
    ]
    if odd_gctd_candidates:
        # Tri déterministe : tid croissant
        odd_gctd_candidates.sort(key=lambda t: t["tid"])
        odd_gctd = odd_gctd_candidates[0]
        selected["odd_gctd"] = {
            "tid": odd_gctd["tid"],
            "tx": odd_gctd["tx"],
            "ty": odd_gctd["ty"],
            "gctd_size": odd_gctd["gctd_size"]
        }
        selected_tids.add(odd_gctd["tid"])

    # Diagnostic des critères (après sélection)
    if verbose:
        ordinary_total = len([
            t for t in tiles_info
            if not t["is_edge"] and has_block_with_3_to_5_materials(t)
        ])
        high_count_total = len([t for t in tiles_info if t["max_tex"] >= 6])
        edge_total = len([t for t in tiles_info if t["is_edge"] and t["max_tex"] >= 2])
        odd_gctd_total = len([t for t in tiles_info if t["gctd_size"] > 0 and t["gctd_size"] % 2 == 1])

        print(f"     [DIAGNOSTIC] Critères de sélection :")
        print(f"       - Ordinaire (3-5 mat/bloc, hors bord) : {ordinary_total} candidates")
        print(f"       - High count (6+ mat)                : {high_count_total} candidates")
        print(f"       - Bord (2+ mat)                      : {edge_total} candidates")
        print(f"       - GCTD impair                        : {odd_gctd_total} candidates")

    if not selected:
        return {"ok": False, "error": "Aucune tuile de référence trouvée"}

    return {"ok": True, "selected": selected}


def create_zone_mask(project_path: Path, grid_w: int) -> dict:
    """
    Crée un masque PNG de zone carrée centrale (4×4 tuiles).

    Returns:
        {"ok": True, "mask_path": Path} ou {"ok": False, "error": str}
    """
    import cv2
    import numpy as np

    # Résolution basse : 128 px/tuile
    px_per_tile = 128
    mask_size = grid_w * px_per_tile

    # Créer masque noir
    mask = np.zeros((mask_size, mask_size), dtype=np.uint8)

    # Zone centrale 4×4 tuiles
    center_start = (grid_w - 4) // 2
    center_end = center_start + 4

    y_start = center_start * px_per_tile
    y_end = center_end * px_per_tile
    x_start = center_start * px_per_tile
    x_end = center_end * px_per_tile

    # Remplir zone centrale en blanc
    mask[y_start:y_end, x_start:x_end] = 255

    # Sauvegarder
    corrections_dir = project_path / "test" / "corrections"
    corrections_dir.mkdir(parents=True, exist_ok=True)
    mask_path = corrections_dir / "zone_mask.png"

    cv2.imwrite(str(mask_path), mask)

    return {"ok": True, "mask_path": mask_path}


def generate_corrections_in_temp(project_path: Path, temp_dir: Path) -> dict:
    """
    Génère les résultats Corrections en lançant le worker dans un sous-processus.

    Returns:
        {"ok": True} ou {"ok": False, "error": str}
    """
    if not VENV_PYTHON.exists():
        return {"ok": False, "error": f"Interpréteur venv introuvable : {VENV_PYTHON}"}

    worker_script = REPO_ROOT / "tools" / "check_regression_corrections_worker.py"
    if not worker_script.exists():
        return {"ok": False, "error": f"Worker introuvable : {worker_script}"}

    try:
        # Surveiller surfaces.json de Zimnitrita AVANT
        zimnitrita_mtime_before = get_file_mtime(ZIMNITRITA_SURFACES)

        try:
            # Lancer le worker
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"

            result = subprocess.run(
                [str(VENV_PYTHON), str(worker_script),
                 "--project-path", str(project_path),
                 "--out-dir", str(temp_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,  # 10 minutes max
                env=env
            )

            if result.returncode != 0:
                error_msg = f"Worker retourné code {result.returncode}"
                if result.stderr:
                    error_msg += f"\nStderr: {result.stderr[:500]}"
                return {"ok": False, "error": error_msg}

            # Lire result.json
            result_json = temp_dir / "result.json"
            if not result_json.exists():
                return {"ok": False, "error": "result.json non créé par le worker"}

            worker_result = json.loads(result_json.read_text(encoding="utf-8"))

            if not worker_result.get("ok"):
                return {"ok": False, "error": worker_result.get("error", "Erreur inconnue")}

            return {"ok": True}

        finally:
            # Surveiller surfaces.json de Zimnitrita APRÈS
            zimnitrita_mtime_after = get_file_mtime(ZIMNITRITA_SURFACES)
            if zimnitrita_mtime_before != zimnitrita_mtime_after:
                print(f"      [AVERTISSEMENT] {ZIMNITRITA_SURFACES} a été modifié pendant la génération !")
                if zimnitrita_mtime_before is None:
                    print(f"                      Avant: absent, Après: présent")
                elif zimnitrita_mtime_after is None:
                    print(f"                      Avant: présent, Après: absent")
                else:
                    before_str = datetime.fromtimestamp(zimnitrita_mtime_before).isoformat()
                    after_str = datetime.fromtimestamp(zimnitrita_mtime_after).isoformat()
                    print(f"                      Avant: {before_str}, Après: {after_str}")

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout (10 minutes) atteint"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_terrain_files_snapshot(project_path: Path) -> dict:
    """
    Relève chemin, taille et mtime de TOUS les fichiers terrain (.Data, .EditorData, .terr).

    Returns:
        {Path: {"size": int, "mtime": float}}
    """
    # Lire chemins terrain via project_reader
    terrain_result = get_terrain_dirs(project_path)
    if not terrain_result.get("ok"):
        return {}

    data_dir = Path(terrain_result["data_dir"])
    editor_dir = Path(terrain_result["editor_dir"])
    terr_file = Path(terrain_result["terr_file"])

    snapshot = {}

    # .Data (récursif)
    if data_dir.exists():
        for f in data_dir.rglob("*"):
            if f.is_file():
                snapshot[f] = {
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime
                }

    # .EditorData (récursif)
    if editor_dir.exists():
        for f in editor_dir.rglob("*"):
            if f.is_file():
                snapshot[f] = {
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime
                }

    # .terr
    if terr_file.exists():
        snapshot[terr_file] = {
            "size": terr_file.stat().st_size,
            "mtime": terr_file.stat().st_mtime
        }

    return snapshot


def compare_terrain_files_snapshots(before: dict, after: dict) -> dict:
    """
    Compare deux snapshots de fichiers terrain.

    Returns:
        {"changed": bool, "created": [Path], "deleted": [Path], "modified": [Path]}
    """
    before_paths = set(before.keys())
    after_paths = set(after.keys())

    created = sorted(after_paths - before_paths)
    deleted = sorted(before_paths - after_paths)
    modified = []

    for path in sorted(before_paths & after_paths):
        if before[path] != after[path]:
            modified.append(path)

    changed = bool(created or deleted or modified)

    return {
        "changed": changed,
        "created": created,
        "deleted": deleted,
        "modified": modified
    }


# ===============================================================================
# DETAIL (pour --detail)
# ===============================================================================

def save_satmap_detail(detail_dir: Path, current_satmap: Path, ref_hash_data: dict, current_hash: dict, diff_result: dict) -> None:
    """
    Sauvegarde les détails de la comparaison Satmap.

    Args:
        detail_dir: Dossier de détail pour cette partie
        current_satmap: Chemin de la satmap actuelle générée
        ref_hash_data: Hash de référence
        current_hash: Hash actuel
        diff_result: Résultat de create_diff_thumbnail
    """
    detail_dir.mkdir(parents=True, exist_ok=True)

    # Copier la satmap actuelle
    import shutil
    shutil.copy2(current_satmap, detail_dir / "satmap_current.png")

    # Créer differences.md
    diff_md = detail_dir / "differences.md"
    with diff_md.open("w", encoding="utf-8") as f:
        f.write("# Différences Satmap\n\n")
        f.write(f"**Hash référence** : `{ref_hash_data.get('hash', '')[:64]}`\n\n")
        f.write(f"**Hash actuel** : `{current_hash['hash'][:64]}`\n\n")

        if diff_result and diff_result.get("bbox_tiles"):
            bbox = diff_result["bbox_tiles"]
            f.write(f"**Zone différente** : tuiles ({bbox['x_min']},{bbox['y_min']})-({bbox['x_max']},{bbox['y_max']})\n\n")
        elif diff_result and diff_result.get("ok"):
            f.write("**Zone différente** : différence plus fine que la résolution de la miniature\n\n")


def save_scan_detail(detail_dir: Path, current_scan: Path, ref_scan: Path, cmp_result: dict) -> None:
    """
    Sauvegarde les détails de la comparaison Scan.

    Args:
        detail_dir: Dossier de détail pour cette partie
        current_scan: Chemin du scan actuel généré
        ref_scan: Chemin du scan de référence
        cmp_result: Résultat de compare_scan_json
    """
    import shutil
    detail_dir.mkdir(parents=True, exist_ok=True)

    # Copier le scan actuel
    shutil.copy2(current_scan, detail_dir / "qtre_scan_current.json")
    shutil.copy2(ref_scan, detail_dir / "qtre_scan_reference.json")

    # Créer differences.md
    diff_md = detail_dir / "differences.md"
    with diff_md.open("w", encoding="utf-8") as f:
        f.write("# Différences Scan QTRE\n\n")

        if cmp_result.get("error"):
            f.write(f"**ERREUR** : {cmp_result['error']}\n\n")
            return

        if cmp_result["identical"]:
            f.write("**Aucune différence**\n\n")
            return

        # Tuiles différentes
        if cmp_result["diff_tiles"]:
            f.write(f"## Tuiles modifiées ({cmp_result['total_diff_tiles']} total)\n\n")
            for t in cmp_result["diff_tiles"]:
                f.write(f"- **Tuile {t['tid']}** : champs différents : {', '.join(t['fields'])}\n")
            f.write("\n")

        # Tuiles présentes d'un seul côté
        if cmp_result["tiles_only_in_ref"]:
            f.write(f"## Tuiles absentes de l'actuel ({len(cmp_result['tiles_only_in_ref'])} total)\n\n")
            f.write(f"{', '.join(str(t) for t in cmp_result['tiles_only_in_ref'])}\n\n")

        if cmp_result["tiles_only_in_current"]:
            f.write(f"## Tuiles nouvelles ({len(cmp_result['tiles_only_in_current'])} total)\n\n")
            f.write(f"{', '.join(str(t) for t in cmp_result['tiles_only_in_current'])}\n\n")

        # Projet
        if cmp_result["diff_project"]:
            f.write(f"## Chemin du terrain\n\n")
            f.write(f"- **Référence** : {cmp_result['diff_project']['ref']}\n")
            f.write(f"- **Actuel** : {cmp_result['diff_project']['current']}\n\n")

        # Clés de premier niveau
        if cmp_result["diff_toplevel"]:
            f.write(f"## Clés de premier niveau\n\n")
            f.write(f"{', '.join(cmp_result['diff_toplevel'])}\n\n")


def save_masks_detail(detail_dir: Path, temp_path: Path, masks_dir: Path, diff_masks: list, only_in_ref: set, only_in_current: set) -> None:
    """
    Sauvegarde les détails de la comparaison Masques.

    Args:
        detail_dir: Dossier de détail pour cette partie
        temp_path: Dossier temporaire contenant les masques actuels
        masks_dir: Dossier contenant les masques de référence
        diff_masks: Liste des masques différents
        only_in_ref: Masques présents uniquement en référence
        only_in_current: Masques présents uniquement en actuel
    """
    import shutil
    detail_dir.mkdir(parents=True, exist_ok=True)

    # Créer sous-dossiers
    current_dir = detail_dir / "current"
    ref_dir = detail_dir / "reference"
    current_dir.mkdir(exist_ok=True)
    ref_dir.mkdir(exist_ok=True)

    # Copier tous les masques actuels
    for mask_file in temp_path.glob("*.png"):
        shutil.copy2(mask_file, current_dir / mask_file.name)

    # Copier les masques de référence pertinents (différents ou absents de l'actuel)
    for mask_name in diff_masks:
        ref_png = masks_dir / mask_name["name"]
        if ref_png.exists():
            shutil.copy2(ref_png, ref_dir / ref_png.name)

    for mask_name in only_in_ref:
        ref_png = masks_dir / mask_name
        if ref_png.exists():
            shutil.copy2(ref_png, ref_dir / ref_png.name)

    # Créer differences.md
    diff_md = detail_dir / "differences.md"
    with diff_md.open("w", encoding="utf-8") as f:
        f.write("# Différences Masques\n\n")

        if not diff_masks and not only_in_ref and not only_in_current:
            f.write("**Aucune différence**\n\n")
            return

        if diff_masks:
            f.write(f"## Masques différents ({len(diff_masks)})\n\n")
            for m in diff_masks:
                if "error" in m:
                    f.write(f"- **{m['name']}** : ERREUR - {m['error']}\n")
                else:
                    f.write(f"- **{m['name']}** : {m['diff_pixels']} pixels différents, écart max {m['max_diff']:.4f}\n")
            f.write("\n")

        if only_in_ref:
            f.write(f"## Masques absents de l'actuel ({len(only_in_ref)})\n\n")
            f.write(f"{', '.join(sorted(only_in_ref))}\n\n")

        if only_in_current:
            f.write(f"## Masques nouveaux ({len(only_in_current)})\n\n")
            f.write(f"{', '.join(sorted(only_in_current))}\n\n")


def save_corrections_detail(detail_dir: Path, temp_path: Path, corrections_dir: Path, project_path: Path,
                            diff_json: list, diff_png: list, only_in_ref_json: set, only_in_current_json: set,
                            only_in_ref_png: set, only_in_current_png: set) -> None:
    """
    Sauvegarde les détails de la comparaison Corrections.

    Args:
        detail_dir: Dossier de détail pour cette partie
        temp_path: Dossier temporaire contenant les résultats actuels
        corrections_dir: Dossier contenant les résultats de référence
        project_path: Chemin du projet (pour normalisation)
        diff_json: Liste des JSON différents
        diff_png: Liste des PNG différents
        only_in_ref_json/png: Fichiers présents uniquement en référence
        only_in_current_json/png: Fichiers présents uniquement en actuel
    """
    import shutil
    detail_dir.mkdir(parents=True, exist_ok=True)

    # Créer sous-dossiers
    current_dir = detail_dir / "current"
    ref_dir = detail_dir / "reference"
    current_norm_dir = detail_dir / "current_normalized"
    ref_norm_dir = detail_dir / "reference_normalized"

    for d in [current_dir, ref_dir, current_norm_dir, ref_norm_dir]:
        d.mkdir(exist_ok=True)

    # Liste blanche stricte
    json_whitelist = {
        "inspect_tile.json",
        "inspection_scan_tiles.json",
        "corrections_inspect_tile.json",
        "corrections_scan_global.json",
        "corrections_scan_zone.json",
        "corrections_terrain_health.json",
        "corrections_file_inventory.json"
    }

    # Copier tous les JSON actuels (brut et normalisé)
    for json_file in temp_path.glob("*.json"):
        if json_file.name in json_whitelist:
            shutil.copy2(json_file, current_dir / json_file.name)

            # Sauvegarder version normalisée
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                norm_data = normalize_corrections_json(data, project_path)
                norm_path = current_norm_dir / json_file.name
                norm_path.write_text(json.dumps(norm_data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass  # Ignorer les erreurs de normalisation

    # Copier tous les PNG actuels
    for png_file in temp_path.glob("tile_*_*.png"):
        shutil.copy2(png_file, current_dir / png_file.name)

    # Copier les JSON de référence pertinents (brut et normalisé)
    all_ref_json = set()
    for d in diff_json:
        all_ref_json.add(d["name"])
    all_ref_json.update(only_in_ref_json)

    for json_name in all_ref_json:
        ref_json = corrections_dir / json_name
        if ref_json.exists():
            shutil.copy2(ref_json, ref_dir / json_name)

            # Sauvegarder version normalisée
            try:
                data = json.loads(ref_json.read_text(encoding="utf-8"))
                norm_data = normalize_corrections_json(data, project_path)
                norm_path = ref_norm_dir / json_name
                norm_path.write_text(json.dumps(norm_data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

    # Copier les PNG de référence pertinents
    all_ref_png = set()
    for d in diff_png:
        all_ref_png.add(d["name"])
    all_ref_png.update(only_in_ref_png)

    for png_name in all_ref_png:
        ref_png = corrections_dir / png_name
        if ref_png.exists():
            shutil.copy2(ref_png, ref_dir / png_name)

    # Créer differences.md
    diff_md = detail_dir / "differences.md"
    with diff_md.open("w", encoding="utf-8") as f:
        f.write("# Différences Corrections\n\n")

        if (not diff_json and not diff_png and not only_in_ref_json and
            not only_in_current_json and not only_in_ref_png and not only_in_current_png):
            f.write("**Aucune différence**\n\n")
            return

        # JSON différents
        if diff_json:
            f.write(f"## JSON différents ({len(diff_json)})\n\n")
            for d in diff_json:
                if "error" in d:
                    f.write(f"### {d['name']} [ERREUR]\n\n")
                    f.write(f"```\n{d['error']}\n```\n\n")
                else:
                    f.write(f"### {d['name']} ({d['total_diffs']} différences)\n\n")
                    if d.get("diff_keys"):
                        for dk in d["diff_keys"]:
                            ref_val = str(dk["ref"])[:300]
                            curr_val = str(dk["current"])[:300]
                            f.write(f"- **{dk['key']}**\n")
                            f.write(f"  - Référence : `{ref_val}`\n")
                            f.write(f"  - Actuel : `{curr_val}`\n")
                        f.write("\n")
            f.write("\n")

        # PNG différents
        if diff_png:
            f.write(f"## PNG différents ({len(diff_png)})\n\n")
            for d in diff_png:
                if "error" in d:
                    f.write(f"- **{d['name']}** : ERREUR - {d['error']}\n")
                else:
                    f.write(f"- **{d['name']}** : {d['diff_pixels']} pixels différents, écart max {d['max_diff']:.4f}\n")
            f.write("\n")

        # JSON présents d'un seul côté
        if only_in_ref_json:
            f.write(f"## JSON absents de l'actuel ({len(only_in_ref_json)})\n\n")
            f.write(f"{', '.join(sorted(only_in_ref_json))}\n\n")

        if only_in_current_json:
            f.write(f"## JSON nouveaux ({len(only_in_current_json)})\n\n")
            f.write(f"{', '.join(sorted(only_in_current_json))}\n\n")

        # PNG présents d'un seul côté
        if only_in_ref_png:
            f.write(f"## PNG absents de l'actuel ({len(only_in_ref_png)})\n\n")
            f.write(f"{', '.join(sorted(only_in_ref_png))}\n\n")

        if only_in_current_png:
            f.write(f"## PNG nouveaux ({len(only_in_current_png)})\n\n")
            f.write(f"{', '.join(sorted(only_in_current_png))}\n\n")


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


def compare_mask_pixels(ref_png: Path, current_png: Path) -> dict:
    """
    Compare deux masques PNG pixel par pixel.

    Args:
        ref_png: Masque de référence
        current_png: Masque actuel

    Returns:
        {
            "identical": bool,
            "diff_pixels": int | None,
            "max_diff": float | None,  # 0-1 normalisé
            "error": str | None
        }
    """
    import cv2
    import numpy as np

    try:
        # Lire les deux images en 16-bit (IMREAD_UNCHANGED)
        ref = cv2.imread(str(ref_png), cv2.IMREAD_UNCHANGED)
        current = cv2.imread(str(current_png), cv2.IMREAD_UNCHANGED)

        if ref is None:
            return {"identical": False, "diff_pixels": None, "max_diff": None,
                    "error": f"Référence illisible: {ref_png}"}
        if current is None:
            return {"identical": False, "diff_pixels": None, "max_diff": None,
                    "error": f"Actuel illisible: {current_png}"}

        # Vérifier les dimensions
        if ref.shape != current.shape:
            return {"identical": False, "diff_pixels": None, "max_diff": None,
                    "error": f"Dimensions différentes: {ref.shape} vs {current.shape}"}

        # Comparer les pixels
        diff_mask = (ref != current)
        diff_pixels = int(np.sum(diff_mask))

        if diff_pixels == 0:
            return {"identical": True, "diff_pixels": 0, "max_diff": 0.0, "error": None}

        # Calculer écart max normalisé
        abs_diff = np.abs(ref.astype(np.float32) - current.astype(np.float32))
        max_diff_raw = float(np.max(abs_diff))
        # Normaliser selon le dtype
        if ref.dtype == np.uint16:
            max_diff_norm = max_diff_raw / 65535.0
        else:
            max_diff_norm = max_diff_raw / 255.0

        return {
            "identical": False,
            "diff_pixels": diff_pixels,
            "max_diff": max_diff_norm,
            "error": None
        }

    except Exception as e:
        return {"identical": False, "diff_pixels": None, "max_diff": None,
                "error": f"Erreur comparaison: {e}"}


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
# COMPARAISON CORRECTIONS
# ===============================================================================

def normalize_corrections_json(data: dict, project_path: Path) -> dict:
    """
    Normalise un JSON Corrections pour la comparaison.

    - Retire dates, durées, chemins temporaires
    - Convertit chemins absolus en relatifs au dossier projet
    - Traite récursivement les structures imbriquées

    Args:
        data: Dictionnaire JSON à normaliser
        project_path: Chemin absolu du dossier projet (base pour chemins relatifs)

    Returns:
        Dictionnaire normalisé
    """
    import re

    # Champs à retirer (dates, durées)
    REMOVED_FIELDS = {
        "generated_at", "timestamp", "date", "created_at",
        "duration", "duration_s", "elapsed_time", "processing_time_ms",
        "modified_time"
    }

    # Convertir chemin absolu en relatif
    def normalize_path(path_str: str) -> str:
        # Ignorer les chemins vides
        if not path_str:
            return path_str

        # Détecter chemins temporaires (les marquer comme tels)
        if re.search(r'[\\/][Tt]emp[\\/]|[\\/]tmp[\\/]', path_str):
            return "<TEMP_PATH>"

        # Convertir en Path pour normalisation
        try:
            p = Path(path_str)
            if p.is_absolute():
                # Essayer de rendre relatif au projet
                try:
                    rel = p.relative_to(project_path)
                    return str(rel).replace('\\', '/')
                except ValueError:
                    # Hors projet : garder absolu mais normaliser les séparateurs
                    return str(p).replace('\\', '/')
            return path_str.replace('\\', '/')
        except Exception:
            return path_str

    # Fonction récursive de normalisation
    def normalize_value(value):
        if isinstance(value, dict):
            result = {}
            for k, v in value.items():
                # Ignorer les champs à retirer
                if k in REMOVED_FIELDS:
                    continue
                # Normaliser la valeur
                result[k] = normalize_value(v)
            return result
        elif isinstance(value, list):
            return [normalize_value(item) for item in value]
        elif isinstance(value, str):
            # Si c'est un chemin (contient \\ ou /, ou finit par extension connue)
            if ('\\' in value or '/' in value or
                any(value.endswith(ext) for ext in ['.png', '.json', '.ttile', '.terr', '.edds', '.dds'])):
                return normalize_path(value)
            return value
        else:
            return value

    return normalize_value(data)


def compare_corrections_json(ref_path: Path, current_path: Path, project_path: Path) -> dict:
    """
    Compare deux JSON Corrections normalisés.

    Args:
        ref_path: Chemin du JSON de référence
        current_path: Chemin du JSON actuel
        project_path: Chemin du projet (pour normalisation)

    Returns:
        {
            "identical": bool,
            "diff_keys": [{"key": str, "ref": any, "current": any}] ou None,  # Max 30
            "total_diffs": int,
            "error": str ou None
        }
    """
    try:
        # Lire les deux JSON
        ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
        current_data = json.loads(current_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"identical": False, "diff_keys": None, "total_diffs": 0, "error": f"Erreur lecture : {e}"}

    try:
        # Normaliser
        ref_norm = normalize_corrections_json(ref_data, project_path)
        current_norm = normalize_corrections_json(current_data, project_path)

        # Comparer directement
        if ref_norm == current_norm:
            return {"identical": True, "diff_keys": None, "total_diffs": 0, "error": None}

        # Trouver les différences (parcours récursif)
        diffs = []

        def find_diffs(ref_val, curr_val, path=""):
            if type(ref_val) != type(curr_val):
                diffs.append({
                    "key": path,
                    "ref": f"type: {type(ref_val).__name__}",
                    "current": f"type: {type(curr_val).__name__}"
                })
            elif isinstance(ref_val, dict):
                all_keys = set(ref_val.keys()) | set(curr_val.keys())
                for k in sorted(all_keys):
                    new_path = f"{path}.{k}" if path else k
                    if k not in ref_val:
                        diffs.append({"key": new_path, "ref": "<absent>", "current": str(curr_val[k])[:100]})
                    elif k not in curr_val:
                        diffs.append({"key": new_path, "ref": str(ref_val[k])[:100], "current": "<absent>"})
                    elif ref_val[k] != curr_val[k]:
                        find_diffs(ref_val[k], curr_val[k], new_path)
            elif isinstance(ref_val, list):
                if len(ref_val) != len(curr_val):
                    diffs.append({
                        "key": f"{path}[length]",
                        "ref": len(ref_val),
                        "current": len(curr_val)
                    })
                for i, (r, c) in enumerate(zip(ref_val, curr_val)):
                    if r != c:
                        find_diffs(r, c, f"{path}[{i}]")
            else:
                # Valeurs simples différentes
                diffs.append({
                    "key": path,
                    "ref": str(ref_val)[:100],
                    "current": str(curr_val)[:100]
                })

        find_diffs(ref_norm, current_norm)

        return {
            "identical": False,
            "diff_keys": diffs[:30],  # Max 30 pour affichage
            "total_diffs": len(diffs),
            "error": None
        }

    except Exception as e:
        return {"identical": False, "diff_keys": None, "total_diffs": 0, "error": f"Erreur comparaison : {e}"}


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


def cmd_enregistrer_single_project(project_name: str, project_path: Path, masks_only: bool = False, corrections_only: bool = False) -> int:
    """
    Enregistre une reference pour un seul projet.

    Returns:
        0 si OK, 1 si erreurs
    """
    print(f"=== Enregistrement reference pour projet : {project_name} ===")
    print(f"    Projet : {project_path}")
    print()

    test_dir = project_path / "test"

    # Verification si test/ ou corrections/ existe deja
    if corrections_only:
        # Mode --corrections-seulement : ne vérifier que si corrections/ existe
        corrections_dir = test_dir / "corrections"
        if corrections_dir.exists():
            print(f"[!!] Dossier test/corrections/ existe deja")
            print(f"     Fichiers : {list(corrections_dir.glob('*'))}")
            print()
            reponse = input("     Ecraser test/corrections/ ? (o/N) : ").strip().lower()
            if reponse != 'o':
                print("[--] Annule")
                return 0
            print()
    elif masks_only:
        # Mode --masques-seulement : ne vérifier que si masks/ existe
        masks_dir = test_dir / "masks"
        if masks_dir.exists():
            print(f"[!!] Dossier test/masks/ existe deja")
            print(f"     Fichiers : {len(list(masks_dir.glob('*.png')))} masques PNG")
            print()
            reponse = input("     Ecraser test/masks/ et satmap/scan ? (o/N) : ").strip().lower()
            if reponse != 'o':
                print("[--] Annule")
                return 0
            print()
    else:
        # Mode normal : vérifier test/
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
            reponse = input("     Ecraser la reference existante complete ? (o/N) : ").strip().lower()
            if reponse != 'o':
                print("[--] Annule")
                return 0
            print()

    # Creer test/
    test_dir.mkdir(parents=True, exist_ok=True)

    # Preparer manifest (charger l'existant si corrections_only ou masks_only)
    manifest_path = test_dir / "manifest.json"
    if (corrections_only or masks_only) and manifest_path.exists():
        # Charger le manifest existant et ne mettre à jour que la partie concernée
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Mettre à jour la date pour la partie modifiée
            if corrections_only:
                manifest["date_corrections"] = datetime.now().isoformat()
            elif masks_only:
                manifest["date_masks"] = datetime.now().isoformat()
        except Exception:
            # Manifest illisible : en créer un nouveau
            manifest = {
                "date": datetime.now().isoformat(),
                "commit": get_git_commit(),
                "project": project_name,
                "elements": {}
            }
    else:
        # Créer nouveau manifest
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
        masks_success = False

        # === SATMAP ===
        if not masks_only and not corrections_only:
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
                        manifest["elements"]["satmap"] = {"status": "ok"}
                    else:
                        print(f"     [KO] Erreur creation miniature")
                        manifest["elements"]["satmap"] = {"status": "error", "error": "Erreur creation miniature"}
                except Exception as e:
                    print(f"     [KO] Erreur traitement : {e}")
                    manifest["elements"]["satmap"] = {"status": "error", "error": str(e)}

            print()

            # === SCAN ===
            if not corrections_only:
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
            else:
                scan_success = True  # Skip

            print()

        # === MASQUES ===
        if not corrections_only:
            print("=== MASQUES ===")
            start_time = time.time()
            result = generate_masks_in_temp(project_path, temp_path)
            duration = time.time() - start_time
        else:
            masks_success = True  # Skip
            result = {"ok": True, "masks": []}
            duration = 0.0

        if not result["ok"]:
            print(f"[KO] Erreur generation : {result['error']}")
            manifest["elements"]["masks"] = {"status": "error", "error": result["error"]}
        else:
            masks_list = result["masks"]
            if not corrections_only:
                print(f"[OK] {len(masks_list)} masques generes (duree: {duration:.1f}s)")

                try:
                    # Créer dossier masks/
                    masks_dir = test_dir / "masks"
                    masks_dir.mkdir(parents=True, exist_ok=True)

                    # Copier les PNG et calculer les hash
                    import cv2
                    masks_hash = {}
                    for mask_name in masks_list:
                        src = temp_path / mask_name
                        dst = masks_dir / mask_name

                        # Copier le fichier
                        shutil.copy2(src, dst)
                        print(f"     [OK] {dst}")

                        # Calculer hash des pixels (16-bit)
                        img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
                        if img is not None:
                            pixel_hash = hashlib.sha256(img.tobytes()).hexdigest()
                            masks_hash[mask_name] = {
                                "hash": pixel_hash,
                                "shape": img.shape,
                                "dtype": str(img.dtype)
                            }

                    # Sauvegarder masks_hash.json
                    hash_json = masks_dir / "masks_hash.json"
                    hash_json.write_text(json.dumps(masks_hash, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"     [OK] Hash enregistre : {hash_json}")

                    masks_success = True
                    manifest["elements"]["masks"] = {"status": "ok", "duration_s": round(duration, 1)}

                except Exception as e:
                    print(f"     [KO] Erreur traitement : {e}")
                    manifest["elements"]["masks"] = {"status": "error", "error": str(e)}

        print()

        # === CORRECTIONS ===
        if not masks_only:  # Corrections exécutées sauf si --masques-seulement
            print("=== CORRECTIONS ===")
            corrections_success = False

            try:
                # Lire grille du projet
                grid = get_project_grid(project_path)
                if not grid.get("ok"):
                    print(f"[KO] Erreur lecture grille : {grid['error']}")
                    manifest["elements"]["corrections"] = {"status": "error", "error": grid["error"]}
                else:
                    grid_w = grid["grid_w"]
                    num_blk = grid["num_blk"]

                    # Obtenir dirs terrain
                    dirs = get_terrain_dirs(project_path)
                    if not dirs["ok"]:
                        print(f"[KO] Erreur lecture terrain : {dirs['error']}")
                        manifest["elements"]["corrections"] = {"status": "error", "error": dirs["error"]}
                    else:
                        data_dir = Path(dirs["data_dir"])
                        prefix_result = project_reader.get_tile_prefix(data_dir)
                        if not prefix_result.get("ok"):
                            print(f"[KO] Erreur détection préfixe : {prefix_result['error']}")
                            manifest["elements"]["corrections"] = {"status": "error", "error": prefix_result["error"]}
                        else:
                            tile_prefix = prefix_result["tile_prefix"]

                            # 1. Sélectionner tuiles de référence
                            print("[1/4] Sélection des tuiles de référence...")
                            tiles_result = select_reference_tiles(project_path, data_dir, grid_w, num_blk, tile_prefix, verbose=True)
                            if not tiles_result.get("ok"):
                                print(f"     [KO] {tiles_result['error']}")
                                manifest["elements"]["corrections"] = {"status": "error", "error": tiles_result["error"]}
                            else:
                                selected = tiles_result["selected"]
                                print(f"     [OK] {len(selected)} tuile(s) sélectionnée(s)")
                                for key, info in selected.items():
                                    print(f"          {key}: tid={info['tid']} ({info['tx']},{info['ty']})")

                                # Sauvegarder tiles.json
                                corrections_dir = test_dir / "corrections"
                                corrections_dir.mkdir(parents=True, exist_ok=True)
                                tiles_json = corrections_dir / "tiles.json"
                                tiles_json.write_text(
                                    json.dumps({"selected": selected}, indent=2, ensure_ascii=False),
                                    encoding="utf-8"
                                )
                                print(f"     [OK] Sauvegardé : {tiles_json}")

                                # 2. Créer masque de zone
                                print("[2/4] Création du masque de zone...")
                                mask_result = create_zone_mask(project_path, grid_w)
                                if not mask_result.get("ok"):
                                    print(f"     [KO] {mask_result['error']}")
                                else:
                                    mask_path = mask_result["mask_path"]
                                    print(f"     [OK] Masque créé : {mask_path}")

                                    # 3. Générer résultats Corrections (dossier temporaire propre)
                                    print("[3/4] Génération des résultats Corrections (via worker)...")
                                    start_time = time.time()

                                    with tempfile.TemporaryDirectory() as corrections_temp_dir:
                                        corrections_temp_path = Path(corrections_temp_dir)
                                        gen_result = generate_corrections_in_temp(project_path, corrections_temp_path)
                                        duration = time.time() - start_time

                                        if not gen_result.get("ok"):
                                            print(f"     [KO] {gen_result['error']}")
                                            manifest["elements"]["corrections"] = {"status": "error", "error": gen_result["error"]}
                                        else:
                                            print(f"     [OK] Généré (durée: {duration:.1f}s)")

                                            # 4. Copier les résultats dans test/corrections/ (LISTE BLANCHE STRICTE)
                                            print("[4/4] Copie des résultats...")
                                            try:
                                                # Liste blanche des JSON générés par le worker
                                                json_whitelist = {
                                                    "inspect_tile.json",
                                                    "inspection_scan_tiles.json",
                                                    "corrections_inspect_tile.json",
                                                    "corrections_scan_global.json",
                                                    "corrections_scan_zone.json",
                                                    "corrections_terrain_health.json",
                                                    "corrections_file_inventory.json"
                                                }

                                                # Copier uniquement les JSON de la liste blanche
                                                for json_name in json_whitelist:
                                                    json_file = corrections_temp_path / json_name
                                                    if json_file.exists():
                                                        shutil.copy2(json_file, corrections_dir / json_name)
                                                        print(f"     [OK] {json_name}")

                                                # Copier uniquement les PNG tile_{tx}_{ty}*.png
                                                for png_file in corrections_temp_path.glob("tile_*_*.png"):
                                                    shutil.copy2(png_file, corrections_dir / png_file.name)
                                                    print(f"     [OK] {png_file.name}")

                                                corrections_success = True
                                                manifest["elements"]["corrections"] = {"status": "ok", "duration_s": round(duration, 1)}

                                                # Ajouter note pour ZBK si nécessaire
                                                if project_name == "Zbk_island":
                                                    if "notes" not in manifest:
                                                        manifest["notes"] = []
                                                    manifest["notes"].append(
                                                        "corrections_inspect_tile enregistré AVEC le bug connu (grille et préfixe de Zimnitrita appliqués) ; "
                                                        "une différence est attendue sur cet élément à l'étape 4b."
                                                    )
                                                    manifest["notes"].append(
                                                        "corrections_scan_zone : échelle du masque calculée pour 32 tuiles (bug connu, à corriger à l'étape 4b)."
                                                    )

                                            except Exception as e:
                                                print(f"     [KO] Erreur copie : {e}")
                                                manifest["elements"]["corrections"] = {"status": "error", "error": str(e)}

            except Exception as e:
                print(f"[KO] Erreur Corrections : {e}")
                manifest["elements"]["corrections"] = {"status": "error", "error": str(e)}

            print()

    # Ecrire manifest
    manifest_path = test_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Manifest enregistre : {manifest_path}")

    print()
    print("=" * 70)

    # Bilan
    if masks_only:
        if masks_success:
            print("[OK] ENREGISTREMENT TERMINE")
            print("     Masques : [OK]")
        else:
            print("[!!] ENREGISTREMENT PARTIEL")
            print("     Masques : [KO]")
        print("=" * 70)
        return 0 if masks_success else 1
    elif corrections_only:
        # Vérifier si corrections_success existe
        corrections_success = manifest["elements"].get("corrections", {}).get("status") == "ok"
        if corrections_success:
            print("[OK] ENREGISTREMENT TERMINE")
            print("     Corrections : [OK]")
        else:
            print("[!!] ENREGISTREMENT PARTIEL")
            print("     Corrections : [KO]")
        print("=" * 70)
        return 0 if corrections_success else 1
    else:
        # Vérifier si corrections_success existe (peut ne pas être défini si erreur avant)
        corrections_success = manifest["elements"].get("corrections", {}).get("status") == "ok"

        all_ok = satmap_success and scan_success and masks_success and corrections_success
        if all_ok:
            print("[OK] ENREGISTREMENT TERMINE")
            print("     Satmap      : [OK]")
            print("     Scan        : [OK]")
            print("     Masques     : [OK]")
            print("     Corrections : [OK]")
        else:
            print("[!!] ENREGISTREMENT PARTIEL")
            print(f"     Satmap      : {'[OK]' if satmap_success else '[KO]'}")
            print(f"     Scan        : {'[OK]' if scan_success else '[KO]'}")
            print(f"     Masques     : {'[OK]' if masks_success else '[KO]'}")
            print(f"     Corrections : {'[OK]' if corrections_success else '[KO]'}")
        print("=" * 70)
        return 0 if all_ok else 1


def cmd_enregistrer(project_name: str, masks_only: bool = False, corrections_only: bool = False) -> int:
    """
    Commande enregistrer : enregistre une reference dans data/projects/<nom>/test/

    Args:
        project_name: Nom du projet ou "tous"
        masks_only: Si True, enregistrer uniquement les masques
        corrections_only: Si True, enregistrer uniquement les Corrections

    Returns:
        0 si OK, 1 si erreurs
    """
    if project_name == "tous":
        # Mode tous : utiliser EXCLUSIVEMENT REFERENCE_PROJECTS
        print("=== Enregistrement tous les projets ===")
        print()

        all_projects = REFERENCE_PROJECTS

        print(f"Projets de référence : {', '.join(all_projects)}")
        print()

        # Enregistrer chaque projet
        results = {}
        for pname in sorted(all_projects):
            ppath = PROJECTS_DIR / pname
            exit_code = cmd_enregistrer_single_project(pname, ppath, masks_only=masks_only, corrections_only=corrections_only)
            results[pname] = exit_code
            print()

        # Bilan global
        print("=" * 70)
        ok_count = sum(1 for code in results.values() if code == 0)
        ko_count = len(results) - ok_count

        print(f"BILAN GLOBAL : {ok_count} OK, {ko_count} KO")
        for pname, code in sorted(results.items()):
            status = "[OK]" if code == 0 else "[KO]"
            print(f"  {pname}: {status}")
        print("=" * 70)

        return 0 if ko_count == 0 else 1

    else:
        # Mode projet unique
        project_path = PROJECTS_DIR / project_name
        if not project_path.exists():
            print(f"[KO] Projet introuvable : {project_path}")
            return 1

        return cmd_enregistrer_single_project(project_name, project_path, masks_only=masks_only, corrections_only=corrections_only)


def cmd_comparer_project(project_name: str, project_path: Path, ref_dir: Optional[Path] = None, masks_only: bool = False, corrections_only: bool = False, detail_dir: Optional[Path] = None) -> dict:
    """
    Compare un projet a sa reference.

    Args:
        project_name: Nom du projet
        project_path: Chemin du projet
        ref_dir: Dossier de reference a utiliser (par defaut: project_path/test)
        masks_only: Si True, comparer uniquement les masques
        corrections_only: Si True, comparer uniquement les Corrections
        detail_dir: Si fourni, sauvegarder les fichiers generes et differences dans ce dossier

    Returns:
        {
            "project": str,
            "has_test": bool,
            "satmap_status": "ok" | "ko" | "skip" | "error",
            "satmap_detail": str,
            "scan_status": "ok" | "ko" | "skip" | "error",
            "scan_detail": str,
            "masks_status": "ok" | "ko" | "skip" | "error",
            "masks_detail": str,
            "corrections_status": "ok" | "ko" | "skip" | "error",
            "corrections_detail": str
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
            "masks_status": "skip",
            "masks_detail": "Pas de reference (dossier test/ absent)",
            "corrections_status": "skip",
            "corrections_detail": "Pas de reference (dossier test/ absent)",
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
            "masks_status": "skip",
            "masks_detail": "Manifest absent",
            "corrections_status": "skip",
            "corrections_detail": "Manifest absent",
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
            "masks_status": "skip",
            "masks_detail": f"Erreur lecture manifest : {e}",
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
        "masks_status": "skip",
        "masks_detail": "",
        "corrections_status": "skip",
        "corrections_detail": "",
    }

    # === SATMAP ===
    if masks_only or corrections_only:
        result["satmap_status"] = "skip"
        result["satmap_detail"] = "Skip (--masques-seulement)" if masks_only else "Skip (--corrections-seulement)"
    else:
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

                                # Sauvegarder détails si demandé (même si identique)
                                if detail_dir:
                                    satmap_detail_dir = detail_dir / "satmap"
                                    save_satmap_detail(satmap_detail_dir, current_satmap, ref_hash_data, current_hash, None)
                            else:
                                result["satmap_status"] = "ko"
                                result["satmap_detail"] = f"Difference detectee (hash: {current_hash['hash'][:16]}... vs ref: {ref_hash[:16]}...)"

                                # Creer diff_thumb.png avec rectangle englobant
                                ref_thumb = test_dir / "satmap_thumb.png"
                                diff_thumb = test_dir / "diff_thumb.png"
                                diff_result = None
                                if ref_thumb.exists():
                                    diff_result = create_diff_thumbnail(ref_thumb, current_satmap, diff_thumb, grid_w)
                                    if diff_result["ok"]:
                                        result["satmap_detail"] += f" | diff_thumb.png cree"
                                        if diff_result["bbox_tiles"]:
                                            bbox = diff_result["bbox_tiles"]
                                            result["satmap_detail"] += f" | zone tuiles: ({bbox['x_min']},{bbox['y_min']})-({bbox['x_max']},{bbox['y_max']})"
                                        else:
                                            result["satmap_detail"] += " | difference plus fine que la resolution de la miniature"

                                # Sauvegarder détails si demandé
                                if detail_dir:
                                    satmap_detail_dir = detail_dir / "satmap"
                                    save_satmap_detail(satmap_detail_dir, current_satmap, ref_hash_data, current_hash, diff_result)

                        except Exception as e:
                            result["satmap_status"] = "error"
                            result["satmap_detail"] = f"[ERREUR] Comparaison : {e}"

    # === SCAN ===
    if masks_only or corrections_only:
        result["scan_status"] = "skip"
        result["scan_detail"] = "Skip (--masques-seulement)" if masks_only else "Skip (--corrections-seulement)"
    else:
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

                                # Sauvegarder détails si demandé (même si identique)
                                if detail_dir:
                                    scan_detail_dir = detail_dir / "scan"
                                    save_scan_detail(scan_detail_dir, current_scan, ref_scan, cmp)
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

                                # Sauvegarder détails si demandé
                                if detail_dir:
                                    scan_detail_dir = detail_dir / "scan"
                                    save_scan_detail(scan_detail_dir, current_scan, ref_scan, cmp)

                        except Exception as e:
                            result["scan_status"] = "error"
                            result["scan_detail"] = f"[ERREUR] Comparaison : {e}"

    # === MASQUES ===
    if corrections_only:
        result["masks_status"] = "skip"
        result["masks_detail"] = "Skip (--corrections-seulement)"
    else:
        # Comparer uniquement si reference existe (manifest.elements.masks)
        masks_ref = elements.get("masks", {})
        if masks_ref.get("status") == "error":
            result["masks_status"] = "skip"
            result["masks_detail"] = f"Reference en erreur : {masks_ref.get('error', 'inconnue')}"
        elif not masks_ref:
            # Pas de référence masques enregistrée
            result["masks_status"] = "skip"
            result["masks_detail"] = "Pas de reference masques enregistree"
        else:
            # Référence existe : comparer
            masks_dir = test_dir / "masks"
            hash_json = masks_dir / "masks_hash.json"

            if not masks_dir.exists() or not hash_json.exists():
                result["masks_status"] = "error"
                result["masks_detail"] = "Dossier masks/ ou masks_hash.json absent"
            else:
                # Générer masques actuels
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    start_time = time.time()
                    gen_result = generate_masks_in_temp(project_path, temp_path)
                    duration = time.time() - start_time

                    if not gen_result["ok"]:
                        result["masks_status"] = "ko"
                        result["masks_detail"] = f"Erreur generation : {gen_result['error']}"
                    else:
                        current_masks = gen_result["masks"]

                        # Charger hash de référence
                        try:
                            ref_hash_data = json.loads(hash_json.read_text(encoding="utf-8"))
                            ref_mask_names = set(ref_hash_data.keys())
                            current_mask_names = set(current_masks)

                            # Vérifier présence/absence
                            only_in_ref = ref_mask_names - current_mask_names
                            only_in_current = current_mask_names - ref_mask_names
                            common = ref_mask_names & current_mask_names

                            # Comparer les masques communs
                            diff_masks = []
                            for mask_name in sorted(common):
                                ref_png = masks_dir / mask_name
                                current_png = temp_path / mask_name

                                if not ref_png.exists():
                                    diff_masks.append({
                                        "name": mask_name,
                                        "error": "Reference PNG absent"
                                    })
                                    continue

                                if not current_png.exists():
                                    diff_masks.append({
                                        "name": mask_name,
                                        "error": "Actuel PNG absent"
                                    })
                                    continue

                                # Comparer pixels
                                cmp = compare_mask_pixels(ref_png, current_png)
                                if cmp.get("error"):
                                    diff_masks.append({
                                        "name": mask_name,
                                        "error": cmp["error"]
                                    })
                                elif not cmp["identical"]:
                                    diff_masks.append({
                                        "name": mask_name,
                                        "diff_pixels": cmp["diff_pixels"],
                                        "max_diff": cmp["max_diff"]
                                    })

                            # Résultat
                            if not only_in_ref and not only_in_current and not diff_masks:
                                result["masks_status"] = "ok"
                                result["masks_detail"] = f"Identiques ({len(common)} masques, {duration:.1f}s)"

                                # Sauvegarder détails si demandé (même si identique)
                                if detail_dir:
                                    masks_detail_dir = detail_dir / "masks"
                                    save_masks_detail(masks_detail_dir, temp_path, masks_dir, [], set(), set())
                            else:
                                result["masks_status"] = "ko"
                                details = []

                                if diff_masks:
                                    details.append(f"{len(diff_masks)} masque(s) different(s) : {', '.join(m['name'] for m in diff_masks[:5])}")
                                    if len(diff_masks) > 5:
                                        details[-1] += f" ... +{len(diff_masks)-5} autres"

                                if only_in_ref:
                                    names = ', '.join(sorted(only_in_ref)[:5])
                                    if len(only_in_ref) > 5:
                                        names += f" ... +{len(only_in_ref)-5} autres"
                                    details.append(f"{len(only_in_ref)} masque(s) absent(s) de l'actuel : {names}")

                                if only_in_current:
                                    names = ', '.join(sorted(only_in_current)[:5])
                                    if len(only_in_current) > 5:
                                        names += f" ... +{len(only_in_current)-5} autres"
                                    details.append(f"{len(only_in_current)} masque(s) nouveau(x) : {names}")

                                result["masks_detail"] = " | ".join(details)

                                # Sauvegarder détails si demandé
                                if detail_dir:
                                    masks_detail_dir = detail_dir / "masks"
                                    save_masks_detail(masks_detail_dir, temp_path, masks_dir, diff_masks, only_in_ref, only_in_current)

                        except Exception as e:
                            result["masks_status"] = "error"
                            result["masks_detail"] = f"[ERREUR] Comparaison : {e}"

    # === CORRECTIONS ===
    if masks_only:
        result["corrections_status"] = "skip"
        result["corrections_detail"] = "Skip (--masques-seulement)"
    else:
        corrections_ref = elements.get("corrections", {})
        if corrections_ref.get("status") == "error":
            result["corrections_status"] = "error"
            result["corrections_detail"] = f"Reference en erreur : {corrections_ref.get('error', 'inconnue')}"
        elif not corrections_ref:
            # Pas de référence corrections enregistrée
            result["corrections_status"] = "error"
            result["corrections_detail"] = "Pas de reference Corrections enregistree"
        else:
            # Référence existe : comparer
            corrections_dir = test_dir / "corrections"

            if not corrections_dir.exists():
                result["corrections_status"] = "error"
                result["corrections_detail"] = "Dossier corrections/ absent"
            else:
                # Liste blanche stricte des JSON générés par le worker
                json_whitelist = {
                    "inspect_tile.json",
                    "inspection_scan_tiles.json",
                    "corrections_inspect_tile.json",
                    "corrections_scan_global.json",
                    "corrections_scan_zone.json",
                    "corrections_terrain_health.json",
                    "corrections_file_inventory.json"
                }

                # Lister les fichiers de référence (LISTE BLANCHE STRICTE)
                ref_json_files = sorted([f.name for f in corrections_dir.glob("*.json") if f.name in json_whitelist])
                ref_png_files = sorted([f.name for f in corrections_dir.glob("tile_*_*.png")])

                # Générer résultats actuels
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    start_time = time.time()
                    gen_result = generate_corrections_in_temp(project_path, temp_path)
                    duration = time.time() - start_time

                    if not gen_result.get("ok"):
                        result["corrections_status"] = "ko"
                        result["corrections_detail"] = f"Erreur generation : {gen_result['error']}"
                    else:
                        # Lister les fichiers actuels (LISTE BLANCHE STRICTE)
                        current_json_files = sorted([f.name for f in temp_path.glob("*.json") if f.name in json_whitelist])
                        current_png_files = sorted([f.name for f in temp_path.glob("tile_*_*.png")])

                        try:
                            # Vérifier présence/absence de fichiers
                            only_in_ref_json = set(ref_json_files) - set(current_json_files)
                            only_in_current_json = set(current_json_files) - set(ref_json_files)
                            common_json = set(ref_json_files) & set(current_json_files)

                            only_in_ref_png = set(ref_png_files) - set(current_png_files)
                            only_in_current_png = set(current_png_files) - set(ref_png_files)
                            common_png = set(ref_png_files) & set(current_png_files)

                            # Comparer les JSON communs
                            diff_json = []
                            for json_name in sorted(common_json):
                                ref_json = corrections_dir / json_name
                                current_json = temp_path / json_name

                                cmp = compare_corrections_json(ref_json, current_json, project_path)

                                if cmp.get("error"):
                                    diff_json.append({
                                        "name": json_name,
                                        "error": cmp["error"]
                                    })
                                elif not cmp["identical"]:
                                    diff_json.append({
                                        "name": json_name,
                                        "total_diffs": cmp["total_diffs"],
                                        "diff_keys": cmp["diff_keys"]
                                    })

                            # Comparer les PNG communs
                            diff_png = []
                            for png_name in sorted(common_png):
                                ref_png = corrections_dir / png_name
                                current_png = temp_path / png_name

                                cmp = compare_mask_pixels(ref_png, current_png)
                                if cmp.get("error"):
                                    diff_png.append({
                                        "name": png_name,
                                        "error": cmp["error"]
                                    })
                                elif not cmp["identical"]:
                                    diff_png.append({
                                        "name": png_name,
                                        "diff_pixels": cmp["diff_pixels"],
                                        "max_diff": cmp["max_diff"]
                                    })

                            # Résultat global
                            if (not only_in_ref_json and not only_in_current_json and
                                not only_in_ref_png and not only_in_current_png and
                                not diff_json and not diff_png):
                                result["corrections_status"] = "ok"
                                result["corrections_detail"] = f"Identiques ({len(common_json)} JSON, {len(common_png)} PNG, {duration:.1f}s)"

                                # Sauvegarder détails si demandé (même si identique)
                                if detail_dir:
                                    corrections_detail_dir = detail_dir / "corrections"
                                    save_corrections_detail(corrections_detail_dir, temp_path, corrections_dir, project_path,
                                                           [], [], set(), set(), set(), set())
                            else:
                                result["corrections_status"] = "ko"
                                details = []

                                # JSON différents
                                if diff_json:
                                    summary = []
                                    for d in diff_json[:5]:
                                        if "error" in d:
                                            summary.append(f"{d['name']}[ERREUR]")
                                        else:
                                            summary.append(f"{d['name']}({d['total_diffs']} diffs)")
                                    if len(diff_json) > 5:
                                        summary.append(f"+{len(diff_json)-5} autres")
                                    details.append(f"{len(diff_json)} JSON different(s) : {', '.join(summary)}")

                                # PNG différents
                                if diff_png:
                                    summary = []
                                    for d in diff_png[:5]:
                                        if "error" in d:
                                            summary.append(f"{d['name']}[ERREUR]")
                                        else:
                                            summary.append(f"{d['name']}({d['diff_pixels']}px)")
                                    if len(diff_png) > 5:
                                        summary.append(f"+{len(diff_png)-5} autres")
                                    details.append(f"{len(diff_png)} PNG different(s) : {', '.join(summary)}")

                                # JSON présents d'un seul côté
                                if only_in_ref_json:
                                    names = ', '.join(sorted(only_in_ref_json)[:5])
                                    if len(only_in_ref_json) > 5:
                                        names += f" ... +{len(only_in_ref_json)-5} autres"
                                    details.append(f"{len(only_in_ref_json)} JSON absent(s) de l'actuel : {names}")

                                if only_in_current_json:
                                    names = ', '.join(sorted(only_in_current_json)[:5])
                                    if len(only_in_current_json) > 5:
                                        names += f" ... +{len(only_in_current_json)-5} autres"
                                    details.append(f"{len(only_in_current_json)} JSON nouveau(x) : {names}")

                                # PNG présents d'un seul côté
                                if only_in_ref_png:
                                    names = ', '.join(sorted(only_in_ref_png)[:5])
                                    if len(only_in_ref_png) > 5:
                                        names += f" ... +{len(only_in_ref_png)-5} autres"
                                    details.append(f"{len(only_in_ref_png)} PNG absent(s) de l'actuel : {names}")

                                if only_in_current_png:
                                    names = ', '.join(sorted(only_in_current_png)[:5])
                                    if len(only_in_current_png) > 5:
                                        names += f" ... +{len(only_in_current_png)-5} autres"
                                    details.append(f"{len(only_in_current_png)} PNG nouveau(x) : {names}")

                                result["corrections_detail"] = " | ".join(details)

                                # Sauvegarder détails si demandé
                                if detail_dir:
                                    corrections_detail_dir = detail_dir / "corrections"
                                    save_corrections_detail(corrections_detail_dir, temp_path, corrections_dir, project_path,
                                                           diff_json, diff_png, only_in_ref_json, only_in_current_json,
                                                           only_in_ref_png, only_in_current_png)

                        except Exception as e:
                            result["corrections_status"] = "error"
                            result["corrections_detail"] = f"[ERREUR] Comparaison : {e}"

    return result


def cmd_comparer(project_name: str, masks_only: bool = False, corrections_only: bool = False, detail: bool = False) -> int:
    """
    Commande comparer : compare la generation actuelle a la reference.

    Args:
        project_name: Nom du projet ou "tous"
        masks_only: Si True, comparer uniquement les masques
        corrections_only: Si True, comparer uniquement les Corrections
        detail: Si True, sauvegarder les fichiers generes et creer un rapport detaille

    Returns:
        0 si aucun KO, 1 sinon
    """
    # Créer dossier horodaté pour --detail
    detail_root = None
    if detail:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        detail_root = REPO_ROOT / "_archives" / "analyses" / "regression_detail" / timestamp
        detail_root.mkdir(parents=True, exist_ok=True)

    if project_name == "tous":
        # Mode tous : utiliser EXCLUSIVEMENT REFERENCE_PROJECTS
        print("=== Comparaison tous les projets ===")
        print()

        projects_with_test = REFERENCE_PROJECTS

        print(f"Projets de référence : {', '.join(projects_with_test)}")
        print()

        results = []
        for pname in sorted(projects_with_test):
            ppath = PROJECTS_DIR / pname
            project_detail_dir = (detail_root / pname) if detail_root else None
            result = cmd_comparer_project(pname, ppath, masks_only=masks_only, corrections_only=corrections_only, detail_dir=project_detail_dir)
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

            # Masques
            if res["masks_status"] == "ok":
                print(f"  Masques    : [OK] {res['masks_detail']}")
            elif res["masks_status"] == "ko":
                print(f"  Masques    : [KO] {res['masks_detail']}")
            elif res["masks_status"] == "error":
                print(f"  Masques    : [ERREUR] {res['masks_detail']}")
            else:
                print(f"  Masques    : [SKIP] {res['masks_detail']}")

            # Corrections
            if res["corrections_status"] == "ok":
                print(f"  Corrections: [OK] {res['corrections_detail']}")
            elif res["corrections_status"] == "ko":
                print(f"  Corrections: [KO] {res['corrections_detail']}")
            elif res["corrections_status"] == "error":
                print(f"  Corrections: [ERREUR] {res['corrections_detail']}")
            else:
                print(f"  Corrections: [SKIP] {res['corrections_detail']}")

            print()

        # CORRECTION PHASE 2C : bilan global correct (OK / PARTIEL / KO)
        print("=" * 70)
        ok_count = 0
        partiel_count = 0
        ko_count = 0

        for r in results:
            # Collecter les statuts des éléments comparés (non-skip)
            compared_statuses = []
            if r["satmap_status"] != "skip":
                compared_statuses.append(r["satmap_status"])
            if r["scan_status"] != "skip":
                compared_statuses.append(r["scan_status"])
            if r["masks_status"] != "skip":
                compared_statuses.append(r["masks_status"])
            if r["corrections_status"] != "skip":
                compared_statuses.append(r["corrections_status"])

            # Classement selon les éléments comparés uniquement
            if any(s in ["ko", "error"] for s in compared_statuses):
                ko_count += 1
            elif all(s == "ok" for s in compared_statuses) and len(compared_statuses) > 0:
                ok_count += 1
            else:
                # Cas où rien n'a été comparé (tous skip) ou mix de statuts
                partiel_count += 1

        print(f"BILAN GLOBAL : {ok_count} OK, {partiel_count} PARTIEL, {ko_count} KO")
        print("=" * 70)

        # Afficher le chemin du dossier de détail si --detail
        if detail_root:
            print()
            print(f"Détails sauvegardés dans : {detail_root.resolve()}")
            print()

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

        project_detail_dir = (detail_root / project_name) if detail_root else None
        result = cmd_comparer_project(project_name, project_path, masks_only=masks_only, corrections_only=corrections_only, detail_dir=project_detail_dir)

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
            print(f"Scan    : [OK] {result['scan_detail']}")
        elif result["scan_status"] == "ko":
            print(f"Scan    : [KO] {result['scan_detail']}")
        elif result["scan_status"] == "error":
            print(f"Scan    : [ERREUR] {result['scan_detail']}")
        else:
            print(f"Scan    : [SKIP] {result['scan_detail']}")

        print()

        # Masques
        if result["masks_status"] == "ok":
            print(f"Masques     : [OK] {result['masks_detail']}")
        elif result["masks_status"] == "ko":
            print(f"Masques     : [KO] {result['masks_detail']}")
        elif result["masks_status"] == "error":
            print(f"Masques     : [ERREUR] {result['masks_detail']}")
        else:
            print(f"Masques     : [SKIP] {result['masks_detail']}")

        print()

        # Corrections
        if result["corrections_status"] == "ok":
            print(f"Corrections : [OK] {result['corrections_detail']}")
        elif result["corrections_status"] == "ko":
            print(f"Corrections : [KO] {result['corrections_detail']}")
        elif result["corrections_status"] == "error":
            print(f"Corrections : [ERREUR] {result['corrections_detail']}")
        else:
            print(f"Corrections : [SKIP] {result['corrections_detail']}")

        print()
        print("=" * 70)

        # Bilan
        has_ko = (result["satmap_status"] == "ko" or result["scan_status"] == "ko" or
                  result["masks_status"] == "ko" or result["corrections_status"] == "ko")
        has_error = (result["satmap_status"] == "error" or result["scan_status"] == "error" or
                     result["masks_status"] == "error" or result["corrections_status"] == "error")

        if has_ko or has_error:
            print("[KO] DIFFERENCES OU ERREURS DETECTEES")
        else:
            print("[OK] AUCUNE DIFFERENCE")

        print("=" * 70)

        # Afficher le chemin du dossier de détail si --detail
        if detail_root:
            print()
            print(f"Détails sauvegardés dans : {detail_root.resolve()}")
            print()

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
    parser.add_argument(
        "--masques-seulement",
        action="store_true",
        help="Enregistrer ou comparer uniquement les masques (pas satmap ni scan)"
    )
    parser.add_argument(
        "--corrections-seulement",
        action="store_true",
        help="Enregistrer ou comparer uniquement les Corrections (pas satmap, scan ni masques)"
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Sauvegarder les fichiers generes et creer un rapport detaille des differences (commande comparer uniquement)"
    )

    args = parser.parse_args()

    # Sauvegarde AVANT toute génération ; restauration dans finally (erreur, Ctrl+C compris),
    # après le retour de la commande, donc après la fin de tous les sous-processus (worker masques)
    snapshot = snapshot_protected_files(get_protected_files(get_tested_projects(args.projet)))

    # Surveiller fichiers terrain AVANT
    terrain_snapshot_before = {}
    if args.commande in ["enregistrer", "comparer"]:
        for pname in get_tested_projects(args.projet):
            ppath = PROJECTS_DIR / pname
            terrain_snapshot_before[pname] = get_terrain_files_snapshot(ppath)

    exit_code = 1
    restore_ok = False
    terrain_files_ok = True

    try:
        if args.commande == "valider-script":
            exit_code = cmd_valider_script(args.projet)
        elif args.commande == "enregistrer":
            exit_code = cmd_enregistrer(args.projet, masks_only=args.masques_seulement, corrections_only=args.corrections_seulement)
        elif args.commande == "comparer":
            exit_code = cmd_comparer(args.projet, masks_only=args.masques_seulement, corrections_only=args.corrections_seulement, detail=args.detail)
        elif args.commande == "tester-detection":
            if args.projet == "tous":
                print("[KO] tester-detection ne supporte pas --projet tous")
                exit_code = 1
            else:
                exit_code = cmd_tester_detection(args.projet)
        else:
            exit_code = 0
    finally:
        # Surveiller fichiers terrain APRÈS
        if args.commande in ["enregistrer", "comparer"]:
            print()
            print("=" * 70)
            print("[SURVEILLANCE] Vérification des fichiers terrain...")

            for pname in get_tested_projects(args.projet):
                ppath = PROJECTS_DIR / pname
                terrain_snapshot_after = get_terrain_files_snapshot(ppath)
                terrain_snapshot_before_project = terrain_snapshot_before.get(pname, {})

                # Si le relevé "avant" a échoué (vide), afficher erreur au lieu de comparer
                if not terrain_snapshot_before_project:
                    terrain_files_ok = False
                    print(f"[KO] {pname} : erreur de surveillance (relevé 'avant' vide ou échoué)")
                    continue

                diff = compare_terrain_files_snapshots(
                    terrain_snapshot_before_project,
                    terrain_snapshot_after
                )

                if diff["changed"]:
                    terrain_files_ok = False
                    print(f"[KO] {pname} : fichiers terrain modifiés !")

                    if diff["created"]:
                        print(f"     Créés ({len(diff['created'])}) :")
                        for f in diff["created"][:10]:
                            print(f"       + {f}")
                        if len(diff["created"]) > 10:
                            print(f"       ... +{len(diff['created'])-10} autres")

                    if diff["deleted"]:
                        print(f"     Supprimés ({len(diff['deleted'])}) :")
                        for f in diff["deleted"][:10]:
                            print(f"       - {f}")
                        if len(diff["deleted"]) > 10:
                            print(f"       ... +{len(diff['deleted'])-10} autres")

                    if diff["modified"]:
                        print(f"     Modifiés ({len(diff['modified'])}) :")
                        for f in diff["modified"][:10]:
                            print(f"       ~ {f}")
                        if len(diff["modified"]) > 10:
                            print(f"       ... +{len(diff['modified'])-10} autres")
                else:
                    print(f"[OK] {pname} : aucun fichier terrain modifié")

            print("=" * 70)
            print()

        restore_ok = restore_protected_files(snapshot)
        if not restore_ok:
            print()
            print("=" * 70)
            print("BILAN GLOBAL : KO (échec restauration des fichiers protégés)")
            print("=" * 70)

    if not restore_ok or not terrain_files_ok:
        return 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
