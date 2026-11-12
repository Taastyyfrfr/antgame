"""
renderer.py - High-fidelity cross-section renderer for the 2D ant colony simulator.
Handles day/night sky cycle, swaying grass blades, cached terrain blitting,
procedural segmented ants with articulated 6-leg walk cycles, and particle effects.
"""

import math
import random
import pygame

class Renderer:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.surface_y = 130

        # Day/Night atmospheric cycle (0.0 to 1.0, 1.0 = full cycle ~ 240 seconds)
        self.time_of_day = 0.25 # starts at mid-morning
        self.cycle_speed = 0.002 # smooth transition

        # Procedural grass along surface
        self.grass_blades = []
        random.seed(1337)
        for x in range(0, width, 4):
            height_var = random.randint(8, 18)
            curve = random.uniform(-2.0, 2.0)
            green_val = random.randint(110, 175)
            color = (random.randint(60, 95), green_val, random.randint(35, 65))
            self.grass_blades.append({"x": x, "h": height_var, "c": curve, "color": color, "phase": random.uniform(0, 6.28)})

        # Ambient dust and pollen particles
        self.pollen_particles = []
        for _ in range(45):
            self.pollen_particles.append({
                "x": random.uniform(0, width),
                "y": random.uniform(10, self.surface_y + 10),
                "vx": random.uniform(0.2, 0.7),
                "vy": random.uniform(-0.15, 0.15),
                "radius": random.uniform(1.0, 2.2),
                "alpha": random.randint(80, 180)
            })

        # Pre-calculated sky colors (Dawn, Noon, Sunset, Night)
        self.sky_dawn_top = (110, 70, 115)
        self.sky_dawn_bot = (235, 145, 95)

        self.sky_noon_top = (75, 140, 215)
        self.sky_noon_bot = (165, 205, 245)

        self.sky_dusk_top = (65, 45, 95)
        self.sky_dusk_bot = (225, 95, 60)

        self.sky_night_top = (10, 14, 28)
        self.sky_night_bot = (22, 28, 48)

        # Stars in night sky
        self.stars = []
        for _ in range(70):
            self.stars.append((random.randint(0, width), random.randint(0, self.surface_y - 15), random.uniform(0.5, 1.8)))

        # Ant leg phase offsets for alternating tripod gait (legs 0..5)
        # Left side: 0 (front), 1 (mid), 2 (rear)
        # Right side: 3 (front), 4 (mid), 5 (rear)
        self.tripod_offsets = [0.0, math.pi, 0.0, math.pi, 0.0, math.pi]

    def update(self, dt=1.0):
        """Advances day/night cycle and ambient particles."""
        self.time_of_day = (self.time_of_day + self.cycle_speed * dt * 0.08) % 1.0

        # Update ambient pollen floating across surface
        for p in self.pollen_particles:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt + math.sin(p["x"] * 0.02) * 0.1
            if p["x"] > self.width:
                p["x"] = 0
                p["y"] = random.uniform(10, self.surface_y)

    def _get_sky_colors(self):
        """Calculates interpolated top and bottom colors for the sky gradient."""
        t = self.time_of_day
        if t < 0.25: # Night to Dawn
            f = t / 0.25
            top = self._lerp_color(self.sky_night_top, self.sky_dawn_top, f)
            bot = self._lerp_color(self.sky_night_bot, self.sky_dawn_bot, f)
        elif t < 0.5: # Dawn to Noon
            f = (t - 0.25) / 0.25
            top = self._lerp_color(self.sky_dawn_top, self.sky_noon_top, f)
            bot = self._lerp_color(self.sky_dawn_bot, self.sky_noon_bot, f)
        elif t < 0.75: # Noon to Dusk
            f = (t - 0.5) / 0.25
            top = self._lerp_color(self.sky_noon_top, self.sky_dusk_top, f)
            bot = self._lerp_color(self.sky_noon_bot, self.sky_dusk_bot, f)
        else: # Dusk to Night
            f = (t - 0.75) / 0.25
            top = self._lerp_color(self.sky_dusk_top, self.sky_night_top, f)
            bot = self._lerp_color(self.sky_dusk_bot, self.sky_night_bot, f)
        return top, bot

    @staticmethod
    def _lerp_color(c1, c2, factor):
        f = max(0.0, min(1.0, factor))
        return (
            int(c1[0] + (c2[0] - c1[0]) * f),
            int(c1[1] + (c2[1] - c1[1]) * f),
            int(c1[2] + (c2[2] - c1[2]) * f),
        )

    def draw_sky(self, surface):
        """Renders sky gradient, celestial bodies, and stars."""
        top_c, bot_c = self._get_sky_colors()

        # Vertical sky gradient
        sky_rect_h = self.surface_y + 10
        for y in range(0, sky_rect_h, 2):
            factor = y / sky_rect_h
            col = self._lerp_color(top_c, bot_c, factor)
            pygame.draw.line(surface, col, (0, y), (self.width, y), 2)

        # Stars during dusk and night
        night_intensity = max(0.0, math.cos(self.time_of_day * math.pi * 2))
        if night_intensity > 0.1:
            star_alpha = int(night_intensity * 230)
            for sx, sy, sr in self.stars:
                pygame.draw.circle(surface, (240, 240, 255), (sx, sy), int(sr))

        # Sun / Moon arc
        angle = self.time_of_day * math.pi * 2
        sun_x = int(self.width * 0.5 - math.cos(angle) * (self.width * 0.45))
        sun_y = int(self.surface_y * 0.75 - math.sin(angle) * (self.surface_y * 0.65))

        if math.sin(angle) > -0.1:
            # Sun
            pygame.draw.circle(surface, (255, 240, 190), (sun_x, sun_y), 11)
            pygame.draw.circle(surface, (255, 250, 225), (sun_x, sun_y), 8)
        else:
            # Moon (opposite sun)
            moon_x = int(self.width * 0.5 + math.cos(angle) * (self.width * 0.45))
            moon_y = int(self.surface_y * 0.75 + math.sin(angle) * (self.surface_y * 0.65))
            pygame.draw.circle(surface, (220, 230, 245), (moon_x, moon_y), 9)
            pygame.draw.circle(surface, top_c, (moon_x + 3, moon_y - 2), 7) # Moon crescent

    def draw_grass_and_surface(self, surface, time_sec):
        """Draws procedural swaying grass along the surface dirt line."""
        wind = math.sin(time_sec * 1.8) * 4.0
        for g in self.grass_blades:
            sway = wind + math.sin(time_sec * 2.5 + g["phase"]) * 3.0 + g["c"]
            base_x = g["x"]
            base_y = self.surface_y
            tip_x = base_x + sway
            tip_y = base_y - g["h"]
            pygame.draw.line(surface, g["color"], (base_x, base_y), (int(tip_x), int(tip_y)), 2)

        # Ambient floating dust / pollen
        for p in self.pollen_particles:
            pygame.draw.circle(surface, (255, 250, 210), (int(p["x"]), int(p["y"])), int(p["radius"]))

    def draw_sunlight_shafts(self, surface):
        """Soft atmospheric sunlight shafts filtering into the main tunnel entrance."""
        top_c, _ = self._get_sky_colors()
        if self.time_of_day > 0.2 and self.time_of_day < 0.8:
            # Daytime light shafts
            shaft_surf = pygame.Surface((120, 160), pygame.SRCALPHA)
            poly = [(40, 0), (80, 0), (120, 160), (0, 160)]
            pygame.draw.polygon(shaft_surf, (255, 245, 200, 18), poly)
            surface.blit(shaft_surf, (640 - 60, self.surface_y - 10))

    def draw_terrain(self, surface, world):
        """Blits cached subterranean chunk surfaces (dirty chunks are refreshed)."""
        world.render_dirty_chunks()
        c_px = world.chunk_size_px

        for cx in range(world.chunks_x):
            px = cx * c_px
            for cy in range(world.chunks_y):
                py = cy * c_px
                # Only subterranean or surface-intersecting chunks need blitting
                if py + c_px >= self.surface_y - 10:
                    surface.blit(world.chunk_surfaces[cx][cy], (px, py))

    def draw_ant(self, surface, ant, followed=False):
        """
        Draws an articulated, segmented procedural ant:
        - Head with dual angled antennae and mandibles
        - Mesosoma (thorax)
        - Petiole & Metasoma (gaster with segmented abdomen bands)
        - 6 articulated legs executing natural walk cycles
        - Carried items (food crumb or dirt pellet)
        """
        ix, iy = ant.x, ant.y
        ang = ant.angle
        cos_a = math.cos(ang)
        sin_a = math.sin(ang)
        norm_x = -sin_a
        norm_y = cos_a

        # 1. Articulated Legs (6 legs, 3 pairs)
        leg_color = (45, 24, 16)
        leg_len1 = ant.length * 0.45
        leg_len2 = ant.length * 0.40

        for i in range(6):
            side = -1 if i < 3 else 1
            pair_idx = i % 3 # 0: front, 1: mid, 2: rear
            offset_along = (pair_idx - 1.0) * (ant.length * 0.28)

            # Leg root on thorax
            root_x = ix - cos_a * offset_along + norm_x * (ant.width * 0.45 * side)
            root_y = iy - sin_a * offset_along + norm_y * (ant.width * 0.45 * side)

            # Leg walk cycle swing
            phase = ant.walk_phase + self.tripod_offsets[i]
            swing = math.sin(phase) * 0.35

            # Leg joint (knee)
            knee_angle = ang + (math.pi * 0.45 + swing) * side
            knee_x = root_x + math.cos(knee_angle) * leg_len1
            knee_y = root_y + math.sin(knee_angle) * leg_len1

            # Leg tip (foot)
            foot_angle = knee_angle + (0.5 * side)
            foot_x = knee_x + math.cos(foot_angle) * leg_len2
            foot_y = knee_y + math.sin(foot_angle) * leg_len2

            pygame.draw.line(surface, leg_color, (int(root_x), int(root_y)), (int(knee_x), int(knee_y)), 1)
            pygame.draw.line(surface, leg_color, (int(knee_x), int(knee_y)), (int(foot_x), int(foot_y)), 1)

        # 2. Gaster (Abdomen)
        gaster_dist = ant.length * 0.45
        gx = ix - cos_a * gaster_dist
        gy = iy - sin_a * gaster_dist
        gaster_r = ant.width * 0.85
        pygame.draw.circle(surface, ant.base_color, (int(gx), int(gy)), max(2, int(gaster_r)))
        # Abdominal stripe segment
        stripe_x = gx - cos_a * (gaster_r * 0.35)
        stripe_y = gy - sin_a * (gaster_r * 0.35)
        pygame.draw.circle(surface, (ant.base_color[0] + 25, ant.base_color[1] + 15, ant.base_color[2] + 10), (int(stripe_x), int(stripe_y)), max(1, int(gaster_r * 0.6)))

        # 3. Mesosoma (Thorax)
        pygame.draw.circle(surface, ant.base_color, (int(ix), int(iy)), max(2, int(ant.width * 0.65)))

        # 4. Head & Mandibles
        head_dist = ant.length * 0.42
        hx = ix + cos_a * head_dist
        hy = iy + sin_a * head_dist
        head_r = ant.width * (0.95 if ant.caste == "Soldier" else 0.7)
        pygame.draw.circle(surface, ant.head_color, (int(hx), int(hy)), max(2, int(head_r)))

        # Dual Antennae
        ant_len = ant.length * 0.6
        is_greeting = getattr(ant, 'greeting_timer', 0) > 0
        for ant_side in (-1, 1):
            wiggle = math.sin(ant.walk_phase * 3.8 + ant_side) * 0.45 if is_greeting else math.sin(ant.walk_phase * 0.8 + ant_side) * 0.15
            ant_angle = ang + (0.45 * ant_side) + wiggle
            ax_elbow = hx + math.cos(ant_angle) * (ant_len * 0.55)
            ay_elbow = hy + math.sin(ant_angle) * (ant_len * 0.55)
            ax_tip = ax_elbow + math.cos(ant_angle + 0.35 * ant_side) * (ant_len * 0.5)
            ay_tip = ay_elbow + math.sin(ant_angle + 0.35 * ant_side) * (ant_len * 0.5)
            pygame.draw.line(surface, ant.head_color, (int(hx), int(hy)), (int(ax_elbow), int(ay_elbow)), 1)
            pygame.draw.line(surface, ant.head_color, (int(ax_elbow), int(ay_elbow)), (int(ax_tip), int(ay_tip)), 1)

        # Mandibles
        mand_len = ant.length * (0.35 if ant.caste == "Soldier" else 0.22)
        m1_x = hx + cos_a * mand_len + norm_x * (head_r * 0.5)
        m1_y = hy + sin_a * mand_len + norm_y * (head_r * 0.5)
        m2_x = hx + cos_a * mand_len - norm_x * (head_r * 0.5)
        m2_y = hy + sin_a * mand_len - norm_y * (head_r * 0.5)
        pygame.draw.line(surface, (30, 15, 10), (int(hx), int(hy)), (int(m1_x), int(m1_y)), 1)
        pygame.draw.line(surface, (30, 15, 10), (int(hx), int(hy)), (int(m2_x), int(m2_y)), 1)

        # 5. Carried Cargo (Food crumb, Dirt pellet, or Egg)
        if ant.cargo == 1: # FOOD
            cargo_x = hx + cos_a * (mand_len + 3)
            cargo_y = hy + sin_a * (mand_len + 3)
            pygame.draw.circle(surface, (245, 230, 90), (int(cargo_x), int(cargo_y)), 3)
        elif ant.cargo == 2: # DIRT
            cargo_x = hx + cos_a * (mand_len + 3)
            cargo_y = hy + sin_a * (mand_len + 3)
            pygame.draw.circle(surface, (115, 78, 50), (int(cargo_x), int(cargo_y)), 3)
        elif ant.cargo == 3: # EGG
            cargo_x = hx + cos_a * (mand_len + 3)
            cargo_y = hy + sin_a * (mand_len + 3)
            pygame.draw.ellipse(surface, (245, 245, 240), (int(cargo_x - 2), int(cargo_y - 2), 4, 3))

        # Highlight ring if inspected/followed
        if followed:
            pygame.draw.circle(surface, (255, 220, 80), (int(ix), int(iy)), int(ant.length + 6), 1)

    def draw_particles(self, surface, world):
        """Draws falling loose dirt grains, visual dust specks, and water droplets."""
        # Visual dust specks from ant digging (fade out with remaining life)
        for d in world.dust_particles:
            ratio = max(0.2, min(1.0, d[4] / 20.0))
            col = (int(85 * ratio + 30), int(55 * ratio + 20), int(35 * ratio + 15))
            ix, iy = int(d[0]), int(d[1])
            if 0 <= ix < self.width and 0 <= iy < self.height:
                surface.set_at((ix, iy), col)

        # Falling heavy sand grains (God power TOOL_DIRT only)
        for p in world.falling_dirt:
            pygame.draw.rect(surface, (120, 82, 52), (int(p[0]), int(p[1]), 2, 2))

        # Water droplets
        for w in world.water_droplets:
            pygame.draw.circle(surface, (140, 200, 245), (int(w[0]), int(w[1])), 2)

        # Food items
        for f in world.food_items:
            f.draw(surface)
