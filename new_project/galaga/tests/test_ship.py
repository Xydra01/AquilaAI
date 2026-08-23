"""
Test ship movement mechanics.
"""
import pytest
from unittest.mock import patch, MagicMock

class TestShip:
    def test_ship_initial_position(self):
        """Ship should start at bottom center."""
        from galaga.ship import Ship
        with patch("pygame.display.set_mode") as mock_setmode:
            screen = MagicMock()
            mock_setmode.return_value = screen
            ship = Ship(screen)
            assert ship.rect.centerx == screen.get_width() // 2