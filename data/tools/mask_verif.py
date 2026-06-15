import tkinter as tk
from tkinter import filedialog, messagebox
import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from pathlib import Path
import re

try:
    from mask_threshold_cleaner import process_all_masks, MASK_CONFIG, DEFAULT_RULE
except Exception:
    process_all_masks = None
    MASK_CONFIG = {}
    DEFAULT_RULE = None


def assemble_mask_list(masks, mode="max", ordered_indices=None):
    """Assemble une liste de masques 2D uint16 en un seul masque uint16.

    Args:
        masks: Liste de tableaux numpy 2D (uint16 prefere, uint8 accepte).
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

class MaskOverlapApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Détecteur de conflits de masques PNG 16-bits")
        self.root.geometry("1200x700")

        self.mask_paths = []
        self.masks = []
        self.mask_stack = None
        self.cleaned_masks = None
        self.ordered_indices = []
        self.ax_conflict = None
        self.canvas = None
        self.fig = None
        self.ax_qtre_combined = None
        self.default_mask_dir = Path("h:/logiciel perso/Map generator/data/projects/Zbk_island/sources/instant")
        if not self.default_mask_dir.exists():
            self.default_mask_dir = Path.cwd()
            
        self.blend_mode_var = tk.BooleanVar(value=True)
        self.conflict_threshold_var = tk.DoubleVar(value=0.15)
        self.meters_per_pixel_var = tk.DoubleVar(value=1.0)
        self.reforger_error_mask_paths = []
        self.reforger_error_masks = []
        self.reforger_error_combined = None
        self.qtre_combined_heatmap = None
        self.cyan_mask = None
        # Tableau de couleurs contrastées pour distinguer rapidement les masques.
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

        # --- Interface Graphique (UI) ---
        control_frame = tk.Frame(root, padx=10, pady=10)
        control_frame.pack(side=tk.TOP, fill=tk.X)

        self.btn_load_masks = tk.Button(
            control_frame,
            text="Charger masques PNG 16-bit",
            command=self.load_masks,
            bg="#2196F3",
            fg="white",
            font=('Helvetica', 10, 'bold')
        )
        self.btn_load_masks.pack(side=tk.LEFT, padx=5)

        self.btn_reset = tk.Button(
            control_frame,
            text="Réinitialiser",
            command=self.reset_masks,
            bg="#607D8B",
            fg="white",
            font=('Helvetica', 10, 'bold')
        )
        self.btn_reset.pack(side=tk.LEFT, padx=5)

        self.lbl_status = tk.Label(control_frame, text="Aucun masque chargé", fg="gray")
        self.lbl_status.pack(side=tk.LEFT, padx=8)

        self.lbl_conflict_info = tk.Label(
            control_frame,
            text="Clique sur la carte de conflits pour voir les noms des masques concernés.",
            fg="#455A64"
        )
        self.lbl_conflict_info.pack(side=tk.LEFT, padx=8)

        tk.Label(control_frame, text="Seuil conflit (0-1):", fg="#263238").pack(side=tk.LEFT, padx=(10, 2))
        self.entry_conflict_threshold = tk.Entry(control_frame, textvariable=self.conflict_threshold_var, width=6)
        self.entry_conflict_threshold.pack(side=tk.LEFT, padx=2)

        self.btn_process = tk.Button(control_frame, text="Analyser le chevauchement", command=self.analyze_overlap, bg="#FF5722", fg="white", font=('Helvetica', 10, 'bold'), state=tk.DISABLED)
        self.btn_process.pack(side=tk.RIGHT, padx=10)

        # Section supplementaire : suppression des superpositions par ordre des masques.
        cleanup_frame = tk.LabelFrame(root, text="Correction des superpositions (ordre 01 -> XX)", padx=10, pady=8)
        cleanup_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 8))

        self.lbl_order_info = tk.Label(
            cleanup_frame,
            text="Ordre actuel: aucun masque charge",
            fg="#455A64"
        )
        self.lbl_order_info.pack(side=tk.LEFT, padx=4)

        self.btn_preview_cleanup = tk.Button(
            cleanup_frame,
            text="Previsualiser correction",
            command=self.preview_cleanup_ordered,
            bg="#6A1B9A",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED
        )
        self.btn_preview_cleanup.pack(side=tk.RIGHT, padx=4)

        self.btn_threshold_clean = tk.Button(
            cleanup_frame,
            text="Nettoyer masques (threshold)",
            command=self.run_threshold_cleaning,
            bg="#1565C0",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold')
        )
        self.btn_threshold_clean.pack(side=tk.RIGHT, padx=4)

        self.chk_blend_mode = tk.Checkbutton(
            cleanup_frame,
            text="Mode fondu gris (nuances de gris)",
            variable=self.blend_mode_var,
            onvalue=True,
            offvalue=False,
            fg="#263238"
        )
        self.chk_blend_mode.pack(side=tk.RIGHT, padx=10)

        self.btn_export_cleanup = tk.Button(
            cleanup_frame,
            text="Exporter masques corriges",
            command=self.export_cleaned_masks,
            bg="#2E7D32",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED
        )
        self.btn_export_cleanup.pack(side=tk.RIGHT, padx=4)

        # Section assemblage de masques
        assembly_frame = tk.LabelFrame(root, text="Assemblage de masques en un seul", padx=10, pady=8)
        assembly_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 8))

        self.lbl_assembly_info = tk.Label(
            assembly_frame,
            text="Combine plusieurs masques en un seul masque selon la methode choisie",
            fg="#455A64"
        )
        self.lbl_assembly_info.pack(side=tk.LEFT, padx=4)

        self.assembly_mode = tk.StringVar(value="homogeneous")
        tk.Radiobutton(
            assembly_frame,
            text="Maximum",
            variable=self.assembly_mode,
            value="max",
            fg="#263238"
        ).pack(side=tk.LEFT, padx=4)

        tk.Radiobutton(
            assembly_frame,
            text="Addition (clamp)",
            variable=self.assembly_mode,
            value="add",
            fg="#263238"
        ).pack(side=tk.LEFT, padx=4)

        tk.Radiobutton(
            assembly_frame,
            text="Homogene (sans double pixel)",
            variable=self.assembly_mode,
            value="homogeneous",
            fg="#263238"
        ).pack(side=tk.LEFT, padx=4)

        tk.Radiobutton(
            assembly_frame,
            text="Priorite (01->XX)",
            variable=self.assembly_mode,
            value="priority",
            fg="#263238"
        ).pack(side=tk.LEFT, padx=4)

        self.btn_assemble = tk.Button(
            assembly_frame,
            text="Assembler",
            command=self.assemble_masks,
            bg="#6A1B9A",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED
        )
        self.btn_assemble.pack(side=tk.RIGHT, padx=4)

        self.btn_export_assembled_separate = tk.Button(
            assembly_frame,
            text="Sauvegarder a part",
            command=self.export_assembled_mask_separate,
            bg="#2E7D32",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED
        )
        self.btn_export_assembled_separate.pack(side=tk.RIGHT, padx=4)

        self.assembled_mask = None

        # Section QTRE + erreurs Reforger
        qtre_frame = tk.LabelFrame(root, text="Comparaison QTRE vs erreurs Reforger", padx=10, pady=8)
        qtre_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 8))

        self.btn_load_reforger_errors = tk.Button(
            qtre_frame,
            text="Charger masks erreur Reforger",
            command=self.load_reforger_error_masks,
            bg="#00838F",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED
        )
        self.btn_load_reforger_errors.pack(side=tk.LEFT, padx=4)

        self.btn_overlay_qtre_reforger = tk.Button(
            qtre_frame,
            text="Superposer sur heatmap QTRE",
            command=self.overlay_qtre_with_reforger,
            bg="#AD1457",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED
        )
        self.btn_overlay_qtre_reforger.pack(side=tk.LEFT, padx=4)

        self.btn_export_qtre_combined = tk.Button(
            qtre_frame,
            text="Exporter heatmap combinee",
            command=self.export_qtre_combined_heatmap,
            bg="#2E7D32",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED
        )
        self.btn_export_qtre_combined.pack(side=tk.LEFT, padx=4)

        self.btn_list_cyan_coords = tk.Button(
            qtre_frame,
            text="Lister zones cyan (m)",
            command=self.export_cyan_zones_coordinates,
            bg="#455A64",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED
        )
        self.btn_list_cyan_coords.pack(side=tk.LEFT, padx=4)

        self.btn_fix_reforger_errors = tk.Button(
            qtre_frame,
            text="Corriger zones erreur Reforger",
            command=self.correct_reforger_error_zones,
            bg="#6D4C41",
            fg="white",
            activeforeground="white",
            disabledforeground="white",
            font=('Helvetica', 10, 'bold'),
            state=tk.DISABLED
        )
        self.btn_fix_reforger_errors.pack(side=tk.LEFT, padx=4)

        tk.Label(qtre_frame, text="m/px:", fg="#263238").pack(side=tk.LEFT, padx=(12, 2))
        self.entry_meters_per_pixel = tk.Entry(qtre_frame, textvariable=self.meters_per_pixel_var, width=7)
        self.entry_meters_per_pixel.pack(side=tk.LEFT, padx=2)

        self.lbl_qtre_info = tk.Label(
            qtre_frame,
            text="Charge des masques puis des masks erreur Reforger pour comparer QTRE.",
            fg="#455A64"
        )
        self.lbl_qtre_info.pack(side=tk.LEFT, padx=10)

        # Zone d'affichage des cartes
        self.plot_frame = tk.Frame(root)
        self.plot_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)

    def _clear_plot(self):
        for widget in self.plot_frame.winfo_children():
            widget.destroy()
        if self.fig is not None:
            plt.close(self.fig)
            self.fig = None
        self.canvas = None

    def reset_masks(self):
        self.mask_paths = []
        self.masks = []
        self.mask_stack = None
        self.cleaned_masks = None
        self.assembled_mask = None
        self.reforger_error_mask_paths = []
        self.reforger_error_masks = []
        self.reforger_error_combined = None
        self.qtre_combined_heatmap = None
        self.cyan_mask = None
        self.ordered_indices = []
        self.ax_conflict = None
        self.ax_qtre_combined = None
        self.btn_process.config(state=tk.DISABLED)
        self.btn_preview_cleanup.config(state=tk.DISABLED)
        self.btn_export_cleanup.config(state=tk.DISABLED)
        self.btn_assemble.config(state=tk.DISABLED)
        self.btn_export_assembled_separate.config(state=tk.DISABLED)
        self.btn_load_reforger_errors.config(state=tk.DISABLED)
        self.btn_overlay_qtre_reforger.config(state=tk.DISABLED)
        self.btn_export_qtre_combined.config(state=tk.DISABLED)
        self.btn_list_cyan_coords.config(state=tk.DISABLED)
        self.btn_fix_reforger_errors.config(state=tk.DISABLED)
        self.lbl_status.config(text="Aucun masque chargé", fg="gray")
        self.lbl_order_info.config(text="Ordre actuel: aucun masque charge", fg="#455A64")
        self.lbl_conflict_info.config(text="Clique sur la carte de conflits pour voir les noms des masques concernés.", fg="#455A64")
        self.lbl_assembly_info.config(text="Combine plusieurs masques en un seul masque selon la methode choisie", fg="#455A64")
        self.lbl_qtre_info.config(text="Charge des masques puis des masks erreur Reforger pour comparer QTRE.", fg="#455A64")
        self._clear_plot()

    def load_masks(self):
        file_paths = filedialog.askopenfilenames(
            initialdir=str(self.default_mask_dir),
            filetypes=[("Masques PNG 16-bit", "*.png")]
        )
        if not file_paths:
            return

        self._load_masks_from_paths(list(file_paths))

    def _load_masks_from_paths(self, file_paths):
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

            if mask.ndim != 2:
                errors.append(f"{file_name}: image non mono-canal")
                continue

            if mask.dtype == np.uint8:
                # Conversion 8-bit -> 16-bit sur toute la dynamique (0-255 -> 0-65535).
                mask = (mask.astype(np.uint16) * 257)
                warnings.append(f"{file_name}: converti de uint8 vers uint16")
            elif mask.dtype != np.uint16:
                errors.append(f"{file_name}: format {mask.dtype} (attendu: uint16 ou uint8)")
                continue

            if ref_shape is None:
                ref_shape = mask.shape
            elif mask.shape != ref_shape:
                errors.append(f"{file_name}: dimensions {mask.shape} != {ref_shape}")
                continue

            loaded_masks.append(mask)
            loaded_paths.append(path)

        if len(loaded_masks) < 2:
            self.mask_paths = loaded_paths
            self.masks = loaded_masks
            self.btn_process.config(state=tk.DISABLED)
            self.btn_preview_cleanup.config(state=tk.DISABLED)
            self.btn_export_cleanup.config(state=tk.DISABLED)
            msg = "Il faut au moins 2 masques PNG 16-bit valides de même taille."
            if errors:
                msg += "\n\nDétails:\n- " + "\n- ".join(errors[:10])
            messagebox.showwarning("Chargement incomplet", msg)
            status_text = f"{len(loaded_masks)} masque valide"
            if len(loaded_masks) != 1:
                status_text += "s"
            self.lbl_status.config(text=status_text, fg="#B26A00")
            return

        self.mask_paths = loaded_paths
        self.masks = loaded_masks
        self.cleaned_masks = None
        self.assembled_mask = None
        self.reforger_error_mask_paths = []
        self.reforger_error_masks = []
        self.reforger_error_combined = None
        self.qtre_combined_heatmap = None
        self.cyan_mask = None
        self.btn_process.config(state=tk.NORMAL)
        self.btn_preview_cleanup.config(state=tk.NORMAL)
        self.btn_export_cleanup.config(state=tk.DISABLED)
        self.btn_assemble.config(state=tk.NORMAL)
        self.btn_export_assembled_separate.config(state=tk.DISABLED)
        self.btn_load_reforger_errors.config(state=tk.NORMAL)
        self.btn_overlay_qtre_reforger.config(state=tk.DISABLED)
        self.btn_export_qtre_combined.config(state=tk.DISABLED)
        self.btn_list_cyan_coords.config(state=tk.DISABLED)
        self.btn_fix_reforger_errors.config(state=tk.DISABLED)
        self.lbl_status.config(text=f"{len(self.masks)} masques chargés ({self.masks[0].shape[1]}x{self.masks[0].shape[0]})", fg="black")
        self._update_order_label()
        self.lbl_qtre_info.config(text="Masques charges. Charge maintenant les masks erreur Reforger.", fg="#1565C0")

        if errors:
            messagebox.showinfo("Fichiers ignorés", "Certains fichiers ont été ignorés:\n- " + "\n- ".join(errors[:10]))
        if warnings:
            messagebox.showinfo("Conversions appliquées", "Conversions automatiques:\n- " + "\n- ".join(warnings[:10]))

    def check_ready(self):
        self.btn_process.config(state=tk.NORMAL if len(self.masks) >= 2 else tk.DISABLED)

    def _read_png_unicode_safe(self, path):
        # imdecode via bytes contourne certains problemes de chemins Unicode sous Windows.
        try:
            png_bytes = np.fromfile(path, dtype=np.uint8)
            if png_bytes.size == 0:
                return None
            return cv2.imdecode(png_bytes, cv2.IMREAD_UNCHANGED)
        except Exception:
            return None

    def _get_conflict_threshold(self):
        # Seuil en fraction [0..1]. Si l'utilisateur entre 15, on interprete 15%.
        try:
            threshold = float(self.conflict_threshold_var.get())
        except Exception:
            threshold = 0.15

        if threshold > 1.0 and threshold <= 100.0:
            threshold = threshold / 100.0

        threshold = max(0.0, min(1.0, threshold))
        self.conflict_threshold_var.set(threshold)
        return threshold

    def _build_conflict_stack(self, masks):
        threshold = self._get_conflict_threshold()
        stack = np.stack(
            [(m.astype(np.float32) / 65535.0) > threshold for m in masks],
            axis=0
        )
        return stack, threshold

    def run_threshold_cleaning(self):
        if process_all_masks is None:
            messagebox.showerror(
                "Nettoyage indisponible",
                "Le module mask_threshold_cleaner.py est introuvable ou invalide."
            )
            return

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
            text=f"Nettoyage termine: {len(cleaned_files)} masque(s) dans {output_dir}",
            fg="#1B5E20"
        )

        auto_load = messagebox.askyesno(
            "Charger les masques nettoyes",
            f"{len(cleaned_files)} masque(s) nettoye(s) detecte(s).\nCharger ces masques maintenant ?"
        )
        if auto_load:
            self._load_masks_from_paths([str(p) for p in cleaned_files])

    def analyze_overlap(self):
        if len(self.masks) < 2:
            messagebox.showwarning("Analyse impossible", "Charge au moins 2 masques valides.")
            return

        self._clear_plot()

        h, w = self.masks[0].shape
        self.mask_stack, threshold = self._build_conflict_stack(self.masks)
        overlap_count = np.sum(self.mask_stack, axis=0)
        conflict_zone = overlap_count >= 2

        # Superposition colorée avec intensité normalisée par masque.
        overlay = np.zeros((h, w, 3), dtype=np.float32)
        legend_handles = []

        for idx, mask in enumerate(self.masks):
            color = np.array(self.mask_colors[idx % len(self.mask_colors)], dtype=np.float32)
            mask_norm = mask.astype(np.float32) / 65535.0
            mask_alpha = np.where(mask > 0, mask_norm, 0.0)

            for c in range(3):
                overlay[..., c] += mask_alpha * color[c]

            legend_handles.append(Patch(color=color, label=f"M{idx+1}: {Path(self.mask_paths[idx]).name}"))

        overlay = np.clip(overlay, 0.0, 1.0)
        conflict_ratio = (np.count_nonzero(conflict_zone) / float(h * w)) * 100.0
        pair_lines = self._format_pair_conflicts_summary()

        # --- Intégration des graphiques dans Tkinter ---
        self.fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
        self.fig.patch.set_facecolor('#F0F0F0')
        self.ax_conflict = ax2

        # Affichage de la vue superposée
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

        # Affichage de la carte d'alerte des conflits
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

        # Intégration Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.mpl_connect('button_press_event', self._on_conflict_click)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _format_pair_conflicts_summary(self, max_items=3):
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

    def _extract_numeric_order(self, file_path):
        stem = Path(file_path).stem
        match = re.search(r"(\d+)", stem)
        if match:
            return int(match.group(1))
        return 10**9

    def _compute_ordered_indices(self):
        indexed_paths = list(enumerate(self.mask_paths))
        indexed_paths.sort(key=lambda item: (self._extract_numeric_order(item[1]), Path(item[1]).stem.lower()))
        return [idx for idx, _ in indexed_paths]

    def _update_order_label(self):
        if not self.mask_paths:
            self.lbl_order_info.config(text="Ordre actuel: aucun masque charge", fg="#455A64")
            return

        self.ordered_indices = self._compute_ordered_indices()
        ordered_names = [Path(self.mask_paths[idx]).name for idx in self.ordered_indices]
        preview = " -> ".join(ordered_names[:6])
        if len(ordered_names) > 6:
            preview += " -> ..."
        self.lbl_order_info.config(text=f"Ordre detecte: {preview}", fg="#1B5E20")

    def _build_cleaned_masks_from_order(self):
        if len(self.masks) < 2:
            return None

        self.ordered_indices = self._compute_ordered_indices()
        cleaned = [np.zeros_like(mask, dtype=np.uint16) for mask in self.masks]

        if self.blend_mode_var.get():
            # Fondu enchaine: chaque masque prend une part de l'opacite restante.
            remaining = np.ones(self.masks[0].shape, dtype=np.float32)
            for idx in self.ordered_indices:
                alpha = self.masks[idx].astype(np.float32) / 65535.0
                contrib = alpha * remaining
                cleaned[idx] = np.clip(np.round(contrib * 65535.0), 0, 65535).astype(np.uint16)
                remaining *= (1.0 - alpha)
            return cleaned

        occupied = np.zeros(self.masks[0].shape, dtype=bool)

        # Le premier masque dans l'ordre garde ses pixels, les suivants ne prennent que les pixels libres.
        for idx in self.ordered_indices:
            current = self.masks[idx]
            keep = (current > 0) & (~occupied)
            cleaned[idx] = np.where(keep, current, 0).astype(np.uint16)
            occupied |= keep

        return cleaned

    def preview_cleanup_ordered(self):
        if len(self.masks) < 2:
            messagebox.showwarning("Prévisualisation impossible", "Charge au moins 2 masques valides.")
            return

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
        if self.blend_mode_var.get():
            # Le signalement de conflit suit toujours le seuil de detection configure.
            cleaned_conflict = cleaned_overlap >= 2
            right_title = "Apres fondu gris (ordre 01->XX)"
            right_metric = f"Conflits (> {threshold:.2f})"
        else:
            cleaned_conflict = cleaned_overlap >= 2
            right_title = "Apres correction (ordre 01->XX)"
            right_metric = f"Conflits (> {threshold:.2f})"

        orig_count = int(np.count_nonzero(original_conflict))
        clean_count = int(np.count_nonzero(cleaned_conflict))
        removed_count = orig_count - clean_count

        self.fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
        self.fig.patch.set_facecolor('#F0F0F0')
        self.ax_conflict = ax2

        ax1.imshow(original_overlap, cmap='viridis', vmin=0, vmax=max(2, len(self.masks)))
        ax1.contour(original_conflict.astype(np.uint8), levels=[0.5], colors='red', linewidths=0.8)
        ax1.set_title(f"Avant correction\nConflits: {orig_count} px", fontsize=10, fontweight='bold')
        ax1.axis('off')

        ax2.imshow(cleaned_overlap, cmap='viridis', vmin=0, vmax=max(2, len(self.masks)))
        ax2.contour(cleaned_conflict.astype(np.uint8), levels=[0.5], colors='red', linewidths=0.8)
        ax2.set_title(f"{right_title}\n{right_metric}: {clean_count} px", fontsize=10, fontweight='bold')
        ax2.axis('off')

        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.btn_export_cleanup.config(state=tk.NORMAL)
        if self.blend_mode_var.get():
            self.lbl_conflict_info.config(
                text=f"Previsualisation fondu terminee: depassements {clean_count} px (objectif: 0).",
                fg="#1B5E20"
            )
        else:
            self.lbl_conflict_info.config(
                text=f"Previsualisation terminee: {removed_count} px de conflit retires ({orig_count} -> {clean_count}).",
                fg="#1B5E20"
            )

    def _unique_output_path(self, output_dir, base_name, suffix):
        candidate = Path(output_dir) / f"{base_name}{suffix}"
        if not candidate.exists():
            return candidate

        idx = 1
        while True:
            candidate = Path(output_dir) / f"{base_name}_{idx:02d}{suffix}"
            if not candidate.exists():
                return candidate
            idx += 1

    def export_cleaned_masks(self):
        if self.cleaned_masks is None:
            messagebox.showwarning(
                "Export impossible",
                "Clique d'abord sur 'Previsualiser correction' puis valide le resultat avant export."
            )
            return

        validate = messagebox.askyesno(
            "Valider et exporter",
            "Exporter les nouveaux masques corriges sans ecraser les originaux ?"
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
        for idx, original_path in enumerate(self.mask_paths):
            original_name = Path(original_path).stem
            suffix = Path(original_path).suffix
            out_path = self._unique_output_path(output_dir, f"{original_name}_noconflict", suffix)

            ok = cv2.imwrite(str(out_path), self.cleaned_masks[idx])
            if ok:
                saved_files.append(out_path.name)

        if not saved_files:
            messagebox.showerror("Export", "Aucun fichier n'a ete ecrit.")
            return

        self.lbl_status.config(
            text=f"Export termine: {len(saved_files)} masque(s) corriges dans {output_dir}",
            fg="#1B5E20"
        )
        messagebox.showinfo(
            "Export termine",
            f"{len(saved_files)} masque(s) exporte(s) sans ecraser les originaux.\n\nExemple: {saved_files[0]}"
        )

    def _on_conflict_click(self, event):
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
                text=f"Pixel ({x}, {y}) -> {active_indices.size} masques: " + ", ".join(names),
                fg="#B71C1C"
            )
        elif active_indices.size == 1:
            name = Path(self.mask_paths[int(active_indices[0])]).name
            self.lbl_conflict_info.config(
                text=f"Pixel ({x}, {y}) -> 1 masque actif: {name} (pas de conflit)",
                fg="#37474F"
            )
        else:
            self.lbl_conflict_info.config(
                text=f"Pixel ({x}, {y}) -> aucun masque actif",
                fg="#37474F"
            )

    def assemble_masks(self):
        """Assemble plusieurs masques en un seul selon la methode choisie."""
        if len(self.masks) < 2:
            messagebox.showwarning("Assemblage impossible", "Charge au moins 2 masques valides.")
            return

        mode = self.assembly_mode.get()
        h, w = self.masks[0].shape
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

        # Afficher le resultat
        self._clear_plot()

        # Calculer les statistiques
        non_zero_pixels = np.count_nonzero(assembled)
        total_pixels = h * w
        coverage_ratio = (non_zero_pixels / total_pixels) * 100.0
        mean_value = np.mean(assembled[assembled > 0]) if non_zero_pixels > 0 else 0
        max_value = np.max(assembled)

        self.fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
        self.fig.patch.set_facecolor('#F0F0F0')

        # Affichage du masque assemble
        ax1.imshow(assembled, cmap='gray', vmin=0, vmax=65535)
        ax1.set_title(
            f"Masque assemble ({method_name})\n{non_zero_pixels} px actifs ({coverage_ratio:.2f}%)",
            fontsize=10,
            fontweight='bold'
        )
        ax1.axis('off')

        # Histogramme des valeurs
        hist_data = assembled[assembled > 0].flatten()
        if hist_data.size > 0:
            ax2.hist(hist_data, bins=100, color='steelblue', alpha=0.7, edgecolor='black')
            ax2.set_title(
                f"Distribution des valeurs\nMoyenne: {mean_value:.0f} | Max: {max_value}",
                fontsize=10,
                fontweight='bold'
            )
            ax2.set_xlabel("Valeur (0-65535)")
            ax2.set_ylabel("Nombre de pixels")
            ax2.grid(True, alpha=0.3)
        else:
            ax2.text(0.5, 0.5, "Masque vide", ha='center', va='center', fontsize=12)
            ax2.axis('off')

        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.lbl_assembly_info.config(
            text=f"Assemblage termine: {len(self.masks)} masques -> 1 masque par methode '{method_name}'",
            fg="#1B5E20"
        )
        self.btn_export_assembled_separate.config(state=tk.NORMAL)

        # Proposer l'export
        export_now = messagebox.askyesno(
            "Assemblage termine",
            f"Masque assemble cree avec succes ({method_name}).\n"
            f"Couverture: {non_zero_pixels} px ({coverage_ratio:.2f}%)\n\n"
            "Exporter maintenant ?"
        )

        if export_now:
            self.export_assembled_mask()

    def export_assembled_mask_separate(self):
        """Exporte le masque assemble dans un dossier dedie sans ecraser les originaux."""
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
            text=f"Masque assemble sauvegarde a part: {out_path.name}",
            fg="#1B5E20"
        )
        messagebox.showinfo(
            "Sauvegarde terminee",
            f"Masque assemble enregistre dans:\n{out_path}"
        )

    def load_reforger_error_masks(self):
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

        msg = f"{len(loaded_errors)} mask(s) erreur Reforger charge(s)."
        if resize_count > 0:
            msg += f" Upscale auto applique sur {resize_count} fichier(s)."
        self.lbl_qtre_info.config(text=msg, fg="#1B5E20")

        if errors:
            messagebox.showinfo("Fichiers erreur ignores", "Certains fichiers ont ete ignores:\n- " + "\n- ".join(errors[:10]))

    def _compute_qtre_conflict_mask(self):
        if len(self.masks) < 2:
            raise ValueError("Il faut au moins 2 masques QTRE.")
        stack, threshold = self._build_conflict_stack(self.masks)
        overlap_count = np.sum(stack, axis=0)
        return overlap_count, (overlap_count >= 2), threshold

    def overlay_qtre_with_reforger(self):
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
            text=f"Superposition terminee: rouge={qtre_only_px} px | magenta={both_px} px | cyan={cyan_px} px",
            fg="#1B5E20"
        )

        self.btn_export_qtre_combined.config(state=tk.NORMAL)
        self.btn_list_cyan_coords.config(state=tk.NORMAL)
        self.btn_fix_reforger_errors.config(state=tk.NORMAL)

    def _count_conflict_pixels(self, masks):
        stack, _ = self._build_conflict_stack(masks)
        overlap_count = np.sum(stack, axis=0)
        return int(np.count_nonzero(overlap_count >= 2))

    def correct_reforger_error_zones(self):
        if self.qtre_combined_heatmap is None:
            messagebox.showwarning(
                "Correction impossible",
                "Genere d'abord la heatmap combinee QTRE + Reforger."
            )
            return
        if len(self.masks) < 2:
            messagebox.showwarning("Correction impossible", "Charge au moins 2 masques QTRE.")
            return

        # Magenta = pixels detectes a la fois par QTRE et par les erreurs Reforger.
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

        # Sur les pixels magenta, seul le masque dominant est conserve.
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

        # Utiliser les masques corriges en memoire et relancer l'analyse.
        self.masks = corrected_masks
        self.mask_paths = [str(p) for p in saved_paths]
        self.default_mask_dir = Path(output_dir)

        # La heatmap combinee precedente est obsolete apres correction.
        self.qtre_combined_heatmap = None
        self.cyan_mask = None
        self.btn_export_qtre_combined.config(state=tk.DISABLED)
        self.btn_list_cyan_coords.config(state=tk.DISABLED)
        self.btn_fix_reforger_errors.config(state=tk.DISABLED)

        self.analyze_overlap()

        delta = before_conflicts - after_conflicts
        self.lbl_status.config(
            text=f"Correction Reforger exportee: {len(saved_paths)} masques | conflits {before_conflicts} -> {after_conflicts}",
            fg="#1B5E20"
        )
        self.lbl_qtre_info.config(
            text=f"Correction magenta terminee: {magenta_count} px traites | reduction conflits: {delta} px.",
            fg="#1B5E20"
        )
        messagebox.showinfo(
            "Correction terminee",
            f"Pixels magenta traites: {magenta_count}\n"
            f"Conflits avant: {before_conflicts}\n"
            f"Conflits apres: {after_conflicts}\n"
            f"Reduction: {delta}\n\n"
            f"Masques corriges exportes dans:\n{output_dir}"
        )

    def export_qtre_combined_heatmap(self):
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

        self.lbl_status.config(text=f"Heatmap combinee exportee: {Path(output_path).name}", fg="#1B5E20")
        messagebox.showinfo("Export reussi", f"Heatmap combinee exportee:\n{output_path}")

    def export_cyan_zones_coordinates(self):
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
            text=f"{len(rows)} zone(s) cyan exportee(s) en metres (m/px={meter_per_px}).",
            fg="#1B5E20"
        )
        messagebox.showinfo(
            "Export zones cyan termine",
            f"{len(rows)} zone(s) exportee(s) vers:\n{output_path}\n\nApercu:\n{preview}"
        )

    def export_assembled_mask(self):
        """Exporte le masque assemble."""
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
                text=f"Masque assemble exporte: {Path(output_path).name}",
                fg="#1B5E20"
            )
            messagebox.showinfo(
                "Export reussi",
                f"Masque assemble exporte:\n{output_path}"
            )
        else:
            messagebox.showerror("Erreur export", "Impossible d'ecrire le fichier PNG.")

if __name__ == "__main__":
    root = tk.Tk()
    app = MaskOverlapApp(root)
    root.mainloop()