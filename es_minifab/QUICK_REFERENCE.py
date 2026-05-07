"""
Quick Reference Card
====================

MiniFab Integrated Training System - 快速參考
"""

# ============================================================
# 1. 快速開始
# ============================================================

"""
安裝依賴:
    python setup_dependencies.py

基本訓練:
    python integrated_training.py

自定義訓練 (10代, 3回合/代, 20種族, 4Actor):
    python integrated_training.py \
        --generations 10 \
        --episodes-per-gen 3 \
        --population-size 20 \
        --ray-actors 4

結果位置:
    ./training_results/
        ├── gen_0_checkpoint.json
        ├── gen_5_checkpoint.json
        ├── gen_10_checkpoint.json
        └── training_report.json
"""

# ============================================================
# 2. 核心模組速查
# ============================================================

MODULES = {
    "minifab_decision_system.py": {
        "主要類": [
            "EventType - 事件類型枚舉",
            "DecisionContext - 決策上下文",
            "FeatureVector - 12維特徵向量",
            "FeatureExtractor - 特徵提取器",
            "EventDrivenScheduler - 事件調度器",
        ],
        "用途": "事件驅動決策系統",
        "關鍵函數": "extract_lot_features(), trigger_decision()",
    },
    
    "minifab_es_trainer.py": {
        "主要類": [
            "PolicyIndividual - 策略個體",
            "PolicyNetwork - 神經網路",
            "EvolutionStrategies - ES訓練器",
        ],
        "用途": "演化策略訓練",
        "關鍵參數": {
            "population_size": "種族大小 (20)",
            "elite_size": "精英數量 (4)",
            "mutation_std": "突變標準差 (0.1)",
        },
    },
    
    "minifab_ray_trainer.py": {
        "主要類": [
            "MiniFabSimulatorActor - Ray Actor",
            "RayDistributedTrainer - 分散式訓練器",
            "DistributedPolicyOptimizer - 優化器",
        ],
        "用途": "Ray分散式訓練",
        "關鍵配置": "num_actors (4)",
    },
    
    "integrated_training.py": {
        "主要類": ["IntegratedTrainer - 整合訓練器"],
        "用途": "完整訓練流程",
        "入口": "python integrated_training.py",
    },
}

# ============================================================
# 3. 12維特徵速查
# ============================================================

FEATURES_12D = {
    "Machine (4)": {
        "1. utilization": "機台利用率 [0,1]",
        "2. setup_count": "換線次數 [0,∞]",
        "3. pending_lots": "待處理Lot數 [0,∞]",
        "4. idle_time": "閒置時間 [0,∞]",
    },
    "Queue (4)": {
        "5. length": "隊列長度 [0,∞]",
        "6. age_max": "最長等待時間 [0,∞]",
        "7. variety": "產品多樣性 [0,1]",
        "8. downstream_util": "下游Buffer利用率 [0,1]",
    },
    "Lot (4)": {
        "9. remaining_steps": "剩餘步驟 [0,6]",
        "10. wait_time": "等待時間 [0,∞]",
        "11. product_type": "產品類型 [0,1]",
        "12. batch_potential": "配批可能性 [0,1]",
    },
}

# ============================================================
# 4. 訓練流程速查
# ============================================================

TRAINING_FLOW = """
1️⃣ 初始化
   - 建立Ray集群 (4 Actor)
   - 初始化ES種族 (20策略)
   - 建立事件調度器

2️⃣ 代循環 (for each generation):
   
   a) 評估種族
      - 每個策略 vs 其他19個 (同儕比較)
      - 計算適應度 = 勝率 + 平均獎勵
      - 使用Ray並行評估 (4x加速)
   
   b) 分散式環境模擬
      - 最佳策略在Ray環境上評估
      - 4個Actor並行運行3回合
      - 聚合結果 (平均獎勵, Makespan等)
   
   c) 進化下一代
      - 精英保留 (前4個)
      - 其他由精英突變產生
      - 自適應變異率
   
   d) 保存檢查點 (每5代)
      - 種族快照
      - 訓練統計
      - 可恢復狀態

3️⃣ 最終報告
   - 最優個體信息
   - 適應度曲線
   - 配置詳情
"""

# ============================================================
# 5. 決策點流程速查
# ============================================================

DECISION_POINT_FLOW = """
當時間跳到決策點 (例如: 機台加工完畢):

1️⃣ 處理觸發事件
   └─ 機台狀態改為閒置
   └─ 完成的Lot進入下一工序

2️⃣ 特徵提取 (12維)
   ├─ 機台特徵 (4個)
   ├─ 隊列特徵 (4個)
   └─ Lot特徵 (4個)

3️⃣ 神經網路決策
   ├─ 輸入: 特徵向量 (12維)
   ├─ 隱層: 64神經元 + ReLU
   └─ 輸出: 動作概率分佈
   └─ 決策: argmax(概率)

4️⃣ 註冊未來事件 ⭐
   ├─ 查表取得加工時間
   ├─ 計算完成時刻 = 現在 + 加工時間
   ├─ 在事件隊列中註冊事件
   └─ 時間軸繼續快轉
"""

