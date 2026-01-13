"""
Static file validation for Advanced Options toggle structure and behavior.

This module verifies that the HTML, JavaScript, and CSS for the Advanced
Options panel are defined correctly, and that all required static files exist.

Note: These tests validate the static file structure but do not test runtime
behavior. For true end-to-end testing of the toggle functionality, consider
using browser automation tools like Selenium or Playwright to verify that
clicking the button actually changes panel visibility at runtime.
"""

from pathlib import Path

from bs4 import BeautifulSoup


def test_advanced_options_html_structure():
    """Verify HTML structure is correct for Advanced Options toggle."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    html_file = repo_root / "src/langgraph_system_generator/api/static/index.html"
    content = html_file.read_text()
    soup = BeautifulSoup(content, "html.parser")
    
    # Check button exists with correct attributes
    button = soup.find(id="advancedToggle")
    assert button is not None, "Missing advancedToggle button"
    assert button.get("aria-expanded") == "false", \
        "Button should start with aria-expanded=false"
    assert button.get("aria-controls") == "advancedPanel", \
        "Button should have aria-controls set to advancedPanel"
    
    # Check panel exists with correct initial state
    panel = soup.find(id="advancedPanel")
    assert panel is not None, "Missing advancedPanel element"
    style_attr = panel.get("style") or ""
    assert "display:none" in style_attr.replace(" ", "") or "display: none" in style_attr, \
        "Panel should start hidden with display: none"
    
    # Check all advanced form fields exist
    required_fields = [
        "model", "customEndpoint", "preset", "temperature", "maxTokens", 
        "agentType", "memoryConfig", "graphStyle", "retrieverType", "documentLoader"
    ]
    for field_id in required_fields:
        field = soup.find(id=field_id)
        assert field is not None, f"Missing required field with id={field_id}"
    
    # Check custom endpoint group starts hidden
    custom_group = soup.find(id="customEndpointGroup")
    assert custom_group is not None, "Missing customEndpointGroup"
    style_attr = custom_group.get("style") or ""
    assert "display:none" in style_attr.replace(" ", "") or "display: none" in style_attr, \
        "Custom endpoint group should start hidden"
    
    # Check model select has optgroups for organization
    model_select = soup.find(id="model")
    optgroups = model_select.find_all("optgroup")
    assert len(optgroups) > 0, "Model select should have optgroups for organization"
    
    # Verify key optgroups exist
    optgroup_labels = [og.get("label") for og in optgroups]
    assert "OpenAI" in optgroup_labels, "Missing OpenAI optgroup"
    assert "Anthropic Claude" in optgroup_labels, "Missing Anthropic Claude optgroup"
    assert "Google Gemini" in optgroup_labels, "Missing Google Gemini optgroup"
    
    # Check JavaScript is loaded
    scripts = soup.find_all("script")
    has_app_script = any(
        tag.get("src") == "/static/app.js" for tag in scripts
    )
    assert has_app_script, "Missing app.js script tag"


def test_advanced_options_javascript():
    """Verify JavaScript toggle logic is correct.
    
    Note: This test uses string matching to validate JavaScript structure.
    For more robust validation, consider using a JavaScript parser like
    esprima to validate the AST structure.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    js_file = repo_root / "src/langgraph_system_generator/api/static/app.js"
    content = js_file.read_text()
    
    # Check event listener exists
    assert "advancedToggle.addEventListener('click'" in content, \
        "Missing click event listener for advancedToggle"
    
    # Check toggle logic
    assert "getAttribute('aria-expanded')" in content, \
        "Missing check for aria-expanded attribute"
    assert "advancedPanel.style.display = 'block'" in content, \
        "Missing logic to show panel"
    assert "advancedPanel.style.display = 'none'" in content, \
        "Missing logic to hide panel"
    assert "setAttribute('aria-expanded', 'true')" in content, \
        "Missing logic to set aria-expanded to true"
    assert "setAttribute('aria-expanded', 'false')" in content, \
        "Missing logic to set aria-expanded to false"
    
    # Check model change event listener for custom endpoint
    assert "modelSelect.addEventListener('change'" in content, \
        "Missing change event listener for model select"
    assert "customEndpointGroup.style.display" in content, \
        "Missing logic to show/hide custom endpoint group"


def test_advanced_options_css():
    """Verify CSS styling for toggle icon and panel animation."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    css_file = repo_root / "src/langgraph_system_generator/api/static/style.css"
    content = css_file.read_text()
    
    # Check toggle icon rotation
    assert ".toggle-icon" in content, "Missing .toggle-icon class"
    assert '.advanced-toggle[aria-expanded="true"] .toggle-icon' in content, \
        "Missing CSS rule for icon rotation when expanded"
    assert "transform: rotate(90deg)" in content, \
        "Missing rotate transform for icon"
    
    # Check panel animation
    assert ".advanced-panel" in content, "Missing .advanced-panel class"
    assert "animation: slideDown" in content, \
        "Missing slideDown animation for panel"
    assert "@keyframes slideDown" in content, \
        "Missing slideDown keyframes definition"


def test_static_files_exist():
    """Verify all static files exist in the correct location."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    static_dir = repo_root / "src/langgraph_system_generator/api/static"
    
    assert static_dir.exists(), f"Static directory not found: {static_dir}"
    assert (static_dir / "index.html").exists(), "index.html not found"
    assert (static_dir / "app.js").exists(), "app.js not found"
    assert (static_dir / "style.css").exists(), "style.css not found"
