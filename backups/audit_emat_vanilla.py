"""
audit_emat_vanilla.py - Audit complet des fichiers .emat vanilla
Lecture seule, aucune modification de fichier.

Analyse :
1. Paramètres .emat (BCRMiddleMap, MiddleColor, Color, etc.)
2. Comparaison avec vanilla d'origine
3. Vérification existence middle dans texture_Middle/
4. Comparaison avec catalogue
5. Orphelins et middles partagés
"""

import re
import json
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict

from catalog_config import get_catalog_path, TEXTURES_USER_DIR


def extract_emat_params(emat_path: Path) -> Dict[str, str]:
    """
    Extrait les paramètres d'un fichier .emat (lecture texte brute).

    Returns:
        {
            "BCRMiddleMap": str,
            "MiddleColor": str,
            "Color": str,
            "MiddleScaleUV": str,
            "MiddleBCRBlend": str,
            "DebugColor": str,
            "parent": str (si héritage)
        }
    """
    params = {
        "BCRMiddleMap": "ABSENT",
        "MiddleColor": "ABSENT",
        "Color": "ABSENT",
        "MiddleScaleUV": "ABSENT",
        "MiddleBCRBlend": "ABSENT",
        "DebugColor": "ABSENT",
        "parent": "ABSENT"
    }

    try:
        content = emat_path.read_text(encoding='utf-8', errors='ignore')

        # BCRMiddleMap (extraire nom sans GUID ni extension)
        bcr_match = re.search(r'BCRMiddleMap\s+"([^"]+)"', content)
        if bcr_match:
            full_path = bcr_match.group(1)
            # Extraire nom de fichier sans GUID/extension
            name = full_path.split('/')[-1].split('\\')[-1]
            # Retirer GUID {xxx}
            name = re.sub(r'\{[^}]+\}', '', name)
            # Retirer extension
            name = name.rsplit('.', 1)[0] if '.' in name else name
            params["BCRMiddleMap"] = name.strip()

        # MiddleColor
        mc_match = re.search(r'MiddleColor\s+"([^"]+)"', content)
        if mc_match:
            params["MiddleColor"] = mc_match.group(1)

        # Color
        c_match = re.search(r'(?<![a-zA-Z])Color\s+"([^"]+)"', content)
        if c_match:
            params["Color"] = c_match.group(1)

        # MiddleScaleUV
        scale_match = re.search(r'MiddleScaleUV\s+"([^"]+)"', content)
        if scale_match:
            params["MiddleScaleUV"] = scale_match.group(1)

        # MiddleBCRBlend
        blend_match = re.search(r'MiddleBCRBlend\s+"([^"]+)"', content)
        if blend_match:
            params["MiddleBCRBlend"] = blend_match.group(1)

        # DebugColor
        debug_match = re.search(r'DebugColor\s+"([^"]+)"', content)
        if debug_match:
            params["DebugColor"] = debug_match.group(1)

        # Parent (héritage)
        parent_match = re.search(r'Inherit\s+"([^"]+)"', content)
        if parent_match:
            params["parent"] = parent_match.group(1)

    except Exception as e:
        params["_error"] = str(e)

    return params


def is_vanilla_emat(emat_path: Path, vanilla_dir: Path, vanilla_cache: Dict[str, Path]) -> Tuple[bool, str]:
    """
    Vérifie si un .emat est vanilla (identique à la copie vanilla).

    Args:
        vanilla_cache: {filename: full_path} pour éviter recherches répétées

    Returns:
        (is_vanilla, status)
        status: "IDENTICAL" | "MODIFIED" | "NOT_FOUND" | "ERROR"
    """
    if not vanilla_dir.exists():
        return False, "VANILLA_DIR_NOT_FOUND"

    try:
        # Chercher dans le cache d'abord
        if emat_path.name in vanilla_cache:
            vanilla_path = vanilla_cache[emat_path.name]
        else:
            # Chercher récursivement (lent mais nécessaire)
            matches = list(vanilla_dir.glob(f"**/{emat_path.name}"))
            if not matches:
                return False, "NOT_FOUND"
            vanilla_path = matches[0]
            vanilla_cache[emat_path.name] = vanilla_path

        # Comparaison octet par octet
        local_content = emat_path.read_bytes()
        vanilla_content = vanilla_path.read_bytes()

        if local_content == vanilla_content:
            return True, "IDENTICAL"
        else:
            return False, "MODIFIED"

    except Exception as e:
        return False, f"ERROR: {e}"


