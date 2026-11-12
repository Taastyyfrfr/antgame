"""
test_smoke.py - Automated verification and sanity checks for ant colony simulator.
"""

import os
import sys
import unittest
import numpy as np

# Ensure dummy video driver for headless execution
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
pygame.init()

from world import World, CELL_AIR, CELL_BEDROCK, CELL_MOUND
from pheromones import PheromoneGrid, LAYER_HOME, LAYER_FOOD, LAYER_DANGER
from ants import AntColony, Ant, CASTE_WORKER, CASTE_SOLDIER, CASTE_QUEEN, Brood
from threats import Threat
from renderer import Renderer
from ui import UI, TOOL_FOOD, TOOL_DIG

class TestAntColonySimulator(unittest.TestCase):
    def setUp(self):
        self.world = World(width=1280, height=720, cell_size=2, chunk_size_px=64)
        self.pheromones = PheromoneGrid(world_width=1280, world_height=720, cell_size=4)
        self.colony = AntColony(world=self.world, pheromones=self.pheromones)
        self.renderer = Renderer(width=1280, height=720)
        self.ui = UI(width=1280, height=720)

    def test_starter_colony_generated(self):
        """Verify pre-carved starter chambers and Queen placement."""
        self.assertIsNotNone(self.world.royal_chamber_pos)
        self.assertIsNotNone(self.world.nursery_chamber_pos)
        self.assertIsNotNone(self.world.food_storage_pos)

        # Queen exists and is located at royal chamber
        self.assertIsNotNone(self.colony.queen)
        self.assertEqual(self.colony.queen.caste, CASTE_QUEEN)
        self.assertFalse(self.world.is_solid(self.colony.queen.x, self.colony.queen.y))

        # Initial workers and soldiers spawned
        stats = self.colony.get_stats()
        self.assertGreater(stats["workers"], 10)
        self.assertGreater(stats["soldiers"], 2)
        self.assertGreater(stats["food"], 10)
        self.assertGreater(stats["eggs"] + stats["larvae"] + stats["pupae"], 5)

    def test_chunk_dirty_neighbor_boundary(self):
        """Verify adjustment #1: 3-pixel border dirtying marks adjacent chunks."""
        # Chunk 0,0 spans pixels 0..63 in x and y.
        # Clean all chunks first
        self.world.chunk_dirty.fill(False)
        
        # Carve at pixel (63, 200) - this is within 1 pixel of chunk border x=64
        self.world.carve_pixel(63, 200, play_effects=False)

        cx = 63 // 64 # chunk 0
        cy = 200 // 64 # chunk 3
        self.assertTrue(self.world.chunk_dirty[cx, cy])
        # Right neighbor chunk (cx + 1 = 1, cy = 3) MUST also be marked dirty!
        self.assertTrue(self.world.chunk_dirty[cx + 1, cy], "Adjacent right chunk should be marked dirty within 3px")

    def test_pheromone_slice_diffusion_no_wrapping(self):
        """Verify adjustment #3: slice diffusion does not wrap across opposite screen edges."""
        self.pheromones.clear()
        
        # Deposit high intensity near the right boundary (x = 1270, y = 360)
        self.pheromones.deposit(1270, 360, layer_idx=LAYER_FOOD, amount=100.0, radius=1)
        self.assertGreater(self.pheromones.sample(1270, 360, LAYER_FOOD), 10.0)

        # Opposite left edge must have ZERO pheromones
        left_edge_val_before = self.pheromones.sample(5, 360, LAYER_FOOD)
        self.assertEqual(left_edge_val_before, 0.0)

        # Run 20 diffusion steps
        for _ in range(20):
            self.pheromones.update(dt=1.0)

        # Left edge must STILL be 0.0 (no wrap-around!)
        left_edge_val_after = self.pheromones.sample(5, 360, LAYER_FOOD)
        self.assertEqual(left_edge_val_after, 0.0, "Pheromone must not wrap across opposite screen edge")

    def test_simulation_step_headless(self):
        """Run 60 simulation steps to verify physics, AI, brood, and rendering with no errors."""
        surface = pygame.Surface((1280, 720))
        for _ in range(60):
            self.world.update_physics(1.0)
            self.pheromones.update(1.0)
            self.colony.update(1.0)
            self.renderer.update(1.0)

        # Render full scene
        self.renderer.draw_sky(surface)
        self.renderer.draw_grass_and_surface(surface, 1.0)
        self.renderer.draw_terrain(surface, self.world)
        for ant in self.colony.ants:
            self.renderer.draw_ant(surface, ant)
        self.ui.draw(surface, self.colony, self.world)

    def test_threat_and_soldier_combat(self):
        """Verify threats spawn and soldiers attack them."""
        # Spawn threat near royal chamber
        rx, ry = self.world.royal_chamber_pos
        self.colony.spawn_threat(rx, ry - 30, "spider")
        self.assertEqual(len(self.colony.threats), 1)

        threat = self.colony.threats[0]
        initial_hp = threat.hp

        # Run 30 steps with a soldier nearby
        soldier = Ant(rx, ry - 30, caste=CASTE_SOLDIER, colony=self.colony)
        self.colony.ants.append(soldier)

        for _ in range(30):
            self.colony.update(1.0)
            threat.update(self.world, self.pheromones, self.colony.spatial_hash)

        # Soldier should have engaged and dealt damage
        self.assertLess(threat.hp, initial_hp)

    def test_surface_ground_hugging_no_flying(self):
        """Verify ants on surface are snapped to ground contour and never float into sky."""
        ant = Ant(x=250, y=50, caste=CASTE_WORKER, colony=self.colony) # In the sky
        self.colony.ants.append(ant)
        
        # Step movement
        ant._step_movement(1.0, self.world)
        
        ground_y = self.world.get_surface_y(ant.x)
        self.assertAlmostEqual(ant.y, ground_y - 2, delta=2.0)
        self.assertGreaterEqual(ant.y, 120, "Ant must hug ground line and never float into sky")

    def test_excavator_dig_streak(self):
        """Verify excavators carve dig streaks through solid earth."""
        # Find solid dirt near royal chamber
        rx, ry = self.world.royal_chamber_pos
        excavator = Ant(x=rx, y=ry, caste=CASTE_WORKER, colony=self.colony)
        excavator.subrole = "Excavator"
        excavator.dig_streak = 5
        excavator.dig_angle = 0.0 # Dig rightward
        
        # Count solid cells to the right before digging
        test_x = int(rx + 25)
        test_y = int(ry)
        
        for _ in range(6):
            excavator.update(1.0, self.world, self.pheromones, self.colony.spatial_hash, self.colony)
            
        # The excavator should have completed its streak and picked up dirt
        self.assertEqual(excavator.dig_streak, 0)
        self.assertEqual(excavator.cargo, 2) # CARGO_DIRT

    def test_natural_surface_food_spawning(self):
        """Verify natural seeds/berries spawn along surface grass."""
        surface_foods = [f for f in self.world.food_items if f.y <= 145]
        self.assertGreaterEqual(len(surface_foods), 3, "Initial surface food items should be present")

if __name__ == "__main__":
    unittest.main()