# ============================================================
# 6. ES同儕比較速查
# ============================================================

ES_PEER_COMPARISON = """
傳統方法 (標準答案):
Strategy 1 Score ──┐
                   ├─→ vs. Optimal Solution (Ground Truth)
Strategy 2 Score ──┘
問題: 工廠排程沒有「絕對最佳解」❌


ES同儕比較 (相對評估):
Strategy 1 ──┐
             ├─ vs Strategy 2 ┐
             │                ├─ vs 所有其他策略
             └─ vs Strategy 3 ┘

Fitness(Strategy 1) = (勝場數 / 總對戰數) × 100 + 平均獎勵

優點:
✓ 無需定義最優解
✓ 自適應於環境變化
✓ 自然選擇淘汰不適者
✓ 種族多樣性維持
"""

# ============================================================
# 7. Ray並行架構速查
# ============================================================

RAY_PARALLEL_SPEEDUP = """
序列執行 (Baseline):
Policy 1 → Policy 2 → ... → Policy 20
耗時: 20 × 3回合 = 60個環境步驟

4個Actor並行:
Actor1: P1  P5  P9  P13 P17
Actor2: P2  P6  P10 P14 P18
Actor3: P3  P7  P11 P15 P19
Actor4: P4  P8  P12 P16 P20
耗時: (20 × 3) / 4 = 15個環境步驟

加速倍數: 60 / 15 = 4x ✓
"""

# ============================================================
# 8. 常用命令速查
# ============================================================

COMMANDS = {
    "安裝": "python setup_dependencies.py",
    "快速訓練 (3代)": "python integrated_training.py --generations 3",
    "完整訓練": "python integrated_training.py --generations 10 --episodes-per-gen 5",
    "多Actor訓練": "python integrated_training.py --ray-actors 8",
    "大種族訓練": "python integrated_training.py --population-size 50",
}

# ============================================================
# 9. 配置參數表
# ============================================================

CONFIG_TABLE = """
┌─────────────────┬──────────┬──────────┬───────────────┐
│ 參數            │ 默認值   │ 推薦範圍 │ 說明          │
├─────────────────┼──────────┼──────────┼───────────────┤
│ generations     │ 10       │ 5-50     │ 訓練代數      │
│ episodes_per    │ 3        │ 1-5      │ 每代回合數    │
│ population_size │ 20       │ 10-50    │ 種族大小      │
│ elite_size      │ 4        │ 2-10     │ 精英數量      │
│ ray_actors      │ 4        │ 2-8      │ 並行Actor數   │
│ mutation_std    │ 0.1      │ 0.05-0.2 │ 突變標準差    │
└─────────────────┴──────────┴──────────┴───────────────┘

配置建議:
💻 單機 (4核):   ray_actors=4, population=20
🖥️ 工作站 (8核):  ray_actors=8, population=30
🔥 高性能:       ray_actors=16, population=50
⚡ 快速測試:     generations=3, episodes_per=1
"""

# ============================================================
# 10. 故障排除速查
# ============================================================

TROUBLESHOOTING = {
    "Ray初始化失敗": {
        "症狀": "RuntimeError: Failed to initialize Ray",
        "解決": [
            "pip install --upgrade ray",
            "python -c 'import ray; ray.init()'",
        ],
    },
    "內存不足": {
        "症狀": "MemoryError or process killed",
        "解決": [
            "減少 --ray-actors (4→2)",
            "減少 --population-size (20→10)",
            "增加 --episodes-per-gen 並減少 --generations",
        ],
    },
    "訓練很慢": {
        "症狀": "超過1小時還沒完成",
        "解決": [
            "增加 --ray-actors (if hardware allows)",
            "減少 --episodes-per-gen",
            "在GPU上運行 (需配置Ray GPU)",
        ],
    },
}

# ============================================================
# 11. 性能指標速查
# ============================================================

PERFORMANCE_METRICS = """
監控指標:

1. 適應度進度
   Best Fitness: ↗️ 應該遞增
   Mean Fitness: ↗️ 應該上升
   Std Fitness:  ↙️ 應該縮小 (收斂)

2. 環境性能
   Mean Reward: ↗️ 應該上升
   Mean Makespan: ↙️ 應該下降
   Setup Count: ↙️ 應該下降

3. 系統效率
   Generation Time: 應穩定在5-10分鐘
   Ray Throughput: 環境/秒

成功指標:
✓ 第1代 → 第10代: 適應度提升20%+
✓ Makespan改善10%+
✓ Setup次數減少30%+
"""

# ============================================================

def print_quick_ref():
    """打印快速參考"""
    print(__doc__)
    print("\n" + "="*60)
    print("快速開始:\n")
    for cmd, desc in COMMANDS.items():
        print(f"{cmd:20} → {cmd}")
    print("\n" + "="*60)
    print("性能指標:\n")
    print(PERFORMANCE_METRICS)


if __name__ == "__main__":
    print_quick_ref()
