#!/usr/bin/env python3
"""
Quick Start Script
==================

MiniFab Integrated Training - 一鍵啟動指南
"""

import subprocess
import sys
import os
from pathlib import Path


def print_header(title):
    """打印標題"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def step_install_dependencies():
    """安裝依賴"""
    print_header("Step 1: Installing Dependencies")
    
    print("Installing required packages...")
    print("This may take 5-10 minutes. Please wait...\n")
    
    try:
        result = subprocess.run(
            [sys.executable, "setup_dependencies.py"],
            cwd=Path(__file__).parent,
            capture_output=False,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def step_verify_installation():
    """驗證安裝"""
    print_header("Step 2: Verifying Installation")
    
    modules_to_check = [
        ("numpy", "NumPy"),
        ("gymnasium", "Gymnasium"),
        ("pettingzoo", "PettingZoo"),
        ("simpy", "SimPy"),
        ("ray", "Ray"),
        ("minifab_decision_system", "Decision System"),
        ("minifab_es_trainer", "ES Trainer"),
        ("minifab_ray_trainer", "Ray Trainer"),
    ]
    
    all_ok = True
    for module, name in modules_to_check:
        try:
            __import__(module)
            print(f"✅ {name}")
        except ImportError:
            print(f"❌ {name}")
            all_ok = False
    
    return all_ok


def step_quick_test():
    """快速測試"""
    print_header("Step 3: Running Quick Test (2 generations)")
    
    print("Starting training with minimal settings...")
    print("This will take ~5 minutes.\n")
    
    try:
        result = subprocess.run(
            [
                sys.executable,
                "integrated_training.py",
                "--generations", "2",
                "--ray-actors", "2",
                "--episodes-per-gen", "1",
                "--output-dir", "./test_results",
            ],
            cwd=Path(__file__).parent,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def step_check_results():
    """檢查結果"""
    print_header("Step 4: Checking Results")
    
    results_dir = Path(__file__).parent / "test_results"
    
    if results_dir.exists():
        files = list(results_dir.glob("*"))
        print(f"✅ Results saved in: {results_dir}\n")
        print("Generated files:")
        for f in files:
            size = f.stat().st_size if f.is_file() else "DIR"
            print(f"  - {f.name} ({size})")
        return True
    else:
        print("❌ Results directory not found")
        return False


def step_full_training():
    """完整訓練"""
    print_header("Step 5: Ready for Full Training!")
    
    print("""
Now you're ready to run the complete training!

For full training (10 generations, ~2 hours):
    
    python integrated_training.py \\
        --generations 10 \\
        --episodes-per-gen 3 \\
        --population-size 20 \\
        --ray-actors 4

For custom training:
    
    python integrated_training.py --help

For more information:
    
    - Read TRAINING_GUIDE.md
    - Check QUICK_REFERENCE.py
    - Run INTEGRATION_EXAMPLES.py
    """)


def print_summary():
    """打印總結"""
    print_header("Installation Summary")
    
    print("""
✅ 所有系統已安裝完成!

📊 已安裝的組件:
  
  1️⃣  Ray 分散式訓練 (4x並行加速)
  2️⃣  事件驅動決策系統 (12維特徵自動提取)
  3️⃣  演化策略 (ES - 同儕比較無需標準答案)
  4️⃣  完整訓練引擎 (檢查點、報告、監控)

📁 生成的文件:
  
  - ./test_results/          快速測試結果
  - ./training_results/      (完整訓練時自動創建)

📚 推薦閱讀:
  
  1. IMPLEMENTATION_SUMMARY.md   (實現總結)
  2. TRAINING_GUIDE.md           (完整指南)
  3. QUICK_REFERENCE.py          (快速參考)

🚀 快速命令:
  
  # 再次運行快速測試
  python integrated_training.py --generations 2 --ray-actors 2
  
  # 完整訓練
  python integrated_training.py --generations 10
  
  # 查看幫助
  python integrated_training.py --help

💡 下一步:
  
  1. 根據硬體配置調整參數 (見 TRAINING_GUIDE.md)
  2. 自定義特徵或策略 (見 INTEGRATION_EXAMPLES.py)
  3. 監控訓練進度 (查看 ./training_results/)
    """)


def main():
    """主函數"""
    print_header("MiniFab Integrated Training - Quick Start")
    
    print("""
This script will guide you through:
  
  1. Installing dependencies (5-10 min)
  2. Verifying installation
  3. Running quick test (5 min)
  4. Checking results
  5. Preparing for full training
  
Let's get started! 🚀
    """)
    
    input("Press Enter to begin...")
    
    # 步驟1: 安裝依賴
    if not step_install_dependencies():
        print("\n❌ Installation failed. Please try manual installation:")
        print("  pip install ray[tune] gymnasium pettingzoo simpy numpy pandas")
        return False
    
    # 步驟2: 驗證安裝
    if not step_verify_installation():
        print("\n❌ Verification failed. Some modules are missing.")
        return False
    
    # 步驟3: 快速測試
    print("\n繼續快速測試? (y/n): ", end="")
    if input().lower() != 'y':
        print("跳過快速測試")
    else:
        if not step_quick_test():
            print("\n⚠️ Quick test failed, but installation may still be OK")
        else:
            step_check_results()
    
    # 步驟4: 完整訓練準備
    step_full_training()
    
    # 總結
    print_summary()
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
