"""
Pygame Galaga Clone - Enemy System
===================================
Handles alien enemies, wave spawning, and formation patterns.
"""

import pygame
import math
import random
from typing import List

class Enemy:
    """Base enemy class."""
    
    def __init__(self, x: float, y: float, enemy_type: int = 0):
        self.x = x
        self.y = y
        self.enemy_type = enemy_type
        self.health = 1
        self.max_health = 1
        self.alive = True
        
        # Movement properties based on type
        if enemy_type == 0:  # Basic Grunt
            self.speed = 2
            self.width = 35
            self.height = 30
            self.color = (150, 50, 50)
            self.shoot_chance = 0.01
        elif enemy_type == 1:  # Fast Scout
            self.speed = 4
            self.width = 30
            self.height = 25
            self.color = (200, 150, 50)
            self.shoot_chance = 0.008
        elif enemy_type == 2:  # Tank Boss
            self.speed = 1.5
            self.width = 45
            self.height = 35
            self.health = 5
            self.max_health = 5
            self.color = (50, 50, 200)
            self.shoot_chance = 0.015
            
    def update(self):
        """Update enemy position."""
        self.x += self.speed
        
        # Boundary bounce
        if self.x >= 800 - self.width or self.x <= 0:
            self.speed *= -1
            
    def draw(self, screen):
        """Draw enemy shape."""
        # Main body
        pygame.draw.polygon(screen, self.color, [
            (self.x + self.width // 2, self.y),
            (self.x, self.y + self.height),
            (self.x + self.width, self.y + self.height)
        ])
        
        # Wings
        wing_points = [
            (self.x - 5, self.y + 10),
            (self.x - 15, self.y + 20),
            (self.x + self.width + 5, self.y + 10),
            (self.x + self.width - 5, self.y + 20)
        ]
        pygame.draw.polygon(screen, self.color, wing_points)
        
        # Health bar if damaged
        if self.health < self.max_health:
            health_ratio = self.health / self.max_health
            pygame.draw.rect(screen, (100, 100, 100), 
                           (self.x + 5, self.y - 8, self.width - 10, 4))
            pygame.draw.rect(screen, (255, 0, 0), 
                           (self.x + 5, self.y - 8, (self.width - 10) * health_ratio, 4))

class EnemyWave:
    """Manages enemy spawning and wave progression."""
    
    def __init__(self):
        self.enemies: List[Enemy] = []
        self.wave_num = 0
        self.pattern = None
        
    def spawn_wave(self, screen_width: int = 800, screen_height: int = 600):
        """Spawn enemies in current wave pattern."""
        self.pattern = generate_wave_pattern(self.wave_num)
        
        if self.pattern['type'] == 'grid':
            rows = self.pattern.get('rows', 5)
            cols = self.pattern.get('cols', 3)
            
            for row in range(rows):
                for col in range(cols):
                    x = (screen_width // 2) - ((cols - 1) * 70) + (col * 70)
                    y = 50 + (row * 60)
                    enemy_type = random.choice([0, 0, 1]) if row > 2 else 0
                    self.en