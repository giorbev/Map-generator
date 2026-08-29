# 🗺️ Map Generator Pro

> **Automatic texture mask generator for Arma Reforger**  
> Transform your heightmap into a natural map without manual painting

![Version](https://img.shields.io/badge/version-7.0-green)
![Python](https://img.shields.io/badge/python-3.x-blue)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## 📖 Table of Contents

- [Why Map Generator Pro?](#-why-map-generator-pro)
- [Features](#-features)
- [Installation](#-installation)
- [Complete Workflow A→Z](#-complete-workflow-az)
- [Key Concepts](#-key-concepts)
- [Project Structure](#-project-structure)
- [Technical Constraints](#️-technical-constraints)
- [Glossary](#-glossary)
- [Contributing](#-contributing)

---

## 🎯 Why Map Generator Pro?

Creating a map in **Arma Reforger** involves, among many tasks, applying terrain and vegetation textures across the entire landscape. This step, known as **material painting**, can be done manually in Bohemia Interactive's Workbench — but this approach quickly reveals its limitations.

### The starting observation

Manually painting materials on a **16×16 km** map is a **colossal** undertaking. On a map like Zimnitrita (32×32 tiles), this means thousands of blocks to cover by hand. Every grassland, forest, rock face, and alpine area must be painted individually.

But the problem runs deeper. Even with patience, manual painting suffers from the **blank canvas** syndrome: how do you decide where to put the forest? Where does rock begin? Where does grassland end? The map often ends up as an artificial patchwork, with no natural coherence with the terrain's relief.

Manual mapping, however skillful, always carries **the mark of human hands**: transitions are too sharp, zones too regular, vegetation too symmetrical. Nothing that resembles nature.

### The idea

Faced with these challenges, the idea emerged to create a tool that places terrain and vegetation masks in a **natural way, without manual intervention**. The principle is simple: use the heightmap itself — altitude, slope, distance to coast, Gaea erosion data — to automatically determine where each type of vegetation should appear.

- **Rock** appears naturally where slopes are steep
- **Forests** colonize gentle hillsides
- **Alpine meadows** sit at altitude
- **Coastal areas** follow the shoreline

All of this **without the user painting a single tile**.

### The added value

Beyond time savings, Map Generator offers something manual painting cannot easily provide: the ability to **instantly visualize your map's potential**. Within minutes, you get a complete terrain rendering — inspiring new mapping ideas and revealing unexpected areas that make a map truly unique.

> ⚠️ **Note**: Map Generator is not a terrain sculpting tool. It works from a heightmap already finalized in Reforger Workbench. Its role is to transform that heightmap into texture masks that are coherent with the natural relief.

---

## ✨ Features

- ✅ **Automatic generation of 13 masks** (seabed, coastal, rock, forests, grasslands, alpine...)
- ✅ **Biome presets** (Oceanic Temperate, Mediterranean, Continental, etc.)
- ✅ **Auto-calibration** of parameters from heightmap
- ✅ **QTRE Budget** — Automatic validation (max 5-7 textures/block)
- ✅ **Satmap V2.0** — Generate textured satellite map from `.edds`
- ✅ **K-means classification** — Satmap segmentation by colors
- ✅ **Tile inspection** — Detailed analysis of Reforger `.ttile` files
- ✅ **Native desktop interface** — PyWebView application (Windows/Linux)

---

## 🚀 Installation

### Prerequisites

- **Python 3.8+**
- **Reforger Workbench** (to export `.asc` heightmap)

### Install dependencies

```bash
pip install -r requirements.txt
```

### Launch

```bash
python main.py
```

The application opens in a native desktop window.

---

## 📋 Complete Workflow A→Z

### ⚠️ Golden Rule

> **If the heightmap changes at any point, all steps from step 2 onward must be repeated.**  
> The heightmap is the ground truth of the entire pipeline.

---

### **Step 1 — Prepare terrain in Reforger Workbench**

#### 1️⃣ Sculpt the terrain
Work on altitude, hills, valleys, cliffs. Smooth rough areas. Place roads and rivers. This step is done entirely in **Reforger Workbench**.

#### 2️⃣ Export the heightmap
Once the terrain is satisfactory, export the heightmap as **`.asc`** from Workbench. This file is the foundation for the entire Map Generator pipeline.

> 💡 **Note**: Roads, objects and entities placed in Workbench are not taken into account by Map Generator. Only terrain geometry (height, slope) influences mask generation.

---

### **Step 2 — Configure the project**

#### 1️⃣ Create a project
On the **Projects** screen, click "Create project". Give it a clear name (e.g., `Zimnitrita`, `ZBK_island`).

#### 2️⃣ Import the heightmap
In **Terrain > Paths & files**, select the `.asc` file exported from Workbench. Also configure:
- **Reforger addon** (path to `addons/`)
- **catalog.json** (texture catalog)
- **Data dir** (`data/` folder of the project)

#### 3️⃣ Parse Workbench info
In **Terrain > Paths**, paste the "General Info" text copied from Workbench. This automatically sets up the grid (32×32 tiles, cellsize, etc.).

#### 4️⃣ Analyze the terrain
In **Terrain > Metric Atlas**, click "Analyze heightmap". This step computes slopes, altitudes and auto-calibrated parameters.

---

### **Step 3 — Choose materials**

#### 1️⃣ Select a biome
In **Generation > Masks**, choose the biome matching your map:
- Oceanic Temperate
- Mediterranean
- Continental
- etc.

Apply preset to load coherent textures.

#### 2️⃣ Adjust mapping
In the mapping table, assign each mask the desired Reforger texture. Vanilla textures are pre-loaded from `surfaces.json`.

---

### **Step 4 — Generate masks**

#### 1️⃣ Tune parameters
In **Generation > Parameters**, adjust:
- Slope thresholds (rock, cliff)
- fBm amplitude (fractal noise)
- Altitude thresholds for each zone

Auto-calibration from heightmap is a good starting point.

#### 2️⃣ Generate preview
In **Generation > Baking**, click **"Generate preview"**. The pipeline processes the heightmap (may take several minutes for 4097×4097). Preview displays.

#### 3️⃣ Validate and iterate
If the result is not satisfactory, adjust parameters and regenerate. Repeat until happy. Export PNG masks.

---

### **Step 5 — Quality control**

#### 1️⃣ Check QTRE budget
In **Inspection > QTRE Grid**, scan tiles. Each block must not exceed **5 (or 7 with patch)** textures. Red blocks indicate overflow.

#### 2️⃣ Inspect anomalies
Use **Inspection > Inspect Tile** to examine problematic tiles. **Corrections > Global Scan** to detect negligible slots.

---

### **Step 6 — Export and integration**

#### 1️⃣ Export PNG masks
Click **"Export PNG masks"** in **Generation > Baking**. Files are copied to `outputs/masks/latest/`.

#### 2️⃣ Generate Satmap (optional)
In **Satmap > Satmap V2.0**, generate the textured satmap from `.edds` files + `catalog.json`.

#### 3️⃣ Baking `.ttile` (WIP)
Direct writing to `.ttile` files is under development. For now, PNG masks must be integrated manually.

---

## 🧩 Key Concepts

### Masks — Principles and Order

#### What is a mask?

A mask is a **grayscale image** the same size as the heightmap (4097×4097 for a 16km map). White means "this texture applies here at 100%", black means "it doesn't apply at all", and gray levels express blending.

Map Generator generates **13 masks** simultaneously:

| Mask | Description |
|------|-------------|
| `seabed` | Seabed |
| `coastal` | Coastal zone |
| `alpages` | Alpine meadows |
| `landes_rocheuses` | Rocky heathlands |
| `maquis_landes` | Scrubland and heathlands |
| `foret_coniferes` | Coniferous forest |
| `foret_feuillue` | Deciduous forest |
| `flow` | Erosion traces (dry rivers) |
| `landes_plateau` | Plateau heathlands |
| `rock` | Rock outcrops |
| `deposit` | Alluvial deposits |
| `prairie_seche` | Dry grassland |
| `prairie_humide` | Wet grassland |

#### The subtraction principle

Masks are applied **in priority order, subtracting** each mask from subsequent ones. This means:

1. The `seabed` mask is placed first. Its area is "reserved" and cannot be covered.
2. The `coastal` mask is placed next, but only on areas not already occupied by `seabed`.
3. And so on until `prairie_humide`, the last mask.

This method ensures that **each pixel belongs to exactly one priority mask**, avoiding conflicts and ensuring complete terrain coverage (99.8% in practice).

#### Why order matters

Changing mask order changes the map's appearance. For example:

- If `rock` comes before `foret_coniferes`, rocky areas "eat into" the forest on slopes → more mineral feel.
- If `foret_coniferes` comes first, it grows into steep areas → more wooded feel.

> 💡 **Note**: The order pre-configured in Map Generator gives a natural European temperate terrain result, validated on Zimnitrita.

---

### QTRE Budget — 5 or 7 textures per block

#### Reforger's slot system

In the **Enfusion** engine, each terrain block (a tile subdivision) can hold a maximum number of textures simultaneously. This is called the **slot budget**.

By default, Reforger limits this to **5 textures per block**. Map Generator Pro uses an extended configuration allowing up to **7 textures per block** (Zimnitrita/QTRE configuration).

#### Why it matters

If a block exceeds its budget, Reforger may **crash** or display visual artifacts. The QTRE grid in the **Inspection** tab lets you visualize, block by block, how many textures are in use.

| Status | Color | Meaning |
|--------|-------|---------|
| **OK** | 🟢 Green | Texture count below budget |
| **Limit** | 🟡 Yellow | Exactly at budget — monitor |
| **Critical** | 🟠 Orange | Budget +1 — at risk |
| **Overflow** | 🔴 Red | Budget exceeded — must fix |

#### How to reduce overflows

- Reduce the number of active masks in dense areas
- Increase priority thresholds so certain masks yield
- Use **Global Scan** (Corrections) to identify negligible slots to remove
- Adjust QTRE threshold in **Generation > Parameters**

---

## 📂 Project Structure

```
data/projects/ProjectName/
├── inputs/              # Source files provided by the user
│   ├── heightmap/       # .asc (Workbench heightmap)
│   ├── satmap/          # .png (reference satmap)
│   ├── masks/           # .png (Zone A exclusion mask)
│   └── gaea/            # .png (flow, deposit from Gaea)
├── outputs/
│   ├── masks/latest/    # Generated PNG masks
│   ├── generated/       # Satmap, previews, result images
│   ├── cache/           # Terrain cache (npz, qtre_scan.json)
│   └── logs/            # Timestamped session logs
├── project.json         # Project configuration and paths
└── surfaces.json        # Reforger materials list
```

### Source files

| File | Description | Where to find it |
|------|-------------|------------------|
| **Heightmap (.asc)** | Terrain altitude map. Source of the entire pipeline. Export from Workbench after finalizing terrain sculpting. | Workbench > Terrain > Export > ASC |
| **Satmap (.png)** | Reference satellite image. Optional — useful for satmap generation. | Your existing satmap |
| **Exclusion mask (.png)** | Defines a priority Zone A. White areas are treated with priority and excluded from auto generation. Useful for urban or manually controlled zones. | Image editor (Gimp, Photoshop) — or exported from Reforger WB |
| **Flow (.png)** | Hydraulic erosion mask from Gaea. Traces dry rivers and ravines. | Gaea > Export > Flow mask |
| **Deposit (.png)** | Alluvial deposit mask from Gaea. Traces sediment zones at slope bases. | Gaea > Export > Deposit mask |
| **Catalog JSON** | Texture catalog with average colors and middle BCR files. Contains vanilla AND custom textures. | Default: `data/Textures_ArmaReforger/catalog.json` |

---

## ⚙️ Technical Constraints

### Limits of automatic generation

- ❌ Masks are based on geometry (altitude, slope, coast distance) — not roads, paths or built areas.
- ❌ Generated forests are "statistically probable" and may cover areas where the user wouldn't want forest.
- ❌ Generation is a natural starting point, not a replacement for fine-grained mapping.
- ❌ Sea and water areas are detected by altitude threshold (altitude < 0), which may not exactly match Reforger's shoreline.

### QTRE Budget

- ⚠️ **Max 5 textures/block** (vanilla Reforger)
- ⚠️ **Max 7 textures/block** (with Zimnitrita QTRE patch)
- ⚠️ **6+ textures = Workbench crash risk**

---

## 📚 Glossary

| Term | Definition |
|------|------------|
| **`.ttile`** | Reforger binary file containing terrain tile texture data (materials, weights per block) |
| **`.edds`** | Compressed texture layer file (LZ4 DDS format) in `.EditorData`. Contains color data per material layer. |
| **`LRS2`** | Binary chunk in `.ttile` files listing active materials per block (Layer Resource Set 2) |
| **`QTRE`** | Extended texture budget configuration (7 slots instead of default 5) |
| **`fBm`** | Fractional Brownian Motion — fractal noise used to naturally enrich slope transitions |
| **`Slot budget`** | Maximum number of textures allowed per terrain block (5 default, 7 with QTRE) |
| **`Subtraction`** | Mask placement method: each mask removes its area from lower-priority masks |
| **`Heightmap`** | Terrain altitude image, typically in `.asc` (ASCII Grid) or 16-bit `.png` format |
| **`Cellsize`** | Heightmap resolution in meters per pixel (e.g., 4m/px for a 16km map at 4097px) |
| **`catalog.json`** | Reforger texture catalog with average colors and middle BCR files |
| **`Satmap`** | Satellite image of the map generated from applied material colors |
| **`K-means`** | Color-based clustering algorithm used to segment a satmap into vegetation zones |

---

## 🤝 Contributing

Contributions are welcome! For questions, suggestions or bug reports, open an **issue** on GitHub.

---

## 📄 License

MIT License — © 2026 **giorbev**

---

## 🎮 Created by

**Map Generator Pro v7.0**  
by **giorbev**

For the **Arma Reforger** community 🎖️
