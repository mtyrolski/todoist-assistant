"""
Test the Chainlit application basic functionality.
"""

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def test_chainlit_imports():
    """Test that all necessary imports work."""
    try:
        import chainlit as cl
        from todoist.plots import current_tasks_types
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_app_structure():
    """Test that the app structure is correct."""
    app_path = Path(__file__).parent / "app.py"
    config_path = Path(__file__).parent / ".chainlit" / "config.toml"
    
    if not app_path.exists():
        print(f"❌ App file not found: {app_path}")
        return False
    
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        return False
    
    print("✅ App structure is correct")
    return True

def test_app_loading():
    """Test that the app can be loaded without errors."""
    try:
        # Import the app module
        from todoist.chainlit_app import app
        print("✅ App loaded successfully")
        return True
    except Exception as e:
        print(f"❌ Error loading app: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Chainlit Application")
    print("=" * 50)
    
    tests = [
        test_chainlit_imports,
        test_app_structure,
        test_app_loading,
    ]
    
    passed = 0
    for test in tests:
        print(f"\n🔍 Running {test.__name__}...")
        if test():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"📊 Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed! Chainlit app is ready to use.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please check the errors above.")
        sys.exit(1)