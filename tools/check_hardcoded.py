#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_hardcoded.py — Garde-fou valeurs en dur

Détecte les valeurs interdites dans le code :
- Noms de projets (Zimnitrita, ZBK_island, ZBK_terrain, ZBK_)
- Lettres de disque absolues (I:/, H:/, etc.)
- Préfixes de fichiers (Terrain_, ZBK_terrain_)
- Préfixes de textures custom (zi_, ZI_)

Utilisation :
    python tools/check_hardcoded.py

Sortie :
    - Code 0 : aucune occurrence non couverte par exceptions
    - Code 1 : au moins une occurrence non couverte
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple

# Racine du projet
REPO_ROOT = Path(__file__).resolve().parent.parent

# Fichier des exceptions tolérées
EXCEPTIONS_FILE = REPO_ROOT / "tools" / "hardcoded_exceptions.json"

# Dossiers exclus de la recherche
EXCLUDED_DIRS = {'_archives', '_analyses', 'tools', 'data', 'build', 'dist', '.git', '.venv', '__pycache__'}

# Motifs interdits (case-insensitive)
FORBIDDEN_PATTERNS = {
    'project_name_zimnitrita': re.compile(r'\bZimnitrita\b', re.IGNORECASE),
    'project_name_zbk_island': re.compile(r'\bZbk_island\b', re.IGNORECASE),
    'project_prefix_zbk': re.compile(r'\bZBK_terrain_\b'),  # Case-sensitive (préfixe exact)
    'project_prefix_zbk_short': re.compile(r'\bZBK_\b'),  # Case-sensitive
    'drive_letter': re.compile(r'\b[A-Za-z]:[/\\]'),  # Lettre de disque absolue (\b : ignore "Tiles:\s", "file:///")
    'prefix_terrain': re.compile(r'\bTerrain_\b'),  # Préfixe standard
    'texture_custom_zi': re.compile(r'\bzi_[A-Za-z0-9_]+'),  # Texture custom zi_*
    'texture_custom_ZI': re.compile(r'\bZI_[A-Za-z0-9_]+'),  # Texture custom ZI_*
}


def is_excluded_path(file_path: Path) -> bool:
    """Vérifie si le chemin est dans un dossier exclu."""
    parts = file_path.parts
    return any(excluded in parts for excluded in EXCLUDED_DIRS)


def is_comment_or_docstring(line: str) -> bool:
    """Détecte si une ligne est un commentaire ou dans une docstring (simple heuristique)."""
    stripped = line.strip()
    # Commentaires Python
    if stripped.startswith('#'):
        return True
    # Docstrings (détection simple : lignes contenant uniquement """ ou ''')
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return True
    if stripped.endswith('"""') or stripped.endswith("'''"):
        return True
    return False


def scan_file(file_path: Path) -> List[Tuple[str, int, str, str]]:
    """
    Scanne un fichier pour détecter les motifs interdits.

    Returns:
        Liste de tuples (motif_name, line_num, line_content, extrait)
    """
    findings = []
    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            # Ignorer commentaires et docstrings
            if is_comment_or_docstring(line):
                continue

            # Chercher chaque motif
            for pattern_name, pattern in FORBIDDEN_PATTERNS.items():
                matches = pattern.finditer(line)
                for match in matches:
                    # Extraire 40 caractères autour du match
                    start = max(0, match.start() - 20)
                    end = min(len(line), match.end() + 20)
                    extract = line[start:end].strip()
                    if len(extract) > 60:
                        extract = extract[:57] + '...'

                    findings.append((pattern_name, i, line.strip(), extract))

    except UnicodeDecodeError:
        print(f"[WARNING] Impossible de lire {file_path} (encodage non UTF-8)", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] Erreur lecture {file_path}: {e}", file=sys.stderr)

    return findings


