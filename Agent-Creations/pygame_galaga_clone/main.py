"""
Pygame Galaga Clone - Main Game Entry Point
=============================================
A classic arcade shooter inspired by Galaga
"""

import pygame
import sys
import random
import math
from typing import List, Tuple

# Initialize Pygame
pygame.init()

# Screen settings
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Galaga Clone")

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
BLUE = (0, 100, 255)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)

# Game constants
PLAYER_SPEED = 5
BULLET_SPEED = 7
ENEMY_BULLET_SPEED = 4
WAVE_COUNT = 5
LIVES = 3


class Player:
    def __init__(self):
        self.width = 40
        self.height = 40
        self.x = SCREEN_WIDTH // 2 - self.width // 2
        self.y = SCREEN_HEIGHT - 60
        self.speed = PLAYER_SPEED
        self.lives = LIVES
        self.shoot_delay = 0
        self.cooldown = 0
        
    def handle_events(self):
        """Handle quit events and shooting"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            # Shoot on spacebar press (only once per cooldown)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                self.shoot()
        
        return True
        
    def update(self):
        """Update position based on key state"""
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            self.x -= self.speed
        elif keys[pygame.K_RIGHT]:
            self.x += self.speed
            
        # Clamp player position to screen bounds
        self.x = max(0, min(self.x, SCREEN_WIDTH - self.width))
        
    def shoot(self):
        """Create bullet when space is pressed"""
        if self.cooldown == 0:
            bullets.append(Bullet(self.x + self.width // 2 - 3, self.y))
            self.cooldown = 15
            
    def update_cooldown(self):
        """Decrease cooldown timer"""
        if self.cooldown > 0:
            self.cooldown -= 1
    
    def draw(self, screen):
        # Draw player ship (triangle)
        points = [(self.x, self.y),
                  (self.x + 20, self.y - 30),
                  (self.x + 40, self.y)]
        pygame.draw.polygon(screen, GREEN, points, 2)



class Bullet:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.width = 6
        self.height = 12
        self.speed = BULLET_SPEED

    def update(self):
        self.y -= self.speed

    def draw(self, screen):
        pygame.draw.rect(screen, WHITE, (self.x - 3, self.y, self.width, self.height))



class EnemyBullet:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.width = 6
        self.height = 12
        self.speed = ENEMY_BULLET_SPEED

    def update(self):
        self.y += self.speed

    def draw(self, screen):
        pygame.draw.rect(screen, RED, (self.x - 3, self.y, self.width, self.height))



class Enemy:
    def __init__(self, x, y, enemy_type="basic"):
        self.x = x
        self.y = y
        self.width = 40
        self.height = 40
        self.speed = 2
        if enemy_type == "fast":
            self.speed = 3
            self.color = CYAN
            self.health = 1
        elif enemy_type == "tank":
            self.speed = 1
            self.color = MAGENTA
            self.health = 5
        else:  # basic
            self.speed = 2
            self.color = BLUE
            self.health = 2
        self.type = enemy_type

    def update(self):
        self.y += self.speed

    def draw(self, screen):
        # Draw enemy ship (inverted triangle)
        points = [(self.x + self.width // 2, self.y - 10),
                  (self.x, self.y + self.height),
                  (self.x + self.width, self.y + self.height)]
        pygame.draw.polygon(screen, self.color, points, 2)



class Particle:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.size = random.randint(3, 8)
        self.speed = random.randint(1, 4)
        self.angle = random.uniform(0, 2 * math.pi)
        self.color = (random.randint(100, 255), random.randint(100, 255), random.randint(100, 255))
        self.life = random.randint(20, 40)

    def update(self):
        self.x += self.speed * math.cos(self.angle)
        self.y += self.speed * math.sin(self.angle)
        self.life -= 1

    def draw(self, screen):
        if self.life > 0:
            pygame.draw.circle(screen, self.color, (int(self.x), int(self.y)), self.size)



def spawn_enemy():
    """Create a new enemy at random position above the screen"""
    x = random.randint(0, SCREEN_WIDTH - 40)
    y = random.randint(-50, 0)  # Start above screen
    enemy_types = ["basic", "fast", "tank"]
    enemy_type = random.choice(enemy_types)
    enemies.append(Enemy(x, y, enemy_type))


# Global game state
bullets = []
enemy_bullets = []
particles = []
player = Player()
enemies = []
wave = 0

# Main game loop
clock = pygame.time.Clock()
running = True

while running:
    # Handle events
    if not player.handle_events():
        break
    
    # Update player position and cooldowns
    player.update()
    player.update_cooldown()
    
    # Update bullets
    for bullet in bullets[:]:
        bullet.update()
        if bullet.y < 0:
            bullets.remove(bullet)
            
    # Update enemy bullets
    for eb in enemy_bullets[:]:
        eb.update()
        if eb.y > SCREEN_HEIGHT:
            enemy_bullets.remove(eb)
            
    # Spawn enemies
    if wave < WAVE_COUNT and len(enemies) < 10 + wave * 2:
        spawn_enemy()
        
    # Update enemies
    for enemy in enemies[:]:
        enemy.update()
        # Check collision with player bullets
        for bullet in bullets[:]:
            if (bullet.x < enemy.x + enemy.width and
                bullet.x + bullet.width > enemy.x and
                bullet.y < enemy.y + enemy.height and
                bullet.y + bullet.height > enemy.y):
                enemy.health -= 1
                bullet.y = -100  # Remove bullet
                if enemy.health <= 0:
                    enemies.remove(enemy)
                    particles.append(Particle(enemy.x, enemy.y))
        # Check collision with enemy bullets
        for eb in enemy_bullets[:]:
            if (eb.x < player.x + player.width and
                eb.x + eb.width > player.x and
                eb.y < player.y + player.height and
                eb.y + eb.height > player.y):
                player.lives -= 1
                eb.y = -100  # Remove bullet
                particles.append(Particle(player.x, player.y))
                if player.lives <= 0:
                    running = False
        # Check if enemy reached bottom
        if enemy.y > SCREEN_HEIGHT - 50:
            enemies.remove(enemy)
    
    # Update particles
    for p in particles[:]:
        p.update()
        if p.life <= 0:
            particles.remove(p)
            
    # Draw everything
    screen.fill(BLACK)
    
    # Draw player
    player.draw(screen)
    
    # Draw bullets
    for bullet in bullets:
        bullet.draw(screen)
        
    # Draw enemy bullets
    for eb in enemy_bullets:
        eb.draw(screen)
        
    # Draw enemies
    for enemy in enemies:
        enemy.draw(screen)
        
    # Draw particles
    for p in particles:
        p.draw(screen)
    
    # Draw UI
    font = pygame.font.Font(None, 36)
    text = font.render(f"Wave: {wave}", True, WHITE)
    screen.blit(text, (10, 10))
    text = font.render(f"Lives: {player.lives}", True, WHITE)
    screen.blit(text, (SCREEN_WIDTH - 250, 10))
    if len(enemies) > 0:
        enemies_left = WAVE_COUNT * 20 - sum(1 for e in enemies if e.health > 0)
        text = font.render(f"Enemies: {len(enemies)}", True, WHITE)
        screen.blit(text, (SCREEN_WIDTH // 2 - 70, 10))
    
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()