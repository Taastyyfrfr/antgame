"""
world.py - Subterranean terrain, chunk caching, water percolation, and earth layers.
Manages a 2D cross-section world with 64x64 pixel chunk caching.
Implements 3-pixel border neighbor dirtying, moisture seepage, and starter chambers.
"""

import math
import random
from collections import deque
import numpy as np
import pygame

# Cell Types
CELL_AIR = 0
CELL_TOPSOIL = 1
CELL_LOAM = 2
CELL_CLAY = 3
CELL_STONE = 4
CELL_BEDROCK = 5
CELL_MOUND = 6

# Color palettes (Base colors before lighting/moisture)
PALETTE = {
    CELL_AIR: (38, 28, 22),       # Dark excavated background tunnel
    CELL_TOPSOIL: (102, 68, 45),   # Rich organic dark brown
    CELL_LOAM: (128, 85, 54),      # Warm earthy brown
    CELL_CLAY: (148, 86, 48),      # Terracotta / reddish clay
    CELL_STONE: (90, 85, 80),      # Dense grey mineral stone
    CELL_BEDROCK: (50, 48, 52),    # Deep impenetrable dark bedrock
    CELL_MOUND: (115, 78, 50),     # Excavated loose mound dirt
}

PALETTE_RGB = np.array([
    [38, 28, 22],   # CELL_AIR: Dark excavated background tunnel
    [102, 68, 45],  # CELL_TOPSOIL: Rich organic dark brown
    [128, 85, 54],  # CELL_LOAM: Warm earthy brown
    [148, 86, 48],  # CELL_CLAY: Terracotta / reddish clay
    [90, 85, 80],   # CELL_STONE: Dense grey mineral stone
    [50, 48, 52],   # CELL_BEDROCK: Deep impenetrable dark bedrock
    [115, 78, 50],  # CELL_MOUND: Excavated loose mound dirt
], dtype=np.float32)

SURFACE_Y = 130  # Top 18% of 720 is surface air (0 to 130)


class ExcavationBlueprint:
    """Manages an autonomous multi-step excavation project (shaft extension, side branch, chamber)."""
    def __init__(self, name, waypoints, chamber_radius=0):
        self.name = name
        self.waypoints = list(waypoints)
        self.chamber_radius = chamber_radius
        self.current_idx = 0
        self.completed = False

    def get_current_target(self, world):
        """Returns the active (x, y) target where solid dirt needs to be carved."""
        while self.current_idx < len(self.waypoints):
            tx, ty = self.waypoints[self.current_idx]
            if world.is_solid(tx, ty) and world.get_cell(tx, ty) != CELL_BEDROCK:
                return tx, ty
            has_solid = False
            for dx, dy in ((0, 6), (0, -6), (6, 0), (-6, 0)):
                if world.is_solid(tx + dx, ty + dy) and world.get_cell(tx + dx, ty + dy) != CELL_BEDROCK:
                    has_solid = True
                    return tx + dx, ty + dy
            if not has_solid:
                self.current_idx += 1
            else:
                return tx, ty

        # If waypoints carved, carve domed chamber at terminal point
        if self.chamber_radius > 0 and len(self.waypoints) > 0:
            cx, cy = self.waypoints[-1]
            for r in range(8, self.chamber_radius, 4):
                for ang in (0, 0.785, 1.57, 2.356, 3.141, 3.927, 4.712, 5.497):
                    tx = cx + math.cos(ang) * r
                    ty = cy + math.sin(ang) * (r * 0.6)
                    if world.is_solid(tx, ty) and world.get_cell(tx, ty) != CELL_BEDROCK:
                        return tx, ty

        self.completed = True
        return None


