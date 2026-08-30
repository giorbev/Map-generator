# Référence Fonctions — Map Generator Pro v7.0

**Guide de référence rapide** : Fonctions principales par script

---

## 📌 app.py — Application Streamlit principale

### Gestion projets

```python
create_project(name: str, author: str, description: str) → Path
    """Crée structure nouveau projet et retourne son chemin"""

load_project(project_path: str) → None
    """Charge projet dans session_state (heightmap + terrain_data + config)"""

save_project() → None
    """Sauvegarde état courant dans project.json"""

auto_save() → None
    """Sauvegarde automatique après modification UI"""

list_projects() → list[dict]
    """Liste projets triés par date modification (récents en premier)"""
```

### Cache terrain_data

```python
save_terrain_data_cache(terrain_data: dict, project_path: Path) → bool
    """Sauvegarde terrain_data en NPZ compressé + JSON métadonnées"""

load_terrain_data_cache(project_path: Path, heightmap_path: str) → dict | None
    """Charge terrain_data depuis cache si valide (version pipeline + mtime)"""
```

### Session & UI

```python
initialize_session() → None
    """Initialise variables session_state au démarrage"""

render_navigation_cards() → None
    """Affiche page navigation par cartes (7 onglets)"""

init_navigation() → None
    """Initialise système navigation si nécessaire"""
```

### Parsers

```python
parse_reforger_world_data(text: str) → dict
    """Parse copier-coller World Composition Reforger"""

normalize_path(path_str: str) → str
    """Nettoie chemin Windows (guillemets, espaces, séparateurs)"""
```

### Bibliothèque matériaux (OBSOLÈTE v7.0)

```python
load_merged_library(project_path: str | None) → dict
    """Fusionne bibliothèque vanilla + custom (OBSOLÈTE)"""

save_custom_library(project_path: str, roles: list, materials: list) → None
save_vanilla_library(roles: list, materials: list) → None
```

---

## 📌 base_map.py — Données terrain fondamentales

### Classe BaseMap

```python
class BaseMap:
    __init__(heightmap_path: str, vertical_exaggeration: float = 10.0)
    
    # Propriétés
    heightmap_float: np.ndarray      # float32 altitudes réelles (m)
    heightmap_uint8: np.ndarray      # uint8 normalisé 0-255
    width, height: int
    altitude_min, altitude_max: float
    altitude_range: float
    cellsize: float
    slopes: np.ndarray               # float32 degrés
    water_mask: np.ndarray           # bool
    biome_masks: dict[str, np.ndarray]  # 7 biomes
    
    # Méthodes privées
    _load_heightmap(path: str) → tuple[np.ndarray, np.ndarray]
    _load_asc(path: str) → tuple[np.ndarray, dict]
    _calculate_slopes() → np.ndarray
    _generate_water_mask() → np.ndarray
    _generate_biome_masks() → dict
```

**Biomes disponibles** : `water`, `sand`, `snow`, `rock`, `tundra`, `forest_dense`, `prairie`

---

## 📌 terrain_analysis.py — Calcul dérivés terrain

### Fonction principale

```python
compute_terrain_data(
    heightmap_path: str | Path,
    params: dict | None = None,
    progress_callback: Callable[[str, float], None] | None = None
) → dict
    """
    Calcule TOUS dérivés terrain depuis heightmap UNE SEULE FOIS
    
    Returns:
        {
            # Données brutes
            'heightmap': np.ndarray,         # float32
            'heightmap_smooth': np.ndarray,  # float32
            'meta': dict,                    # ncols, nrows, cellsize, nodata
            'cellsize': float,
            
            # Dérivés
            'slope': np.ndarray,             # float32 degrés
            'curvature': np.ndarray,         # float32 normalisé
            'curvature_plan': np.ndarray,
            'curvature_profile': np.ndarray,
            'tpi_local': np.ndarray,         # Topographic Position Index local 11px
            'tpi_macro': np.ndarray,         # TPI macro 51px
            'flow': np.ndarray,              # Accumulation priority flood
            'deposit': np.ndarray,           # TPI multi-échelle
            'distance_cote': np.ndarray,     # Distance côte (m)
            'aspect': np.ndarray,            # Degrés 0-360
            'roughness': np.ndarray,         # float32 normalisé
            
            # Métadonnées
            'params': dict,                  # Paramètres calibrés
            'computation_time': float,       # secondes
            'timestamp': str,                # ISO 8601
            'pipeline_version': str,         # "2.3.0"
            'heightmap_path': str
        }
    """
```

