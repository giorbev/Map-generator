# -*- coding: utf-8 -*-
"""
build_port_prefabs.py — Régénère app/port_prefabs.py : emprise au sol des prefabs de port du jeu de base

Lit les prefabs (.et) de Prefabs/Structures/Infrastructure/Naval (quais, murs, escaliers, cales, bollards,
pontons, digues) dans une copie décompactée du jeu, suit l'héritage jusqu'au modèle (.xob) et lit sa boîte
englobante (bloc HEAD du .xob : 6 flottants à l'octet 24, min x y z puis max x y z, y = hauteur).

Usage : python tools/build_port_prefabs.py "<jeu décompacté>/addons/data"
"""

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from layer_port import genre_port  # noqa: E402


def main():
    data = Path(sys.argv[1])
    paks = sorted(d for d in data.iterdir() if d.is_dir() and d.name.startswith("data"))

    def trouve(rel):
        for d in paks:
            if (d / rel).is_file():
                return d / rel
        return None

    def xob_de(p, prof=0):
        t = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'Object\s+"\{[0-9A-F]+\}([^"]+\.xob)"', t)
        if m:
            return trouve(m.group(1))
        m = re.match(r'\s*\w+\s*:\s*"\{[0-9A-F]+\}([^"]+\.et)"', t)
        q = trouve(m.group(1)) if m else None
        return xob_de(q, prof + 1) if q and prof < 6 else None

    table = {}
    for d in paks:
        for et in (d / "Prefabs/Structures/Infrastructure/Naval").rglob("*.et"):
            g = genre_port(et.stem)
            if g is None or et.stem in table:
                continue
            x = xob_de(et)
            if x is None:
                continue
            b = x.read_bytes()
            if b[8:16] != b"XOB9HEAD":
                continue
            mn_x, _, mn_z, mx_x, _, mx_z = struct.unpack_from("<6f", b, 24)
            table[et.stem] = (g, round(mn_x, 2), round(mn_z, 2), round(mx_x, 2), round(mx_z, 2))
    lignes = [f"    {k!r}: {v!r}," for k, v in sorted(table.items())]
    src = ('# -*- coding: utf-8 -*-\n'
           '"""Emprise au sol des prefabs de port du jeu de base — généré par tools/build_port_prefabs.py, ne pas modifier.\n\n'
           'nom du prefab → (genre, x min, z min, x max, z max), mètres, repère du modèle (z vers l\'avant).\n"""\n\n'
           'PORT_PREFABS = {\n' + "\n".join(lignes) + "\n}\n")
    (ROOT / "app" / "port_prefabs.py").write_text(src, encoding="utf-8", newline="\n")
    print(f"{len(table)} prefabs de port écrits dans app/port_prefabs.py")


if __name__ == "__main__":
    main()