class World:
    def __init__(self, width=1280, height=720, cell_size=2, chunk_size_px=64):
        self.width = width
        self.height = height
        self.cell_size = cell_size
        self.chunk_size_px = chunk_size_px

        self.cols = width // cell_size
        self.rows = height // cell_size
        self.surface_row = SURFACE_Y // cell_size

        self.chunks_x = (width + chunk_size_px - 1) // chunk_size_px
        self.chunks_y = (height + chunk_size_px - 1) // chunk_size_px

        # Grid arrays (cols, rows)
        self.grid = np.zeros((self.cols, self.rows), dtype=np.uint8)
        self.moisture = np.zeros((self.cols, self.rows), dtype=np.float32)

        # Chunk management with SRCALPHA
        self.chunk_surfaces = []
        self.chunk_dirty = np.ones((self.chunks_x, self.chunks_y), dtype=bool)

        for cx in range(self.chunks_x):
            row_surfs = []
            for cy in range(self.chunks_y):
                w = min(chunk_size_px, self.width - cx * chunk_size_px)
                h = min(chunk_size_px, self.height - cy * chunk_size_px)
                row_surfs.append(pygame.Surface((w, h), pygame.SRCALPHA))
            self.chunk_surfaces.append(row_surfs)

        # Particles: harmless visual dust from digging, falling sand from God power, and water
        self.dust_particles = []  # list of [x, y, vx, vy, life] - visual only, never settles!
        self.falling_dirt = []    # list of [x, y, vx, vy] - heavy sand from God power TOOL_DIRT only
        self.water_droplets = []  # list of [x, y, vx, vy]
        self.food_items = []      # list of FoodItem objects
        self.surface_food_timer = 0.0
        self.total_carved_cells = 0

        # Navigation Flow Fields on the 4x4 Grid (320 x 180, 4x fewer cells than 640x360)
        self.nav_scale = 4
        self.nav_cols = width // self.nav_scale      # 320
        self.nav_rows = height // self.nav_scale     # 180
        self.nav_surface_row = SURFACE_Y // self.nav_scale # 32

        self.dist_to_surface = np.full((self.nav_cols, self.nav_rows), 99999, dtype=np.int32)
        self.dist_to_pantry = np.full((self.nav_cols, self.nav_rows), 99999, dtype=np.int32)
        self.dist_to_nursery = np.full((self.nav_cols, self.nav_rows), 99999, dtype=np.int32)
        self.dist_to_royal = np.full((self.nav_cols, self.nav_rows), 99999, dtype=np.int32)
        self.dist_to_dig = np.full((self.nav_cols, self.nav_rows), 99999, dtype=np.int32)

        self.nav_dirty = True
        self.nav_step_idx = 0
        self._dial_buckets = [deque() for _ in range(4)]

        # Autonomous excavation blueprints (deepening main shaft, branching tunnels, chambers)
        self.blueprints = [
            ExcavationBlueprint("Deep Shaft Extension", [
                (640, 465), (640, 490), (640, 515), (640, 545), (640, 575), (640, 605)
            ]),
            ExcavationBlueprint("Lower Nursery Branch (Right)", [
                (640, 475), (670, 495), (700, 515), (735, 530), (770, 540)
            ], chamber_radius=28),
            ExcavationBlueprint("Deep Granary Branch (Left)", [
                (640, 485), (610, 505), (580, 525), (545, 540), (510, 550)
            ], chamber_radius=26),
            ExcavationBlueprint("Mid-Level Gallery (Left)", [
                (640, 240), (600, 235), (560, 230), (520, 225), (480, 220)
            ], chamber_radius=22),
            ExcavationBlueprint("Mid-Level Gallery (Right)", [
                (640, 240), (680, 235), (720, 230), (760, 225), (800, 220)
            ], chamber_radius=22),
        ]
        self.dig_targets = [(640, 465)] # Fallback target

        # Generate world layers and starter colony
        self._generate_terrain()
        self._carve_starter_colony()
        self.mark_all_chunks_dirty()
        self.update_all_flow_fields()

    def _generate_terrain(self):
        """Generates cross-section subterranean layers with natural noise."""
        np.random.seed(42)
        for c in range(self.cols):
            # Surface slight rolling hill variation
            hill = int(math.sin(c * 0.03) * 4 + math.sin(c * 0.08) * 2)
            surf_r = self.surface_row + hill

            # Surface air above
            self.grid[c, :surf_r] = CELL_AIR

            # Layer heights
            topsoil_end = surf_r + 45
            loam_end = topsoil_end + 130
            clay_end = loam_end + 100
            bedrock_start = self.rows - 16

            # Assign soil types with blended noise boundaries
            for r in range(surf_r, self.rows):
                noise = int(np.random.randint(-3, 4))
                if r < topsoil_end + noise:
                    self.grid[c, r] = CELL_TOPSOIL
                elif r < loam_end + noise:
                    self.grid[c, r] = CELL_LOAM
                elif r < clay_end + noise:
                    self.grid[c, r] = CELL_CLAY
                elif r >= bedrock_start:
                    self.grid[c, r] = CELL_BEDROCK
                else:
                    # Deep stone pockets
                    if np.random.rand() < 0.12:
                        self.grid[c, r] = CELL_STONE
                    else:
                        self.grid[c, r] = CELL_CLAY

        # Random deep stone boulders
        for _ in range(14):
            bx = np.random.randint(40, self.cols - 40)
            by = np.random.randint(self.surface_row + 100, self.rows - 25)
            br = np.random.randint(8, 20)
            self._fill_circle(bx * self.cell_size, by * self.cell_size, br * self.cell_size, CELL_STONE, carve_bedrock=False)

    def _carve_starter_colony(self):
        """
        Pre-carves starter colony architecture:
        - Surface entrance with starter mound
        - Main descending tunnel
        - Royal chamber for the Queen (deep and protected)
        - Nursery chamber for brood
        - Food pantry storage chamber
        """
        center_x = self.width // 2 # 640
        surf_y = SURFACE_Y

        # 1. Entrance crater / mound
        self.carve_circle(center_x, surf_y, 14, play_effects=False)
        self.carve_circle(center_x - 10, surf_y + 8, 12, play_effects=False)

        # Deposit starter mound dirt flanks around entrance
        for dx in range(-45, -14):
            h = int(12 * math.exp(-((dx + 25) ** 2) / 100))
            for dy in range(h):
                self.set_pixel(center_x + dx, surf_y - dy, CELL_MOUND)
        for dx in range(14, 45):
            h = int(12 * math.exp(-((dx - 25) ** 2) / 100))
            for dy in range(h):
                self.set_pixel(center_x + dx, surf_y - dy, CELL_MOUND)

        # 2. Main shaft winding down to depth
        curr_x = center_x
        for y in range(surf_y, 420, 4):
            curr_x += int(math.sin(y * 0.04) * 2)
            self.carve_circle(curr_x, y, 11, play_effects=False)

        # 3. Royal Chamber (deep at Y ~ 430)
        royal_x, royal_y = curr_x, 440
        self.carve_ellipse(royal_x, royal_y, 42, 24, play_effects=False)
        self.royal_chamber_pos = (royal_x, royal_y)

        # 4. Nursery Chamber (to the right, Y ~ 330)
        nursery_x, nursery_y = curr_x + 90, 330
        self.carve_tunnel(curr_x, 340, nursery_x, nursery_y, radius=8)
        self.carve_ellipse(nursery_x, nursery_y, 34, 20, play_effects=False)
        self.nursery_chamber_pos = (nursery_x, nursery_y)

        # 5. Food Storage Pantry (to the left, Y ~ 310)
        pantry_x, pantry_y = curr_x - 90, 310
        self.carve_tunnel(curr_x, 320, pantry_x, pantry_y, radius=8)
        self.carve_ellipse(pantry_x, pantry_y, 36, 20, play_effects=False)
        self.food_storage_pos = (pantry_x, pantry_y)

        # Pre-seed pantry with a few food drops
        self.drop_food(pantry_x - 10, pantry_y + 4, amount=25, food_type="sugar")
        self.drop_food(pantry_x + 12, pantry_y + 4, amount=20, food_type="seed")

        # Pre-seed natural surface food items (seeds and berries) along surface grass
        for sx in (200, 390, 580, 700, 880, 1070):
            sy = self.get_surface_y(sx) - 3
            ft = "seed" if sx % 2 == 0 else "fruit"
            self.drop_food(sx, sy, amount=random.randint(20, 35), food_type=ft)

        # Reset total carved cells counter so it tracks only post-generation digging
        self.total_carved_cells = 0

    def carve_tunnel(self, x1, y1, x2, y2, radius=8):
        """Carves a continuous tubular tunnel between two points."""
        dist = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(dist / 3))
        for s in range(steps + 1):
            t = s / steps
            px = x1 + (x2 - x1) * t
            py = y1 + (y2 - y1) * t
            self.carve_circle(px, py, radius, play_effects=False)

    def carve_ellipse(self, cx, cy, rx, ry, play_effects=False):
        """Carves a horizontal oblong room/chamber."""
        for dy in range(-ry, ry + 1):
            max_dx = int(rx * math.sqrt(max(0, 1.0 - (dy / ry) ** 2)))
            for dx in range(-max_dx, max_dx + 1):
                self.carve_pixel(cx + dx, cy + dy, play_effects=play_effects)

    def mark_chunk_dirty_at_pixel(self, px, py, border_margin_px=3):
        """
        Marks chunk containing (px, py) dirty.
        If within border_margin_px of a 64x64 chunk boundary,
        also marks adjacent neighbor chunk(s) dirty for seamless rim shading.
        """
        px = int(px)
        py = int(py)
        cx = px // self.chunk_size_px
        cy = py // self.chunk_size_px

        if 0 <= cx < self.chunks_x and 0 <= cy < self.chunks_y:
            self.chunk_dirty[cx, cy] = True

            # Border checks within chunk
            rel_x = px % self.chunk_size_px
            rel_y = py % self.chunk_size_px

            # Left neighbor
            if rel_x < border_margin_px and cx > 0:
                self.chunk_dirty[cx - 1, cy] = True
            # Right neighbor
            if rel_x >= self.chunk_size_px - border_margin_px and cx < self.chunks_x - 1:
                self.chunk_dirty[cx + 1, cy] = True
            # Top neighbor
            if rel_y < border_margin_px and cy > 0:
                self.chunk_dirty[cx, cy - 1] = True
            # Bottom neighbor
            if rel_y >= self.chunk_size_px - border_margin_px and cy < self.chunks_y - 1:
                self.chunk_dirty[cx, cy + 1] = True
            # Diagonal corner neighbors
            if rel_x < border_margin_px and rel_y < border_margin_px and cx > 0 and cy > 0:
                self.chunk_dirty[cx - 1, cy - 1] = True
            if rel_x >= self.chunk_size_px - border_margin_px and rel_y < border_margin_px and cx < self.chunks_x - 1 and cy > 0:
                self.chunk_dirty[cx + 1, cy - 1] = True
            if rel_x < border_margin_px and rel_y >= self.chunk_size_px - border_margin_px and cx > 0 and cy < self.chunks_y - 1:
                self.chunk_dirty[cx - 1, cy + 1] = True
            if rel_x >= self.chunk_size_px - border_margin_px and rel_y >= self.chunk_size_px - border_margin_px and cx < self.chunks_x - 1 and cy < self.chunks_y - 1:
                self.chunk_dirty[cx + 1, cy + 1] = True

    def mark_all_chunks_dirty(self):
        self.chunk_dirty.fill(True)

    def is_solid(self, px, py):
        """Returns True if the world pixel is inside solid terrain."""
        if px < 0 or px >= self.width or py >= self.height:
            return True
        if py < 0:
            return False
        col = int(px // self.cell_size)
        row = int(py // self.cell_size)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return self.grid[col, row] != CELL_AIR
        return True

    def get_surface_y(self, px):
        """Returns the y-coordinate of the highest solid ground pixel at horizontal position px near the surface."""
        col = int(max(0, min(self.width - 1, px)) // self.cell_size)
        max_r = min(self.rows, self.surface_row + 16)
        for r in range(0, max_r):
            if self.grid[col, r] != CELL_AIR:
                return r * self.cell_size
        return SURFACE_Y

    def _get_nav_masks(self):
        """Builds open air mask and boundary border mask on the 4x4 nav grid (320x180)."""
        sub = (self.grid == CELL_AIR)
        open_mask = sub[0::2, 0::2] | sub[1::2, 0::2] | sub[0::2, 1::2] | sub[1::2, 1::2]
        open_mask[:, :self.nav_surface_row] = False

        solid = ~open_mask
        is_border = np.zeros((self.nav_cols, self.nav_rows), dtype=bool)
        border = open_mask[1:-1, 1:-1] & (
            solid[:-2, 1:-1] | solid[2:, 1:-1] | solid[1:-1, :-2] | solid[1:-1, 2:]
        )
        is_border[1:-1, 1:-1] = border
        return open_mask, is_border

    def update_all_flow_fields(self):
        """Recomputes all 5 flow fields synchronously on 4x4 grid (used at startup / forced)."""
        open_mask, is_border = self._get_nav_masks()
        self._fill_dials(self.dist_to_surface, self.nav_cols // 2, self.nav_surface_row, open_mask, is_border)

        px, py = self.food_storage_pos
        self._fill_dials(self.dist_to_pantry, int(px // self.nav_scale), int(py // self.nav_scale), open_mask, is_border)

        nx, ny = self.nursery_chamber_pos
        self._fill_dials(self.dist_to_nursery, int(nx // self.nav_scale), int(ny // self.nav_scale), open_mask, is_border)

        rx, ry = self.royal_chamber_pos
        self._fill_dials(self.dist_to_royal, int(rx // self.nav_scale), int(ry // self.nav_scale), open_mask, is_border)

        targets = self.get_active_dig_targets()
        self._fill_dials_multi(self.dist_to_dig, targets, open_mask, is_border)

        self.nav_dirty = False
        self.nav_step_idx = 0

    def update_flow_fields(self, force=False):
        """Called externally; if force is True, updates all immediately."""
        if force:
            self.update_all_flow_fields()
        else:
            self.step_flow_fields()

    def step_flow_fields(self):
        """Staggers updates across frames: updates at most ONE flow field per frame when nav_dirty is True."""
        if not self.nav_dirty:
            return

        open_mask, is_border = self._get_nav_masks()

        if self.nav_step_idx == 0:
            self._fill_dials(self.dist_to_surface, self.nav_cols // 2, self.nav_surface_row, open_mask, is_border)
        elif self.nav_step_idx == 1:
            px, py = self.food_storage_pos
            self._fill_dials(self.dist_to_pantry, int(px // self.nav_scale), int(py // self.nav_scale), open_mask, is_border)
        elif self.nav_step_idx == 2:
            nx, ny = self.nursery_chamber_pos
            self._fill_dials(self.dist_to_nursery, int(nx // self.nav_scale), int(ny // self.nav_scale), open_mask, is_border)
        elif self.nav_step_idx == 3:
            rx, ry = self.royal_chamber_pos
            self._fill_dials(self.dist_to_royal, int(rx // self.nav_scale), int(ry // self.nav_scale), open_mask, is_border)
        elif self.nav_step_idx == 4:
            targets = self.get_active_dig_targets()
            self._fill_dials_multi(self.dist_to_dig, targets, open_mask, is_border)

        self.nav_step_idx += 1
        if self.nav_step_idx >= 5:
            self.nav_step_idx = 0
            self.nav_dirty = False

    def _fill_dials(self, dist_arr, target_c, target_r, open_mask, is_border):
        """Dial's algorithm on the 4x4 nav grid (320x180)."""
        dist_arr.fill(99999)
        surf_r = self.nav_surface_row

        target_c = max(1, min(self.nav_cols - 2, target_c))
        target_r = max(surf_r, min(self.nav_rows - 2, target_r))

        if not open_mask[target_c, target_r]:
            found = False
            for r_dist in range(1, 10):
                for dc in range(-r_dist, r_dist + 1):
                    for dr in range(-r_dist, r_dist + 1):
                        nc, nr = target_c + dc, target_r + dr
                        if 1 <= nc < self.nav_cols - 1 and surf_r <= nr < self.nav_rows - 1:
                            if open_mask[nc, nr]:
                                target_c, target_r = nc, nr
                                found = True
                                break
                    if found:
                        break
                if found:
                    break
            if not found:
                return

        for b in self._dial_buckets:
            b.clear()

        dist_arr[target_c, target_r] = 0
        self._dial_buckets[0].append((target_c, target_r))
        idx = 0
        active = 1
        dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))

        while active > 0:
            b_idx = idx % 4
            b = self._dial_buckets[b_idx]
            if not b:
                idx += 1
                continue
            c, r = b.popleft()
            active -= 1
            d = dist_arr[c, r]
            if d < idx:
                continue

            for dc, dr in dirs:
                nc, nr = c + dc, r + dr
                if 0 <= nc < self.nav_cols and surf_r <= nr < self.nav_rows and open_mask[nc, nr]:
                    step_cost = 3 if is_border[nc, nr] else 1
                    nd = d + step_cost
                    if nd < dist_arr[nc, nr]:
                        dist_arr[nc, nr] = nd
                        self._dial_buckets[nd % 4].append((nc, nr))
                        active += 1

    def _fill_dials_multi(self, dist_arr, targets, open_mask, is_border):
        """Multi-source Dial BFS initializing multiple active dig targets at distance 0."""
        dist_arr.fill(99999)
        surf_r = self.nav_surface_row

        for b in self._dial_buckets:
            b.clear()

        active = 0
        for tx, ty in targets:
            tc = int(tx // self.nav_scale)
            tr = int(ty // self.nav_scale)
            tc = max(1, min(self.nav_cols - 2, tc))
            tr = max(surf_r, min(self.nav_rows - 2, tr))

            if not open_mask[tc, tr]:
                for r_dist in range(1, 10):
                    found = False
                    for dc in range(-r_dist, r_dist + 1):
                        for dr in range(-r_dist, r_dist + 1):
                            nc, nr = tc + dc, tr + dr
                            if 1 <= nc < self.nav_cols - 1 and surf_r <= nr < self.nav_rows - 1 and open_mask[nc, nr]:
                                tc, tr = nc, nr
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break

            if open_mask[tc, tr] and dist_arr[tc, tr] > 0:
                dist_arr[tc, tr] = 0
                self._dial_buckets[0].append((tc, tr))
                active += 1

        if active == 0:
            return

        idx = 0
        dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
        while active > 0:
            b_idx = idx % 4
            b = self._dial_buckets[b_idx]
            if not b:
                idx += 1
                continue
            c, r = b.popleft()
            active -= 1
            d = dist_arr[c, r]
            if d < idx:
                continue

            for dc, dr in dirs:
                nc, nr = c + dc, r + dr
                if 0 <= nc < self.nav_cols and surf_r <= nr < self.nav_rows and open_mask[nc, nr]:
                    step_cost = 3 if is_border[nc, nr] else 1
                    nd = d + step_cost
                    if nd < dist_arr[nc, nr]:
                        dist_arr[nc, nr] = nd
                        self._dial_buckets[nd % 4].append((nc, nr))
                        active += 1

    def get_flow_direction(self, px, py, target_name="surface"):
        """
        Samples 8 neighboring cells on the 4x4 grid (320x180) around (px, py).
        Returns a smooth unit steering vector (vx, vy, dist) toward the lowest-distance open neighbor.
        """
        if target_name == "surface":
            dist_map = self.dist_to_surface
        elif target_name == "pantry":
            dist_map = self.dist_to_pantry
        elif target_name == "nursery":
            dist_map = self.dist_to_nursery
        elif target_name == "dig":
            dist_map = self.dist_to_dig
        else: # "royal"
            dist_map = self.dist_to_royal

        col = int(px // self.nav_scale)
        row = int(py // self.nav_scale)

        if not (0 <= col < self.nav_cols and 0 <= row < self.nav_rows):
            return 0.0, -1.0, 99999

        curr_d = dist_map[col, row]
        best_d = curr_d
        best_dc = 0
        best_dr = 0

        # Sample 8 neighbor cells
        for ndc, ndr in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            nc = col + ndc
            nr = row + ndr
            if 0 <= nc < self.nav_cols and 0 <= nr < self.nav_rows:
                d = dist_map[nc, nr]
                if d < best_d:
                    best_d = d
                    best_dc = ndc
                    best_dr = ndr

        if best_dc == 0 and best_dr == 0:
            return 0.0, -1.0, curr_d

        length = math.hypot(best_dc, best_dr)
        vx = best_dc / length
        vy = best_dr / length

        # Slight organic wobble (-0.11 to +0.11 rad) so trails look natural
        angle = math.atan2(vy, vx) + random.uniform(-0.11, 0.11)
        return math.cos(angle), math.sin(angle), best_d

    def get_active_dig_targets(self):
        """Returns the list of active excavation targets across current blueprints."""
        targets = []
        for bp in self.blueprints:
            if not bp.completed:
                t = bp.get_current_target(self)
                if t:
                    targets.append(t)

        if not targets:
            # Fallback: project a new target deeper down
            lowest_y = 550
            for y in range(460, self.height - 30, 8):
                if not self.is_solid(640, y):
                    lowest_y = max(lowest_y, y)
            new_target = (640, min(self.height - 30, lowest_y + 14))
            targets.append(new_target)

        return targets

    def get_active_dig_target(self, ant_id=0):
        """Returns an assigned excavation target for a specific excavator based on its ID."""
        targets = self.get_active_dig_targets()
        return targets[ant_id % len(targets)]

    def get_cell(self, px, py):
        col = int(px // self.cell_size)
        row = int(py // self.cell_size)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return self.grid[col, row]
        return CELL_BEDROCK

    def set_pixel(self, px, py, cell_type):
        col = int(px // self.cell_size)
        row = int(py // self.cell_size)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            if self.grid[col, row] != cell_type:
                self.grid[col, row] = cell_type
                self.mark_chunk_dirty_at_pixel(px, py)

    def carve_pixel(self, px, py, play_effects=True):
        """Carves a single world pixel into air if not bedrock."""
        col = int(px // self.cell_size)
        row = int(py // self.cell_size)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            cell = self.grid[col, row]
            if cell != CELL_AIR and cell != CELL_BEDROCK:
                self.grid[col, row] = CELL_AIR
                self.mark_chunk_dirty_at_pixel(px, py)
                self.nav_dirty = True
                self.total_carved_cells += 1
                if play_effects and random.random() < 0.25:
                    self.add_dust(px, py)
                return True
        return False

    def fill_pixel(self, px, py, cell_type=CELL_LOAM):
        """Fills a single world pixel with soil."""
        col = int(px // self.cell_size)
        row = int(py // self.cell_size)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            if self.grid[col, row] == CELL_AIR:
                self.grid[col, row] = cell_type
                self.mark_chunk_dirty_at_pixel(px, py)
                self.nav_dirty = True
                return True
        return False

    def carve_circle(self, cx, cy, radius, play_effects=True):
        """Carves a circular region around (cx, cy)."""
        cx, cy, radius = int(cx), int(cy), int(radius)
        r_sq = radius * radius
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= r_sq:
                    self.carve_pixel(cx + dx, cy + dy, play_effects=play_effects)

    def fill_circle(self, cx, cy, radius, cell_type=CELL_LOAM):
        """Fills a circular region with soil."""
        cx, cy, radius = int(cx), int(cy), int(radius)
        r_sq = radius * radius
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= r_sq:
                    self.fill_pixel(cx + dx, cy + dy, cell_type=cell_type)

    def _fill_circle(self, cx, cy, radius, cell_type, carve_bedrock=False):
        cx, cy, radius = int(cx), int(cy), int(radius)
        r_sq = radius * radius
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= r_sq:
                    col = int((cx + dx) // self.cell_size)
                    row = int((cy + dy) // self.cell_size)
                    if 0 <= col < self.cols and 0 <= row < self.rows:
                        if carve_bedrock or self.grid[col, row] != CELL_BEDROCK:
                            self.grid[col, row] = cell_type
                            self.mark_chunk_dirty_at_pixel(cx + dx, cy + dy)

    def drop_food(self, px, py, amount=20, food_type="sugar"):
        """Spawns food at pixel position."""
        self.food_items.append(FoodItem(px, py, amount=amount, food_type=food_type))

    def add_pantry_food(self, amount=1, food_type="sugar"):
        """Adds a food drop neatly spread across the flat floor of the pantry chamber."""
        px, py = self.food_storage_pos
        drop_x = px + random.uniform(-26, 26)
        drop_y = py + 6
        self.drop_food(drop_x, drop_y, amount=amount, food_type=food_type)

    def add_water_drop(self, px, py):
        """Adds a seeping water droplet."""
        self.water_droplets.append([px, py, random.uniform(-0.2, 0.2), random.uniform(1.0, 2.5)])

    def add_falling_dirt(self, px, py):
        """Adds falling loose dirt grain (heavy sand from God power TOOL_DIRT)."""
        self.falling_dirt.append([px, py, random.uniform(-0.3, 0.3), random.uniform(1.2, 3.0)])

    def add_dust(self, px, py):
        """Adds harmless visual dust particle that fades out over ~20 ticks without settling into solid earth."""
        self.dust_particles.append([
            float(px + random.uniform(-2, 2)),
            float(py + random.uniform(-2, 2)),
            random.uniform(-0.6, 0.6),
            random.uniform(0.4, 1.4),
            20.0
        ])

    def update_physics(self, dt=1.0):
        """Updates falling dirt, settling sand, and water droplet percolation."""
        # 0. Harmless visual dust particles from ant excavation (never settle into solid dirt)
        kept_dust = []
        for d in self.dust_particles:
            d[0] += d[2]
            d[1] += d[3]
            d[3] = min(3.0, d[3] + 0.08) # gentle gravity
            d[4] -= dt # life countdown
            if d[4] > 0 and 0 <= int(d[0]) < self.width and 0 <= int(d[1]) < self.height:
                if not self.is_solid(d[0], d[1]):
                    kept_dust.append(d)
        self.dust_particles = kept_dust

        # 1. Falling dirt grains (heavy sand from God power TOOL_DIRT that settles into CELL_MOUND)
        kept_dirt = []
        for p in self.falling_dirt:
            p[0] += p[2]
            p[1] += p[3]
            p[3] = min(6.0, p[3] + 0.15) # gravity

            ix, iy = int(p[0]), int(p[1])
            if iy >= self.height - 4 or self.is_solid(ix, iy):
                # Settle into loose soil
                settle_y = iy - 1
                if not self.is_solid(ix, settle_y):
                    self.fill_pixel(ix, settle_y, CELL_MOUND)
                elif not self.is_solid(ix - 1, settle_y):
                    self.fill_pixel(ix - 1, settle_y, CELL_MOUND)
                elif not self.is_solid(ix + 1, settle_y):
                    self.fill_pixel(ix + 1, settle_y, CELL_MOUND)
            elif 0 <= ix < self.width and 0 <= iy < self.height:
                kept_dirt.append(p)
        self.falling_dirt = kept_dirt

        # 2. Water droplets & moisture percolation
        kept_water = []
        for w in self.water_droplets:
            w[0] += w[2]
            w[1] += w[3]
            w[3] = min(4.0, w[3] + 0.1)

            ix, iy = int(w[0]), int(w[1])
            col = int(ix // self.cell_size)
            row = int(iy // self.cell_size)

            if 0 <= col < self.cols and 0 <= row < self.rows:
                if self.grid[col, row] != CELL_AIR:
                    # Absorb moisture into soil cell
                    self.moisture[col, row] = min(1.0, self.moisture[col, row] + 0.4)
                    self.mark_chunk_dirty_at_pixel(ix, iy)
                elif iy >= self.height - 4:
                    pass # Evaporate at bedrock floor
                else:
                    kept_water.append(w)
            elif iy < self.height:
                kept_water.append(w)
        self.water_droplets = kept_water

        # 3. Moisture percolation downwards through porous earth
        if random.random() < 0.2:
            wet_cols = np.random.randint(0, self.cols, size=40)
            wet_rows = np.random.randint(self.surface_row, self.rows - 1, size=40)
            for c, r in zip(wet_cols, wet_rows):
                m = self.moisture[c, r]
                if m > 0.05:
                    # Percolate down
                    below = r + 1
                    if below < self.rows and self.grid[c, below] != CELL_BEDROCK:
                        transfer = m * 0.15
                        self.moisture[c, r] -= transfer
                        self.moisture[c, below] = min(1.0, self.moisture[c, below] + transfer)
                        self.mark_chunk_dirty_at_pixel(c * self.cell_size, r * self.cell_size)

        # 4. Food physics (gravity drop if suspended in air)
        for f in self.food_items:
            f.update(self)

        # Clean depleted food
        self.food_items = [f for f in self.food_items if f.amount > 0]

        # 5. Natural surface food replenishment (fallen seeds / berries)
        self.surface_food_timer += dt * 0.033
        if self.surface_food_timer >= 22.0:
            self.surface_food_timer = 0.0
            surface_food_count = sum(1 for f in self.food_items if f.y <= SURFACE_Y + 15)
            if surface_food_count < 6:
                # Random location along grass (avoiding directly over the entrance crater 620-660)
                spawn_x = random.choice([
                    random.uniform(60, 580),
                    random.uniform(700, self.width - 60)
                ])
                spawn_y = self.get_surface_y(spawn_x) - 4
                food_type = "seed" if random.random() < 0.6 else "fruit"
                self.drop_food(spawn_x, spawn_y, amount=random.randint(18, 30), food_type=food_type)

        # 6. Staggered Flow Field Updates (at most ONE BFS field per frame when dirty)
        if self.nav_dirty:
            self.step_flow_fields()

    def render_dirty_chunks(self):
        """Vectorized offscreen chunk rendering with NumPy array operations (no per-cell draw.rect)."""
        c_px = self.chunk_size_px
        cells_per_chunk = c_px // self.cell_size

        for cx in range(self.chunks_x):
            for cy in range(self.chunks_y):
                if not self.chunk_dirty[cx, cy]:
                    continue

                surf = self.chunk_surfaces[cx][cy]
                start_c = cx * cells_per_chunk
                start_r = cy * cells_per_chunk
                end_c = min(self.cols, start_c + cells_per_chunk)
                end_r = min(self.rows, start_r + cells_per_chunk)

                cw = end_c - start_c
                ch = end_r - start_r

                if cw <= 0 or ch <= 0:
                    self.chunk_dirty[cx, cy] = False
                    continue

                chunk_grid = self.grid[start_c:end_c, start_r:end_r]
                chunk_moist = self.moisture[start_c:end_c, start_r:end_r]

                # 1. Base colors from vectorized LUT
                colors = PALETTE_RGB[chunk_grid].copy()

                is_solid = (chunk_grid != CELL_AIR)
                rows_grid = np.arange(start_r, end_r)[None, :]
                is_sky = (~is_solid) & (rows_grid < self.surface_row)

                # 2. 1-cell rim shadow along subterranean tunnel walls
                pad_grid = np.zeros((cw + 2, ch + 2), dtype=np.uint8)
                pad_grid[1:-1, 1:-1] = chunk_grid
                if start_c > 0:
                    pad_grid[0, 1:-1] = self.grid[start_c - 1, start_r:end_r]
                if end_c < self.cols:
                    pad_grid[-1, 1:-1] = self.grid[end_c, start_r:end_r]
                if start_r > 0:
                    pad_grid[1:-1, 0] = self.grid[start_c:end_c, start_r - 1]
                if end_r < self.rows:
                    pad_grid[1:-1, -1] = self.grid[start_c:end_c, end_r]

                solid_neighbors = (
                    (pad_grid[:-2, 1:-1] != CELL_AIR) |
                    (pad_grid[2:, 1:-1] != CELL_AIR) |
                    (pad_grid[1:-1, :-2] != CELL_AIR) |
                    (pad_grid[1:-1, 2:] != CELL_AIR)
                )
                rim_mask = (~is_solid) & (~is_sky) & solid_neighbors
                colors[rim_mask] = [25, 18, 14]

                # 3. Moisture darkening for solid earth
                has_moisture = is_solid & (chunk_moist > 0.05)
                factor = np.maximum(0.55, 1.0 - chunk_moist * 0.45)
                colors[has_moisture] *= factor[has_moisture, None]

                # 4. Procedural grain variation
                c_indices = np.arange(start_c, end_c)[:, None]
                grain = (((c_indices * 37 + rows_grid * 19) % 11) - 5).astype(np.float32)
                colors[is_solid] += grain[is_solid, None]

                # 5. Output arrays
                final_rgb = np.clip(colors, 0, 255).astype(np.uint8)
                alpha = np.full((cw, ch), 255, dtype=np.uint8)
                alpha[is_sky] = 0

                # 6. Blit & scale to chunk surface
                temp_surf = pygame.Surface((cw, ch), pygame.SRCALPHA)
                pygame.surfarray.blit_array(temp_surf, final_rgb)
                alpha_view = pygame.surfarray.pixels_alpha(temp_surf)
                alpha_view[:, :] = alpha
                del alpha_view

                dest_w = cw * self.cell_size
                dest_h = ch * self.cell_size
                pygame.transform.scale(temp_surf, (dest_w, dest_h), surf)

                self.chunk_dirty[cx, cy] = False


class FoodItem:
    """Represents a piece of food (sugar, seed, fruit) in the world."""
    def __init__(self, x, y, amount=25, food_type="sugar"):
        self.x = float(x)
        self.y = float(y)
        self.amount = amount
        self.max_amount = amount
        self.food_type = food_type
        self.color = (245, 245, 230) if food_type == "sugar" else (170, 215, 80) if food_type == "seed" else (220, 70, 90)

    def update(self, world):
        """Falls downward through air until resting on solid ground."""
        if not world.is_solid(self.x, self.y + 2):
            self.y += 1.5
            if world.is_solid(self.x, self.y):
                self.y -= 1.0

    def draw(self, surface):
        radius = max(2, int(2 + 4 * (self.amount / self.max_amount)))
        ix, iy = int(self.x), int(self.y)
        pygame.draw.circle(surface, self.color, (ix, iy), radius)
        # Specular glint
        pygame.draw.circle(surface, (255, 255, 255), (ix - 1, iy - 1), max(1, radius // 2))
