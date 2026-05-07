"""
Installation and Setup Guide for Distributed MiniFab Training
==============================================================

This guide covers installing dependencies and running the integrated training system.
"""

import subprocess
import sys
from pathlib import Path


def install_dependencies():
    """安裝所有必要的依賴"""
    
    packages = [
        # 核心依賴
        "numpy>=1.21.0",
        "pandas>=1.3.0",
        "scipy>=1.7.0",
        
        # RL框架
        "gymnasium>=0.26.0",
        "pettingzoo>=1.26.0",
        "simpy>=4.0.0",
        
        # 分散式訓練
        "ray[tune]>=2.0.0",
        "ray[rllib]>=2.0.0",
        
        # 可視化
        "matplotlib>=3.4.0",
        "tensorboard>=2.8.0",
    ]
    
    print("Installing dependencies...")
    for package in packages:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package]
            )
            print(f"✓ Installed {package}")
        except subprocess.CalledProcessError:
            print(f"✗ Failed to install {package}")
            return False
    
    return True


def verify_installation():
    """驗證安裝"""
    
    modules = [
        "numpy",
        "pandas",
        "gymnasium",
        "pettingzoo",
        "simpy",
        "ray",
    ]
    
    print("\nVerifying installation...")
    all_ok = True
    
    for module in modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except ImportError:
            print(f"✗ {module}")
            all_ok = False
    
    return all_ok


if __name__ == "__main__":
    if install_dependencies():
        if verify_installation():
            print("\n✓ All dependencies installed successfully!")
        else:
            print("\n✗ Some modules failed to import")
            sys.exit(1)
    else:
        print("\n✗ Installation failed")
        sys.exit(1)
