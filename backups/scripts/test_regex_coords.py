"""
Script de test pour vérifier le parsing des coordonnées depuis le nom de fichier
"""
import re
from pathlib import Path

# Exemples de noms de fichiers
test_cases = [
    "N49_19_W1_12_-N49_25_W0_47_USGS_Sat.tif",
    "N49_19_W1_12-N49_25_W0_47.tif",
    "N49_19_E1_12_-N49_25_E0_47.png",
    "satmap_N49_19_W1_12_N49_25_W0_47.jpg",
    "N49_19_W001_12_-N49_25_W000_47.tif",  # avec des zéros en tête
]

def test_parse(filename):
    name = Path(filename).stem
    print(f"\n{'='*70}")
    print(f"Fichier : {filename}")
    print(f"Stem    : {name}")

    m = re.findall(r'[Nn](\d+)_(\d+)_[EeWw](\d+)_(\d+)', name)
    print(f"Groupes : {m}")

    if len(m) >= 2:
        lat1 = int(m[0][0]) + int(m[0][1])/60
        lon1 = int(m[0][2]) + int(m[0][3])/60
        lat2 = int(m[1][0]) + int(m[1][1])/60
        lon2 = int(m[1][2]) + int(m[1][3])/60

        if 'W' in name.upper():
            lon1, lon2 = -lon1, -lon2

        north = max(lat1, lat2)
        south = min(lat1, lat2)
        west  = min(lon1, lon2)
        east  = max(lon1, lon2)

        print(f"✅ RÉSULTAT :")
        print(f"   N={north:.4f}  S={south:.4f}")
        print(f"   W={west:.4f}   E={east:.4f}")
    else:
        print(f"❌ ÉCHEC : besoin de 2 groupes, trouvé {len(m)}")

if __name__ == "__main__":
    for test in test_cases:
        test_parse(test)

    print(f"\n{'='*70}")
    print("\nEntrez votre nom de fichier pour tester :")
    user_input = input("> ").strip()
    if user_input:
        test_parse(user_input)
