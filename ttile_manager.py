"""
ttile_manager.py — Gestionnaire complet des fichiers .ttile Reforger/Enfusion
==============================================================================

Modes disponibles :
  inspect       Affiche l'état d'un bloc (matériaux, distribution, budget)
  visualize     Exporte la grille 45×45 d'un bloc en PNG
  scan          Scanne tous les blocs d'une zone ou de la map
  stats         Liste tous les matériaux utilisés sur la map avec comptage
  validate      Vérifie la cohérence LRS2 ↔ GCTD
  replace       Remplace un matériau par un autre (1 bloc / liste / all)
  merge         Fusionne un matériau vers un autre (redirige les cellules)
  optimize      Fusionne les matériaux sous-représentés pour libérer des slots
  apply-mask    Applique un masque PNG sur un/plusieurs blocs
  apply-pipeline Applique un dossier de masques sur la Zone A
  backup-zone-b Sauvegarde l'état Zone B → JSON
  restore-zone-b Restaure l'état Zone B depuis JSON
  clean-zone-a  Écrit une texture neutre sur tous les blocs Zone A
  restore       Restaure un/tous les blocs depuis backup .bak
  export-csv    Exporte l'état de tous les blocs en CSV
  compare       Compare deux états de la map

Usage général :
  python ttile_manager.py --mode <mode> --addon-path <path> [options]

Options communes :
  --addon-path  Chemin racine addon Reforger (contient World/Zimnitrita/Terrain/)
  --terr-file   Chemin terrain.terr (auto-détecté si absent)
  --bx --by     Coordonnées globales d'un bloc
  --blocks      Liste de blocs "bx,by;bx,by;..."
  --all         Opérer sur tous les blocs de la map
  --mask        Masque d'exclusion PNG (Zone B = noir, Zone A = blanc)
  --dry-run     Simule sans écrire
  --no-confirm  Ne pas demander confirmation
  --out         Fichier/dossier de sortie

Exemples :
  python ttile_manager.py --mode inspect --addon-path "I:/..." --bx 34 --by 79
  python ttile_manager.py --mode replace --addon-path "I:/..." --bx 34 --by 79 --old-mat 8 --new-mat 26
  python ttile_manager.py --mode replace --addon-path "I:/..." --all --old-mat 0 --new-mat 3
  python ttile_manager.py --mode backup-zone-b --addon-path "I:/..." --mask exclusion.png --out zone_b.json
  python ttile_manager.py --mode apply-mask --addon-path "I:/..." --bx 34 --by 79 --mask rock.png --mat 8
  python ttile_manager.py --mode optimize --addon-path "I:/..." --bx 34 --by 79 --threshold 5
"""

import argparse
import ast
import csv
import json
import shutil
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─── Table des matériaux ──────────────────────────────────────────────────────

SURFACES = {
    0: 'Grass_03_default',
    1: 'SeaBed_01',
    2: 'Dirt_01',
    3: 'Grass_03',
    4: 'ForestDeciduous_02',
    5: 'Crop_Field_01',
    6: 'Crop_Field_02',
    7: 'Debris_Rock_01',
    8: 'Rock_01',
    9: 'Dirt_02',
    10: 'Pebbles_01',
    11: 'Pebbles_02',
    12: 'Asphalt_01',
    13: 'Concrete_01',
    14: 'Grass_01',
    15: 'ZI_Crop_Field_03',
    16: 'BeachGrass_01',
    17: 'Cobblestone_01_Wave',
    18: 'Concrete_02',
    19: 'ForestConiferous_02',
    20: 'Grass_02',
    21: 'Heather_01',
    22: 'MountainGrass_01',
    23: 'ForestClearing_Coniferous_01',
    24: 'ForestPine_01_Base',
    25: 'ForestClearing_Deciduous_01',
    26: 'ForestConiferous_01_Base',
    27: 'ForestDeciduous_01_Base',
    28: 'Grass_03_coastal',
    29: 'ZI_Crop_Field_01',
    30: 'ZI_Crop_Field_02',
    31: 'ZI_Crop_Field_04',
    32: 'ZI_Crop_Field_Cut_01',
    33: 'ZI_Crop_Field_Cut_02',
    34: 'ZI_Ground_Sport_01',
    35: 'SulfurStream_01_bed',
    36: 'MountainGrass_03_aut',
    37: 'MountainGrass_02_aut',
    38: 'MountainGrass_01_aut',
    39: 'Heather_01_aut',
    40: 'Grass_03_aut',
    41: 'Grass_02_aut',
    42: 'Grass_01_aut_leaves',
    43: 'Grass_01_aut',
    44: 'ForestPine_01_Base_aut',
    45: 'ForestDeciduous_02_aut',
    46: 'ForestDeciduous_01_Base_aut',
    47: 'ForestConiferous_02_aut',
    48: 'ForestConiferous_01_Base_aut',
    49: 'ForestClearing_Deciduous_01_aut',
    50: 'ForestClearing_Coniferous_01_aut',
    51: 'Debris_Coal_03',
    52: 'Debris_Coal_02',
    53: 'Debris_Coal_01',
    54: 'Rock_02',
    55: 'MountainGrass_02',
    56: 'MountainGrass_03',
    57: 'Dirt_03',
    58: 'zi_MountainGrass_02',
    59: 'zi_MountainGrass_04',
    60: 'zi_Heather_01',
}
SURFACES_INV = {v: k for k, v in SURFACES.items()}

GRID_W  = 32           # tuiles par axe
NUM_BLK = 4            # blocs par tuile par axe
GCTD_GRID = 45         # cellules par axe dans le payload GCTD
GCTD_SIZE = 2026       # bytes par section (45×45 + 1 padding)
MAX_SLOTS = 7          # slots max par bloc (w0..w6)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS — Chemins et tuiles
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_addon(addon_path: str) -> Dict:
    """Retourne les chemins data_dir, editor_dir, terr_file."""
    root = Path(addon_path)
    # Chercher le dossier Terrain/
    candidates = list(root.rglob('Terrain.terr'))
    if not candidates:
        # Essai chemin direct
        terr = root / 'World' / 'Zimnitrita' / 'Terrain' / 'Terrain.terr'
        if not terr.exists():
            raise FileNotFoundError(f"Terrain.terr introuvable sous {root}")
        candidates = [terr]
    terr_file  = candidates[0]
    terr_dir   = terr_file.parent
    data_dir   = terr_dir / '.Data'
    editor_dir = terr_dir / '.EditorData'
    return {'data_dir': data_dir, 'editor_dir': editor_dir, 'terr_file': terr_file}


