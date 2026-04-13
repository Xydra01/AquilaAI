"""
Pygame Galaga Clone - Particle System
======================================
Handles visual effects like explosions, trails, and debris.
"""

import pygame
import math
import random
from typing import List

class Particle:
    """Individual particle for visual effects."""
    
    def __init__(self, x: float, y: float, vx: float, vy: float, 
                 color: tuple, lifetime: int = 30):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        
    def update(self):
        """Update particle position and decay."""
        self.x += self.vx
        self.y += self.vy
        self.lifetime -= 1
        
    def draw(self, screen):
        """Draw particle to screen."""
        if self.lifetime > 0:
            alpha = int((self.lifetime / self.max_lifetime) * 255)
            pygame.draw.circle(screen, (*self.color[:3], alpha), 
                             (int(self.x), int(self.y)), 3)

class ParticleSystem:
    """Manages all particles in the game."""
    
    def __init__(self):
        self.particles: List[Particle] = []
        
    def spawn_explosion(self, x: float, y: float, color: tuple, speed: float = 3):
        """Spawn explosion particle effect."""
        for i in range(15):
            angle = math.pi * 2 / 15 * i
            self.particles.append(Particle(
                x=x, y=y, 
                vx=math.cos(angle) * speed * random.uniform(0.8, 1.2),
                vy=math.sin(angle) * speed * random.uniform(0.8, 1.2),
                color=color,
                lifetime=random.randint(20, 35)
            ))
            
    def spawn_trail(self, x: float, y: float, color: tuple):
        """Spawn trail particles."""
        for i in range(5):
            self.particles.append(Particle(
                x=x, y=y - random.uniform(2, 5), 
                vx=0, vy=-random.uniform(1, 2),
                color=color,
                lifetime=random.randint(10, 20)
            ))
            
    def update(self):
        """Update all particles."""
        self.particles = [p for p in self.particles if p.lifetime > 0]
        
    def draw(self, screen):
        """Draw all particles."""
        for particle in self.particles:
            particle.draw(screen)