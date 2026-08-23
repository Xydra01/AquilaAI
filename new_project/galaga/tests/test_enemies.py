"""
Test enemy spawning and movement.
"""
import pytest
from unittest.mock import patch, MagicMock

class TestEnemy:
    def test_enemy_initial_position(self):
        """Enemies should spawn at top of screen."""
        from galaga.enemy import Enemy
        with patch("pygame.display.set_mode") as mock_setmode:
            screen = MagicMock()
            mock_setmode.return_value = screen
            enemy = Enemy(screen)
            assert enemy.rect.y == 0