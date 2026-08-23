"""
Test collision detection.
"""
import pytest
from unittest.mock import patch, MagicMock

class TestCollision:
    def test_ship_bullet_collision(self):
        """Ship should detect bullet collisions."""
        from galaga.ship import Ship
        with patch("pygame.display.set_mode") as mock_setmode:
            screen = MagicMock()
            mock_setmode.return_value = screen
            ship = Ship(screen)
            assert hasattr(ship, 'collide_with')