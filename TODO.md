# TODO.md — Roadmap Map Generator Pro v3.0+

**Date :** 9 mai 2026  
**Version actuelle :** 3.0 (Hypsométrique + NatureMap fonctionnels)  
**Prochaine :** 3.1 (Morphologie complète) → 4.0 (Système projets complet)

---

## 🎯 Priorités par version

### v3.1 — Analyses Morphologiques Avancées [HAUTE PRIORITÉ]

#### 1. 🧭 Exposition (Aspect) — ⭐⭐⭐
**Fichier :** `naturemap_biomes_generator.py`

**Description :** Calcul orientation des versants (N/S/E/W)
- Chaque versant a des caractéristiques différentes :
  - **Nord** (315-45°) = Plus humide → Herbe/Mousse dense
  - **Sud** (135-225°) = Xérophyte → Roche/Sol nu
  - **Est/Ouest** = Transition

**Implémentation :**
```python
def _compute_aspect(self):
    """Calcule exposition versants (0-360°)"""
    # Utiliser gradients Sobel existants
    # aspect_deg = degrees(arctan2(gy, gx))
    return self.aspect_deg
```

**Impact :** Moduler scores de texture par orientation

---

#### 2. 📊 TPI (Topographic Position Index) — ⭐⭐⭐
**Fichier :** `naturemap_biomes_generator.py`

**Description :** Mesure crêtes vs vallées vs pentes uniformes
- TPI = altitude_pixel - moyenne_locale_voisins
- **TPI > +10m** = Crêtes → Roche
- **-10m ≤ TPI ≤ +10m** = Pentes uniformes → Transitions
- **TPI < -10m** = Vallées → Herbe/Prairies

**Implémentation :**
```python
def _compute_tpi(self, window_size=25):
    """TPI : altitude - moyenne locale"""
    from scipy.ndimage import uniform_filter
    h = self.heightmap_original.astype(np.float32)
    return h - uniform_filter(h, size=window_size)
```

**Impact :** Herbe concentrée dans vallées, Roche sur crêtes

---

#### 3. 💧 Flow Accumulation D8 — ⭐⭐⭐
**Fichier :** `naturemap_biomes_generator.py`

**Description :** Simulation drainage (où l'eau s'accumule)
- Chaque pixel draine vers son voisin le plus bas
- Accumuler pixels en amont
- HIGH flow = Rivières/zones humides
- LOW flow = Crêtes sèches

**Implémentation :**
```python
def _compute_flow_accumulation(self):
    """D8 flow routing"""
    # Chaque pixel → voisin le plus bas
    # Compter accumulation en amont
    # Log-normaliser : log(1 + accumulation)
```

**Impact :** Rivières et zones humides automatiquement détectées

---

#### 4. 🕳️ Dépressions Fermées — ⭐⭐
**Fichier :** `naturemap_biomes_generator.py`

**Description :** Minima locaux (dolines, mares)
- Pixels où tous voisins sont plus hauts
- Cas spéciaux rares mais intéressants

**Implémentation :**
```python
def _compute_depressions(self):
    """Détecte cavités fermées"""
    from scipy.ndimage import minimum_filter
    # depressions = (h <= min_filter(h, size=3) + tolerance)
```

**Impact :** Zones karstiques particulières

---

#### 5. 🔗 Intégration TextureLayerGenerator — ⭐⭐⭐
**Fichier :** `texture_layer_generator.py`

**Description :** Utiliser analyses dans génération masques
- Créer `generate_smart_masks(aspect, tpi, flow)`
- Combiner : pentes (40%) + TPI (30%) + Aspect (20%) + Flow (10%)
- Remplacer logique pentes-seul par morpho-intelligente

**Résultat :** Masques 10× plus naturels

---

### v3.1.5 — Système Intelligent Budget Textures (Enfusion/Reforger) [TRÈS HAUTE PRIORITÉ]

#### 🎯 L'Objectif Central
Passer d'une simple exportation d'images à un système intelligent capable de gérer le budget de textures (slots) par bloc, afin de respecter les contraintes techniques du moteur de jeu (Enfusion/Reforger).

#### 1. ⚖️ Arbitrage des textures (Gestion du budget)
**Description :**
- Analyser chaque bloc (ex: 1x1 km) pour compter le nombre de textures nécessaires.
- Si le nombre dépasse la limite moteur, prioriser les textures les plus importantes (ex: Forêt > Herbe sèche).
- Fusionner ou supprimer les textures minoritaires pour éviter les crashs ou dépassements de slots.

#### 2. 🖤 Correction de la logique "Noir = Transparent"
**Description :**
- Corriger la logique où le noir (0) est interprété comme absence de modification.
- Inverser la logique des masques ou forcer un écrasement (overwrite) explicite des couches précédentes.
- Éviter la superposition indéfinie des textures importées.

#### 3. 🧱 Génération de masques techniques (Textures de base)
**Description :**
- Mettre en place 4 masques principaux basés sur l'analyse de la heightmap :
  - Herbe/Plaine (zones plates, altitude basse)
  - Roche/Falaise (pentes > 45°)
  - Sable/Eau (masque drainage + percentile 15)
  - Terre/Sentiers (zones de transition ou creux TPI)

