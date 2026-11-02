# -*- coding: utf-8 -*-
"""
textures_sync.py — Textures d'un projet face au .terr et à l'addon Reforger

Synchronisation (sync_textures) :
  pour chaque matériau du .terr dont le .emat est dans l'addon (custom, ou vanilla surchargé
  par l'addon), le .emat est copié dans <projet>/textures/emat/ (parents compris s'ils sont
  dans l'addon), son middle est cherché puis son entrée du catalog est recalculée.
  Ordre de recherche du middle (chemin BCRMiddleMap du .emat, héritage résolu) :
    1. déjà dans les middles du projet (ex. custom qui reprend un middle vanilla)
    2. image source à côté du .edds dans l'addon (.png, .tif, .tga, .jpg) → PNG
    3. .edds de l'addon décodé (edds_decoder.decode_edds_color) → PNG
    4. sinon manquant (ex. middle du jeu de base, hors de l'addon)
  Une entrée marquée "manual": true (choix de l'utilisateur) n'est jamais réécrite.

État (textures_status) : lecture seule, une ligne par matériau du .terr.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from catalog_config import CATALOG_NAME, EMAT_SUBDIR, MIDDLES_SUBDIR
from edds_decoder import decode_edds_color
from generate_catalog import build_catalog_entry, compute_avg_color, find_middle_file
from satmap_v2_textured_v2 import resolve_catalog_entry
from terrain_terr_reader import read_mats_from_terr

# Images sources cherchées à côté d'un .edds de l'addon, dans cet ordre
SOURCE_IMAGE_EXTS = (".png", ".tif", ".tiff", ".tga", ".jpg", ".jpeg")
# Images acceptées pour un choix manuel
MANUAL_IMAGE_EXTS = SOURCE_IMAGE_EXTS + (".edds", ".dds")

# Nom d'un middle choisi à la main quand le nom de l'image est déjà pris : <emat>_manual.png
MANUAL_SUFFIX = "_manual"

# Matériaux du moteur (ex. system/terrain/default.emat), sans .emat à copier
SYSTEM_PREFIX = "system/"

# Champs ignorés pour décider si une entrée du catalog a changé
_VOLATILE_FIELDS = ("resolved_date",)

_PARENT_RE = re.compile(r'TerrainMaterial\s*:\s*"(?:\{[0-9A-Fa-f]+\})?([^"]+\.emat)"')
_MIDDLE_RE = re.compile(r'BCRMiddleMap\s+"(?:\{[0-9A-Fa-f]+\})?([^"]+)"')


# ── Lecture des .emat ──────────────────────────────────────────────────────

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _parent_ref(emat_path: Path) -> Optional[str]:
    """Chemin de ressource du parent (ex. Terrains/Common/Surfaces/MountainGrass_01.emat), ou None."""
    m = _PARENT_RE.search(_read_text(emat_path))
    return m.group(1) if m else None


def _middle_ref(emat_name: str, emat_dir: Path) -> Optional[str]:
    """Chemin de ressource du BCRMiddleMap, en remontant l'héritage dans emat_dir ; None si absent."""
    seen = set()
    name = emat_name
    while name and name not in seen:
        seen.add(name)
        path = emat_dir / name
        if not path.exists():
            return None
        text = _read_text(path)
        m = _MIDDLE_RE.search(text)
        if m:
            return m.group(1)
        p = _PARENT_RE.search(text)
        name = Path(p.group(1)).name if p else None
    return None


def _split_emat(text: str):
    """
    Découpe un .emat en (en-tête, propriétés, fin) ; une propriété = (clé, lignes), un bloc
    imbriqué (« Clé { … } ») formant une seule propriété.
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.rstrip().endswith("{")), None)
    if start is None:
        return None
    items, i, depth = [], start + 1, 1
    end = len(lines)
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if depth == 1 and stripped == "}":
            end = i
            break
        key = stripped.split()[0] if stripped else ""
        block = [line]
        if stripped.endswith("{"):
            d = 1
            while d > 0 and i + 1 < len(lines):
                i += 1
                block.append(lines[i])
                d += lines[i].count("{") - lines[i].count("}")
        items.append((key, block))
        i += 1
    return lines[:start + 1], items, lines[end:]


def merge_emat_override(base_text: str, patch_text: str) -> str:
    """
    .emat de l'addon qui surcharge un .emat vanilla : Workbench n'y enregistre que les propriétés
    modifiées, le moteur complète avec l'original. Renvoie l'original avec les propriétés du
    patch appliquées (remplacées ou ajoutées), l'en-tête étant celui du patch.
    """
    base, patch = _split_emat(base_text), _split_emat(patch_text)
    if base is None or patch is None:
        return patch_text
    _, base_items, base_end = base
    patch_head, patch_items, _ = patch
    merged = list(base_items)
    index = {k: n for n, (k, _) in enumerate(merged) if k}
    for key, block in patch_items:
        if key in index:
            merged[index[key]] = (key, block)
        else:
            index[key] = len(merged)
            merged.append((key, block))
    out = patch_head + [l for _, block in merged for l in block] + base_end
    return "\n".join(out) + "\n"


def _effective_emat(addon_path: Path, vanilla_dir: Path) -> str:
    """Contenu effectif d'un .emat de l'addon : fusionné avec le vanilla du même nom s'il existe."""
    text = _read_text(addon_path)
    vanilla = vanilla_dir / EMAT_SUBDIR / addon_path.name
    return merge_emat_override(_read_text(vanilla), text) if vanilla.exists() else text


