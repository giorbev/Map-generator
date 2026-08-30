from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
import unicodedata

import cv2
import numpy as np


# =========================
# Parametres de pipeline
# =========================
# Dossier source demande par l'utilisateur.
SOURCE_DIR = Path(r"H:\logiciel perso\Map generator\data\projects\Zbk_island\sources\instant\clean_threshold")

# Dossier racine de sortie. Le script cree 2 sous-dossiers:
# - 01_threshold (resultat etape 1)
# - 02_reforger_stack (resultat etape 2, exclusif + renomme)
OUTPUT_ROOT = SOURCE_DIR / "processed_pipeline"
THRESHOLD_DIR = OUTPUT_ROOT / "01_threshold"
REFORGER_DIR = OUTPUT_ROOT / "02_reforger_stack"


@dataclass(frozen=True)
class MaskRule:
    threshold: int
    invert_before: bool = False
    invert_after: bool = False
    enabled: bool = True


# Configuration par fichier (etape 1).
# Zone utile finale attendue en BLANC sur fond NOIR.
MASK_CONFIG: Dict[str, MaskRule] = {
    "01_seabed.png": MaskRule(threshold=40),
    "02_cotier10.png": MaskRule(threshold=55),
    "03_cotier20.png": MaskRule(threshold=60),
    "06_lowlandGrass2.png": MaskRule(threshold=58),
    "07_middlelandgrass3.png": MaskRule(threshold=62),
    "08_highland1.png": MaskRule(threshold=66),
    "09_highland2.png": MaskRule(threshold=70),
    "10_debrisRock.png": MaskRule(threshold=72),
    "11_rock.png": MaskRule(threshold=78),
    "12_curvature01_tresprofond.png": MaskRule(threshold=50),
    "13_curvature02_vallees douces.png": MaskRule(threshold=48),
    "14_curvature03_plat herbe normal.png": MaskRule(threshold=52),
    "15_curvature04_herbes rases.png": MaskRule(threshold=56),
    "17_sediments.png": MaskRule(threshold=62),
}

# Si un fichier n'a pas de regle explicite, il est ignore par securite.
DEFAULT_RULE = MaskRule(threshold=64, invert_before=False, invert_after=False, enabled=False)


@dataclass(frozen=True)
class PriorityRule:
    key: str
    label: str
    priority: int  # 1 = plus prioritaire
    tokens: List[str]


# Ordre absolu de priorite (plus prioritaire -> moins prioritaire)
PRIORITY_RULES: List[PriorityRule] = [
    PriorityRule("sea", "Mer", 1, ["sea", "seabed", "mer"]),
    PriorityRule("rock", "Rock", 2, ["rock"]),
    PriorityRule("debris", "DebrisRock", 3, ["debris"]),
    PriorityRule("sediments", "Sediments", 4, ["sediment", "sediments"]),
    PriorityRule("curvature", "Curvature", 5, ["curvature", "courbure"]),
    PriorityRule("highland2", "Highland2", 6, ["highland2", "highland 2"]),
    PriorityRule("highland1", "Highland1", 7, ["highland1", "highland 1"]),
    PriorityRule("middleland", "Middleland", 8, ["middleland"]),
    PriorityRule("lowland", "Lowland", 9, ["lowland"]),
    PriorityRule("coastal20", "Coastal20", 10, ["cotier20", "coast20", "coastal20", "0-20", "20"]),
    PriorityRule("coastal10", "Coastal10", 11, ["cotier10", "coast10", "coastal10", "0-10", "10"]),
]


def normalize_text(text: str) -> str:
    txt = unicodedata.normalize("NFKD", text)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return " ".join(txt.lower().replace("_", " ").replace("-", " ").split())


def read_image_unicode_safe(path: Path) -> np.ndarray | None:
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
        if raw.size == 0:
            return None
        return cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
    except Exception:
        return None


