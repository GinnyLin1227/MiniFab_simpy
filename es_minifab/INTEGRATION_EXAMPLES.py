"""
Integration with Existing MiniFab Environment
==============================================

如何將新的系統與現有的 minifab_env2.py 集成
"""

# 示例1: 在現有環境中使用事件驅動決策系統
# =========================================================

def example_event_driven_with_env():
    """
    在MiniFabEnv中使用事件驅動決策系統
    """
    from minifab_env2 import MultiAgentMiniFabEnv
    from minifab_decision_system import (
        EventDrivenScheduler,
        FeatureExtractor,
        EventType,
        DecisionContext,
    )
    import numpy as np
    
    # 1. 建立環境
    env = MultiAgentMiniFabEnv(
        max_lots=84,
        decision_interval=30.0,
        max_time=20000.0,
        seed=42,
    )
    
    # 2. 建立決策系統
    config = {
        "PROCESS_FLOW": ["S1", "S2", "S3", "S4", "S5", "S6"],
        "PROCESS_TIME": {
            "S1": 225, "S2": 30, "S3": 55,
            "S4": 50, "S5": 255, "S6": 10,
        },
        "STEP_TO_CELL": {
            "S1": "C1", "S5": "C1", "S3": "C2",
            "S6": "C2", "S2": "C3", "S4": "C3",
        },
        "BUFFER_CAPACITY": {"C1": 18, "C2": 12, "C3": 12},
        "PRODUCT_MIX": {"Pa": 51, "Pb": 30, "TW": 3},
    }
    
    scheduler = EventDrivenScheduler(config)
    
    # 3. 訓練迴圈
    observations, infos = env.reset(seed=42)
    
    for step in range(100):
        # 在決策點使用事件驅動系統
        if step % 10 == 0:  # 每10步的決策點
            # 建立決策上下文
            context = DecisionContext(
                current_time=env.core.env.now,
                machine_name="Ma",
                event_type=EventType.MACHINE_AVAILABLE,
                machine_state={},
                cell_queues=env.core.cell_queues,
                pending_transport=env.core.transport_task_pool,
                wip_summary={},
            )
            
            # 觸發決策
            action_idx, metadata = scheduler.trigger_decision(
                context,
                policy_network=None  # 後續可替換為訓練好的網路
            )
        
        # 正常執行環境步驟
        actions = {
            agent: env.action_space(agent).sample()
            for agent in env.agents
        }
        
        observations, rewards, terminations, truncations, infos = env.step(actions)
        
        if any(terminations.values()):
            break
    
    print("✓ Event-driven decision system integrated successfully")


# 示例2: 使用ES訓練器評估策略
# =========================================================

def example_es_training():
    """
    使用ES訓練器進行策略進化
    """
    from minifab_es_trainer import EvolutionStrategies, PolicyNetwork
    from minifab_env2 import MultiAgentMiniFabEnv
    import numpy as np
    
    # 1. 初始化ES
    es = EvolutionStrategies(
        input_dim=12,
        hidden_dim=64,
        output_dim=4,
        population_size=10,  # 小規模示例
        elite_size=2,
        mutation_std=0.1,
    )
    
    # 2. 定義評估函數
    def evaluate_fn(network):
        """評估策略在環境中的表現"""
        env = MultiAgentMiniFabEnv(
            max_lots=84,
            decision_interval=30.0,
            max_time=5000.0,  # 快速評估
        )
        
        obs, _ = env.reset()
        total_reward = 0
        
        while env.agents:
            # 使用網路生成動作
            actions = {}
            for agent in env.agents:
                probs = network.forward(obs[agent].reshape(1, -1))
                actions[agent] = int(np.argmax(probs[0]))
            
            obs, rewards, terms, truncs, _ = env.step(actions)
            total_reward += sum(rewards.values())
            
            if any(terms.values()) or any(truncs.values()):
                break
        
        env.close()
        return total_reward
    
    # 3. 訓練迴圈
    for generation in range(3):
        print(f"\nGeneration {generation}")
        
        # 評估
        eval_stats = es.evaluate_population(evaluate_fn, num_trials=1)
        print(f"Best fitness: {eval_stats['best_fitness']:.2f}")
        print(f"Mean fitness: {eval_stats['mean_fitness']:.2f}")
        
        # 進化
        es.evolve()
    
    print("\n✓ ES training completed")


# 示例3: 使用Ray進行分散式訓練
# =========================================================