def _same_lines(a: str, b: str) -> bool:
    """Deux contenus .emat identiques (fins de ligne et espaces de bord ignorés)."""
    def norm(t):
        return [line.strip() for line in t.splitlines() if line.strip()]
    return norm(a) == norm(b)


# ── Middles ────────────────────────────────────────────────────────────────

def _save_png(src: Path, dest: Path) -> bool:
    """Convertit une image (PNG, TIF, TGA, JPG, .edds, .dds) en PNG ; False si illisible."""
    from PIL import Image
    try:
        if src.suffix.lower() in (".edds", ".dds"):
            img = decode_edds_color(src)
            if img is None:
                return False
        else:
            img = Image.open(src)
            img.load()
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        tmp = dest.with_name(dest.stem + ".tmp.png")
        img.save(tmp)
        tmp.replace(dest)
        return True
    except Exception as e:
        print(f"[TEXTURES] Conversion impossible {src.name} : {e}")
        return False


def _import_middle(addon_ref: Path, dest: Path) -> Optional[str]:
    """Copie le middle depuis l'addon (image source puis .edds) ; renvoie la source ou None."""
    for ext in SOURCE_IMAGE_EXTS:
        src = addon_ref.with_suffix(ext)
        if src.exists() and _save_png(src, dest):
            return "addon_image"
    if addon_ref.exists() and _save_png(addon_ref, dest):
        return "addon_edds"
    return None


# ── Catalog ────────────────────────────────────────────────────────────────

def _load_catalog(catalog_path: Path) -> dict:
    return json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else {}


def _write_catalog(catalog_path: Path, catalog: dict) -> None:
    tmp = catalog_path.with_name(catalog_path.stem + ".tmp.json")
    tmp.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(catalog_path)


def _differs(old: Optional[dict], new: dict) -> bool:
    if old is None:
        return True
    strip = lambda e: {k: v for k, v in e.items() if k not in _VOLATILE_FIELDS}
    return strip(old) != strip(new)


def _origin(emat_name: str, terr_path: str, addon_path: Path, vanilla_dir: Path) -> str:
    """custom (addon seul), override (addon + même nom en vanilla), vanilla, system (moteur), absent."""
    in_vanilla = (vanilla_dir / EMAT_SUBDIR / emat_name).exists()
    if addon_path.exists():
        return "override" if in_vanilla else "custom"
    if in_vanilla:
        return "vanilla"
    return "system" if terr_path.lower().startswith(SYSTEM_PREFIX) else "absent"


# ── Synchronisation ────────────────────────────────────────────────────────

def _copy_emat_chain(addon_dir: Path, ref: str, emat_dir: Path, vanilla_dir: Path, report: dict) -> bool:
    """
    Copie un .emat de l'addon (et ses parents présents dans l'addon), fusionné avec le vanilla du
    même nom s'il s'agit d'une surcharge ; True si un fichier a changé.
    """
    changed = False
    seen = set()
    while ref and ref not in seen:
        seen.add(ref)
        src = addon_dir / ref
        if not src.exists():
            # Parent hors de l'addon : il doit déjà être dans le projet (vanilla)
            if not (emat_dir / Path(ref).name).exists():
                report["parent_missing"].append(Path(ref).name)
            break
        dst = emat_dir / src.name
        text = _effective_emat(src, vanilla_dir)
        if not dst.exists() or not _same_lines(text, _read_text(dst)):
            report["emat_added" if not dst.exists() else "emat_updated"].append(src.name)
            dst.write_text(text, encoding="utf-8")
            changed = True
        ref = _parent_ref(src)
    return changed


