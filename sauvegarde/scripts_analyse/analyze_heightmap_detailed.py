import numpy as np
import matplotlib.pyplot as plt

# Charger heightmap
hmap = np.loadtxt(r"data\projects\Zimnitrita\sources\temp_Terrain_modified3.asc", skiprows=6)
print(f"Dimensions: {hmap.shape}")
print(f"Min: {hmap.min():.2f} m")
print(f"Max: {hmap.max():.2f} m")
print("")

# Distribution complète
print("=== DISTRIBUTION COMPLÈTE PAR TRANCHE ===")
tranches = [
    (-205, -150, "Mer très profonde"),
    (-150, -100, "Mer profonde"),
    (-100, -82, "Mer moyenne"),
    (-82, -66, "Transition mer (P7-P10)"),
    (-66, -50, "Zone intermédiaire"),
    (-50, -25, "Rivières profondes ?"),
    (-25, -10, "Rivières peu profondes ?"),
    (-10, 0, "Transition rivière/terre ?"),
    (0, 10, "Plages/côtes basses"),
    (10, 50, "Côtes/prairies basses"),
    (50, 200, "Plaines"),
    (200, 500, "Collines"),
    (500, 1000, "Montagnes basses"),
    (1000, 1843, "Montagnes hautes"),
]

for min_alt, max_alt, label in tranches:
    count = ((hmap >= min_alt) & (hmap < max_alt)).sum()
    pct = count / hmap.size * 100
    if count > 0:
        print(f"{min_alt:5d} à {max_alt:5d}m ({label:30s}) : {pct:6.2f}%  ({count:,} px)")

print("")
print("=== DÉTECTION PLATEAUX (sauts brusques) ===")
# Détecter les sauts brusques dans la distribution
h_sorted = np.sort(hmap.flatten())
percentiles = [0.5, 1, 2, 5, 7, 7.3, 8, 10, 12, 15, 18, 20, 25, 30]
prev_val = None
for p in percentiles:
    idx = int(len(h_sorted) * p / 100)
    val = h_sorted[idx]
    if prev_val is not None:
        saut = val - prev_val
        marker = " ← SAUT !" if saut > 10 else ""
        print(f"P{p:5.1f}% : {val:7.2f}m  (saut: {saut:6.2f}m){marker}")
    else:
        print(f"P{p:5.1f}% : {val:7.2f}m")
    prev_val = val

print("")
print("=== RECOMMANDATION DÉTECTION NIVEAU MER ===")

# Trouver le premier saut > 10m
h_sorted = np.sort(hmap.flatten())
sea_detected = None
for p in range(1, 20):
    p_curr = h_sorted[int(len(h_sorted) * p / 100)]
    p_next = h_sorted[int(len(h_sorted) * (p + 1) / 100)]
    saut = p_next - p_curr

    if p_curr < -20 and saut > 10:
        sea_detected = p_curr
        print(f"SAUT DÉTECTÉ à P{p}% : {p_curr:.1f}m -> {p_next:.1f}m (saut {saut:.1f}m)")
        print(f"-> Niveau mer proposé : {sea_detected:.0f}m")
        break

if sea_detected is None:
    print("Pas de saut brusque détecté -> Niveau mer = 0m (standard)")

print("")
print("=== ZONES PROPOSÉES ===")
if sea_detected:
    print(f"Mer (SeaBed) : {hmap.min():.0f}m à {sea_detected-2:.0f}m")
    print(f"Coastal : {sea_detected-2:.0f}m à {sea_detected+50:.0f}m")
    print(f"Lowland : {sea_detected+50:.0f}m à ...")
else:
    print(f"Mer (SeaBed) : < -2m")
    print(f"Coastal : -2m à 50m")
    print(f"Lowland : 50m à ...")

# Histogramme pour visualisation
print("")
print("Génération histogramme distribution_altitude.png...")
plt.figure(figsize=(14, 6))

# Histogramme altitude négative (mer/rivières)
plt.subplot(1, 2, 1)
negative = hmap[hmap < 0]
if len(negative) > 0:
    plt.hist(negative, bins=100, color='blue', alpha=0.7, edgecolor='black')
    plt.axvline(sea_detected if sea_detected else -82, color='red', linestyle='--', linewidth=2, label=f'Niveau mer détecté: {sea_detected if sea_detected else -82:.0f}m')
    plt.xlabel('Altitude (m)')
    plt.ylabel('Pixels')
    plt.title('Distribution altitudes NÉGATIVES (mer/rivières)')
    plt.legend()
    plt.grid(alpha=0.3)

# Histogramme altitude positive (terre)
plt.subplot(1, 2, 2)
positive = hmap[hmap >= 0]
plt.hist(positive, bins=100, color='green', alpha=0.7, edgecolor='black')
plt.xlabel('Altitude (m)')
plt.ylabel('Pixels')
plt.title('Distribution altitudes POSITIVES (terre)')
plt.grid(alpha=0.3)

plt.tight_layout()
plt.savefig('distribution_altitude.png', dpi=150, bbox_inches='tight')
print("✓ Histogramme sauvegardé : distribution_altitude.png")
