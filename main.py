"""
main.py - Entry point and main loop for the lightweight ambient 2D Ant Colony Simulator.
Runs with fixed 1280x720 internal canvas via pygame.SCALED for Wayland/X11 compatibility.
Features 30 FPS default, 60 FPS toggle, 15 FPS Eco Background mode on focus loss.
"""

import sys
import math
import random
import pygame
import numpy as np

from world import World
from pheromones import PheromoneGrid, LAYER_FOOD, LAYER_DANGER
from ants import AntColony, CARGO_FOOD
from renderer import Renderer
from ui import (
    UI, TOOL_FOOD, TOOL_RAIN, TOOL_DIG, TOOL_DIRT,
    TOOL_PHEROMONE, TOOL_THREAT, TOOL_INSPECT
)

WIDTH = 1280
HEIGHT = 720

def main():
    # Initialize Pygame with SCALED flag for seamless Wayland/X11 scaling
    pygame.init()
    pygame.display.set_caption("Ant Colony Simulator - Ambient Desktop")

    flags = pygame.SCALED | pygame.RESIZABLE
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
    canvas = pygame.Surface((WIDTH, HEIGHT))

    clock = pygame.time.Clock()

    # Core systems
    world = World(width=WIDTH, height=HEIGHT, cell_size=2, chunk_size_px=64)
    pheromones = PheromoneGrid(world_width=WIDTH, world_height=HEIGHT, cell_size=4)
    colony = AntColony(world=world, pheromones=pheromones)
    renderer = Renderer(width=WIDTH, height=HEIGHT)
    ui = UI(width=WIDTH, height=HEIGHT)

    # State & FPS throttle
    target_fps = 30
    user_target_fps = 30 # Can be toggled between 30 and 60
    eco_mode = False
    show_pheromones = False
    fullscreen = False

    mouse_down = False
    mouse_button = 1

    running = True
    sim_accum = 0.0
    fixed_dt = 1.0 / 30.0 # Standard simulation step

    while running:
        # Measure delta time
        raw_dt_ms = clock.tick(target_fps)
        dt = min(raw_dt_ms / 1000.0, 0.1) # Clamp delta time against large pauses
        ui.fps = clock.get_fps()

        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # Wayland / X11 Focus Loss for Eco Background Throttling
            elif event.type == pygame.WINDOWFOCUSLOST:
                eco_mode = True
                ui.eco_mode = True
                target_fps = 15
            elif event.type == pygame.WINDOWFOCUSGAINED:
                eco_mode = False
                ui.eco_mode = False
                target_fps = user_target_fps
            elif event.type == pygame.ACTIVEEVENT:
                if hasattr(event, "gain") and hasattr(event, "state"):
                    # Fallback focus tracking for older SDL
                    if event.state & 2: # Window focus
                        eco_mode = not event.gain
                        ui.eco_mode = eco_mode
                        target_fps = 15 if eco_mode else user_target_fps

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_h:
                    ui.toggle_visibility()
                elif event.key == pygame.K_v:
                    show_pheromones = not show_pheromones
                elif event.key == pygame.K_f:
                    # Toggle 30 FPS / 60 FPS
                    user_target_fps = 60 if user_target_fps == 30 else 30
                    if not eco_mode:
                        target_fps = user_target_fps
                elif event.key == pygame.K_SPACE:
                    # Toggle Pause / 1x
                    cur = ui.get_current_speed()
                    ui.set_speed(1.0 if cur == 0.0 else 0.0)
                elif event.key == pygame.K_F11:
                    # Fullscreen toggle
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((WIDTH, HEIGHT), flags | pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
                # Tool hotkeys 1-7
                elif event.key in (pygame.K_1, pygame.K_KP1):
                    ui.active_tool = TOOL_FOOD
                elif event.key in (pygame.K_2, pygame.K_KP2):
                    ui.active_tool = TOOL_RAIN
                elif event.key in (pygame.K_3, pygame.K_KP3):
                    ui.active_tool = TOOL_DIG
                elif event.key in (pygame.K_4, pygame.K_KP4):
                    ui.active_tool = TOOL_DIRT
                elif event.key in (pygame.K_5, pygame.K_KP5):
                    ui.active_tool = TOOL_PHEROMONE
                elif event.key in (pygame.K_6, pygame.K_KP6):
                    ui.active_tool = TOOL_THREAT
                elif event.key in (pygame.K_7, pygame.K_KP7):
                    ui.active_tool = TOOL_INSPECT

            elif event.type == pygame.MOUSEWHEEL:
                ui.adjust_brush(event.y)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button in (1, 3):
                    mouse_down = True
                    mouse_button = event.button
                    # First check if UI dock was clicked
                    if not ui.handle_click(event.pos):
                        # Apply god power once on initial click
                        apply_tool(ui.active_tool, event.pos, ui.brush_radius, mouse_button, world, pheromones, colony, ui)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button in (1, 3):
                    mouse_down = False

        # Continuous drag application for tools (Dig, Fill, Rain, Food, Pheromone)
        mouse_pos = pygame.mouse.get_pos()
        if mouse_down and not (ui.visible and (ui.dock_rect.collidepoint(mouse_pos) or ui.stats_rect.collidepoint(mouse_pos))):
            if ui.active_tool in (TOOL_FOOD, TOOL_RAIN, TOOL_DIG, TOOL_DIRT, TOOL_PHEROMONE):
                apply_tool(ui.active_tool, mouse_pos, ui.brush_radius, mouse_button, world, pheromones, colony, ui)

        # Simulation updates with speed multiplier
        speed_mult = ui.get_current_speed()
        if speed_mult > 0.0:
            sim_dt = min(dt * speed_mult, 0.15)
            # Update world physics (falling dirt, water seepage, food settling)
            world.update_physics(sim_dt * 30.0)

            # Update pheromones (vectorized numpy diffusion and evaporation)
            pheromones.update(sim_dt * 30.0)

            # Update ant colony simulation (AI, brood, threats)
            colony.update(sim_dt * 30.0)

            # Update ambient sky & particles
            renderer.update(sim_dt * 30.0)

        # Rendering pipeline
        # 1. Sky & Celestion arc
        renderer.draw_sky(canvas)

        # 2. Swaying grass and ambient surface pollen
        renderer.draw_grass_and_surface(canvas, pygame.time.get_ticks() / 1000.0)

        # 3. Subterranean earth chunks (cached surfaces with 3px seamless boundary rim shading)
        renderer.draw_terrain(canvas, world)

        # 4. Atmospheric sunbeams near tunnel entrance
        renderer.draw_sunlight_shafts(canvas)

        # 5. Pheromone Heatmap Overlay (if toggled on with 'V')
        if show_pheromones:
            pheromones.render_overlay(canvas)

        # 6. Brood (eggs, larvae, pupae in nursery)
        for b in colony.brood:
            b.draw(canvas)

        # 7. Falling dirt grains, water drops, and food morsels
        renderer.draw_particles(canvas, world)

        # 8. Threats (beetles, spiders)
        for threat in colony.threats:
            threat.draw(canvas)

        # 9. Procedural segmented ants
        followed_ant = ui.inspected_ant if (ui.inspected_ant and ui.inspected_ant.alive) else None
        for ant in colony.ants:
            is_followed = (ant == followed_ant)
            renderer.draw_ant(canvas, ant, followed=is_followed)

        # 10. UI Dock, stats, inspector, and brush cursor
        ui.draw(canvas, colony, world)
        ui.draw_brush_cursor(canvas, mouse_pos)

        # Blit canvas to screen
        screen.blit(canvas, (0, 0))
        pygame.display.flip()

    pygame.quit()
    sys.exit(0)


def apply_tool(tool_id, pos, radius, button, world, pheromones, colony, ui):
    """Executes the active god power tool at position."""
    mx, my = pos

    if tool_id == TOOL_FOOD:
        # Drop food crumbs
        food_type = "sugar" if button == 1 else "seed" if random.random() < 0.5 else "fruit"
        # Spawn within brush radius
        for _ in range(max(1, radius // 10)):
            ox = mx + random.uniform(-radius * 0.6, radius * 0.6)
            oy = my + random.uniform(-radius * 0.6, radius * 0.6)
            world.drop_food(ox, oy, amount=random.randint(15, 30), food_type=food_type)

    elif tool_id == TOOL_RAIN:
        # Pour water droplets that seep into soil
        for _ in range(max(2, radius // 5)):
            ox = mx + random.uniform(-radius, radius)
            oy = my + random.uniform(-radius, radius)
            world.add_water_drop(ox, oy)

    elif tool_id == TOOL_DIG:
        # Carve circular tunnel / room (respects bedrock)
        world.carve_circle(mx, my, radius, play_effects=True)

    elif tool_id == TOOL_DIRT:
        # Drop loose falling dirt
        for _ in range(max(2, radius // 4)):
            ox = mx + random.uniform(-radius * 0.7, radius * 0.7)
            oy = my + random.uniform(-radius * 0.7, radius * 0.7)
            world.add_falling_dirt(ox, oy)

    elif tool_id == TOOL_PHEROMONE:
        # Paint FOOD (Left Click) or DANGER (Right Click)
        layer = LAYER_FOOD if button == 1 else LAYER_DANGER
        amount = 40.0
        grid_r = max(1, radius // 4)
        pheromones.deposit(mx, my, layer_idx=layer, amount=amount, radius=grid_r)

    elif tool_id == TOOL_THREAT:
        # Spawn small beetle (button 1) or agile spider (button 3)
        ttype = "beetle" if button == 1 else "spider"
        colony.spawn_threat(mx, my, threat_type=ttype)

    elif tool_id == TOOL_INSPECT:
        # Find closest ant within radius
        closest_ant = None
        min_d = radius + 15
        for ant in colony.ants:
            d = math.hypot(ant.x - mx, ant.y - my)
            if d < min_d:
                min_d = d
                closest_ant = ant
        ui.inspected_ant = closest_ant

if __name__ == "__main__":
    main()