#### 4. 📦 Optimisation de l'export
**Description :**
- Automatiser le découpage des textures en tiles compatibles avec les sous-scènes du World Editor.
- Générer un fichier de configuration (JSON/HJSON) listant les textures assignées aux slots pour chaque zone.

---

### v3.2 — Système de Projets Complets [TRÈS HAUTE PRIORITÉ]

#### 1. 🏠 Page d'Accueil avec Gestion Projets
**Fichier :** `app.py` (nouvelle page initiale)

**Features :**
- [x] Liste projets existants
- [x] Bouton "Nouveau Projet" → Dialog création
- [x] Bouton "Importer Projet" → File picker
- [x] Bouton "Supprimer Projet" → Confirmation
- [x] Affichage infos projet (date création, heightmap, nb masques)
- [x] Recherche/filtre projets
- [x] Preview miniature heightmap

**Structure dossiers :**
```
projects/
├── mon_ile_2026/
│   ├── project.json          # Metadata + config
│   ├── heightmap/
│   │   ├── original.asc
│   │   └── metadata.json
│   ├── maps/
│   │   ├── hypsometric.png
│   │   ├── naturemap.png
│   │   ├── satellite.png
│   │   └── manifest.json
│   ├── masks/
│   │   ├── herbe.png
│   │   ├── terre.png
│   │   ├── roche_legere.png
│   │   ├── roche_forte.png
│   │   └── manifest.json
│   ├── export/
│   │   └── reforger/
│   │       ├── heightmap_reforger.asc
│   │       └── surface_maps.tar
│   └── satmap/ (optionnel)
│       └── satellite.png
```

**Fichier `project.json` :**
```json
{
  "name": "Mon Île 2026",
  "created": "2026-05-09T15:30:00Z",
  "modified": "2026-05-09T18:45:00Z",
  "heightmap": {
    "filename": "original.asc",
    "dimensions": [4352, 4064],
    "altitude_min": -40.0,
    "altitude_max": 164.0,
    "cellsize": 10.93
  },
  "satmap": {
    "filename": "satellite.png",
    "enabled": true
  },
  "maps_generated": ["hypsometric", "naturemap", "satellite"],
  "masks_generated": ["herbe", "terre", "roche_legere", "roche_forte"],
  "last_settings": {
    "climate_profile": "tempéré",
    "hillshade_strength": 0.5
  }
}
```

---

#### 2. 📤 Import/Export Projets
**Fichier :** `app.py` + nouvelles fonctions

**Features :**
- [x] Export projet complet → ZIP
- [x] Import ZIP → Reconstruction arborescence
- [x] Sauvegarde automatique après génération
- [x] Sauvegarde config utilisateur (profils climatiques, etc.)
- [x] Historique versions projet

**Commandes export :**
```python
def export_project_as_zip(project_name, output_path):
    """Exporte projet complet en ZIP"""
    # Zipper projects/projet_name/ entièrement
    # Inclure project.json + tous masques + cartes
    # Exclus : cache Python, fichiers temporaires
```

**Commandes import :**
```python
def import_project_from_zip(zip_path, projects_dir):
    """Importe ZIP en nouveau projet"""
    # Extraire ZIP
    # Valider structure + project.json
    # Recréer arborescence
```

---

#### 3. 🔗 Intégration Données Reforger
**Fichier :** `app.py` (nouvelle section dans "Export")

**Features :**
- [x] Zone "Importer depuis Reforger"
- [x] Copier-coller données Reforger brutes
- [x] Parser automatique métadonnées (résolution, altitude)
- [x] Conversion format Reforger → ASC/PNG
- [x] Validation hauteurs

**Format accepté :**
```
Reforger Surface Map Export:
Dimensions: 16257×16257px
Cell Size: 2.734375 m/px
Min Altitude: -40.256 m
Max Altitude: 164.512 m
[données brutes hex ou binaire]
```

**Parseur :**
```python
def parse_reforger_data(raw_text):
    """Extrait métadonnées Reforger"""
    # Regex dimensions/cellsize/altitudes
    # Convertir données vers numpy array
    # Sauvegarder en ASC avec header correct
```

---

### v3.3 — Remaniement Graphique Complet [HAUTE PRIORITÉ]

#### 1. 🎨 Redesign Interface Streamlit
**Fichier :** `app.py` (CSS + layout)

**Améliorations :**
- [x] Palette couleur cohérente (bleu terrain, vert nature, marron roche)
- [x] Sidebar collapsible pour plus d'espace
- [x] Badges statut (✅ Généré, ⏳ Calcul, ❌ Erreur)
- [x] Icônes Emoji + FontAwesome pour clarté
- [x] Layout responsive (mobile-friendly)
- [x] Mode sombre optionnel
- [x] Gradients subtils + ombres