**Version pipeline** : `TERRAIN_PIPELINE_VERSION = "2.3.0"`

**Algorithmes utilisés** :
- Flow : Priority flood (heap) + post-processing (blur + gamma)
- TPI : Fenêtres glissantes multi-échelles
- Curvature : Zevenbergen & Thorne (plan + profile)

---

## 📌 hypsometric_colormap.py — Cartes hypsométriques

### Classe principale

```python
class HypsometricColormapGenerator:
    __init__(heightmap_path: str, output_dir: str = "output")
    
    save(
        filename: str,
        add_hillshade: bool = False,
        add_enrichment: bool = False
    ) → str
        """
        Génère et sauvegarde colormap hypsométrique
        
        Args:
            filename: Nom fichier sortie
            add_hillshade: Ajouter ombrage relief
            add_enrichment: Ajouter modulation TPI + talwegs
        
        Returns:
            Chemin fichier généré
        """
    
    # Méthodes privées
    _load_heightmap(path: str) → np.ndarray
    _load_asc(path: str) → np.ndarray
    _define_altitude_zones() → None
    _build_hypsometric_palette() → interp1d
    _apply_palette(heightmap: np.ndarray) → np.ndarray
    _compute_hillshade(heightmap: np.ndarray) → np.ndarray
    _compute_enrichment(heightmap: np.ndarray) → np.ndarray
```

**Palette** : Gradient vert bas → jaune → orange → rouge → brun haut

---

## 📌 pipeline_v5.py — Pipeline terrain unifié

### Fonction principale

```python
run_pipeline(
    asc_path: Path,
    output_dir: Path,
    exclusion_mask: Path | None = None,
    gaea_flow: Path | None = None,
    gaea_deposit: Path | None = None,
    mask_config: dict | None = None,
    mode: str = 'preview',  # 'preview' | 'png' | 'ttile'
    terrain_root: Path | None = None,
    data_dir: Path | None = None,
    terr_path: Path | None = None,
    params: dict | None = None
) → dict
    """
    Pipeline complet génération masques terrain
    
    Returns:
        {
            'masks': dict[str, np.ndarray],      # Masques uint16
            'preview_path': str,                 # PNG preview
            'stats': dict,                       # Statistiques
            'warnings': list[str],
            'blocks_written': int,               # Si mode='ttile'
            'blocks_skipped': int
        }
    """
```

### Modules pipeline (9 étapes)

```python
# Module 1 : Lecture heightmap
load_asc(path: Path) → tuple[np.ndarray, dict]

# Module 2 : Calcul terrain
calculate_slope(heightmap: np.ndarray, cellsize: float) → np.ndarray
calculate_curvature_zt(heightmap: np.ndarray, cellsize: float) → np.ndarray
calculate_tpi(heightmap: np.ndarray, radius: int) → np.ndarray
calculate_flow_accumulation(heightmap: np.ndarray, cellsize: float) → np.ndarray
calculate_coastal_distance(heightmap: np.ndarray, sea_level: float, cellsize: float) → np.ndarray

# Module 3-4 : Masques base + végétation
generate_seabed_mask(heightmap, coastal_dist) → np.ndarray
generate_coastal_mask(heightmap, coastal_dist) → np.ndarray
generate_rock_mask(slope, roughness) → np.ndarray
generate_vegetation_masks(heightmap, slope, tpi, flow) → dict

# Module 5 : Application exclusion
apply_exclusion_mask(masks: dict, exclusion: np.ndarray) → dict

# Module 6 : Normalisation
normalize_masks_exclusive(masks: dict) → dict

# Module 7 : Arbitrage budget
arbitrate_budget_per_block(
    masks: dict,
    priorities: dict,
    block_size: int,
    max_slots: int
) → dict

# Module 8 : Visualisation
generate_preview_map(masks: dict, colors: dict) → np.ndarray

# Module 9 : Export
export_masks_png(masks: dict, output_dir: Path) → list[str]
export_ttile(masks: dict, terrain_root: Path, terr_path: Path) → dict
```

### Configuration

```python
MASK_TEXTURE_MAP: dict[str, list[int]]    # Mapping masque → mat_ids
DEFAULT_PRIORITIES: dict[str, int]        # Ordre application masques
BUDGET_MAX: int = 6                       # Slots max par bloc
```

---

## 📌 tab_pipeline_v5.py — Interface UI Pipeline V5

