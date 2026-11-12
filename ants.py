"""
ants.py - Ant colony simulation driven by coarse-grid navigation flow fields.
Features purposeful state machines for Foragers, Excavators, Nurses, and Soldiers,
surface ground-hugging, social greetings, and natural rest cycles.
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

# Purposeful State Machine
STATE_EXITING_NEST = "Exiting Nest"
STATE_SURFACE_FORAGING = "Foraging on Surface"
STATE_RETURNING_FOOD = "Returning Food"

STATE_GOING_TO_DIG = "Heading to Dig"
STATE_DIGGING = "Digging"
STATE_HAULING_DIRT = "Hauling Dirt"

STATE_NURSING = "Tending Nursery"
STATE_RELOCATING_EGG = "Relocating Egg"
STATE_FEEDING_LARVA = "Feeding Larva"

STATE_RESTING = "Resting"
STATE_GREETING = "Greeting"

STATE_PATROLLING = "Patrolling"
STATE_COMBAT = "In Combat"

CARGO_NONE = 0
CARGO_FOOD = 1
CARGO_DIRT = 2
CARGO_EGG = 3

SURFACE_Y = 130

class SpatialHash:
    """Fast O(1) spatial partitioning for ant neighbors, food, greetings, and combat."""
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
    _ant_id_counter = 0

    def __init__(self, x, y, caste=CASTE_WORKER, subrole=SUBROLE_FORAGER, colony=None):
        Ant._ant_id_counter += 1
        self.id = Ant._ant_id_counter
        self.x = float(x)
        self.y = float(y)
        self.caste = caste
        self.subrole = subrole
        self.colony = colony
        self.angle = random.uniform(0, math.pi * 2)
        self.target_angle = self.angle
        self.cargo = CARGO_NONE
        self.carried_egg = None
        self.energy = random.uniform(85.0, 100.0)
        self.health = 100.0
        self.alive = True

        # Initial state setup
        if caste == CASTE_QUEEN:
            self.state = "Ruling / Laying Eggs"
            self.length = 20.0
            self.width = 7.0
            self.speed = 0.6
            self.base_color = (70, 30, 20)
            self.head_color = (60, 25, 15)
        elif caste == CASTE_SOLDIER:
            self.state = STATE_PATROLLING
            self.length = 14.0
            self.width = 5.0
            self.speed = 1.35
            self.base_color = (95, 45, 25)
            self.head_color = (135, 42, 22)
        else: # WORKER
            self.length = 10.0
            self.width = 3.5
            self.speed = 1.6
            self.base_color = (75, 40, 25)
            self.head_color = (65, 32, 20)
            if subrole == SUBROLE_FORAGER:
                self.state = STATE_SURFACE_FORAGING if y <= SURFACE_Y + 4 else STATE_EXITING_NEST
            elif subrole == SUBROLE_EXCAVATOR:
                self.state = STATE_GOING_TO_DIG
            else: # Nurse
                self.state = STATE_NURSING

        # Navigation and behavior timers
        self.walk_phase = random.uniform(0, 10.0)
        self.pheromone_timer = 0.0
        self.target_threat = None
        self.greeting_timer = 0.0
        self.greeting_cooldown = random.uniform(5.0, 15.0)
        self.rest_timer = 0.0

        # Excavator specifics
        self.dig_streak = 0
        self.dig_angle = 0.0
        self.dig_target = (640, 460)

        # Forager surface direction
        self.surface_dir = 1 if random.random() < 0.5 else -1

    def update(self, dt, world, pheromones, spatial_hash, colony):
        if not self.alive:
            return

        self.walk_phase += self.speed * 0.35 * dt

        # Energy consumption
        self.energy = max(0.0, self.energy - 0.03 * dt)

        # Greeting timer & cooldown countdown
        if self.greeting_cooldown > 0:
            self.greeting_cooldown -= dt

        if self.greeting_timer > 0:
            self.greeting_timer -= dt
            # Wiggle antennae during greeting; do not move
            self.walk_phase += 0.5 * dt
            return

        # Queen behavior
        if self.caste == CASTE_QUEEN:
            self._update_queen(dt, world, colony)
            self._step_movement(dt, world)
            return

        # Rest state logic
        if self.state == STATE_RESTING:
            self.rest_timer -= dt
            self.energy = min(100.0, self.energy + 18.0 * dt)
            if self.rest_timer <= 0:
                # Return to primary duties
                if self.subrole == SUBROLE_FORAGER:
                    self.state = STATE_EXITING_NEST
                elif self.subrole == SUBROLE_EXCAVATOR:
                    self.state = STATE_GOING_TO_DIG
                else:
                    self.state = STATE_NURSING
            return

        # Check fatigue (workers need brief rest when energy drops)
        if self.caste == CASTE_WORKER and self.cargo == CARGO_NONE and self.energy < 12.0:
            self.state = STATE_RESTING
            self.rest_timer = random.uniform(3.5, 6.0)
            return

        # Pheromone emission timer
        self.pheromone_timer += dt
        if self.pheromone_timer >= 1.0:
            self.pheromone_timer = 0.0
            if self.cargo == CARGO_FOOD:
                # Lay strong FOOD pheromones back to nest
                pheromones.deposit(self.x, self.y, layer_idx=1, amount=22.0, radius=2)
            elif self.y > SURFACE_Y:
                # Lay faint HOME pheromones along tunnels
                pheromones.deposit(self.x, self.y, layer_idx=0, amount=8.0, radius=1)

        # Caste dispatch
        if self.caste == CASTE_SOLDIER:
            self._update_soldier(dt, world, pheromones, colony)
        else:
            self._update_worker(dt, world, pheromones, colony)

        # Physics stepping & surface ground-hugging
        self._step_movement(dt, world)

    def _update_queen(self, dt, world, colony):
        """Queen resides in the royal chamber, slowly laying eggs when fed."""
        self.state = "Ruling / Laying Eggs"
        rx, ry = world.royal_chamber_pos
        dx = rx - self.x
        dy = ry - self.y
        dist = math.hypot(dx, dy)
        if dist > 26:
            self.target_angle = math.atan2(dy, dx)
        else:
            if random.random() < 0.02:
                self.target_angle = random.uniform(0, math.pi * 2)

        # Egg production
        colony.queen_egg_timer += dt * 0.03
        if colony.food_stockpile > 0 and colony.queen_egg_timer > 9.0:
            colony.queen_egg_timer = 0.0
            colony.food_stockpile = max(0, colony.food_stockpile - 1)
            colony.spawn_brood(self.x + random.uniform(-8, 8), self.y + random.uniform(-4, 4), Brood.STAGE_EGG)

    def _update_soldier(self, dt, world, pheromones, colony):
        """Soldier patrols entrance and intercepts threats with fierce combat."""
        # 1. Threat search within 140px
        closest_threat = None
        min_dist = 140.0
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
            if min_dist < 12.0:
                closest_threat.take_damage(1.4 * dt, world)
                self.x += random.uniform(-0.5, 0.5)
            return

        self.state = STATE_PATROLLING
        self.target_threat = None

        # Sample DANGER pheromones
        bias, mag = pheromones.sense_forward(self.x, self.y, self.angle, layer_idx=2, dist=18.0)
        if mag > 0.1:
            self.target_angle += bias * 0.6
        else:
            # Patrol upper tunnel and surface entrance using flow field
            if self.y > 340:
                vx, vy, _ = world.get_flow_direction(self.x, self.y, "surface")
                self.target_angle = math.atan2(vy, vx)
            elif self.y <= SURFACE_Y + 4:
                # Walk across surface entrance crater
                if random.random() < 0.02:
                    self.surface_dir = -self.surface_dir
                self.target_angle = 0.0 if self.surface_dir > 0 else math.pi

    def _update_worker(self, dt, world, pheromones, colony):
        """Dispatches worker logic according to its subrole."""
        if self.subrole == SUBROLE_EXCAVATOR:
            self._update_excavator(dt, world, pheromones, colony)
        elif self.subrole == SUBROLE_NURSE:
            self._update_nurse(dt, world, pheromones, colony)
        else:
            self._update_forager(dt, world, pheromones, colony)

    def _update_forager(self, dt, world, pheromones, colony):
        """Forager: Uses flow field to exit, patrols surface grass, and returns food to pantry."""
        # 1. Returning food to pantry
        if self.cargo == CARGO_FOOD:
            self.state = STATE_RETURNING_FOOD
            surf_y = world.get_surface_y(self.x)

            if self.y <= surf_y + 4:
                # On surface: head horizontally toward entrance crater (x=640)
                entrance_x = world.width // 2
                dx = entrance_x - self.x
                if abs(dx) > 16:
                    self.target_angle = 0.0 if dx > 0 else math.pi
                else:
                    # Over entrance: dive down into tunnel
                    self.target_angle = math.pi / 2
                return
            else:
                # Inside tunnels: follow flow field to pantry!
                vx, vy, dist = world.get_flow_direction(self.x, self.y, "pantry")
                if dist < 18:
                    # Reached pantry! Store food crumb
                    self.cargo = CARGO_NONE
                    colony.food_stockpile += 1
                    self.energy = 100.0
                    self.state = STATE_EXITING_NEST
                    return
                else:
                    self.target_angle = math.atan2(vy, vx)
                return

        # 2. Exiting nest toward surface
        if self.state == STATE_EXITING_NEST:
            surf_y = world.get_surface_y(self.x)
            if self.y <= surf_y + 4:
                # Successfully reached surface! Start surface foraging
                self.state = STATE_SURFACE_FORAGING
                self.surface_dir = 1 if random.random() < 0.5 else -1
                return
            else:
                vx, vy, _ = world.get_flow_direction(self.x, self.y, "surface")
                self.target_angle = math.atan2(vy, vx)
                return

        # 3. Surface foraging
        self.state = STATE_SURFACE_FORAGING
        # Check nearby food items
        for food in world.food_items:
            if food.amount > 0 and math.hypot(food.x - self.x, food.y - self.y) < 18:
                food.amount -= 1
                self.cargo = CARGO_FOOD
                self.state = STATE_RETURNING_FOOD
                self.target_angle = math.pi if self.x > (world.width // 2) else 0.0
                return

        # Follow FOOD pheromone trail on surface if present
        f_bias, f_mag = pheromones.sense_forward(self.x, self.y, self.angle, layer_idx=1, dist=18.0)
        if f_mag > 0.1:
            self.target_angle += f_bias * 0.45
        else:
            # Patrol along grass line
            if self.x < 45:
                self.surface_dir = 1
            elif self.x > world.width - 45:
                self.surface_dir = -1
            elif random.random() < 0.015:
                self.surface_dir = -self.surface_dir

            self.target_angle = 0.0 if self.surface_dir > 0 else math.pi

    def _update_excavator(self, dt, world, pheromones, colony):
        """Excavator: Uses flow field to reach dig sites, carves 8-14 bites, hauls dirt to mound."""
        # 1. Hauling excavated dirt to surface mound
        if self.cargo == CARGO_DIRT:
            self.state = STATE_HAULING_DIRT
            surf_y = world.get_surface_y(self.x)
            entrance_x = world.width // 2

            if self.y <= surf_y + 4:
                # On surface! Walk 15-45px left or right onto anthill mound
                mound_target_x = entrance_x + (30 if self.surface_dir > 0 else -30)
                dx = mound_target_x - self.x

                if abs(dx) > 10:
                    self.target_angle = 0.0 if dx > 0 else math.pi
                else:
                    # Deposit dirt pellet onto mound slopes
                    world.fill_pixel(self.x, surf_y, 6) # CELL_MOUND
                    world.fill_pixel(self.x, surf_y - 1, 6) # Build mound height
                    self.cargo = CARGO_NONE
                    self.dig_target = world.get_expansion_target()
                    self.state = STATE_GOING_TO_DIG
                    self.surface_dir = -self.surface_dir
                    return
            else:
                # Follow flow field to surface entrance
                vx, vy, _ = world.get_flow_direction(self.x, self.y, "surface")
                self.target_angle = math.atan2(vy, vx)
            return

        # 2. Executing an active digging streak (8 to 14 bites)
        if self.dig_streak > 0:
            self.state = STATE_DIGGING
            self.target_angle = self.dig_angle

            # Carve bite ahead
            bite_x = self.x + math.cos(self.dig_angle) * 7.0
            bite_y = self.y + math.sin(self.dig_angle) * 7.0

            if world.get_cell(bite_x, bite_y) != 5: # Not bedrock
                world.carve_circle(bite_x, bite_y, radius=6, play_effects=True)
                self.dig_streak -= 1
                self.dig_angle += random.uniform(-0.08, 0.08)
                if self.dig_streak <= 0:
                    self.cargo = CARGO_DIRT
                    self.state = STATE_HAULING_DIRT
                    world.nav_dirty = True
            else:
                # Bedrock hit
                self.dig_streak = 0
                self.cargo = CARGO_DIRT
                self.state = STATE_HAULING_DIRT
                world.nav_dirty = True
            return

        # 3. Heading to dig site
        self.state = STATE_GOING_TO_DIG
        tx, ty = self.dig_target
        dist_to_target = math.hypot(tx - self.x, ty - self.y)

        # Check if right in front of solid diggable dirt
        front_x = self.x + math.cos(self.angle) * 8.0
        front_y = self.y + math.sin(self.angle) * 8.0
        if world.get_cell(front_x, front_y) not in (0, 5) and (dist_to_target < 35 or self.y > 200):
            # Start dig streak!
            self.dig_streak = random.randint(8, 14)
            self.dig_angle = math.atan2(ty - self.y, tx - self.x) if dist_to_target > 6 else self.angle
            self.state = STATE_DIGGING
            return

        # Follow navigation field toward the chamber nearest to the dig site
        target_field = "royal" if ty > 380 else "pantry" if tx < (world.width // 2) else "nursery"
        vx, vy, _ = world.get_flow_direction(self.x, self.y, target_field)
        self.target_angle = math.atan2(vy, vx)

    def _update_nurse(self, dt, world, pheromones, colony):
        """Nurse: Uses flow fields to care for brood, group eggs in nursery, and feed hungry larvae."""
        nx, ny = world.nursery_chamber_pos

        # 1. Relocating egg to nursery
        if self.cargo == CARGO_EGG:
            self.state = STATE_RELOCATING_EGG
            vx, vy, dist = world.get_flow_direction(self.x, self.y, "nursery")
            if dist < 16:
                # Place egg in nursery cluster
                if self.carried_egg:
                    self.carried_egg.x = self.x + random.uniform(-5, 5)
                    self.carried_egg.y = self.y + random.uniform(-3, 3)
                    self.carried_egg.carried = False
                    self.carried_egg = None
                self.cargo = CARGO_NONE
                self.state = STATE_NURSING
                return
            else:
                self.target_angle = math.atan2(vy, vx)
            return

        # 2. Feeding hungry larvae
        if self.state == STATE_FEEDING_LARVA:
            dist_nursery = math.hypot(nx - self.x, ny - self.y)
            if dist_nursery < 25:
                # Feed larva
                for b in colony.brood:
                    if b.stage == Brood.STAGE_LARVA and b.fed_count < 3 and colony.food_stockpile > 0:
                        b.fed_count += 1
                        colony.food_stockpile = max(0, colony.food_stockpile - 1)
                        break
                self.state = STATE_NURSING
            else:
                vx, vy, _ = world.get_flow_direction(self.x, self.y, "nursery")
                self.target_angle = math.atan2(vy, vx)
            return

        # 3. Nursing: check stray eggs or hungry larvae
        self.state = STATE_NURSING
        for b in colony.brood:
            if b.stage == Brood.STAGE_EGG and not b.carried:
                if math.hypot(nx - b.x, ny - b.y) > 30 and math.hypot(self.x - b.x, self.y - b.y) < 18:
                    b.carried = True
                    self.carried_egg = b
                    self.cargo = CARGO_EGG
                    self.state = STATE_RELOCATING_EGG
                    return

        # Check hungry larva
        for b in colony.brood:
            if b.stage == Brood.STAGE_LARVA and b.fed_count < 3 and colony.food_stockpile > 0:
                self.state = STATE_FEEDING_LARVA
                return

        # Gentle pacing between nursery and royal chamber
        target_chamber = "nursery" if random.random() < 0.6 else "royal"
        vx, vy, _ = world.get_flow_direction(self.x, self.y, target_chamber)
        self.target_angle = math.atan2(vy, vx)

    def _step_movement(self, dt, world):
        """Wall collision avoidance, surface ground contour snapping, and smooth stepping."""
        # Smooth turning toward target_angle
        diff = (self.target_angle - self.angle + math.pi) % (2 * math.pi) - math.pi
        self.angle += diff * min(1.0, 5.0 * dt)

        is_actively_digging = (self.caste == CASTE_WORKER and self.subrole == SUBROLE_EXCAVATOR and self.dig_streak > 0)

        if not is_actively_digging:
            # Three feelers ahead to avoid walls
            feeler_dist = 6.0
            cx = self.x + math.cos(self.angle) * feeler_dist
            cy = self.y + math.sin(self.angle) * feeler_dist
            lx = self.x + math.cos(self.angle + 0.55) * feeler_dist
            ly = self.y + math.sin(self.angle + 0.55) * feeler_dist
            rx = self.x + math.cos(self.angle - 0.55) * feeler_dist
            ry = self.y + math.sin(self.angle - 0.55) * feeler_dist

            c_solid = world.is_solid(cx, cy)
            l_solid = world.is_solid(lx, ly)
            r_solid = world.is_solid(rx, ry)

            if c_solid:
                if not l_solid:
                    self.target_angle += 1.2
                elif not r_solid:
                    self.target_angle -= 1.2
                else:
                    self.target_angle += math.pi + random.uniform(-0.3, 0.3)
            else:
                if l_solid and not r_solid:
                    self.target_angle -= 0.12
                elif r_solid and not l_solid:
                    self.target_angle += 0.12

        # Step forward
        move_speed = self.speed * (0.85 if self.cargo != CARGO_NONE else 1.0)
        nx = self.x + math.cos(self.angle) * move_speed * dt
        ny = self.y + math.sin(self.angle) * move_speed * dt

        # Boundary clamping
        nx = max(8, min(world.width - 8, nx))
        ny = max(8, min(world.height - 8, ny))

        # --- Surface Ground-Hugging (Zero Sky Flying) ---
        surf_y = world.get_surface_y(nx)
        is_at_or_above_surface = (ny <= surf_y + 4)
        is_over_entrance = not world.is_solid(nx, SURFACE_Y + 8)

        # Allow downward descent if over entrance crater
        wants_to_descend = (
            self.state in (STATE_RETURNING_FOOD, STATE_GOING_TO_DIG, STATE_HAULING_DIRT)
            and math.sin(self.angle) > 0.05
        )

        if is_at_or_above_surface:
            if not is_over_entrance or not wants_to_descend:
                # Snap strictly to ground contour!
                ny = surf_y - 2
                slope = (world.get_surface_y(nx + 4) - world.get_surface_y(nx - 4)) / 8.0
                base_angle = 0.0 if math.cos(self.angle) >= 0 else math.pi
                self.target_angle = base_angle + math.atan(slope) * (1.0 if math.cos(self.angle) >= 0 else -1.0)

        # Commit position
        if not world.is_solid(nx, ny) or is_actively_digging:
            self.x = nx
            self.y = ny
        else:
            self.target_angle += math.pi * 0.75


class AntColony:
    """Manages ant population, castes, subroles, greetings, and dynamic rebalancing."""
    def __init__(self, world, pheromones):
        self.world = world
        self.pheromones = pheromones
        self.spatial_hash = SpatialHash(cell_size=32, width=world.width, height=world.height)

        self.ants = []
        self.brood = []
        self.threats = []

        self.food_stockpile = 40
        self.queen_egg_timer = 0.0
        self.max_ants = 320
        self.tick_counter = 0

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
        self.tick_counter += 1

        # 1. Update Spatial Hash
        self.spatial_hash.clear()
        for ant in self.ants:
            self.spatial_hash.insert(ant, ant.x, ant.y)

        # 2. Social Greetings Check (Every 4 frames per ant)
        for i, ant in enumerate(self.ants):
            if (i + self.tick_counter) % 4 == 0:
                if (ant.caste == CASTE_WORKER and ant.cargo == CARGO_NONE 
                        and ant.greeting_cooldown <= 0 and ant.greeting_timer <= 0 
                        and ant.state not in (STATE_DIGGING, STATE_COMBAT)):
                    neighbors = self.spatial_hash.query_radius(ant.x, ant.y, 11)
                    for n in neighbors:
                        if (n is not ant and n.caste == CASTE_WORKER and n.cargo == CARGO_NONE 
                                and n.greeting_cooldown <= 0 and n.greeting_timer <= 0):
                            ant.greeting_timer = 0.25
                            n.greeting_timer = 0.25
                            ant.greeting_cooldown = 12.0
                            n.greeting_cooldown = 12.0
                            break

        # 3. Update Ants
        for ant in self.ants:
            ant.update(dt, self.world, self.pheromones, self.spatial_hash, self)

        # Clean dead ants
        self.ants = [a for a in self.ants if a.alive]

        # 4. Update Brood
        hatched_brood = []
        kept_brood = []
        for b in self.brood:
            b.update(dt, self)
            if b.ready_to_hatch:
                hatched_brood.append(b)
            else:
                kept_brood.append(b)
        self.brood = kept_brood

        # Hatch brood into adults
        for b in hatched_brood:
            caste = CASTE_SOLDIER if random.random() < 0.15 else CASTE_WORKER
            self.spawn_ant(b.x, b.y, caste=caste)

        # 5. Update Threats
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
