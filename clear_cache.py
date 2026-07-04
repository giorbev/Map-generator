#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script utilitaire : Vider les caches terrain_data de tous les projets
======================================================================

Usage:
    python clear_cache.py                  # Vide tous les caches
    python clear_cache.py <project_name>   # Vide cache d'un projet spécifique
"""

import sys
from pathlib import Path
import shutil


def clear_all_caches():
    """Vide tous les caches terrain_data.npz du dossier data/projects/"""
    data_dir = Path(__file__).parent / "data" / "projects"

    if not data_dir.exists():
        print(f"❌ Dossier {data_dir} introuvable")
        return

    total_cleared = 0
    total_size_mb = 0.0

    print("🔍 Recherche des caches terrain_data...\n")

    for project_dir in data_dir.iterdir():
        if not project_dir.is_dir():
            continue

        cache_dir = project_dir / "cache"
        if not cache_dir.exists():
            continue

        cache_file = cache_dir / "terrain_data.npz"
        meta_file = cache_dir / "terrain_meta.json"

        if cache_file.exists():
            size_mb = cache_file.stat().st_size / 1024 / 1024
            total_size_mb += size_mb

            # Supprimer cache
            cache_file.unlink()
            print(f"🗑️  Supprimé : {project_dir.name}/cache/terrain_data.npz ({size_mb:.2f} MB)")
            total_cleared += 1

        if meta_file.exists():
            meta_file.unlink()
            print(f"🗑️  Supprimé : {project_dir.name}/cache/terrain_meta.json")

        # Supprimer dossier cache vide
        if cache_dir.exists() and not any(cache_dir.iterdir()):
            cache_dir.rmdir()
            print(f"📁 Dossier cache vide supprimé : {project_dir.name}/cache/")

    print("\n" + "="*60)
    if total_cleared > 0:
        print(f"✅ {total_cleared} cache(s) supprimé(s) ({total_size_mb:.2f} MB libérés)")
    else:
        print("ℹ️  Aucun cache trouvé")
    print("="*60)


def clear_project_cache(project_name):
    """Vide le cache d'un projet spécifique"""
    data_dir = Path(__file__).parent / "data" / "projects"
    project_dir = data_dir / project_name

    if not project_dir.exists():
        print(f"❌ Projet '{project_name}' introuvable dans {data_dir}")
        return

    cache_dir = project_dir / "cache"
    cache_file = cache_dir / "terrain_data.npz"
    meta_file = cache_dir / "terrain_meta.json"

    if not cache_file.exists() and not meta_file.exists():
        print(f"ℹ️  Aucun cache trouvé pour le projet '{project_name}'")
        return

    size_mb = 0.0
    if cache_file.exists():
        size_mb = cache_file.stat().st_size / 1024 / 1024
        cache_file.unlink()
        print(f"🗑️  Supprimé : terrain_data.npz ({size_mb:.2f} MB)")

    if meta_file.exists():
        meta_file.unlink()
        print(f"🗑️  Supprimé : terrain_meta.json")

    # Supprimer dossier cache vide
    if cache_dir.exists() and not any(cache_dir.iterdir()):
        cache_dir.rmdir()
        print(f"📁 Dossier cache vide supprimé")

    print(f"\n✅ Cache du projet '{project_name}' nettoyé ({size_mb:.2f} MB libérés)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Nettoyer projet spécifique
        project_name = sys.argv[1]
        clear_project_cache(project_name)
    else:
        # Nettoyer tous les caches
        clear_all_caches()
