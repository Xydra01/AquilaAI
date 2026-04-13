"""
Pygame Galaga Clone - Enemy Types System
========================================
Handles multiple enemy types with different behaviors.
"""

import pygame
import random
from typing import List, Dict
from utils import get_distance

class EnemyTypes:
    """Enemy type definitions."""
    
    # Base stats (scale by wave)
    TYPES = {
        'bas': {
            'name': 'Bas',
            'color': (200, 80, 50),
            'health': 3,
            'speed': 2,
            'points': 100,
            'fire_rate': 2000,  # ms between shots
        },
        'mid': {
            'name': 'Mid',
            'color': (255, 100, 50),
            'health': 5,
            'speed': 3,
            'points': 200,
            'fire_rate': 1500,
        },
        'top': {
            'name': 'Top',
            'color': (255, 200, 100),
            'health': 8,
            'speed': 4,
            'points': 300,
            'fire_rate': 1000,
        },
    }
    
    @staticmethod
    def get_by_wave(wave: int):
        """Get enemy type based on wave."""
        if wave <= 2:
            return 'bas'
        elif wave <= 5:
            return random.choice(['bas', 'mid'])
        else:
            return random.choice(['bas', 'mid', 'top'])
            
    @staticmethod
    def get_points(enemy_type: str) -> int:
        """Get points for enemy type."""
        return EnemyTypes.TYPES[enemy_type]['points']
        
class Enemy:
    """Base enemy class."""
    
    def __init__(self, x: float, y: float, enemy_type: str):
        self.x = x
        self.y = y
        self.type = enemy_type
        stats = EnemyTypes.TYPES[enemy_type]
        
        self.width = 35
        self.height = 25
        self.health = stats['health'] * (1 + (wave - 1) * 0.5)
        self.speed = stats['speed']
        self.color = stats['color']
        
    def take_damage(self, amount: int):
        """Reduce enemy health."""
        self.health -= amount
        
    def draw(self, screen):
        """Draw enemy sprite."""
        # Enemy body (inverted triangle)
        points = [
            (self.x + self.width // 2, self.y),      # Bottom
            (self.x, self.y - self.height),          # Top left
            (self.x + self.width, self.y - self.height)   # Top right
        ]
        
        pygame.draw.polygon(screen, self.color, points, 3)
        
        # Draw health bar above enemy
        if self.health < EnemyTypes.TYPES[self.type]['health'] * (1 + 0.5):
            max_width = 40
            current_width = int((self.health / 
                               EnemyTypes.TYPES[self.type]['health']) * max_width)
            
            pygame.draw.rect(screen, (30, 30, 40), 
                           (self.x - 20, self.y - 35, max_width, 6))
            pygame.draw.rect(screen, self.color, 
                           (self.x - 20, self.y - 35, current_width, 6))