def bx_by_to_tile(bx: int, by: int) -> Tuple[int, int, int]:
    """Retourne (tile_id, tx, ty) depuis les coordonnées globales de bloc."""
    tx = bx // NUM_BLK
    ty = by // NUM_BLK
    return ty * GRID_W + tx, tx, ty


def tile_to_ttile_path(data_dir: Path, tile_id: int) -> Path:
    return data_dir / f'Terrain_{tile_id}.ttile'


def get_all_tile_ids(data_dir: Path) -> List[int]:
    """Retourne tous les tile_ids présents sur disque."""
    ids = []
    for f in data_dir.glob('Terrain_*.ttile'):
        try:
            ids.append(int(f.stem.split('_')[1]))
        except (ValueError, IndexError):
            pass
    return sorted(ids)


def mat_name(mat_id: int, surfaces: Optional[Dict] = None) -> str:
    tbl = surfaces or SURFACES
    return tbl.get(mat_id, f'MAT_{mat_id}')


def mat_id_from_name(name: str, surfaces: Optional[Dict] = None) -> Optional[int]:
    tbl = surfaces or SURFACES
    inv = {v: k for k, v in tbl.items()}
    return inv.get(name)


def load_surfaces_from_terr(terr_file: Path) -> Dict[int, str]:
    """Lit la table des matériaux depuis terrain.terr."""
    try:
        data = terr_file.read_bytes()
        mats_pos = data.find(b'MATS')
        if mats_pos < 0:
            return SURFACES
        mats_size = struct.unpack_from('>I', data, mats_pos + 4)[0]
        mats_data = data[mats_pos + 8: mats_pos + 8 + mats_size]
        count = struct.unpack_from('<I', mats_data, 0)[0]
        surfaces = {}
        pos = 4
        for i in range(count):
            str_len = struct.unpack_from('<H', mats_data, pos)[0]
            pos += 2
            name = mats_data[pos:pos + str_len].decode('utf-8', errors='replace')
            name = Path(name).stem  # enlever .emat et le chemin
            surfaces[i] = name
            pos += str_len
            pos += 16  # GUID
        return surfaces if surfaces else SURFACES
    except Exception:
        return SURFACES


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS — IFF / .ttile
# ═══════════════════════════════════════════════════════════════════════════════

def find_chunk(data: bytes, tag: bytes) -> Tuple[int, int, bytes]:
    pos = data.find(tag)
    if pos < 0:
        return -1, 0, b''
    size = struct.unpack_from('>I', data, pos + 4)[0]
    return pos, size, data[pos + 8: pos + 8 + size]


def replace_chunk(data: bytearray, tag: bytes, new_payload: bytes) -> bytearray:
    pos = data.find(tag)
    if pos < 0:
        raise ValueError(f"Chunk {tag} introuvable")
    old_size = struct.unpack_from('>I', data, pos + 4)[0]
    delta    = len(new_payload) - old_size
    struct.pack_into('>I', data, pos + 4, len(new_payload))
    data[pos + 8: pos + 8 + old_size] = new_payload
    form_size = struct.unpack_from('>I', data, 4)[0]
    struct.pack_into('>I', data, 4, form_size + delta)
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS — LRS2
# ═══════════════════════════════════════════════════════════════════════════════

def parse_lrs2(raw: bytes) -> Dict[Tuple[int, int], List[int]]:
    entries, pos = {}, 0
    while pos < len(raw) - 6:
        idx  = struct.unpack_from('<I', raw, pos)[0]
        cnt  = struct.unpack_from('<H', raw, pos + 4)[0]
        mats = list(struct.unpack_from(f'<{cnt}H', raw, pos + 6))
        bx, by = idx & 0x7F, (idx >> 7) & 0x7F
        entries[(bx, by)] = mats
        pos += 6 + cnt * 2
    return entries


def build_lrs2(entries: Dict) -> bytes:
    parts = []
    for (bx, by), mats in sorted(entries.items()):
        parts.append(struct.pack('<IH', bx | (by << 7), len(mats)))
        parts.append(struct.pack(f'<{len(mats)}H', *mats))
    return b''.join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS — GCTD
# ═══════════════════════════════════════════════════════════════════════════════

def find_gctd_sections(gctd: bytes, lrs2_entries: Dict) -> List[Dict]:
    """
    Retourne liste de sections : {bx, by, hdr_off, data_off, data_size}.
    """
    sections = []
    pos = 2  # skip 2-byte global header
    while pos < len(gctd) - 4:
        fx = struct.unpack_from('<H', gctd, pos)[0]
        fy = struct.unpack_from('<H', gctd, pos + 2)[0]
        if (fx, fy) in lrs2_entries and fx < 128 and fy < 128:
            # Trouver la prochaine section pour calculer la taille
            next_off = len(gctd)
            probe = pos + 4
            while probe < len(gctd) - 4:
                nx = struct.unpack_from('<H', gctd, probe)[0]
                ny = struct.unpack_from('<H', gctd, probe + 2)[0]
                if (nx, ny) in lrs2_entries and nx < 128 and ny < 128 and (nx, ny) != (fx, fy):
                    next_off = probe
                    break
                probe += 1
            data_off  = pos + 4
            data_size = next_off - data_off
            sections.append({'bx': fx, 'by': fy, 'hdr_off': pos,
                              'data_off': data_off, 'data_size': data_size})
            pos += 2030
        else:
            pos += 1
    return sections


def get_section(gctd: bytes, bx: int, by: int, lrs2_entries: Dict) -> Optional[Dict]:
    for sec in find_gctd_sections(gctd, lrs2_entries):
        if sec['bx'] == bx and sec['by'] == by:
            return sec
    return None


