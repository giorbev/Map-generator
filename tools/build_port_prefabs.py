# -*- coding: utf-8 -*-
"""
build_port_prefabs.py — Régénère app/port_prefabs.py et app/mur_prefabs.py : emprise au sol des prefabs du jeu de base

  port_prefabs.py  Prefabs/Structures/Infrastructure/Naval : quais, murs de quai, escaliers, cales, bollards,
                   pontons, digues (genre d'après layer_port.genre_port)
  mur_prefabs.py   Prefabs/Structures/Walls : pièces de murs, palissades et clôtures (famille d'après
                   layer_port.famille_mur ; rambardes, bordures, glissières, poteaux seuls, portails exclus)

Pour chaque prefab (.et), suit l'héritage jusqu'au modèle (.xob) et lit sa boîte englobante (bloc HEAD du .xob :
6 flottants à l'octet 24, min x y z puis max x y z, y = hauteur).

Usage : python tools/build_port_prefabs.py "<jeu décompacté>/addons/data"
"""

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from layer_port import famille_mur, genre_port  # noqa: E402


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

    def table(dossier, classe):
        t = {}
        for d in paks:
            for et in (d / dossier).rglob("*.et"):
                g = classe(et.stem)
                if g is None or et.stem in t:
                    continue
                x = xob_de(et)
                if x is None:
                    continue
                b = x.read_bytes()
                if b[8:16] != b"XOB9HEAD":
                    continue
                mn_x, _, mn_z, mx_x, _, mx_z = struct.unpack_from("<6f", b, 24)
                t[et.stem] = (g, round(mn_x, 2), round(mn_z, 2), round(mx_x, 2), round(mx_z, 2))
        return t

    for nom, var, dossier, classe, quoi in (
            ("port_prefabs.py", "PORT_PREFABS", "Prefabs/Structures/Infrastructure/Naval", genre_port, "de port"),
            ("mur_prefabs.py", "MUR_PREFABS", "Prefabs/Structures/Walls", famille_mur, "de murs et clôtures")):
        t = table(dossier, classe)
        lignes = [f"    {k!r}: {v!r}," for k, v in sorted(t.items())]
        src = ('# -*- coding: utf-8 -*-\n'
               f'"""Emprise au sol des prefabs {quoi} du jeu de base — généré par tools/build_port_prefabs.py, '
               'ne pas modifier.\n\n'
               'nom du prefab → (genre, x min, z min, x max, z max), mètres, repère du modèle (z vers l\'avant).\n"""\n\n'
               f'{var} = {{\n' + "\n".join(lignes) + "\n}\n")
        (ROOT / "app" / nom).write_text(src, encoding="utf-8", newline="\n")
        print(f"{len(t)} prefabs {quoi} écrits dans app/{nom}")


if __name__ == "__main__":
    main()
