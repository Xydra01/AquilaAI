"""
Pygame Galaga Clone - Player Ship
==================================
Handles player movement, shooting, and collision detection.
"""

import pygame
import math
from typing import List

class PlayerShip:
    """Player spaceship with smooth movement and shooting."""
    
    def __init__(self):
        self.width = 50
        self.height = 60
        self.x = 400
        self.y = 500
        self.speed = 5
        self.vx = 0
        self.vy = 0
        self.health = 3
        self.max_health = 3
        self.last_shot_time = 0
        self.shoot_delay = 200  # milliseconds
        
    def handle_input(self, keys_pressed):
        """Handle keyboard input for movement."""
        self.vx = 0
        self.vy = 0
        
        if keys_pressed[pygame.K_LEFT] or keys_pressed[pygame.K_a]:
            self.vx = -self.speed
        if keys_pressed[pygame.K_RIGHT] or keys_pressed[pygame.K_d]:
            self.vx = self.speed
        if keys_pressed[pygame.K_UP] or keys_pressed[pygame.K_w]:
            self.vy = -self.speed * 0.7
        if keys_pressed[pygame.K_DOWN] or keys_pressed[pygame.K_s]:
            self.vy = self.speed * 0.7
            
    def update(self):
        """Update player position with smooth movement."""
        self.x += self.vx
        self.y += self.vy
        
        # Boundary constraints
        self.x = max(25, min(775, self.x))
        self.y = max(0, min(550, self.y))
        
    def draw(self, screen):
        """Draw player ship using simple polygon."""
        # Draw ship body (triangle shape)
        points = [
            (self.x - 25, self.y + 30),  # bottom tip
            (self.x, self.y - 10),       # top center
            (self.x + 25, self.y + 30),  # bottom right
        ]
        
        # Main body color
        pygame.draw.polygon(screen, (0, 255, 255), points)
        
        # Cockpit
        pygame.draw.circle(screen, (100, 200, 255), 
                          (int(self.x), int(self.y - 15)), 8)
        
        # Engine glow
        if self.vx != 0 or self.vy != 0:
            pygame.draw.circle(screen, (255, 100, 0), 
                              (int(self.x + 15), int(self.y + 32)), 6)
            pygame.draw.circle(screen, (255, 150, 50), 
                              (int(self.x - 15), int(self.y + 32)), 6)
        
        # Health indicator
        for i in range(self.health):
            color = [(255, 0, 0), (255, 200, 0), (0, 255, 0)][i]
            pygame.draw.circle(screen, color, 
                              (int(self.x - 10), int(self.y + 45)), 5)

class PlayerBullet:
    """Player projectile."""
    
    def __init__(self, x: float, y: float):
        self.width = 6
        self.height = 12
        self.x = x
        self.y = y
        self.speed = 10
        
    def update(self):
        """Move bullet upward."""
        self.y -= self.speed
        
    def draw(self, screen):
        """Draw bullet."""
        pygame.draw.rect(screen, (255, 255, 255), 
                        (self.x - 3, self.y, self.width, self.height))