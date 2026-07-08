"""
Outil de vérification et correction de masques PNG 16-bit.

Fonctionnalités principales:
- Détection des conflits de chevauchement entre masques
- Correction par ordre de priorité (mode hard ou blend)
- Assemblage de masques multiples en un seul
- Comparaison QTRE vs erreurs Reforger
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from pathlib import Path
import re
import json
from scipy.ndimage import binary_dilation, gaussian_filter

try:
    from mask_threshold_cleaner import process_all_masks, MASK_CONFIG, DEFAULT_RULE
except Exception:
    process_all_masks = None
    MASK_CONFIG = {}
    DEFAULT_RULE = None


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def assemble_mask_list(masks, mode="max", ordered_indices=None):
    """Assemble une liste de masques 2D uint16 en un seul masque uint16.

    Args:
        masks: Liste de tableaux numpy 2D (uint16 prefere, uint8 accepte, RGB/RGBA convertis auto).
        mode: "max", "add", "average", "homogeneous" ou "priority".
        ordered_indices: Ordre utilise en mode "priority".

    Returns:
        np.ndarray uint16 de meme taille que les masques d'entree.
    """
    if masks is None or len(masks) < 2:
        raise ValueError("Il faut au moins 2 masques pour l'assemblage.")

    ref_shape = masks[0].shape
    normalized_masks = []

    for idx, mask in enumerate(masks):
        # Conversion automatique RGB/RGBA -> niveaux de gris
        if mask.ndim == 3:
            if mask.shape[2] == 3:
                mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
            elif mask.shape[2] == 4:
                mask = cv2.cvtColor(mask, cv2.COLOR_BGRA2GRAY)
            else:
                raise ValueError(f"Masque index {idx}: format couleur non supporté ({mask.shape[2]} canaux).")

        if mask.ndim != 2:
            raise ValueError(f"Masque index {idx}: image non mono-canal.")
        if mask.shape != ref_shape:
            raise ValueError(f"Masque index {idx}: dimensions {mask.shape} != {ref_shape}.")

        if mask.dtype == np.uint8:
            normalized_masks.append(mask.astype(np.uint16) * 257)
        elif mask.dtype == np.uint16:
            normalized_masks.append(mask)
        else:
            raise ValueError(f"Masque index {idx}: dtype {mask.dtype} non supporte (uint8/uint16).")

    h, w = ref_shape

    if mode == "max":
        assembled = np.zeros((h, w), dtype=np.uint16)
        for mask in normalized_masks:
            assembled = np.maximum(assembled, mask)
        return assembled

    if mode == "add":
        assembled = np.zeros((h, w), dtype=np.uint32)
        for mask in normalized_masks:
            assembled += mask.astype(np.uint32)
        return np.clip(assembled, 0, 65535).astype(np.uint16)

    if mode in ("average", "homogeneous"):
        sum_vals = np.zeros((h, w), dtype=np.float32)
        count = np.zeros((h, w), dtype=np.float32)
        for mask in normalized_masks:
            sum_vals += mask.astype(np.float32)
            count += (mask > 0).astype(np.float32)
        count = np.maximum(count, 1.0)
        return np.round(sum_vals / count).astype(np.uint16)

    if mode == "priority":
        if ordered_indices is None:
            ordered_indices = list(range(len(normalized_masks)))
        if len(ordered_indices) != len(normalized_masks):
            raise ValueError("ordered_indices doit contenir un index pour chaque masque.")

        assembled = np.zeros((h, w), dtype=np.uint16)
        occupied = np.zeros((h, w), dtype=bool)
        for idx in ordered_indices:
            current = normalized_masks[idx]
            keep = (current > 0) & (~occupied)
            assembled = np.where(keep, current, assembled)
            occupied |= keep
        return assembled

    raise ValueError(f"Mode d'assemblage inconnu: {mode}")


def analyze_mask_histogram(mask_uint16):
    """Analyse l'histogramme d'un masque et suggère un seuil optimal.

    Args:
        mask_uint16: Masque numpy array uint16

    Returns:
        dict avec stats et suggestion
    """
    # Normaliser en 0-255
    mask_u8 = (mask_uint16.astype(np.float32) / 65535.0 * 255.0).astype(np.uint8)

    # Calculer histogramme
    hist, bins = np.histogram(mask_u8.flatten(), bins=256, range=(0, 256))

    # Statistiques
    non_zero = mask_u8[mask_u8 > 0]
    stats = {
        'min': int(np.min(mask_u8)),
        'max': int(np.max(mask_u8)),
        'mean': float(np.mean(mask_u8)),
        'median': float(np.median(mask_u8)),
        'p10': float(np.percentile(mask_u8, 10)),
        'p25': float(np.percentile(mask_u8, 25)),
        'p50': float(np.percentile(mask_u8, 50)),
        'p75': float(np.percentile(mask_u8, 75)),
        'p90': float(np.percentile(mask_u8, 90)),
        'non_zero_count': len(non_zero),
        'non_zero_percent': (len(non_zero) / mask_u8.size) * 100.0
    }

    # Suggestion de seuil intelligent
    if stats['non_zero_percent'] < 5:
        # Masque très sparse : seuil bas
        suggested = max(5, int(stats['p10']))
        reason = f"Masque sparse ({stats['non_zero_percent']:.1f}% non-zéro) → seuil bas (P10)"
    elif stats['max'] < 30:
        # Valeurs très faibles : seuil très bas
        suggested = max(3, int(stats['mean'] * 0.5))
        reason = f"Valeurs faibles (max={stats['max']}) → seuil bas (50% moyenne)"
    else:
        # Détection bimodale (2 pics)
        # Chercher le creux entre 2 pics potentiels
        smooth_hist = gaussian_filter(hist.astype(np.float32), sigma=3)

        # Chercher minimum local entre P25 et P75
        start_idx = int(stats['p25'])
        end_idx = min(int(stats['p75']), 255)

        if end_idx > start_idx + 10:
            valley_idx = start_idx + np.argmin(smooth_hist[start_idx:end_idx])
            suggested = valley_idx
            reason = f"Creux détecté entre 2 pics → seuil optimal"
        else:
            # Fallback : légèrement au-dessus de P10
            suggested = int(stats['p10'] * 1.2)
            reason = f"Distribution standard → P10 × 1.2"

    suggested = max(1, min(255, suggested))  # Clamp 1-255

    return {
        'stats': stats,
        'histogram': hist,
        'bins': bins,
        'suggested_threshold': suggested,
        'suggestion_reason': reason
    }


def convert_to_bw_with_falloff(mask_uint16, threshold=15, falloff_pixels=40):
    """Convertit un masque uint16 en noir & blanc avec falloff doux sur les bords.

    Args:
        mask_uint16: Masque numpy array uint16 (0-65535)
        threshold: Seuil de conversion (0-255) - tout pixel > threshold devient blanc
        falloff_pixels: Nombre de pixels pour le falloff gaussien sur les bords

    Returns:
        np.ndarray uint16 avec falloff appliqué
    """
    # Normaliser en 0-255 uint8
    mask_u8 = (mask_uint16.astype(np.float32) / 65535.0 * 255.0).astype(np.uint8)

    # Appliquer seuil binaire
    binary_mask = (mask_u8 > threshold).astype(np.uint8) * 255

    # Appliquer falloff : flou gaussien direct sur le binaire
    if falloff_pixels > 0:
        # Flou gaussien directement sur le masque binaire pour créer un falloff doux
        # Plus le sigma est grand, plus la transition est douce
        sigma = falloff_pixels / 2.5  # Ajusté pour un falloff optimal
        result_float = gaussian_filter(binary_mask.astype(np.float32), sigma=sigma)
        result_u8 = np.clip(result_float, 0, 255).astype(np.uint8)
    else:
        result_u8 = binary_mask

    # Reconvertir en uint16
    result_uint16 = (result_u8.astype(np.float32) / 255.0 * 65535.0).astype(np.uint16)

    return result_uint16


def convert_float32_to_uint16(input_path, output_path=None):
    """Convertit une image float32 en uint16 PNG normalisé.

    Args:
        input_path: Chemin vers l'image source (PNG, TIF, etc.).
        output_path: Chemin de sauvegarde optionnel. Si None, ajoute '_uint16' au nom.

    Returns:
        tuple: (array uint16, chemin de sortie) ou (None, None) si pas de conversion nécessaire.

    Raises:
        ValueError: Si le fichier n'existe pas ou est illisible.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise ValueError(f"Fichier introuvable: {input_path}")

    # Lecture de l'image (supporte PNG, TIF, etc.)
    try:
        # Essai avec imread pour TIF/PNG avec métadonnées float
        img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            # Fallback pour chemins Unicode ou formats spéciaux
            img_bytes = np.fromfile(str(input_path), dtype=np.uint8)
            img = cv2.imdecode(img_bytes, cv2.IMREAD_UNCHANGED)

        if img is None:
            raise ValueError(f"Impossible de lire l'image: {input_path}")
    except Exception as exc:
        raise ValueError(f"Erreur de lecture: {exc}")

    # Vérification du dtype
    if img.dtype != np.float32:
        print(f"[INFO] L'image est déjà en {img.dtype}, pas de conversion nécessaire.")
        return None, None

    # Conversion RGB/RGBA -> niveaux de gris si nécessaire
    if img.ndim == 3:
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        else:
            raise ValueError(f"Format couleur non supporté: {img.shape[2]} canaux")

    # Normalisation float32 -> uint16 (0..1 -> 0..65535)
    # Gaea exporte souvent dans [0, 1], mais on clip au cas où
    img_min = np.min(img)
    img_max = np.max(img)

    if img_max > img_min:
        # Normalisation linéaire sur toute la plage dynamique
        img_normalized = (img - img_min) / (img_max - img_min)
    else:
        # Image uniforme
        img_normalized = np.zeros_like(img)

    img_uint16 = np.clip(np.round(img_normalized * 65535.0), 0, 65535).astype(np.uint16)

    # Génération du chemin de sortie
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_uint16.png"
    else:
        output_path = Path(output_path)

    # Sauvegarde
    ok = cv2.imwrite(str(output_path), img_uint16)
    if not ok:
        raise ValueError(f"Impossible d'écrire le fichier: {output_path}")

    print(f"[OK] Conversion réussie: {input_path.name} -> {output_path.name}")
    print(f"     Plage originale: [{img_min:.6f}, {img_max:.6f}] -> [0, 65535]")

    return img_uint16, str(output_path)


# ============================================================================
# APPLICATION PRINCIPALE
# ============================================================================

