import pygame
import math
import random

# Initialize Pygame
pygame.init()

# Screen setup
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Galaga Clone")
clock = pygame.time.Clock()

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)

# Game constants
PLAYER_SPEED = 5
PLAYER_THRUST = 0.2
ENEMY_SPEED = 2
ENEMY_ZIGZAG = 0.02
BULLET_SPEED = 7
PARTICLE_LIFETIME = 30

class Particle:
    """Particle effect for explosions"""
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.vx = random.uniform(-2, 2)
        self.vy = random.uniform(-2, 2)
        self.life = PARTICLE_LIFETIME
        self.color = color
        self.size = random.randint(2, 5)
    
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        self.size = max(0, self.size - 0.1)
        return self.life > 0
    
    def draw(self, surface):
        if self.life > 0:
            alpha = int(255 * (self.life / PARTICLE_LIFETIME))
            pygame.draw.circle(surface, (*self.color[:3], alpha), (int(self.x), int(self.y)), self.size)

class Bullet:
    """Player and enemy projectiles"""
    def __init__(self, x, y, direction, is_player=True):
        self.x = x
        self.y = y
        self.direction = direction  # 1 for up, -1 for down
        self.is_player = is_player
        self.speed = BULLET_SPEED
        self.width = 4
        self.height = 10
    
    def update(self):
        self.y += self.direction * self.speed
        return 0 <= self.y < SCREEN_HEIGHT
    
    def draw(self, surface):
        color = YELLOW if self.is_player else RED
        pygame.draw.rect(surface, color, (self.x - self.width//2, self.y, self.width, self.height))

class Ship:
    """Base class for player and enemy ships"""
    def __init__(self, x, y, is_player=False):
        self.x = x
        self.y = y
        self.width = 40
        self.height = 30
        self.is_player = is_player
        self.color = GREEN if is_player else ORANGE
        self.thrust = 0
        self.velocity = 0
        self.speed = PLAYER_SPEED if is_player else ENEMY_SPEED
    
    def update(self):
        self.velocity += self.thrust
        self.velocity = max(-self.speed, min(self.speed, self.velocity))
        self.x += self.velocity
        self.y += self.velocity
        
        # Boundary checks
        if self.x < 0:
            self.x = 0
        if self.x > SCREEN_WIDTH - self.width:
            self.x = SCREEN_WIDTH - self.width
        if self.y < 0:
            self.y = 0
        if self.y > SCREEN_HEIGHT - self.height:
            self.y = SCREEN_HEIGHT - self.height
    
    def apply_thrust(self, thrust_input):
        if thrust_input:
            self.thrust = PLAYER_THRUST if self.is_player else -ENEMY_SPEED * 0.5
        else:
            self.thrust = 0
    
    def draw(self, surface):
        # Draw ship body
        pygame.draw.polygon(surface, self.color, [
            (self.x + self.width//2, self.y),
            (self.x, self.y + self.height),
            (self.x + self.width, self.y + self.height)
        ])
        # Draw cockpit
        pygame.draw.circle(surface, WHITE, (self.x + self.width//2, self.y + 10), 5)

class PlayerShip(Ship):
    """Player ship with thrust and movement"""
    def __init__(self, x, y):
        super().__init__(x, y, is_player=True)
        self.width = 50
        self.height = 35
        self.color = GREEN
        self.thrust = 0
        self.velocity = 0
    
    def update(self):
        self.velocity += self.thrust
        self.velocity = max(-self.speed, min(self.speed, self.velocity))
        self.x += self.velocity
        self.y += self.velocity
        
        # Boundary checks
        if self.x < 0:
            self.x = 0
        if self.x > SCREEN_WIDTH - self.width:
            self.x = SCREEN_WIDTH - self.width
        if self.y < 0:
            self.y = 0
        if self.y > SCREEN_HEIGHT - self.height:
            self.y = SCREEN_HEIGHT - self.height
    
    def apply_thrust(self, thrust_input):
        if thrust_input:
            self.thrust = PLAYER_THRUST
        else:
            self.thrust = 0
    
    def draw(self, surface):
        # Draw ship body
        pygame.draw.polygon(surface, self.color, [
            (self.x + self.width//2, self.y),
            (self.x, self.y + self.height),
            (self.x + self.width, self.y + self.height)
        ])
        # Draw cockpit
        pygame.draw.circle(surface, WHITE, (self.x + self.width//2, self.y + 10), 5)
        # Draw thruster flame when thrusting
        if self.thrust > 0:
            pygame.draw.rect(surface, RED, (self.x + 15, self.y + self.height, 10, 15))

class EnemyShip(Ship):
    """Enemy ship with zig-zag movement pattern"""
    def __init__(self, x, y):
        super().__init__(x, y, is_player=False)
        self.width = 45
        self.height = 30
        self.color = ORANGE
        self.direction = 1
        self.zigzag_timer = 0
        self.zigzag_period = 100
    
    def update(self):
        # Horizontal movement with zig-zag
        self.zigzag_timer += 1
        if self.zigzag_timer >= self.zigzag_period:
            self.direction *= -1
            self.zigzag_timer = 0
        
        self.x += self.speed * self.direction * 0.5
        self.y += self.speed * 0.3
        
        # Boundary checks
        if self.x < 0:
            self.x = 0
        if self.x > SCREEN_WIDTH - self.width:
            self.x = SCREEN_WIDTH - self.width
        if self.y < 0:
            self.y = 0
        if self.y > SCREEN_HEIGHT - self.height:
            self.y = SCREEN_HEIGHT - self.height
    
    def draw(self, surface):
        # Draw enemy ship body
        pygame.draw.polygon(surface, self.color, [
            (self.x + self.width//2, self.y),
            (self.x, self.y + self.height),
            (self.x + self.width, self.y + self.height)
        ])
        # Draw enemy cockpit
        pygame.draw.circle(surface, WHITE, (self.x + self.width//2, self.y + 10), 4)

class Game:
    """Main game class"""
    def __init__(self):
        self.score = 0
        self.game_over = False
        self.running = True
        self.player = PlayerShip(SCREEN_WIDTH // 2 - 25, SCREEN_HEIGHT - 60)
        self.enemies = []
        self.bullets = []
        self.particles = []
        self.enemy_spawn_timer = 0
        self.enemy_spawn_interval = 60
        self.font = pygame.font.Font(None, 36)
    
    def spawn_enemy(self):
        x = random.randint(0, SCREEN_WIDTH - 50)
        y = random.randint(0, SCREEN_HEIGHT // 2)
        self.enemies.append(EnemyShip(x, y))
    
    def spawn_bullet(self, ship):
        if ship.is_player:
            x = ship.x + ship.width // 2 - 2
            y = ship.y
        else:
            x = ship.x + ship.width // 2 - 2
            y = ship.y + ship.height
        self.bullets.append(Bullet(x, y, 1 if ship.is_player else -1, ship.is_player))
    
    def create_explosion(self, x, y):
        for _ in range(10):
            self.particles.append(Particle(x, y, random.choice([RED, ORANGE, YELLOW])))
    
    def check_collisions(self):
        for bullet in self.bullets[:]:
            for enemy in self.enemies[:]:
                if (bullet.x < enemy.x + enemy.width and
                    bullet.x + bullet.width > enemy.x and
                    bullet.y < enemy.y + enemy.height and
                    bullet.y + bullet.height > enemy.y):
                    self.create_explosion(enemy.x + enemy.width // 2, enemy.y + enemy.height // 2)
                    self.enemies.remove(enemy)
                    self.bullets.remove(bullet)
                    self.score += 100
                    break
            else:
                continue
            break
        
        for bullet in self.bullets[:]:
            if bullet.y < 0:
                self.bullets.remove(bullet)
        
        for enemy in self.enemies[:]:
            if (enemy.x < self.player.x + self.player.width and
                enemy.x + enemy.width > self.player.x and
                enemy.y < self.player.y + self.player.height and
                enemy.y + enemy.height > self.player.y):
                self.game_over = True
                self.create_explosion(self.player.x + self.player.width // 2, self.player.y + self.player.height // 2)
                self.player = PlayerShip(SCREEN_WIDTH // 2 - 25, SCREEN_HEIGHT - 60)
                self.score = 0
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE and not self.game_over:
                    self.spawn_bullet(self.player)
                elif event.key == pygame.K_ESCAPE:
                    self.running = False
    
    def handle_continuous_input(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.player.apply_thrust(True)
        else:
            self.player.apply_thrust(False)
        
        if keys[pygame.K_LEFT]:
            self.player.velocity = -self.player.speed
        elif keys[pygame.K_RIGHT]:
            self.player.velocity = self.player.speed
        else:
            self.player.velocity = 0
    
    def update(self):
        if self.game_over:
            return
        
        self.player.update()
        self.handle_continuous_input()
        
        self.enemy_spawn_timer += 1
        if self.enemy_spawn_timer >= self.enemy_spawn_interval:
            self.spawn_enemy()
            self.enemy_spawn_timer = 0
        
        for enemy in self.enemies[:]:
            enemy.update()
        
        for bullet in self.bullets[:]:
            if not bullet.update():
                self.bullets.remove(bullet)
        
        for particle in self.particles[:]:
            if not particle.update():
                self.particles.remove(particle)
        
        self.check_collisions()
    
    def draw(self):
        screen.fill(BLACK)
        
        # Draw player
        self.player.draw(screen)
        
        # Draw enemies
        for enemy in self.enemies:
            enemy.draw(screen)
        
        # Draw bullets
        for bullet in self.bullets:
            bullet.draw(screen)
        
        # Draw particles
        for particle in self.particles:
            particle.draw(screen)
        
        # Draw score
        score_text = self.font.render(f"Score: {self.score}", True, WHITE)
        screen.blit(score_text, (10, 10))
        
        # Draw game over screen
        if self.game_over:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            overlay.fill(BLACK)
            overlay.set_alpha(128)
            screen.blit(overlay, (0, 0))
            game_over_text = self.font.render("GAME OVER", True, RED)
            score_text = self.font.render(f"Final Score: {self.score}", True, WHITE)
            restart_text = self.font.render("Press SPACE to restart", True, WHITE)
            screen.blit(game_over_text, (SCREEN_WIDTH//2 - game_over_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
            screen.blit(score_text, (SCREEN_WIDTH//2 - score_text.get_width()//2, SCREEN_HEIGHT//2 + 10))
            screen.blit(restart_text, (SCREEN_WIDTH//2 - restart_text.get_width()//2, SCREEN_HEIGHT//2 + 50))
        
        pygame.display.flip()
    
    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            clock.tick(60)
        
        pygame.quit()

if __name__ == "__main__":
    game = Game()
    game.run()