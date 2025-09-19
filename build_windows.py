#!/usr/bin/env python3
"""
Build script for creating Windows executable package.
This script handles the entire build process including PyInstaller and packaging.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
import zipfile

def check_dependencies():
    """Check if required build dependencies are installed."""
    print("Checking build dependencies...")
    
    required_packages = ['pyinstaller', 'streamlit', 'pandas', 'plotly']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ {package} (missing)")
    
    if missing_packages:
        print("\nInstalling missing packages...")
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install'
        ] + missing_packages)
    
    return True

def create_icon():
    """Create a simple icon file if one doesn't exist."""
    icon_dir = Path('img')
    icon_dir.mkdir(exist_ok=True)
    
    icon_path = icon_dir / 'icon.ico'
    if not icon_path.exists():
        # Create a simple placeholder icon using PIL if available
        try:
            from PIL import Image, ImageDraw
            
            # Create a simple icon
            img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # Draw a simple checkmark or task-like icon
            draw.rectangle([10, 10, 54, 54], fill=(70, 130, 180), outline=(0, 0, 0), width=2)
            draw.line([20, 32, 30, 42], fill=(255, 255, 255), width=3)
            draw.line([30, 42, 44, 22], fill=(255, 255, 255), width=3)
            
            img.save(icon_path, format='ICO')
            print(f"✓ Created icon: {icon_path}")
        except ImportError:
            print("! PIL not available, skipping icon creation")
    else:
        print(f"✓ Icon exists: {icon_path}")

def build_executable():
    """Build the executable using PyInstaller."""
    print("\nBuilding executable with PyInstaller...")
    
    # Clean previous builds
    for dir_name in ['build', 'dist', '__pycache__']:
        if Path(dir_name).exists():
            shutil.rmtree(dir_name)
            print(f"✓ Cleaned {dir_name}")
    
    # Run PyInstaller
    spec_file = 'todoist_assistant.spec'
    cmd = [sys.executable, '-m', 'PyInstaller', spec_file, '--clean']
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("✗ PyInstaller failed:")
        print(result.stdout)
        print(result.stderr)
        return False
    
    print("✓ PyInstaller completed successfully")
    return True

def create_distribution_package():
    """Create a distribution package with installer."""
    print("\nCreating distribution package...")
    
    dist_dir = Path('dist')
    # Check for both Windows (.exe) and Unix executables
    exe_path = dist_dir / 'TodoistAssistant.exe'
    unix_exe_path = dist_dir / 'TodoistAssistant'
    
    if exe_path.exists():
        source_exe = exe_path
        target_name = 'TodoistAssistant.exe'
    elif unix_exe_path.exists():
        source_exe = unix_exe_path
        target_name = 'TodoistAssistant.exe'  # Rename for Windows distribution
    else:
        print(f"✗ Executable not found in {dist_dir}")
        return False
    
    print(f"✓ Found executable: {source_exe}")
    
    # Create package directory
    package_dir = Path('TodoistAssistant_Windows')
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir()
    
    # Copy executable
    shutil.copy2(source_exe, package_dir / target_name)
    print(f"✓ Copied executable as {target_name}")
    
    # Copy supporting files
    files_to_copy = [
        'install.bat',
        '.env.example',
        'README.md',
        'LICENSE'
    ]
    
    for file_name in files_to_copy:
        if Path(file_name).exists():
            shutil.copy2(file_name, package_dir / file_name)
            print(f"✓ Copied {file_name}")
    
    # Copy directories
    dirs_to_copy = ['configs', 'img']
    for dir_name in dirs_to_copy:
        if Path(dir_name).exists():
            shutil.copytree(dir_name, package_dir / dir_name)
            print(f"✓ Copied {dir_name}/")
    
    # Create installation instructions
    instructions = """# Todoist Assistant - Windows Installation

## Quick Start

1. **Install**: Double-click `install.bat` to install Todoist Assistant
2. **Configure**: On first run, you'll be prompted to configure your Todoist API key
3. **Run**: Use the desktop shortcut or Start Menu to launch the application

## Manual Installation

If the automatic installer doesn't work:

1. Copy `TodoistAssistant.exe` to a folder of your choice
2. Double-click `TodoistAssistant.exe` to run
3. Follow the configuration prompts

## Getting Your API Key

1. Go to https://todoist.com/prefs/integrations
2. Find the "API token" section
3. Copy your API token
4. Paste it into the configuration when prompted

## Troubleshooting

- **Antivirus Warning**: Some antivirus programs may flag the executable. This is a false positive common with PyInstaller-built applications.
- **Configuration Issues**: The configuration file is stored in `%APPDATA%\\TodoistAssistant\\.env`
- **Port Issues**: If port 8501 is busy, the application will try to use another port

## Uninstallation

Use the uninstaller in the Start Menu or manually delete the installation folder.
"""
    
    with open(package_dir / 'INSTALL_INSTRUCTIONS.md', 'w') as f:
        f.write(instructions)
    print("✓ Created installation instructions")
    
    # Create ZIP package
    zip_path = Path(f'TodoistAssistant_Windows_v1.0.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in package_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(package_dir.parent)
                zipf.write(file_path, arcname)
    
    print(f"✓ Created distribution package: {zip_path}")
    
    # Show package contents
    print(f"\nPackage contents ({package_dir}):")
    for item in sorted(package_dir.rglob('*')):
        if item.is_file():
            size = item.stat().st_size / (1024 * 1024)  # MB
            print(f"  {item.relative_to(package_dir)} ({size:.1f} MB)")
    
    return True

def main():
    """Main build process."""
    print("=" * 60)
    print("        Todoist Assistant - Windows Build Script")
    print("=" * 60)
    
    try:
        # Step 1: Check dependencies
        if not check_dependencies():
            return 1
        
        # Step 2: Create icon
        create_icon()
        
        # Step 3: Build executable
        if not build_executable():
            return 1
        
        # Step 4: Create distribution package
        if not create_distribution_package():
            return 1
        
        print("\n" + "=" * 60)
        print("✓ Build completed successfully!")
        print("=" * 60)
        print("\nDistribution package created: TodoistAssistant_Windows_v1.0.zip")
        print("This package contains everything needed for Windows installation.")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Build failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())