class MaskOverlapApp:
    """Interface graphique pour la vérification et correction de masques."""

    def __init__(self, root):
        self.root = root
        self.root.title("Mask Verif Pro - Détecteur de conflits et conversion")
        self.root.geometry("1400x900")  # Fenêtre plus grande
        self.root.state('zoomed')  # Maximiser au démarrage (Windows)

        # Charger material_types.json
        self.material_types_path = Path(__file__).parent / "material_types.json"
        try:
            with open(self.material_types_path, 'r', encoding='utf-8') as f:
                self.material_types = json.load(f)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger material_types.json: {e}")
            self.material_types = {"Default": {
                "min_visible": 0.161,
                "noise_amplitude": 0.15,
                "blur_radius": 10,
                "falloff_curve": "smooth"
            }}

        # --- Variables d'état ---
        self._init_state_variables()

        # --- Interface Graphique ---
        self._build_ui()

    # ========================================================================
    # INITIALISATION
    # ========================================================================

    def _init_state_variables(self):
        """Initialise toutes les variables d'état de l'application."""
        # Masques principaux
        self.mask_paths = []
        self.masks = []
        self.mask_stack = None
        self.cleaned_masks = None
        self.assembled_mask = None
        self.ordered_indices = []

        # Masques erreur Reforger
        self.reforger_error_mask_paths = []
        self.reforger_error_masks = []
        self.reforger_error_combined = None
        self.qtre_combined_heatmap = None
        self.cyan_mask = None

        # Affichage
        self.ax_conflict = None
        self.ax_qtre_combined = None
        self.canvas = None
        self.fig = None

        # Configuration
        self.default_mask_dir = Path("h:/logiciel perso/Map generator/data/projects/Zbk_island/sources/instant")
        if not self.default_mask_dir.exists():
            self.default_mask_dir = Path.cwd()

        # Paramètres
        self.blend_mode_var = tk.BooleanVar(value=False)  # Mode hard par défaut (géologique)
        self.priority_threshold_var = tk.DoubleVar(value=0.05)  # Seuil 5% pour priorité stricte
        self.conflict_threshold_var = tk.DoubleVar(value=0.15)
        self.meters_per_pixel_var = tk.DoubleVar(value=1.0)
        self.assembly_mode = tk.StringVar(value="homogeneous")
        self.exclusion_base_mask = tk.IntVar(value=0)
        self.exclusion_mask_idx = tk.IntVar(value=1)

        # Paramètres conversion noir & blanc
        self.bw_threshold_var = tk.IntVar(value=15)
        self.bw_falloff_var = tk.IntVar(value=40)
        self.bw_preview_mask = None
        self.bw_processed_masks = None

        # Paramètres traitement batch falloff
        self.batch_falloff_var = tk.IntVar(value=40)
        self.batch_noise_var = tk.DoubleVar(value=0.30)
        self.batch_material_type_var = tk.StringVar(value="Default")
        self.batch_falloff_preview_masks = None

        # Palette de couleurs pour distinction visuelle
        self.mask_colors = [
            (0.90, 0.15, 0.15),  # rouge
            (0.10, 0.70, 0.20),  # vert
            (0.12, 0.45, 0.90),  # bleu
            (0.95, 0.65, 0.10),  # orange
            (0.70, 0.20, 0.85),  # violet
            (0.10, 0.75, 0.75),  # cyan
            (0.85, 0.85, 0.15),  # jaune
            (0.95, 0.40, 0.65),  # rose
        ]

    def _build_ui(self):
        """Construit l'interface graphique complète."""
        # Container principal avec sidebar + content
        main_container = tk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)

        # Sidebar à gauche
        self._build_sidebar(main_container)

        # Zone principale à droite (contenu + graphiques)
        right_container = tk.Frame(main_container)
        right_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Zone de contenu (onglets)
        self.content_frame = tk.Frame(right_container)
        self.content_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False, padx=10, pady=10)

        # Zone de log
        self._build_log_frame(right_container)

        # Zone graphique en bas
        self._build_plot_frame(right_container)

        # Construction des contenus d'onglets
        self._build_corrections_content()
        self._build_assembly_content()
        self._build_overlay_content()
        self._build_processmask_content()
        self._build_reforger_content()

        # Affichage initial
        self._show_corrections_tab()

    def _build_sidebar(self, parent):
        """Construit la barre latérale de navigation."""
        sidebar = tk.Frame(parent, bg="#263238", width=220)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=0, pady=0)
        sidebar.pack_propagate(False)

        # Logo / Titre
        title_label = tk.Label(
            sidebar,
            text="Mask Verif Pro",
            bg="#263238",
            fg="white",
            font=('Helvetica', 14, 'bold'),
            pady=15
        )
        title_label.pack(side=tk.TOP, fill=tk.X)

        # Bouton Charger masques
        self.btn_load_masks = tk.Button(
            sidebar,
            text="📂 Charger masques PNG",
            command=self.load_masks,
            bg="#2196F3",
            fg="white",
            font=('Helvetica', 10, 'bold'),
            activebackground="#1976D2",
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            pady=8
        )
        self.btn_load_masks.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 5))

        # Bouton Réinitialiser
        self.btn_reset = tk.Button(
            sidebar,
            text="🔄 Réinitialiser",
            command=self.reset_masks,
            bg="#607D8B",
            fg="white",
            font=('Helvetica', 10, 'bold'),
            activebackground="#455A64",
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            pady=8
        )
        self.btn_reset.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 20))

        # Séparateur
        tk.Frame(sidebar, bg="#37474F", height=2).pack(fill=tk.X, padx=10, pady=5)

        # Titre section Traitement
        tk.Label(
            sidebar,
            text="TRAITEMENT",
            bg="#263238",
            fg="#90A4AE",
            font=('Helvetica', 9, 'bold'),
            anchor="w",
            padx=15
        ).pack(fill=tk.X, pady=(10, 5))

        # Onglets de navigation
        self.btn_tab_corrections = self._create_nav_button(sidebar, "✂️ Corrections", self._show_corrections_tab)
        self.btn_tab_assembly = self._create_nav_button(sidebar, "🔧 Assemblage", self._show_assembly_tab)
        self.btn_tab_overlay = self._create_nav_button(sidebar, "🎨 Superposition", self._show_overlay_tab)
        self.btn_tab_processmask = self._create_nav_button(sidebar, "⚙️ ProcessMask", self._show_processmask_tab)

        # Séparateur
        tk.Frame(sidebar, bg="#37474F", height=2).pack(fill=tk.X, padx=10, pady=15)

        # Titre section Reforger
        tk.Label(
            sidebar,
            text="ARMA REFORGER",
            bg="#263238",
            fg="#90A4AE",
            font=('Helvetica', 9, 'bold'),
            anchor="w",
            padx=15
        ).pack(fill=tk.X, pady=(10, 5))

        self.btn_tab_reforger = self._create_nav_button(sidebar, "🎮 QTRE vs Erreurs", self._show_reforger_tab)

        # Status en bas de sidebar
        self.lbl_status = tk.Label(
            sidebar,
            text="Aucun masque\nchargé",
            bg="#263238",
            fg="#90A4AE",
            font=('Helvetica', 8),
            wraplength=200,
            justify="center",
            pady=10
        )
        self.lbl_status.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

        # Variable pour onglet actif
        self.active_tab = None
        self.nav_buttons = [
            self.btn_tab_corrections,
            self.btn_tab_assembly,
            self.btn_tab_overlay,
            self.btn_tab_processmask,
            self.btn_tab_reforger
        ]

    def _create_nav_button(self, parent, text, command):
        """Crée un bouton de navigation stylisé."""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg="#37474F",
            fg="white",
            font=('Helvetica', 10),
            activebackground="#455A64",
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            anchor="w",
            padx=15,
            pady=10
        )
        btn.pack(side=tk.TOP, fill=tk.X, padx=10, pady=2)
        return btn

    def _set_active_tab(self, btn):
        """Met à jour le style du bouton actif."""
        for b in self.nav_buttons:
            b.config(bg="#37474F", fg="white")
        btn.config(bg="#2196F3", fg="white")

    def _build_corrections_content(self):
        """Construit le contenu de l'onglet Corrections."""
        self.corrections_content = tk.Frame(self.content_frame, bg="white")

        # Titre
        title_frame = tk.Frame(self.corrections_content, bg="white")
        title_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(
            title_frame,
            text="Correction des masques",
            font=('Helvetica', 14, 'bold'),
            bg="white",
            fg="#263238"
        ).pack(side=tk.LEFT)

        # Section 1: Nettoyage threshold
        threshold_frame = tk.LabelFrame(
            self.corrections_content,
            text="🧹 Nettoyage par seuil (threshold)",
            font=('Helvetica', 10, 'bold'),
            padx=15,
            pady=10,
            bg="white"
        )
        threshold_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(
            threshold_frame,
            text="Applique les seuils de la configuration MASK_CONFIG pour nettoyer les masques.",
            bg="white",
            fg="#455A64",
            wraplength=600,
            justify="left"
        ).pack(anchor="w", pady=(0, 10))

        self.btn_threshold_clean = tk.Button(
            threshold_frame,
            text="▶ Nettoyer masques (threshold)",
            command=self.run_threshold_cleaning,
            bg="#1565C0",
            fg="white",
            activebackground="#0D47A1",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            pady=5
        )
        self.btn_threshold_clean.pack(anchor="w")

        # Section 2: Correction par priorité
        priority_frame = tk.LabelFrame(
            self.corrections_content,
            text="✂️ Correction géologique par priorité (haute → basse)",
            font=('Helvetica', 10, 'bold'),
            padx=15,
            pady=10,
            bg="white"
        )
        priority_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(
            priority_frame,
            text="Ordre DÉCROISSANT (50→01) : les numéros élevés ont la priorité la plus haute.\n"
                 "Ex: 50_rock écrase 20_grass | Mode Hard: seule la texture prioritaire survit sur chaque pixel",
            bg="white",
            fg="#455A64",
            font=('Helvetica', 8),
            wraplength=600,
            justify="left"
        ).pack(anchor="w", pady=(0, 10))

        self.lbl_order_info = tk.Label(
            priority_frame,
            text="Ordre actuel: aucun masque chargé",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9, 'bold'),
            wraplength=600,
            justify="left"
        )
        self.lbl_order_info.pack(anchor="w", pady=(0, 10))

        options_frame = tk.Frame(priority_frame, bg="white")
        options_frame.pack(anchor="w", pady=(0, 10))

        self.chk_blend_mode = tk.Checkbutton(
            options_frame,
            text="Mode fondu gris (nuances progressives)",
            variable=self.blend_mode_var,
            onvalue=True,
            offvalue=False,
            bg="white",
            fg="#263238",
            font=('Helvetica', 9)
        )
        self.chk_blend_mode.pack(side=tk.LEFT)

        buttons_frame = tk.Frame(priority_frame, bg="white")
        buttons_frame.pack(anchor="w")

        self.btn_preview_cleanup = tk.Button(
            buttons_frame,
            text="👁 Prévisualiser correction",
            command=self.preview_cleanup_ordered,
            bg="#6A1B9A",
            fg="white",
            activebackground="#4A148C",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_preview_cleanup.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_export_cleanup = tk.Button(
            buttons_frame,
            text="💾 Exporter masques corrigés",
            command=self.export_cleaned_masks,
            bg="#2E7D32",
            fg="white",
            activebackground="#1B5E20",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_export_cleanup.pack(side=tk.LEFT)

        # Section 3: Conversion Noir & Blanc avec Falloff
        bw_frame = tk.LabelFrame(
            self.corrections_content,
            text="🎯 Conversion Noir & Blanc avec Falloff",
            font=('Helvetica', 10, 'bold'),
            padx=15,
            pady=10,
            bg="white"
        )
        bw_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(
            bw_frame,
            text="Convertit un masque en noir & blanc avec transition douce (falloff) sur les bords des zones blanches.",
            bg="white",
            fg="#455A64",
            wraplength=600,
            justify="left"
        ).pack(anchor="w", pady=(0, 10))

        # Sliders
        sliders_frame = tk.Frame(bw_frame, bg="white")
        sliders_frame.pack(anchor="w", fill=tk.X, pady=(0, 10))

        # Threshold
        threshold_slider_frame = tk.Frame(sliders_frame, bg="white")
        threshold_slider_frame.pack(fill=tk.X, pady=5)
        tk.Label(
            threshold_slider_frame,
            text="Seuil (threshold):",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9),
            width=18,
            anchor="w"
        ).pack(side=tk.LEFT)
        self.bw_threshold_slider = tk.Scale(
            threshold_slider_frame,
            from_=0,
            to=255,
            orient=tk.HORIZONTAL,
            variable=self.bw_threshold_var,
            bg="white",
            fg="#263238",
            highlightthickness=0,
            length=300
        )
        self.bw_threshold_slider.pack(side=tk.LEFT, padx=(10, 5))
        self.lbl_bw_threshold_value = tk.Label(
            threshold_slider_frame,
            text="15",
            bg="white",
            fg="#1565C0",
            font=('Helvetica', 9, 'bold'),
            width=4
        )
        self.lbl_bw_threshold_value.pack(side=tk.LEFT)
        self.bw_threshold_var.trace_add('write', self._update_bw_threshold_label)

        # Falloff
        falloff_slider_frame = tk.Frame(sliders_frame, bg="white")
        falloff_slider_frame.pack(fill=tk.X, pady=5)
        tk.Label(
            falloff_slider_frame,
            text="Falloff (pixels):",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9),
            width=18,
            anchor="w"
        ).pack(side=tk.LEFT)
        self.bw_falloff_slider = tk.Scale(
            falloff_slider_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.bw_falloff_var,
            bg="white",
            fg="#263238",
            highlightthickness=0,
            length=300
        )
        self.bw_falloff_slider.pack(side=tk.LEFT, padx=(10, 5))
        self.lbl_bw_falloff_value = tk.Label(
            falloff_slider_frame,
            text="40",
            bg="white",
            fg="#1565C0",
            font=('Helvetica', 9, 'bold'),
            width=4
        )
        self.lbl_bw_falloff_value.pack(side=tk.LEFT)
        self.bw_falloff_var.trace_add('write', self._update_bw_falloff_label)

        # Boutons
        bw_buttons_frame = tk.Frame(bw_frame, bg="white")
        bw_buttons_frame.pack(anchor="w")

        self.btn_bw_analyze = tk.Button(
            bw_buttons_frame,
            text="📊 Analyser + Suggérer",
            command=self.analyze_and_suggest_threshold,
            bg="#00897B",
            fg="white",
            activebackground="#00695C",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_bw_analyze.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_bw_preview = tk.Button(
            bw_buttons_frame,
            text="👁 Aperçu N&B",
            command=self.preview_bw_conversion,
            bg="#9C27B0",
            fg="white",
            activebackground="#7B1FA2",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_bw_preview.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_bw_apply_batch = tk.Button(
            bw_buttons_frame,
            text="⚡ Appliquer (batch)",
            command=self.apply_bw_batch,
            bg="#FF6F00",
            fg="white",
            activebackground="#E65100",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_bw_apply_batch.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_bw_export = tk.Button(
            bw_buttons_frame,
            text="💾 Exporter",
            command=self.export_bw_masks,
            bg="#2E7D32",
            fg="white",
            activebackground="#1B5E20",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_bw_export.pack(side=tk.LEFT)

    def _build_assembly_content(self):
        """Construit le contenu de l'onglet Assemblage."""
        self.assembly_content = tk.Frame(self.content_frame, bg="white")

        # Titre
        title_frame = tk.Frame(self.assembly_content, bg="white")
        title_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(
            title_frame,
            text="Assemblage de masques",
            font=('Helvetica', 14, 'bold'),
            bg="white",
            fg="#263238"
        ).pack(side=tk.LEFT)

        # Description
        tk.Label(
            self.assembly_content,
            text="Combine plusieurs masques en un seul selon la méthode choisie.",
            bg="white",
            fg="#455A64",
            wraplength=600,
            justify="left"
        ).pack(anchor="w", pady=(0, 15))

        # Options d'assemblage standard
        modes_frame = tk.LabelFrame(
            self.assembly_content,
            text="🔧 Méthode d'assemblage standard",
            font=('Helvetica', 10, 'bold'),
            padx=15,
            pady=10,
            bg="white"
        )
        modes_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Radiobutton(
            modes_frame,
            text="Maximum (garde la valeur max de chaque pixel)",
            variable=self.assembly_mode,
            value="max",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9)
        ).pack(anchor="w", pady=2)

        tk.Radiobutton(
            modes_frame,
            text="Addition (somme avec clamp à 65535)",
            variable=self.assembly_mode,
            value="add",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9)
        ).pack(anchor="w", pady=2)

        tk.Radiobutton(
            modes_frame,
            text="Homogène (moyenne sans double pixel)",
            variable=self.assembly_mode,
            value="homogeneous",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9)
        ).pack(anchor="w", pady=2)

        tk.Radiobutton(
            modes_frame,
            text="Priorité (ordre 01 → XX)",
            variable=self.assembly_mode,
            value="priority",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9)
        ).pack(anchor="w", pady=2)

        tk.Radiobutton(
            modes_frame,
            text="Exclusion (masque base + masque d'exclusion)",
            variable=self.assembly_mode,
            value="exclusion",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9),
            command=self._toggle_exclusion_controls
        ).pack(anchor="w", pady=2)

        # Boutons d'action assemblage standard
        actions_frame = tk.Frame(self.assembly_content, bg="white")
        actions_frame.pack(anchor="w", pady=(10, 0))

        self.btn_assemble = tk.Button(
            actions_frame,
            text="▶ Assembler",
            command=self.assemble_masks,
            bg="#6A1B9A",
            fg="white",
            activebackground="#4A148C",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_assemble.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_export_assembled_separate = tk.Button(
            actions_frame,
            text="💾 Sauvegarder résultat",
            command=self.export_assembled_mask_separate,
            bg="#2E7D32",
            fg="white",
            activebackground="#1B5E20",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_export_assembled_separate.pack(side=tk.LEFT)

        # Section Exclusion
        exclusion_frame = tk.LabelFrame(
            self.assembly_content,
            text="✂️ Configuration masque d'exclusion",
            font=('Helvetica', 10, 'bold'),
            padx=15,
            pady=10,
            bg="white"
        )
        exclusion_frame.pack(fill=tk.X, pady=(15, 0))

        tk.Label(
            exclusion_frame,
            text="Le noir du masque d'exclusion cache les zones du masque de base.\nLe blanc du masque d'exclusion laisse apparaître le masque de base.",
            bg="white",
            fg="#455A64",
            font=('Helvetica', 9),
            justify="left",
            wraplength=600
        ).pack(anchor="w", pady=(0, 10))

        # Sélecteur masque de base
        base_mask_row = tk.Frame(exclusion_frame, bg="white")
        base_mask_row.pack(anchor="w", pady=5)
        tk.Label(
            base_mask_row,
            text="Masque de base (à filtrer):",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9),
            width=25,
            anchor="w"
        ).pack(side=tk.LEFT)
        self.combo_base_mask = ttk.Combobox(
            base_mask_row,
            textvariable=self.exclusion_base_mask,
            state="readonly",
            width=40,
            font=('Helvetica', 9)
        )
        self.combo_base_mask.pack(side=tk.LEFT, padx=(10, 0))

        # Sélecteur masque d'exclusion
        exclusion_mask_row = tk.Frame(exclusion_frame, bg="white")
        exclusion_mask_row.pack(anchor="w", pady=5)
        tk.Label(
            exclusion_mask_row,
            text="Masque d'exclusion (noir=cache):",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9),
            width=25,
            anchor="w"
        ).pack(side=tk.LEFT)
        self.combo_exclusion_mask = ttk.Combobox(
            exclusion_mask_row,
            textvariable=self.exclusion_mask_idx,
            state="readonly",
            width=40,
            font=('Helvetica', 9)
        )
        self.combo_exclusion_mask.pack(side=tk.LEFT, padx=(10, 0))

        # Info assemblage
        self.lbl_assembly_info = tk.Label(
            self.assembly_content,
            text="Sélectionnez une méthode et cliquez sur 'Assembler'.",
            bg="white",
            fg="#90A4AE",
            font=('Helvetica', 9, 'italic'),
            wraplength=600,
            justify="left"
        )
        self.lbl_assembly_info.pack(anchor="w", pady=(15, 0))

    def _build_overlay_content(self):
        """Construit le contenu de l'onglet Superposition."""
        self.overlay_content = tk.Frame(self.content_frame, bg="white")

        # Titre
        title_frame = tk.Frame(self.overlay_content, bg="white")
        title_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(
            title_frame,
            text="Superposition et analyse",
            font=('Helvetica', 14, 'bold'),
            bg="white",
            fg="#263238"
        ).pack(side=tk.LEFT)

        # Description
        tk.Label(
            self.overlay_content,
            text="Superpose les masques avec des couleurs différentes et analyse les zones de chevauchement.",
            bg="white",
            fg="#455A64",
            wraplength=600,
            justify="left"
        ).pack(anchor="w", pady=(0, 15))

        # Options
        options_frame = tk.LabelFrame(
            self.overlay_content,
            text="⚙️ Paramètres d'analyse",
            font=('Helvetica', 10, 'bold'),
            padx=15,
            pady=10,
            bg="white"
        )
        options_frame.pack(fill=tk.X, pady=(0, 15))

        threshold_row = tk.Frame(options_frame, bg="white")
        threshold_row.pack(anchor="w", pady=5)
        tk.Label(
            threshold_row,
            text="Seuil de conflit (0-1):",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9)
        ).pack(side=tk.LEFT, padx=(0, 10))
        self.entry_conflict_threshold = tk.Entry(
            threshold_row,
            textvariable=self.conflict_threshold_var,
            width=10,
            font=('Helvetica', 9)
        )
        self.entry_conflict_threshold.pack(side=tk.LEFT)
        tk.Label(
            threshold_row,
            text="(détection de chevauchement)",
            bg="white",
            fg="#90A4AE",
            font=('Helvetica', 8, 'italic')
        ).pack(side=tk.LEFT, padx=(10, 0))

        # Boutons d'action
        actions_frame = tk.Frame(self.overlay_content, bg="white")
        actions_frame.pack(anchor="w", pady=(10, 0))

        self.btn_preview_overlay = tk.Button(
            actions_frame,
            text="🎨 Aperçu superposition couleurs",
            command=self.preview_color_overlay,
            bg="#4CAF50",
            fg="white",
            activebackground="#388E3C",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_preview_overlay.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_process = tk.Button(
            actions_frame,
            text="🔍 Analyser chevauchement",
            command=self.analyze_overlap,
            bg="#FF5722",
            fg="white",
            activebackground="#D84315",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_process.pack(side=tk.LEFT)

        # Info
        self.lbl_conflict_info = tk.Label(
            self.overlay_content,
            text="Cliquez sur la carte de conflits pour voir les masques concernés.",
            bg="white",
            fg="#90A4AE",
            font=('Helvetica', 9, 'italic'),
            wraplength=600,
            justify="left"
        )
        self.lbl_conflict_info.pack(anchor="w", pady=(15, 0))

    def _build_processmask_content(self):
        """Construit le contenu de l'onglet ProcessMask."""
        self.processmask_content = tk.Frame(self.content_frame, bg="white")

        # Titre
        title_frame = tk.Frame(self.processmask_content, bg="white")
        title_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(
            title_frame,
            text="ProcessMask - Traitement Batch",
            font=('Helvetica', 14, 'bold'),
            bg="white",
            fg="#263238"
        ).pack(side=tk.LEFT)

        # Section Falloff Batch
        section_falloff = tk.LabelFrame(
            self.processmask_content,
            text="⚙ Traitement Batch - Falloff",
            font=('Helvetica', 10, 'bold'),
            bg="white",
            fg="#263238",
            relief=tk.GROOVE,
            bd=2,
            padx=15,
            pady=15
        )
        section_falloff.pack(fill=tk.X, pady=(0, 15))

        # Description
        desc_text = "Applique un falloff progressif aux bords de tous les masques chargés."
        tk.Label(
            section_falloff,
            text=desc_text,
            font=('Helvetica', 9),
            bg="white",
            fg="#555555"
        ).pack(anchor="w", pady=(0, 15))

        # Slider Falloff
        falloff_frame = tk.Frame(section_falloff, bg="white")
        falloff_frame.pack(fill=tk.X, pady=10)

        tk.Label(
            falloff_frame,
            text="Falloff (pixels):",
            font=('Helvetica', 9),
            bg="white",
            fg="#263238"
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.falloff_scale = tk.Scale(
            falloff_frame,
            from_=0,
            to=150,
            orient=tk.HORIZONTAL,
            variable=self.batch_falloff_var,
            bg="white",
            fg="#263238",
            relief=tk.FLAT,
            length=400
        )
        self.falloff_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_batch_falloff_value = tk.Label(
            falloff_frame,
            text=str(self.batch_falloff_var.get()),
            font=('Helvetica', 9, 'bold'),
            bg="white",
            fg="#2196F3"
        )
        self.lbl_batch_falloff_value.pack(side=tk.LEFT, padx=(10, 0))

        self.batch_falloff_var.trace('w', self._update_batch_falloff_label)

        # Section Noise Pattern
        noise_separator = tk.Frame(section_falloff, bg="#E0E0E0", height=2)
        noise_separator.pack(fill=tk.X, pady=15)

        noise_label = tk.Label(
            section_falloff,
            text="🎲 Noise Pattern",
            font=('Helvetica', 9, 'bold'),
            bg="white",
            fg="#263238"
        )
        noise_label.pack(anchor="w", pady=(0, 10))

        noise_desc = tk.Label(
            section_falloff,
            text="Ajoute variation aléatoire naturelle aux masques (Perlin noise).",
            font=('Helvetica', 9),
            bg="white",
            fg="#555555"
        )
        noise_desc.pack(anchor="w", pady=(0, 10))

        # Slider Noise intensity
        noise_frame = tk.Frame(section_falloff, bg="white")
        noise_frame.pack(fill=tk.X, pady=10)

        tk.Label(
            noise_frame,
            text="Intensité:",
            font=('Helvetica', 9),
            bg="white",
            fg="#263238"
        ).pack(side=tk.LEFT, padx=(0, 10))

        noise_scale = tk.Scale(
            noise_frame,
            from_=0.0,
            to=1.0,
            orient=tk.HORIZONTAL,
            variable=self.batch_noise_var,
            resolution=0.05,
            bg="white",
            fg="#263238",
            relief=tk.FLAT,
            length=400
        )
        self.noise_scale = noise_scale
        self.noise_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_batch_noise_value = tk.Label(
            noise_frame,
            text=f"{self.batch_noise_var.get():.2f}",
            font=('Helvetica', 9, 'bold'),
            bg="white",
            fg="#FF9800"
        )
        self.lbl_batch_noise_value.pack(side=tk.LEFT, padx=(10, 0))

        self.batch_noise_var.trace('w', self._update_batch_noise_label)

        # Section Sélection du type de matériau
        material_separator = tk.Frame(section_falloff, bg="#E0E0E0", height=2)
        material_separator.pack(fill=tk.X, pady=15)

        material_label = tk.Label(
            section_falloff,
            text="📦 Type de Matériau",
            font=('Helvetica', 9, 'bold'),
            bg="white",
            fg="#263238"
        )
        material_label.pack(anchor="w", pady=(0, 10))

        material_desc = tk.Label(
            section_falloff,
            text="Sélectionnez le type de matériau pour adapter les paramètres.",
            font=('Helvetica', 9),
            bg="white",
            fg="#555555"
        )
        material_desc.pack(anchor="w", pady=(0, 10))

        # Dropdown matériau type
        material_frame = tk.Frame(section_falloff, bg="white")
        material_frame.pack(fill=tk.X, pady=10)

        tk.Label(
            material_frame,
            text="Type:",
            font=('Helvetica', 9),
            bg="white",
            fg="#263238"
        ).pack(side=tk.LEFT, padx=(0, 10))

        material_options = list(self.material_types.keys())
        self.material_dropdown = ttk.Combobox(
            material_frame,
            textvariable=self.batch_material_type_var,
            values=material_options,
            state="readonly",
            font=('Helvetica', 9),
            width=25
        )
        self.material_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.batch_material_type_var.trace('w', self._on_material_type_changed)

        # Boutons d'action
        buttons_frame = tk.Frame(section_falloff, bg="white")
        buttons_frame.pack(fill=tk.X, pady=(15, 0))

        self.btn_preview_batch_falloff = tk.Button(
            buttons_frame,
            text="👁 Prévisualiser",
            command=self.preview_batch_falloff,
            bg="#7E57C2",
            fg="white",
            font=('Helvetica', 9, 'bold'),
            relief=tk.FLAT,
            cursor="hand2",
            padx=15,
            pady=8
        )
        self.btn_preview_batch_falloff.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_apply_batch_falloff = tk.Button(
            buttons_frame,
            text="⚡ Appliquer (batch)",
            command=self.apply_batch_falloff,
            bg="#FF9800",
            fg="white",
            font=('Helvetica', 9, 'bold'),
            relief=tk.FLAT,
            cursor="hand2",
            padx=15,
            pady=8
        )
        self.btn_apply_batch_falloff.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_export_batch_falloff = tk.Button(
            buttons_frame,
            text="💾 Exporter",
            command=self.export_batch_falloff,
            bg="#4CAF50",
            fg="white",
            font=('Helvetica', 9, 'bold'),
            relief=tk.FLAT,
            cursor="hand2",
            padx=15,
            pady=8
        )
        self.btn_export_batch_falloff.pack(side=tk.LEFT)

    def _build_reforger_content(self):
        """Construit le contenu de l'onglet ARMA Reforger."""
        self.reforger_content = tk.Frame(self.content_frame, bg="white")

        # Titre
        title_frame = tk.Frame(self.reforger_content, bg="white")
        title_frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(
            title_frame,
            text="ARMA Reforger - QTRE vs Erreurs",
            font=('Helvetica', 14, 'bold'),
            bg="white",
            fg="#263238"
        ).pack(side=tk.LEFT)

        # Description
        tk.Label(
            self.reforger_content,
            text="Compare les conflits détectés par QTRE avec les erreurs réelles du Workbench Reforger.",
            bg="white",
            fg="#455A64",
            wraplength=600,
            justify="left"
        ).pack(anchor="w", pady=(0, 15))

        # Section 1: Chargement erreurs
        load_frame = tk.LabelFrame(
            self.reforger_content,
            text="📂 Chargement des erreurs Reforger",
            font=('Helvetica', 10, 'bold'),
            padx=15,
            pady=10,
            bg="white"
        )
        load_frame.pack(fill=tk.X, pady=(0, 15))

        self.btn_load_reforger_errors = tk.Button(
            load_frame,
            text="▶ Charger masques erreur Reforger",
            command=self.load_reforger_error_masks,
            bg="#00838F",
            fg="white",
            activebackground="#006064",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_load_reforger_errors.pack(anchor="w")

        # Section 2: Analyse
        analysis_frame = tk.LabelFrame(
            self.reforger_content,
            text="🔬 Analyse et visualisation",
            font=('Helvetica', 10, 'bold'),
            padx=15,
            pady=10,
            bg="white"
        )
        analysis_frame.pack(fill=tk.X, pady=(0, 15))

        param_row = tk.Frame(analysis_frame, bg="white")
        param_row.pack(anchor="w", pady=(0, 10))
        tk.Label(
            param_row,
            text="Mètres par pixel:",
            bg="white",
            fg="#263238",
            font=('Helvetica', 9)
        ).pack(side=tk.LEFT, padx=(0, 10))
        self.entry_meters_per_pixel = tk.Entry(
            param_row,
            textvariable=self.meters_per_pixel_var,
            width=10,
            font=('Helvetica', 9)
        )
        self.entry_meters_per_pixel.pack(side=tk.LEFT)

        btn_row1 = tk.Frame(analysis_frame, bg="white")
        btn_row1.pack(anchor="w", pady=(0, 5))

        self.btn_overlay_qtre_reforger = tk.Button(
            btn_row1,
            text="🔥 Générer heatmap combinée",
            command=self.overlay_qtre_with_reforger,
            bg="#AD1457",
            fg="white",
            activebackground="#880E4F",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_overlay_qtre_reforger.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_export_qtre_combined = tk.Button(
            btn_row1,
            text="💾 Exporter heatmap",
            command=self.export_qtre_combined_heatmap,
            bg="#2E7D32",
            fg="white",
            activebackground="#1B5E20",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_export_qtre_combined.pack(side=tk.LEFT)

        btn_row2 = tk.Frame(analysis_frame, bg="white")
        btn_row2.pack(anchor="w")

        self.btn_list_cyan_coords = tk.Button(
            btn_row2,
            text="📍 Lister zones cyan (m)",
            command=self.export_cyan_zones_coordinates,
            bg="#455A64",
            fg="white",
            activebackground="#263238",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_list_cyan_coords.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_fix_reforger_errors = tk.Button(
            btn_row2,
            text="✂️ Corriger zones magenta",
            command=self.correct_reforger_error_zones,
            bg="#6D4C41",
            fg="white",
            activebackground="#4E342E",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            cursor="hand2",
            relief=tk.FLAT,
            state=tk.DISABLED,
            pady=5
        )
        self.btn_fix_reforger_errors.pack(side=tk.LEFT)

        # Info
        self.lbl_qtre_info = tk.Label(
            self.reforger_content,
            text="Chargez d'abord les masques QTRE, puis les masques erreur Reforger.",
            bg="white",
            fg="#90A4AE",
            font=('Helvetica', 9, 'italic'),
            wraplength=600,
            justify="left"
        )
        self.lbl_qtre_info.pack(anchor="w", pady=(15, 0))

    def _build_log_frame(self, parent):
        """Zone de log pour l'historique des opérations."""
        log_container = tk.LabelFrame(
            parent,
            text="📋 Journal des opérations",
            font=('Helvetica', 9, 'bold'),
            bg="white",
            fg="#263238",
            padx=5,
            pady=5
        )
        log_container.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 10))

        # Frame pour le texte + scrollbar
        log_frame = tk.Frame(log_container, bg="white")
        log_frame.pack(fill=tk.X)

        # Scrollbar
        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Widget Text pour le log
        self.log_text = tk.Text(
            log_frame,
            height=6,
            width=80,
            bg="#FAFAFA",
            fg="#263238",
            font=('Consolas', 9),
            wrap=tk.WORD,
            yscrollcommand=scrollbar.set,
            relief=tk.FLAT,
            state=tk.DISABLED
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

        # Bouton pour effacer le log
        clear_btn = tk.Button(
            log_container,
            text="🗑️ Effacer log",
            command=self._clear_log,
            bg="#607D8B",
            fg="white",
            activebackground="#455A64",
            activeforeground="white",
            font=('Helvetica', 8),
            cursor="hand2",
            relief=tk.FLAT,
            pady=2
        )
        clear_btn.pack(anchor="e", pady=(5, 0))

        # Message de bienvenue
        self._log("✅ Application démarrée - Chargez des masques PNG pour commencer")

    def _log(self, message):
        """Ajoute un message au log avec timestamp."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear_log(self):
        """Efface le contenu du log."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self._log("🗑️ Log effacé")

    def _build_plot_frame(self, parent):
        """Zone d'affichage des graphiques."""
        self.plot_frame = tk.Frame(parent, bg="#F5F5F5")
        self.plot_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10)

    # ========================================================================
    # GESTION DES ONGLETS
    # ========================================================================

    def _show_corrections_tab(self):
        """Affiche l'onglet Corrections."""
        self._hide_all_contents()
        self.corrections_content.pack(fill=tk.BOTH, expand=True)
        self._set_active_tab(self.btn_tab_corrections)

    def _show_assembly_tab(self):
        """Affiche l'onglet Assemblage."""
        self._hide_all_contents()
        self.assembly_content.pack(fill=tk.BOTH, expand=True)
        self._set_active_tab(self.btn_tab_assembly)

    def _show_overlay_tab(self):
        """Affiche l'onglet Superposition."""
        self._hide_all_contents()
        self.overlay_content.pack(fill=tk.BOTH, expand=True)
        self._set_active_tab(self.btn_tab_overlay)

    def _show_processmask_tab(self):
        """Affiche l'onglet ProcessMask."""
        self._hide_all_contents()
        self.processmask_content.pack(fill=tk.BOTH, expand=True)
        self._set_active_tab(self.btn_tab_processmask)

    def _show_reforger_tab(self):
        """Affiche l'onglet ARMA Reforger."""
        self._hide_all_contents()
        self.reforger_content.pack(fill=tk.BOTH, expand=True)
        self._set_active_tab(self.btn_tab_reforger)

    def _hide_all_contents(self):
        """Masque tous les contenus d'onglets."""
        for content in [self.corrections_content, self.assembly_content,
                        self.overlay_content, self.processmask_content, self.reforger_content]:
            content.pack_forget()

    # ========================================================================
    # CONVERSION NOIR & BLANC AVEC FALLOFF
    # ========================================================================

    def _update_bw_threshold_label(self, *args):
        """Met à jour le label du threshold."""
        self.lbl_bw_threshold_value.config(text=str(self.bw_threshold_var.get()))

    def _update_bw_falloff_label(self, *args):
        """Met à jour le label du falloff."""
        self.lbl_bw_falloff_value.config(text=str(self.bw_falloff_var.get()))

    def analyze_and_suggest_threshold(self):
        """Analyse le masque et suggère un seuil optimal."""
        if not self.masks:
            messagebox.showwarning("Analyse impossible", "Chargez au moins 1 masque.")
            return

        self._log("📊 Analyse du masque en cours...")

        # Analyser le premier masque
        analysis = analyze_mask_histogram(self.masks[0])
        stats = analysis['stats']
        suggested = analysis['suggested_threshold']
        reason = analysis['suggestion_reason']

        # Afficher l'histogramme avec le seuil suggéré
        self._clear_plot()

        self.fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(13, 9))
        self.fig.patch.set_facecolor('#F0F0F0')

        # Original
        ax1.imshow(self.masks[0], cmap='gray', vmin=0, vmax=65535)
        ax1.set_title("Original (uint16)", fontsize=10, fontweight='bold')
        ax1.axis('off')

        # Histogramme
        ax2.bar(analysis['bins'][:-1], analysis['histogram'], width=1, color='steelblue', alpha=0.7)
        ax2.axvline(suggested, color='red', linewidth=2, linestyle='--', label=f'Seuil suggéré: {suggested}')
        ax2.axvline(stats['p10'], color='orange', linewidth=1, linestyle=':', label=f"P10: {stats['p10']:.0f}")
        ax2.axvline(stats['median'], color='green', linewidth=1, linestyle=':', label=f"Médiane: {stats['median']:.0f}")
        ax2.axvline(stats['p90'], color='purple', linewidth=1, linestyle=':', label=f"P90: {stats['p90']:.0f}")
        ax2.set_title("Histogramme (0-255)", fontsize=10, fontweight='bold')
        ax2.set_xlabel("Valeur")
        ax2.set_ylabel("Nombre de pixels")
        ax2.legend(fontsize=8)
        ax2.grid(True, alpha=0.3)

        # Stats
        stats_text = (
            f"📊 Statistiques\n\n"
            f"Min: {stats['min']}\n"
            f"Max: {stats['max']}\n"
            f"Moyenne: {stats['mean']:.1f}\n"
            f"Médiane: {stats['median']:.1f}\n\n"
            f"P10: {stats['p10']:.1f}\n"
            f"P25: {stats['p25']:.1f}\n"
            f"P75: {stats['p75']:.1f}\n"
            f"P90: {stats['p90']:.1f}\n\n"
            f"Pixels non-zéro:\n{stats['non_zero_percent']:.1f}%\n\n"
            f"✨ Seuil suggéré:\n{suggested}\n\n"
            f"Raison:\n{reason}"
        )
        ax3.text(0.1, 0.5, stats_text, fontsize=9, verticalalignment='center',
                 family='monospace', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        ax3.axis('off')

        # Aperçu avec seuil suggéré
        preview_suggested = convert_to_bw_with_falloff(self.masks[0], suggested, self.bw_falloff_var.get())
        ax4.imshow(preview_suggested, cmap='gray', vmin=0, vmax=65535)
        ax4.set_title(f"Aperçu avec seuil suggéré ({suggested})", fontsize=10, fontweight='bold')
        ax4.axis('off')

        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Proposer d'appliquer le seuil suggéré
        apply_suggestion = messagebox.askyesno(
            "Seuil suggéré",
            f"Seuil suggéré: {suggested}\n\n"
            f"Raison: {reason}\n\n"
            f"Voulez-vous appliquer ce seuil ?",
            icon='question'
        )

        if apply_suggestion:
            self.bw_threshold_var.set(suggested)
            self._log(f"✅ Seuil suggéré appliqué: {suggested} - {reason}")
        else:
            self._log(f"ℹ️ Seuil suggéré: {suggested} (non appliqué)")

    def preview_bw_conversion(self):
        """Prévisualise la conversion N&B sur le premier masque."""
        if not self.masks:
            messagebox.showwarning("Aperçu impossible", "Chargez au moins 1 masque.")
            return

        threshold = self.bw_threshold_var.get()
        falloff = self.bw_falloff_var.get()

        self._log(f"👁 Aperçu conversion N&B - Seuil: {threshold}, Falloff: {falloff} px")

        # Convertir le premier masque
        original = self.masks[0]
        converted = convert_to_bw_with_falloff(original, threshold, falloff)
        self.bw_preview_mask = converted

        # Affichage comparatif
        self._clear_plot()

        self.fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
        self.fig.patch.set_facecolor('#F0F0F0')

        ax1.imshow(original, cmap='gray', vmin=0, vmax=65535)
        ax1.set_title("Original (uint16)", fontsize=10, fontweight='bold')
        ax1.axis('off')

        ax2.imshow(converted, cmap='gray', vmin=0, vmax=65535)
        ax2.set_title(
            f"Noir & Blanc + Falloff\nSeuil: {threshold} | Falloff: {falloff} px",
            fontsize=10,
            fontweight='bold'
        )
        ax2.axis('off')

        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.pack(fill=tk.BOTH, expand=True)

        self._log(f"✅ Aperçu N&B affiché - {Path(self.mask_paths[0]).name}")

        # Forcer l'update de l'interface
        self.root.update_idletasks()

    def apply_bw_batch(self):
        """Applique la conversion N&B à tous les masques chargés."""
        if not self.masks:
            messagebox.showwarning("Application impossible", "Chargez au moins 1 masque.")
            return

        threshold = self.bw_threshold_var.get()
        falloff = self.bw_falloff_var.get()

        self._log(f"⚡ Application batch N&B - {len(self.masks)} masque(s) - Seuil: {threshold}, Falloff: {falloff} px")

        # Convertir tous les masques
        converted_masks = []
        for idx, mask in enumerate(self.masks):
            converted = convert_to_bw_with_falloff(mask, threshold, falloff)
            converted_masks.append(converted)
            self._log(f"  → {Path(self.mask_paths[idx]).name} converti")

        self.bw_processed_masks = converted_masks
        self.btn_bw_export.config(state=tk.NORMAL)

        self._log(f"✅ Batch terminé - {len(converted_masks)} masque(s) converti(s)")
        messagebox.showinfo(
            "Batch terminé",
            f"{len(converted_masks)} masque(s) converti(s) en N&B avec falloff.\n\n"
            f"Cliquez sur 'Exporter' pour sauvegarder les résultats."
        )

    def export_bw_masks(self):
        """Exporte les masques N&B convertis."""
        if not self.bw_processed_masks:
            messagebox.showwarning("Export impossible", "Aucun masque N&B à exporter.")
            return

        output_dir = filedialog.askdirectory(
            title="Choisir le dossier de sortie des masques N&B",
            initialdir=str(self.default_mask_dir)
        )
        if not output_dir:
            return

        output_dir = Path(output_dir)
        saved_files = []

        for idx, converted_mask in enumerate(self.bw_processed_masks):
            original_name = Path(self.mask_paths[idx]).stem
            out_path = self._unique_output_path(output_dir, f"{original_name}_bw", ".png")

            ok = cv2.imwrite(str(out_path), converted_mask)
            if ok:
                saved_files.append(out_path.name)

        if not saved_files:
            messagebox.showerror("Export", "Aucun fichier n'a été écrit.")
            return

        self.lbl_status.config(text=f"Export N&B:\n{len(saved_files)} masque(s)")
        self._log(f"💾 Export N&B réussi - {len(saved_files)} masque(s) vers {output_dir.name}")

        messagebox.showinfo(
            "Export terminé",
            f"{len(saved_files)} masque(s) N&B exporté(s).\n\n"
            f"Dossier: {output_dir}\n\n"
            f"Exemple: {saved_files[0]}"
        )

    # ========================================================================
    # TRAITEMENT BATCH FALLOFF
    # ========================================================================

    def _update_batch_falloff_label(self, *args):
        """Met à jour le label du falloff batch."""
        self.lbl_batch_falloff_value.config(text=str(self.batch_falloff_var.get()))

    def _update_batch_noise_label(self, *args):
        """Met à jour le label du noise batch."""
        self.lbl_batch_noise_value.config(text=f"{self.batch_noise_var.get():.2f}")

    def _on_material_type_changed(self, *args):
        """Callback quand le type de matériau change — active/désactive les sliders."""
        material_type = self.batch_material_type_var.get()

        if material_type == "None":
            # Mode libre : activer les sliders
            self.falloff_scale.config(state=tk.NORMAL)
            self.noise_scale.config(state=tk.NORMAL)
            self._log(f"Mode libre — utilisez les sliders pour paramétrer")
        else:
            # Mode type : désactiver les sliders, charger les params du type
            params = self.material_types.get(material_type, self.material_types["Default"])

            # Désactiver les sliders
            self.falloff_scale.config(state=tk.DISABLED)
            self.noise_scale.config(state=tk.DISABLED)

            # Mettre à jour les valeurs (optionnel, pour affichage)
            blur_radius = params.get("blur_radius", 10)
            noise_amp = params.get("noise_amplitude", 0.15)
            min_visible = params.get("min_visible", 0.161)

            self._log(f"Type [{material_type}] — Falloff={blur_radius}px, Noise=±{noise_amp*100:.0f}%, Seuil={min_visible*31:.0f}/31")

    def _generate_perlin_noise(self, shape, scale=50, intensity=0.15):
        """Génère du Perlin-like noise (simplifié avec gaussian blur)."""
        h, w = shape
        # Créer du bruit aléatoire
        noise = np.random.randn(h, w).astype(np.float32)
        # Appliquer un blur gaussien pour lisser (effet Perlin-like)
        from scipy.ndimage import gaussian_filter
        noise_smooth = gaussian_filter(noise, sigma=scale)
        # Normaliser en [-1, 1]
        noise_min = noise_smooth.min()
        noise_max = noise_smooth.max()
        if noise_max > noise_min:
            noise_norm = (noise_smooth - noise_min) / (noise_max - noise_min) * 2 - 1  # [-1, 1]
        else:
            noise_norm = np.zeros_like(noise_smooth)
        # Convertir en [-65535*intensity, 65535*intensity]
        noise_scaled = (noise_norm * 65535 * intensity).astype(np.float32)
        return noise_scaled

    def _apply_noise_to_mask(self, mask_uint16, noise_intensity=0.15):
        """Applique du noise à un masque, mais SEULEMENT où le masque a des valeurs (pas sur le noir)."""
        if noise_intensity <= 0:
            return mask_uint16

        noise = self._generate_perlin_noise(mask_uint16.shape, scale=50, intensity=noise_intensity)

        # Convertir mask en float pour calcul
        mask_float = mask_uint16.astype(np.float32)

        # Créer un "mask weight" : le bruit s'applique proportionnellement à la valeur du masque
        # Zones noires (0) = pas de bruit
        # Zones blanches (65535) = bruit maximal
        mask_weight = mask_float / 65535.0  # Normaliser en [0, 1]

        # Appliquer le bruit modulé par le poids
        noise_modulated = noise * mask_weight  # Bruit diminue vers les zones noires

        # Ajouter au masque et clipper
        result = np.clip(mask_float + noise_modulated, 0, 65535)
        return result.astype(np.uint16)

    def _apply_edge_falloff_to_mask(self, mask_uint16, falloff_pixels=40):
        """Applique falloff SEULEMENT sur les bords du masque, préserve les zones blanches."""
        from scipy.ndimage import distance_transform_edt

        # Créer masque binaire (blanc = non-zéro, noir = zéro)
        binary_mask = (mask_uint16 > 0).astype(np.uint8)

        # Détecter les pixels de bordure (distance du bord intérieur)
        distance = distance_transform_edt(binary_mask).astype(np.float32)

        # Créer une courbe de falloff : loin du bord = 1.0, près du bord = diminue
        falloff_distance = falloff_pixels
        falloff_curve = np.clip(distance / falloff_distance, 0, 1.0)

        # Appliquer le falloff : zones centrales restent 65535, bords diminuent progressivement
        result = (mask_uint16.astype(np.float32) * falloff_curve).astype(np.uint16)

        return result

    def _apply_enfusion_threshold(self, mask_uint16, material_type="Default"):
        """Applique le seuil minimal Enfusion selon le type de matériau."""
        params = self.material_types.get(material_type, self.material_types["Default"])
        min_visible = params.get("min_visible", 5/31)

        # Convertir min_visible (0-1 normalized) en uint16
        threshold_uint16 = int(min_visible * 65535)
        result = mask_uint16.copy()
        result[result < threshold_uint16] = 0
        return result

    def _preview_edge_falloff_and_noise(self, mask_uint16, falloff_pixels=40, noise_intensity=0.15, material_type="Default"):
        """Combine edge falloff + noise + seuil Enfusion adapté au matériau."""
        # Appliquer falloff sur bords
        with_falloff = self._apply_edge_falloff_to_mask(mask_uint16, falloff_pixels)
        # Appliquer noise
        if noise_intensity > 0:
            result = self._apply_noise_to_mask(with_falloff, noise_intensity=noise_intensity)
        else:
            result = with_falloff
        # Appliquer seuil minimal Enfusion selon type matériau
        result = self._apply_enfusion_threshold(result, material_type=material_type)
        return result

    def preview_batch_falloff(self):
        """Prévisualise le falloff sur le premier masque."""
        if not self.masks:
            messagebox.showwarning("Aperçu impossible", "Chargez au moins 1 masque.")
            return

        material_type = self.batch_material_type_var.get()

        # Récupérer les params selon le type
        if material_type == "None":
            # Mode libre : utiliser les sliders
            falloff = self.batch_falloff_var.get()
            noise_intensity = self.batch_noise_var.get()
        else:
            # Mode type : ignorer les sliders, utiliser les params du type
            params = self.material_types.get(material_type, self.material_types["Default"])
            falloff = params.get("blur_radius", 10)
            noise_intensity = params.get("noise_amplitude", 0.15)

        self._log(f"👁 Aperçu [{material_type}] - Falloff: {falloff} px, Noise: {noise_intensity:.2f}")

        # Convertir le premier masque avec falloff
        original = self.masks[0]
        converted = self._preview_edge_falloff_and_noise(original, falloff_pixels=falloff, noise_intensity=noise_intensity, material_type=material_type)

        # Affichage comparatif
        self._clear_plot()

        self.fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
        self.fig.patch.set_facecolor('#F0F0F0')

        ax1.imshow(original, cmap='gray', vmin=0, vmax=65535)
        ax1.set_title("Original (quasi-binaire)", fontsize=10, fontweight='bold')
        ax1.axis('off')

        ax2.imshow(converted, cmap='gray', vmin=0, vmax=65535)
        ax2.set_title(f"Falloff + Noise [{material_type}]\nFalloff: {falloff} px | Noise: {noise_intensity:.2f}", fontsize=10, fontweight='bold')
        ax2.axis('off')

        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def apply_batch_falloff(self):
        """Applique edge falloff + noise à tous les masques chargés."""
        if not self.masks:
            messagebox.showwarning("Application impossible", "Chargez au moins 1 masque.")
            return

        material_type = self.batch_material_type_var.get()

        # Récupérer les params selon le type
        if material_type == "None":
            # Mode libre : utiliser les sliders
            falloff = self.batch_falloff_var.get()
            noise_intensity = self.batch_noise_var.get()
        else:
            # Mode type : ignorer les sliders, utiliser les params du type
            params = self.material_types.get(material_type, self.material_types["Default"])
            falloff = params.get("blur_radius", 10)
            noise_intensity = params.get("noise_amplitude", 0.15)

        self._log(f"⚡ Application [{material_type}] batch à {len(self.masks)} masque(s) - Falloff: {falloff} px, Noise: {noise_intensity:.2f}")

        self.batch_falloff_preview_masks = []

        for idx, mask in enumerate(self.masks):
            # Appliquer edge falloff + noise avec type matériau
            converted = self._preview_edge_falloff_and_noise(
                mask,
                falloff_pixels=falloff,
                noise_intensity=noise_intensity,
                material_type=material_type
            )
            self.batch_falloff_preview_masks.append(converted)

        self._log(f"✅ Traitement batch [{material_type}] terminé - {len(self.batch_falloff_preview_masks)} masque(s) prêt(s)")
        messagebox.showinfo(
            "Traitement terminé",
            f"Traitement [{material_type}] appliqué à {len(self.batch_falloff_preview_masks)} masque(s).\n\n"
            f"Vous pouvez maintenant exporter les masques traités."
        )

    def export_batch_falloff(self):
        """Exporte les masques traités avec falloff+noise."""
        if not self.batch_falloff_preview_masks:
            messagebox.showwarning("Export impossible", "Aucun masque traité à exporter.")
            return

        output_dir = filedialog.askdirectory(
            title="Choisir le dossier de sortie des masques traités",
            initialdir=str(self.default_mask_dir)
        )
        if not output_dir:
            return

        output_dir = Path(output_dir)
        saved_files = []

        for idx, converted_mask in enumerate(self.batch_falloff_preview_masks):
            original_name = Path(self.mask_paths[idx]).stem
            out_path = self._unique_output_path(output_dir, f"{original_name}_processed", ".png")

            ok = cv2.imwrite(str(out_path), converted_mask)
            if ok:
                saved_files.append(out_path.name)

        if not saved_files:
            messagebox.showerror("Export", "Aucun fichier n'a été écrit.")
            return

        self.lbl_status.config(text=f"Export Traitement:\n{len(saved_files)} masque(s)")
        self._log(f"💾 Export traitement réussi - {len(saved_files)} masque(s) vers {output_dir.name}")

        messagebox.showinfo(
            "Export terminé",
            f"{len(saved_files)} masque(s) avec falloff+noise exporté(s).\n\n"
            f"Dossier: {output_dir}\n\n"
            f"Exemple: {saved_files[0]}"
        )

    # ========================================================================
    # GESTION DES MASQUES (CHARGEMENT / RESET)
    # ========================================================================

    def reset_masks(self):
        """Réinitialise tous les masques et l'interface."""
        # Ne réinitialiser que les données de masques, pas les préférences utilisateur
        self.mask_paths = []
        self.masks = []
        self.mask_stack = None
        self.cleaned_masks = None
        self.assembled_mask = None
        self.ordered_indices = []

        # Masques erreur Reforger
        self.reforger_error_mask_paths = []
        self.reforger_error_masks = []
        self.reforger_error_combined = None
        self.qtre_combined_heatmap = None
        self.cyan_mask = None

        # Masques N&B
        self.bw_preview_mask = None
        self.bw_processed_masks = None

        # Masques traitement batch falloff
        self.batch_falloff_preview_masks = None

        # Ne PAS réinitialiser les préférences utilisateur :
        # - self.assembly_mode (conserve le choix de l'utilisateur)
        # - self.blend_mode_var
        # - self.conflict_threshold_var
        # - self.bw_threshold_var
        # - self.bw_falloff_var
        # etc.

        self._update_ui_after_reset()
        self._clear_plot()
        self._log("🔄 Réinitialisation des masques effectuée (préférences conservées)")

    def _update_ui_after_reset(self):
        """Met à jour l'interface après reset."""
        # Boutons
        self.btn_process.config(state=tk.DISABLED)
        self.btn_preview_cleanup.config(state=tk.DISABLED)
        self.btn_export_cleanup.config(state=tk.DISABLED)
        self.btn_preview_overlay.config(state=tk.DISABLED)
        self.btn_assemble.config(state=tk.DISABLED)
        self.btn_export_assembled_separate.config(state=tk.DISABLED)
        self.btn_load_reforger_errors.config(state=tk.DISABLED)
        self.btn_overlay_qtre_reforger.config(state=tk.DISABLED)
        self.btn_export_qtre_combined.config(state=tk.DISABLED)
        self.btn_list_cyan_coords.config(state=tk.DISABLED)
        self.btn_fix_reforger_errors.config(state=tk.DISABLED)

        # Boutons N&B
        self.btn_bw_analyze.config(state=tk.DISABLED)
        self.btn_bw_preview.config(state=tk.DISABLED)
        self.btn_bw_apply_batch.config(state=tk.DISABLED)
        self.btn_bw_export.config(state=tk.DISABLED)

        # Labels
        self.lbl_status.config(text="Aucun masque\nchargé")
        self.lbl_order_info.config(text="Ordre actuel: aucun masque chargé", bg="white", fg="#455A64")
        self.lbl_conflict_info.config(text="Cliquez sur la carte de conflits pour voir les masques concernés.", bg="white", fg="#90A4AE")
        self.lbl_assembly_info.config(text="Sélectionnez une méthode et cliquez sur 'Assembler'.", bg="white", fg="#90A4AE")
        self.lbl_qtre_info.config(text="Chargez d'abord les masques QTRE, puis les masques erreur Reforger.", bg="white", fg="#90A4AE")

    def load_masks(self):
        """Ouvre un dialogue pour charger les masques."""
        file_paths = filedialog.askopenfilenames(
            initialdir=str(self.default_mask_dir),
            filetypes=[("Masques PNG 16-bit", "*.png")]
        )
        if not file_paths:
            return

        self._load_masks_from_paths(list(file_paths))

    def _load_masks_from_paths(self, file_paths):
        """Charge les masques depuis une liste de chemins."""
        if not file_paths:
            return

        self.default_mask_dir = Path(file_paths[0]).parent

        loaded_masks = []
        loaded_paths = []
        errors = []
        warnings = []
        ref_shape = None

        for path in file_paths:
            mask = self._read_png_unicode_safe(path)
            file_name = Path(path).name

            if mask is None:
                errors.append(f"{file_name}: lecture impossible")
                continue

            # Détection float32 et proposition de conversion
            if mask.dtype == np.float32:
                response = messagebox.askyesno(
                    "Masque float32 détecté",
                    f"Le fichier '{file_name}' est en float32 (probablement export Gaea).\n\n"
                    f"Voulez-vous le convertir en uint16 PNG et le sauvegarder ?\n\n"
                    f"Le fichier original sera renommé avec '_original' et le nouveau fichier "
                    f"uint16 sera créé.",
                    icon='question'
                )

                if response:
                    try:
                        # Conversion float32 → uint16
                        converted_mask, _ = convert_float32_to_uint16(path)
                        if converted_mask is not None:
                            # Renommer l'original
                            original_backup = Path(path).parent / f"{Path(path).stem}_original{Path(path).suffix}"
                            if not original_backup.exists():
                                Path(path).rename(original_backup)

                            mask = converted_mask
                            warnings.append(f"{file_name}: converti float32 → uint16 et sauvegardé")
                            self._log(f"🔧 {file_name} converti float32 → uint16 PNG")
                        else:
                            errors.append(f"{file_name}: conversion float32 échouée")
                            continue
                    except Exception as exc:
                        errors.append(f"{file_name}: erreur conversion float32 ({exc})")
                        continue
                else:
                    errors.append(f"{file_name}: float32 ignoré (conversion refusée)")
                    continue

            # Conversion automatique RGB/RGBA -> niveaux de gris
            if mask.ndim == 3:
                if mask.shape[2] == 3:
                    mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
                    warnings.append(f"{file_name}: converti RGB -> niveaux de gris")
                elif mask.shape[2] == 4:
                    mask = cv2.cvtColor(mask, cv2.COLOR_BGRA2GRAY)
                    warnings.append(f"{file_name}: converti RGBA -> niveaux de gris")
                else:
                    errors.append(f"{file_name}: format couleur non supporté ({mask.shape[2]} canaux)")
                    continue

            if mask.ndim != 2:
                errors.append(f"{file_name}: image non mono-canal")
                continue

            if mask.dtype == np.uint8:
                mask = (mask.astype(np.uint16) * 257)
                warnings.append(f"{file_name}: converti de uint8 vers uint16")
            elif mask.dtype != np.uint16:
                errors.append(f"{file_name}: format {mask.dtype} (attendu: uint16 ou uint8)")
                continue

            # Auto-correction dimensions : redimensionner si nécessaire
            if ref_shape is None:
                ref_shape = mask.shape
            elif mask.shape != ref_shape:
                # Redimensionner automatiquement vers la taille de référence
                target_w, target_h = ref_shape[1], ref_shape[0]
                mask_resized = cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
                warnings.append(f"{file_name}: redimensionné {mask.shape[1]}x{mask.shape[0]} → {target_w}x{target_h}")
                self._log(f"🔧 {file_name} redimensionné automatiquement vers {target_w}x{target_h}")
                mask = mask_resized

            loaded_masks.append(mask)
            loaded_paths.append(path)

        if len(loaded_masks) < 1:
            messagebox.showwarning(
                "Aucun masque valide",
                "Aucun masque valide n'a pu être chargé.\n\nDétails:\n- " + "\n- ".join(errors[:10]) if errors else "Aucun fichier sélectionné."
            )
            return

        self._finalize_mask_loading(loaded_masks, loaded_paths, errors, warnings)


    def _finalize_mask_loading(self, loaded_masks, loaded_paths, errors, warnings):
        """Finalise le chargement des masques."""
        self.mask_paths = loaded_paths
        self.masks = loaded_masks
        self.cleaned_masks = None
        self.assembled_mask = None
        self.reforger_error_mask_paths = []
        self.reforger_error_masks = []
        self.reforger_error_combined = None
        self.qtre_combined_heatmap = None
        self.cyan_mask = None

        # Mise à jour des listes déroulantes pour l'exclusion
        self._update_exclusion_mask_lists()

        # Activation des boutons selon le nombre de masques
        single_mask_mode = (len(self.masks) == 1)

        # Boutons disponibles avec 1 seul masque : aucun (nécessite au moins 2 masques)
        # Boutons nécessitant 2+ masques
        self.btn_process.config(state=tk.DISABLED if single_mask_mode else tk.NORMAL)
        self.btn_preview_cleanup.config(state=tk.DISABLED if single_mask_mode else tk.NORMAL)
        self.btn_export_cleanup.config(state=tk.DISABLED)
        self.btn_preview_overlay.config(state=tk.DISABLED if single_mask_mode else tk.NORMAL)
        self.btn_assemble.config(state=tk.DISABLED if single_mask_mode else tk.NORMAL)
        self.btn_export_assembled_separate.config(state=tk.DISABLED)

        # QTRE disponible même avec 1 masque (si on a des erreurs Reforger)
        self.btn_load_reforger_errors.config(state=tk.NORMAL)
        self.btn_overlay_qtre_reforger.config(state=tk.DISABLED)
        self.btn_export_qtre_combined.config(state=tk.DISABLED)
        self.btn_list_cyan_coords.config(state=tk.DISABLED)
        self.btn_fix_reforger_errors.config(state=tk.DISABLED)

        # Conversion N&B disponible avec 1+ masque
        self.btn_bw_analyze.config(state=tk.NORMAL)
        self.btn_bw_preview.config(state=tk.NORMAL)
        self.btn_bw_apply_batch.config(state=tk.NORMAL)
        self.btn_bw_export.config(state=tk.DISABLED)

        mask_word = "masque" if len(self.masks) == 1 else "masques"
        self.lbl_status.config(
            text=f"{len(self.masks)} {mask_word}\nchargé{'s' if len(self.masks) > 1 else ''}\n{self.masks[0].shape[1]}x{self.masks[0].shape[0]} px"
        )
        self._update_order_label()

        if len(self.masks) == 1:
            self.lbl_qtre_info.config(
                text="1 seul masque chargé. Les fonctions de comparaison nécessitent 2+ masques.",
                bg="white",
                fg="#FF6F00"
            )
        else:
            self.lbl_qtre_info.config(
                text="Masques chargés. Chargez maintenant les masques erreur Reforger.",
                bg="white",
                fg="#1565C0"
            )

        if errors:
            messagebox.showinfo("Fichiers ignorés", "Certains fichiers ont été ignorés:\n- " + "\n- ".join(errors[:10]))
            self._log(f"⚠️ {len(errors)} fichier(s) ignoré(s)")
        if warnings:
            messagebox.showinfo("Conversions appliquées", "Conversions automatiques:\n- " + "\n- ".join(warnings[:10]))
            self._log(f"🔄 {len(warnings)} conversion(s) appliquée(s)")

        self._log(f"📂 {len(self.masks)} masque(s) chargé(s) - {self.masks[0].shape[1]}x{self.masks[0].shape[0]} px")

        if len(self.masks) == 1:
            self._log("ℹ️ Mode 1 masque : conversion float32 disponible, comparaisons désactivées (nécessite 2+ masques)")

    def _read_png_unicode_safe(self, path):
        """Lit un PNG en gérant les chemins Unicode (Windows)."""
        try:
            png_bytes = np.fromfile(path, dtype=np.uint8)
            if png_bytes.size == 0:
                return None
            return cv2.imdecode(png_bytes, cv2.IMREAD_UNCHANGED)
        except Exception:
            return None

    # ========================================================================
    # ANALYSE DE CONFLITS
    # ========================================================================

    def analyze_overlap(self):
        """Analyse et affiche les conflits de chevauchement."""
        if len(self.masks) < 2:
            messagebox.showwarning("Analyse impossible", "Charge au moins 2 masques valides.")
            return

        self._log("🔍 Analyse de chevauchement en cours...")
        self._clear_plot()

        h, w = self.masks[0].shape
        self.mask_stack, threshold = self._build_conflict_stack(self.masks)
        overlap_count = np.sum(self.mask_stack, axis=0)
        conflict_zone = overlap_count >= 2

        overlay, legend_handles = self._build_color_overlay()
        conflict_ratio = (np.count_nonzero(conflict_zone) / float(h * w)) * 100.0
        pair_lines = self._format_pair_conflicts_summary()

        # Affichage graphique
        self.fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
        self.fig.patch.set_facecolor('#F0F0F0')
        self.ax_conflict = ax2

        # Vue superposée
        ax1.imshow(overlay)
        ax1.set_title("Superposition multi-masques (code couleur)", fontsize=10, fontweight='bold')
        ax1.axis('off')
        ax1.legend(
            handles=legend_handles[:12],
            loc='upper center',
            bbox_to_anchor=(0.5, -0.08),
            ncol=2,
            fontsize=8,
            frameon=False
        )

        # Carte de conflits
        ax2.imshow(overlap_count, cmap='viridis', vmin=0, vmax=max(2, len(self.masks)))
        ax2.contour(conflict_zone.astype(np.uint8), levels=[0.5], colors='red', linewidths=0.8)
        ax2.set_title(
            f"Conflits (>=2 masques > {threshold:.2f})\n{np.count_nonzero(conflict_zone)} px ({conflict_ratio:.2f}%)",
            fontsize=10,
            fontweight='bold'
        )
        if pair_lines:
            ax2.text(
                0.5,
                -0.12,
                "Top paires en conflit: " + " | ".join(pair_lines),
                transform=ax2.transAxes,
                ha='center',
                va='top',
                fontsize=8,
                color="#263238"
            )
        ax2.axis('off')

        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.mpl_connect('button_press_event', self._on_conflict_click)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._log(f"✅ Analyse terminée - {np.count_nonzero(conflict_zone)} px en conflit ({conflict_ratio:.2f}%)")

    def preview_color_overlay(self):
        """Affiche un aperçu de la superposition colorée."""
        if len(self.masks) < 2:
            messagebox.showwarning("Aperçu impossible", "Charge au moins 2 masques valides.")
            return

        self._log("🎨 Génération de la superposition colorée...")
        self._clear_plot()

        try:
            overlay, legend_handles = self._build_color_overlay()
        except ValueError as exc:
            messagebox.showwarning("Aperçu impossible", str(exc))
            return

        h, w = self.masks[0].shape
        self.fig, ax = plt.subplots(1, 1, figsize=(11, 8))
        self.fig.patch.set_facecolor('#F0F0F0')

        ax.imshow(overlay)
        ax.set_title(
            f"Aperçu superposition colorée\n{len(self.masks)} masques chargés",
            fontsize=11,
            fontweight='bold'
        )
        ax.axis('off')
        ax.legend(
            handles=legend_handles[:12],
            loc='upper center',
            bbox_to_anchor=(0.5, -0.05),
            ncol=2,
            fontsize=8,
            frameon=False,
        )

        self.fig.tight_layout()
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.lbl_conflict_info.config(
            text=f"Aperçu couleur affiché: {len(self.masks)} masques superposés sur {w}x{h} px.",
            bg="white",
            fg="#1B5E20"
        )

        self._log(f"✅ Aperçu superposition affiché - {len(self.masks)} masques sur {w}x{h} px")

    def _build_conflict_stack(self, masks):
        """Construit un stack binaire de conflits selon le seuil."""
        threshold = self._get_conflict_threshold()
        stack = np.stack(
            [(m.astype(np.float32) / 65535.0) > threshold for m in masks],
            axis=0
        )
        return stack, threshold

    def _build_color_overlay(self):
        """Construit une image RGB superposant tous les masques en couleur."""
        if len(self.masks) < 2:
            raise ValueError("Charge au moins 2 masques valides.")

        h, w = self.masks[0].shape
        overlay = np.zeros((h, w, 3), dtype=np.float32)
        legend_handles = []

        for idx, mask in enumerate(self.masks):
            color = np.array(self.mask_colors[idx % len(self.mask_colors)], dtype=np.float32)
            mask_norm = mask.astype(np.float32) / 65535.0
            mask_alpha = np.where(mask > 0, mask_norm, 0.0)

            for c in range(3):
                overlay[..., c] += mask_alpha * color[c]

            legend_handles.append(Patch(color=color, label=f"M{idx+1}: {Path(self.mask_paths[idx]).name}"))

        return np.clip(overlay, 0.0, 1.0), legend_handles

    def _format_pair_conflicts_summary(self, max_items=3):
        """Retourne les top paires en conflit."""
        if self.mask_stack is None:
            return []

        n = self.mask_stack.shape[0]
        pair_stats = []
        for i in range(n):
            for j in range(i + 1, n):
                px = int(np.count_nonzero(self.mask_stack[i] & self.mask_stack[j]))
                if px > 0:
                    name_i = Path(self.mask_paths[i]).name
                    name_j = Path(self.mask_paths[j]).name
                    pair_stats.append((px, f"{name_i} + {name_j}: {px}px"))

        pair_stats.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in pair_stats[:max_items]]

    def _on_conflict_click(self, event):
        """Gère le clic sur la carte de conflits."""
        if event.inaxes != self.ax_conflict or self.mask_stack is None:
            return
        if event.xdata is None or event.ydata is None:
            return

        x = int(event.xdata)
        y = int(event.ydata)
        h, w = self.mask_stack.shape[1], self.mask_stack.shape[2]
        if x < 0 or y < 0 or x >= w or y >= h:
            return

        active_indices = np.where(self.mask_stack[:, y, x])[0]
        if active_indices.size >= 2:
            names = [Path(self.mask_paths[i]).name for i in active_indices]
            self.lbl_conflict_info.config(
                text=f"Pixel ({x}, {y}) → {active_indices.size} masques: " + ", ".join(names),
                bg="white",
                fg="#B71C1C"
            )
        elif active_indices.size == 1:
            name = Path(self.mask_paths[int(active_indices[0])]).name
            self.lbl_conflict_info.config(
                text=f"Pixel ({x}, {y}) → 1 masque actif: {name} (pas de conflit)",
                bg="white",
                fg="#37474F"
            )
        else:
            self.lbl_conflict_info.config(
                text=f"Pixel ({x}, {y}) → aucun masque actif",
                bg="white",
                fg="#37474F"
            )

    def _get_conflict_threshold(self):
        """Récupère le seuil de conflit normalisé [0..1]."""
        try:
            threshold = float(self.conflict_threshold_var.get())
        except Exception:
            threshold = 0.15

        if threshold > 1.0 and threshold <= 100.0:
            threshold = threshold / 100.0

        threshold = max(0.0, min(1.0, threshold))
        self.conflict_threshold_var.set(threshold)
        return threshold

    # ========================================================================
    # CORRECTION PAR ORDRE DE PRIORITÉ
    # ========================================================================

    def preview_cleanup_ordered(self):
        """Prévisualise la correction par ordre de priorité."""
        if len(self.masks) < 2:
            messagebox.showwarning("Prévisualisation impossible", "Charge au moins 2 masques valides.")
            return

        mode = "fondu gris" if self.blend_mode_var.get() else "hard"
        self._log(f"👁 Prévisualisation correction (mode {mode})...")
        cleaned = self._build_cleaned_masks_from_order()
        if cleaned is None:
            messagebox.showwarning("Prévisualisation impossible", "Impossible de corriger les superpositions.")
            return

        self.cleaned_masks = cleaned
        self._clear_plot()

        original_stack, threshold = self._build_conflict_stack(self.masks)
        cleaned_stack, _ = self._build_conflict_stack(self.cleaned_masks)

        original_overlap = np.sum(original_stack, axis=0)
        cleaned_overlap = np.sum(cleaned_stack, axis=0)

        original_conflict = original_overlap >= 2
        cleaned_conflict = cleaned_overlap >= 2

        orig_count = int(np.count_nonzero(original_conflict))
        clean_count = int(np.count_nonzero(cleaned_conflict))
        removed_count = orig_count - clean_count

        if self.blend_mode_var.get():
            right_title = f"Apres fondu gris (ordre 01->XX)\nSeuil: > {threshold:.2f}"
        else:
            right_title = f"Apres correction (ordre 01->XX)\nSeuil: > {threshold:.2f}"

        self.fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
        self.fig.patch.set_facecolor('#F0F0F0')
        self.ax_conflict = ax2

        ax1.imshow(original_overlap, cmap='viridis', vmin=0, vmax=max(2, len(self.masks)))
        ax1.contour(original_conflict.astype(np.uint8), levels=[0.5], colors='red', linewidths=0.8)
        ax1.set_title(f"Avant correction\nConflits: {orig_count} px", fontsize=10, fontweight='bold')
        ax1.axis('off')

        ax2.imshow(cleaned_overlap, cmap='viridis', vmin=0, vmax=max(2, len(self.masks)))
        ax2.contour(cleaned_conflict.astype(np.uint8), levels=[0.5], colors='red', linewidths=0.8)
        ax2.set_title(f"{right_title}\nConflits: {clean_count} px", fontsize=10, fontweight='bold')
        ax2.axis('off')

        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.btn_export_cleanup.config(state=tk.NORMAL)

        if self.blend_mode_var.get():
            self.lbl_conflict_info.config(
                text=f"Prévisualisation fondu terminée: dépassements {clean_count} px (objectif: 0).",
                bg="white",
                fg="#1B5E20"
            )
            self._log(f"✅ Prévisualisation fondu - Dépassements: {clean_count} px")
        else:
            self.lbl_conflict_info.config(
                text=f"Prévisualisation terminée: {removed_count} px de conflit retirés ({orig_count} → {clean_count}).",
                bg="white",
                fg="#1B5E20"
            )
            self._log(f"✅ Prévisualisation - Conflits réduits: {orig_count} → {clean_count} px (-{removed_count})")

    def _build_cleaned_masks_from_order(self):
        """Construit les masques corrigés selon l'ordre de priorité."""
        if len(self.masks) < 2:
            return None

        self.ordered_indices = self._compute_ordered_indices()
        cleaned = [np.zeros_like(mask, dtype=np.uint16) for mask in self.masks]

        if self.blend_mode_var.get():
            # Mode fondu : chaque masque prend une part de l'opacité restante
            remaining = np.ones(self.masks[0].shape, dtype=np.float32)
            for idx in self.ordered_indices:
                alpha = self.masks[idx].astype(np.float32) / 65535.0
                contrib = alpha * remaining
                cleaned[idx] = np.clip(np.round(contrib * 65535.0), 0, 65535).astype(np.uint16)
                remaining *= (1.0 - alpha)
            return cleaned

        # Mode hard : le premier masque garde ses pixels, les suivants prennent les pixels libres
        occupied = np.zeros(self.masks[0].shape, dtype=bool)

        for idx in self.ordered_indices:
            current = self.masks[idx]
            keep = (current > 0) & (~occupied)
            cleaned[idx] = np.where(keep, current, 0).astype(np.uint16)
            occupied |= keep

        return cleaned

    def export_cleaned_masks(self):
        """Exporte les masques corrigés avec renommage séquentiel selon ordre de pose."""
        if self.cleaned_masks is None:
            messagebox.showwarning(
                "Export impossible",
                "Clique d'abord sur 'Previsualiser correction' puis valide le resultat avant export."
            )
            return

        validate = messagebox.askyesno(
            "Valider et exporter",
            "Exporter les masques corriges avec renommage sequentiel (01->XX selon ordre de pose) ?"
        )
        if not validate:
            return

        output_dir = filedialog.askdirectory(
            title="Choisir le dossier de sortie des masques corriges",
            initialdir=str(self.default_mask_dir)
        )
        if not output_dir:
            return

        self.default_mask_dir = Path(output_dir)

        saved_files = []

        # Exporter selon l'ORDRE DE POSE (ordered_indices)
        # ordered_indices contient l'ordre décroissant (haute priorité d'abord = posé en premier)
        for export_number, original_idx in enumerate(self.ordered_indices, start=1):
            original_path = self.mask_paths[original_idx]
            original_name = Path(original_path).stem
            suffix = Path(original_path).suffix

            # Enlever ancien numéro si présent
            import re
            name_without_number = re.sub(r'^\d+_', '', original_name)

            # Nouveau nom séquentiel selon ordre de pose
            new_name = f"{export_number:02d}_{name_without_number}"
            out_path = Path(output_dir) / f"{new_name}{suffix}"

            # Si fichier existe déjà, ajouter suffixe
            if out_path.exists():
                out_path = self._unique_output_path(output_dir, new_name, suffix)

            ok = cv2.imwrite(str(out_path), self.cleaned_masks[original_idx])
            if ok:
                saved_files.append(out_path.name)
                self._log(f"  → Masque {export_number:02d}: {Path(original_path).name} → {out_path.name}")

        if not saved_files:
            messagebox.showerror("Export", "Aucun fichier n'a ete ecrit.")
            return

        self.lbl_status.config(
            text=f"Export terminé:\n{len(saved_files)} masque(s)\ncorrigés"
        )
        self._log(f"💾 Export réussi - {len(saved_files)} masque(s) renommé(s) séquentiellement (01→{len(saved_files):02d})")
        messagebox.showinfo(
            "Export termine",
            f"{len(saved_files)} masque(s) exporté(s) avec renommage séquentiel.\n\n"
            f"Ordre de pose (priorité décroissante):\n"
            f"Premier: {saved_files[0]}\n"
            f"Dernier: {saved_files[-1]}\n\n"
            f"Dossier: {output_dir}"
        )

    def _compute_ordered_indices(self):
        """Calcule l'ordre des masques selon leur numéro de fichier.

        Ordre DÉCROISSANT (géologique) : 50 → 40 → 30 → 20 → 10
        Le numéro le plus élevé = priorité la plus haute
        """
        indexed_paths = list(enumerate(self.mask_paths))
        # IMPORTANT : reverse=True pour ordre décroissant (haute priorité d'abord)
        indexed_paths.sort(
            key=lambda item: (self._extract_numeric_order(item[1]), Path(item[1]).stem.lower()),
            reverse=True
        )
        return [idx for idx, _ in indexed_paths]

    def _update_order_label(self):
        """Met à jour le label affichant l'ordre détecté."""
        if not self.mask_paths:
            self.lbl_order_info.config(text="Ordre actuel: aucun masque chargé", bg="white", fg="#455A64")
            return

        self.ordered_indices = self._compute_ordered_indices()
        ordered_names = [Path(self.mask_paths[idx]).name for idx in self.ordered_indices]
        preview = " → ".join(ordered_names[:4])
        if len(ordered_names) > 4:
            preview += " → ..."
        self.lbl_order_info.config(
            text=f"Ordre détecté (décroissant, haute priorité d'abord): {preview}",
            bg="white",
            fg="#1B5E20"
        )

    def _extract_numeric_order(self, file_path):
        """Extrait le premier nombre du nom de fichier pour tri."""
        stem = Path(file_path).stem
        match = re.search(r"(\d+)", stem)
        if match:
            return int(match.group(1))
        return 10**9

    # ========================================================================
    # NETTOYAGE PAR THRESHOLD
    # ========================================================================

    def run_threshold_cleaning(self):
        """Lance le nettoyage threshold via mask_threshold_cleaner."""
        if process_all_masks is None:
            messagebox.showerror(
                "Nettoyage indisponible",
                "Le module mask_threshold_cleaner.py est introuvable ou invalide."
            )
            return

        self._log("🧹 Lancement du nettoyage threshold...")
        source_dir = self.default_mask_dir
        if not source_dir.exists():
            messagebox.showwarning("Dossier invalide", f"Dossier source introuvable:\n{source_dir}")
            return

        output_dir = source_dir / "clean_threshold"
        run_ok = messagebox.askyesno(
            "Nettoyage des masques",
            f"Lancer le nettoyage threshold sur:\n{source_dir}\n\nSortie:\n{output_dir}"
        )
        if not run_ok:
            return

        try:
            process_all_masks(
                source_dir=source_dir,
                output_dir=output_dir,
                config=MASK_CONFIG,
                default_rule=DEFAULT_RULE,
            )
        except Exception as exc:
            messagebox.showerror("Erreur nettoyage", f"Le nettoyage a echoue:\n{exc}")
            return

        cleaned_files = sorted(output_dir.glob("*.png"))
        if not cleaned_files:
            messagebox.showwarning(
                "Nettoyage termine",
                "Aucun masque nettoye genere. Verifie la configuration MASK_CONFIG."
            )
            return

        self.lbl_status.config(
            text=f"Nettoyage:\n{len(cleaned_files)} masque(s)\nterminé"
        )
        self._log(f"✅ Nettoyage threshold terminé - {len(cleaned_files)} masque(s) généré(s)")

        auto_load = messagebox.askyesno(
            "Charger les masques nettoyes",
            f"{len(cleaned_files)} masque(s) nettoye(s) detecte(s).\nCharger ces masques maintenant ?"
        )
        if auto_load:
            self._load_masks_from_paths([str(p) for p in cleaned_files])

    # ========================================================================
    # ASSEMBLAGE DE MASQUES
    # ========================================================================

    def _toggle_exclusion_controls(self):
        """Active/désactive les contrôles d'exclusion selon le mode."""
        if self.assembly_mode.get() == "exclusion":
            self.lbl_assembly_info.config(
                text="Mode exclusion : le noir du masque d'exclusion cache les zones du masque de base.",
                bg="white",
                fg="#1565C0"
            )
        else:
            self.lbl_assembly_info.config(
                text="Sélectionnez une méthode et cliquez sur 'Assembler'.",
                bg="white",
                fg="#90A4AE"
            )

    def _update_exclusion_mask_lists(self):
        """Met à jour les listes déroulantes avec les masques chargés."""
        if not self.masks:
            return

        mask_names = [f"{idx}: {Path(path).name}" for idx, path in enumerate(self.mask_paths)]

        self.combo_base_mask['values'] = mask_names
        self.combo_exclusion_mask['values'] = mask_names

        # Sélection par défaut
        if len(self.masks) >= 2:
            self.exclusion_base_mask.set(0)
            self.exclusion_mask_idx.set(1)
            self.combo_base_mask.current(0)
            self.combo_exclusion_mask.current(1)

    def _apply_exclusion_mask(self, base_idx, exclusion_idx):
        """Applique un masque d'exclusion sur un masque de base.

        Args:
            base_idx: Index du masque de base
            exclusion_idx: Index du masque d'exclusion (noir=cache, blanc=révèle)

        Returns:
            np.ndarray uint16: Masque résultant
        """
        if base_idx < 0 or base_idx >= len(self.masks):
            raise ValueError(f"Index masque de base invalide: {base_idx}")
        if exclusion_idx < 0 or exclusion_idx >= len(self.masks):
            raise ValueError(f"Index masque d'exclusion invalide: {exclusion_idx}")

        base_mask = self.masks[base_idx].astype(np.float32)
        exclusion_mask = self.masks[exclusion_idx].astype(np.float32)

        # Statistiques pour debug
        excl_min = np.min(exclusion_mask)
        excl_max = np.max(exclusion_mask)
        excl_zeros = np.count_nonzero(exclusion_mask == 0)
        excl_total = exclusion_mask.size

        self._log(f"📊 Masque d'exclusion - Min: {excl_min:.0f}, Max: {excl_max:.0f}, Pixels noirs (0): {excl_zeros}/{excl_total} ({100*excl_zeros/excl_total:.1f}%)")

        # Normaliser le masque d'exclusion en 0-1 (0=noir=cache, 1=blanc=révèle)
        exclusion_normalized = exclusion_mask / 65535.0

        # Appliquer l'exclusion : multiplier le masque de base par le masque d'exclusion
        # Où exclusion est noir (0) → résultat = 0 (caché)
        # Où exclusion est blanc (65535) → résultat = base_mask (révélé)
        result = base_mask * exclusion_normalized

        # Reconvertir en uint16 en clampant les valeurs
        result = np.clip(result, 0, 65535).astype(np.uint16)

        # Stats résultat
        result_zeros = np.count_nonzero(result == 0)
        result_nonzeros = np.count_nonzero(result > 0)
        self._log(f"✅ Résultat - Pixels noirs: {result_zeros}, Pixels non-noirs: {result_nonzeros}")

        return result

    def assemble_masks(self):
        """Assemble plusieurs masques en un seul selon la methode choisie."""
        if len(self.masks) < 2:
            messagebox.showwarning("Assemblage impossible", "Charge au moins 2 masques valides.")
            return

        # Nettoyage de l'affichage précédent
        self._clear_plot()

        mode = self.assembly_mode.get()
        self._log(f"🔧 Assemblage en cours (mode: {mode})...")
        h, w = self.masks[0].shape

        # Mode exclusion : traitement spécial
        if mode == "exclusion":
            try:
                # Récupérer les index depuis les combobox
                base_idx = self.combo_base_mask.current()
                exclusion_idx = self.combo_exclusion_mask.current()

                self._log(f"📌 Indices sélectionnés - Base: {base_idx}, Exclusion: {exclusion_idx}")

                if base_idx < 0 or exclusion_idx < 0:
                    messagebox.showwarning(
                        "Configuration invalide",
                        "Sélectionnez un masque de base et un masque d'exclusion dans les listes déroulantes."
                    )
                    return

                if base_idx == exclusion_idx:
                    messagebox.showwarning(
                        "Configuration invalide",
                        "Le masque de base et le masque d'exclusion doivent être différents."
                    )
                    return

                assembled = self._apply_exclusion_mask(base_idx, exclusion_idx)
                method_name = f"Exclusion (Base: M{base_idx+1}, Excl: M{exclusion_idx+1})"
            except Exception as exc:
                self._log(f"❌ Erreur exclusion: {exc}")
                messagebox.showerror("Erreur exclusion", str(exc))
                return
        else:
            # Modes standard
            ordered_indices = None
            if mode == "priority":
                self.ordered_indices = self._compute_ordered_indices()
                ordered_indices = self.ordered_indices

            try:
                assembled = assemble_mask_list(self.masks, mode=mode, ordered_indices=ordered_indices)
            except ValueError as exc:
                messagebox.showerror("Erreur assemblage", str(exc))
                return

            mode_titles = {
                "max": "Maximum",
                "add": "Addition (clamp 65535)",
                "average": "Moyenne",
                "homogeneous": "Homogene (sans double pixel)",
                "priority": "Priorite (ordre 01->XX)",
            }
            method_name = mode_titles.get(mode, mode)

        self.assembled_mask = assembled

        # Statistiques
        non_zero_pixels = np.count_nonzero(assembled)
        total_pixels = h * w
        coverage_ratio = (non_zero_pixels / total_pixels) * 100.0
        mean_value = np.mean(assembled[assembled > 0]) if non_zero_pixels > 0 else 0
        max_value = np.max(assembled)

        # Affichage avec aperçu du masque assemblé
        # (le clear_plot a déjà été fait au début de la fonction)

        # Affichage spécifique pour le mode exclusion
        if mode == "exclusion":
            self.fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))
            self.fig.patch.set_facecolor('#F0F0F0')

            # Masque de base
            ax1.imshow(self.masks[base_idx], cmap='gray', vmin=0, vmax=65535)
            ax1.set_title(
                f"Masque de base (M{base_idx+1})\n{Path(self.mask_paths[base_idx]).name}",
                fontsize=9,
                fontweight='bold'
            )
            ax1.axis('off')

            # Masque d'exclusion
            ax2.imshow(self.masks[exclusion_idx], cmap='gray', vmin=0, vmax=65535)
            ax2.set_title(
                f"Masque d'exclusion (M{exclusion_idx+1})\n{Path(self.mask_paths[exclusion_idx]).name}\nNoir=cache | Blanc=révèle",
                fontsize=9,
                fontweight='bold'
            )
            ax2.axis('off')

            # Masque résultant
            ax3.imshow(assembled, cmap='gray', vmin=0, vmax=65535)
            ax3.set_title(
                f"Résultat après exclusion\n{non_zero_pixels} px actifs ({coverage_ratio:.2f}%)",
                fontsize=9,
                fontweight='bold'
            )
            ax3.axis('off')

            # Histogramme de distribution
            hist_data = assembled[assembled > 0].flatten()
            if hist_data.size > 0:
                ax4.hist(hist_data, bins=100, color='steelblue', alpha=0.7, edgecolor='black')
                ax4.set_title(
                    f"Distribution des valeurs\nMoyenne: {mean_value:.0f} | Max: {max_value}",
                    fontsize=9,
                    fontweight='bold'
                )
                ax4.set_xlabel("Valeur (0-65535)")
                ax4.set_ylabel("Nombre de pixels")
                ax4.grid(True, alpha=0.3)
            else:
                ax4.text(0.5, 0.5, "Masque vide", ha='center', va='center', fontsize=12)
                ax4.axis('off')

        else:
            # Affichage standard pour les autres modes
            self.fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 6))
            self.fig.patch.set_facecolor('#F0F0F0')

            # Masque assemblé (aperçu principal)
            ax1.imshow(assembled, cmap='gray', vmin=0, vmax=65535)
            ax1.set_title(
                f"Masque assemblé ({method_name})\n{non_zero_pixels} px actifs ({coverage_ratio:.2f}%)",
                fontsize=10,
                fontweight='bold'
            )
            ax1.axis('off')

            # Superposition colorée des masques d'origine pour comparaison
            try:
                overlay, legend_handles = self._build_color_overlay()
                ax2.imshow(overlay)
                ax2.set_title(
                    f"Masques d'origine superposés\n{len(self.masks)} masques",
                    fontsize=10,
                    fontweight='bold'
                )
                ax2.axis('off')

                # Légende compacte en bas de l'overlay
                if len(legend_handles) <= 8:
                    ax2.legend(
                        handles=legend_handles,
                        loc='upper center',
                        bbox_to_anchor=(0.5, -0.05),
                        ncol=2,
                        fontsize=7,
                        frameon=False
                    )
            except Exception:
                ax2.text(0.5, 0.5, "Aperçu non disponible", ha='center', va='center', fontsize=10)
                ax2.axis('off')

            # Histogramme de distribution
            hist_data = assembled[assembled > 0].flatten()
            if hist_data.size > 0:
                ax3.hist(hist_data, bins=100, color='steelblue', alpha=0.7, edgecolor='black')
                ax3.set_title(
                    f"Distribution des valeurs\nMoyenne: {mean_value:.0f} | Max: {max_value}",
                    fontsize=10,
                    fontweight='bold'
                )
                ax3.set_xlabel("Valeur (0-65535)")
                ax3.set_ylabel("Nombre de pixels")
                ax3.grid(True, alpha=0.3)
            else:
                ax3.text(0.5, 0.5, "Masque vide", ha='center', va='center', fontsize=12)
                ax3.axis('off')

        try:
            self.fig.tight_layout()

            self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            self.lbl_assembly_info.config(
                text=f"Assemblage terminé: {len(self.masks)} masques → 1 masque par méthode '{method_name}'",
                bg="white",
                fg="#1B5E20"
            )
            self.btn_export_assembled_separate.config(state=tk.NORMAL)
            self._log(f"✅ Assemblage terminé ({method_name}) - Couverture: {coverage_ratio:.2f}%")

            # Forcer l'update de l'interface avant la popup
            self.root.update_idletasks()

            export_now = messagebox.askyesno(
                "Assemblage termine",
                f"Masque assemble cree avec succes ({method_name}).\n"
                f"Couverture: {non_zero_pixels} px ({coverage_ratio:.2f}%)\n\n"
                "Exporter maintenant ?"
            )

            if export_now:
                self.export_assembled_mask()
        except Exception as exc:
            self._log(f"❌ Erreur affichage: {exc}")
            messagebox.showerror("Erreur affichage", f"Erreur lors de l'affichage:\n{exc}")

    def export_assembled_mask(self):
        """Exporte le masque assemblé."""
        if self.assembled_mask is None:
            messagebox.showwarning("Export impossible", "Aucun masque assemble a exporter.")
            return

        output_path = filedialog.asksaveasfilename(
            title="Enregistrer le masque assemble",
            initialdir=str(self.default_mask_dir),
            defaultextension=".png",
            filetypes=[("PNG 16-bit", "*.png")]
        )

        if not output_path:
            return

        ok = cv2.imwrite(output_path, self.assembled_mask)

        if ok:
            self.lbl_status.config(
                text=f"Masque\nassemblé\nexporté"
            )
            self._log(f"💾 Masque assemblé exporté - {Path(output_path).name}")
            messagebox.showinfo(
                "Export reussi",
                f"Masque assemble exporte:\n{output_path}"
            )
        else:
            messagebox.showerror("Erreur export", "Impossible d'ecrire le fichier PNG.")

    def export_assembled_mask_separate(self):
        """Exporte le masque assemblé dans un dossier dédié."""
        if self.assembled_mask is None:
            messagebox.showwarning("Export impossible", "Aucun masque assemble a sauvegarder.")
            return

        output_dir = self.default_mask_dir / "assembled_exports"
        output_dir.mkdir(parents=True, exist_ok=True)

        src_names = [Path(p).stem for p in self.mask_paths[:2]]
        if len(self.mask_paths) > 2:
            src_token = f"{src_names[0]}_{src_names[1]}_plus{len(self.mask_paths)-2}"
        else:
            src_token = "_".join(src_names)

        mode_token = self.assembly_mode.get()
        base_name = f"assembled_{mode_token}_{src_token}"
        out_path = self._unique_output_path(output_dir, base_name, ".png")

        ok = cv2.imwrite(str(out_path), self.assembled_mask)
        if not ok:
            messagebox.showerror("Erreur export", "Impossible d'ecrire le masque assemble.")
            return

        self.default_mask_dir = output_dir
        self.lbl_status.config(
            text=f"Masque\nassemblé\nsauvegardé"
        )
        messagebox.showinfo(
            "Sauvegarde terminee",
            f"Masque assemble enregistre dans:\n{out_path}"
        )

    # ========================================================================
    # COMPARAISON QTRE VS REFORGER
    # ========================================================================

    def load_reforger_error_masks(self):
        """Charge les masques d'erreur Reforger."""
        if len(self.masks) < 2:
            messagebox.showwarning("Chargement impossible", "Charge d'abord les masques QTRE.")
            return

        file_paths = filedialog.askopenfilenames(
            initialdir=str(self.default_mask_dir),
            filetypes=[("Masques PNG", "*.png")]
        )
        if not file_paths:
            return

        target_h, target_w = self.masks[0].shape
        loaded_errors = []
        loaded_paths = []
        resize_count = 0
        errors = []

        for path in file_paths:
            arr = self._read_png_unicode_safe(path)
            file_name = Path(path).name
            if arr is None:
                errors.append(f"{file_name}: lecture impossible")
                continue

            if arr.ndim == 3:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

            if arr.dtype == np.uint16:
                err_mask = (arr > 0).astype(np.uint8)
            elif arr.dtype == np.uint8:
                err_mask = (arr > 0).astype(np.uint8)
            else:
                errors.append(f"{file_name}: dtype {arr.dtype} non supporte")
                continue

            if err_mask.shape != (target_h, target_w):
                err_mask = cv2.resize(err_mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
                resize_count += 1

            loaded_errors.append(err_mask.astype(bool))
            loaded_paths.append(path)

        if not loaded_errors:
            messagebox.showwarning("Aucun masque valide", "Aucun mask erreur Reforger n'a pu etre charge.")
            return

        self.reforger_error_masks = loaded_errors
        self.reforger_error_mask_paths = loaded_paths
        self.reforger_error_combined = np.any(np.stack(self.reforger_error_masks, axis=0), axis=0)
        self.btn_overlay_qtre_reforger.config(state=tk.NORMAL)
        self.btn_export_qtre_combined.config(state=tk.DISABLED)
        self.btn_list_cyan_coords.config(state=tk.DISABLED)
        self.btn_fix_reforger_errors.config(state=tk.DISABLED)

        msg = f"{len(loaded_errors)} masque(s) erreur Reforger chargé(s)."
        if resize_count > 0:
            msg += f" Upscale auto appliqué sur {resize_count} fichier(s)."
        self.lbl_qtre_info.config(text=msg, bg="white", fg="#1B5E20")
        self._log(f"🎮 {len(loaded_errors)} masque(s) erreur Reforger chargé(s)")

        if errors:
            messagebox.showinfo("Fichiers erreur ignores", "Certains fichiers ont ete ignores:\n- " + "\n- ".join(errors[:10]))

    def overlay_qtre_with_reforger(self):
        """Superpose QTRE et erreurs Reforger dans une heatmap combinée."""
        if len(self.masks) < 2:
            messagebox.showwarning("Superposition impossible", "Charge d'abord les masques QTRE.")
            return
        if self.reforger_error_combined is None:
            messagebox.showwarning("Superposition impossible", "Charge d'abord les masks erreur Reforger.")
            return

        overlap_count, qtre_mask, threshold = self._compute_qtre_conflict_mask()
        reforger_mask = self.reforger_error_combined

        both = qtre_mask & reforger_mask
        qtre_only = qtre_mask & (~reforger_mask)
        cyan_only = reforger_mask & (~qtre_mask)

        h, w = qtre_mask.shape
        base_intensity = np.clip((overlap_count.astype(np.float32) / max(2, len(self.masks))) * 80.0, 0, 80).astype(np.uint8)
        combined = np.stack([base_intensity, base_intensity, base_intensity], axis=-1)

        combined[qtre_only] = np.array([255, 0, 0], dtype=np.uint8)
        combined[cyan_only] = np.array([0, 255, 255], dtype=np.uint8)
        combined[both] = np.array([255, 0, 255], dtype=np.uint8)

        self.qtre_combined_heatmap = combined
        self.cyan_mask = cyan_only
        self._clear_plot()

        self.fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
        self.fig.patch.set_facecolor('#F0F0F0')
        self.ax_qtre_combined = ax2

        ax1.imshow(overlap_count, cmap='hot', vmin=0, vmax=max(2, len(self.masks)))
        ax1.set_title(f"Heatmap QTRE (seuil > {threshold:.2f})", fontsize=10, fontweight='bold')
        ax1.axis('off')

        ax2.imshow(combined)
        ax2.set_title("QTRE + Reforger\nRouge=QTRE | Magenta=les deux | Cyan=Reforger seul", fontsize=10, fontweight='bold')
        ax2.axis('off')

        self.fig.tight_layout()
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        qtre_only_px = int(np.count_nonzero(qtre_only))
        both_px = int(np.count_nonzero(both))
        cyan_px = int(np.count_nonzero(cyan_only))
        self.lbl_qtre_info.config(
            text=f"Superposition terminée: rouge={qtre_only_px} px | magenta={both_px} px | cyan={cyan_px} px",
            bg="white",
            fg="#1B5E20"
        )

        self.btn_export_qtre_combined.config(state=tk.NORMAL)
        self.btn_list_cyan_coords.config(state=tk.NORMAL)
        self.btn_fix_reforger_errors.config(state=tk.NORMAL)

        self._log(f"🔥 Heatmap combinée - Rouge: {qtre_only_px} | Magenta: {both_px} | Cyan: {cyan_px} px")

    def _compute_qtre_conflict_mask(self):
        """Calcule le masque de conflits QTRE."""
        if len(self.masks) < 2:
            raise ValueError("Il faut au moins 2 masques QTRE.")
        stack, threshold = self._build_conflict_stack(self.masks)
        overlap_count = np.sum(stack, axis=0)
        return overlap_count, (overlap_count >= 2), threshold

    def correct_reforger_error_zones(self):
        """Corrige les zones magenta (détectées par QTRE et Reforger)."""
        if self.qtre_combined_heatmap is None:
            messagebox.showwarning(
                "Correction impossible",
                "Genere d'abord la heatmap combinee QTRE + Reforger."
            )
            return
        if len(self.masks) < 2:
            messagebox.showwarning("Correction impossible", "Charge au moins 2 masques QTRE.")
            return

        magenta_mask = (
            (self.qtre_combined_heatmap[..., 0] == 255)
            & (self.qtre_combined_heatmap[..., 1] == 0)
            & (self.qtre_combined_heatmap[..., 2] == 255)
        )

        magenta_count = int(np.count_nonzero(magenta_mask))
        if magenta_count == 0:
            messagebox.showinfo(
                "Correction inutile",
                "Aucun pixel magenta detecte. Rien a corriger."
            )
            return

        before_conflicts = self._count_conflict_pixels(self.masks)

        stack_values = np.stack(self.masks, axis=0).astype(np.uint16)
        dominant_idx = np.argmax(stack_values, axis=0)
        corrected_stack = stack_values.copy()

        for idx in range(corrected_stack.shape[0]):
            non_dominant_on_magenta = magenta_mask & (dominant_idx != idx)
            corrected_stack[idx, non_dominant_on_magenta] = 0

        corrected_masks = [corrected_stack[idx] for idx in range(corrected_stack.shape[0])]
        after_conflicts = self._count_conflict_pixels(corrected_masks)

        output_dir = filedialog.askdirectory(
            title="Choisir le dossier de sortie des masques corriges Reforger",
            initialdir=str(self.default_mask_dir)
        )
        if not output_dir:
            return

        saved_paths = []
        for idx, original_path in enumerate(self.mask_paths):
            original_name = Path(original_path).stem
            suffix = Path(original_path).suffix
            out_path = self._unique_output_path(output_dir, f"{original_name}_reforgerfix", suffix)
            ok = cv2.imwrite(str(out_path), corrected_masks[idx])
            if ok:
                saved_paths.append(out_path)

        if len(saved_paths) != len(corrected_masks):
            messagebox.showerror(
                "Export incomplet",
                "Tous les masques corriges n'ont pas pu etre ecrits."
            )
            return

        self.masks = corrected_masks
        self.mask_paths = [str(p) for p in saved_paths]
        self.default_mask_dir = Path(output_dir)

        self.qtre_combined_heatmap = None
        self.cyan_mask = None
        self.btn_export_qtre_combined.config(state=tk.DISABLED)
        self.btn_list_cyan_coords.config(state=tk.DISABLED)
        self.btn_fix_reforger_errors.config(state=tk.DISABLED)

        self.analyze_overlap()

        delta = before_conflicts - after_conflicts
        self.lbl_status.config(
            text=f"Correction\nReforger\nexportée"
        )
        self.lbl_qtre_info.config(
            text=f"Correction magenta terminée: {magenta_count} px traités | réduction conflits: {delta} px.",
            bg="white",
            fg="#1B5E20"
        )
        self._log(f"✂️ Correction magenta - {magenta_count} px traités | Conflits: {before_conflicts} → {after_conflicts} (-{delta})")
        messagebox.showinfo(
            "Correction terminee",
            f"Pixels magenta traites: {magenta_count}\n"
            f"Conflits avant: {before_conflicts}\n"
            f"Conflits apres: {after_conflicts}\n"
            f"Reduction: {delta}\n\n"
            f"Masques corriges exportes dans:\n{output_dir}"
        )

    def _count_conflict_pixels(self, masks):
        """Compte le nombre de pixels en conflit."""
        stack, _ = self._build_conflict_stack(masks)
        overlap_count = np.sum(stack, axis=0)
        return int(np.count_nonzero(overlap_count >= 2))

    def export_qtre_combined_heatmap(self):
        """Exporte la heatmap combinée QTRE + Reforger."""
        if self.qtre_combined_heatmap is None:
            messagebox.showwarning("Export impossible", "Genere d'abord la superposition QTRE + Reforger.")
            return

        output_path = filedialog.asksaveasfilename(
            title="Enregistrer la heatmap combinee",
            initialdir=str(self.default_mask_dir),
            defaultextension=".png",
            filetypes=[("PNG", "*.png")]
        )
        if not output_path:
            return

        bgr_img = cv2.cvtColor(self.qtre_combined_heatmap, cv2.COLOR_RGB2BGR)
        ok = cv2.imwrite(output_path, bgr_img)
        if not ok:
            messagebox.showerror("Erreur export", "Impossible d'ecrire la heatmap combinee.")
            return

        self.lbl_status.config(text=f"Heatmap\ncombinée\nexportée")
        self._log(f"💾 Heatmap combinée exportée - {Path(output_path).name}")
        messagebox.showinfo("Export reussi", f"Heatmap combinee exportee:\n{output_path}")

    def export_cyan_zones_coordinates(self):
        """Exporte les coordonnées des zones cyan (erreurs Reforger seules)."""
        if self.cyan_mask is None:
            messagebox.showwarning("Extraction impossible", "Genere d'abord la superposition QTRE + Reforger.")
            return

        try:
            meter_per_px = float(self.meters_per_pixel_var.get())
            if meter_per_px <= 0:
                raise ValueError
        except Exception:
            messagebox.showwarning("Valeur invalide", "La valeur m/px doit etre un nombre > 0.")
            return

        cyan_u8 = self.cyan_mask.astype(np.uint8)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(cyan_u8, connectivity=8)

        rows = []
        for label_id in range(1, num_labels):
            area_px = int(stats[label_id, cv2.CC_STAT_AREA])
            cx, cy = centroids[label_id]
            x_m = cx * meter_per_px
            y_m = cy * meter_per_px
            rows.append((label_id, area_px, cx, cy, x_m, y_m))

        if not rows:
            messagebox.showinfo("Zones cyan", "Aucune zone cyan detectee (pas d'erreur Reforger seule).")
            return

        output_path = filedialog.asksaveasfilename(
            title="Enregistrer les coordonnees des zones cyan",
            initialdir=str(self.default_mask_dir),
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Texte", "*.txt")]
        )
        if not output_path:
            return

        header = "zone_id,area_px,centroid_x_px,centroid_y_px,centroid_x_m,centroid_y_m"
        lines = [header]
        for zone_id, area_px, cx, cy, x_m, y_m in rows:
            lines.append(f"{zone_id},{area_px},{cx:.2f},{cy:.2f},{x_m:.2f},{y_m:.2f}")

        Path(output_path).write_text("\n".join(lines), encoding="utf-8")

        preview = "\n".join(lines[:8])
        self.lbl_qtre_info.config(
            text=f"{len(rows)} zone(s) cyan exportée(s) en mètres (m/px={meter_per_px}).",
            bg="white",
            fg="#1B5E20"
        )
        self._log(f"📍 {len(rows)} zone(s) cyan exportée(s) - {Path(output_path).name}")
        messagebox.showinfo(
            "Export zones cyan termine",
            f"{len(rows)} zone(s) exportee(s) vers:\n{output_path}\n\nApercu:\n{preview}"
        )

    # ========================================================================
    # UTILITAIRES
    # ========================================================================

    def _clear_plot(self):
        """Efface la zone graphique."""
        for widget in self.plot_frame.winfo_children():
            widget.destroy()
        if self.fig is not None:
            plt.close(self.fig)
            self.fig = None
        self.canvas = None

    def _unique_output_path(self, output_dir, base_name, suffix):
        """Génère un chemin de sortie unique en incrémentant si nécessaire."""
        candidate = Path(output_dir) / f"{base_name}{suffix}"
        if not candidate.exists():
            return candidate

        idx = 1
        while True:
            candidate = Path(output_dir) / f"{base_name}_{idx:02d}{suffix}"
            if not candidate.exists():
                return candidate
            idx += 1


# ============================================================================
# POINT D'ENTRÉE
# ============================================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = MaskOverlapApp(root)
    root.mainloop()
