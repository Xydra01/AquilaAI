import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import Agent

@patch('main.client.chat')
def test_agent_run_chat_streaming_and_vision(mock_chat):
    """TDD Goal: Ensure run_chat streams correctly and passes image payloads to the model."""
    
    # 1. Mock generator returning two distinct chunks
    def mock_generator():
        yield {"message": {"content": "I see "}}
        yield {"message": {"content": "an image."}}
    mock_chat.return_value = mock_generator()
    
    agent = Agent()
    
    # 2. Call run_chat with stream=True and an image
    generator = agent.run_chat(
        user_input="Look at this",
        chat_history=[],
        image_payloads=["data:image/jpeg;base64,fake_b64_string"],
        stream=True
    )
    
    # 3. Verify generator yields chunks sequentially (Fixes the "Dictionary Output" bug)
    chunks = list(generator)
    assert len(chunks) == 2
    assert chunks[0]["message"]["content"] == "I see "
    assert chunks[1]["message"]["content"] == "an image."
    
    # 4. Verify the client received the cleaned image and stream flag!
    args, kwargs = mock_chat.call_args
    messages_sent = args[0]
    
    assert kwargs["stream"] is True
    
    # Verify the OS formatted the image for the OpenAI /v1 endpoint
    last_msg_content = messages_sent[-1]["content"]
    assert isinstance(last_msg_content, list)
    assert last_msg_content[0] == {"type": "text", "text": "Look at this"}
    assert last_msg_content[1]["type"] == "image_url"
    assert last_msg_content[1]["image_url"]["url"] == "data:image/jpeg;base64,fake_b64_string"