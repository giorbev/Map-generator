# Workflow Global — Génération et Import Masques Terrain

**Projet** : Zimnitrita (16 km²)  
**Version** : 1.0  
**Date** : 2026-08-01

---

## 📋 Vue d'ensemble

Ce document décrit le workflow complet de bout en bout pour la génération et l'import des masques terrain sur Zimnitrita, depuis la préparation initiale jusqu'à la validation finale.

**Pipeline** :
```
Heightmap brute
    ↓
Correction manuelle Workbench
    ↓
Masques Gaea (flow, deposit)
    ↓
Pipeline v3 → 14 masques PNG 16 bits
    ↓
Simulation budget
    ↓
Nettoyage Zone B
    ↓
Import Workbench
    ↓
Validation finale
```

---

## Phase 1 — Préparation terrain

### Objectif
Corriger les artefacts de la heightmap source avant génération des masques.

### Étapes

#### 1.1 Correction manuelle dans Workbench

**Ouvrir Workbench** :
```
World Editor → Open World → Zimnitrita
Terrain Tool → Edit Heightmap
```

**Corrections typiques** :
- Lisser artefacts d'import (pics isolés, crevasses)
- Ajuster zones côtières (pente excessive)
- Corriger anomalies bathymétriques
- Aplanir zones constructions prévues

**Outils Workbench** :
- **Smooth** : Lissage général
- **Flatten** : Aplanissement zones spécifiques
- **Raise/Lower** : Ajustements locaux

#### 1.2 Rebuild Heightmap

**Après modifications** :
```
Terrain Tool → Manage → Rebuild Heightmap
```

**Effet** :
- Bake les modifications dans les fichiers `.ttile`
- Met à jour les normales et la géométrie
- Régénère les index internes

**⚠️ Obligatoire** : Sans rebuild, les modifications ne seront pas visibles dans les exports.

#### 1.3 Export heightmap .asc (si modifiée)

**Si heightmap source modifiée** :
```
Terrain Tool → Export → Heightmap .asc
Destination : data/projects/Zimnitrita/heightmap_corrected.asc
```

**Mettre à jour pipeline_v3.py** :
```python
ASC_PATH = Path("data/projects/Zimnitrita/heightmap_corrected.asc")
```

---

## Phase 2 — Génération masques

### 2a. Masques Gaea

**Objectif** : Générer masques flow (écoulement) et deposit (accumulation) via érosion hydraulique.

#### Ouvrir Gaea

```
Gaea → New Project
Import Heightmap → heightmap_corrected.asc
```

#### Configurer Erosion2

**Paramètres Zimnitrita** (16 km²) :
```
Erosion2 Node:
  - Downcutting    : 0.55  (profondeur incision rivières)
  - Suspended Load : 0.42  (transport sédiments)
  - Shape          : 0.68  (forme vallées)
  - Rock Hardness  : 0.50  (résistance roche)
  - Sediment       : 0.35  (accumulation)
  - Duration       : 50    (cycles érosion)
```

**Ports de sortie** :
- **Flow** : Intensité écoulement (0 = sec, 1 = rivière)
- **Sediment** : Accumulation sédiments (0 = roche nue, 1 = dépôt)

#### Export masques

```
Flow Output → Export
  Format : PNG 16-bit
  Nom : flow_uint16.png
  Destination : data/projects/Zimnitrita/

Sediment Output → Export
  Format : PNG 16-bit
  Nom : sediment_uint16.png
  Destination : data/projects/Zimnitrita/
```

**Vérification visuelle** :
- Flow : Réseaux hydrographiques cohérents
- Sediment : Accumulation vallées, absence crêtes

---

### 2b. Pipeline v3

**Objectif** : Générer les 14 masques terrain depuis heightmap + flow + deposit.

#### Configuration pipeline_v3.py

```python
# Chemins entrées
ASC_PATH = Path("data/projects/Zimnitrita/heightmap_corrected.asc")
FLOW_PATH = Path("data/projects/Zimnitrita/flow_uint16.png")
DEPOSIT_PATH = Path("data/projects/Zimnitrita/sediment_uint16.png")

# Masque exclusion Zone B
EXCLUSION_MASK = Path("data/projects/Zimnitrita/zone_b_mask.png")

# Dossier sortie
OUTPUT_DIR = Path("data/projects/Zimnitrita/masks_v3")
```

