# Map Generator Pro v3.0 🗺️

**Plateforme de génération de cartes topographiques** pour Arma Reforger, Unreal Engine 5 et Unity.

Convertit une **heightmap** en cartes de biomes, masques de textures, et analyses morphologiques — tout dans une interface web Streamlit interactive.

---

## 🎯 Features Actuelles (v3.0)

| Feature | État | Description |
|---------|------|-------------|
| 🎨 Hypsométrique PURE | ✅ | Colormap altitude-only (Vert→Jaune→Orange→Rouge→Marron) |
| 🌿 NatureMap Biomes | ✅ | 8 biomes (eau, neige, roche, toundra, forêt, prairie, sable) |
| 📊 Calques Textures | ✅ | Masques pente pour Reforger (herbe/terre/roche/escarpement) |
| 📈 Analyse Heightmap | ✅ | Stats détaillées (dimensions, altitudes, pentes, distribution) |
| 🛰️ SatMap | ✅ | Support images satellite pour enrichissement |
| 📤 Export | ✅ | PNG 8/16-bit, ASC ESRI, téléchargement direct |
| 🌱 Végétation | 🔄 | VPN export (Enfusion polylines) |

---

## 📋 Prérequis

- **Python 3.10+**
- **Packages :** `streamlit`, `numpy`, `scipy`, `pillow`, `opencv-python`, `matplotlib`, `pandas`

### Installation

```bash
# 1. Cloner le repo
git clone https://github.com/ton-username/map-generator.git
cd "Map generator"

# 2. Créer virtual env (recommandé)
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows PowerShell
source .venv/bin/activate   # Linux/macOS

# 3. Installer dépendances
pip install streamlit pillow numpy scipy matplotlib pandas opencv-python

# 4. Lancer l'app
streamlit run app.py
```

L'application s'ouvre automatiquement sur `http://localhost:8501`

---

## 🚀 Démarrage Rapide

### 1. Charger une Heightmap

1. **Sidebar gauche** → "📂 Chargement & Export"
2. **"📁 Heightmap"** → Cliquer "Browse files"
3. Sélectionner un fichier `.asc`, `.png`, `.tga`, ou `.jpg`
4. **BaseMap se crée automatiquement** (métadonnées, pentes, biomes)

### 2. Générer Cartes

- **Onglet "Hypsométrique PURE"** → "🚀 Générer" → Colormap altitude
- **Onglet "NatureMap Biomes"** → "🚀 Générer" → Carte 8 biomes
- **Onglet "Calques Textures"** → "🚀 Générer" → Masques pente

### 3. Télécharger Résultats

Chaque carte générée → Bouton **"📥 Télécharger PNG"** en bas de l'onglet

---

## 📁 Architecture Projet

```
Map generator/
├── app.py                              # 🎯 Interface Streamlit principale
│
├── ─── CORE MODULES ───
├── base_map.py                        # Chargeur heightmap + dérivées
├── naturemap_biomes_generator.py      # Génération 8 biomes
├── hypsometric_colormap.py            # Colormap hypsométrique
├── texture_layer_generator.py         # Masques texture pente
├── satellite_colormap_generator.py    # Colormap réaliste satellite
│
├── ─── GÉNÉRATEURS SPÉCIALISÉS ───
├── urban_analysis_generator.py        # Analyse urbaine
├── airfield_analysis_generator.py     # Analyse aéroports
├── slope_mask_generator.py            # Masques pente
│
├── ─── OUTILS ───
├── asc_png_converter.py               # Convertisseur ASC ↔ PNG
├── mask_correction_tool.py            # Correction masque
│
├── ─── DONNÉES ───
├── input/                             # Heightmaps sources
├── output/                            # Cartes générées
├── prompts/                           # Templates
│
├── ─── CONFIG ───
├── NOTICE.md                          # 📖 Documentation complète
├── TODO.md                            # 🗂️ Roadmap v3.1/3.2/3.3
├── README.md                          # 👈 Vous êtes ici
├── LICENSE
└── .gitignore
```

---

## 📖 Documentation Complète

- **[NOTICE.md](NOTICE.md)** — Architecture DDD, tous les modules détaillés
- **[TODO.md](TODO.md)** — Roadmap complète (v3.1 morphologie, v3.2 projets, v3.3 UI)

---

## 📊 Formats Supportés

### Entrée (Heightmap)
- `*.asc` — ASC ESRI Grid (recommandé, préserve altitudes réelles)
- `*.png` — PNG 8/16-bit
- `*.tga`, `*.jpg` — Images

### Sortie
- **Cartes :** PNG 8-bit colorées (hypsométrique, naturemap, satellite)
- **Masques :** PNG 8-bit N/B (pentes)
- **Export Reforger :** ASC header correct + PNG surface maps
- **Export ASC :** Format ESRI ASCII Grid avec metadata.json

---

## 🔮 Roadmap

### v3.1 — Morphologie Avancée (PRIORITÉ HAUTE)
4 analyses pour textures **10× plus naturelles** :
- 🧭 **Exposition** — Versants N/S/E/W
- 📊 **TPI** — Crêtes vs vallées vs pentes
- 💧 **Flow Accumulation** — Drainage + rivières
- 🕳️ **Dépressions** — Dolines/mares

### v3.2 — Système Projets (PRIORITÉ TRÈS HAUTE)
- 🏠 Page d'accueil avec liste projets
- 💾 Sauvegarde/Import/Export projets ZIP
- 🔗 Import données Reforger brutes (copier-coller)

### v3.3 — Remaniement Graphique (PRIORITÉ HAUTE)
- 🎨 Design UI complet (couleurs, layout responsive)
- 📊 Cartes d'information visuelles
- ⌨️ Shortcuts clavier + notifications

**→ Voir [TODO.md](TODO.md) pour détails complets**

---

## 🧪 Tester Localement

```bash
# Test Hypsométrique
python -c "
from hypsometric_colormap import HypsometricColormapGenerator
gen = HypsometricColormapGenerator('input/bornholm_ter.asc')
img, _ = gen.generate(smooth=True)
img.save('output/test_hypsometric.png')
print('✅ OK')
"

# Test NatureMap
python -c "
from naturemap_biomes_generator import NatureMapBiomesGenerator
gen = NatureMapBiomesGenerator('input/bornholm_ter.asc')
img = gen.generate()
img.save('output/test_naturemap.png')
print('✅ OK')
"
```

---

## 📞 Support

- **Issues/Bugs :** GitHub Issues
- **Questions :** GitHub Discussions
- **Contributions :** PRs bienvenues (voir TODO.md)

---

## 📄 License

Voir [LICENSE](LICENSE)

---

**Version :** 3.0  
**Date :** 9 mai 2026  
**Statut :** ✅ Production-ready | 🔄 v3.1 en planning