def get_payload(gctd: bytes, sec: Dict) -> bytearray:
    return bytearray(gctd[sec['data_off']: sec['data_off'] + sec['data_size']])


def set_payload(gctd: bytearray, sec: Dict, payload: bytearray):
    gctd[sec['data_off']: sec['data_off'] + sec['data_size']] = payload


def payload_grid(payload: bytes) -> List[List[int]]:
    """Retourne la grille 45×45 depuis le payload."""
    grid = []
    for row in range(GCTD_GRID):
        line = []
        for col in range(GCTD_GRID):
            idx = row * GCTD_GRID + col
            line.append(payload[idx] if idx < len(payload) else 0)
        grid.append(line)
    return grid


def grid_to_payload(grid: List[List[int]], orig_size: int) -> bytearray:
    """Convertit la grille 45×45 en payload bytes."""
    out = bytearray(orig_size)
    for row in range(GCTD_GRID):
        for col in range(GCTD_GRID):
            idx = row * GCTD_GRID + col
            if idx < orig_size:
                out[idx] = grid[row][col]
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS — Masque PNG
# ═══════════════════════════════════════════════════════════════════════════════

def load_mask(mask_path: Path):
    """Charge un masque PNG et retourne l'image PIL en mode 'L'."""
    try:
        from PIL import Image
        return Image.open(mask_path).convert('L')
    except ImportError:
        print("[ERREUR] Pillow manquant : pip install Pillow")
        sys.exit(1)


def mask_value_for_block(mask_img, bx: int, by: int,
                          mask_size: int = 4096,
                          threshold: int = 128) -> float:
    """
    Retourne la valeur moyenne du masque pour le bloc (bx,by).
    Valeur 0.0 = entièrement noir (Zone B), 1.0 = entièrement blanc (Zone A).
    """
    tile_px = mask_size // (GRID_W * NUM_BLK)  # pixels par bloc
    px_x0 = bx * tile_px
    px_y0 = (GRID_W * NUM_BLK - 1 - by) * tile_px  # flip Y
    region = mask_img.crop((px_x0, px_y0, px_x0 + tile_px, px_y0 + tile_px))
    import numpy as np
    arr = np.array(region, dtype=float)
    return float(arr.mean() / 255.0)


def mask_grid_for_block(mask_img, bx: int, by: int,
                         mask_size: int = 4096) -> List[List[float]]:
    """
    Retourne une grille 45×45 de valeurs [0.0,1.0] du masque pour le bloc.
    """
    from PIL import Image
    import numpy as np
    tile_px = mask_size // (GRID_W * NUM_BLK)
    px_x0 = bx * tile_px
    px_y0 = (GRID_W * NUM_BLK - 1 - by) * tile_px
    region = mask_img.crop((px_x0, px_y0, px_x0 + tile_px, px_y0 + tile_px))
    region = region.resize((GCTD_GRID, GCTD_GRID), Image.LANCZOS)
    arr = np.array(region, dtype=float) / 255.0
    return arr.tolist()


def is_zone_b(mask_img, bx: int, by: int, threshold: float = 0.5) -> bool:
    return mask_value_for_block(mask_img, bx, by) < threshold


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS — Lecture/écriture .ttile
# ═══════════════════════════════════════════════════════════════════════════════

class TtileFile:
    """Wrapper pour lire/écrire un .ttile."""

    def __init__(self, path: Path):
        self.path = path
        self._raw = bytearray(path.read_bytes())
        _, _, lrs2_raw  = find_chunk(bytes(self._raw), b'LRS2')
        _, _, gctd_raw  = find_chunk(bytes(self._raw), b'GCTD')
        self.lrs2       = parse_lrs2(lrs2_raw)
        self.gctd       = bytearray(gctd_raw)
        self._sections  = None  # cache

    def sections(self) -> List[Dict]:
        if self._sections is None:
            self._sections = find_gctd_sections(bytes(self.gctd), self.lrs2)
        return self._sections

    def get_section(self, bx: int, by: int) -> Optional[Dict]:
        for sec in self.sections():
            if sec['bx'] == bx and sec['by'] == by:
                return sec
        return None

    def blocks(self) -> List[Tuple[int, int]]:
        return [(s['bx'], s['by']) for s in self.sections()]

    def get_payload(self, bx: int, by: int) -> Optional[bytearray]:
        sec = self.get_section(bx, by)
        if sec is None:
            return None
        return get_payload(bytes(self.gctd), sec)

    def set_payload(self, bx: int, by: int, payload: bytearray):
        sec = self.get_section(bx, by)
        if sec is None:
            raise ValueError(f"Bloc ({bx},{by}) introuvable")
        set_payload(self.gctd, sec, payload)
        self._sections = None  # invalider cache

    def get_mats(self, bx: int, by: int) -> Optional[List[int]]:
        return self.lrs2.get((bx, by))

    def set_mats(self, bx: int, by: int, mats: List[int]):
        self.lrs2[(bx, by)] = mats

    def save(self, backup: bool = True):
        bak = self.path.with_suffix('.ttile.bak')
        if backup and not bak.exists():
            shutil.copy2(self.path, bak)
        raw = bytearray(self._raw)
        raw = replace_chunk(raw, b'LRS2', build_lrs2(self.lrs2))
        raw = replace_chunk(raw, b'GCTD', bytes(self.gctd))
        self.path.write_bytes(bytes(raw))

    def validate(self, bx: int, by: int) -> List[str]:
        """Retourne liste d'erreurs de cohérence LRS2 ↔ GCTD."""
        errors = []
        mats = self.get_mats(bx, by)
        if mats is None:
            return [f"Bloc ({bx},{by}) absent du LRS2"]
        payload = self.get_payload(bx, by)
        if payload is None:
            return [f"Bloc ({bx},{by}) absent du GCTD"]
        max_idx = max(payload[:GCTD_GRID * GCTD_GRID])
        if max_idx >= len(mats):
            errors.append(f"Index GCTD max={max_idx} dépasse LRS2 count={len(mats)}")
        if len(mats) > MAX_SLOTS:
            errors.append(f"LRS2 count={len(mats)} dépasse MAX_SLOTS={MAX_SLOTS}")
        return errors


