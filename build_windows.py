#!/usr/bin/env python3
"""Build script for creating Windows executable package.

This module handles the entire build process including PyInstaller compilation
and distribution package creation for Windows deployment.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Final

# Build configuration constants
ICON_SIZE: Final[tuple[int, int]] = (64, 64)
ICON_COLORS: Final[dict[str, tuple[int, int, int]]] = {
    'background': (70, 130, 180),
    'border': (0, 0, 0),
    'checkmark': (255, 255, 255),
}
PACKAGE_VERSION: Final[str] = '1.0'
REQUIRED_BUILD_PACKAGES: Final[list[str]] = ['pyinstaller', 'PIL']


def check_dependencies() -> bool:
    """Verify that required build dependencies are installed.
    
    Returns:
        True if all dependencies are available, False otherwise.
    """
    print("Checking build dependencies...")
    
    missing_packages: list[str] = []
    
    for package in REQUIRED_BUILD_PACKAGES:
        try:
            __import__(package)
            print(f"✓ {package}")
        except ImportError:
            package_name = 'pillow' if package == 'PIL' else package
            missing_packages.append(package_name)
            print(f"✗ {package} (missing)")
    
    if missing_packages:
        print("\nMissing packages detected.")
        print("Please install build dependencies with:")
        print("  uv pip install --extra build .")
        return False
    
    return True


def create_icon(icon_dir: Path = Path('img')) -> None:
    """Create application icon if it doesn't exist.
    
    Args:
        icon_dir: Directory where the icon should be created.
    """
    from PIL import Image, ImageDraw
    
    icon_dir.mkdir(exist_ok=True)
    icon_path = icon_dir / 'icon.ico'
    
    if icon_path.exists():
        print(f"✓ Icon exists: {icon_path}")
        return
    
    # Create icon with checkmark design
    img = Image.new('RGBA', ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw task checkbox
    draw.rectangle(
        [10, 10, 54, 54],
        fill=ICON_COLORS['background'],
        outline=ICON_COLORS['border'],
        width=2
    )
    
    # Draw checkmark
    draw.line([20, 32, 30, 42], fill=ICON_COLORS['checkmark'], width=3)
    draw.line([30, 42, 44, 22], fill=ICON_COLORS['checkmark'], width=3)
    
    img.save(icon_path, format='ICO')
    print(f"✓ Created icon: {icon_path}")


def clean_build_directories() -> None:
    """Remove previous build artifacts."""
    build_dirs = ['build', 'dist', '__pycache__']
    
    for dir_name in build_dirs:
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"✓ Cleaned {dir_name}")


def build_executable(spec_file: str = 'todoist_assistant.spec') -> bool:
    """Build the executable using PyInstaller.
    
    Args:
        spec_file: Path to the PyInstaller specification file.
        
    Returns:
        True if build succeeded, False otherwise.
    """
    print("\nBuilding executable with PyInstaller...")
    clean_build_directories()
    
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


def find_executable() -> Path | None:
    """Locate the built executable in the dist directory.
    
    Returns:
        Path to the executable if found, None otherwise.
    """
    dist_dir = Path('dist')
    
    for exe_name in ['TodoistAssistant.exe', 'TodoistAssistant']:
        exe_path = dist_dir / exe_name
        if exe_path.exists():
            return exe_path
    
    return None


def copy_support_files(package_dir: Path) -> None:
    """Copy supporting files to the distribution package.
    
    Args:
        package_dir: Target directory for the package files.
    """
    # Copy individual files
    files_to_copy = ['install.bat', '.env.example', 'README.md', 'LICENSE']
    for file_name in files_to_copy:
        file_path = Path(file_name)
        if file_path.exists():
            shutil.copy2(file_path, package_dir / file_name)
            print(f"✓ Copied {file_name}")
    
    # Copy directories
    for dir_name in ['configs', 'img']:
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.copytree(dir_path, package_dir / dir_name)
            print(f"✓ Copied {dir_name}/")


def create_installation_instructions(package_dir: Path) -> None:
    """Generate installation instructions for the package.
    
    Args:
        package_dir: Directory where instructions should be created.
    """
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
    
    with open(package_dir / 'INSTALL_INSTRUCTIONS.md', 'w', encoding='utf-8') as f:
        f.write(instructions)
    print("✓ Created installation instructions")


def create_distribution_package() -> bool:
    """Create the complete distribution package with installer.
    
    Returns:
        True if package creation succeeded, False otherwise.
    """
    print("\nCreating distribution package...")
    
    # Find executable
    source_exe = find_executable()
    if source_exe is None:
        print("✗ Executable not found in dist/")
        return False
    
    print(f"✓ Found executable: {source_exe}")
    
    # Create package directory
    package_dir = Path('TodoistAssistant_Windows')
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir()
    
    # Copy executable
    target_exe = package_dir / 'TodoistAssistant.exe'
    shutil.copy2(source_exe, target_exe)
    print(f"✓ Copied executable as {target_exe.name}")
    
    # Copy supporting files and create instructions
    copy_support_files(package_dir)
    create_installation_instructions(package_dir)
    
    # Create ZIP archive
    zip_path = Path(f'TodoistAssistant_Windows_v{PACKAGE_VERSION}.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in package_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(package_dir.parent)
                zipf.write(file_path, arcname)
    
    print(f"✓ Created distribution package: {zip_path}")
    
    # Display package contents
    print(f"\nPackage contents ({package_dir}):")
    for item in sorted(package_dir.rglob('*')):
        if item.is_file():
            size_mb = item.stat().st_size / (1024 * 1024)
            print(f"  {item.relative_to(package_dir)} ({size_mb:.1f} MB)")
    
    return True


def main() -> int:
    """Execute the build process.
    
    Returns:
        Exit code (0 for success, 1 for failure).
    """
    print("=" * 60)
    print("        Todoist Assistant - Windows Build Script")
    print("=" * 60)
    
    try:
        # Verify dependencies
        if not check_dependencies():
            return 1
        
        # Create icon
        create_icon()
        
        # Build executable
        if not build_executable():
            return 1
        
        # Create distribution package
        if not create_distribution_package():
            return 1
        
        print("\n" + "=" * 60)
        print("✓ Build completed successfully!")
        print("=" * 60)
        print(f"\nDistribution package created: TodoistAssistant_Windows_v{PACKAGE_VERSION}.zip")
        print("This package contains everything needed for Windows installation.")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n✗ Build cancelled by user")
        return 130
    except Exception as e:
        print(f"\n✗ Build failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())