```python
render_tab_pipeline_v5() → None
    """Point d'entrée onglet Pipeline V5 depuis app.py"""

browse_file(title: str, filetypes: list | None) → str | None
    """Dialog tkinter sélection fichier"""

browse_directory(title: str) → str | None
    """Dialog tkinter sélection dossier"""

# Fonctions internes
_load_v5_config(project_path: Path) → None
_save_v5_config(project_path: Path, config: dict) → None
_render_sources_section() → dict
_render_mapping_section() → dict
_render_params_section() → dict
_render_preview_section() → None
_render_export_section() → None
```

---

## 📌 ttile_manager.py — Gestionnaire .ttile complet

### Parsing IFF

```python
parse_ttile(data: bytes) → dict[bytes, tuple]
    """Parse chunks IFF → {tag: (pos, size, payload)}"""

rebuild_ttile(original: bytes, replacements: dict[bytes, bytes]) → bytes
    """Reconstruit .ttile avec chunks remplacés"""
```

### Parsing sections terrain

```python
parse_lrs2(payload: bytes) → dict[tuple, tuple]
    """Parse LRS2 → {(bx,by): ([mat_ids], index)}"""

build_lrs2(entries: dict) → bytes
    """Reconstruit section LRS2"""

parse_gctd(payload: bytes, n_blocs: int) → tuple[bytes, dict, int]
    """Parse GCTD → (header, {(bx,by): data}, payload_size)"""

build_gctd(header: bytes, sections: dict) → bytes
    """Reconstruit section GCTD"""
```

### Opérations blocs

```python
get_block_path(bx: int, by: int, data_dir: Path) → Path
    """Retourne chemin .ttile pour bloc (bx, by)"""

get_block_distribution(block_data: bytes) → dict[int, int]
    """Comptage matériaux dans bloc → {mat_id: count}"""

apply_mask_to_block(
    block_data: bytes,
    mask_png: Path,
    mat_id: int,
    threshold: float = 0.5
) → bytes
    """Applique masque PNG sur bloc"""

optimize_block(block_data: bytes, threshold: int = 5) → bytes
    """Fusionne matériaux sous-représentés (<threshold pixels)"""

replace_material_in_block(
    block_data: bytes,
    old_mat: int,
    new_mat: int,
    condition_mat: int | None = None
) → bytes
    """Remplace old_mat par new_mat (conditionnel si condition_mat)"""

validate_block_consistency(block_data: bytes) → dict
    """Vérifie cohérence LRS2 ↔ GCTD"""
```

### Modes CLI

```python
mode_inspect(bx: int, by: int, data_dir: Path) → None
mode_visualize(bx: int, by: int, data_dir: Path, out: Path) → None
mode_scan(data_dir: Path, mask: Path | None, out: Path) → None
mode_stats(data_dir: Path, out: Path) → None
mode_validate(data_dir: Path) → None
mode_replace(bx, by, old_mat, new_mat, data_dir, dry_run) → None
mode_merge(bx, by, src_mat, dst_mat, data_dir, dry_run) → None
mode_optimize(bx, by, threshold, data_dir, dry_run) → None
mode_apply_mask(bx, by, mask, mat_id, data_dir, dry_run) → None
mode_backup_zone_b(data_dir, mask, out) → None
mode_restore_zone_b(data_dir, backup_json, dry_run) → None
mode_clean_zone_a(data_dir, mask, neutral_mat, dry_run) → None
```

---

## 📌 merge_mat.py — Merge matériaux standalone

### Fonctions principales

```python
merge_block(
    bx: int,
    by: int,
    src_mat: int,
    dst_mat: int,
    mat_filter: int | None = None,
    dry_run: bool = False
) → bool
    """
    Merge src_mat vers dst_mat dans bloc (bx, by)
    
    Args:
        mat_filter: Si fourni, merge SEULEMENT où ce matériau présent
    """

merge_tile(tx: int, ty: int, src_mat, dst_mat, mat_filter, dry_run) → int
    """Merge tous blocs d'une tuile"""

merge_all(src_mat, dst_mat, mat_filter, dry_run) → int
    """Merge tous blocs de la map"""

restore_block(bx: int, by: int) → bool
    """Restaure bloc depuis backup .bak"""

restore_all() → int
    """Restaure tous blocs depuis backups"""
```

**Usage CLI** :
```bash
python merge_mat.py --src 0 --dst 3 --tile 4,27
python merge_mat.py --src 0,mat:9 --dst 3 --all
python merge_mat.py --restore
```

---

## 📌 satmap_v2_generator.py — Génération Satmap v2

### Fonctions principales

