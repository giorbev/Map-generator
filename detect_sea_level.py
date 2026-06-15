import numpy as np

# Charger heightmap
hmap = np.loadtxt(r"data\projects\Zimnitrita\sources\temp_Terrain_modified3.asc", skiprows=6)
print(f"Min: {hmap.min():.2f} m")
print(f"Max: {hmap.max():.2f} m")
print("")

print("=== DISTRIBUTION ALTITUDES NÉGATIVES ===")
for seuil in [-200, -150, -100, -82, -70, -50, -25, -10, -5, 0]:
    count = (hmap <= seuil).sum()
    pct = count / hmap.size * 100
    print(f"  <= {seuil:4d}m : {pct:6.2f}%  ({count:,} pixels)")

print("")
print("=== HYPOTHÈSES NIVEAU MER ===")

# Hypothèse 1 : Minimum altitude
print(f"Hypothèse 1 (min altitude) : {hmap.min():.2f} m")

# Hypothèse 2 : Saut brusque dans distribution
alt_sorted = np.sort(hmap.flatten())
p1 = alt_sorted[int(len(alt_sorted) * 0.01)]
p2 = alt_sorted[int(len(alt_sorted) * 0.02)]
p5 = alt_sorted[int(len(alt_sorted) * 0.05)]
p7 = alt_sorted[int(len(alt_sorted) * 0.073)]  # 7.3% d'après analyse précédente
p10 = alt_sorted[int(len(alt_sorted) * 0.10)]

print(f"Percentile 1%  : {p1:.2f} m")
print(f"Percentile 2%  : {p2:.2f} m")
print(f"Percentile 5%  : {p5:.2f} m")
print(f"Percentile 7.3%: {p7:.2f} m")
print(f"Percentile 10% : {p10:.2f} m")

print("")
print("=== SAUT DE DISTRIBUTION (détection mer) ===")
# Détecter saut brusque
for i in [1, 2, 5, 7, 10]:
    val = alt_sorted[int(len(alt_sorted) * i / 100)]
    next_val = alt_sorted[int(len(alt_sorted) * (i + 1) / 100)]
    saut = next_val - val
    print(f"P{i}% -> P{i+1}% : {val:.1f}m -> {next_val:.1f}m (saut: {saut:.1f}m)")

print("")
print("=== RECOMMANDATION ===")
# Si saut > 50m entre P7 et P8, c'est probablement la frontière mer/terre
if p7 < -50 and p10 > 0:
    print(f"Niveau mer détecté : environ {p7:.0f}m (7.3% de la carte sous cette altitude)")
    print(f"Zone mer : {hmap.min():.0f}m à {p7:.0f}m")
    print(f"Zone terre : {p7:.0f}m à {hmap.max():.0f}m")
else:
    print("Niveau mer = 0m (pas de zone immergée significative)")
