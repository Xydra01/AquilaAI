"""
Pygame Galaga Clone - Utility Functions
========================================
Helper functions for math, drawing, and game logic.
"""

import pygame
import random
import math

def get_random_angle() -> float:
    """Generate a random angle in radians."""
    return random.uniform(0, math.pi * 2)

def get_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    """Calculate distance between two points."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def clamp_value(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))

def create_starfield(count: int = 100):
    """Create background starfield."""
    stars = []
    for i in range(count):
        stars.append({
            'x': random.randint(0, 800),
            'y': random.randint(0, 600),
            'size': random.randint(1, 3),
            'alpha': random.uniform(0.3, 0.8)
        })
    return stars

def draw_text(text: str, font_size: int, color: tuple, screen, x: int, y: int):
    """Draw text to screen with optional background box."""
    font = pygame.font.Font(None, font_size)
    text_surface = font.render(text, True, color)
    rect = text_surface.get_rect(center=(x, y))
    screen.blit(text_surface, rect)

def draw_button(text: str, x: int, y: int, width: int, height: int, 
                color: tuple, hover_color: tuple):
    """Draw a button with hover effect."""
    mouse_pos = pygame.mouse.get_pos()
    if (x < mouse_pos[0] < x + width and y < mouse_pos[1] < y + height):
        pygame.draw.rect(screen, hover_color, (x - 2, y - 2, width + 4, height + 4))
    else:
        pygame.draw.rect(screen, color, (x - 2, y - 2, width + 4, height + 4))
    
    draw_text(text, 18, (0, 0, 0), screen, x + width // 2, y + height // 2)

def generate_wave_pattern(wave_num: int):
    """Generate enemy formation pattern based on wave number."""
    patterns = {
        1: {'type': 'grid', 'rows': 5, 'cols': 3},
        2: {'type': 'zigzag', 'angle': math.pi/4},
        3: {'type': 'diamond', 'center_x': 400, 'center_y': 150},
        4: {'type': 'grid', 'rows': 6, 'cols': 4},
        5: {'type': 'random', 'spread': 0.3}
    }
    return patterns.get(wave_num, patterns[1])
"""
"""