def sync_textures(textures_dir: Path, addon_dir: Path, terr_path: Path, vanilla_dir: Path) -> dict:
    """
    Synchronise les textures du projet avec le .terr et l'addon (voir l'en-tête du module).
    vanilla_dir : textures vanilla de référence (vanilla_base), base des .emat surchargés.

    Returns:
        {"ok": True, "emat_added": [...], "emat_updated": [...], "middles_added": [{"middle", "source"}],
         "entries_written": [...], "manual_kept": [...], "middle_missing": [{"emat", "middle"}],
         "emat_missing": [...], "parent_missing": [...]}  ou {"ok": False, "error": str}
    """
    textures_dir, addon_dir = Path(textures_dir), Path(addon_dir)
    emat_dir = textures_dir / EMAT_SUBDIR
    middles_dir = textures_dir / MIDDLES_SUBDIR
    catalog_path = textures_dir / CATALOG_NAME
    if not emat_dir.exists() or not middles_dir.exists():
        return {"ok": False, "error": f"Dossier de textures du projet incomplet : {textures_dir}"}
    try:
        mats = read_mats_from_terr(terr_path)
    except Exception as e:
        return {"ok": False, "error": f"Lecture du .terr impossible : {e}"}

    catalog = _load_catalog(catalog_path)
    report = {"ok": True, "emat_added": [], "emat_updated": [], "middles_added": [], "entries_written": [],
              "manual_kept": [], "middle_missing": [], "emat_missing": [], "parent_missing": []}
    cache = {}

    for m in mats:
        emat = m["emat"]
        addon_path = addon_dir / m["path"]
        from_addon = addon_path.exists()
        if from_addon:
            _copy_emat_chain(addon_dir, m["path"], emat_dir, vanilla_dir, report)
        old = resolve_catalog_entry(m["name"], catalog)
        if not (emat_dir / emat).exists():
            if old is None:
                report["emat_missing"].append(emat)
            continue
        if old is not None and old.get("manual"):
            report["manual_kept"].append(emat)
            continue
        if not from_addon and old is not None:
            continue  # vanilla déjà au catalog : inchangé

        # Middle : projet, puis image source ou .edds de l'addon
        middle_source = None
        ref = _middle_ref(emat, emat_dir)
        if ref:
            stem = Path(ref).stem
            found = find_middle_file(stem, middles_dir)
            if found:
                if old and old.get("middle_bcr") == found.name and old.get("middle_source"):
                    middle_source = old["middle_source"]
                else:
                    middle_source = "vanilla" if (vanilla_dir / MIDDLES_SUBDIR / found.name).exists() else "projet"
            else:
                middle_source = _import_middle(addon_dir / ref, middles_dir / (stem + ".png"))
                if middle_source:
                    report["middles_added"].append({"middle": stem + ".png", "source": middle_source})
                else:
                    report["middle_missing"].append({"emat": emat, "middle": ref})

        entry, parent_missing, _ = build_catalog_entry(emat, emat_dir, middles_dir, cache)
        report["parent_missing"].extend(p.split(" → ")[-1] for p in parent_missing)
        entry["provenance"] = _origin(emat, m["path"], addon_path, vanilla_dir)
        if middle_source:
            entry["middle_source"] = middle_source
        key = next((k for k in (emat, m["name"]) if k in catalog), emat)
        if _differs(catalog.get(key), entry):
            catalog[key] = entry
            report["entries_written"].append(emat)

    report["parent_missing"] = sorted(set(report["parent_missing"]))
    if report["entries_written"]:
        _write_catalog(catalog_path, catalog)
    return report


# ── Choix manuel d'un middle ───────────────────────────────────────────────

