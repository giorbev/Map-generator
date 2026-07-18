# Workflow Final - Masques Zimnitrita

**Date** : 30 juin 2026  
**Statut** : ✅ Validé et fonctionnel

---

## 🎯 Ordre de priorité écologique (décroissant)

### Terrain (70-40)
```
70_coast.png       → Délimite terre/mer (priorité haute)
60_rock.png        → Rochers dominants
50_flow.png        → Érosion
40_deposit.png     → Dépôts sédiments
```

### Végétation exposée/Prairies (30-21)
```
30_landes_rocheuses.png  → Végétation de pente
25_alpages.png           → Alpages montagne
23_prairie_plateau.png   → Prairies plateau
22_prairie_humide.png    → Prairies humides
21_prairie_seche.png     → Prairies sèches
```

### Forêts (15-11)
```
15_foret_clearing_coniferous.png  → Clairières conifères
14_foret_clearing_deciduous.png   → Clairières feuillues
13_foret_pins.png                 → Forêts pins
12_foret_coniferes.png            → Forêts conifères
11_foret_feuillue.png             → Forêts feuillues
```

### Mer (01)
```
01_seabed.png  → Fond marin (pas de conflit)
```

---

## 🔧 Scripts utilisés

### 1. Préparation initiale
```bash
python prepare_zimnitrita_masks.py
```
- Conversion format (float32 → uint16)
- Renommage initial des masques

### 2. Uniformisation dimensions
```bash
python resize_masks_uniform.py
```
- Redimensionne tous vers 4097x4097
- Résout les conflits de taille

### 3. Numérotation écologique
```bash
python reorder_masks_ecological.py
```
- Applique l'ordre de priorité final
- Backup automatique

---

## ✅ Correction QTRE (mask_verif.py)

### Configuration
- **Mode** : Hard (pas de fondu)
- **Ordre** : Décroissant (haute priorité d'abord)
- **Résultat** : Une seule texture dominante par pixel

### Workflow
1. Charger les 15 masques
2. Vérifier ordre affiché : 70 → 60 → ... → 01
3. Onglet "Corrections" → "Prévisualiser correction"
4. Vérifier réduction conflits (> 90%)
5. Exporter masques corrigés

---

## 🎮 Import Reforger

### Fichiers à importer
Dossier : `corrected/` (avec `_noconflict` après export)

Tous les masques 4097x4097 uint16 PNG

### Mapping textures Reforger
```
70_coast        → coastal_pebbles / sand
60_rock         → rock_walls / cliff
50_flow         → erosion_dirt
40_deposit      → sediment_deposit
30_landes       → mountain_grass_03 (rocky)
25_alpages      → mountain_grass_01 (alpine)
23_prairie_plat → grass_01 (plateau)
22_prairie_hum  → grass_02 (humid)
21_prairie_sec  → grass_01_autumn (dry)
15_clearing_con → clearing_coniferous
14_clearing_dec → clearing_deciduous
13_foret_pins   → forest_pine
12_foret_conif  → forest_coniferous
11_foret_feuil  → forest_deciduous
01_seabed       → seabed
```

---

## 💡 Principes clés

### Pourquoi cet ordre fonctionne
1. **Coast définit les contours** → reste visible
2. **Rock domine sans écraser la côte** → éléments marquants
3. **Flow/Deposit entre terrain et végétation** → transitions
4. **Végétation graduée** : exposé (landes) → ouvert (prairies) → dense (forêts)
5. **Seabed en dernier** → pas de conflit avec terre

### Mode Hard vs Mode Fondu
- **Hard** (recommandé) : Une seule texture gagne (zero conflit QTRE)
- **Fondu** : Plusieurs textures survivent avec valeurs réduites (peut créer conflits)

---

## 🔍 Vérifications post-import

### Dans Reforger Workbench
- [ ] Pas d'erreurs console "texture overflow"
- [ ] Pas de blocs > 5 textures
- [ ] Transitions visuelles naturelles
- [ ] Côte bien visible
- [ ] Rochers bien marqués
- [ ] Forêts dans zones protégées

### Performance
- Taille map : 16km × 16km
- Résolution masques : 4097 × 4097
- Nombre textures : 15
- Conflits QTRE : 0 attendu

---

## 📚 Références

### Outils
- `mask_verif.py` : Vérification et correction QTRE
- `prepare_zimnitrita_masks.py` : Préparation initiale
- `resize_masks_uniform.py` : Uniformisation dimensions
- `reorder_masks_ecological.py` : Ordre écologique

### Documentation projet
- `MEMORY.md` : Mémoire contexte projet
- `reference_reforger_constraints.md` : Contraintes QTRE Reforger

---

**✅ Workflow validé le 30/06/2026**
