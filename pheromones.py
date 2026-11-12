"""
pheromones.py - Vectorized coarse-grid chemical signaling for the ant colony.
Maintains HOME, FOOD, and DANGER pheromone layers using NumPy.
Uses non-wrapping slice indexing for diffusion to avoid boundary wrap-around.
"""

import numpy as np
import pygame

LAYER_HOME = 0
LAYER_FOOD = 1
LAYER_DANGER = 2

class PheromoneGrid:
    def __init__(self, world_width=1280, world_height=720, cell_size=4):
        self.world_width = world_width
        self.world_height = world_height
        self.cell_size = cell_size
        self.grid_w = world_width // cell_size
        self.grid_h = world_height // cell_size

        # Layers: 0: HOME, 1: FOOD, 2: DANGER
        self.layers = np.zeros((3, self.grid_w, self.grid_h), dtype=np.float32)

        # Simulation parameters
        # Evaporation: multiplier per update step
        self.decay_rates = np.array([0.997, 0.994, 0.985], dtype=np.float32)
        # Diffusion rates: slice laplacian weight
        self.diff_rates = np.array([0.08, 0.08, 0.12], dtype=np.float32)
        self.max_vals = np.array([100.0, 100.0, 100.0], dtype=np.float32)

        # Cached visualization surface
        self._vis_surface = pygame.Surface((self.grid_w, self.grid_h), pygame.SRCALPHA)

    def deposit(self, world_x, world_y, layer_idx, amount=10.0, radius=1):
        """Deposits pheromone at world coordinates."""
        gx = int(world_x // self.cell_size)
        gy = int(world_y // self.cell_size)

        if 0 <= gx < self.grid_w and 0 <= gy < self.grid_h:
            x_min = max(0, gx - radius)
            x_max = min(self.grid_w, gx + radius + 1)
            y_min = max(0, gy - radius)
            y_max = min(self.grid_h, gy + radius + 1)

            self.layers[layer_idx, x_min:x_max, y_min:y_max] = np.minimum(
                self.max_vals[layer_idx],
                self.layers[layer_idx, x_min:x_max, y_min:y_max] + amount
            )

    def sample(self, world_x, world_y, layer_idx):
        """Samples pheromone intensity at world coordinates."""
        gx = int(world_x // self.cell_size)
        gy = int(world_y // self.cell_size)
        if 0 <= gx < self.grid_w and 0 <= gy < self.grid_h:
            return float(self.layers[layer_idx, gx, gy])
        return 0.0

    def get_gradient(self, world_x, world_y, layer_idx, sample_dist=8.0):
        """
        Returns normalized steering gradient (dx, dy) towards higher pheromone intensity.
        Uses 4-directional neighborhood sampling.
        """
        c = self.sample(world_x, world_y, layer_idx)
        right = self.sample(world_x + sample_dist, world_y, layer_idx)
        left = self.sample(world_x - sample_dist, world_y, layer_idx)
        down = self.sample(world_x, world_y + sample_dist, layer_idx)
        up = self.sample(world_x, world_y - sample_dist, layer_idx)

        dx = right - left
        dy = down - up
        mag = (dx * dx + dy * dy) ** 0.5
        if mag > 0.01:
            return dx / mag, dy / mag, mag
        return 0.0, 0.0, 0.0

    def update(self, dt=1.0):
        """
        Vectorized diffusion and evaporation step.
        Uses slice indexing without np.roll so pheromones do not wrap across screen edges.
        """
        for i in range(3):
            grid = self.layers[i]
            diff = self.diff_rates[i]
            decay = self.decay_rates[i]

            # Slice-based discrete 2D Laplacian (strictly inner domain, no edge wrapping)
            # Center: grid[1:-1, 1:-1]
            # Neighbors: left, right, up, down
            inner = grid[1:-1, 1:-1]
            neighbors = (
                grid[:-2, 1:-1]   # Left
                + grid[2:, 1:-1]   # Right
                + grid[1:-1, :-2]   # Up
                + grid[1:-1, 2:]    # Down
            )
            laplacian = neighbors - 4.0 * inner
            grid[1:-1, 1:-1] += diff * laplacian

            # Evaporation
            grid *= decay

            # Threshold zero-out very small values to save compute
            grid[grid < 0.005] = 0.0

    def clear(self):
        """Clears all pheromone layers."""
        self.layers.fill(0.0)

    def render_overlay(self, target_surface):
        """
        Blits an alpha-blended heatmap visualization of the pheromone layers.
        Cyan: HOME, Orange/Yellow: FOOD, Red: DANGER.
        """
        # Vectorized RGBA buffer generation (grid_w, grid_h, 4)
        home = np.clip(self.layers[LAYER_HOME] * (255.0 / 60.0), 0, 255).astype(np.uint8)
        food = np.clip(self.layers[LAYER_FOOD] * (255.0 / 60.0), 0, 255).astype(np.uint8)
        danger = np.clip(self.layers[LAYER_DANGER] * (255.0 / 50.0), 0, 255).astype(np.uint8)

        # Transpose from (w, h) to (h, w) for pygame surface pixel array or build RGBA
        r = np.clip(danger.astype(np.uint16) + (food.astype(np.uint16) * 9 // 10), 0, 255).astype(np.uint8)
        g = np.clip((home.astype(np.uint16) * 7 // 10) + (food.astype(np.uint16) * 8 // 10), 0, 255).astype(np.uint8)
        b = np.clip(home.astype(np.uint16), 0, 255).astype(np.uint8)
        a = np.clip((r.astype(np.uint16) + g.astype(np.uint16) + b.astype(np.uint16)) // 2, 0, 160).astype(np.uint8)

        # Combine into (h, w, 4) buffer for pygame
        rgba = np.stack([r.T, g.T, b.T, a.T], axis=-1)
        pygame.image.frombuffer(rgba.tobytes(), (self.grid_w, self.grid_h), "RGBA")
        
        # Fast scale to world screen
        overlay = pygame.image.frombuffer(rgba.tobytes(), (self.grid_w, self.grid_h), "RGBA")
        scaled_overlay = pygame.transform.scale(overlay, (self.world_width, self.world_height))
        target_surface.blit(scaled_overlay, (0, 0))
