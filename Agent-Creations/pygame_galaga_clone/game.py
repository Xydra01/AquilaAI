"""
Pygame Galaga Clone - Main Game Class
======================================
Handles game state, collision detection, and main loop.
"""

import pygame
import random
import math
from typing import List, Tuple
from player import PlayerShip
from enemy import EnemyTypes
from bullet import Bullets
from particle import ParticleSystem
from utils import (
    get_random_angle, get_distance, 
    clamp_value, create_starfield, draw_text
)

class GalagaGame:
    """Main game class for Galaga clone."""
    
    def __init__(self):
        pygame.display.set_caption("🚀 Galaga Clone - Space Shooter")
        
        # Screen settings
        self.screen = pygame.display.set_mode((800, 600))
        self.clock = pygame.time.Clock()
        self.running = True
        
        # Colors (Galaga-inspired palette)
        self.colors = {
            'background': (15, 20, 35),       # Deep space blue-black
            'player': (0, 200, 255),          # Cyan ship
            'enemy_bas': (200, 80, 50),       # Orange alien
            'enemy_mid': (255, 100, 50),      # Yellow-orange alien
            'enemy_top': (255, 200, 100),     # Bright yellow alien
            'bullet_player': (0, 255, 200),   # Green player bullets
            'bullet_enemy': (255, 80, 80),    # Red enemy bullets
            'text_ui': (200, 220, 255),       # Light blue UI text
            'explosion': (255, 100, 0),       # Orange explosions
        }
        
        # Game settings
        self.settings = {
            'player_speed': 5,
            'bullet_speed': 10,
            'enemy_speed_base': 2,
            'fire_rate': 300,  # ms between shots
            'wave_time': 10000,  # ms per wave
        }
        
        # Game state
        self.state = {
            'status': 'menu',      # menu, playing, paused, game_over, won
            'score': 0,
            'lives': 3,
            'wave': 1,
            'high_score': 0,
            'time_remaining': 0,
        }
        
        # Initialize game objects
        self.player = None
        self.enemies: List[object] = []
        self.bullets: List[object] = []
        self.particles: ParticleSystem = ParticleSystem()
        self.stars = create_starfield(100)  # Background stars
        
        # Timers
        self.last_shot_time = 0
        self.last_wave_spawn_time = pygame.time.get_ticks()
        self.wave_spawn_interval = 2000  # ms between enemy groups
        
        # Load or create sprite shapes (simple geometric for now)
        self.sprite_cache = {}
        
    def run(self):
        """Main game loop."""
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(60)  # Cap at 60 FPS
            
            if not self.running:
                break
                
        print(f"\n🎮 Game closed. Final Score: {self.state['score']}")

    def handle_events(self):
        """Process pygame events."""
        for event in pygame.event.get():
            if event.type == QUIT:
                self.running = False
                
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    self.running = False
                elif event.key == K_SPACE and self.state['status'] == 'playing':
                    self.player.shoot()
                elif event.key == K_p and self.state['status'] in ('menu', 'playing'):
                    self.toggle_pause()
                elif event.key == K_r and self.state['status'] == 'game_over':
                    self.restart_game()
                elif event.key == K_UP or event.key == K_w:
                    # Quick restart from menu
                    if self.state['status'] == 'menu':
                        self.start_new_game()
                
    def toggle_pause(self):
        """Toggle pause state."""
        if self.state['status'] == 'playing':
            self.state['status'] = 'paused'
            print("⏸️  Paused")
        elif self.state['status'] == 'paused':
            self.state['status'] = 'playing'
            print("▶️  Resumed")
            
    def restart_game(self):
        """Restart game from game over state."""
        self.state['score'] = 0
        self.state['lives'] = 3
        self.state['wave'] = 1
        self.state['status'] = 'menu'
        self.enemies.clear()
        self.bullets.clear()
        self.particles.clear()
        
    def start_new_game(self):
        """Initialize a new game."""
        self.state['score'] = 0
        self.state['lives'] = 3
        self.state['wave'] = 1
        self.state['status'] = 'playing'
        self.enemies.clear()
        self.bullets.clear()
        self.particles.clear()
        self.player = PlayerShip(self.screen, self.colors)
        
    def start_wave(self):
        """Start a new wave of enemies."""
        # Create enemy formation based on wave number
        formation_size = 5 + (self.state['wave'] * 2)
        enemies_per_row = max(3, formation_size // 2)
        
        for row in range(enemies_per_row):
            for col in range(enemies_per_row - row):
                enemy_type = EnemyTypes.get_by_wave(self.state['wave'])
                x = 100 + col * 40 + (row * 30) % 20
                y = 50 + row * 30
                self.enemies.append(EnemyType.create(enemy_type, x, y))
                
        print(f"🌊 Wave {self.state['wave']} started! {len(self.enemies)} enemies spawned.")
        
    def update(self):
        """Update all game objects."""
        if self.state['status'] != 'playing':
            return
            
        # Update player
        self.player.update()
        
        # Handle player shooting cooldown
        now = pygame.time.get_ticks()
        if now - self.last_shot_time > self.settings['fire_rate']:
            self.player.shoot()
            self.last_shot_time = now
            
        # Spawn enemy projectiles periodically
        self.spawn_enemy_projectiles()
        
        # Update bullets
        self.bullets.update()
        
        # Update particles
        self.particles.update()
        
        # Check wave completion
        if len(self.enemies) == 0:
            self.state['status'] = 'menu'
            
        # Update starfield (subtle movement)
        for star in self.stars:
            star.move()
            
    def spawn_enemy_projectiles(self):
        """Spawn enemy bullets periodically."""
        now = pygame.time.get_ticks()
        if now - self.last_wave_spawn_time > 30000:  # Every 30 seconds
            for enemy in self.enemies:
                if random.random() < 0.3:  # 30% chance per enemy
                    angle = get_random_angle()
                    speed = 3 + (self.state['wave'] * 0.5)
                    x_vel = math.cos(angle) * speed
                    y_vel = math.sin(angle) * speed
                    self.bullets.append(Bullet(
                        x=enemy.x, 
                        y=enemy.y + 15,
                        vx=x_vel, vy=y_vel,
                        color=self.colors['bullet_enemy'],
                        is_enemy=True
                    ))
            self.last_wave_spawn_time = now
            
    def check_collisions(self):
        """Check all collision events."""
        for bullet in self.bullets[:]:
            # Check if bullet hit player
            if bullet.is_enemy:
                if get_distance(
                    bullet.x, bullet.y, 
                    self.player.x + 10, self.player.y + 15
                ) < 20:
                    self.player.take_damage()
                    self.bullets.remove(bullet)
                    continue
                    
            # Check if bullet hit any enemy
            for enemy in self.enemies[:]:
                if get_distance(
                    bullet.x, bullet.y, 
                    enemy.x, enemy.y + 15
                ) < 20:
                    self.kill_enemy(enemy)
                    self.bullets.remove(bullet)
                    break
                    
        # Check player vs enemy collision
        for enemy in self.enemies[:]:
            if get_distance(
                enemy.x, enemy.y + 15,
                self.player.x + 10, self.player.y + 15
            ) < 25:
                self.player.take_damage()
                self.kill_enemy(enemy)
                
        # Check boundaries for bullets
        for bullet in self.bullets[:]:
            if (bullet.x < 0 or bullet.x > 800 or 
                bullet.y < 0 or bullet.y > 600):
                self.bullets.remove(bullet)
                
    def kill_enemy(self, enemy):
        """Destroy an enemy and create effects."""
        score = EnemyTypes.get_points(enemy.type) * self.state['wave']
        self.state['score'] += score
        
        # Create explosion particles
        for i in range(10):
            angle = math.pi * 2 / 10 * i
            self.particles.spawn_explosion(
                enemy.x, enemy.y, 
                color=self.colors.get('explosion'),
                speed=3
            )
            
        if score > self.state['high_score']:
            self.state['high_score'] = score
            
    def update_game_state(self):
        """Update game status messages."""
        if self.state['status'] == 'game_over':
            return "GAME OVER - Press R to restart\n"
        elif self.state['status'] == 'paused':
            return "PAUSED - Press P to resume\n"
        else:
            return ""

    def draw(self):
        """Draw everything to the screen."""
        # Clear screen
        self.screen.fill(self.colors['background'])
        
        # Draw background stars
        for star in self.stars:
            self.screen.set_alpha(star.alpha)
            self.screen.blit(pygame.Surface((2, 4), pygame.SRCALPHA).convert(), (star.x, star.y))
            
        # Draw player
        if self.player and self.state['status'] == 'playing':
            self.player.draw(self.screen)
            
        # Draw enemies
        for enemy in self.enemies:
            enemy.draw(self.screen)
            
        # Draw bullets
        for bullet in self.bullets:
            bullet.draw(self.screen)
            
        # Draw particles
        self.particles.draw(self.screen)
        
        # Draw UI overlay
        self.draw_ui()
        
        # Draw status message
        status = self.update_game_state()
        if status:
            draw_text(status, self.screen, (400, 520), 
                      font_size=18, color=self.colors['text_ui'], align='center')
                      
        pygame.display.flip()
        
    def draw_ui(self):
        """Draw the UI overlay."""
        # Score
        score_text = f"SCORE: {self.state['score']}"
        high_score_text = f"HIGH SCORE: {self.state['high_score']}" if self.state['high_score'] else ""
        draw_text(score_text, self.screen, (20, 10), 
                  font_size=24, color=self.colors['text_ui'], align='left')
        draw_text(high_score_text, self.screen, (20, 35), 
                  font_size=16, color=(150, 170, 200), align='left')
                  
        # Wave info
        wave_text = f"WAVE: {self.state['wave']}"
        draw_text(wave_text, self.screen, (400, 10), 
                  font_size=20, color=self.colors['text_ui'], align='center')
                  
        # Lives
        lives_text = f"LIVES: {self.state['lives']}"
        draw_text(lives_text, self.screen, (760, 10), 
                  font_size=24, color=self.colors['text_ui'], align='right')
                  
        # Instructions
        instructions = [
            "ARROWS/WASD: Move",
            "SPACE: Shoot",
            "P: Pause"
        ]
        for i, instruction in enumerate(instructions, 1):
            draw_text(instruction, self.screen, (400, 560 + i * 20), 
                      font_size=14, color=(150, 170, 200), align='center')