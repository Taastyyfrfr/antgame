"""
ants.py - Ant colony simulation with centerline flow-field navigation,
clean single-authority movement, frame-tick dt units, and guaranteed excavation.
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

        self.age += dt * 0.015 # tick based growth
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

        # Total distance traveled tracker
        self.distance_traveled = 0.0

        # Morphology & speed per caste (speed in pixels per unit dt)
        if caste == CASTE_QUEEN:
            self.state = "Ruling / Laying Eggs"
            self.length = 20.0
            self.width = 7.0
            self.speed = 0.55
            self.base_color = (70, 30, 20)
            self.head_color = (60, 25, 15)
        elif caste == CASTE_SOLDIER:
            self.state = STATE_PATROLLING
            self.length = 14.0
            self.width = 5.0
            self.speed = 1.3
            self.base_color = (95, 45, 25)
            self.head_color = (135, 42, 22)
        else: # WORKER
            self.length = 10.0
            self.width = 3.5
            self.speed = 1.55
            self.base_color = (75, 40, 25)
            self.head_color = (65, 32, 20)
            if subrole == SUBROLE_FORAGER:
                self.state = STATE_SURFACE_FORAGING if y <= SURFACE_Y + 4 else STATE_EXITING_NEST
            elif subrole == SUBROLE_EXCAVATOR:
                self.state = STATE_GOING_TO_DIG
            else: # Nurse
                self.state = STATE_NURSING

        # Timers (all calibrated to frame-tick dt units where 30 dt = 1 sec)
        self.walk_phase = random.uniform(0, 10.0)
        self.pheromone_timer = 0.0
        self.target_threat = None
        self.greeting_timer = 0.0
        self.greeting_cooldown = random.uniform(100.0, 300.0)
        self.rest_timer = 0.0

        # Excavator variables
        self.dig_bites_remaining = 0
        self.dig_bite_timer = 0.0
        self.dig_target = (640, 465)

        # Forager surface direction (1 = right, -1 = left)
        self.surface_dir = 1 if random.random() < 0.5 else -1

    def update(self, dt, world, pheromones, spatial_hash, colony):
        if not self.alive:
            return

        self.walk_phase += self.speed * 0.25 * dt

        # Energy consumption (drains over ~2000 ticks)
        self.energy = max(0.0, self.energy - 0.015 * dt)

        # Greeting countdown
        if self.greeting_cooldown > 0:
            self.greeting_cooldown -= dt

        if self.greeting_timer > 0:
            self.greeting_timer -= dt
            # Wiggle antennae during greeting; do not translate
            self.walk_phase += 0.4 * dt
            return

        # Queen behavior
        if self.caste == CASTE_QUEEN:
            self._update_queen(dt, world, colony)
            self._step_movement(dt, world)
            return

        # Rest state logic
        if self.state == STATE_RESTING:
            self.rest_timer -= dt
            self.energy = min(100.0, self.energy + 0.8 * dt)
            if self.rest_timer <= 0:
                if self.subrole == SUBROLE_FORAGER:
                    self.state = STATE_EXITING_NEST
                elif self.subrole == SUBROLE_EXCAVATOR:
                    self.state = STATE_GOING_TO_DIG
                else:
                    self.state = STATE_NURSING
            return

        # Check fatigue (workers rest when energy drops below 10)
        if self.caste == CASTE_WORKER and self.cargo == CARGO_NONE and self.energy < 10.0:
            self.state = STATE_RESTING
            self.rest_timer = 120.0 # 4 seconds rest
            return

        # Pheromone emission timer (every 30 ticks = 1 second)
        self.pheromone_timer += dt
        if self.pheromone_timer >= 30.0:
            self.pheromone_timer = 0.0
            if self.cargo == CARGO_FOOD:
                # Strong FOOD pheromone trail
                pheromones.deposit(self.x, self.y, layer_idx=1, amount=25.0, radius=2)
            elif self.y > SURFACE_Y:
                # Faint HOME trail in tunnels
                pheromones.deposit(self.x, self.y, layer_idx=0, amount=8.0, radius=1)

        # Caste state dispatch
        if self.caste == CASTE_SOLDIER:
            self._update_soldier(dt, world, pheromones, colony)
        else:
            self._update_worker(dt, world, pheromones, colony)

        # Single-authority movement stepping
        self._step_movement(dt, world)

    def _update_queen(self, dt, world, colony):
        """Queen rests in royal chamber and produces eggs when food is available."""
        self.state = "Ruling / Laying Eggs"
        rx, ry = world.royal_chamber_pos
        dx = rx - self.x
        dy = ry - self.y
        dist = math.hypot(dx, dy)
        if dist > 24:
            self.target_angle = math.atan2(dy, dx)
        else:
            if random.random() < 0.015:
                self.target_angle = random.uniform(0, math.pi * 2)

        # Egg production every 250 ticks (~8.3s) if food available
        colony.queen_egg_timer += dt
        if colony.food_stockpile > 0 and colony.queen_egg_timer >= 250.0:
            colony.queen_egg_timer = 0.0
            colony.food_stockpile = max(0, colony.food_stockpile - 1)
            colony.spawn_brood(self.x + random.uniform(-8, 8), self.y + random.uniform(-4, 4), Brood.STAGE_EGG)

    def _update_soldier(self, dt, world, pheromones, colony):
        """Soldier patrols entrance and intercepts threats with fierce combat."""
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
                closest_threat.take_damage(1.5 * dt, world)
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
            if self.y > 320:
                vx, vy, _ = world.get_flow_direction(self.x, self.y, "surface")
                self.target_angle = math.atan2(vy, vx)
            elif self.y <= SURFACE_Y + 4:
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
                # On surface: head toward entrance crater (x=640)
                entrance_x = world.width // 2
                dx = entrance_x - self.x
                if abs(dx) > 10:
                    self.target_angle = 0.0 if dx > 0 else math.pi
                else:
                    # Within 10px of entrance: dive down into tunnel
                    self.target_angle = math.pi / 2
                return
            else:
                # Inside tunnels: follow flow field to pantry
                vx, vy, dist = world.get_flow_direction(self.x, self.y, "pantry")
                px, py = world.food_storage_pos
                if dist < 24 or math.hypot(px - self.x, py - self.y) < 28:
                    # Reached pantry! Store food
                    self.cargo = CARGO_NONE
                    colony.food_stockpile += 1
                    colony.total_food_delivered += 1
                    self.energy = 100.0
                    self.state = STATE_EXITING_NEST
                    return
                else:
                    self.target_angle = math.atan2(vy, vx)
                return

        # 2. Exiting nest toward surface (if underground and unladen)
        surf_y = world.get_surface_y(self.x)
        if self.y > surf_y + 4:
            self.state = STATE_EXITING_NEST
            vx, vy, _ = world.get_flow_direction(self.x, self.y, "surface")
            self.target_angle = math.atan2(vy, vx)
            return

        # 3. Surface foraging (self.y <= surf_y + 4)
        self.state = STATE_SURFACE_FORAGING
        # Check nearby food items
        for food in world.food_items:
            if food.amount > 0 and math.hypot(food.x - self.x, food.y - self.y) < 26:
                food.amount -= 1
                self.cargo = CARGO_FOOD
                self.state = STATE_RETURNING_FOOD
                self.target_angle = math.pi if self.x > (world.width // 2) else 0.0
                return

        # Follow FOOD pheromone trail on surface if present
        f_bias, f_mag = pheromones.sense_forward(self.x, self.y, self.angle, layer_idx=1, dist=18.0)
        if f_mag > 0.1:
            self.target_angle += f_bias * 0.4
        else:
            if self.x < 45:
                self.surface_dir = 1
            elif self.x > world.width - 45:
                self.surface_dir = -1
            elif random.random() < 0.015:
                self.surface_dir = -self.surface_dir

            self.target_angle = 0.0 if self.surface_dir > 0 else math.pi

    def _update_excavator(self, dt, world, pheromones, colony):
        """Excavator: Uses flow field to reach dig sites, carves 10 bites, hauls dirt to mound."""
        # 1. Hauling excavated dirt to surface mound
        if self.cargo == CARGO_DIRT:
            self.state = STATE_HAULING_DIRT
            surf_y = world.get_surface_y(self.x)
            entrance_x = world.width // 2

            if self.y <= surf_y + 4:
                # On surface! Walk 18-45px left or right onto anthill mound
                mound_target_x = entrance_x + (32 if self.surface_dir > 0 else -32)
                dx = mound_target_x - self.x

                if abs(dx) > 10:
                    self.target_angle = 0.0 if dx > 0 else math.pi
                else:
                    # Deposit dirt pellet onto mound slopes
                    world.fill_pixel(self.x, surf_y, 6) # CELL_MOUND
                    world.fill_pixel(self.x, surf_y - 1, 6) # Mound height
                    self.cargo = CARGO_NONE
                    self.dig_target = world.get_active_dig_target()
                    self.state = STATE_GOING_TO_DIG
                    self.surface_dir = -self.surface_dir
                    return
            else:
                vx, vy, _ = world.get_flow_direction(self.x, self.y, "surface")
                self.target_angle = math.atan2(vy, vx)
            return

        # 2. Executing an active digging streak (10 bites, 1 bite every 3 ticks)
        if self.state == STATE_DIGGING or self.dig_bites_remaining > 0:
            self.state = STATE_DIGGING
            self.dig_bite_timer += dt

            # Stop moving translationally while biting dirt
            tx, ty = self.dig_target
            self.target_angle = math.atan2(ty - self.y, tx - self.x) if math.hypot(tx - self.x, ty - self.y) > 5 else self.angle

            if self.dig_bite_timer >= 3.0:
                self.dig_bite_timer = 0.0
                bite_x = self.x + math.cos(self.target_angle) * 7.0
                bite_y = self.y + math.sin(self.target_angle) * 7.0

                if world.get_cell(bite_x, bite_y) != 5: # Not bedrock
                    world.carve_circle(bite_x, bite_y, radius=7, play_effects=True)
                    self.dig_bites_remaining -= 1
                    # Spawn dirt particles
                    world.add_falling_dirt(bite_x, bite_y)
                else:
                    self.dig_bites_remaining = 0

                if self.dig_bites_remaining <= 0:
                    self.cargo = CARGO_DIRT
                    self.state = STATE_HAULING_DIRT
                    world.nav_dirty = True
            return

        # 3. Heading to dig site using flow field
        self.state = STATE_GOING_TO_DIG
        surf_y = world.get_surface_y(self.x)
        if self.y <= surf_y + 4:
            # On surface: head to entrance crater
            entrance_x = world.width // 2
            dx = entrance_x - self.x
            if abs(dx) > 10:
                self.target_angle = 0.0 if dx > 0 else math.pi
            else:
                self.target_angle = math.pi / 2
            return

        tx, ty = self.dig_target
        dist_to_target = math.hypot(tx - self.x, ty - self.y)

        # Check if within 14px of dig target or front is solid diggable dirt
        front_x = self.x + math.cos(self.angle) * 8.0
        front_y = self.y + math.sin(self.angle) * 8.0
        if dist_to_target < 14.0 or (world.get_cell(front_x, front_y) not in (0, 5) and self.y > 200):
            self.state = STATE_DIGGING
            self.dig_bites_remaining = 10
            self.dig_bite_timer = 0.0
            return

        # Follow "dig" flow field
        vx, vy, _ = world.get_flow_direction(self.x, self.y, "dig")
        self.target_angle = math.atan2(vy, vx)

    def _update_nurse(self, dt, world, pheromones, colony):
        """Nurse: Uses flow fields to care for brood, group eggs in nursery, and feed hungry larvae."""
        nx, ny = world.nursery_chamber_pos

        # 1. Relocating egg to nursery
        if self.cargo == CARGO_EGG:
            self.state = STATE_RELOCATING_EGG
            vx, vy, dist = world.get_flow_direction(self.x, self.y, "nursery")
            if dist < 14:
                if self.carried_egg:
                    self.carried_egg.x = self.x + random.uniform(-4, 4)
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

        for b in colony.brood:
            if b.stage == Brood.STAGE_LARVA and b.fed_count < 3 and colony.food_stockpile > 0:
                self.state = STATE_FEEDING_LARVA
                return

        # Pacing near nursery
        vx, vy, _ = world.get_flow_direction(self.x, self.y, "nursery")
        self.target_angle = math.atan2(vy, vx)

    def _step_movement(self, dt, world):
        """Clean single-authority movement with wall sliding and surface contour ground-hugging."""
        if self.state == STATE_DIGGING:
            return # Stay in place while actively carving

        # 1. Smooth turn interpolation (0.25 rad per unit dt)
        diff = (self.target_angle - self.angle + math.pi) % (2 * math.pi) - math.pi
        self.angle += diff * min(1.0, 0.25 * dt)

        # 2. Calculate intended next position
        move_speed = self.speed * (0.85 if self.cargo != CARGO_NONE else 1.0)
        step_dist = move_speed * dt
        nx = self.x + math.cos(self.angle) * step_dist
        ny = self.y + math.sin(self.angle) * step_dist

        # Clamp inside world boundaries
        nx = max(8, min(world.width - 8, nx))
        ny = max(8, min(world.height - 8, ny))

        # 3. Surface ground-hugging: strictly snap y to terrain line
        surf_y = world.get_surface_y(nx)
        is_at_or_above_surface = (ny <= surf_y + 3)
        entrance_x = world.width // 2
        is_near_entrance = (abs(nx - entrance_x) <= 12)

        wants_to_descend = (
            self.state in (STATE_RETURNING_FOOD, STATE_GOING_TO_DIG)
            and is_near_entrance
        )

        if is_at_or_above_surface:
            if not wants_to_descend:
                # Snap strictly to ground contour - never float in sky!
                ny = surf_y - 2
                slope = (world.get_surface_y(nx + 4) - world.get_surface_y(nx - 4)) / 8.0
                base_angle = 0.0 if math.cos(self.angle) >= 0 else math.pi
                self.target_angle = base_angle + math.atan(slope) * (1.0 if math.cos(self.angle) >= 0 else -1.0)

        # 4. Collision check and parallel sliding (never bounce 180 deg)
        if not world.is_solid(nx, ny):
            self.distance_traveled += math.hypot(nx - self.x, ny - self.y)
            self.x = nx
            self.y = ny
        else:
            # Try sliding along x-axis only
            if not world.is_solid(nx, self.y):
                self.distance_traveled += abs(nx - self.x)
                self.x = nx
            # Or try sliding along y-axis only
            elif not world.is_solid(self.x, ny):
                self.distance_traveled += abs(ny - self.y)
                self.y = ny
            else:
                # Small gentle adjustment without 180 bounce
                self.target_angle += random.choice([-0.3, 0.3])


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

        # Track total stats for verification
        self.total_food_delivered = 0

        # Spawn Queen in Royal Chamber
        qx, qy = world.royal_chamber_pos
        self.queen = Ant(qx, qy, caste=CASTE_QUEEN, colony=self)
        self.ants.append(self.queen)

        # Spawn starter Workers with balanced subroles (45% Forager, 35% Excavator, 20% Nurse)
        spawned_workers = 0
        attempts = 0
        while spawned_workers < 28 and attempts < 150:
            attempts += 1
            subrole = SUBROLE_FORAGER if spawned_workers % 10 < 5 else SUBROLE_EXCAVATOR if spawned_workers % 10 < 8 else SUBROLE_NURSE
            if subrole == SUBROLE_FORAGER and spawned_workers < 5:
                # Early foragers patrolling surface grass / entrance mound
                ax = 640 + random.uniform(-40, 40)
                ay = world.get_surface_y(ax) - 2
            elif subrole == SUBROLE_FORAGER and spawned_workers < 8:
                # Early foragers in upper entrance shaft
                ax = 640 + random.uniform(-8, 8)
                ay = random.uniform(160, 220)
            else:
                ax = qx + random.uniform(-30, 30)
                ay = qy + random.uniform(-16, 16)

            if not world.is_solid(ax, ay) or ay <= world.get_surface_y(ax):
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
                            ant.greeting_timer = 8.0 # 8 ticks greeting
                            n.greeting_timer = 8.0
                            ant.greeting_cooldown = 300.0 # 10s cooldown
                            n.greeting_cooldown = 300.0
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