```python
load_catalog(catalog_path: Path) → dict
    """Charge catalogue textures enrichi (tint_srgb + BCR paths)"""

get_material_color(mat_id: int, catalog: dict, surfaces: list) → np.ndarray
    """Retourne RGB [R,G,B] pour matériau (mode colored)"""

load_material_texture(
    mat_id: int,
    catalog: dict,
    surfaces: list,
    textures_root: Path
) → np.ndarray | None
    """Charge texture middle BCR (mode textured)"""

generate_satmap_v2(
    terrain_root: Path,
    catalog_path: Path,
    output_path: Path,
    mode: str = 'colored',  # 'colored' | 'textured'
    exclusion_mask: Path | None = None,
    resolution: int = 4097
) → Path
    """
    Génère Satmap v2 depuis layer.edds + LRS2
    
    Returns:
        Chemin PNG généré
    """
```

### Helpers

```python
blend_materials(
    colors: list[np.ndarray],
    weights: np.ndarray
) → np.ndarray
    """Blend couleurs selon poids GPU"""

extract_block_weights(
    edds_data: dict,
    bx: int,
    by: int,
    block_size: int = 128
) → np.ndarray
    """Extrait poids (H, W, 7) pour bloc"""
```

---

## 📌 terrain_terr_reader.py — Parser .terr

```python
read_mats_from_terr(terr_path: Path) → list[dict]
    """
    Parse .terr et extrait liste matériaux
    
    Returns:
        [
            {'id': 0, 'name': 'Grass_03_default', 'guid': '...'},
            {'id': 1, 'name': 'SeaBed_01', 'guid': '...'},
            ...
        ]
    """

# Helpers internes
_parse_iff_chunks(data: bytes) → dict
_extract_surf_names(chunks: dict) → list[str]
_extract_guids(chunks: dict) → list[str]
```

---

## 📌 edds_decoder.py — Décodeur layer.edds

```python
decode_edds_layer(file_path: Path) → dict
    """
    Décode .edds layer (poids GPU)
    
    Returns:
        {
            'width': int,
            'height': int,
            'channels': int,  # 1-7
            'data': np.ndarray  # (H, W, channels) uint8
        }
    """

extract_all_weights(file_path: Path) → np.ndarray
    """Extrait tous poids normalisés → (H, W, 7) float32"""

# Helpers
_decode_rgba(data: bytes, width: int, height: int) → np.ndarray
_decode_bc5(data: bytes, width: int, height: int) → np.ndarray
```

---

## 📌 lrs2_parser.py — Parser LRS2

```python
load_lrs2_from_ttile(ttile_path: Path) → dict[tuple, list]
    """
    Parse section LRS2 depuis .ttile
    
    Returns:
        {
            (bx, by): [mat0, mat1, mat2, ...],  # Matériaux actifs bloc
            ...
        }
    """

parse_lrs2_raw(payload: bytes) → dict[tuple, tuple]
    """Parse payload LRS2 → {(bx,by): ([mats], index)}"""
```

---

## 📌 pipeline_validation.py — Validation masques

```python
load_masks_from_paths(
    file_paths: list[str | Path],
    max_size: int | None = None
) → dict
    """
    Charge masques PNG 16-bit
    
    Returns:
        {
            'masks': list[np.ndarray],  # uint16
            'paths': list[str],
            'shape': tuple,
            'errors': list[str],
            'warnings': list[str]
        }
    """

analyze_conflicts(
    masks: list[np.ndarray],
    threshold: float = 0.15
) → dict
    """
    Détecte conflits masques (overlap > seuil)
    
    Returns:
        {
            'conflict_map': np.ndarray,
            'conflict_pixels': int,
            'conflict_pct': float,
            'pairs': list[tuple]  # [(i, j, overlap_pct)]
        }
    """

simulate_qtre(
    masks: list[np.ndarray],
    priorities: list[int],
    max_slots: int = 4
) → dict
    """
    Simule arbitrage QTRE 4-textures
    
    Returns:
        {
            'final_map': np.ndarray,  # mat_id par pixel
            'stats': dict,
            'warnings': list[str]
        }
    """

export_conflict_report(
    conflicts: dict,
    output_path: Path,
    format: str = 'json'  # 'json' | 'csv' | 'png'
) → Path
```

---

## 📌 project_manager.py — Gestion surfaces.json

