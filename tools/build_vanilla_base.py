"""
build_vanilla_base.py — Reconstruit data/Textures_ArmaReforger/vanilla_base/ depuis Textures/.

vanilla_base/ est la base copiée dans le dossier utilisateur au premier lancement de l'exe
(main._init_first_launch). Elle contient la partie vanilla de Textures/ : les textures custom
dont le nom commence par zi_ (casse ignorée) sont exclues.

Contenu produit :
    vanilla_base/catalog.json         entrées du catalog hors zi_
    vanilla_base/biomes_presets.json  copie telle quelle
    vanilla_base/emat/                .emat hors zi_
    vanilla_base/texture_Middle/      middles référencés par le catalog filtré

Usage (depuis la racine du dépôt) :
    .venv\\Scripts\\python.exe tools/build_vanilla_base.py            simulation, aucune écriture
    .venv\\Scripts\\python.exe tools/build_vanilla_base.py --ecrire   l'ancien vanilla_base/ part dans
                                                                     _archives/code/<date>_vanilla_base/
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXTURES_DIR = ROOT / "data" / "Textures_ArmaReforger" / "Textures"
VANILLA_DIR = ROOT / "data" / "Textures_ArmaReforger" / "vanilla_base"
ARCHIVE_DIR = ROOT / "_archives" / "code" / f"{datetime.now():%Y-%m-%d}_vanilla_base"

CUSTOM_PREFIX = "zi_"  # comparé en minuscules


def is_custom(name: str) -> bool:
    return name.lower().startswith(CUSTOM_PREFIX)


def plan() -> dict:
    """Calcule le contenu du nouveau vanilla_base sans rien écrire."""
    catalog = json.loads((TEXTURES_DIR / "catalog.json").read_text(encoding="utf-8"))
    catalog_vanilla = {k: v for k, v in catalog.items() if not is_custom(k)}

    emats = sorted(p for p in (TEXTURES_DIR / "emat").glob("*.emat") if not is_custom(p.name))

    middles_dir = TEXTURES_DIR / "texture_Middle"
    needed = sorted({v["middle_bcr"] for v in catalog_vanilla.values() if v.get("middle_bcr")})
    middles = [middles_dir / m for m in needed if (middles_dir / m).exists()]
    missing = [m for m in needed if not (middles_dir / m).exists()]

    return {
        "catalog_total": len(catalog),
        "catalog_vanilla": catalog_vanilla,
        "excluded_entries": sorted(k for k in catalog if is_custom(k)),
        "emats": emats,
        "excluded_emats": sorted(p.name for p in (TEXTURES_DIR / "emat").glob("*.emat") if is_custom(p.name)),
        "middles": middles,
        "missing_middles": missing,
        "unused_middles": sorted(p.name for p in middles_dir.iterdir() if p.name not in needed),
        "biomes": TEXTURES_DIR / "biomes_presets.json",
    }


def report(p: dict) -> None:
    size = sum(m.stat().st_size for m in p["middles"]) / 1e6
    print(f"Source      : {TEXTURES_DIR}")
    print(f"Destination : {VANILLA_DIR}")
    print(f"catalog.json        : {len(p['catalog_vanilla'])} entrées sur {p['catalog_total']}")
    print(f"   exclues ({len(p['excluded_entries'])}) : {', '.join(p['excluded_entries'])}")
    print(f"emat/               : {len(p['emats'])} fichiers")
    print(f"   exclus ({len(p['excluded_emats'])}) : {', '.join(p['excluded_emats'])}")
    print(f"texture_Middle/     : {len(p['middles'])} fichiers ({size:.1f} Mo)")
    print(f"   référencés mais absents de Textures/ : {', '.join(p['missing_middles']) or 'aucun'}")
    print(f"   non copiés (zi_ ou non référencés)   : {', '.join(p['unused_middles'])}")
    print(f"biomes_presets.json : {'copié' if p['biomes'].exists() else 'ABSENT de Textures/'}")


def write(p: dict) -> None:
    if VANILLA_DIR.exists():
        ARCHIVE_DIR.parent.mkdir(parents=True, exist_ok=True)
        if ARCHIVE_DIR.exists():
            sys.exit(f"[ERREUR] archive déjà présente, rien n'est écrit : {ARCHIVE_DIR}")
        shutil.move(str(VANILLA_DIR), str(ARCHIVE_DIR))
        print(f"[ARCHIVE] ancien vanilla_base -> {ARCHIVE_DIR}")

    (VANILLA_DIR / "emat").mkdir(parents=True)
    (VANILLA_DIR / "texture_Middle").mkdir()
    for f in p["emats"]:
        shutil.copy2(f, VANILLA_DIR / "emat" / f.name)
    for f in p["middles"]:
        shutil.copy2(f, VANILLA_DIR / "texture_Middle" / f.name)
    shutil.copy2(p["biomes"], VANILLA_DIR / "biomes_presets.json")
    (VANILLA_DIR / "catalog.json").write_text(
        json.dumps(p["catalog_vanilla"], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] écrit : {VANILLA_DIR}")


def main() -> None:
    ecrire = "--ecrire" in sys.argv
    print("MODE :", "ECRITURE" if ecrire else "SIMULATION (aucune écriture)")
    p = plan()
    report(p)
    if ecrire:
        write(p)


if __name__ == "__main__":
    main()