#### Ordre de priorité masques

**MASK_PRIORITY validé pour Zimnitrita** :
```python
MASK_PRIORITY = [
    "seabed",            # 1. Fond marin (priorité max)
    "flow",              # 2. Rivières
    "deposit",           # 3. Dépôts sédimentaires
    "coastal_flat",      # 4. Plages plates
    "coastal_slope",     # 5. Pentes côtières
    "landes_rocheuses",  # 6. Landes rocheuses
    "rock",              # 7. Roche nue
    "prairie_humide",    # 8. Prairies humides
    "prairie_seche",     # 9. Prairies sèches
    "landes_plateau",    # 10. Landes de plateau
    "maquis_landes",     # 11. Maquis et landes
    "alpages",           # 12. Alpages
    "foret_feuillue",    # 13. Forêts feuillues
    "foret_coniferes"    # 14. Forêts conifères
]
```

**Raison de l'ordre** :
- Seabed en premier (zones submergées prioritaires)
- Flow/deposit ensuite (réseaux hydro)
- Coastal avant inland (zones littorales spécifiques)
- Rock avant prairies (affleurements prioritaires)
- Forêts en dernier (remplissage)

#### Lancement

```bash
python pipeline_v3.py
```

**Progression attendue** :
```
[INFO] Chargement heightmap : 16257×16257
[INFO] Enrichissement slope via fBm
[INFO] Calcul percentiles...
[INFO] Génération masque seabed... OK
[INFO] Génération masque flow... OK
[INFO] Génération masque deposit... OK
...
[INFO] Export 14 masques dans OUTPUT_DIR
[OK] Pipeline terminé : 14 masques générés
```

**Sortie** : 14 fichiers PNG 16 bits dans `OUTPUT_DIR`
```
01_mask_seabed.png
02_mask_flow.png
03_mask_deposit.png
04_mask_coastal_flat.png
05_mask_coastal_slope.png
06_mask_landes_rocheuses.png
07_mask_rock.png
08_mask_prairie_humide.png
09_mask_prairie_seche.png
10_mask_landes_plateau.png
11_mask_maquis_landes.png
12_mask_alpages.png
13_mask_foret_feuillue.png
14_mask_foret_coniferes.png
```

---

### 2c. Simulation budget

**Objectif** : Vérifier que le nombre de textures par bloc reste ≤ 5 (limite QTRE Reforger).

#### Lancement

```bash
python simulate_masks.py --masks-dir OUTPUT_DIR --output simulate_budget.png
```

**Sortie** : Image PNG 4096×4096 avec code couleur par bloc
- 🟢 **Vert** : 1-4 textures (OK)
- 🔵 **Cyan** : 5 textures (limite)
- 🔴 **Rouge** : 6+ textures (dépassement)

#### Analyse

**Stats console** :
```
Budget par nombre de textures :
  1 texture  : 4520 blocs (27.5%)
  2 textures : 6780 blocs (41.2%)
  3 textures : 3890 blocs (23.7%)
  4 textures :  980 blocs (6.0%)
  5 textures :  210 blocs (1.3%)
  6 textures :   48 blocs (0.3%) ← CRITIQUE
  7 textures :    4 blocs (0.0%) ← CRITIQUE
```

**Objectif validé** : >70% blocs verts (1-4 textures)

**Si dépassement >2%** :
1. Réduire nombre de masques (fusionner prairies)
2. Ajuster seuils dans pipeline_v3.py
3. Créer masques d'exclusion supplémentaires
4. Re-générer et re-simuler

---

## Phase 3 — Nettoyage terrain (spécifique Zimnitrita)

