"""
Analyser les formats QTRE sur Zimnitrita pour trouver les formats 6-7 textures
"""

import sys
import io
from pathlib import Path
import struct
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Utiliser le parseur existant
from reforger_texture_budget import _iter_tmat_bmats

terrain_dir = Path(r"I:\reforger_travail\Zimnitrita_map\World\Zimnitrita\Terrain")
data_dir = terrain_dir / ".Data"

ttile_files = sorted(data_dir.glob("*.ttile"))

print(f"Analyse de {len(ttile_files)} fichiers .ttile...\n")

qtre_sizes = Counter()
mat_counts = Counter()
qtre_examples = {}
max_per_file = {}

for ttile_path in ttile_files:
    with open(ttile_path, 'rb') as f:
        data = f.read()

    file_max = 0
    for bx, by, mat_ids, qtre in _iter_tmat_bmats(data):
        n_mat = len(mat_ids)
        mat_counts[n_mat] += 1
        file_max = max(file_max, n_mat)

        if qtre and len(qtre) > 0:
            qsize = len(qtre)
            qtre_sizes[qsize] += 1

            # Garder un exemple pour chaque combinaison (taille, n_mat)
            key = (qsize, n_mat)
            if key not in qtre_examples:
                qtre_examples[key] = {
                    'file': ttile_path.name,
                    'block': (bx, by)
                }

    max_per_file[ttile_path.name] = file_max

print("="*80)
print("RÉSULTATS")
print("="*80 + "\n")

print("Nombre de textures par bloc:")
for n in sorted(mat_counts.keys()):
    count = mat_counts[n]
    pct = count / sum(mat_counts.values()) * 100
    print(f"  {n} textures : {count:6d} blocs ({pct:5.1f}%)")

print(f"\nTotal : {sum(mat_counts.values())} blocs analysés")

max_textures = max(mat_counts.keys()) if mat_counts else 0
print(f"Max textures/bloc : {max_textures}")

print("\n" + "="*80)
print("Tailles QTRE par nombre de textures:")
print("="*80)

# Grouper par nombre de textures
by_mat_count = {}
for (qsize, n_mat), ex in qtre_examples.items():
    if n_mat not in by_mat_count:
        by_mat_count[n_mat] = []
    by_mat_count[n_mat].append((qsize, ex))

for n_mat in sorted(by_mat_count.keys()):
    print(f"\n{n_mat} textures:")
    for qsize, ex in sorted(by_mat_count[n_mat]):
        count = qtre_sizes[qsize]
        print(f"  Taille {qsize:5d} bytes ({count:6d} occurrences) - {ex['file']} bloc {ex['block']}")

print("\n" + "="*80)
print("FICHIERS AVEC LE PLUS DE TEXTURES:")
print("="*80)

top_files = sorted(max_per_file.items(), key=lambda x: -x[1])[:10]
for fname, max_tex in top_files:
    print(f"  {fname} : {max_tex} textures max")