def set_manual_middle(textures_dir: Path, emat_name: str, image_path: Optional[str]) -> dict:
    """
    Choix manuel du middle d'un matériau : l'image est copiée en PNG dans les middles du projet et
    l'entrée du catalog est marquée "manual": true (la synchronisation ne la réécrit plus).
    image_path vide : le choix manuel est retiré (la prochaine synchronisation recalcule l'entrée).
    """
    textures_dir = Path(textures_dir)
    emat_dir = textures_dir / EMAT_SUBDIR
    middles_dir = textures_dir / MIDDLES_SUBDIR
    catalog_path = textures_dir / CATALOG_NAME
    catalog = _load_catalog(catalog_path)

    if not image_path:
        entry = catalog.get(emat_name)
        if entry is None or not entry.get("manual"):
            return {"ok": True, "changed": False}
        entry.pop("manual", None)
        entry.pop("middle_source", None)
        if (emat_dir / emat_name).exists():
            entry, _, _ = build_catalog_entry(emat_name, emat_dir, middles_dir, {})
        catalog[emat_name] = entry
        _write_catalog(catalog_path, catalog)
        return {"ok": True, "changed": True}

    src = Path(image_path)
    if not src.exists():
        return {"ok": False, "error": f"Fichier introuvable : {src}"}
    if src.suffix.lower() not in MANUAL_IMAGE_EXTS:
        return {"ok": False, "error": f"Format non pris en charge : {src.suffix}"}
    dest = middles_dir / (src.stem + ".png")
    if dest.exists() and src.resolve() != dest.resolve():
        # Ne jamais écraser un middle existant (il peut servir à d'autres matériaux)
        dest = middles_dir / (Path(emat_name).stem + MANUAL_SUFFIX + ".png")
    if src.resolve() != dest.resolve() and not _save_png(src, dest):
        return {"ok": False, "error": f"Image illisible : {src.name}"}

    if (emat_dir / emat_name).exists():
        entry, _, _ = build_catalog_entry(emat_name, emat_dir, middles_dir, {})
    else:
        entry = dict(catalog.get(emat_name) or {})
    tint = entry.get("tint_srgb") or [255, 255, 255]
    entry.update({"middle_bcr": dest.name, "avg_color": compute_avg_color(dest, tint),
                  "manual": True, "middle_source": "manual", "resolved_date": str(date.today())})
    catalog[emat_name] = entry
    _write_catalog(catalog_path, catalog)
    return {"ok": True, "changed": True, "middle": dest.name}


# ── État ───────────────────────────────────────────────────────────────────

def textures_status(textures_dir: Path, addon_dir: Path, terr_path: Path, vanilla_dir: Path) -> dict:
    """
    État des textures du projet, une ligne par matériau du .terr (lecture seule, sans chemin absolu).

    middle_state : ok | missing (fichier absent) | none (pas de middle : couleur unie) | not_in_catalog
    """
    textures_dir, addon_dir, vanilla_dir = Path(textures_dir), Path(addon_dir), Path(vanilla_dir)
    emat_dir = textures_dir / EMAT_SUBDIR
    middles_dir = textures_dir / MIDDLES_SUBDIR
    try:
        mats = read_mats_from_terr(terr_path)
    except Exception as e:
        return {"ok": False, "error": f"Lecture du .terr impossible : {e}"}
    catalog = _load_catalog(textures_dir / CATALOG_NAME)

    rows = []
    for m in mats:
        emat = m["emat"]
        addon_path = addon_dir / m["path"]
        project_emat = emat_dir / emat
        entry = resolve_catalog_entry(m["name"], catalog)
        ref = _middle_ref(emat, emat_dir) if project_emat.exists() else None
        if entry is None:
            state, middle, source = "not_in_catalog", None, None
        elif not entry.get("middle_bcr"):
            state, middle, source = "none", None, None
        else:
            middle = entry["middle_bcr"]
            if (middles_dir / middle).exists():
                state = "ok"
                source = entry.get("middle_source") or (
                    "vanilla" if (vanilla_dir / MIDDLES_SUBDIR / middle).exists() else "projet")
            else:
                state, source = "missing", None
        rows.append({
            "id": m["id"],
            "name": m["name"],
            "emat": emat,
            "path": m["path"],
            "origin": _origin(emat, m["path"], addon_path, vanilla_dir),
            "emat_in_project": project_emat.exists(),
            "needs_sync": addon_path.exists() and (not project_emat.exists() or not _same_lines(
                _effective_emat(addon_path, vanilla_dir), _read_text(project_emat))),
            "middle": middle,
            "middle_ref": ref,
            "middle_in_addon": bool(ref) and any((addon_dir / ref).with_suffix(x).exists()
                                                 for x in SOURCE_IMAGE_EXTS + (Path(ref).suffix,)),
            "middle_state": state,
            "middle_source": source,
            "manual": bool(entry and entry.get("manual")),
            "tint": (entry or {}).get("tint_srgb"),
            "avg_color": (entry or {}).get("avg_color"),
        })

    counts = {
        "total": len(rows),
        "ok": sum(r["middle_state"] == "ok" for r in rows),
        "none": sum(r["middle_state"] == "none" for r in rows),
        "missing": sum(r["middle_state"] == "missing" for r in rows),
        "not_in_catalog": sum(r["middle_state"] == "not_in_catalog" for r in rows),
        "needs_sync": sum(r["needs_sync"] for r in rows),
        "from_addon": sum(r["origin"] in ("custom", "override") for r in rows),
        "manual": sum(r["manual"] for r in rows),
    }
    return {"ok": True, "materials": rows, "counts": counts}
