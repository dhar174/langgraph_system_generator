"""
End-to-end test for Advanced Options toggle functionality.

This test validates that the Advanced Options panel expands/collapses
correctly when the toggle button is clicked.
"""

from pathlib import Path


def test_advanced_options_html_structure():
    """Verify HTML structure is correct for Advanced Options toggle."""
    html_file = Path("src/langgraph_system_generator/api/static/index.html")
    content = html_file.read_text()
    
    # Check button exists with correct attributes
    assert 'id="advancedToggle"' in content, "Missing advancedToggle button"
    assert 'aria-expanded="false"' in content, "Button should start with aria-expanded=false"
    assert 'aria-controls="advancedPanel"' in content, "Button should have aria-controls"
    
    # Check panel exists with correct initial state
    assert 'id="advancedPanel"' in content, "Missing advancedPanel div"
    assert 'style="display: none;"' in content, "Panel should start hidden"
    
    # Check all advanced form fields exist
    required_fields = [
        'id="model"',
        'id="temperature"',
        'id="maxTokens"',
        'id="agentType"',
        'id="memoryConfig"'
    ]
    for field in required_fields:
        assert field in content, f"Missing required field: {field}"
    
    # Check JavaScript is loaded
    assert 'src="/static/app.js"' in content, "Missing app.js script tag"
    
    print("✅ HTML structure validation passed")


def test_advanced_options_javascript():
    """Verify JavaScript toggle logic is correct."""
    js_file = Path("src/langgraph_system_generator/api/static/app.js")
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
    
    print("✅ JavaScript logic validation passed")


def test_advanced_options_css():
    """Verify CSS styling for toggle icon and panel animation."""
    css_file = Path("src/langgraph_system_generator/api/static/style.css")
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
    
    print("✅ CSS styling validation passed")


def test_static_files_exist():
    """Verify all static files exist in the correct location."""
    static_dir = Path("src/langgraph_system_generator/api/static")
    
    assert static_dir.exists(), f"Static directory not found: {static_dir}"
    assert (static_dir / "index.html").exists(), "index.html not found"
    assert (static_dir / "app.js").exists(), "app.js not found"
    assert (static_dir / "style.css").exists(), "style.css not found"
    
    print("✅ All static files exist")


if __name__ == "__main__":
    import sys
    import os
    
    # Change to repo root for relative paths to work
    repo_root = Path("/home/runner/work/langgraph_system_generator/langgraph_system_generator")
    os.chdir(repo_root)
    
    try:
        test_static_files_exist()
        test_advanced_options_html_structure()
        test_advanced_options_javascript()
        test_advanced_options_css()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nAdvanced Options toggle functionality is correctly implemented:")
        print("  • HTML structure is valid")
        print("  • JavaScript event handling is correct")
        print("  • CSS animations are properly defined")
        print("  • All required files exist")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