def write_image_unicode_safe(path: Path, image: np.ndarray) -> bool:
    ext = path.suffix.lower() if path.suffix else ".png"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        return False
    encoded.tofile(str(path))
    return True


def to_uint8_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    if image.dtype == np.uint8:
        return image
    if image.dtype == np.uint16:
        return (image / 257).astype(np.uint8)
    if np.issubdtype(image.dtype, np.floating):
        if image.max() <= 1.0:
            image = image * 255.0
        return np.clip(image, 0, 255).astype(np.uint8)

    return np.clip(image, 0, 255).astype(np.uint8)


def apply_threshold(mask_u8: np.ndarray, rule: MaskRule) -> np.ndarray:
    work = mask_u8
    if rule.invert_before:
        work = cv2.bitwise_not(work)

    _, binary = cv2.threshold(work, rule.threshold, 255, cv2.THRESH_BINARY)

    if rule.invert_after:
        binary = cv2.bitwise_not(binary)

    return binary


def find_rule_for_file(file_name: str, config: Dict[str, MaskRule], default_rule: MaskRule) -> MaskRule:
    # 1) match exact
    if file_name in config:
        return config[file_name]

    # 2) match normalise (accents/casse/espaces)
    normalized_name = normalize_text(file_name)
    normalized_map = {normalize_text(k): v for k, v in config.items()}
    return normalized_map.get(normalized_name, default_rule)


def classify_priority(file_name: str) -> PriorityRule | None:
    name = normalize_text(Path(file_name).stem)
    matched: List[tuple[int, PriorityRule]] = []
    for rule in PRIORITY_RULES:
        for token in rule.tokens:
            if token in name:
                matched.append((len(token), rule))
                break

    if not matched:
        return None

    # Si plusieurs categories matchent, on garde d'abord le token le plus specifique
    # (plus long), puis la priorite la plus forte en cas d'egalite.
    matched.sort(key=lambda item: (-item[0], item[1].priority))
    return matched[0][1]


def step1_threshold_clean(
    source_dir: Path,
    threshold_dir: Path,
    config: Dict[str, MaskRule],
    default_rule: MaskRule,
) -> List[Path]:
    png_files = sorted(source_dir.glob("*.png"))
    if not png_files:
        return []

    threshold_dir.mkdir(parents=True, exist_ok=True)
    cleaned_paths: List[Path] = []

    print("\n=== ETAPE 1: Threshold individuel ===")
    for src in png_files:
        rule = find_rule_for_file(src.name, config, default_rule)
        if not rule.enabled:
            print(f"[SKIP] {src.name} (pas de regle active)")
            continue

        img = read_image_unicode_safe(src)
        if img is None:
            print(f"[ERR] {src.name} (lecture impossible)")
            continue

        u8 = to_uint8_grayscale(img)
        binary = apply_threshold(u8, rule)

        dst = threshold_dir / src.name
        ok = write_image_unicode_safe(dst, binary)
        if not ok:
            print(f"[ERR] {src.name} (ecriture impossible)")
            continue

        cleaned_paths.append(dst)
        print(
            f"[OK] {src.name} -> threshold={rule.threshold}, "
            f"invert_before={rule.invert_before}, invert_after={rule.invert_after}"
        )

    return cleaned_paths


def load_binary_masks(paths: List[Path]) -> List[dict]:
    masks: List[dict] = []
    ref_shape = None

    for path in sorted(paths):
        img = read_image_unicode_safe(path)
        if img is None:
            print(f"[ERR] {path.name} (lecture impossible)")
            continue

        u8 = to_uint8_grayscale(img)
        # Force binaire propre pour la cascade.
        _, binary = cv2.threshold(u8, 127, 255, cv2.THRESH_BINARY)

        if ref_shape is None:
            ref_shape = binary.shape
        elif binary.shape != ref_shape:
            print(f"[ERR] {path.name} (dimensions {binary.shape} != {ref_shape})")
            continue

        priority_rule = classify_priority(path.name)
        if priority_rule is None:
            print(f"[SKIP] {path.name} (categorie de priorite introuvable)")
            continue

        masks.append(
            {
                "path": path,
                "name": path.name,
                "label": priority_rule.label,
                "priority": priority_rule.priority,
                "mask": binary,
            }
        )

    # Tri traitement: du plus prioritaire au moins prioritaire.
    masks.sort(key=lambda x: (x["priority"], normalize_text(Path(x["name"]).stem)))
    return masks


