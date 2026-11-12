"""
ui.py - Minimalist HUD dock, god power tools, inspection overlay, and brush controls.
"""

import math
import pygame

TOOL_FOOD = 1
TOOL_RAIN = 2
TOOL_DIG = 3
TOOL_DIRT = 4
TOOL_PHEROMONE = 5
TOOL_THREAT = 6
TOOL_INSPECT = 7

TOOL_NAMES = {
    TOOL_FOOD: "1: Food Drop",
    TOOL_RAIN: "2: Rain / Water",
    TOOL_DIG: "3: Excavate",
    TOOL_DIRT: "4: Fill Dirt",
    TOOL_PHEROMONE: "5: Pheromone",
    TOOL_THREAT: "6: Spawn Threat",
    TOOL_INSPECT: "7: Inspect Ant",
}

class UI:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.visible = True # Toggle with 'H'
        self.active_tool = TOOL_FOOD
        self.brush_radius = 16
        self.min_brush = 6
        self.max_brush = 48

        self.speed_multipliers = [0.0, 1.0, 2.0, 4.0] # 0 = Pause
        self.speed_index = 1 # Default 1x

        self.inspected_ant = None
        self.eco_mode = False
        self.fps = 30.0

        # UI fonts
        pygame.font.init()
        self.font = pygame.font.SysFont("DejaVu Sans, Liberation Sans, sans-serif", 13)
        self.font_bold = pygame.font.SysFont("DejaVu Sans, Liberation Sans, sans-serif", 13, bold=True)
        self.font_title = pygame.font.SysFont("DejaVu Sans, Liberation Sans, sans-serif", 15, bold=True)

        # Tool buttons layout (Top Left corner)
        self.dock_rect = pygame.Rect(14, 14, 300, 160)
        self.stats_rect = pygame.Rect(width - 250, 14, 236, 160)

    def toggle_visibility(self):
        self.visible = not self.visible

    def cycle_speed(self):
        self.speed_index = (self.speed_index + 1) % len(self.speed_multipliers)

    def set_speed(self, mult):
        if mult in self.speed_multipliers:
            self.speed_index = self.speed_multipliers.index(mult)

    def get_current_speed(self):
        return self.speed_multipliers[self.speed_index]

    def adjust_brush(self, delta):
        self.brush_radius = max(self.min_brush, min(self.max_brush, self.brush_radius + delta * 3))

    def handle_click(self, mouse_pos):
        """Checks if a UI button in the dock or stats bar was clicked."""
        if not self.visible:
            return False

        mx, my = mouse_pos
        # Check tool buttons in dock
        if self.dock_rect.collidepoint(mx, my):
            # 7 tool buttons in 2 columns
            rel_y = my - self.dock_rect.y - 30
            row = rel_y // 24
            rel_x = mx - self.dock_rect.x - 10
            col = 0 if rel_x < 135 else 1
            idx = row * 2 + col + 1
            if 1 <= idx <= 7:
                self.active_tool = idx
            return True

        # Check speed controls
        speed_bar = pygame.Rect(self.dock_rect.x + 10, self.dock_rect.bottom - 32, 280, 24)
        if speed_bar.collidepoint(mx, my):
            slot = (mx - speed_bar.x) // 70
            if 0 <= slot < 4:
                self.speed_index = slot
            return True

        return False

    def draw(self, surface, colony, world):
        if not self.visible:
            # Subtle minimal indicator in bottom-right corner
            hint_txt = self.font.render("Press 'H' for UI Dock | 'V' Pheromones", True, (200, 200, 200))
            hint_bg = pygame.Surface((hint_txt.get_width() + 10, hint_txt.get_height() + 6), pygame.SRCALPHA)
            hint_bg.fill((20, 20, 24, 140))
            surface.blit(hint_bg, (self.width - hint_txt.get_width() - 20, self.height - 28))
            surface.blit(hint_txt, (self.width - hint_txt.get_width() - 15, self.height - 25))
            return

        # 1. Left Dock: Tools & Controls
        dock_surf = pygame.Surface((self.dock_rect.width, self.dock_rect.height), pygame.SRCALPHA)
        dock_surf.fill((24, 22, 28, 205))
        pygame.draw.rect(dock_surf, (80, 75, 90), (0, 0, self.dock_rect.width, self.dock_rect.height), 1, border_radius=8)

        # Title
        title_txt = self.font_title.render("🐜 Ant Colony Simulator", True, (255, 235, 190))
        dock_surf.blit(title_txt, (12, 8))

        # Tool Buttons (Grid 2 cols)
        tools = [
            (1, "1: Food", TOOL_FOOD),
            (2, "2: Rain", TOOL_RAIN),
            (3, "3: Dig", TOOL_DIG),
            (4, "4: Dirt", TOOL_DIRT),
            (5, "5: Phero", TOOL_PHEROMONE),
            (6, "6: Threat", TOOL_THREAT),
            (7, "7: Inspect", TOOL_INSPECT),
        ]

        for i, label, tid in tools:
            col = (i - 1) % 2
            row = (i - 1) // 2
            bx = 10 + col * 140
            by = 32 + row * 23
            btn_rect = pygame.Rect(bx, by, 132, 20)

            is_active = (self.active_tool == tid)
            btn_bg = (70, 95, 135) if is_active else (40, 36, 44)
            pygame.draw.rect(dock_surf, btn_bg, (bx, by, 132, 20), border_radius=4)
            if is_active:
                pygame.draw.rect(dock_surf, (255, 225, 120), (bx, by, 132, 20), 1, border_radius=4)

            txt = self.font_bold.render(label, True, (255, 255, 255) if is_active else (190, 190, 195))
            dock_surf.blit(txt, (bx + 8, by + 3))

        # Speed Controls bar
        speed_y = self.dock_rect.height - 30
        speeds = [("PAUSE", 0.0), ("1x", 1.0), ("2x", 2.0), ("4x", 4.0)]
        for s_idx, (s_label, s_val) in enumerate(speeds):
            sx = 10 + s_idx * 70
            is_cur = (self.speed_index == s_idx)
            s_bg = (120, 80, 50) if is_cur else (45, 40, 48)
            pygame.draw.rect(dock_surf, s_bg, (sx, speed_y, 65, 18), border_radius=3)
            if is_cur:
                pygame.draw.rect(dock_surf, (255, 200, 110), (sx, speed_y, 65, 18), 1, border_radius=3)
            stxt = self.font_bold.render(s_label, True, (255, 255, 255) if is_cur else (160, 160, 165))
            dock_surf.blit(stxt, (sx + 10, speed_y + 2))

        surface.blit(dock_surf, self.dock_rect.topleft)

        # 2. Right Dock: Colony Statistics & Eco Mode Indicator
        stats = colony.get_stats()
        stats_surf = pygame.Surface((self.stats_rect.width, self.stats_rect.height), pygame.SRCALPHA)
        stats_surf.fill((24, 22, 28, 205))
        pygame.draw.rect(stats_surf, (80, 75, 90), (0, 0, self.stats_rect.width, self.stats_rect.height), 1, border_radius=8)

        # Colony Header & Eco Badge
        h_txt = self.font_bold.render("Colony Status", True, (255, 235, 190))
        stats_surf.blit(h_txt, (10, 8))

        eco_label = "ECO: 15 FPS" if self.eco_mode else f"{int(self.fps)} FPS"
        eco_col = (110, 220, 130) if self.eco_mode else (220, 220, 120)
        fps_txt = self.font_bold.render(eco_label, True, eco_col)
        stats_surf.blit(fps_txt, (self.stats_rect.width - fps_txt.get_width() - 10, 8))

        # Metrics rows
        lines = [
            f"Ants: {stats['total_ants']} (W:{stats['workers']} S:{stats['soldiers']} Q:1)",
            f"Roles: {stats['foragers']} Foragers, {stats['excavators']} Diggers, {stats['nurses']} Nurses",
            f"Brood: {stats['eggs']} eggs, {stats['larvae']} larvae, {stats['pupae']} pupae",
            f"Food Stockpile: {stats['food']} units",
            f"Max Tunnel Depth: {stats['max_depth']} px",
            f"Brush: {self.brush_radius}px (Scroll to resize)"
        ]

        for li, line in enumerate(lines):
            txt = self.font.render(line, True, (215, 215, 220))
            stats_surf.blit(txt, (10, 30 + li * 20))

        surface.blit(stats_surf, self.stats_rect.topleft)

        # 3. Inspected Ant Detail Panel (if active)
        if self.inspected_ant and self.inspected_ant.alive:
            ant = self.inspected_ant
            ins_surf = pygame.Surface((220, 95), pygame.SRCALPHA)
            ins_surf.fill((30, 28, 38, 225))
            pygame.draw.rect(ins_surf, (240, 200, 100), (0, 0, 220, 95), 1, border_radius=6)

            caste_desc = f"{ant.caste} ({ant.subrole})" if ant.caste == "Worker" else ant.caste
            cargo_name = "Food Crumb" if ant.cargo == 1 else "Dirt Pellet" if ant.cargo == 2 else "Brood Egg" if ant.cargo == 3 else "None"
            ant_info = [
                f"Ant ID: {id(ant) % 10000} - {caste_desc}",
                f"State: {ant.state}",
                f"Health: {int(ant.health)}%  Energy: {int(ant.energy)}%",
                f"Carrying: {cargo_name}"
            ]
            for li, info in enumerate(ant_info):
                c = (255, 225, 120) if li == 0 else (220, 220, 225)
                itxt = self.font_bold.render(info, True, c) if li == 0 else self.font.render(info, True, c)
                ins_surf.blit(itxt, (8, 6 + li * 21))

            surface.blit(ins_surf, (self.dock_rect.x, self.dock_rect.bottom + 12))

    def draw_brush_cursor(self, surface, mouse_pos):
        """Draws glowing reticle showing tool brush diameter."""
        if not self.visible:
            return

        mx, my = mouse_pos
        # If over dock or stats, do not draw brush reticle
        if self.dock_rect.collidepoint(mx, my) or self.stats_rect.collidepoint(mx, my):
            return

        color = (255, 255, 255)
        if self.active_tool == TOOL_FOOD:
            color = (255, 240, 120)
        elif self.active_tool == TOOL_RAIN:
            color = (130, 210, 255)
        elif self.active_tool == TOOL_DIG:
            color = (255, 120, 120)
        elif self.active_tool == TOOL_DIRT:
            color = (190, 140, 90)
        elif self.active_tool == TOOL_PHEROMONE:
            color = (110, 255, 180)
        elif self.active_tool == TOOL_THREAT:
            color = (255, 70, 70)
        elif self.active_tool == TOOL_INSPECT:
            color = (255, 220, 80)

        pygame.draw.circle(surface, color, (mx, my), self.brush_radius, 1)
        pygame.draw.line(surface, color, (mx - 3, my), (mx + 3, my), 1)
        pygame.draw.line(surface, color, (mx, my - 3), (mx, my + 3), 1)
