"""
terrain_terr_reader.py — Lecture du fichier terrain.terr d'Enfusion
Extrait la liste ordonnée des matériaux depuis le chunk MATS.
C'est la SOURCE DE VÉRITÉ pour l'ordre des matériaux (id = position 0-based).

Format MATS :
  u16 LE  : nombre de groupes UI (ignoré pour l'ordre)
  répéter :
    u32 LE  : longueur de la chaîne
    string  : "{GUID}Terrains/.../Surface.emat\0"
"""
import struct
import re
from pathlib import Path


def read_mats_from_terr(terr_path: str | Path) -> list[dict]:
    """
    Lit la liste des matériaux depuis terrain.terr.

    Returns:
        list de dicts : [
            {
                "id":   int,    # index 0-based = id Enfusion
                "name": str,    # nom court (ex: "Grass_03")
                "guid": str,    # GUID Enfusion (ex: "CBF745CAEA83CF98")
                "path": str,    # chemin relatif (ex: "Terrains/Common/Surfaces/Grass_03.emat")
                "emat": str,    # nom du fichier .emat (ex: "Grass_03.emat")
            }
        ]
    """
    data = open(terr_path, "rb").read()

    # Localiser le chunk MATS
    i = data.find(b"MATS")
    if i < 0:
        raise ValueError(f"Chunk MATS introuvable dans {terr_path}")

    chunk_size = struct.unpack_from(">I", data, i + 4)[0]
    chunk = data[i + 8: i + 8 + chunk_size]

    # Parser
    off = 2  # skip u16 "nombre de groupes"
    entries = []

    while off < len(chunk) - 4:
        str_len = struct.unpack_from("<I", chunk, off)[0]
        if str_len == 0 or str_len > 300:
            off += 1
            continue
        off += 4
        if off + str_len > len(chunk):
            break

        raw = chunk[off: off + str_len].decode("ascii", errors="replace").rstrip("\x00")
        off += str_len

        m = re.match(r"\{([0-9A-Fa-f]+)\}(.+\.emat)", raw)
        if m:
            guid, path = m.groups()
            name = path.split("/")[-1].replace(".emat", "")
            entries.append({
                "id":   len(entries),
                "name": name,
                "guid": guid.upper(),
                "path": path,
                "emat": path.split("/")[-1],
            })

    return entries


def build_id_to_name(terr_path: str | Path) -> dict[int, str]:
    """Retourne {id: nom} pour tous les matériaux."""
    return {e["id"]: e["name"] for e in read_mats_from_terr(terr_path)}


def build_name_to_id(terr_path: str | Path) -> dict[str, int]:
    """Retourne {nom: id} pour tous les matériaux."""
    return {e["name"]: e["id"] for e in read_mats_from_terr(terr_path)}


def build_guid_to_id(terr_path: str | Path) -> dict[str, int]:
    """Retourne {guid: id} — utile pour les lookups par référence Enfusion."""
    return {e["guid"]: e["id"] for e in read_mats_from_terr(terr_path)}


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "Terrain.terr"
    entries = read_mats_from_terr(path)
    print(f"{'id':4} {'nom':45} {'guid':18} chemin")
    print("-" * 120)
    for e in entries:
        print(f"[{e['id']:2d}] {e['name']:45} {{{e['guid']}}} {e['path']}")
    print(f"\nTotal: {len(entries)} matériaux")