```python
load_or_update_surfaces(
    project_path: str | Path,
    terr_path: str | Path
) → tuple[dict, dict]
    """
    Charge ou génère surfaces.json depuis .terr
    
    Returns:
        (
            name_to_id: {"Grass_01": 0, ...},
            id_to_name: {0: "Grass_01", ...}
        )
    """

# Helpers
_generate_surfaces_json(terr_path: Path, output_path: Path) → dict
_check_surfaces_valid(surfaces_json: Path, terr_path: Path) → bool
```

---

## 📌 reforger_texture_budget.py — Budget QTRE

```python
arbitrate_qtre_block(
    masks: list[np.ndarray],
    priorities: list[int],
    max_slots: int = 4
) → np.ndarray
    """Arbitrage per-pixel selon priorités → (H, W) mat_id"""

compute_block_budget(masks: list[np.ndarray]) → dict
    """
    Calcul distribution et slots nécessaires
    
    Returns:
        {
            'slots_needed': int,
            'materials': dict,  # {mat_id: pixel_count}
            'coverage': dict    # {mat_id: pct}
        }
    """

optimize_mask_coverage(
    masks: list[np.ndarray],
    target_slots: int
) → list[np.ndarray]
    """Fusionne masques pour respecter budget"""

load_it_mask(path: Path, target_shape: tuple) → np.ndarray
    """Charge masque Instant Terra (curvature/sediment)"""
```

---

## 📌 write_ttile_block.py — Écriture blocs .ttile

```python
write_block_from_masks(
    bx: int,
    by: int,
    masks: list[np.ndarray],
    mat_ids: list[int],
    terrain_root: Path,
    terr_path: Path,
    backup: bool = True
) → bool
    """
    Écrit bloc .ttile depuis masques
    
    Process:
        1. Backup .bak si demandé
        2. Calcul grille 45×45
        3. Arbitrage 6 slots max
        4. Encode GCTD (4 slots + sub)
        5. Encode LRS2
        6. Rebuild IFF
        7. Écriture
    """

encode_gctd_grid(
    grid: np.ndarray,
    mat_list: list[int]
) → bytes
    """Encode grille 45×45 en format GCTD compressé"""

encode_lrs2_entry(
    bx: int,
    by: int,
    mat_list: list[int]
) → bytes
    """Encode entrée LRS2 pour bloc"""
```

---

## 📌 check_terrain_health.py — Diagnostic santé

```python
check_all_blocks(
    terrain_root: Path,
    mode: str = 'full'  # 'full' | 'quick'
) → dict
    """
    Diagnostic complet terrain
    
    Returns:
        {
            'total_blocks': int,
            'corrupted': list[tuple],     # [(bx, by)]
            'empty': list[tuple],         # Blocs 100% default
            'overbudget': list[tuple],    # >6 slots
            'inconsistent': list[tuple],  # LRS2 ≠ GCTD
            'report': str,
            'warnings': list[str]
        }
    """

check_block_health(bx: int, by: int, data_dir: Path) → dict
    """Diagnostic bloc individuel"""

generate_health_report(results: dict, output_path: Path) → Path
    """Génère rapport HTML/JSON"""
```

---

## 📌 Scripts utilitaires

### compare_texture_blocks.py

```python
compare_blocks(
    block1_path: Path,
    block2_path: Path
) → dict
    """Compare deux blocs .ttile"""
```

### scan_exclusion_zone.py

```python
scan_zone(
    terrain_root: Path,
    exclusion_mask: Path
) → dict
    """Scanne Zone B pour backup"""
```

### simulate_masks.py

```python
simulate_pipeline(
    masks_dir: Path,
    heightmap_path: Path
) → dict
    """Simule pipeline sans écrire"""
```

### tile_inspector.py

```python
inspect_tile(tx: int, ty: int, data_dir: Path) → dict
    """Inspecte tuile complète (16 blocs)"""
```

---

## 🔧 Constantes globales

### Format terrain

```python
GCTD_GRID = 45          # Cellules par axe grille GCTD
GCTD_SIZE = 2026        # Bytes par section (45×45 + 1 padding)
GRID_W = 32             # Tuiles par axe
NUM_BLK = 4             # Blocs par tuile par axe
BUDGET_MAX = 6          # Slots max QTRE (7 total - 1 réservé)
```

### Résolutions

```python
OUTPUT_SIZE = 4096      # Résolution masques PNG
SATMAP_SIZE = 4097      # Résolution Satmap
BLOCK_RES = 128         # Résolution bloc terrain
TILE_RES = 512          # Résolution tuile (128 × 4)
```

---

**Document généré le** : 2026-08-14  
**Auteur** : Claude Code  
**Usage** : Référence rapide développeur
