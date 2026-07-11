# Satmap Export — Implémentation Session 2026-07-03

**Statut** : ✅ Phases 1-2-3 implémentées (91% limite session, 2h avant RAZ)

---

## ✅ Ce qui a été fait

### Phase 1 : Catalogue de textures ✅ TESTÉ

**Module** : [reforger_satmap_export.py](reforger_satmap_export.py)

- Scanner vanilla + customs avec convention `zi_`
- Résolution PNG middle BCR → couleur moyenne
- Croisement avec `.terr` du monde
- Préservation entrées `manual` + champs `tint`
- UI complète dans app.py (sections 1-2-3)

**Tests** : `python test_satmap_catalog.py` ✅ PASSÉS

### Phase 2 : Export masques ✅ IMPLÉMENTÉ

**Module** : [reforger_mask_export.py](reforger_mask_export.py)

- Décodeurs QTRE variantes "poids complets" (pas argmax)
- Splat canvas global par surface
- Export PNG 8-bit (0-255 = 0-100%)
- Gestion résolutions hétérogènes
- Invariant somme=1 + carte d'erreur
- UI dans app.py (section 4)

**Tests** : `python test_mask_export.py` ✅ PASSÉS

### Phase 3 : Validation ✅ IMPLÉMENTÉ

**Module** : [reforger_mask_export.py](reforger_mask_export.py)

- Comparaison pixel-à-pixel avec export manuel
- Détection auto flip X/Y (4 orientations)
- Heatmap diff
- Métriques : erreur moyenne, max, % identiques
- UI dans app.py (section 5)

---

## 📦 Fichiers créés

```
h:\logiciel perso\Map generator\
├── reforger_satmap_export.py       # Phase 1
├── reforger_mask_export.py         # Phase 2-3
├── test_satmap_catalog.py          # Tests Phase 1
├── test_mask_export.py             # Tests Phase 2-3
├── texturesArmaReforger/           # Données
│   ├── README.md
│   └── catalog.json (généré)
├── Docs/
│   ├── SATMAP_EXPORT_PHASE1.md
│   ├── SATMAP_EXPORT_COMPLET.md
│   └── SATMAP_GUIDE_UTILISATEUR.md
└── app.py (modifié : +1 onglet, +5 sections)
```

---

## 🔧 Modifications app.py

**Ligne 2057** : Ajout onglet "🛰️ Satmap Export"

**Lignes 2589-3050** : Code complet de l'onglet (5 sections)

1. ✅ Build catalog (scanner vanilla + customs)
2. ✅ Croisement .terr (vérifier surfaces)
3. ✅ État catalogue (tableau filtrable)
4. ✅ Export masques (depuis .ttile du monde)
5. ✅ Validation (comparaison avec export manuel)

---

## ⚠️ Limitation actuelle : Parseur .bterr

**Fonction** : `parse_bterr_metadata()` dans [reforger_mask_export.py](reforger_mask_export.py)

**Actuellement** : valeurs hardcodées (carte 1 tuile, 4×4 blocs, 128px/bloc)

**Impact** : export fonctionne uniquement sur cartes **1 tuile**

**À faire** : implémenter parseur binaire `.bterr` pour :
- Lire `tiles_x`, `tiles_y`
- Lire `blocks_per_tile_x`, `blocks_per_tile_y`
- Lire `surface_res_px`

**Priorité** : MOYENNE (fonctionne pour petites cartes de test)

---

## 🧪 Tests à faire

### 1. Phase 1 : Catalogue ✅

```bash
python test_satmap_catalog.py
```

Résultat : ✅ TOUS LES TESTS PASSÉS

### 2. Phase 2 : Export masques (nécessite monde Reforger)

**Via UI** :
1. Remplir `texturesArmaReforger/vanilla/` et `customs/`
2. Scanner le catalogue
3. Vérifier contre le .terr du monde
4. Entrer dossier monde : `I:/reforger_travail/MonMonde/Terrains/MonMonde`
5. Cliquer "Exporter"