# ═══════════════════════════════════════════════════════════════════════════════
# MODES
# ═══════════════════════════════════════════════════════════════════════════════

def mode_inspect(ttile: TtileFile, bx: int, by: int, surfaces: Dict):
    tile_id, tx, ty = bx_by_to_tile(bx, by)
    mats    = ttile.get_mats(bx, by)
    payload = ttile.get_payload(bx, by)

    print(f"═══ Bloc ({bx},{by}) — Tuile {tile_id} (tx={tx}, ty={ty}) ═══")
    print(f"Fichier : {ttile.path.name}")
    print()

    if mats is None:
        print("[INFO] Bloc absent du LRS2 — texture par défaut (w0 implicite)")
        return

    print(f"LRS2 ({len(mats)} matériaux) :")
    for i, m in enumerate(mats):
        print(f"  [{i}] {m:2d} — {mat_name(m, surfaces)}")

    if payload is None:
        print("[INFO] Bloc absent du GCTD")
        return

    grid_data = payload[:GCTD_GRID * GCTD_GRID]
    cnt = Counter(grid_data)
    total = sum(cnt.values())

    print(f"\nGCTD distribution (grille 45×45 = {total} cellules) :")
    for local_idx, count in sorted(cnt.items(), key=lambda x: -x[1]):
        if local_idx < len(mats):
            name = mat_name(mats[local_idx], surfaces)
        else:
            name = f"IDX_{local_idx} (hors liste!)"
        pct = count / total * 100
        bar = '█' * int(pct / 2)
        print(f"  [{local_idx}] {name:35s} : {count:4d} cellules ({pct:5.1f}%) {bar}")

    budget_used = len(mats)
    budget_free = MAX_SLOTS - budget_used
    status = "OK" if budget_free >= 0 else "DÉPASSEMENT"
    print(f"\nBudget : {budget_used}/{MAX_SLOTS} slots utilisés, {budget_free} libres — {status}")

    errors = ttile.validate(bx, by)
    if errors:
        print(f"\n[WARN] Erreurs de validation :")
        for e in errors:
            print(f"  ! {e}")


