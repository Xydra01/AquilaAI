import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tool_library import email_tools

@patch('tool_library.email_tools.smtplib.SMTP')
def test_email_sender_success(mock_smtp):
    """TDD Goal: Ensure the EmailSender class correctly formats and dispatches emails via SMTP."""
    mock_server = MagicMock()
    mock_smtp.return_value = mock_server
    mock_server.__enter__.return_value = mock_server
    
    sender = email_tools.EmailSender(
        smtp_server="smtp.test.com", 
        smtp_port=587, 
        from_email="bot@test.com", 
        smtp_password="password",
        use_tls=True
    )
    
    success = sender.send_email(
        recipients=["human@test.com"],
        subject="Test Subject",
        plain_body="Hello world."
    )
    
    assert success is True
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_with("bot@test.com", "password")
    mock_server.send_message.assert_called_once()