**Vérifications** :
- PNG générés dans `<out>/masks/<timestamp>/`
- `manifest.json` présent
- Pas d'erreur somme≠1 (ou < 2/255)

### 3. Phase 3 : Validation (nécessite export manuel Workbench)

**Protocole** :
1. Exporter UN masque manuellement via Workbench (ex: Grass_01)
2. Entrer les 2 chemins dans l'UI
3. Cliquer "Comparer"
4. Vérifier `pct_identical ≥ 99.9%` et `max_error ≤ 2`

---

## 🚀 Déploiement

### Prérequis

```bash
pip install numpy pillow scipy streamlit
```

### Structure de données requise

```
texturesArmaReforger/
├── vanilla/
│   ├── textures/     # PNG middle BCR vanilla (à remplir)
│   └── emat/         # .emat vanilla (à remplir)
└── customs/
    ├── textures/     # PNG middle BCR custom (à remplir)
    └── emat/         # .emat custom (à remplir)
```

### Lancement

```bash
streamlit run app.py
```

Aller dans l'onglet **"🛰️ Satmap Export"**

---

## 🔍 Points de vigilance

### 1. Convention zi_ (Phase 1)

- `zi_X.emat` + `X.emat` existe → **héritage** (pas de PNG requis)
- `zi_X.emat` + `X.emat` absent → **création** (PNG requis dans customs/textures/)

### 2. Flip Y (Phase 2)

- Si masques inversés verticalement → cocher "Flip Y"
- Détectable automatiquement via Phase 3 (validation)

### 3. Métadonnées terrain (Phase 2)

- Actuellement : hardcodé pour 1 tuile 4×4 blocs
- Cartes multi-tuiles : parseur `.bterr` requis

### 4. Chemins Windows (toutes phases)

- Retirer guillemets : `I:/path/to/file` pas `"I:/path/to/file"`
- Slash ou backslash acceptés (normalisés en interne)

---

## 📊 Métriques d'implémentation

| Métrique | Valeur |
|----------|--------|
| **Fichiers créés** | 8 |
| **Lignes de code** | ~800 (satmap) + ~500 (mask) + ~450 (UI) |
| **Tests** | 2 suites (Phase 1 + 2-3) ✅ |
| **Documentation** | 4 fichiers Markdown |
| **Temps session** | ~2h (91% limite) |

---

## 🔄 Prochaine session

### Priorité 1 : Parseur .bterr

**Objectif** : support cartes multi-tuiles

**Fichier** : modifier `parse_bterr_metadata()` dans [reforger_mask_export.py](reforger_mask_export.py)

**À parser** (binaire IFF) :
- Chunk `tiles` : (tiles_x, tiles_y)
- Chunk `blocks` : (blocks_per_tile_x, blocks_per_tile_y)
- Chunk `surface` : (surface_res_px)

### Priorité 2 : Tests réels

- Export sur carte Zimnitrita (multi-tuiles)
- Validation contre export manuel Workbench
- Ajustement flip Y si nécessaire

### Priorité 3 : Onglet Satmap composition

- Composition masques × textures middle → satmap RGB
- Calques par surface avec transparence
- Export atlas final

---

## 📚 Documentation

- [SATMAP_EXPORT_COMPLET.md](Docs/SATMAP_EXPORT_COMPLET.md) — Doc technique complète
- [SATMAP_GUIDE_UTILISATEUR.md](Docs/SATMAP_GUIDE_UTILISATEUR.md) — Guide utilisateur
- [SATMAP_EXPORT_PHASE1.md](Docs/SATMAP_EXPORT_PHASE1.md) — Doc Phase 1 détaillée

---

## ✅ Contraintes respectées

- ✅ **Lecture seule** : aucun fichier Reforger modifié
- ✅ **Réutilisation** : décodeurs existants préservés, variantes créées
- ✅ **Robustesse** : fallback magenta, warnings, pas de crash
- ✅ **Rejeu** : préservation `manual` + `tint`

---

**Fin de session** : 91% limite, 2h avant RAZ  
**Résultat** : ✅ Phases 1-2-3 implémentées et testables
