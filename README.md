# 🐜 Ant Colony Simulator - Ambient Desktop

An interactive 2D ant colony simulator designed to run as a lightweight ambient desktop / background application on Linux (Wayland & X11 compatible). The simulation features rich cross-section graphics ("2D ant farm cut-in-half") while maintaining minimal CPU, GPU, and RAM usage so it can remain open on a secondary monitor or workspace all day.

---

## 🌟 Key Features

### 1. High-Performance Ambient Architecture
- **Chunk-Cached Terrain**: Subterranean earth is split into $64 \times 64\text{px}$ offscreen chunk surfaces. Only modified chunks re-render when ants excavate tunnels or dirt settles.
- **Seamless 3-Pixel Boundary Rim Shading**: When digging or filling within 3 pixels of a chunk border, adjacent neighbor chunks are marked dirty so ambient occlusion shadows and tunnel rim shading remain seamless across chunk boundaries.
- **Vectorized NumPy Pheromones**: Dual-layer chemical signaling (`HOME`, `FOOD`, and `DANGER`) running on a coarse $4\times$ downsampled grid ($320 \times 180$) using non-wrapping slice diffusion (`grid[1:-1, 1:-1] += diff * laplacian`).
- **Eco / Background Mode**: Automatically detects window focus loss (`pygame.WINDOWFOCUSLOST`) to throttle rendering to 15 FPS while keeping colony physics stable. Supports default 30 FPS and 60 FPS toggle.
- **`pygame.SCALED` Wayland/X11 Support**: Internal canvas is fixed at $1280 \times 720$, enabling smooth window resizing and borderless fullscreen (`F11`) without breaking mouse brush coordinates.

### 2. Cross-Section Visuals ("Ant Farm Cut-in-Half")
- **Surface Atmosphere (Top 18%)**: Real-time / accelerated day/night sky cycle with celestial sun/moon arc and stars, procedural grass blades swaying in sinusoidal wind waves, and drifting pollen/dust.
- **Subterranean Strata (Bottom 82%)**: Topsoil, rich loam, clay, deep stone boulders, and impenetrable bedrock base with water percolation that darkens wet soil.
- **Procedural Segmented Ants**: Articulated multi-segmented bodies (head with moving antennae & mandibles, thorax, and striped gaster) with 6-leg alternating tripod walk cycles and visible carried cargo (food crumbs and dirt pellets).
- **Colony Life Cycle**:
  - **Queen**: Resides deep in the pre-carved royal chamber, laying eggs when fed.
  - **Brood**: Developing eggs $\rightarrow$ larvae (tended and fed by workers) $\rightarrow$ pupae $\rightarrow$ adult workers/soldiers.
  - **Workers**: Autonomous branching excavation, food foraging, dirt hauling to surface anthill mounds, and brood tending.
  - **Soldiers**: Heavy armored heads with crushing mandibles; patrol shafts and intercept invading pests.

---

## 🎮 Controls & God Powers

### Interactive Tools (Left-Click / Drag to apply, Scroll wheel to resize brush):
| Tool | Hotkey | Description |
|---|:---:|---|
| **Drop Food** | `1` | Spawn sugar drops, seeds, or fruit morsels on surface or in tunnels |
| **Rain / Water** | `2` | Pour water droplets that seep down and moisten porous soil |
| **Excavate / Dig** | `3` | Carve custom tunnels or chambers through earth (avoids bedrock) |
| **Fill Dirt** | `4` | Drop loose falling soil that settles into mounds with physics |
| **Pheromone Brush** | `5` | Paint custom `FOOD` trails (Left Click) or `DANGER` zones (Right Click) |
| **Spawn Threat** | `6` | Drop an invading beetle (Left Click) or spider (Right Click) to test defenses |
| **Inspect Ant** | `7` | Click any ant to track it with an indicator ring and view status in the HUD |

### Shortcuts:
- **`Scroll Wheel`**: Resize tool brush radius ($6\text{px} \dots 48\text{px}$).
- **`Space`**: Toggle pause / resume.
- **`F`**: Toggle target frame rate between 30 FPS and 60 FPS.
- **`H`**: Toggle HUD dock (zen ambient wallpaper mode).
- **`V`**: Toggle live pheromone heatmap overlay.
- **`F11`**: Toggle borderless fullscreen mode.
- **`Esc`**: Exit application.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Linux (Nobara, Fedora, Ubuntu, Arch, etc.) with Wayland or X11

### Installation & Launch
```bash
# Clone the repository
git clone https://github.com/Taastyyfrfr/antgame.git
cd antgame

# Run the launcher (creates local .venv and installs dependencies on first run)
./run.sh
```

Or manually:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

---

## 🧪 Testing & Benchmarks

Run automated tests:
```bash
PYTHONPATH=. .venv/bin/python tests/test_smoke.py
```

Run 300-ant performance stress benchmark:
```bash
PYTHONPATH=. .venv/bin/python tests/test_benchmark.py
```

---

## 📁 Project Structure
```
├── main.py            # Application loop, pygame.SCALED window, FPS eco throttling
├── world.py           # Chunked subterranean terrain, moisture percolation, starter colony
├── pheromones.py      # NumPy vectorized dual-layer diffusion & evaporation
├── ants.py            # Ant castes (Queen/Worker/Soldier), brood lifecycle, spatial hash
├── threats.py         # Invading beetles and spiders with soldier defense AI
├── renderer.py        # Atmospheric day/night sky, procedural ants, lighting & particles
├── ui.py              # Minimalist corner dock, speed buttons, inspector, brush reticle
├── tests/             # Smoke tests and 300-ant performance benchmarks
├── requirements.txt   # Dependencies: pygame-ce, numpy
└── run.sh             # Zero-config virtualenv launcher script
```

---

## 📄 License
MIT License. Feel free to use, modify, and build upon this project!
