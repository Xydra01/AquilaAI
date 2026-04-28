import pygame
import random
import math

# Initialize Pygame
pygame.init()

# Screen settings
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCREEN = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Galaga Clone")
CLOCK = pygame.time.Clock()

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)
PURPLE = (128, 0, 128)

# Game constants
FPS = 60
PLAYER_SPEED = 5
PLAYER_THRUST = 0.3
ENEMY_SPAWN_RATE = 60  # frames between spawns
ENEMY_BASE_SPEED = 2
ENEMY_ZIGZAG_AMPLITUDE = 50
ENEMY_ZIGZAG_PERIOD = 100
ENEMY_HEALTH = 2
BULLET_SPEED = 7
PARTICLE_LIFETIME = 30

# ==================== BASE CLASSES ====================

class Ship:
    """Base class for all ships"""
    
    def __init__(self, x, y, width=40, height=30, color=WHITE):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.health = 1
        self.visible = True
        
    def draw(self, screen):
        """Draw the ship as a simple triangle"""
        if not self.visible:
            return
            
        points = [
            (self.x + self.width // 2, self.y),
            (self.x, self.y + self.height),
            (self.x + self.width, self.y + self.height)
        ]
        pygame.draw.polygon(screen, self.color, points)
        
    def update(self):
        """Base update method - subclasses override"""
        pass
        
    def is_off_screen(self):
        """Check if ship is off screen"""
        return self.x < -self.width or self.x > SCREEN_WIDTH or \
               self.y < -self.height or self.y > SCREEN_HEIGHT

# ==================== PLAYER SHIP ====================

class PlayerShip(Ship):
    """Player ship with thrust and movement"""
    
    def __init__(self, x=SCREEN_WIDTH // 2, y=SCREEN_HEIGHT - 50):
        super().__init__(x, y, width=40, height=30, color=GREEN)
        self.velocity = pygame.math.Vector2(0, 0)
        self.thrusting = False
        self.thruster_flame = pygame.math.Vector2(0, 0)
        
    def update(self):
        """Update player position based on velocity"""
        self.x += self.velocity.x
        self.y += self.velocity.y
        
        # Apply thrust
        if self.thrusting:
            self.velocity.y -= PLAYER_THRUST
            self.thruster_flame.y = -15
            
        # Friction
        self.velocity *= 0.98
        
        # Boundary checks
        self.x = max(0, min(self.x, SCREEN_WIDTH - self.width))
        self.y = max(0, min(self.y, SCREEN_HEIGHT - self.height))
        
    def handle_input(self, keys):
        """Handle player input"""
        self.thrusting = keys[pygame.K_w] or keys[pygame.K_UP]
        self.velocity.x = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.velocity.x = -PLAYER_SPEED
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.velocity.x = PLAYER_SPEED
            
    def draw(self, screen):
        """Draw player ship with thruster flame"""
        super().draw(screen)
        
        # Draw thruster flame
        if self.thrusting:
            flame_points = [
                (self.x + self.width // 2, self.y + self.height),
                (self.x + self.width // 2 - self.thruster_flame.x, 
                 self.y + self.height - self.thruster_flame.y),
                (self.x + self.width // 2 + self.thruster_flame.x, 
                 self.y + self.height - self.thruster_flame.y)
            ]
            flame_color = ORANGE if random.random() < 0.5 else YELLOW
            pygame.draw.polygon(screen, flame_color, flame_points)

# ==================== ENEMY CLASS ====================

class Enemy(Ship):
    """Enemy ship with zig-zag movement patterns"""
    
    def __init__(self, x, y, enemy_type='basic'):
        super().__init__(x, y, width=35, height=25, color=RED)
        self.enemy_type = enemy_type
        self.health = ENEMY_HEALTH
        self.velocity = pygame.math.Vector2(0, 0)
        
        # Movement pattern settings
        self.zigzag_amplitude = ENEMY_ZIGZAG_AMPLITUDE
        self.zigzag_period = ENEMY_ZIGZAG_PERIOD
        self.zigzag_offset = random.uniform(0, self.zigzag_period)
        self.move_speed = ENEMY_BASE_SPEED
        
        # For zig-zag pattern
        self.direction = 1  # 1 for right, -1 for left
        self.zigzag_timer = 0
        
        # Visual properties
        self.rotation = 0
        self.scale = 1.0
        
    def update(self):
        """Update enemy position with zig-zag movement"""
        # Calculate zig-zag movement
        self.zigzag_timer += 1
        zigzag_x = math.sin(self.zigzag_timer / self.zigzag_period * math.pi + 
                           self.zigzag_offset) * self.zigzag_amplitude
        
        # Horizontal movement with zig-zag
        self.x += self.move_speed * self.direction + zigzag_x * 0.3
        
        # Vertical movement (slow descent)
        self.y += self.move_speed * 0.5
        
        # Reverse direction when hitting screen edges
        if self.x <= 0 or self.x >= SCREEN_WIDTH - self.width:
            self.direction *= -1
            
        # Rotation based on zig-zag
        self.rotation = zigzag_x * 0.1
        
        # Check if off screen
        if self.is_off_screen():
            self.visible = False
            
    def draw(self, screen):
        """Draw enemy ship with rotation"""
        if not self.visible:
            return
            
        # Save original rotation
        # Removed unused variable
        
        # Draw enemy as a different shape (inverted triangle with wings)
        wing_width = self.width * 0.4
        wing_height = self.height * 0.3
        
        # Main body
        body_points = [
            (self.x + self.width // 2, self.y),
            (self.x, self.y + self.height),
            (self.x + self.width, self.y + self.height)
        ]
        pygame.draw.polygon(screen, self.color, body_points)
        
        # Draw wings
        wing_points = [
            (self.x - wing_width, self.y + self.height * 0.3),
            (self.x + self.width + wing_width, self.y + self.height * 0.3),
            (self.x + self.width // 2, self.y + self.height)
        ]
        pygame.draw.polygon(screen, PURPLE, wing_points)
        
        # Draw health indicator (small dots)
        if self.health > 1:
            health_x = self.x + self.width // 2
            health_y = self.y - 5
            for i in range(self.health):
                pygame.draw.circle(screen, WHITE, 
                                 (health_x + i * 4, health_y), 3)
                
    def take_damage(self, damage=1):
        """Take damage and reduce health"""
        self.health -= damage
        if self.health <= 0:
            self.visible = False
            return True  # Enemy destroyed
        return False
        
    def reset(self, x, y):
        """Reset enemy to initial state"""
        self.x = x
        self.y = y
        self.health = ENEMY_HEALTH
        self.velocity = pygame.math.Vector2(0, 0)
        self.visible = True
        self.direction = 1
        self.zigzag_timer = 0

# ==================== BULLET CLASS ====================

class Bullet:
    """Projectile class for player and enemy bullets"""
    
    def __init__(self, x, y, is_player_bullet=True, color=GREEN):
        self.x = x
        self.y = y
        self.width = 6
        self.height = 12
        self.is_player_bullet = is_player_bullet
        self.color = color if is_player_bullet else RED
        self.velocity = pygame.math.Vector2(0, -BULLET_SPEED)
        self.active = True
        
    def update(self):
        """Update bullet position"""
        self.y += self.velocity.y
        self.x += self.velocity.x * 0.1  # Slight drift
        
        # Check if off screen
        if self.y < -self.height or self.y > SCREEN_HEIGHT:
            self.active = False
            
    def draw(self, screen):
        """Draw bullet as a small rectangle"""
        if not self.active:
            return
            
        pygame.draw.rect(screen, self.color, 
                        (self.x - self.width // 2, self.y, self.width, self.height))
                        
    def is_off_screen(self):
        """Check if bullet is off screen"""
        return self.y < -self.height or self.y > SCREEN_HEIGHT

# ==================== PARTICLE CLASS ====================

class Particle:
    """Particle for explosion effects"""
    
    def __init__(self, x, y, color, speed=3):
        self.x = x
        self.y = y
        self.color = color
        self.velocity = pygame.math.Vector2(
            random.uniform(-speed, speed),
            random.uniform(-speed, speed)
        )
        self.life = random.randint(10, 30)
        self.active = True
        
    def update(self):
        """Update particle position and life"""
        self.x += self.velocity.x
        self.y += self.velocity.y
        self.life -= 1
        self.velocity *= 0.95  # Slow down over time
        
        if self.life <= 0:
            self.active = False
            
    def draw(self, screen):
        """Draw particle as a small circle"""
        if not self.active:
            return
            
        size = max(1, self.life // 3)
        pygame.draw.circle(screen, self.color, 
                          (int(self.x), int(self.y)), size)

# ==================== GAME MANAGER ====================

class Game:
    """Main game manager"""
    
    def __init__(self):
        self.reset_game()
        
    def reset_game(self):
        """Reset game to initial state"""
        self.state = 'start'  # start, playing, game_over
        self.score = 0
        self.level = 1
        self.wave = 1
        
        # Create player
        self.player = PlayerShip()
        
        # Enemy list
        self.enemies = []
        self.enemy_spawn_timer = 0
        
        # Bullet list
        self.bullets = []
        
        # Particle list
        self.particles = []
        
        # Game timer
        self.frame_count = 0
        self.last_wave_time = 0
        
    def spawn_enemy(self):
        """Spawn a new enemy"""
        if self.enemy_spawn_timer <= 0:
            # Spawn at random x position, top of screen
            x = random.randint(20, SCREEN_WIDTH - 55)
            enemy = Enemy(x, 20, enemy_type='basic')
            self.enemies.append(enemy)
            self.enemy_spawn_timer = ENEMY_SPAWN_RATE
            self.enemy_spawn_timer -= 1
            
    def spawn_particles(self, x, y, color, count=10):
        """Spawn explosion particles"""
        for _ in range(count):
            particle = Particle(x, y, color)
            self.particles.append(particle)
            
    def handle_collisions(self):
        """Handle all collision detection"""
        # Check bullet vs enemy collisions
        for bullet in self.bullets:
            if not bullet.active:
                continue
                
            for enemy in self.enemies:
                if not enemy.visible:
                    continue
                    
                # Simple AABB collision
                if (bullet.x < enemy.x + enemy.width and
                    bullet.x + bullet.width > enemy.x and
                    bullet.y < enemy.y + enemy.height and
                    bullet.y + bullet.height > enemy.y):
                    
                    # Collision detected
                    bullet.active = False
                    enemy.take_damage()
                    
                    # Spawn particles
                    self.spawn_particles(
                        enemy.x + enemy.width // 2,
                        enemy.y + enemy.height // 2,
                        RED,
                        count=8
                    )
                    
                    # Add score
                    self.score += 10
                    
                    # Check if enemy destroyed
                    if enemy.health <= 0:
                        self.spawn_particles(
                            enemy.x + enemy.width // 2,
                            enemy.y + enemy.height // 2,
                            ORANGE,
                            count=15
                        )
                        self.score += 50
                        
        # Check enemy vs player collision
        for enemy in self.enemies:
            if not enemy.visible:
                continue
                
            if (self.player.x < enemy.x + enemy.width and
                self.player.x + self.player.width > enemy.x and
                self.player.y < enemy.y + enemy.height and
                self.player.y + self.player.height > enemy.y):
                
                # Player hit
                self.player.visible = False
                self.state = 'game_over'
                self.spawn_particles(
                    self.player.x + self.player.width // 2,
                    self.player.y + self.player.height // 2,
                    RED,
                    count=30
                )
                
    def draw_start_screen(self):
        """Draw start screen"""
        SCREEN.fill(BLACK)
        
        # Title
        font = pygame.font.Font(None, 72)
        title = font.render("GALAGA CLONE", True, WHITE)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 150))
        SCREEN.blit(title, title_rect)
        
        # Instructions
        font = pygame.font.Font(None, 36)
        instructions = [
            "W/UP: Thrust",
            "A/D or LEFT/RIGHT: Move",
            "Shoot: Spacebar",
            "Press SPACE to Start"
        ]
        
        y = 250
        for line in instructions:
            text = font.render(line, True, GREEN)
            text_rect = text.get_rect(center=(SCREEN_WIDTH // 2, y))
            SCREEN.blit(text, text_rect)
            y += 40
            
        # Score display
        score_text = font.render(f"Score: {self.score}", True, YELLOW)
        score_rect = score_text.get_rect(center=(SCREEN_WIDTH // 2, 50))
        SCREEN.blit(score_text, score_rect)
        
    def draw_game_over_screen(self):
        """Draw game over screen"""
        SCREEN.fill(BLACK)
        
        # Title
        font = pygame.font.Font(None, 72)
        title = font.render("GAME OVER", True, RED)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 150))
        SCREEN.blit(title, title_rect)
        
        # Score
        font = pygame.font.Font(None, 48)
        score_text = font.render(f"Final Score: {self.score}", True, WHITE)
        score_rect = score_text.get_rect(center=(SCREEN_WIDTH // 2, 250))
        SCREEN.blit(score_text, score_rect)
        
        # Restart instruction
        font = pygame.font.Font(None, 36)
        restart_text = font.render("Press SPACE to Restart", True, GREEN)
        restart_rect = restart_text.get_rect(center=(SCREEN_WIDTH // 2, 350))
        SCREEN.blit(restart_text, restart_rect)
        
    def draw(self):
        """Draw everything"""
        SCREEN.fill(BLACK)
        
        if self.state == 'start':
            self.draw_start_screen()
        elif self.state == 'game_over':
            self.draw_game_over_screen()
        else:
            # Draw player
            self.player.draw(SCREEN)
            
            # Draw enemies
            for enemy in self.enemies:
                enemy.draw(SCREEN)
                
            # Draw bullets
            for bullet in self.bullets:
                bullet.draw(SCREEN)
                
            # Draw particles
            for particle in self.particles:
                particle.draw(SCREEN)
                
            # Draw score
            font = pygame.font.Font(None, 36)
            score_text = font.render(f"Score: {self.score}", True, WHITE)
            score_rect = score_text.get_rect(topleft=(10, 10))
            SCREEN.blit(score_text, score_rect)
            
            # Draw level
            level_text = font.render(f"Wave: {self.wave}", True, BLUE)
            level_rect = level_text.get_rect(topright=(SCREEN_WIDTH - 10, 10))
            SCREEN.blit(level_text, level_rect)
            
    def update(self):
        """Update game state"""
        if self.state == 'start':
            return
            
        # Update player
        self.player.update()
        
        # Spawn enemies
        self.enemy_spawn_timer -= 1
        if self.enemy_spawn_timer <= 0:
            self.spawn_enemy()
            
        # Update enemies
        for enemy in self.enemies:
            enemy.update()
            
        # Update bullets
        for bullet in self.bullets:
            bullet.update()
            
        # Update particles
        for particle in self.particles:
            particle.update()
            
        # Handle collisions
        self.handle_collisions()
        
        # Clean up inactive objects
        self.enemies = [e for e in self.enemies if e.visible]
        self.bullets = [b for b in self.bullets if b.active]
        self.particles = [p for p in self.particles if p.active]
        
        # Wave progression
        if len(self.enemies) == 0:
            self.wave += 1
            self.enemy_spawn_timer = max(30, ENEMY_SPAWN_RATE - (self.wave * 5))
            self.last_wave_time = self.frame_count
            
    def handle_input(self, keys):
        """Handle player input"""
        if self.state == 'start':
            if keys[pygame.K_SPACE]:
                self.state = 'playing'
                self.player.handle_input(keys)
                return
                
        elif self.state == 'playing':
            self.player.handle_input(keys)
            
            # Shoot on spacebar
            if keys[pygame.K_SPACE]:
                bullet = Bullet(
                    self.player.x + self.player.width // 2,
                    self.player.y
                )
                self.bullets.append(bullet)
                
        elif self.state == 'game_over':
            if keys[pygame.K_SPACE]:
                self.reset_game()
                
    def run(self):
        """Main game loop"""
        running = True
        
        while running:
            # Event handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    
            # Input handling
            keys = pygame.key.get_pressed()
            self.handle_input(keys)
            
            # Update
            self.update()
            
            # Draw
            self.draw()
            
            # Cap framerate
            CLOCK.tick(FPS)
            
        pygame.quit()

# ==================== MAIN ====================

if __name__ == "__main__":
    game = Game()
    game.run()