**Objectif** : Nettoyer la Zone B (zone d'exclusion) avant import des nouveaux masques.

### 3a. Diagnostic fichiers

**Vérification santé terrain** :
```bash
python edds_decoder.py --scan-health "I:/Reforger.../Zimnitrita/Terrain/.Data"
```

**Sortie attendue** :
```
Map détectée : résolution 512×512, table_offset=148, format=LZ4 
Scan de 1024 fichiers .edds

✓ OK              : 1024 fichiers
✗ Corrompus       : 0 fichiers
⚠ Hors format     : 0 fichiers
⚠ Ttile manquant  : 0 fichiers
```

**⚠️ Si fichiers corrompus** : Ne PAS continuer, restaurer backup ou re-générer depuis Workbench.

---

### 3b. Scan Zone B

**Identifier blocs avec résidus** :
```bash
python clean_weights.py --scan-zone --mask "data/projects/Zimnitrita/zone_b_mask.png"
```

**Sortie exemple** :
```
RÉSUMÉ :
  Blocs 100% blancs traités : 245
  Blocs pleins propres       : 200
  Blocs pleins avec résidus  : 45 → lancer --clean-zone

BLOCS PLEINS avec résidus :
  LRS2=(46,4) Tile(11,1) : Dirt_01 Concrete_01
  LRS2=(47,4) Tile(11,1) : Rock_01 Debris_Rock_01
  ...

Tuiles à nettoyer (--clean-zone) : 11,1 12,3 15,8
```

**Interprétation** :
- **Blocs propres** : Contiennent uniquement Grass_03 ou SeaBed_01 → OK
- **Blocs avec résidus** : Contiennent d'autres matériaux → À nettoyer

---

### 3c. Nettoyage blocs 100% blancs

**Supprimer résidus sur blocs entièrement dans Zone B** :
```bash
python clean_weights.py --clean-zone --mask "data/projects/Zimnitrita/zone_b_mask.png"
```

**Workflow** :
1. **Dry-run** : Affiche détails des blocs à nettoyer
```
[DRY-RUN] 3 tuiles, 45 blocs à nettoyer

  Tuile (11,1) T363 : 15 blocs à nettoyer
  LRS2=(46,4) Bloc(2,0) : Dirt_01 Concrete_01 → supprimés

Nettoyer 45 blocs dans 3 tuiles ? (oui/non) :
```

2. **Confirmation** : Taper `oui`

3. **Backup automatique** : `.ttile.bak` et `.edds.bak` créés

4. **Nettoyage** : Suppression matériaux non autorisés

5. **Résultat** :
```
[OK] (11,1) : 15 blocs nettoyés
[OK] (12,3) : 18 blocs nettoyés
[OK] (15,8) : 12 blocs nettoyés

[TERMINÉ] 45 blocs nettoyés au total
```

**Matériaux conservés** :
- Grass_03 (herbe par défaut)
- SeaBed_01 (fond marin)

**Matériaux supprimés** : Tous les autres (Dirt, Rock, Concrete, etc.)

---

### 3d. RAZ Zone B (si nécessaire)

**Forcer Grass_03 sur tous les blocs 100% blancs** :
```bash
python clean_weights.py --reset-zone --mask "data/projects/Zimnitrita/zone_b_mask.png"
```

**Utilisation** :
- Terrain vierge garanti avant import masques
- Tous les blocs Zone B → 100% Grass_03
- Utile après modifications massives ou corruption

**Workflow** :
```
Matériau cible : Grass_03
Blocs 100% blancs détectés : 245

[DRY-RUN] Reset Zone B : 245 blocs dans 8 tuiles

  Tuile (11,1) T363 : 30 blocs à resetter

Resetter 245 blocs dans 8 tuiles ? (oui/non) : oui

[OK] (11,1) : 30 blocs resettés
...
[TERMINÉ] 245 blocs resettés au total
```

**⚠️ ATTENTION** :
- Workbench **doit être fermé** avant exécution
- Opération irréversible (sauf restauration backup)
- Efface TOUT le contenu Zone B (textures, poids)

---

## Phase 4 — Import masques Workbench

**Objectif** : Importer les 14 masques dans Reforger Workbench.

### Préparation

1. **Fermer tous les scripts Python**
2. **Fermer Workbench** (si ouvert)
3. **Vérifier emplacement masques** : `OUTPUT_DIR` contient les 14 PNG

### Lancement Workbench

```
World Editor → Open World → Zimnitrita
Terrain Tool → Texturing → Import Masks
```

### Import dans l'ordre de priorité

**Ordre EXACT** (défini dans MASK_PRIORITY) :

1. **01_mask_seabed.png** → Assigner à `SeaBed_01.emat`
2. **02_mask_flow.png** → Assigner à `mud_river.emat` (ou texture rivière)
3. **03_mask_deposit.png** → Assigner à `Pebbles_01.emat` (dépôts)
4. **04_mask_coastal_flat.png** → Assigner à `BeachGrass_01.emat`
5. **05_mask_coastal_slope.png** → Assigner à `Pebbles_02.emat`
6. **06_mask_landes_rocheuses.png** → Assigner à `Heather_01.emat`
7. **07_mask_rock.png** → Assigner à `Rock_01.emat`
8. **08_mask_prairie_humide.png** → Assigner à `Grass_03.emat`
9. **09_mask_prairie_seche.png** → Assigner à `Grass_02.emat`
10. **10_mask_landes_plateau.png** → Assigner à `MountainGrass_01.emat`
11. **11_mask_maquis_landes.png** → Assigner à `Debris_Rock_01.emat`
12. **12_mask_alpages.png** → Assigner à `MountainGrass_03.emat`
13. **13_mask_foret_feuillue.png** → Assigner à `ForestDeciduous_01.emat`
14. **14_mask_foret_coniferes.png** → Assigner à `ForestConiferous_01.emat`

**Pour chaque masque** :
```
1. Clic "Add Layer"
2. Sélectionner fichier PNG
3. Assigner matériau (.emat)
4. Clic "Import"
5. Attendre fin traitement (barre progression)
```

### Erreur "Too many layers"

**Symptôme** : Workbench refuse d'importer, message "Too many layers on tile X,Y"

**Cause** : Bloc déjà saturé (6+ textures)

**Solution** :
```bash
python clean_weights.py --clean 11,1
# Nettoyer la tuile concernée pour libérer des slots
```

**Puis** : Ré-essayer l'import du masque

---

### Génération Normal/Vegetation Map

**Obligatoire depuis patch Reforger** : Le canal alpha de la normal map encode la couverture herbe.

**Après import complet des 14 masques** :
```
Terrain Tool → Manage → Generate Normal Map
Terrain Tool → Manage → Generate Vegetation Map
```

**Attendre fin génération** (peut prendre 5-10 minutes pour 16 km²)

**Résultat** :
- Fichiers `*_normal.edds` mis à jour
- Fichiers `*_vegetation.edds` générés
- Rendu herbe cohérent avec masques

---

## Phase 5 — Validation post-import

**Objectif** : Vérifier l'intégrité du terrain après import.

### 5a. Simulation budget post-import

```bash
python simulate_masks.py --masks-dir OUTPUT_DIR --output post_import_budget.png
```

**Comparer avec simulation pré-import** :
- Budget global stable ?
- Nouveaux dépassements ?
- Zones critiques identifiées ?

**Si dégradation** :
- Vérifier ordre import respecté
- Identifier tuiles problématiques
- Nettoyer avec `--clean` si nécessaire

---

### 5b. Validation cohérence tuiles

**Vérifier tuiles suspectes** (pixels noirs, artefacts visuels) :
```bash
python clean_weights.py --validate 11,1
```

**Sortie attendue** :
```
[TTILE] Terrain_363.ttile
  ✅ FORM size: 12345 OK
  ✅ LRS2 size: 256
  ✅ 16 blocs LRS2

[LAYER] Terrain_363_layer.edds
  ✅ Magic DDS OK
  ✅ 0 pixels invalides

[COHÉRENCE LRS2 / LAYER]
  (0,0): Grass_03=87%, Dirt_01=13%

✅ Aucune erreur détectée
```

**Si erreurs détectées** :
- Restaurer backup (`.bak`)
- Nettoyer avec `--clean`
- Re-importer masque concerné

---

### 5c. Diagnostic final fichiers

```bash
python edds_decoder.py --scan-health "I:/Reforger.../Zimnitrita/Terrain/.Data"
```

**Sortie attendue** :
```
✓ OK              : 1024 fichiers
✗ Corrompus       : 0 fichiers
```

**Si fichiers corrompus** :
1. Noter les tile IDs
2. Restaurer depuis backup :
```powershell
# Restaurer .edds
Get-ChildItem -Filter "Terrain_363_layer.edds.bak" | 
  ForEach-Object { Copy-Item $_.FullName ($_.FullName -replace '\.bak$', '') }

# Restaurer .ttile
Get-ChildItem -Filter "Terrain_363.ttile.bak" | 
  ForEach-Object { Copy-Item $_.FullName ($_.FullName -replace '\.bak$', '') }
```
3. Re-générer normal/vegetation map
4. Re-valider

---

## Notes importantes

### Règles de sécurité

1. **Toujours fermer Workbench** avant toute écriture `.edds` ou `.ttile`
   - Workbench verrouille les fichiers
   - Risque corruption si écriture simultanée

2. **Backups automatiques** créés par `clean_weights.py`
   - `.edds.bak` : Backup layer
   - `.ttile.bak` : Backup LRS2
   - Conservés dans le même dossier

3. **Restauration backup PowerShell** :
```powershell
# Restaurer TOUS les .edds
Get-ChildItem -Filter "*.edds.bak" | 
  ForEach-Object { Copy-Item $_.FullName ($_.FullName -replace '\.bak$', '') }

# Restaurer TOUS les .ttile
Get-ChildItem -Filter "*.ttile.bak" | 
  ForEach-Object { Copy-Item $_.FullName ($_.FullName -replace '\.bak$', '') }
```

4. **Dry-run systématique**
   - Tous les outils affichent un aperçu avant modification
   - Toujours vérifier la liste avant confirmer

---

### Spécifications techniques Zimnitrita

| Paramètre | Valeur |
|-----------|--------|
| **Taille map** | 16 km² |
| **Résolution heightmap** | 16257×16257 |
| **Nombre tuiles** | 32×32 = 1024 |
| **Résolution tuile** | 512×512 pixels |
| **Table offset** | 148 |
| **Format compression** | LZ4 chaîné avec dictionnaire |
| **Limite textures/bloc** | 5 (QTRE Reforger) |

---

### Outils de diagnostic rapide

**Santé fichiers** :
```bash
python edds_decoder.py --scan-health "chemin/.Data"
```

**Inspection tuile visuelle** :
```bash
python clean_weights.py --inspect 11,1
# Sortie : tile_11_1_cleanup.png (800×800 avec textures)
```

**Poids réels par matériau** :
```bash
python clean_weights.py --weights 11,1
# Affiche moyenne, min, max, coverage par matériau
```

**Vérification cohérence** :
```bash
python clean_weights.py --validate 11,1
# Vérifie LRS2 ↔ pixels
```

---

### Troubleshooting

#### Problème : Workbench plante à l'import

**Causes possibles** :
1. Masque PNG corrompu
2. Résolution incorrecte
3. Mémoire insuffisante

**Solutions** :
1. Vérifier résolution masque = 16257×16257
2. Vérifier format PNG 16-bit grayscale
3. Fermer applications lourdes
4. Importer par batch (4-5 masques à la fois)

---

#### Problème : Pixels noirs après import

**Causes** :
1. Bloc avec LRS2 vide
2. Corruption fichier .edds
3. Poids non-normalisés

**Solutions** :
```bash
# 1. Identifier tuile concernée (affichage Workbench)
python clean_weights.py --validate tx,ty

# 2. Si corruption détectée
python edds_decoder.py --scan-health "chemin/.Data"

# 3. Restaurer backup si nécessaire
Copy-Item "Terrain_N.ttile.bak" "Terrain_N.ttile"
Copy-Item "Terrain_N_layer.edds.bak" "Terrain_N_layer.edds"
```

---

#### Problème : Budget dépassé (>5 textures)

**Causes** :
1. Masques qui se chevauchent trop
2. Ordre import incorrect
3. Seuils pipeline mal calibrés

**Solutions** :
1. Vérifier MASK_PRIORITY respecté
2. Fusionner masques similaires (ex: prairies)
3. Ajuster seuils `pipeline_v3.py`
4. Créer masques exclusion supplémentaires
5. Re-générer et re-simuler

---

## Références

- [PIPELINE_V3_DEPENDENCIES.md](technical/PIPELINE_V3_DEPENDENCIES.md) — Architecture pipeline v3
- [FORMAT_LAYER_EDDS.md](technical/FORMAT_LAYER_EDDS.md) — Format binaire .edds
- [SCRIPTS_REFERENCE.md](technical/SCRIPTS_REFERENCE.md) — Référence tous les scripts
- [PIPELINE_LOGIQUE.md](technical/PIPELINE_LOGIQUE.md) — Logique génération masques

---

**Dernière mise à jour** : 2026-08-01  
**Projet** : Map Generator Pro — Zimnitrita 16 km²  
**Auteur** : Documentation workflow collaborative
