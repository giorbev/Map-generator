# ROADMAP — Map Generator Pro
*Document interne — refactorisation et développement futur*
*Mis à jour 2026-05-28*

---

## État courant — v5.2

### Pipeline Texture (pipeline_core.py)

| Fonctionnalité | État | Notes |
|---|---|---|
| Pipeline complet heightmap → PNG 16-bit | ✅ Fonctionnel | Testé ZBK island, 0 violation QTRE |
| Biomes climatiques (biomes.json) | ✅ Implémenté | 6 biomes : default, temperate_volcanic, temperate_coastal, alpine_rocky, desert, arctic |
| Analyse hypsométrique adaptive | ✅ Implémenté | _terrain_profile détecte flat/balanced/plateau/mountain, calibre les seuils automatiquement |
| Scalabilité Zimnitrita (65025px) | ✅ Implémenté | MAX_PROCESS_PX=32513 + export pypng ligne par ligne (~200 Mo peak) |
| Import heightmap ASC → PNG | ✅ Implémenté | Conversion one-shot, stockée dans sources/ |
| QTRE 5 ou 7 selon la carte | ✅ Implémenté | Configurable par projet dans project.json |
| Structure projet normalisée | ✅ Implémenté | sources/, generated/, pipeline_temp/, reports/ |

### Modules existants

| Module | État | Notes |
|---|---|---|
| Aperçu Hypsométrique | ✅ Fonctionnel | |
| NatureMap biomes | ✅ Fonctionnel | |
| Aperçu Texture (ancien pipeline) | ✅ Fonctionnel | Profils climatiques, 2 passes |
| Végétation | ✅ Fonctionnel | Carte 2D potentielle |
| Lecture TMAT | ✅ Fonctionnel | |
| SatMap | ✅ Fonctionnel | |
| Reconstruction carte | ✅ Fonctionnel | |
| Fusion masques | ✅ Fonctionnel | |

---

## Priorités suivantes

### 1. Reconstruction et fusion — Zimnitrita *(priorité haute)*

Workflow pour une map partiellement texturée à la main dans Workbench :

1. Lire le `.tmat` → extraire la liste des textures utilisées
2. Importer les masques PNG exportés depuis Workbench → `sources/reforger/export_masks/`
3. Reconstruire une carte 2D superposée (couleur par texture, légende)
4. Sélection des zones à préserver :
   - Mode texture : cocher les textures à garder entièrement
   - Mode zone : dessiner un polygone sur la carte (streamlit-drawable-canvas)
5. Fusion : zones préservées + zones vierges remplies par le pipeline

**Note technique :** résolution et format des masques Workbench à caractériser empiriquement (export un masque test → vérifier résolution, bit-depth, format).

---

### 2. Végétation — 3 chantiers *(priorité haute)*

**2a — Map végétation textures**
Couche supplémentaire au-dessus du pipeline texture : zones forêt/lisière/prairie activent les stems forestiers (ForestDeciduous, Coniferous, ForestClearing déjà dans material_library_vanilla.json). Pipeline en 2 passes : sol d'abord, canopée ensuite.

**2b — SVG → splines Reforger**
Export des contours de zones végétation en SVG simplifié → conversion en splines Reforger (WEGenerators). Difficulté principale : simplification des contours (trop de points = spline inutilisable dans WB).

**2c — Zones de champs**
Détection automatique depuis les masques existants : zones plates + altitude basse + loin de la côte = potentiel agricole. Logique simple sur Grass_01/Dirt.

---

### 3. Assets rocheux *(optionnel, long terme)*

Générer des points de placement (X/Y/Z + orientation) depuis les zones de forte pente/érosion, exportés en `.layer` Reforger. Même principe que le générateur `.layer` OSM. Placement manuel final dans Workbench.

---

## Backlog technique

| Item | Priorité | Notes |
|---|---|---|
| JSON-driven compute_chunk_blends | Moyenne | Faire piloter les eco-conditions de material_library_vanilla.json les scoring functions. Actuellement hardcodé. |
| Stems custom / non-vanilla | Moyenne | Requiert JSON-driven scoring en amont |
| Pipeline érosion 2 passes | Basse | Séparer textures de base et érosion pour calibrage indépendant |
| Variantes roche (aspect, altitude) | Basse | Rock_01 tile rapidement sur grandes surfaces |
| Interface calques (refonte UX) | Très basse | Remplacement Streamlit par stack interactive après stabilisation logique métier |

---

## Règles d'architecture

- **Tout dans le projet** : sources, masques, logs — tous relatifs au dossier projet
- **Hauteur stockée en PNG 16-bit** dans `sources/` après import one-shot (plus d'ASC au runtime)
- **Sortie pipeline** toujours dans `generated/terrain_masks/`
- **Logs horodatés** dans `reports/run_YYYYMMDD_HHMMSS/`
- **NPY intermédiaires** dans `pipeline_temp/` — auto-supprimés après run

---

*Développé par [otea] Giorbev — projet communautaire*
