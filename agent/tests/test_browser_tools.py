import os
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage

from tool_library.browser_tools import navigate_and_interact

# Ensure QApplication is initialized (handled by conftest or implicitly if pytest-qt is used)
def test_browser_navigate_goto(qtbot):
    # Use a safe internal or fast-loading URL, like about:blank or a small data URI
    url = "data:text/html,<html><body><h1>Hello WebEngine</h1></body></html>"
    
    # We expect this to run synchronously in the test thanks to our threading implementation
    result = navigate_and_interact(url=url, action="goto")
    
    assert "Hello WebEngine" in result
    
def test_browser_navigate_click(qtbot):
    html = '''
    <html><body>
    <button id="btn" onclick="document.body.innerText='Clicked'">Wait</button>
    </body></html>
    '''
    url = f"data:text/html,{html}"
    
    navigate_and_interact(url=url, action="goto")
    result = navigate_and_interact(url=url, action="click", selector="#btn")
    assert "Clicked" in result

def test_browser_navigate_fill(qtbot):
    html = '''
    <html><body>
    <input id="inp" type="text" value="">
    <button id="btn" onclick="document.body.innerText=document.getElementById('inp').value">Submit</button>
    </body></html>
    '''
    url = f"data:text/html,{html}"
    
    navigate_and_interact(url=url, action="goto")
    # First fill
    navigate_and_interact(url=url, action="fill", selector="#inp", text="FilledText")
    # Then click to test the value was set
    result = navigate_and_interact(url=url, action="click", selector="#btn")
    
    assert "FilledText" in result
