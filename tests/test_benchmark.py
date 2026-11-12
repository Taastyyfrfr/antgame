"""
test_benchmark.py - Performance benchmark under 300+ active ants and full simulation load.
"""

import os
import time
import numpy as np

os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
pygame.init()

from world import World
from pheromones import PheromoneGrid
from ants import AntColony, Ant, CASTE_WORKER, CASTE_SOLDIER
from renderer import Renderer

def run_benchmark(ticks=500, ant_count=300):
    print(f"=== Ant Colony Simulator Performance Benchmark ===")
    print(f"Testing {ant_count} active ants for {ticks} simulation frames...")

    world = World(width=1280, height=720, cell_size=2, chunk_size_px=64)
    pheromones = PheromoneGrid(world_width=1280, world_height=720, cell_size=4)
    colony = AntColony(world=world, pheromones=pheromones)
    renderer = Renderer(width=1280, height=720)
    screen_surf = pygame.Surface((1280, 720))

    # Spawn up to ant_count
    while len(colony.ants) < ant_count:
        rx, ry = world.royal_chamber_pos
        caste = CASTE_SOLDIER if np.random.rand() < 0.15 else CASTE_WORKER
        colony.ants.append(Ant(rx + np.random.uniform(-40, 40), ry + np.random.uniform(-30, 20), caste=caste, colony=colony))

    # Warmup
    for _ in range(30):
        world.update_physics(1.0)
        pheromones.update(1.0)
        colony.update(1.0)

    # Timing breakdown
    t_physics = 0.0
    t_phero = 0.0
    t_ants = 0.0
    t_render = 0.0

    start_total = time.perf_counter()

    for tick in range(ticks):
        # 1. Physics
        t0 = time.perf_counter()
        world.update_physics(1.0)
        t_physics += time.perf_counter() - t0

        # 2. Pheromone Diffusion
        t0 = time.perf_counter()
        pheromones.update(1.0)
        t_phero += time.perf_counter() - t0

        # 3. Colony & Ants AI
        t0 = time.perf_counter()
        colony.update(1.0)
        t_ants += time.perf_counter() - t0

        # 4. Rendering
        t0 = time.perf_counter()
        renderer.draw_sky(screen_surf)
        renderer.draw_grass_and_surface(screen_surf, tick * 0.033)
        renderer.draw_terrain(screen_surf, world)
        for ant in colony.ants:
            renderer.draw_ant(screen_surf, ant)
        t_render += time.perf_counter() - t0

    total_time = time.perf_counter() - start_total
    avg_ms = (total_time / ticks) * 1000.0
    effective_fps = ticks / total_time

    print(f"Results across {ticks} frames:")
    print(f"  Total time:       {total_time:.3f} s")
    print(f"  Average ms/frame: {avg_ms:.2f} ms")
    print(f"  Maximum potential FPS: {effective_fps:.1f} FPS")
    print(f"Timing Breakdown per Frame:")
    print(f"  - World Physics:      {(t_physics / ticks) * 1000.0:.2f} ms")
    print(f"  - Pheromone NumPy:    {(t_phero / ticks) * 1000.0:.2f} ms")
    print(f"  - Ant AI ({len(colony.ants)} ants): {(t_ants / ticks) * 1000.0:.2f} ms")
    print(f"  - Rendering pipeline: {(t_render / ticks) * 1000.0:.2f} ms")

    assert avg_ms < 25.0, f"Average frame time {avg_ms:.2f}ms exceeds 25ms threshold for 30/60 FPS!"
    print("Benchmark PASSED: Outstanding efficiency for ambient background operation.")

if __name__ == "__main__":
    run_benchmark()