def apply_exclusive_cascade(sorted_masks: List[dict]) -> List[dict]:
    if not sorted_masks:
        return []

    already_taken = np.zeros_like(sorted_masks[0]["mask"], dtype=np.uint8)
    out = []

    print("\n=== ETAPE 2: Cascade exclusive ===")
    for item in sorted_masks:
        current = item["mask"].copy()

        # Logique demandee:
        # Masque_Actuel = Masque_Actuel - already_taken (clamp 0..255)
        # already_taken = already_taken + Masque_Actuel (clamp 0..255)
        current_exclusive = cv2.subtract(current, already_taken)
        already_taken = cv2.add(already_taken, current_exclusive)

        out_item = dict(item)
        out_item["exclusive_mask"] = current_exclusive
        out.append(out_item)

        kept_px = int(np.count_nonzero(current_exclusive))
        print(f"[OK] P{item['priority']:02d} {item['label']}: {item['name']} -> {kept_px} px")

    return out


def export_reforger_stack(exclusive_items: List[dict], output_dir: Path) -> List[Path]:
    if not exclusive_items:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)

    # Export inverse pour Reforger: du moins prioritaire vers le plus prioritaire.
    export_sorted = sorted(
        exclusive_items,
        key=lambda x: (-x["priority"], normalize_text(Path(x["name"]).stem)),
    )

    written: List[Path] = []
    label_count: Dict[str, int] = {}

    print("\n=== EXPORT Reforger (ordre inverse) ===")
    for idx, item in enumerate(export_sorted, start=1):
        label = item["label"]
        label_count[label] = label_count.get(label, 0) + 1
        suffix = f"_{label_count[label]:02d}" if label_count[label] > 1 else ""

        out_name = f"{idx:02d}_{label}{suffix}.png"
        out_path = output_dir / out_name

        if write_image_unicode_safe(out_path, item["exclusive_mask"]):
            written.append(out_path)
            print(f"[OK] {out_name} <- {item['name']}")
        else:
            print(f"[ERR] {out_name} (ecriture impossible)")

    return written


def process_all_masks(
    source_dir: Path,
    output_dir: Path,
    config: Dict[str, MaskRule],
    default_rule: MaskRule = DEFAULT_RULE,
) -> None:
    """Compatibilite avec l'ancien bouton UI: etape 1 uniquement."""
    cleaned = step1_threshold_clean(source_dir, output_dir, config, default_rule)
    print("\nSummary")
    print(f"- processed: {len(cleaned)}")


def run_full_pipeline(
    source_dir: Path,
    threshold_dir: Path,
    reforger_dir: Path,
    config: Dict[str, MaskRule],
    default_rule: MaskRule,
) -> None:
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    print(f"Source: {source_dir}")
    cleaned = step1_threshold_clean(source_dir, threshold_dir, config, default_rule)

    loaded = load_binary_masks(cleaned)
    exclusive = apply_exclusive_cascade(loaded)
    written = export_reforger_stack(exclusive, reforger_dir)

    print("\n=== RESUME ===")
    print(f"- threshold masks: {len(cleaned)}")
    print(f"- classified masks: {len(loaded)}")
    print(f"- exported masks:  {len(written)}")
    print(f"- output stack dir: {reforger_dir}")


if __name__ == "__main__":
    run_full_pipeline(
        source_dir=SOURCE_DIR,
        threshold_dir=THRESHOLD_DIR,
        reforger_dir=REFORGER_DIR,
        config=MASK_CONFIG,
        default_rule=DEFAULT_RULE,
    )