**Palette proposée :**
```
Primaire : #2C5F8D (Bleu terrain)
Secondaire : #27AE60 (Vert nature)
Accent : #D4511F (Orange/Roche)
Neutre : #34495E (Gris foncé)
Succès : #27AE60 (Vert)
Erreur : #E74C3C (Rouge)
Warning : #F39C12 (Orange)
```

---

#### 2. 📊 Panneaux d'Information Améliorés
**Fichier :** `app.py`

**Améliorations :**
- [x] Cards avec gradient background
- [x] Statistiques visuelles (graphes sparkline)
- [x] Progress bars pour % terrains
- [x] Comparaison avant/après génération
- [x] Légende interactive des biomes (couleurs Reforger)

**Exemple card :**
```
┌─ 🗺️ Analyse Heightmap ─────────────┐
│                                      │
│ Dimensions:     4352 × 4064 px      │
│ Altitude:       -40m à 164m         │
│ Dénivellation:  204m                │
│ Résolution:     10.93 m/px          │
│                                      │
│ 📊 Distribution altitudes:           │
│ ████░░░░░░ 30% basse (eau/plaine)  │
│ ██████░░░░ 40% moyenne              │
│ ████░░░░░░ 30% haute                │
└──────────────────────────────────────┘
```

---

#### 3. 🎯 Optimisation UX
**Fichier :** `app.py`

**Améliorations :**
- [x] Wizard de configuration initial
- [x] Tooltips explicatifs (hover)
- [x] Shortcuts clavier (Ctrl+S = Export)
- [x] Notifications toast (succès/erreur)
- [x] Sauvegarde auto toutes les 30s
- [x] Undo/Redo pour dernière génération
- [x] Export rapide vers presse-papiers

---

### v4.0 — Production Ready [FUTURE]

#### Features supplémentaires
- [ ] Multi-threading pour générations parallèles
- [ ] Cache intelligent (regenerer seulement changements)
- [ ] Validation masques Reforger en temps réel
- [ ] Intégration WebSocket pour serveur distant
- [ ] Version Desktop (PyQt6) + Web (FastAPI)
- [ ] Base données projets (SQLite)
- [ ] Analytics utilisation projets
- [ ] Marketplace thèmes/profiles climatiques

---

## 📋 Checklist Implémentation

### v3.1 Morphologie
- [ ] `_compute_aspect()` dans NatureMapBiomesGenerator
- [ ] `_compute_tpi()` dans NatureMapBiomesGenerator
- [ ] `_compute_flow_accumulation()` dans NatureMapBiomesGenerator
- [ ] `_compute_depressions()` dans NatureMapBiomesGenerator
- [ ] `generate_smart_masks()` dans TextureLayerGenerator
- [ ] Tests + validation sur Bornholm
- [ ] Documentation + exemples

### v3.1.5 Budget Textures
- [ ] Comptage textures par bloc (1x1 km)
- [ ] Limite slots moteur configurable (Enfusion/Reforger)
- [ ] Priorisation des textures par importance
- [ ] Fusion/suppression des textures minoritaires
- [ ] Correction logique noir=transparent (overwrite forcé)
- [ ] Génération des 4 masques techniques de base
- [ ] Découpage automatique en tiles World Editor
- [ ] Export config slots par zone (JSON/HJSON)
- [ ] Tests d'import et validation dans Reforger

### v3.2 Projets
- [ ] Page d'accueil design + liste projets
- [ ] Création/Import/Export ZIP
- [ ] Structure dossiers + project.json
- [ ] Sauvegarde auto après génération
- [ ] Parser données Reforger
- [ ] Tests importation/exportation

### v3.3 Graphique
- [ ] Redesign CSS Streamlit
- [ ] Palette couleur + thème
- [ ] Cards d'information améliorées
- [ ] Tooltips + shortcuts clavier
- [ ] Mode sombre optionnel
- [ ] Tests responsive (mobile)

---

## 🚀 Commandes Développement

```bash
# Tester morphologie (une fois v3.1 implémentée)
python -c "
from naturemap_biomes_generator import NatureMapBiomesGenerator
gen = NatureMapBiomesGenerator('input/bornholm_ter.asc')
gen._analyze_heightmap()  # Inclut nouvelles analyses
print(f'Aspect min/max: {gen.aspect_deg.min()}/{gen.aspect_deg.max()}')
print(f'TPI min/max: {gen.tpi_map.min()}/{gen.tpi_map.max()}')
"

# Tester projets (une fois v3.2 implémentée)
streamlit run app.py

# Tester export
python -c "
from app import export_project_as_zip
export_project_as_zip('mon_ile_2026', './exports/mon_ile_2026.zip')
"
```

---

## 📝 Notes

- **Compatibilité :** v3.1+ fonctionne avec v3.0 (rétrocompatible)
- **Performance :** TPI + Flow = +30s par heightmap (acceptable)
- **Dépendances :** scipy (pour analyses morpho) déjà présent
- **Testing :** Bornholm 4352×4064 comme ref (représentatif)

---

**Dernière mise à jour :** 9 mai 2026  
**Responsable :** Développement Map Generator  
**État :** En cours (v3.0 stable, v3.1 planning)