def mode_visualize(ttile: TtileFile, bx: int, by: int,
                   surfaces: Dict, out_path: Path):
    try:
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np
    except ImportError:
        print("[ERREUR] Pillow/numpy manquant"); sys.exit(1)

    mats    = ttile.get_mats(bx, by)
    payload = ttile.get_payload(bx, by)

    if mats is None or payload is None:
        print(f"[ERREUR] Bloc ({bx},{by}) absent"); return

    # Couleurs par matériau (palette simple)
    palette = [
        (34, 139, 34), (0, 128, 0), (101, 67, 33), (85, 107, 47),
        (128, 128, 128), (47, 79, 79), (0, 100, 0), (139, 69, 19),
        (107, 142, 35), (160, 82, 45), (70, 130, 180), (95, 158, 160),
        (46, 139, 87), (143, 188, 143), (32, 178, 170),
    ]

    CELL = 14  # pixels par cellule
    IMG_W = GCTD_GRID * CELL
    IMG_H = GCTD_GRID * CELL + 60  # espace légende

    img  = Image.new('RGB', (IMG_W, IMG_H), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    for row in range(GCTD_GRID):
        for col in range(GCTD_GRID):
            idx = row * GCTD_GRID + col
            local_idx = payload[idx] if idx < len(payload) else 0
            color = palette[local_idx % len(palette)]
            x0, y0 = col * CELL, row * CELL
            draw.rectangle([x0, y0, x0 + CELL - 1, y0 + CELL - 1], fill=color)

    # Légende
    cnt = Counter(payload[:GCTD_GRID * GCTD_GRID])
    total = GCTD_GRID * GCTD_GRID
    y_leg = GCTD_GRID * CELL + 5
    x_leg = 4
    for local_idx, count in sorted(cnt.items(), key=lambda x: -x[1]):
        color = palette[local_idx % len(palette)]
        name  = mat_name(mats[local_idx], surfaces) if local_idx < len(mats) else f'IDX_{local_idx}'
        draw.rectangle([x_leg, y_leg, x_leg + 10, y_leg + 10], fill=color)
        draw.text((x_leg + 13, y_leg), f"{name} ({count/total*100:.0f}%)",
                  fill=(220, 220, 220))
        x_leg += 180
        if x_leg > IMG_W - 180:
            x_leg = 4
            y_leg += 14

    img.save(out_path)
    print(f"[OK] Image sauvegardée : {out_path} ({IMG_W}×{IMG_H})")


def mode_scan(ttile: TtileFile, surfaces: Dict,
              mask_img=None, zone: str = 'all'):
    """Scanne tous les blocs et affiche un résumé."""
    print(f"Scan {ttile.path.name} — {len(ttile.blocks())} blocs actifs")
    print()

    over_budget = []
    empty       = []
    ok          = []

    for bx, by in ttile.blocks():
        mats = ttile.get_mats(bx, by) or []
        n    = len(mats)
        if mask_img:
            z = 'B' if is_zone_b(mask_img, bx, by) else 'A'
            if zone == 'a' and z == 'B':
                continue
            if zone == 'b' and z == 'A':
                continue
        else:
            z = '?'

        payload = ttile.get_payload(bx, by)
        if payload:
            cnt = Counter(payload[:GCTD_GRID * GCTD_GRID])
            dom_idx = cnt.most_common(1)[0][0]
            dom_mat = mats[dom_idx] if dom_idx < len(mats) else -1
            dom_name = mat_name(dom_mat, surfaces)
        else:
            dom_name = '(aucun payload)'

        status = 'OK' if n <= MAX_SLOTS else f'DÉPASSE ({n})'
        line   = f"  ({bx:3d},{by:3d}) Zone{z} slots={n}/{MAX_SLOTS} dom={dom_name}"
        if n > MAX_SLOTS:
            over_budget.append(line)
        else:
            ok.append(line)

    if over_budget:
        print(f"[!] {len(over_budget)} blocs en dépassement :")
        for l in over_budget:
            print(l)
        print()
    print(f"[OK] {len(ok)} blocs dans le budget")
    if over_budget:
        print(f"[!] {len(over_budget)} blocs en dépassement")


def mode_stats(data_dir: Path, surfaces: Dict):
    """Statistiques globales sur tous les .ttile de la map."""
    tile_ids = get_all_tile_ids(data_dir)
    print(f"Scan de {len(tile_ids)} tuiles...")

    global_mat_count  = Counter()
    global_bloc_count = Counter()

    for tid in tile_ids:
        path = tile_to_ttile_path(data_dir, tid)
        try:
            ttile = TtileFile(path)
        except Exception as e:
            continue
        for (bx, by), mats in ttile.lrs2.items():
            payload = ttile.get_payload(bx, by)
            if payload is None:
                continue
            cnt = Counter(payload[:GCTD_GRID * GCTD_GRID])
            for local_idx, n_cells in cnt.items():
                if local_idx < len(mats):
                    global_mat_count[mats[local_idx]] += n_cells
                    global_bloc_count[mats[local_idx]] += 1

    print(f"\n{'Matériau':40s} {'Cellules':>10} {'Blocs':>8}")
    print('-' * 62)
    total_cells = sum(global_mat_count.values())
    for mat_id, cells in global_mat_count.most_common():
        name  = mat_name(mat_id, surfaces)
        blocs = global_bloc_count[mat_id]
        pct   = cells / total_cells * 100
        print(f"  {name:38s} {cells:10d} ({pct:5.1f}%) {blocs:8d}")


def mode_validate(ttile: TtileFile, bx: int, by: int, surfaces: Dict):
    errors = ttile.validate(bx, by)
    if errors:
        print(f"[FAIL] Bloc ({bx},{by}) — {len(errors)} erreur(s) :")
        for e in errors:
            print(f"  ! {e}")
    else:
        print(f"[OK] Bloc ({bx},{by}) — cohérence LRS2 ↔ GCTD validée")


def _do_replace_or_merge(ttile: TtileFile, bx: int, by: int,
                          old_mat: int, new_mat: int, surfaces: Dict) -> Dict:
    """
    Remplace old_mat par new_mat dans un bloc.
    Retourne {'changed': bool, 'cells_modified': int, 'msg': str}.
    """
    mats = ttile.get_mats(bx, by)
    if mats is None:
        return {'changed': False, 'cells_modified': 0,
                'msg': f"Bloc ({bx},{by}) absent du LRS2"}

    if old_mat not in mats:
        return {'changed': False, 'cells_modified': 0,
                'msg': f"Matériau {mat_name(old_mat, surfaces)} absent du bloc ({bx},{by})"}

    old_local = mats.index(old_mat)

    new_mats = mats[:]
    if new_mat in new_mats:
        new_mats.remove(old_mat)
        new_local = new_mats.index(new_mat)
    else:
        new_mats[old_local] = new_mat
        new_local = old_local

    # Modifier GCTD
    payload = ttile.get_payload(bx, by)
    if payload is None:
        return {'changed': False, 'cells_modified': 0,
                'msg': f"Bloc ({bx},{by}) absent du GCTD"}

    cells = 0
    for i in range(min(GCTD_GRID * GCTD_GRID, len(payload))):
        if payload[i] == old_local:
            payload[i] = new_local
            cells += 1

    ttile.set_mats(bx, by, new_mats)
    ttile.set_payload(bx, by, payload)
    return {'changed': True, 'cells_modified': cells,
            'msg': f"({bx},{by}) {mat_name(old_mat, surfaces)} → {mat_name(new_mat, surfaces)} : {cells} cellules"}


def mode_replace(ttile: TtileFile, blocks: List[Tuple[int, int]],
                 old_mat: int, new_mat: int, surfaces: Dict,
                 dry_run: bool, no_confirm: bool):
    print(f"Remplacement : {mat_name(old_mat, surfaces)} → {mat_name(new_mat, surfaces)}")
    print(f"Blocs concernés : {len(blocks)}")
    print()

    results = []
    for bx, by in blocks:
        r = _do_replace_or_merge(ttile, bx, by, old_mat, new_mat, surfaces)
        results.append(r)
        if r['changed']:
            print(f"  [MODIF] {r['msg']}")
        else:
            print(f"  [SKIP]  {r['msg']}")

    changed = [r for r in results if r['changed']]
    total_cells = sum(r['cells_modified'] for r in changed)
    print(f"\nRésumé : {len(changed)}/{len(blocks)} blocs modifiés, {total_cells} cellules")

    if dry_run:
        print("\n[DRY-RUN] Aucune écriture."); return

    if not changed:
        print("Rien à écrire."); return

    if not no_confirm:
        rep = input("\nAppliquer ? [oui/non] : ").strip().lower()
        if rep != 'oui':
            print("Annulé."); return

    ttile.save()
    print(f"[OK] {ttile.path.name} sauvegardé.")


def mode_optimize(ttile: TtileFile, bx: int, by: int,
                  threshold: int, surfaces: Dict,
                  dry_run: bool, no_confirm: bool):
    """Fusionne les matériaux sous-représentés vers le dominant."""
    mats    = ttile.get_mats(bx, by)
    payload = ttile.get_payload(bx, by)

    if mats is None or payload is None:
        print(f"[ERREUR] Bloc ({bx},{by}) absent"); return

    total = GCTD_GRID * GCTD_GRID
    cnt   = Counter(payload[:total])

    print(f"Bloc ({bx},{by}) avant optimisation :")
    for li, n in sorted(cnt.items(), key=lambda x: -x[1]):
        name = mat_name(mats[li], surfaces) if li < len(mats) else f'IDX_{li}'
        print(f"  [{li}] {name:35s} : {n:4d} cellules ({n/total*100:.1f}%)")

    # Trouver le matériau dominant (cible de la fusion)
    dominant_local = cnt.most_common(1)[0][0]
    dominant_mat   = mats[dominant_local] if dominant_local < len(mats) else -1

    # Matériaux sous le seuil
    to_merge = [(li, n) for li, n in cnt.items()
                if n / total * 100 < threshold and li != dominant_local]

    if not to_merge:
        print(f"\nAucun matériau sous le seuil {threshold}% → rien à faire"); return

    print(f"\nMatériaux à fusionner vers {mat_name(dominant_mat, surfaces)} :")
    for li, n in to_merge:
        name = mat_name(mats[li], surfaces) if li < len(mats) else f'IDX_{li}'
        print(f"  [{li}] {name} ({n} cellules, {n/total*100:.1f}%)")

    if dry_run:
        print("\n[DRY-RUN] Aucune écriture."); return

    if not no_confirm:
        rep = input("\nAppliquer ? [oui/non] : ").strip().lower()
        if rep != 'oui':
            print("Annulé."); return

    # Appliquer
    merge_indices = {li for li, _ in to_merge}
    for i in range(min(total, len(payload))):
        if payload[i] in merge_indices:
            payload[i] = dominant_local

    # Reconstruire LRS2 — supprimer les matériaux fusionnés
    kept_locals = sorted(set(payload[:total]))
    new_mats    = [mats[li] for li in kept_locals if li < len(mats)]
    # Remapper les index locaux
    remap = {old: new for new, old in enumerate(kept_locals)}
    for i in range(min(total, len(payload))):
        payload[i] = remap.get(payload[i], payload[i])

    ttile.set_mats(bx, by, new_mats)
    ttile.set_payload(bx, by, payload)
    ttile.save()
    print(f"[OK] Bloc ({bx},{by}) optimisé → {len(new_mats)} matériaux restants")


def mode_apply_mask(ttile: TtileFile, bx: int, by: int,
                    mask_path: Path, mat_id: int, surfaces: Dict,
                    threshold: float, dry_run: bool, no_confirm: bool):
    """Applique un masque PNG sur un bloc — les cellules > threshold reçoivent mat_id."""
    mask_img = load_mask(mask_path)
    grid_vals = mask_grid_for_block(mask_img, bx, by)

    mats    = ttile.get_mats(bx, by) or []
    payload = ttile.get_payload(bx, by)

    # Ajouter mat_id à la liste si absent
    if mat_id not in mats:
        if len(mats) >= MAX_SLOTS:
            print(f"[ERREUR] Budget plein ({MAX_SLOTS} slots) sur ({bx},{by}) — optimiser d'abord")
            return
        mats = mats + [mat_id]
    new_local = mats.index(mat_id)

    if payload is None:
        payload = bytearray(GCTD_SIZE)

    cells_modified = 0
    for row in range(GCTD_GRID):
        for col in range(GCTD_GRID):
            idx = row * GCTD_GRID + col
            if idx < len(payload) and grid_vals[row][col] > threshold:
                payload[idx] = new_local
                cells_modified += 1

    print(f"Bloc ({bx},{by}) : masque {mask_path.name} → {mat_name(mat_id, surfaces)}")
    print(f"  {cells_modified} cellules modifiées (seuil={threshold:.0%})")

    if dry_run:
        print("[DRY-RUN] Aucune écriture."); return

    if not no_confirm:
        rep = input("Appliquer ? [oui/non] : ").strip().lower()
        if rep != 'oui':
            print("Annulé."); return

    ttile.set_mats(bx, by, mats)
    ttile.set_payload(bx, by, payload)
    ttile.save()
    print(f"[OK] Sauvegardé.")


def mode_backup_zone_b(data_dir: Path, mask_path: Path,
                        out_path: Path, surfaces: Dict):
    """Sauvegarde l'état GCTD+LRS2 de tous les blocs Zone B dans un JSON."""
    mask_img = load_mask(mask_path)
    tile_ids = get_all_tile_ids(data_dir)
    backup   = {'version': 1, 'mask': str(mask_path), 'blocs': {}}

    print(f"Backup Zone B — {len(tile_ids)} tuiles...")
    total_blocs = 0
    for tid in tile_ids:
        path = tile_to_ttile_path(data_dir, tid)
        try:
            ttile = TtileFile(path)
        except Exception:
            continue
        for bx, by in ttile.blocks():
            if is_zone_b(mask_img, bx, by):
                mats    = ttile.get_mats(bx, by) or []
                payload = ttile.get_payload(bx, by)
                key     = f"{bx},{by}"
                backup['blocs'][key] = {
                    'tile_id': tid,
                    'mats':    mats,
                    'payload': list(payload) if payload else [],
                }
                total_blocs += 1

    out_path.write_text(json.dumps(backup, indent=2), encoding='utf-8')
    print(f"[OK] {total_blocs} blocs Zone B sauvegardés → {out_path}")


def mode_restore_zone_b(data_dir: Path, backup_path: Path,
                         dry_run: bool, no_confirm: bool):
    """Restaure l'état Zone B depuis un JSON de backup."""
    backup   = json.loads(backup_path.read_text(encoding='utf-8'))
    blocs    = backup.get('blocs', {})
    print(f"Restauration Zone B — {len(blocs)} blocs")

    if dry_run:
        print("[DRY-RUN] Aucune écriture."); return

    if not no_confirm:
        rep = input("Appliquer ? [oui/non] : ").strip().lower()
        if rep != 'oui':
            print("Annulé."); return

    # Grouper par tuile
    by_tile: Dict[int, List] = {}
    for key, info in blocs.items():
        tid = info['tile_id']
        by_tile.setdefault(tid, []).append((key, info))

    for tid, items in by_tile.items():
        path = tile_to_ttile_path(data_dir, tid)
        try:
            ttile = TtileFile(path)
        except Exception as e:
            print(f"  [SKIP] Tuile {tid} : {e}"); continue
        for key, info in items:
            bx, by = map(int, key.split(','))
            ttile.set_mats(bx, by, info['mats'])
            if info['payload']:
                ttile.set_payload(bx, by, bytearray(info['payload']))
        ttile.save()
        print(f"  [OK] Tuile {tid} restaurée")

    print(f"[OK] Zone B restaurée.")


def mode_export_csv(data_dir: Path, out_path: Path, surfaces: Dict):
    """Exporte l'état de tous les blocs en CSV."""
    tile_ids = get_all_tile_ids(data_dir)
    rows     = []
    print(f"Export CSV — {len(tile_ids)} tuiles...")

    for tid in tile_ids:
        tx = tid % GRID_W
        ty = tid // GRID_W
        path = tile_to_ttile_path(data_dir, tid)
        try:
            ttile = TtileFile(path)
        except Exception:
            continue
        for bx, by in ttile.blocks():
            mats    = ttile.get_mats(bx, by) or []
            payload = ttile.get_payload(bx, by)
            if payload:
                cnt      = Counter(payload[:GCTD_GRID * GCTD_GRID])
                dom_li   = cnt.most_common(1)[0][0]
                dom_mat  = mats[dom_li] if dom_li < len(mats) else -1
                dom_name = mat_name(dom_mat, surfaces)
                dom_pct  = cnt[dom_li] / (GCTD_GRID * GCTD_GRID) * 100
            else:
                dom_name, dom_pct = '', 0

            rows.append({
                'bx': bx, 'by': by, 'tx': tx, 'ty': ty, 'tile_id': tid,
                'n_mats': len(mats),
                'budget_free': MAX_SLOTS - len(mats),
                'dominant_mat': dom_name,
                'dominant_pct': round(dom_pct, 1),
                'mats': ','.join(mat_name(m, surfaces) for m in mats),
            })

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[OK] {len(rows)} blocs exportés → {out_path}")


def mode_restore_bak(data_dir: Path, bx: Optional[int], by: Optional[int],
                      all_tiles: bool):
    """Restaure depuis .bak."""
    if all_tiles:
        for bak in data_dir.glob('Terrain_*.ttile.bak'):
            orig = bak.with_suffix('')
            shutil.copy2(bak, orig)
            print(f"[OK] Restauré : {orig.name}")
    elif bx is not None and by is not None:
        tile_id, _, _ = bx_by_to_tile(bx, by)
        orig = tile_to_ttile_path(data_dir, tile_id)
        bak  = orig.with_suffix('.ttile.bak')
        if not bak.exists():
            print(f"[ERREUR] Pas de backup pour {orig.name}"); return
        shutil.copy2(bak, orig)
        print(f"[OK] Restauré : {orig.name}")
    else:
        print("[ERREUR] Préciser --bx/--by ou --all")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def parse_blocks_arg(s: str) -> List[Tuple[int, int]]:
    """Parse "bx,by;bx,by;..." → [(bx,by), ...]."""
    blocks = []
    for part in s.split(';'):
        part = part.strip()
        if ',' in part:
            bx, by = part.split(',', 1)
            blocks.append((int(bx.strip()), int(by.strip())))
    return blocks


def main():
    ap = argparse.ArgumentParser(
        description='ttile_manager.py — Gestionnaire terrain Reforger',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--mode',       required=True,
                    choices=['inspect','visualize','scan','stats','validate',
                             'replace','merge','optimize','apply-mask',
                             'apply-pipeline','backup-zone-b','restore-zone-b',
                             'clean-zone-a','restore','export-csv','compare'])
    ap.add_argument('--addon-path', type=str, default=None)
    ap.add_argument('--data-dir',   type=str, default=None,
                    help='Chemin direct vers .Data/ (alternative à --addon-path)')
    ap.add_argument('--terr-file',  type=str, default=None)
    ap.add_argument('--bx',         type=int, default=None)
    ap.add_argument('--by',         type=int, default=None)
    ap.add_argument('--blocks',     type=str, default=None,
                    help='"bx,by;bx,by;..."')
    ap.add_argument('--all',        action='store_true')
    ap.add_argument('--old-mat',    type=int, default=None)
    ap.add_argument('--new-mat',    type=int, default=None)
    ap.add_argument('--mat',        type=int, default=None,
                    help='Matériau cible pour apply-mask / clean-zone-a')
    ap.add_argument('--mask',       type=str, default=None,
                    help='Masque PNG exclusion Zone B')
    ap.add_argument('--masks-dir',  type=str, default=None,
                    help='Dossier de masques pipeline pour apply-pipeline')
    ap.add_argument('--threshold',  type=float, default=5.0,
                    help='Seuil % pour optimize (défaut 5) ou masque (défaut 0.3)')
    ap.add_argument('--out',        type=str, default=None)
    ap.add_argument('--backup',     type=str, default=None,
                    help='Fichier JSON backup Zone B')
    ap.add_argument('--dry-run',    action='store_true')
    ap.add_argument('--no-confirm', action='store_true')
    ap.add_argument('--zone',       choices=['a', 'b', 'all'], default='all',
                    help='Zone à scanner (a=blanc, b=noir, all=tout)')
    args = ap.parse_args()

    # ── Résoudre les chemins ──
    if args.data_dir:
        data_dir = Path(args.data_dir)
        terr_file = Path(args.terr_file) if args.terr_file else None
    elif args.addon_path:
        try:
            rp = resolve_addon(args.addon_path)
            data_dir  = rp['data_dir']
            terr_file = rp['terr_file'] if not args.terr_file else Path(args.terr_file)
        except FileNotFoundError as e:
            print(f"[ERREUR] {e}"); sys.exit(1)
    else:
        print("[ERREUR] --addon-path ou --data-dir requis"); sys.exit(1)

    # ── Charger les matériaux ──
    surfaces = load_surfaces_from_terr(terr_file) if terr_file and terr_file.exists() else SURFACES

    # ── Résoudre le(s) bloc(s) ──
    blocks: List[Tuple[int, int]] = []
    if args.blocks:
        blocks = parse_blocks_arg(args.blocks)
    elif args.bx is not None and args.by is not None:
        blocks = [(args.bx, args.by)]

    # ── Charger le .ttile si bloc unique ──
    def load_ttile_for_block(bx, by) -> TtileFile:
        tile_id, _, _ = bx_by_to_tile(bx, by)
        path = tile_to_ttile_path(data_dir, tile_id)
        if not path.exists():
            print(f"[ERREUR] {path} introuvable"); sys.exit(1)
        return TtileFile(path)

    # ── Dispatcher par mode ──
    mode = args.mode

    if mode == 'inspect':
        if not blocks:
            print("[ERREUR] --bx --by requis"); sys.exit(1)
        bx, by = blocks[0]
        mode_inspect(load_ttile_for_block(bx, by), bx, by, surfaces)

    elif mode == 'visualize':
        if not blocks:
            print("[ERREUR] --bx --by requis"); sys.exit(1)
        bx, by = blocks[0]
        out = Path(args.out) if args.out else Path(f"bloc_{bx}_{by}.png")
        mode_visualize(load_ttile_for_block(bx, by), bx, by, surfaces, out)

    elif mode == 'scan':
        if not blocks:
            print("[ERREUR] --bx --by requis (scan d'une tuile)"); sys.exit(1)
        bx, by = blocks[0]
        mask_img = load_mask(Path(args.mask)) if args.mask else None
        mode_scan(load_ttile_for_block(bx, by), surfaces, mask_img, args.zone)

    elif mode == 'stats':
        mode_stats(data_dir, surfaces)

    elif mode == 'validate':
        if not blocks:
            print("[ERREUR] --bx --by requis"); sys.exit(1)
        bx, by = blocks[0]
        mode_validate(load_ttile_for_block(bx, by), bx, by, surfaces)

    elif mode in ('replace', 'merge'):
        if args.old_mat is None or args.new_mat is None:
            print("[ERREUR] --old-mat et --new-mat requis"); sys.exit(1)
        if not blocks and not args.all:
            print("[ERREUR] --bx/--by ou --blocks ou --all requis"); sys.exit(1)

        if args.all:
            # Opérer sur toutes les tuiles
            tile_ids = get_all_tile_ids(data_dir)
            print(f"Mode ALL — {len(tile_ids)} tuiles")
            for tid in tile_ids:
                path = tile_to_ttile_path(data_dir, tid)
                try:
                    ttile = TtileFile(path)
                except Exception:
                    continue
                tile_blocks = ttile.blocks()
                if not tile_blocks:
                    continue
                mode_replace(ttile, tile_blocks, args.old_mat, args.new_mat,
                             surfaces, args.dry_run, args.no_confirm)
        else:
            # Grouper les blocs par tuile
            by_tile: Dict[int, List] = {}
            for bx, by in blocks:
                tid, _, _ = bx_by_to_tile(bx, by)
                by_tile.setdefault(tid, []).append((bx, by))
            for tid, tile_blocks in by_tile.items():
                path = tile_to_ttile_path(data_dir, tid)
                if not path.exists():
                    print(f"[SKIP] Tuile {tid} introuvable"); continue
                ttile = TtileFile(path)
                mode_replace(ttile, tile_blocks, args.old_mat, args.new_mat,
                             surfaces, args.dry_run, args.no_confirm)

    elif mode == 'optimize':
        if not blocks:
            print("[ERREUR] --bx --by requis"); sys.exit(1)
        bx, by = blocks[0]
        mode_optimize(load_ttile_for_block(bx, by), bx, by,
                      int(args.threshold), surfaces, args.dry_run, args.no_confirm)

    elif mode == 'apply-mask':
        if not blocks:
            print("[ERREUR] --bx --by requis"); sys.exit(1)
        if not args.mask or args.mat is None:
            print("[ERREUR] --mask et --mat requis"); sys.exit(1)
        bx, by = blocks[0]
        thr = args.threshold if args.threshold <= 1.0 else args.threshold / 100.0
        mode_apply_mask(load_ttile_for_block(bx, by), bx, by,
                        Path(args.mask), args.mat, surfaces,
                        thr, args.dry_run, args.no_confirm)

    elif mode == 'backup-zone-b':
        if not args.mask or not args.out:
            print("[ERREUR] --mask et --out requis"); sys.exit(1)
        mode_backup_zone_b(data_dir, Path(args.mask), Path(args.out), surfaces)

    elif mode == 'restore-zone-b':
        if not args.backup:
            print("[ERREUR] --backup requis"); sys.exit(1)
        mode_restore_zone_b(data_dir, Path(args.backup),
                             args.dry_run, args.no_confirm)

    elif mode == 'clean-zone-a':
        if not args.mask or args.mat is None:
            print("[ERREUR] --mask et --mat requis"); sys.exit(1)
        # Appliquer mat_id sur tous les blocs Zone A avec un masque blanc
        mask_img = load_mask(Path(args.mask))
        tile_ids = get_all_tile_ids(data_dir)
        print(f"Clean Zone A — {len(tile_ids)} tuiles, mat={mat_name(args.mat, surfaces)}")
        for tid in tile_ids:
            path = tile_to_ttile_path(data_dir, tid)
            try:
                ttile = TtileFile(path)
            except Exception:
                continue
            modified = False
            for bx, by in ttile.blocks():
                if not is_zone_b(mask_img, bx, by):
                    r = _do_replace_or_merge(ttile, bx, by,
                                              ttile.get_mats(bx, by)[0] if ttile.get_mats(bx, by) else -1,
                                              args.mat, surfaces)
                    if r['changed']:
                        modified = True
            if modified and not args.dry_run:
                ttile.save()
                print(f"  [OK] Tuile {tid}")

    elif mode == 'restore':
        mode_restore_bak(data_dir, args.bx, args.by, args.all)

    elif mode == 'export-csv':
        out = Path(args.out) if args.out else Path('ttile_export.csv')
        mode_export_csv(data_dir, out, surfaces)

    elif mode == 'compare':
        print("[TODO] Mode compare — à implémenter en v2")

    elif mode == 'apply-pipeline':
        print("[TODO] Mode apply-pipeline — à implémenter en v2")

    else:
        print(f"[ERREUR] Mode inconnu : {mode}")


if __name__ == '__main__':
    main()