def find_middle_file(middle_name: str, middles_dir: Path, all_middle_files: List[str]) -> Tuple[bool, Optional[Path], List[str]]:
    """
    Cherche le fichier middle exact ou similaires.

    Returns:
        (found, path, similar_names)
    """
    if middle_name == "ABSENT":
        return False, None, []

    # Essayer extensions
    for ext in ['.jpg', '.png', '.jpeg', '.JPG', '.PNG']:
        middle_path = middles_dir / (middle_name + ext)
        if middle_path.exists():
            return True, middle_path, []

    # Chercher similaires
    similar = difflib.get_close_matches(middle_name, all_middle_files, n=3, cutoff=0.5)

    return False, None, similar


def check_vanilla_edds(middle_name: str, vanilla_dir: Path) -> Tuple[bool, Optional[Path]]:
    """
    Vérifie si le .edds source existe dans la copie vanilla.

    Returns:
        (found, path)
    """
    if middle_name == "ABSENT":
        return False, None

    # Chercher dans vanilla
    # Arma Reforger utilise généralement .edds dans data/
    for pattern in [
        f"**/{middle_name}.edds",
        f"**/{middle_name}_BCR.edds",
        f"**/{middle_name}*.edds"
    ]:
        matches = list(vanilla_dir.glob(pattern))
        if matches:
            return True, matches[0]

    return False, None


def compare_catalog(emat_name: str, emat_params: Dict, catalog: Dict) -> Dict:
    """
    Compare les paramètres .emat avec le catalogue.

    Returns:
        {
            "in_catalog": bool,
            "middle_bcr_match": bool,
            "middle_bcr_catalog": str,
            "tiling_scale_match": bool,
            "tiling_scale_catalog": float,
            "middle_bcr_manual": bool
        }
    """
    result = {
        "in_catalog": False,
        "middle_bcr_match": None,
        "middle_bcr_catalog": "ABSENT",
        "tiling_scale_match": None,
        "tiling_scale_catalog": "ABSENT",
        "middle_bcr_manual": False
    }

    # Chercher dans catalogue
    entry = catalog.get(emat_name) or catalog.get(emat_name.replace(".emat", ""))

    if not entry:
        return result

    result["in_catalog"] = True

    # middle_bcr
    catalog_middle = entry.get("middle_bcr", "ABSENT")
    result["middle_bcr_catalog"] = catalog_middle

    if catalog_middle != "ABSENT" and emat_params["BCRMiddleMap"] != "ABSENT":
        # Comparer noms (sans extension)
        emat_name_clean = emat_params["BCRMiddleMap"].rsplit('.', 1)[0]
        catalog_name_clean = catalog_middle.rsplit('.', 1)[0]
        result["middle_bcr_match"] = (emat_name_clean == catalog_name_clean)

    # tiling_scale vs MiddleScaleUV
    catalog_scale = entry.get("tiling_scale", "ABSENT")
    result["tiling_scale_catalog"] = catalog_scale

    if catalog_scale != "ABSENT" and emat_params["MiddleScaleUV"] != "ABSENT":
        try:
            # MiddleScaleUV peut être "4 4" → prendre premier nombre
            scale_uv = float(emat_params["MiddleScaleUV"].split()[0])
            result["tiling_scale_match"] = abs(catalog_scale - scale_uv) < 0.01
        except:
            pass

    # middle_bcr_manual
    result["middle_bcr_manual"] = entry.get("middle_bcr_manual", False)

    return result


