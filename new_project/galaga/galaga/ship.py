# Ship class implementation
import pygame

class Ship:
    def __init__(self, screen):
        self.screen = screen
        self.rect = pygame.Rect(0, 0, 64, 96)
        
    @property
    def rect(self):
        return self._rect
    
    @rect.setter
    def rect(self, value):
        self._rect = value
        
    def update(self):
        pass
