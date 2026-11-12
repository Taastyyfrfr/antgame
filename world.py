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

SURFACE_Y = 130  # Top 18% of 720 is surface air (0 to 130)

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

        # Chunk management
        self.chunk_surfaces = []
        self.chunk_dirty = np.ones((self.chunks_x, self.chunks_y), dtype=bool)

        for cx in range(self.chunks_x):
            row_surfs = []
            for cy in range(self.chunks_y):
                w = min(chunk_size_px, self.width - cx * chunk_size_px)
                h = min(chunk_size_px, self.height - cy * chunk_size_px)
                row_surfs.append(pygame.Surface((w, h)))
            self.chunk_surfaces.append(row_surfs)

        # Falling particles: dirt grains and water drops
        self.falling_dirt = []  # list of [x, y, vx, vy]
        self.water_droplets = [] # list of [x, y, vx, vy]
        self.food_items = []    # list of FoodItem objects
        self.surface_food_timer = 0.0
        self.total_carved_cells = 0

        # Navigation Flow Fields on the exact 2x2 World Grid (640 x 360)
        self.dist_to_surface = np.full((self.cols, self.rows), 99999, dtype=np.int32)
        self.dist_to_pantry = np.full((self.cols, self.rows), 99999, dtype=np.int32)
        self.dist_to_nursery = np.full((self.cols, self.rows), 99999, dtype=np.int32)
        self.dist_to_royal = np.full((self.cols, self.rows), 99999, dtype=np.int32)
        self.dist_to_dig = np.full((self.cols, self.rows), 99999, dtype=np.int32)
        self.nav_dirty = True
        self.nav_timer = 0
        self._dial_buckets = [deque() for _ in range(4)]

        # Planned colony excavation targets (deepening shaft, chambers, side pockets)
        self.dig_targets = [
            (640, 465),
            (640, 505),
            (640, 545),
            (600, 440),
            (680, 440),
            (480, 380),
            (800, 380),
            (810, 330),
            (470, 310)
        ]

        # Generate world layers and starter colony
        self._generate_terrain()
        self._carve_starter_colony()
        self.mark_all_chunks_dirty()
        self.update_flow_fields(force=True)

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

    def update_flow_fields(self, force=False):
        """
        Recomputes centerline-weighted subterranean flow fields directly on the 2x2 world grid (640x360).
        Open cells adjacent to solid dirt receive a higher cost (+3) than centerline cells (+1),
        naturally routing ants down the exact middle of narrow tunnels without wall scraping.
        Runs only when terrain is modified (dirty) or forced.
        """
        if not self.nav_dirty and not force:
            return
        self.nav_dirty = False

        surf_r = self.surface_row

        # 1. Open mask of subterranean air cells
        open_mask = (self.grid == CELL_AIR)
        open_mask[:, :surf_r] = False

        # 2. Vectorized boundary detection: open air cells adjacent to solid earth
        solid = (self.grid != CELL_AIR)
        is_border = np.zeros((self.cols, self.rows), dtype=bool)
        border = open_mask[1:-1, 1:-1] & (
            solid[:-2, 1:-1] | solid[2:, 1:-1] | solid[1:-1, :-2] | solid[1:-1, 2:]
        )
        is_border[1:-1, 1:-1] = border

        # 3. Surface entrance flow field (target at crater entrance: col=320, row=surf_r)
        self._fill_dials(self.dist_to_surface, 320, surf_r, open_mask, is_border)

        # 4. Food pantry flow field
        px, py = self.food_storage_pos
        self._fill_dials(self.dist_to_pantry, int(px // self.cell_size), int(py // self.cell_size), open_mask, is_border)

        # 5. Nursery flow field
        nx, ny = self.nursery_chamber_pos
        self._fill_dials(self.dist_to_nursery, int(nx // self.cell_size), int(ny // self.cell_size), open_mask, is_border)

        # 6. Royal chamber flow field
        rx, ry = self.royal_chamber_pos
        self._fill_dials(self.dist_to_royal, int(rx // self.cell_size), int(ry // self.cell_size), open_mask, is_border)

        # 7. Excavation dig target flow field
        dtx, dty = self.get_active_dig_target()
        self._fill_dials(self.dist_to_dig, int(dtx // self.cell_size), int(dty // self.cell_size), open_mask, is_border)

    def _fill_dials(self, dist_arr, target_c, target_r, open_mask, is_border):
        """Dial's algorithm for centerline-weighted integer-distance BFS on the 2x2 grid."""
        dist_arr.fill(99999)
        surf_r = self.surface_row

        target_c = max(1, min(self.cols - 2, target_c))
        target_r = max(surf_r, min(self.rows - 2, target_r))

        # If designated target cell is solid dirt, find nearest open air cell
        if not open_mask[target_c, target_r]:
            found = False
            for r_dist in range(1, 15):
                for dc in range(-r_dist, r_dist + 1):
                    for dr in range(-r_dist, r_dist + 1):
                        nc, nr = target_c + dc, target_r + dr
                        if 1 <= nc < self.cols - 1 and surf_r <= nr < self.rows - 1:
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
                if 0 <= nc < self.cols and surf_r <= nr < self.rows and open_mask[nc, nr]:
                    # Centerline weight: 3 if next to wall, 1 if open center
                    step_cost = 3 if is_border[nc, nr] else 1
                    nd = d + step_cost
                    if nd < dist_arr[nc, nr]:
                        dist_arr[nc, nr] = nd
                        self._dial_buckets[nd % 4].append((nc, nr))
                        active += 1

    def get_flow_direction(self, px, py, target_name="surface"):
        """
        Samples 8 neighboring cells on the exact 2x2 grid around (px, py).
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

        col = int(px // self.cell_size)
        row = int(py // self.cell_size)

        if not (0 <= col < self.cols and 0 <= row < self.rows):
            return 0.0, -1.0, 99999

        curr_d = dist_map[col, row]
        best_d = curr_d
        best_dc = 0
        best_dr = 0

        # Sample 8 neighbor cells
        for ndc, ndr in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            nc = col + ndc
            nr = row + ndr
            if 0 <= nc < self.cols and 0 <= nr < self.rows:
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

    def get_active_dig_target(self):
        """Returns the current expansion excavation target (tx, ty) with solid dirt."""
        for tx, ty in self.dig_targets:
            # Check if there is still solid diggable dirt around target
            has_solid = False
            for r in range(0, 14, 2):
                if self.is_solid(tx, ty + r) and self.get_cell(tx, ty + r) != 5:
                    has_solid = True
                    return tx, ty + r
                if self.is_solid(tx + r, ty) and self.get_cell(tx + r, ty) != 5:
                    has_solid = True
                    return tx + r, ty

        # If all initial targets carved, create deeper shaft target
        lowest_y = 550
        for y in range(460, self.height - 30, 8):
            if not self.is_solid(640, y):
                lowest_y = max(lowest_y, y)
        new_target = (640, min(self.height - 30, lowest_y + 14))
        self.dig_targets.append(new_target)
        return new_target

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
                if play_effects and random.random() < 0.2:
                    self.falling_dirt.append([px, py, random.uniform(-0.5, 0.5), random.uniform(0.5, 2.0)])
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

    def add_water_drop(self, px, py):
        """Adds a seeping water droplet."""
        self.water_droplets.append([px, py, random.uniform(-0.2, 0.2), random.uniform(1.0, 2.5)])

    def add_falling_dirt(self, px, py):
        """Adds falling loose dirt grain."""
        self.falling_dirt.append([px, py, random.uniform(-0.3, 0.3), random.uniform(1.2, 3.0)])

    def update_physics(self, dt=1.0):
        """Updates falling dirt, settling sand, and water droplet percolation."""
        # 1. Falling dirt grains
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

        # 6. Periodic Flow Field Updates (if terrain was modified)
        self.nav_timer += 1
        if self.nav_dirty and self.nav_timer >= 15:
            self.update_flow_fields()
            self.nav_timer = 0

    def render_dirty_chunks(self):
        """Renders only dirty chunks onto their offscreen surfaces."""
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

                # Clear surface
                surf.fill((0, 0, 0, 0))

                for c in range(start_c, end_c):
                    rel_x = (c - start_c) * self.cell_size
                    for r in range(start_r, end_r):
                        rel_y = (r - start_r) * self.cell_size
                        cell = self.grid[c, r]

                        if cell == CELL_AIR:
                            if r < self.surface_row:
                                # Sky air is completely transparent in chunk surface
                                continue
                            else:
                                # Dug subterranean tunnel background with ambient occlusion
                                # Check proximity to solid walls for rim shadow
                                has_solid_neighbor = False
                                for dc, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                                    nc, nr = c + dc, r + dr
                                    if 0 <= nc < self.cols and 0 <= nr < self.rows:
                                        if self.grid[nc, nr] != CELL_AIR:
                                            has_solid_neighbor = True
                                            break

                                if has_solid_neighbor:
                                    # Darker rim shadow along tunnel walls
                                    color = (25, 18, 14)
                                else:
                                    color = PALETTE[CELL_AIR]

                                pygame.draw.rect(surf, color, (rel_x, rel_y, self.cell_size, self.cell_size))
                        else:
                            # Solid soil cell
                            base_color = list(PALETTE[cell])

                            # Moisture darkens the soil
                            m = self.moisture[c, r]
                            if m > 0.05:
                                factor = max(0.55, 1.0 - m * 0.45)
                                base_color[0] = int(base_color[0] * factor)
                                base_color[1] = int(base_color[1] * factor)
                                base_color[2] = int(base_color[2] * factor)

                            # Subtle procedural grain variation
                            grain = ((c * 37 + r * 19) % 11) - 5
                            col_r = min(255, max(0, base_color[0] + grain))
                            col_g = min(255, max(0, base_color[1] + grain))
                            col_b = min(255, max(0, base_color[2] + grain))

                            pygame.draw.rect(surf, (col_r, col_g, col_b), (rel_x, rel_y, self.cell_size, self.cell_size))

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