def main():
    print("=" * 80)
    print("AUDIT COMPLET .EMAT VANILLA")
    print("Lecture seule - Aucune modification")
    print("=" * 80)
    print()

    # Chemins (via catalog_config)
    emat_dir = TEXTURES_USER_DIR / "emat"
    middles_dir = TEXTURES_USER_DIR / "texture_Middle"
    catalog_path = get_catalog_path()
    vanilla_dir = Path(r"H:\mod_enfusion\Arma Reforger_copie\addons\data")

    print("📂 CHEMINS ABSOLUS :")
    print(f"  emat_dir     : {emat_dir.absolute()}")
    print(f"  middles_dir  : {middles_dir.absolute()}")
    print(f"  catalog_path : {catalog_path.absolute()}")
    print(f"  vanilla_dir  : {vanilla_dir.absolute()}")
    print()

    # Vérifications
    if not emat_dir.exists():
        print(f"❌ emat_dir introuvable")
        return 1

    if not middles_dir.exists():
        print(f"❌ middles_dir introuvable")
        return 1

    if not catalog_path.exists():
        print(f"❌ catalog introuvable")
        return 1

    if not vanilla_dir.exists():
        print(f"⚠️  vanilla_dir introuvable : {vanilla_dir}")
        print(f"   Comparaison vanilla désactivée")

    # Charger catalogue
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    # Lister tous les middles
    all_middle_files = [f.name for f in middles_dir.iterdir() if f.is_file()]

    # Lister tous les .emat
    emat_files = sorted([f for f in emat_dir.iterdir() if f.suffix == ".emat"])

    print(f"✅ {len(emat_files)} fichiers .emat trouvés")
    print(f"✅ {len(all_middle_files)} fichiers middle trouvés")
    print(f"✅ {len(catalog)} entrées catalogue")
    print()

    print("🔄 Analyse en cours...")
    print()

    # Cache pour chemins vanilla (éviter recherches répétées)
    vanilla_cache = {}

    # Analyser chaque .emat
    results = []
    vanilla_emats = []
    non_vanilla_emats = []

    for emat_path in emat_files:
        # 1. Extraire paramètres
        params = extract_emat_params(emat_path)

        # 2. Vérifier vanilla
        is_vanilla, vanilla_status = is_vanilla_emat(emat_path, vanilla_dir, vanilla_cache)

        # Si vanilla, analyser
        if vanilla_status in ["IDENTICAL", "MODIFIED"]:
            # 3. Chercher middle
            middle_found, middle_path, similar = find_middle_file(
                params["BCRMiddleMap"], middles_dir, all_middle_files
            )

            # Chercher .edds source vanilla
            edds_found, edds_path = check_vanilla_edds(params["BCRMiddleMap"], vanilla_dir)

            # 4. Comparer catalogue
            catalog_info = compare_catalog(emat_path.name, params, catalog)

            result = {
                "name": emat_path.name,
                "params": params,
                "vanilla_status": vanilla_status,
                "middle_found": middle_found,
                "middle_path": middle_path,
                "similar_middles": similar,
                "edds_found": edds_found,
                "edds_path": edds_path,
                "catalog": catalog_info
            }

            if is_vanilla:
                vanilla_emats.append(result)
            else:
                results.append(result)
        else:
            non_vanilla_emats.append({
                "name": emat_path.name,
                "vanilla_status": vanilla_status
            })

    # 5. Chercher orphelins
    used_middles = set()
    for r in results + vanilla_emats:
        if r.get("middle_path"):
            used_middles.add(r["middle_path"].name)

    orphan_middles = [f for f in all_middle_files if f not in used_middles]

    # 6. Middles partagés
    middle_usage = defaultdict(list)
    for r in results + vanilla_emats:
        if r["params"]["BCRMiddleMap"] != "ABSENT":
            middle_usage[r["params"]["BCRMiddleMap"]].append(r["name"])

    shared_middles = {k: v for k, v in middle_usage.items() if len(v) > 1}

    # Générer rapport markdown
    report_path = Path("AUDIT_EMAT_VANILLA.md")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# 📊 AUDIT .EMAT VANILLA\\n\\n")
        f.write(f"**Date :** {Path.cwd()}\\n")
        f.write(f"**Total .emat :** {len(emat_files)}\\n\\n")

        f.write("---\\n\\n")

        f.write("## 📊 RÉCAPITULATIF\\n\\n")
        f.write(f"```\\n")
        f.write(f"Total .emat analysés    : {len(emat_files)}\\n")
        f.write(f"  Vanilla IDENTICAL     : {len(vanilla_emats)}\\n")
        f.write(f"  Vanilla MODIFIED      : {len([r for r in results if r['vanilla_status'] == 'MODIFIED'])}\\n")
        f.write(f"  NON VANILLA           : {len(non_vanilla_emats)}\\n")
        f.write(f"\\n")

        problems = len([r for r in results + vanilla_emats if not r['middle_found'] or not r['catalog']['in_catalog']])
        f.write(f"Problèmes détectés      : {problems}\\n")
        f.write(f"  Middle manquant       : {len([r for r in results + vanilla_emats if not r['middle_found']])}\\n")
        f.write(f"  Absent du catalogue   : {len([r for r in results + vanilla_emats if not r['catalog']['in_catalog']])}\\n")
        f.write(f"\\n")
        f.write(f"Middles orphelins       : {len(orphan_middles)}\\n")
        f.write(f"Middles partagés        : {len(shared_middles)}\\n")
        f.write(f"```\\n\\n")

        # Problèmes
        f.write("---\\n\\n")
        f.write("## ❌ PROBLÈMES DÉTECTÉS\\n\\n")

        problem_results = [r for r in results + vanilla_emats
                          if not r['middle_found'] or not r['catalog']['in_catalog']
                          or r['vanilla_status'] == "MODIFIED"]

        if problem_results:
            for r in sorted(problem_results, key=lambda x: (not x['middle_found'], not x['catalog']['in_catalog'], x['name'])):
                f.write(f"### {r['name']}\\n\\n")
                f.write(f"**Statut vanilla :** {r['vanilla_status']}\\n\\n")

                if not r['middle_found']:
                    f.write(f"❌ **Middle manquant** : `{r['params']['BCRMiddleMap']}`\\n\\n")
                    if r['similar_middles']:
                        f.write(f"Fichiers similaires :\\n")
                        for sim in r['similar_middles']:
                            f.write(f"  - {sim}\\n")
                        f.write("\\n")

                    if r['edds_found']:
                        f.write(f"✅ Source .edds trouvé : `{r['edds_path']}`\\n\\n")
                    else:
                        f.write(f"❌ Source .edds introuvable\\n\\n")

                if not r['catalog']['in_catalog']:
                    f.write(f"⚠️  **Absent du catalogue**\\n\\n")

                if r['catalog']['in_catalog']:
                    if r['catalog']['middle_bcr_match'] is False:
                        f.write(f"⚠️  **Écart middle_bcr** :\\n")
                        f.write(f"  - .emat : `{r['params']['BCRMiddleMap']}`\\n")
                        f.write(f"  - catalog : `{r['catalog']['middle_bcr_catalog']}`\\n\\n")

                    if r['catalog']['tiling_scale_match'] is False:
                        f.write(f"⚠️  **Écart tiling_scale** :\\n")
                        f.write(f"  - .emat MiddleScaleUV : `{r['params']['MiddleScaleUV']}`\\n")
                        f.write(f"  - catalog tiling_scale : `{r['catalog']['tiling_scale_catalog']}`\\n\\n")

                f.write(f"**Paramètres .emat :**\\n")
                f.write(f"```\\n")
                for k, v in r['params'].items():
                    if not k.startswith("_"):
                        f.write(f"{k:20s} : {v}\\n")
                f.write(f"```\\n\\n")
        else:
            f.write("✅ Aucun problème détecté\\n\\n")

        # .emat OK
        f.write("---\\n\\n")
        f.write("## ✅ .EMAT VANILLA OK\\n\\n")

        ok_results = [r for r in vanilla_emats
                     if r['middle_found'] and r['catalog']['in_catalog']
                     and r['vanilla_status'] == "IDENTICAL"]

        f.write(f"**{len(ok_results)} fichiers OK**\\n\\n")

        for r in sorted(ok_results, key=lambda x: x['name'])[:20]:
            f.write(f"- {r['name']} → `{r['params']['BCRMiddleMap']}`\\n")

        if len(ok_results) > 20:
            f.write(f"\\n... et {len(ok_results) - 20} autres\\n")

        f.write("\\n")

        # NON VANILLA
        f.write("---\\n\\n")
        f.write("## 🔧 .EMAT NON VANILLA\\n\\n")
        f.write(f"**{len(non_vanilla_emats)} fichiers non vanilla (non analysés)**\\n\\n")

        for nv in sorted(non_vanilla_emats, key=lambda x: x['name'])[:20]:
            f.write(f"- {nv['name']} ({nv['vanilla_status']})\\n")

        if len(non_vanilla_emats) > 20:
            f.write(f"\\n... et {len(non_vanilla_emats) - 20} autres\\n")

        f.write("\\n")

        # Orphelins
        f.write("---\\n\\n")
        f.write("## 🗑️ MIDDLES ORPHELINS\\n\\n")
        f.write(f"**{len(orphan_middles)} fichiers non utilisés**\\n\\n")

        for orphan in sorted(orphan_middles)[:30]:
            f.write(f"- {orphan}\\n")

        if len(orphan_middles) > 30:
            f.write(f"\\n... et {len(orphan_middles) - 30} autres\\n")

        f.write("\\n")

        # Middles partagés
        f.write("---\\n\\n")
        f.write("## 🔗 MIDDLES PARTAGÉS\\n\\n")
        f.write(f"**{len(shared_middles)} middles utilisés par plusieurs .emat**\\n\\n")

        for middle, emats in sorted(shared_middles.items(), key=lambda x: -len(x[1]))[:20]:
            f.write(f"### `{middle}` ({len(emats)} .emat)\\n\\n")
            for emat in sorted(emats):
                f.write(f"- {emat}\\n")
            f.write("\\n")

        if len(shared_middles) > 20:
            f.write(f"... et {len(shared_middles) - 20} autres\\n\\n")

    print(f"✅ Rapport généré : {report_path.absolute()}")
    print()
    print("=" * 80)
    print("FIN DE L'AUDIT")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
