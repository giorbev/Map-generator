# Scripts Utilitaires — Map Generator Pro

**Archivés le** : 8 juillet 2026  
**Raison** : Nettoyage projet — séparation scripts core vs scripts ponctuels

---

## 📁 Structure

```
scripts/
├── tests/         # 15 scripts test_*.py — debug fonctionnalités
├── diagnostic/    # 11 scripts analyze_*/diagnose_* — diagnostic technique
├── verification/  # 4 scripts check_*/verify_* — validation données
└── tools/         # 13 scripts utilitaires ponctuels
```

---

## 🧪 Tests (15 fichiers)

Scripts de debug pour valider des fonctionnalités spécifiques :

- `test_debug_generation.py` — Test debug génération
- `test_debug_satmap.py` — Test debug satmap
- `test_diagnostic_textures.py` — Diagnostic textures
- `test_emat_parser.py` — Test parser .emat
- `test_mask_export.py` — Test export masques
- `test_material_colors.py` — Test couleurs matériaux
- `test_palette_construction.py` — Test construction palette
- `test_palette_tuile960.py` — Test palette tuile 960
- `test_satmap_catalog.py` — Test catalogue satmap
- `test_satmap_debug.py` — Test debug satmap
- `test_satmap_simple.py` — Test satmap simple
- `test_satmap_workflow_complet.py` — Test workflow complet satmap
- `test_satmap_zimnitrita.py` — Test satmap projet Zimnitrita
- `test_tiles_84_85.py` — Test tiles 84-85
- `test_tiling_performance.py` — Test performance tiling

---

## 🔍 Diagnostic (11 fichiers)

Scripts d'analyse technique pour debugger des problèmes spécifiques :

- `analyze_bterr.py` — Analyse fichiers .bterr
- `analyze_qtre_formats.py` — Analyse formats QTRE
- `analyze_red_zones.py` — Analyse zones rouges
- `analyze_tile_1015.py` — Analyse tile 1015
- `analyze_tile_coords.py` — Analyse coordonnées tiles
- `diagnose_blocs_noirs.py` — Diagnostic blocs noirs satmap
- `diagnose_coords.py` — Diagnostic coordonnées
- `diagnose_layer_float.py` — Diagnostic layer float
- `diagnose_layer_format.py` — Diagnostic format layer
- `diagnose_layer_uint_reinterpret.py` — Diagnostic layer uint reinterpret
- `diagnose_seabed.py` — Diagnostic seabed

---

## ✅ Vérification (4 fichiers)

Scripts de validation données :

- `check_layer_1015.py` — Vérification layer 1015
- `check_missing_tiles.py` — Vérification tiles manquantes
- `check_supertexture_1015.py` — Vérification supertexture 1015
- `verify_bterr_content.py` — Vérification contenu .bterr

---

## 🔧 Tools (13 fichiers)

Scripts utilitaires ponctuels :

- `add_missing_surfaces.py` — Ajout surfaces manquantes
- `clear_cache.py` — Nettoyage cache
- `compare_lrs2.py` — Comparaison fichiers .lrs2
- `create_black_texture.py` — Création texture noire
- `debug_satmap_black.py` — Debug satmap noire
- `decode_bterr.py` — Décodage fichiers .bterr
- `extract_middle_colors.py` — Extraction couleurs middle
- `extract_terrain_materials.py` — Extraction matériaux terrain
- `identify_black_tiles.py` — Identification tiles noires
- `layer edds generator.py` — Générateur layer EDDS ⚠️ NOM AVEC ESPACE
- `list_iff_chunks.py` — Liste chunks IFF
- `rename_textures.py` — Renommage textures
- `scan_sessions.py` — Scan sessions

---

## ⚠️ Notes

- Ces scripts sont **ponctuels** — utilisés pour debugger des problèmes spécifiques
- Ils **ne sont PAS importés** par app.py
- Conservés pour référence historique et debugging futur
- Peuvent être exécutés directement : `python scripts/tests/test_*.py`

---

## 🔙 Restauration

Si besoin de ramener un script à la racine :
```bash
mv scripts/tests/test_satmap_debug.py ./
```
