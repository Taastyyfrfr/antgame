"""
test_behavior.py - Mandatory behavioral verification test across 400 ticks.
Verifies:
1. Total dirt cells excavated > 50
2. Total food bites delivered to stockpile > 0
3. Average distance traveled by workers > 40px
"""

import os
import sys
import numpy as np

os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
pygame.init()

from world import World
from pheromones import PheromoneGrid
from ants import AntColony

def run_behavioral_verification():
    print("=== Running 400-Tick Behavioral Verification ===")
    world = World(width=1280, height=720, cell_size=2, chunk_size_px=64)
    pheromones = PheromoneGrid(world_width=1280, world_height=720, cell_size=4)
    colony = AntColony(world=world, pheromones=pheromones)

    # Run for 400 simulation ticks
    for tick in range(400):
        world.update_physics(1.0)
        pheromones.update(1.0)
        colony.update(1.0)

    workers = [a for a in colony.ants if a.caste == "Worker"]
    avg_distance = float(np.mean([a.distance_traveled for a in workers])) if workers else 0.0
    dirt_excavated = world.total_carved_cells
    food_delivered = colony.total_food_delivered
    mound_cells = int(np.sum(world.grid == 6))

    print(f"Results across 400 simulation ticks:")
    print(f"  Total dirt cells excavated:     {dirt_excavated}")
    print(f"  Anthill mound cells built:       {mound_cells}")
    print(f"  Total food bites delivered:      {food_delivered}")
    print(f"  Average distance per worker:     {avg_distance:.1f} px")
    print(f"  Current food stockpile:          {colony.food_stockpile}")

    # Assertions
    assert dirt_excavated > 50, f"Expected dirt_excavated > 50, got {dirt_excavated}"
    assert food_delivered > 0, f"Expected food_delivered > 0, got {food_delivered}"
    assert avg_distance > 40.0, f"Expected avg_distance > 40.0, got {avg_distance:.1f}"

    print("ALL BEHAVIORAL VERIFICATION METRICS PASSED!")
    return True

if __name__ == "__main__":
    success = run_behavioral_verification()
    sys.exit(0 if success else 1)
