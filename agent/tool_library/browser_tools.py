"""Local browser automation tools using PySide6 WebEngine."""

import inspect
import os
import time
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, Qt, QUrl
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage

def _ensure_app():
    """Ensure a QApplication instance exists (usually true in GUI, but needed in headless/tests)."""
    app = QApplication.instance()
    if app is None:
        import sys
        # Needed for WebEngine to work headless if no GUI is present
        sys.argv.append("--no-sandbox")
        app = QApplication(sys.argv)
    return app

_active_page = None

def _get_active_page():
    global _active_page
    _ensure_app()
    if _active_page is None:
        _active_page = QWebEnginePage()
    return _active_page

def navigate_and_interact(url: str, action: str = "goto", selector: str = "", text: str = "") -> str:
    """
    Navigate to a URL and perform an action using a local headless WebEngine.
    Maintains a persistent session across calls.
    
    Args:
        url: The URL to load.
        action: 'goto', 'click', or 'fill'.
        selector: CSS selector for 'click' or 'fill'.
        text: Text to input for 'fill' action.
        
    Returns:
        The innerText of the webpage after the action is completed.
    """
    page = _get_active_page()
    loop = QEventLoop()
    
    if action == "goto":
        page.loadFinished.connect(loop.quit)
        page.load(QUrl(url))
        
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(10000)
        
        loop.exec()
        timer.stop()
        
        try:
            page.loadFinished.disconnect(loop.quit)
        except Exception:
            pass

    # Define a helper to run JS and get the result synchronously
    def run_js_sync(script: str) -> any:
        js_loop = QEventLoop()
        result = [None]
        def callback(val):
            result[0] = val
            js_loop.quit()
            
        page.runJavaScript(script, callback)
        
        js_timer = QTimer()
        js_timer.setSingleShot(True)
        js_timer.timeout.connect(js_loop.quit)
        js_timer.start(5000)
        
        js_loop.exec()
        js_timer.stop()
        return result[0]

    # Perform action
    if action == "click" and selector:
        script = f"document.querySelector('{selector}').click();"
        run_js_sync(script)
        # Brief pause to allow any JS side-effects to settle
        time.sleep(0.5)
        QApplication.processEvents()
        
    elif action == "fill" and selector and text:
        # Escape quotes in text
        safe_text = text.replace("'", "\\'").replace('"', '\\"')
        script = f"document.querySelector('{selector}').value = '{safe_text}';"
        run_js_sync(script)
        
    # Get final text content
    extract_script = "document.body.innerText;"
    content = run_js_sync(extract_script)
    
    if content is None:
        return "❌ Error: Could not extract text from the page. It may not have loaded correctly."
        
    return str(content)


def take_screenshot(url: str, output_name: str = "screenshot.png") -> str:
    """
    Takes a screenshot of a webpage.
    
    Args:
        url: The URL to capture.
        output_name: The filename to save the screenshot as (default: screenshot.png).
        
    Returns:
        The absolute path to the saved screenshot file.
    """
    _ensure_app()
    
    page = QWebEnginePage()
    loop = QEventLoop()
    
    page.loadFinished.connect(loop.quit)
    page.load(QUrl(url))
    
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(15000)
    
    loop.exec()
    timer.stop()
    
    # Give it a second to render
    time.sleep(1)
    QApplication.processEvents()

    # Wait until rendering is actually done (we can't perfectly know, but we try)
    # The safest way in WebEngine is to use a QImage and render to it.
    size = page.contentsSize()
    if size.isEmpty():
        size = page.viewportSize()
        if size.isEmpty():
            size = page.geometry().size()
            
    if size.isEmpty():
        page.deleteLater()
        return "❌ Error: Page size is empty, cannot take screenshot."
        
    img = QImage(size.toSize(), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    
    painter = QPainter(img)
    page.view().render(painter)
    painter.end()
    
    # Save to workspace
    from agent import workspace_paths
    output_dir = os.path.join(workspace_paths.get_root(), "Agent-Data", "screenshots")
    os.makedirs(output_dir, exist_ok=True)
    
    file_path = os.path.join(output_dir, output_name)
    success = img.save(file_path)
    
    page.deleteLater()
    
    if success:
        return f"Screenshot saved successfully to {file_path}"
    else:
        return "❌ Error: Failed to save screenshot image."

BROWSER_TOOLS = {
    "navigate_and_interact": {
        "func": navigate_and_interact,
        "description": inspect.getdoc(navigate_and_interact)
    },
    "take_screenshot": {
        "func": take_screenshot,
        "description": inspect.getdoc(take_screenshot)
    }
}
