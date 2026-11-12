"""
threats.py - Invading insects (beetles, spiders) that trigger soldier defense behavior.
"""

import math
import random
import pygame

class Threat:
    def __init__(self, x, y, threat_type="beetle"):
        self.x = float(x)
        self.y = float(y)
        self.vx = random.uniform(-0.8, 0.8)
        self.vy = 0.0
        self.threat_type = threat_type # "beetle" or "spider"
        self.angle = 0.0
        self.alive = True

        if threat_type == "beetle":
            self.hp = 60.0
            self.max_hp = 60.0
            self.speed = 0.9
            self.size = 7
            self.color = (35, 30, 28)
            self.accent = (180, 120, 40)
        else: # spider
            self.hp = 40.0
            self.max_hp = 40.0
            self.speed = 1.4
            self.size = 6
            self.color = (55, 35, 55)
            self.accent = (220, 60, 40)

        self.anim_frame = 0.0

    def update(self, world, pheromones, ant_spatial_hash):
        if not self.alive:
            return

        self.anim_frame += 0.2

        # Physics: fall if in air
        if not world.is_solid(self.x, self.y + self.size + 1):
            self.vy = min(4.0, self.vy + 0.25)
        else:
            self.vy = 0.0

        # Move horizontally
        new_x = self.x + self.vx * self.speed
        new_y = self.y + self.vy

        # Tunnel wall collision & turning
        if world.is_solid(new_x + (self.size if self.vx > 0 else -self.size), self.y):
            self.vx = -self.vx
        else:
            self.x = max(10, min(world.width - 10, new_x))

        if not world.is_solid(self.x, new_y + self.size):
            self.y = new_y
        else:
            # Stand on ground
            self.vy = 0.0

        # Wandering direction changes
        if random.random() < 0.03:
            self.vx = random.uniform(-1.0, 1.0)

        # Deposit DANGER pheromone around threat position
        pheromones.deposit(self.x, self.y, layer_idx=2, amount=8.0, radius=2)

        # Smooth angle
        if abs(self.vx) > 0.1:
            target_angle = 0.0 if self.vx > 0 else math.pi
            self.angle += (target_angle - self.angle) * 0.2

    def take_damage(self, amount, world):
        self.hp -= amount
        if self.hp <= 0 and self.alive:
            self.alive = False
            # Threat killed! Drops nutrient-rich insect protein food for the colony
            world.drop_food(self.x, self.y, amount=40, food_type="fruit")

    def draw(self, surface):
        if not self.alive:
            return

        ix, iy = int(self.x), int(self.y)
        sz = self.size

        # Draw segmented threat body
        if self.threat_type == "beetle":
            # Carapace shell
            pygame.draw.ellipse(surface, self.color, (ix - sz, iy - sz + 1, sz * 2, sz * 2 - 2))
            pygame.draw.ellipse(surface, self.accent, (ix - sz + 2, iy - sz + 2, sz * 2 - 4, sz * 2 - 5), 1)
            # Head and mandibles
            hx = ix + (sz if self.vx > 0 else -sz)
            pygame.draw.circle(surface, (20, 18, 18), (hx, iy), sz // 2 + 1)
        else: # spider
            # Cephalothorax & abdomen
            pygame.draw.circle(surface, self.accent, (ix, iy), sz // 2)
            pygame.draw.circle(surface, self.color, (ix - 3 if self.vx > 0 else ix + 3, iy - 1), sz - 1)
            # Multiple spindly legs
            leg_phase = math.sin(self.anim_frame)
            for i in range(4):
                lx = ix + (i - 1.5) * 3
                pygame.draw.line(surface, self.color, (lx, iy), (lx + (4 if i % 2 == 0 else -4), iy - 4 + int(leg_phase * 2)), 1)
                pygame.draw.line(surface, (40, 20, 40), (lx, iy), (lx + (5 if i % 2 == 0 else -5), iy + 4 - int(leg_phase * 2)), 1)
