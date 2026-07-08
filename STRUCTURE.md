# Structure du Projet — Map Generator Pro v5.1

Mise à jour : 8 juillet 2026

---

## 📁 Arborescence

```
Map generator/
├── 📄 app.py                          # Application principale Streamlit
│
├── 🎯 MODULES CORE (27 fichiers)
│   ├── base_map.py                    # Chargement heightmap (ASC/PNG/TGA)
│   ├── terrain_analysis.py           # Calcul dérivés terrain (slope, curvature, TPI, flow)
│   ├── hypsometric_colormap.py        # Génération couleurs hypsométriques
│   ├── app_config.py                  # Configuration chemins Reforger
│   ├── pipeline_validation.py         # Validation pipeline masques
│   ├── emat_scanner_simple.py         # Scanner .emat directory
│   ├── pipeline_v2.py                 # Pipeline 13 masques terrain
│   ├── mask_utils.py                  # Utilitaires masques
│   ├── reforger_texture_budget.py     # Gestion budget QTRE
│   ├── reforger_mask_export.py        # Export masques Layer .dds
│   ├── reforger_satmap_export.py      # Export SatMap tiles
│   ├── reforger_satmap_direct.py      # Export direct satmap
│   ├── reforger_satmap_generator.py   # Génération satmap
│   ├── reforger_emat_parser.py        # Parse .emat tints
│   ├── satmap_v2_generator.py         # Satmap v2.0 simple
│   ├── satmap_v2_textured.py          # Satmap v2.0 TEXTURE (BCR + tiling)
│   ├── satmap_v2_simple.py            # Satmap v2.0 fallback
│   ├── satmap_verifiers.py            # Vérificateurs satmap
│   ├── layer_dds_reader.py            # Lecture Layer .dds QTRE
│   ├── lrs2_parser.py                 # Parse .lrs2
│   ├── terrain_materials_parser.py    # Parse surfaces .terr
│   ├── vegetation_map.py              # Carte végétation potentielle
│   ├── vegetation_generator.py        # Générateur végétation (ancien?)
│   ├── biome_library.py               # Bibliothèque climats/biomes
│   ├── terrain_atlas.py               # Atlas terrain
│   ├── texture_layer_generator.py     # Générateur texture layer
│   └── edds_decoder.py                # Décodeur EDDS
│
├── 📂 scripts/                        # Scripts ponctuels (44 fichiers)
│   ├── tests/                         # 15 test_*.py
│   ├── diagnostic/                    # 11 analyze_*/diagnose_*.py
│   ├── verification/                  # 4 check_*/verify_*.py
│   ├── tools/                         # 13 utilitaires
│   └── README.md
│
├── 📦 backups/                        # Backups scripts (1 fichier)
│   ├── satmap_v2_textured.backup_2026-07-07.py
│   └── README.md
│
├── 🗄️ sauvegarde/                    # Archives projets
│   ├── architecture_clean_2025-05-25/ # Architecture Clean abandonnée (28 fichiers)
│   └── ... (autres backups)
│
├── 📊 data/                           # Données projets
│   ├── projects/                      # Projets Map Generator
│   ├── material_library_vanilla.json  # Bibliothèque matériaux vanilla
│   └── Textures_ArmaReforger/         # Catalogue textures
│
├── 🖼️ img/                           # Images UI
├── 🎭 masks/                          # Masques générés (legacy)
├── 📤 output/                         # Outputs génération
└── 🎨 texturesArmaReforger/           # Textures Reforger

```

---

## 🎯 Modules Critiques (NE JAMAIS SUPPRIMER)

Ces 12 modules sont **ESSENTIELS** au fonctionnement de app.py :

1. ✅ **base_map.py** — Chargement heightmap
2. ✅ **terrain_analysis.py** — Dérivés terrain
3. ✅ **pipeline_v2.py** — Pipeline masques
4. ✅ **reforger_texture_budget.py** — Budget QTRE
5. ✅ **reforger_mask_export.py** — Export masques
6. ✅ **satmap_v2_textured.py** — Satmap texturé
7. ✅ **layer_dds_reader.py** — Lecture Layer .dds
8. ✅ **lrs2_parser.py** — Parse .lrs2
9. ✅ **terrain_materials_parser.py** — Parse surfaces
10. ✅ **reforger_emat_parser.py** — Parse .emat
11. ✅ **vegetation_map.py** — Carte végétation
12. ✅ **emat_scanner_simple.py** — Scan .emat

---

## 📚 Documentation

- [NETTOYAGE_2026-07-08.md](NETTOYAGE_2026-07-08.md) — Rapport nettoyage projet
- [scripts/README.md](scripts/README.md) — Documentation scripts archivés
- [backups/README.md](backups/README.md) — Documentation backups
- [sauvegarde/architecture_clean_2025-05-25/README.md](sauvegarde/architecture_clean_2025-05-25/README.md) — Architecture Clean

---

## 🔄 Restauration

Si besoin de restaurer un script archivé :

```bash
# Ramener un test à la racine
mv scripts/tests/test_satmap_debug.py ./

# Restaurer architecture clean
mv sauvegarde/architecture_clean_2025-05-25 map_generator
```

---

**Dernière mise à jour** : 8 juillet 2026  
**Version** : 5.1  
**Scripts core** : 28  
**Scripts archivés** : 44