def load_exceptions() -> Dict[str, List[Dict]]:
    """Charge le fichier des exceptions tolérées."""
    if not EXCEPTIONS_FILE.exists():
        return {}

    try:
        return json.loads(EXCEPTIONS_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[ERROR] Erreur lecture {EXCEPTIONS_FILE}: {e}", file=sys.stderr)
        return {}


def is_exception_covered(file_rel: str, pattern_name: str, exceptions: Dict) -> bool:
    """Vérifie si une occurrence est couverte par une exception."""
    file_exceptions = exceptions.get(file_rel, [])

    for exc in file_exceptions:
        if exc.get('pattern') == pattern_name:
            return True

    return False


def count_occurrences(file_path: Path, pattern_name: str) -> int:
    """Compte le nombre d'occurrences d'un motif dans un fichier."""
    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        count = 0

        pattern = FORBIDDEN_PATTERNS[pattern_name]
        for line in lines:
            if is_comment_or_docstring(line):
                continue
            count += len(pattern.findall(line))

        return count
    except:
        return 0


def main():
    print("=== GARDE-FOU VALEURS EN DUR ===\n")

    # Charger exceptions
    exceptions = load_exceptions()
    print(f"✓ Exceptions chargées depuis {EXCEPTIONS_FILE.relative_to(REPO_ROOT)}")
    print(f"  {len(exceptions)} fichiers avec exceptions\n")

    # Scanner tous les fichiers Python et web
    all_findings = {}
    files_scanned = 0

    # Fichiers Python de l'application (app/)
    for py_file in sorted((REPO_ROOT / "app").glob("*.py")):
        if is_excluded_path(py_file):
            continue
        files_scanned += 1
        findings = scan_file(py_file)
        if findings:
            all_findings[py_file] = findings

    # Fichiers web/
    web_dir = REPO_ROOT / "web"
    if web_dir.exists():
        for web_file in sorted(web_dir.glob("*")):
            if web_file.suffix in {'.html', '.js', '.css'}:
                files_scanned += 1
                findings = scan_file(web_file)
                if findings:
                    all_findings[web_file] = findings

    print(f"✓ {files_scanned} fichiers scannés\n")

    # Analyser les résultats
    uncovered = []
    obsolete_exceptions = []

    for file_path, findings in all_findings.items():
        file_rel = str(file_path.relative_to(REPO_ROOT)).replace('\\', '/')

        for pattern_name, line_num, line_content, extract in findings:
            if not is_exception_covered(file_rel, pattern_name, exceptions):
                uncovered.append((file_rel, line_num, pattern_name, extract))

    # Vérifier exceptions obsolètes
    for file_rel, file_exceptions in exceptions.items():
        file_path = REPO_ROOT / file_rel
        if not file_path.exists():
            print(f"[WARNING] Fichier d'exception introuvable : {file_rel}")
            continue

        for exc in file_exceptions:
            pattern_name = exc.get('pattern')
            allowed = exc.get('count', 1)
            actual = count_occurrences(file_path, pattern_name)

            if actual < allowed:
                obsolete_exceptions.append({
                    'file': file_rel,
                    'pattern': pattern_name,
                    'allowed': allowed,
                    'actual': actual,
                    'step': exc.get('step', '?')
                })

    # Afficher résultats
    if uncovered:
        print("=" * 80)
        print("❌ OCCURRENCES NON COUVERTES PAR EXCEPTIONS")
        print("=" * 80)
        for file_rel, line_num, pattern_name, extract in uncovered:
            print(f"\n{file_rel}:{line_num}")
            print(f"  Motif   : {pattern_name}")
            print(f"  Extrait : {extract}")
        print(f"\n{len(uncovered)} occurrence(s) non couverte(s)\n")

    if obsolete_exceptions:
        print("=" * 80)
        print("⚠️  EXCEPTIONS OBSOLÈTES (moins d'occurrences que toléré)")
        print("=" * 80)
        for obs in obsolete_exceptions:
            print(f"\n{obs['file']}")
            print(f"  Motif   : {obs['pattern']}")
            print(f"  Toléré  : {obs['allowed']} occurrences")
            print(f"  Réel    : {obs['actual']} occurrences")
            print(f"  Étape   : {obs['step']}")
        print(f"\n{len(obsolete_exceptions)} exception(s) obsolète(s) à retirer\n")

    # Résultat final
    if not uncovered and not obsolete_exceptions:
        print("=" * 80)
        print("✅ AUCUNE OCCURRENCE NON COUVERTE")
        print("=" * 80)
        print("\nToutes les valeurs en dur sont couvertes par des exceptions.")
        return 0
    elif not uncovered:
        print("=" * 80)
        print("✅ Aucune occurrence non couverte (mais exceptions obsolètes à nettoyer)")
        print("=" * 80)
        return 0
    else:
        print("=" * 80)
        print("❌ ÉCHEC — Occurrences non couvertes détectées")
        print("=" * 80)
        return 1


if __name__ == '__main__':
    sys.exit(main())
