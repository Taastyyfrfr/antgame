"""
ants.py - Ant colony simulation with dynamic worker sub-roles, surface ground-hugging,
forward-cone pheromone navigation, excavator dig streaks, and brood care.
"""

import math
import random
import pygame

CASTE_WORKER = "Worker"
CASTE_SOLDIER = "Soldier"
CASTE_QUEEN = "Queen"

# Worker dynamic sub-roles
SUBROLE_FORAGER = "Forager"
SUBROLE_EXCAVATOR = "Excavator"
SUBROLE_NURSE = "Nurse"

STATE_WANDER = "Wandering"
STATE_FORAGE = "Foraging"
STATE_HAULING = "Hauling Dirt"
STATE_RETURNING = "Returning Home"
STATE_DIGGING = "Digging"
STATE_TENDING = "Tending Brood"
STATE_COMBAT = "In Combat"

CARGO_NONE = 0
CARGO_FOOD = 1
CARGO_DIRT = 2
CARGO_EGG = 3

SURFACE_Y = 130

class SpatialHash:
    """Fast O(1) spatial partitioning for ant neighbors, food, and combat."""
    def __init__(self, cell_size=32, width=1280, height=720):
        self.cell_size = cell_size
        self.cols = (width // cell_size) + 1
        self.rows = (height // cell_size) + 1
        self.buckets = {}

    def clear(self):
        self.buckets.clear()

    def _hash(self, x, y):
        cx = int(x // self.cell_size)
        cy = int(y // self.cell_size)
        return (cx, cy)

    def insert(self, obj, x, y):
        key = self._hash(x, y)
        if key not in self.buckets:
            self.buckets[key] = []
        self.buckets[key].append(obj)

    def query_radius(self, x, y, radius):
        """Returns all objects within radius."""
        r_sq = radius * radius
        min_cx = int((x - radius) // self.cell_size)
        max_cx = int((x + radius) // self.cell_size)
        min_cy = int((y - radius) // self.cell_size)
        max_cy = int((y + radius) // self.cell_size)

        results = []
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                bucket = self.buckets.get((cx, cy))
                if bucket:
                    for obj in bucket:
                        dx = obj.x - x
                        dy = obj.y - y
                        if dx * dx + dy * dy <= r_sq:
                            results.append(obj)
        return results


class Brood:
    """Represents eggs, larvae, and pupae residing in the nursery."""
    STAGE_EGG = 0
    STAGE_LARVA = 1
    STAGE_PUPA = 2

    def __init__(self, x, y, stage=STAGE_EGG):
        self.x = float(x)
        self.y = float(y)
        self.stage = stage
        self.age = 0.0
        self.fed_count = 0
        self.ready_to_hatch = False
        self.carried = False

    def update(self, dt, colony):
        if self.carried:
            return

        self.age += dt * 0.05
        if self.stage == self.STAGE_EGG:
            if self.age > 18.0:
                self.stage = self.STAGE_LARVA
                self.age = 0.0
        elif self.stage == self.STAGE_LARVA:
            # Larva needs feeding by nurse workers
            if self.fed_count >= 2 and self.age > 22.0:
                self.stage = self.STAGE_PUPA
                self.age = 0.0
        elif self.stage == self.STAGE_PUPA:
            if self.age > 20.0:
                self.ready_to_hatch = True

    def draw(self, surface):
        if self.carried:
            return
        ix, iy = int(self.x), int(self.y)
        if self.stage == self.STAGE_EGG:
            pygame.draw.ellipse(surface, (240, 240, 235), (ix - 2, iy - 1, 4, 3))
        elif self.stage == self.STAGE_LARVA:
            size = 3 + min(3, self.fed_count)
            pygame.draw.ellipse(surface, (235, 230, 210), (ix - size // 2, iy - 2, size, 4))
            pygame.draw.circle(surface, (180, 160, 140), (ix + size // 2 - 1, iy), 1)
        else: # PUPA
            pygame.draw.ellipse(surface, (215, 195, 165), (ix - 3, iy - 2, 7, 5))
            pygame.draw.ellipse(surface, (185, 165, 135), (ix - 3, iy - 2, 7, 5), 1)


class Ant:
    def __init__(self, x, y, caste=CASTE_WORKER, subrole=SUBROLE_FORAGER, colony=None):
        self.x = float(x)
        self.y = float(y)
        self.caste = caste
        self.subrole = subrole
        self.colony = colony
        self.angle = random.uniform(0, math.pi * 2)
        self.target_angle = self.angle
        self.state = STATE_WANDER
        self.cargo = CARGO_NONE
        self.carried_egg = None
        self.energy = 100.0
        self.health = 100.0
        self.alive = True

        # Morphology & speed per caste
        if caste == CASTE_QUEEN:
            self.length = 20.0
            self.width = 7.0
            self.speed = 0.6
            self.base_color = (70, 30, 20)
            self.head_color = (60, 25, 15)
        elif caste == CASTE_SOLDIER:
            self.length = 14.0
            self.width = 5.0
            self.speed = 1.3
            self.base_color = (95, 45, 25)
            self.head_color = (130, 45, 25)
        else: # WORKER
            self.length = 10.0
            self.width = 3.5
            self.speed = 1.6
            self.base_color = (75, 40, 25)
            self.head_color = (65, 32, 20)

        # Animation & subrole states
        self.walk_phase = random.uniform(0, 10.0)
        self.pheromone_timer = 0.0
        self.target_threat = None

        # Excavator streak variables
        self.dig_streak = 0
        self.dig_angle = 0.0

        # Forager surface direction (1 = right, -1 = left)
        self.surface_dir = 1 if random.random() < 0.5 else -1

    def update(self, dt, world, pheromones, spatial_hash, colony):
        if not self.alive:
            return

        self.walk_phase += self.speed * 0.35 * dt

        # Queen behavior
        if self.caste == CASTE_QUEEN:
            self._update_queen(dt, world, colony)
            self._step_movement(dt, world)
            return

        # Pheromone emission timer
        self.pheromone_timer += dt
        if self.pheromone_timer >= 1.2:
            self.pheromone_timer = 0.0
            if self.cargo == CARGO_FOOD:
                # Strong FOOD pheromone trail leading back to pantry
                pheromones.deposit(self.x, self.y, layer_idx=1, amount=18.0, radius=2)
            elif self.y > SURFACE_Y - 5:
                # HOME pheromones deposited along tunnels and nest
                pheromones.deposit(self.x, self.y, layer_idx=0, amount=9.0, radius=1)

        # Caste dispatch
        if self.caste == CASTE_SOLDIER:
            self._update_soldier(dt, world, pheromones, colony)
        else:
            self._update_worker(dt, world, pheromones, colony)

        # Movement & surface ground-hugging
        self._step_movement(dt, world)

    def _update_queen(self, dt, world, colony):
        """Queen rests in the royal chamber, laying eggs when fed."""
        self.state = "Ruling / Laying Eggs"
        rx, ry = world.royal_chamber_pos
        dx = rx - self.x
        dy = ry - self.y
        dist = math.hypot(dx, dy)
        if dist > 26:
            self.target_angle = math.atan2(dy, dx)
        else:
            if random.random() < 0.03:
                self.target_angle = random.uniform(0, math.pi * 2)

        # Egg laying logic
        colony.queen_egg_timer += dt * 0.03
        if colony.food_stockpile > 0 and colony.queen_egg_timer > 9.0:
            colony.queen_egg_timer = 0.0
            colony.food_stockpile = max(0, colony.food_stockpile - 1)
            # Lay egg in royal chamber
            colony.spawn_brood(self.x + random.uniform(-8, 8), self.y + random.uniform(-4, 4), Brood.STAGE_EGG)

    def _update_soldier(self, dt, world, pheromones, colony):
        """Soldier patrols entrances and attacks threats."""
        closest_threat = None
        min_dist = 120.0
        for threat in colony.threats:
            if threat.alive:
                d = math.hypot(threat.x - self.x, threat.y - self.y)
                if d < min_dist:
                    min_dist = d
                    closest_threat = threat

        if closest_threat:
            self.state = STATE_COMBAT
            self.target_threat = closest_threat
            self.target_angle = math.atan2(closest_threat.y - self.y, closest_threat.x - self.x)
            if min_dist < 11.0:
                closest_threat.take_damage(0.9 * dt, world)
                self.x += random.uniform(-0.5, 0.5)
        else:
            self.target_threat = None
            bias, mag = pheromones.sense_forward(self.x, self.y, self.angle, layer_idx=2, dist=16.0)
            if mag > 0.08:
                self.state = "Investigating Danger"
                self.target_angle += bias
            else:
                self.state = "Patrolling"
                # Patrol around upper tunnel and surface entrance
                if self.y > 380 and random.random() < 0.04:
                    self.target_angle = -math.pi / 2 # Head upward toward entrance

    def _update_worker(self, dt, world, pheromones, colony):
        """Worker dispatch based on subrole: Forager, Excavator, Nurse."""
        if self.subrole == SUBROLE_EXCAVATOR:
            self._update_excavator(dt, world, pheromones, colony)
        elif self.subrole == SUBROLE_NURSE:
            self._update_nurse(dt, world, pheromones, colony)
        else: # SUBROLE_FORAGER
            self._update_forager(dt, world, pheromones, colony)

    def _update_forager(self, dt, world, pheromones, colony):
        """Forager: Patrols surface grass line, finds food, follows trails back to pantry."""
        # 1. If carrying food, return to pantry
        if self.cargo == CARGO_FOOD:
            self.state = STATE_RETURNING
            px, py = world.food_storage_pos
            dx = px - self.x
            dy = py - self.y
            dist = math.hypot(dx, dy)

            if dist < 26:
                # Successfully stored food!
                self.cargo = CARGO_NONE
                colony.food_stockpile += 1
                self.state = STATE_FORAGE
                self.target_angle = self.angle + math.pi # Turn back to surface
                return

            # Follow HOME pheromone trail or navigate down shaft
            bias, mag = pheromones.sense_forward(self.x, self.y, self.angle, layer_idx=0, dist=14.0)
            if mag > 0.1:
                self.target_angle += bias * 0.4
            else:
                # General steering towards food pantry
                self.target_angle = math.atan2(dy, dx) + random.uniform(-0.25, 0.25)
            return

        # 2. Not carrying food: look for food items
        for food in world.food_items:
            if food.amount > 0 and math.hypot(food.x - self.x, food.y - self.y) < 18:
                food.amount -= 1
                self.cargo = CARGO_FOOD
                self.state = STATE_RETURNING
                self.target_angle = self.angle + math.pi # Turn around with food
                return

        # 3. Foraging movement
        self.state = STATE_FORAGE
        surf_y = world.get_surface_y(self.x)

        if self.y > surf_y + 10:
            # Underground: head up towards entrance crater (640, 130)
            entrance_x = world.width // 2
            dx = entrance_x - self.x
            dy = (SURFACE_Y - 5) - self.y
            self.target_angle = math.atan2(dy, dx) + random.uniform(-0.3, 0.3)
        else:
            # On surface grass! Follow FOOD pheromones or patrol left/right
            f_bias, f_mag = pheromones.sense_forward(self.x, self.y, self.angle, layer_idx=1, dist=18.0)
            if f_mag > 0.1:
                self.target_angle += f_bias * 0.5
            else:
                # Patrol horizontally along grass
                if self.x < 50:
                    self.surface_dir = 1
                elif self.x > world.width - 50:
                    self.surface_dir = -1
                elif random.random() < 0.015:
                    self.surface_dir = -self.surface_dir

                self.target_angle = 0.0 if self.surface_dir > 0 else math.pi

    def _update_excavator(self, dt, world, pheromones, colony):
        """Excavator: digs branching tunnels with consecutive streaks, then hauls dirt to mound."""
        # 1. Hauling excavated dirt to surface mound
        if self.cargo == CARGO_DIRT:
            self.state = STATE_HAULING
            surf_x = world.width // 2
            surf_y = world.get_surface_y(self.x)

            # Check if reached surface mound near entrance
            if self.y <= surf_y + 3 and abs(self.x - surf_x) < 70:
                # Deposit dirt pellet onto anthill mound
                drop_x = self.x + (14 if random.random() < 0.5 else -14)
                drop_y = surf_y
                world.fill_pixel(drop_x, drop_y, 6) # CELL_MOUND
                self.cargo = CARGO_NONE
                self.state = STATE_WANDER
                self.target_angle = math.pi / 2 # Turn back down into tunnels
                return
            else:
                # Steer upward towards surface entrance
                bias, mag = pheromones.sense_forward(self.x, self.y, self.angle, layer_idx=0, dist=14.0)
                if mag > 0.1:
                    self.target_angle += bias * 0.4
                else:
                    self.target_angle = -math.pi / 2 + random.uniform(-0.3, 0.3)
            return

        # 2. Executing an active digging streak
        if self.dig_streak > 0:
            self.state = STATE_DIGGING
            self.target_angle = self.dig_angle

            # Carve bite ahead
            bite_x = self.x + math.cos(self.dig_angle) * 7
            bite_y = self.y + math.sin(self.dig_angle) * 7

            if world.get_cell(bite_x, bite_y) != 5: # Not bedrock
                world.carve_circle(bite_x, bite_y, radius=6, play_effects=True)
                self.dig_streak -= 1
                # Slightly curve the dig streak for natural tunnel branching
                self.dig_angle += random.uniform(-0.1, 0.1)
                if self.dig_streak <= 0:
                    self.cargo = CARGO_DIRT
                    self.state = STATE_HAULING
                    self.target_angle = self.angle + math.pi # Turn back to haul
            else:
                # Bedrock hit: end streak
                self.dig_streak = 0
                self.cargo = CARGO_DIRT
                self.state = STATE_HAULING
                self.target_angle = self.angle + math.pi
            return

        # 3. Seeking digging opportunity
        self.state = STATE_WANDER
        if self.y > 180:
            feeler_x = self.x + math.cos(self.angle) * 8
            feeler_y = self.y + math.sin(self.angle) * 8
            cell = world.get_cell(feeler_x, feeler_y)
            if cell != 0 and cell != 5: # Solid dirt, not air and not bedrock
                # Start dig streak!
                self.dig_streak = random.randint(6, 10)
                self.dig_angle = self.angle + random.uniform(-0.15, 0.15)
                self.state = STATE_DIGGING
                return

        # Natural wander towards deeper chambers
        if self.y < 220 and random.random() < 0.05:
            self.target_angle = math.pi / 2 # Head deeper

    def _update_nurse(self, dt, world, pheromones, colony):
        """Nurse: Tends brood, carries eggs to nursery, feeds hungry larvae."""
        nx, ny = world.nursery_chamber_pos

        # 1. If carrying an egg, haul it to the nursery
        if self.cargo == CARGO_EGG:
            self.state = "Relocating Egg"
            dx = nx - self.x
            dy = ny - self.y
            dist = math.hypot(dx, dy)
            if dist < 18:
                # Place egg safely in nursery
                if self.carried_egg:
                    self.carried_egg.x = self.x
                    self.carried_egg.y = self.y
                    self.carried_egg.carried = False
                    self.carried_egg = None
                self.cargo = CARGO_NONE
                self.state = STATE_TENDING
                return
            else:
                self.target_angle = math.atan2(dy, dx)
            return

        # 2. Check for stray eggs near Queen to transport to nursery
        rx, ry = world.royal_chamber_pos
        for b in colony.brood:
            if b.stage == Brood.STAGE_EGG and not b.carried:
                d_nursery = math.hypot(nx - b.x, ny - b.y)
                if d_nursery > 32 and math.hypot(self.x - b.x, self.y - b.y) < 16:
                    b.carried = True
                    self.carried_egg = b
                    self.cargo = CARGO_EGG
                    self.state = "Relocating Egg"
                    return

        # 3. Feed larvae in nursery using food stockpile
        dist_nursery = math.hypot(nx - self.x, ny - self.y)
        if dist_nursery < 34:
            self.state = STATE_TENDING
            for b in colony.brood:
                if b.stage == Brood.STAGE_LARVA and b.fed_count < 3 and colony.food_stockpile > 0:
                    b.fed_count += 1
                    colony.food_stockpile = max(0, colony.food_stockpile - 1)
                    break
        else:
            # Wander between royal chamber and nursery
            target_pos = world.nursery_chamber_pos if random.random() < 0.6 else world.royal_chamber_pos
            dx = target_pos[0] - self.x
            dy = target_pos[1] - self.y
            self.target_angle = math.atan2(dy, dx) + random.uniform(-0.3, 0.3)

    def _step_movement(self, dt, world):
        """Wall avoidance, surface ground-hugging, and smooth directional stepping."""
        # Smooth interpolation of self.angle towards target_angle
        diff = (self.target_angle - self.angle + math.pi) % (2 * math.pi) - math.pi
        self.angle += diff * min(1.0, 5.0 * dt)

        # Excavators in an active dig streak bypass wall-avoidance
        is_actively_digging = (self.caste == CASTE_WORKER and self.subrole == SUBROLE_EXCAVATOR and self.dig_streak > 0)

        if not is_actively_digging:
            # Three feelers ahead: center, left (+35 deg), right (-35 deg)
            feeler_dist = 6.5
            cx = self.x + math.cos(self.angle) * feeler_dist
            cy = self.y + math.sin(self.angle) * feeler_dist
            lx = self.x + math.cos(self.angle + 0.6) * feeler_dist
            ly = self.y + math.sin(self.angle + 0.6) * feeler_dist
            rx = self.x + math.cos(self.angle - 0.6) * feeler_dist
            ry = self.y + math.sin(self.angle - 0.6) * feeler_dist

            c_solid = world.is_solid(cx, cy)
            l_solid = world.is_solid(lx, ly)
            r_solid = world.is_solid(rx, ry)

            if c_solid:
                if not l_solid:
                    self.target_angle += 1.2
                elif not r_solid:
                    self.target_angle -= 1.2
                else:
                    self.target_angle += math.pi + random.uniform(-0.4, 0.4)
            else:
                if l_solid and not r_solid:
                    self.target_angle -= 0.15
                elif r_solid and not l_solid:
                    self.target_angle += 0.15
                elif random.random() < 0.04:
                    self.target_angle += random.uniform(-0.4, 0.4)

        # Step forward
        move_speed = self.speed * (0.85 if self.cargo != CARGO_NONE else 1.0)
        nx = self.x + math.cos(self.angle) * move_speed * dt
        ny = self.y + math.sin(self.angle) * move_speed * dt

        # Boundary clamping
        nx = max(8, min(world.width - 8, nx))
        ny = max(8, min(world.height - 8, ny))

        # --- Surface Ground-Hugging (Fix Flying Ants) ---
        surf_y = world.get_surface_y(nx)
        is_at_or_above_surface = (ny <= surf_y + 4)
        # Check if positioned over the open entrance crater (around 625-655)
        is_over_entrance = not world.is_solid(nx, SURFACE_Y + 8)

        if is_at_or_above_surface and not is_over_entrance:
            # Constrain ant to walk along the surface ground line; never float into the sky!
            ny = surf_y - 2
            # Orient heading along surface slope
            slope = (world.get_surface_y(nx + 4) - world.get_surface_y(nx - 4)) / 8.0
            base_angle = 0.0 if math.cos(self.angle) >= 0 else math.pi
            self.target_angle = base_angle + math.atan(slope) * (1.0 if math.cos(self.angle) >= 0 else -1.0)

        # Commit movement if position is air (or if actively carving dirt)
        if not world.is_solid(nx, ny) or is_actively_digging:
            self.x = nx
            self.y = ny
        else:
            self.target_angle += math.pi * 0.75


class AntColony:
    """Manages ant population, castes, subroles, and dynamic rebalancing."""
    def __init__(self, world, pheromones):
        self.world = world
        self.pheromones = pheromones
        self.spatial_hash = SpatialHash(cell_size=32, width=world.width, height=world.height)

        self.ants = []
        self.brood = []
        self.threats = []

        self.food_stockpile = 35
        self.queen_egg_timer = 0.0
        self.max_ants = 320

        # Spawn Queen in Royal Chamber
        qx, qy = world.royal_chamber_pos
        self.queen = Ant(qx, qy, caste=CASTE_QUEEN, colony=self)
        self.ants.append(self.queen)

        # Spawn starter Workers with balanced subroles (45% Forager, 35% Excavator, 20% Nurse)
        spawned_workers = 0
        attempts = 0
        while spawned_workers < 28 and attempts < 120:
            attempts += 1
            ax = qx + random.uniform(-30, 30)
            ay = qy + random.uniform(-16, 16)
            if not world.is_solid(ax, ay):
                subrole = SUBROLE_FORAGER if spawned_workers % 10 < 5 else SUBROLE_EXCAVATOR if spawned_workers % 10 < 8 else SUBROLE_NURSE
                self.ants.append(Ant(ax, ay, caste=CASTE_WORKER, subrole=subrole, colony=self))
                spawned_workers += 1

        # Spawn starter Soldiers
        spawned_soldiers = 0
        attempts = 0
        while spawned_soldiers < 6 and attempts < 60:
            attempts += 1
            sx = qx + random.uniform(-28, 28)
            sy = qy + random.uniform(-15, 15)
            if not world.is_solid(sx, sy):
                self.ants.append(Ant(sx, sy, caste=CASTE_SOLDIER, colony=self))
                spawned_soldiers += 1

        # Spawn initial brood in nursery
        nx, ny = world.nursery_chamber_pos
        for _ in range(8):
            self.brood.append(Brood(nx + random.uniform(-15, 15), ny + random.uniform(-8, 8), Brood.STAGE_EGG))
        for _ in range(5):
            self.brood.append(Brood(nx + random.uniform(-15, 15), ny + random.uniform(-8, 8), Brood.STAGE_LARVA))
        for _ in range(4):
            self.brood.append(Brood(nx + random.uniform(-15, 15), ny + random.uniform(-8, 8), Brood.STAGE_PUPA))

    def spawn_brood(self, x, y, stage=Brood.STAGE_EGG):
        if len(self.brood) < 120:
            self.brood.append(Brood(x, y, stage))

    def spawn_ant(self, x, y, caste=CASTE_WORKER):
        if len(self.ants) < self.max_ants:
            # Determine subrole based on current colony needs
            subrole = SUBROLE_FORAGER
            if caste == CASTE_WORKER:
                workers = [a for a in self.ants if a.caste == CASTE_WORKER]
                nurses = sum(1 for a in workers if a.subrole == SUBROLE_NURSE)
                excavators = sum(1 for a in workers if a.subrole == SUBROLE_EXCAVATOR)
                total_w = max(1, len(workers))

                if self.food_stockpile < 12:
                    subrole = SUBROLE_FORAGER
                elif nurses / total_w < 0.20:
                    subrole = SUBROLE_NURSE
                elif excavators / total_w < 0.35:
                    subrole = SUBROLE_EXCAVATOR
                else:
                    subrole = SUBROLE_FORAGER

            self.ants.append(Ant(x, y, caste=caste, subrole=subrole, colony=self))

    def spawn_threat(self, x, y, threat_type="beetle"):
        from threats import Threat
        self.threats.append(Threat(x, y, threat_type))

    def update(self, dt):
        # 1. Update Spatial Hash
        self.spatial_hash.clear()
        for ant in self.ants:
            self.spatial_hash.insert(ant, ant.x, ant.y)

        # 2. Update Ants
        for ant in self.ants:
            ant.update(dt, self.world, self.pheromones, self.spatial_hash, self)

        # Clean dead ants
        self.ants = [a for a in self.ants if a.alive]

        # 3. Update Brood
        hatched_brood = []
        kept_brood = []
        for b in self.brood:
            b.update(dt, self)
            if b.ready_to_hatch:
                hatched_brood.append(b)
            else:
                kept_brood.append(b)
        self.brood = kept_brood

        # Hatch brood into adults (85% worker, 15% soldier)
        for b in hatched_brood:
            caste = CASTE_SOLDIER if random.random() < 0.15 else CASTE_WORKER
            self.spawn_ant(b.x, b.y, caste=caste)

        # 4. Update Threats
        for t in self.threats:
            t.update(self.world, self.pheromones, self.spatial_hash)
        self.threats = [t for t in self.threats if t.alive]

    def get_stats(self):
        workers = [a for a in self.ants if a.caste == CASTE_WORKER]
        foragers = sum(1 for a in workers if a.subrole == SUBROLE_FORAGER)
        excavators = sum(1 for a in workers if a.subrole == SUBROLE_EXCAVATOR)
        nurses = sum(1 for a in workers if a.subrole == SUBROLE_NURSE)
        soldiers = sum(1 for a in self.ants if a.caste == CASTE_SOLDIER)
        eggs = sum(1 for b in self.brood if b.stage == Brood.STAGE_EGG)
        larvae = sum(1 for b in self.brood if b.stage == Brood.STAGE_LARVA)
        pupae = sum(1 for b in self.brood if b.stage == Brood.STAGE_PUPA)
        max_depth = max((int(a.y) for a in self.ants), default=0)
        return {
            "workers": len(workers),
            "foragers": foragers,
            "excavators": excavators,
            "nurses": nurses,
            "soldiers": soldiers,
            "total_ants": len(self.ants),
            "eggs": eggs,
            "larvae": larvae,
            "pupae": pupae,
            "food": self.food_stockpile,
            "max_depth": max_depth,
            "threats": len(self.threats)
        }
