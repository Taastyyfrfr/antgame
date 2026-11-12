"""
ants.py - Ant colony simulation, castes, lifecycle, state machine, and spatial hashing.
"""

import math
import random
import pygame

CASTE_WORKER = "Worker"
CASTE_SOLDIER = "Soldier"
CASTE_QUEEN = "Queen"

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

    def update(self, dt, colony):
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
        ix, iy = int(self.x), int(self.y)
        if self.stage == self.STAGE_EGG:
            # Tiny pearly oval
            pygame.draw.ellipse(surface, (240, 240, 235), (ix - 2, iy - 1, 4, 3))
        elif self.stage == self.STAGE_LARVA:
            # Pale ribbed grub
            size = 3 + min(3, self.fed_count)
            pygame.draw.ellipse(surface, (235, 230, 210), (ix - size // 2, iy - 2, size, 4))
            pygame.draw.circle(surface, (180, 160, 140), (ix + size // 2 - 1, iy), 1) # head dot
        else: # PUPA
            # Cocoon
            pygame.draw.ellipse(surface, (215, 195, 165), (ix - 3, iy - 2, 7, 5))
            pygame.draw.ellipse(surface, (185, 165, 135), (ix - 3, iy - 2, 7, 5), 1)


class Ant:
    def __init__(self, x, y, caste=CASTE_WORKER, colony=None):
        self.x = float(x)
        self.y = float(y)
        self.caste = caste
        self.colony = colony
        self.angle = random.uniform(0, math.pi * 2)
        self.target_angle = self.angle
        self.state = STATE_WANDER
        self.cargo = CARGO_NONE
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
            self.head_color = (130, 45, 25) # Large prominent reddish head
        else: # WORKER
            self.length = 10.0
            self.width = 3.5
            self.speed = 1.6
            self.base_color = (75, 40, 25)
            self.head_color = (65, 32, 20)

        # Animation
        self.walk_phase = random.uniform(0, 10.0)
        self.turn_cooldown = 0
        self.dig_timer = 0
        self.pheromone_timer = 0
        self.target_threat = None

    def update(self, dt, world, pheromones, spatial_hash, colony):
        if not self.alive:
            return

        self.walk_phase += self.speed * 0.35 * dt

        # Queen behavior
        if self.caste == CASTE_QUEEN:
            self._update_queen(dt, world, colony)
            return

        # Pheromone emission timer
        self.pheromone_timer += dt
        if self.pheromone_timer >= 2.0:
            self.pheromone_timer = 0
            if self.cargo == CARGO_FOOD:
                # Emit FOOD pheromone to lay trails back to nest
                pheromones.deposit(self.x, self.y, layer_idx=1, amount=12.0, radius=2)
            elif self.state == STATE_FORAGE or self.state == STATE_WANDER:
                # Emit HOME pheromone for pathing
                pheromones.deposit(self.x, self.y, layer_idx=0, amount=8.0, radius=1)

        # State dispatch
        if self.caste == CASTE_SOLDIER:
            self._update_soldier(dt, world, pheromones, colony)
        else:
            self._update_worker(dt, world, pheromones, colony)

        # Physics & steering
        self._step_movement(dt, world)

    def _update_queen(self, dt, world, colony):
        """Queen rests in the royal chamber, slowly producing eggs when fed."""
        self.state = "Ruling / Laying Eggs"
        rx, ry = world.royal_chamber_pos
        dx = rx - self.x
        dy = ry - self.y
        dist = math.hypot(dx, dy)
        if dist > 25:
            # Queen stays inside her royal chamber
            self.target_angle = math.atan2(dy, dx)
            self.angle += (self.target_angle - self.angle) * 0.1
            self.x += math.cos(self.angle) * self.speed
            self.y += math.sin(self.angle) * self.speed
        else:
            # Gentle pacing
            if random.random() < 0.02:
                self.angle = random.uniform(0, math.pi * 2)

        # Egg laying logic
        colony.queen_egg_timer += dt * 0.03
        if colony.food_stockpile > 0 and colony.queen_egg_timer > 10.0:
            colony.queen_egg_timer = 0
            colony.food_stockpile = max(0, colony.food_stockpile - 1)
            # Spawn egg near queen or in nursery
            nx, ny = world.nursery_chamber_pos
            colony.spawn_brood(self.x + random.uniform(-6, 6), self.y + random.uniform(-4, 4), Brood.STAGE_EGG)

    def _update_soldier(self, dt, world, pheromones, colony):
        """Soldier guards the nest and attacks threats."""
        # 1. Check for nearby threats
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
            # Charge threat
            self.target_angle = math.atan2(closest_threat.y - self.y, closest_threat.x - self.x)
            if min_dist < 10.0:
                # Attack bite!
                closest_threat.take_damage(0.8 * dt, world)
                # Recoil / strike animation
                self.x += random.uniform(-0.5, 0.5)
        else:
            self.target_threat = None
            # Sample DANGER pheromones
            p_dx, p_dy, p_mag = pheromones.get_gradient(self.x, self.y, layer_idx=2)
            if p_mag > 0.05:
                self.state = "Investigating Danger"
                self.target_angle = math.atan2(p_dy, p_dx)
            else:
                self.state = "Patrolling"
                # Soldiers patrol between surface entrance and upper tunnels
                if self.y > 400 and random.random() < 0.05:
                    self.target_angle = -math.pi / 2 # Head upward towards entrance

    def _update_worker(self, dt, world, pheromones, colony):
        """Worker state machine: Dig, Forage, Haul, Tend."""
        # Check nearby food items
        if self.cargo == CARGO_NONE:
            for food in world.food_items:
                if food.amount > 0 and math.hypot(food.x - self.x, food.y - self.y) < 14:
                    food.amount -= 1
                    self.cargo = CARGO_FOOD
                    self.state = STATE_RETURNING
                    self.target_angle = self.angle + math.pi # Turn back
                    return

        # Carrying food: return to pantry or nursery
        if self.cargo == CARGO_FOOD:
            self.state = STATE_RETURNING
            # Navigate towards food storage or nursery
            px, py = world.food_storage_pos
            dx = px - self.x
            dy = py - self.y
            dist = math.hypot(dx, dy)
            if dist < 24:
                # Deposit food in colony stockpile
                self.cargo = CARGO_NONE
                colony.food_stockpile += 1
                self.state = STATE_FORAGE
                self.target_angle = self.angle + math.pi
                return
            else:
                # Steer towards pantry
                self.target_angle = math.atan2(dy, dx) + random.uniform(-0.3, 0.3)
                return

        # Carrying excavated dirt pellet: haul to surface mound
        if self.cargo == CARGO_DIRT:
            self.state = STATE_HAULING
            surf_x, surf_y = world.width // 2, world.surface_row * world.cell_size
            if self.y <= surf_y + 4:
                # On surface! Deposit dirt onto mound
                drop_x = self.x + (15 if random.random() < 0.5 else -15)
                drop_y = self.y
                world.fill_pixel(drop_x, drop_y, 6) # CELL_MOUND
                self.cargo = CARGO_NONE
                self.state = STATE_WANDER
                self.target_angle = math.pi / 2 # Turn back underground
                return
            else:
                # Steer towards surface entrance
                self.target_angle = -math.pi / 2 + random.uniform(-0.4, 0.4)
                return

        # Foraging / Wandering: follow FOOD pheromones or explore
        f_dx, f_dy, f_mag = pheromones.get_gradient(self.x, self.y, layer_idx=1)
        if f_mag > 0.08:
            self.state = STATE_FORAGE
            self.target_angle = math.atan2(f_dy, f_dx) + random.uniform(-0.2, 0.2)
        else:
            # Check digging opportunity
            if self.y > 180 and random.random() < 0.015:
                # Attempt to carve peripheral dirt
                front_x = self.x + math.cos(self.angle) * 8
                front_y = self.y + math.sin(self.angle) * 8
                if world.is_solid(front_x, front_y) and world.get_cell(front_x, front_y) != 5: # not bedrock
                    self.state = STATE_DIGGING
                    world.carve_circle(front_x, front_y, radius=7, play_effects=True)
                    self.cargo = CARGO_DIRT
                    self.target_angle = self.angle + math.pi # Turn around to haul dirt
                    return

            # Tend brood if in nursery
            nx, ny = world.nursery_chamber_pos
            if math.hypot(nx - self.x, ny - self.y) < 30:
                for b in colony.brood:
                    if b.stage == Brood.STAGE_LARVA and b.fed_count < 3 and colony.food_stockpile > 0:
                        b.fed_count += 1
                        colony.food_stockpile = max(0, colony.food_stockpile - 1)
                        self.state = STATE_TENDING
                        break

    def _step_movement(self, dt, world):
        """Wall collision, steering feelers, and physical stepping."""
        # Smooth angle towards target_angle
        diff = (self.target_angle - self.angle + math.pi) % (2 * math.pi) - math.pi
        self.angle += diff * min(1.0, 4.0 * dt)

        # Three feelers: center, left (+35 deg), right (-35 deg)
        feeler_dist = 6.0
        cx = self.x + math.cos(self.angle) * feeler_dist
        cy = self.y + math.sin(self.angle) * feeler_dist

        lx = self.x + math.cos(self.angle + 0.6) * feeler_dist
        ly = self.y + math.sin(self.angle + 0.6) * feeler_dist

        rx = self.x + math.cos(self.angle - 0.6) * feeler_dist
        ry = self.y + math.sin(self.angle - 0.6) * feeler_dist

        center_solid = world.is_solid(cx, cy)
        left_solid = world.is_solid(lx, ly)
        right_solid = world.is_solid(rx, ry)

        if center_solid:
            # Hit wall: turn towards open air
            if not left_solid:
                self.target_angle += 1.2
            elif not right_solid:
                self.target_angle -= 1.2
            else:
                self.target_angle += math.pi + random.uniform(-0.5, 0.5)
        else:
            if left_solid and not right_solid:
                self.target_angle -= 0.15 # Align along wall
            elif right_solid and not left_solid:
                self.target_angle += 0.15
            elif random.random() < 0.05:
                # Random slight wander jitter
                self.target_angle += random.uniform(-0.5, 0.5)

        # Step forward
        move_speed = self.speed * (0.8 if self.cargo != CARGO_NONE else 1.0)
        nx = self.x + math.cos(self.angle) * move_speed * dt
        ny = self.y + math.sin(self.angle) * move_speed * dt

        # World boundary clamp
        nx = max(8, min(world.width - 8, nx))
        ny = max(8, min(world.height - 8, ny))

        if not world.is_solid(nx, ny):
            self.x = nx
            self.y = ny
        else:
            # Slide or rebound
            self.target_angle += math.pi * 0.7


class AntColony:
    """Manages the ant population, castes, brood lifecycle, and spatial indexing."""
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

        # Spawn starter Workers
        for _ in range(28):
            ax = qx + random.uniform(-50, 50)
            ay = qy + random.uniform(-40, 20)
            if not world.is_solid(ax, ay):
                self.ants.append(Ant(ax, ay, caste=CASTE_WORKER, colony=self))

        # Spawn starter Soldiers
        for _ in range(6):
            sx = qx + random.uniform(-30, 30)
            sy = qy - random.uniform(40, 100)
            if not world.is_solid(sx, sy):
                self.ants.append(Ant(sx, sy, caste=CASTE_SOLDIER, colony=self))

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
            self.ants.append(Ant(x, y, caste=caste, colony=self))

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
        workers = sum(1 for a in self.ants if a.caste == CASTE_WORKER)
        soldiers = sum(1 for a in self.ants if a.caste == CASTE_SOLDIER)
        eggs = sum(1 for b in self.brood if b.stage == Brood.STAGE_EGG)
        larvae = sum(1 for b in self.brood if b.stage == Brood.STAGE_LARVA)
        pupae = sum(1 for b in self.brood if b.stage == Brood.STAGE_PUPA)
        max_depth = max((int(a.y) for a in self.ants), default=0)
        return {
            "workers": workers,
            "soldiers": soldiers,
            "total_ants": len(self.ants),
            "eggs": eggs,
            "larvae": larvae,
            "pupae": pupae,
            "food": self.food_stockpile,
            "max_depth": max_depth,
            "threats": len(self.threats)
        }