def example_ray_distributed():
    """
    使用Ray進行分散式環境評估
    """
    try:
        import ray
    except ImportError:
        print("Ray not installed. Run: pip install ray")
        return
    
    from minifab_ray_trainer import RayDistributedTrainer
    from minifab_env2 import MultiAgentMiniFabEnv
    import numpy as np
    
    # 初始化Ray
    if not ray.is_initialized():
        ray.init(ignore_reinit_error=True, num_cpus=4)
    
    # 建立分散式訓練器
    trainer = RayDistributedTrainer(
        MultiAgentMiniFabEnv,
        env_config={
            "max_lots": 84,
            "decision_interval": 30.0,
            "max_time": 5000.0,
        },
        num_actors=2,
    )
    
    # 定義策略
    def policy_fn(agent, obs):
        """簡單策略"""
        return int(obs[0] * 4) % 4
    
    # 執行
    print("Running distributed training...")
    gen_stats = trainer.train_generation(policy_fn, episodes_per_actor=2)
    
    print(f"Generation stats:")
    print(f"  Mean reward: {gen_stats['mean_reward']:.2f}")
    print(f"  Mean makespan: {gen_stats['mean_makespan']:.1f}")
    
    trainer.shutdown()
    print("✓ Ray distributed training completed")


# 示例4: 完整整合 - 調用integrated_training.py
# =========================================================

def example_full_integration():
    """
    完整的整合訓練 (推薦)
    """
    print("""
    完整整合示例 - 只需一行命令:
    
    python integrated_training.py \\
        --generations 10 \\
        --episodes-per-gen 3 \\
        --population-size 20 \\
        --ray-actors 4
    
    這將:
    1. 使用Ray的4個Actor並行評估
    2. 通過ES進化20個策略的種族
    3. 自動提取12維特徵進行決策
    4. 保存所有結果和檢查點
    5. 生成最終報告
    """)


# 示例5: 自定義特徵提取
# =========================================================

def example_custom_features():
    """
    自定義特徵提取 - 添加新特徵
    """
    from minifab_decision_system import FeatureVector, FeatureExtractor
    
    # 擴展FeatureVector類
    class ExtendedFeatureVector(FeatureVector):
        """擴展特徵向量 (14維)"""
        
        # 添加新特徵
        oht_queue_length: float = 0.0      # 13
        bottleneck_score: float = 0.0      # 14
        
        def to_array(self):
            arr = super().to_array()
            return np.append(arr, [
                self.oht_queue_length,
                self.bottleneck_score,
            ])
    
    print("✓ Custom feature extraction example created")


# 示例6: 與現有minifab_rl.py集成
# =========================================================

def example_integration_with_existing_rl():
    """
    與現有RLTrainer集成
    """
    print("""
    在minifab_rl.py中集成新系統:
    
    1. 在RLTrainer.__init__中添加:
        from minifab_decision_system import EventDrivenScheduler
        self.scheduler = EventDrivenScheduler(config)
    
    2. 在select_action方法中使用:
        context = DecisionContext(...)
        action_idx, _ = self.scheduler.trigger_decision(context)
        return action_idx
    
    3. 在訓練循環中:
        # 使用神經網路策略替代Q-table
        from minifab_es_trainer import PolicyNetwork
        self.policy = PolicyNetwork(12, 64, 4)
    """)


# 示例7: 監控和可視化
# =========================================================

def example_monitoring():
    """
    訓練過程監控
    """
    print("""
    監控訓練進度:
    
    1. 實時日誌:
       tail -f ./training_results/*.log
    
    2. 適應度曲線:
       python plot_results.py ./training_results/training_report.json
    
    3. TensorBoard (future):
       tensorboard --logdir=./training_results/
    """)


# ========================================================
# 快速集成檢查清單
# ========================================================

INTEGRATION_CHECKLIST = """
☐ 1. 安裝依賴
     python setup_dependencies.py

☐ 2. 驗證現有環境
     python -c "from minifab_env2 import MultiAgentMiniFabEnv; print('OK')"

☐ 3. 驗證新模組
     python -c "from minifab_decision_system import EventDrivenScheduler; print('OK')"
     python -c "from minifab_es_trainer import EvolutionStrategies; print('OK')"
     python -c "from minifab_ray_trainer import RayDistributedTrainer; print('OK')"

☐ 4. 運行簡單測試
     python integrated_training.py --generations 2 --ray-actors 2

☐ 5. 檢查輸出
     ls -la ./training_results/

☐ 6. 根據需要自定義配置
     編輯 integrated_training.py 中的環境配置

☐ 7. 完整訓練運行
     python integrated_training.py --generations 10
"""


if __name__ == "__main__":
    print("MiniFab Integration Examples")
    print("="*60)
    
    # 打印集成檢查清單
    print(INTEGRATION_CHECKLIST)
    
    print("\n" + "="*60)
    print("Available examples:")
    print("  1. example_event_driven_with_env()")
    print("  2. example_es_training()")
    print("  3. example_ray_distributed()")
    print("  4. example_full_integration()")
    print("  5. example_custom_features()")
    print("  6. example_integration_with_existing_rl()")
    print("  7. example_monitoring()")
    
    print("\nRun examples with:")
    print("  python -c \"from INTEGRATION_EXAMPLES import example_event_driven_with_env; example_event_driven_with_env()\"")
