"""
Integrated Training Script
===========================

整合Ray分散式訓練 + 事件驅動決策 + 演化策略

完整示例：
1. 使用Ray進行分散式環境評估
2. 使用ES進行種族演化
3. 使用事件驅動系統進行實時決策
"""

import numpy as np
import argparse
import json
from pathlib import Path
from datetime import datetime
import wandb

# 假設已安裝必要的包
# pip install ray gymnasium pettingzoo numpy pandas

import ray

# 本地導入
from minifab_env2 import MultiAgentMiniFabEnv
from minifab_decision_system import (
    EventDrivenScheduler, 
    FeatureExtractor,
    EventType,
    DecisionContext,
)
from minifab_es_trainer import EvolutionStrategies, PolicyNetwork
from minifab_ray_trainer import (
    RayDistributedTrainer,
    DistributedPolicyOptimizer,
    setup_ray_cluster,
)


class IntegratedTrainer:
    """整合訓練器"""
    
    def __init__(
        self,
        output_dir: str = "./training_results",
        num_ray_actors: int = 4,
        population_size: int = 20,
        elite_size: int = 4,
    ):
        """
        初始化整合訓練器
        
        Args:
            output_dir: 輸出目錄
            num_ray_actors: Ray Actor數量
            population_size: ES種族大小
            elite_size: ES精英數量
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 設置Ray
        print("[Trainer] Setting up Ray cluster...")
        self.ray_info = setup_ray_cluster(num_workers=num_ray_actors)
        
        # 初始化ES訓練器
        print("[Trainer] Initializing Evolution Strategies...")
        self.es_trainer = EvolutionStrategies(
            input_dim=16,  # 特徵維度
            hidden_dim=64,
            output_dim=4,  # 4種派工策略
            population_size=population_size,
            elite_size=elite_size,
            mutation_std=0.1,
        )
        
        # 初始化事件驅動調度器
        print("[Trainer] Initializing Event-Driven Scheduler...")
        config = self._load_config()
        self.scheduler = EventDrivenScheduler(config)
        
        # 環境配置
        self.env_config = {
            "max_lots": 84,
            "decision_interval": 30.0,
            "max_time": 20000.0,
        }
        
        # 初始化分散式訓練器
        print("[Trainer] Initializing Ray Distributed Trainer...")
        self.ray_trainer = RayDistributedTrainer(
            MultiAgentMiniFabEnv,
            self.env_config,
            num_actors=num_ray_actors,
        )
        
        # 統計
        self.training_log = []
        self.generation = 0
    
    def _load_config(self) -> dict:
        """載入系統配置"""
        # 簡化實現：返回基本配置
        return {
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
    
    def train_generation(self, num_episodes_per_policy: int = 3) -> dict:
        """
        訓練一代
        
        流程：
        1. 使用Ray評估ES種族中的每個策略
        2. 計算相對適應度 (同儕比較)
        3. 進化下一代
        4. 記錄統計信息
        
        Args:
            num_episodes_per_policy: 每個策略的評估回合數
        
        Returns:
            代統計信息
        """
        print(f"\n{'='*60}")
        print(f"Generation {self.generation} Training")
        print(f"{'='*60}")
        
        # 1. 評估種族
        print(f"[Gen {self.generation}] Evaluating {len(self.es_trainer.population)} policies...")
        
        eval_stats = self.es_trainer.evaluate_population(
            evaluate_fn=self._evaluate_policy,
            num_trials=num_episodes_per_policy,
        )
        
        print(f"[Gen {self.generation}] Evaluation complete:")
        print(f"  Best fitness: {eval_stats['best_fitness']:.2f}")
        print(f"  Mean fitness: {eval_stats['mean_fitness']:.2f}")
        print(f"  Worst fitness: {eval_stats['worst_fitness']:.2f}")
        
        # 2. 使用Ray進行並行環境模擬
        print(f"[Gen {self.generation}] Running distributed environment rollouts...")
        
        best_individual = self.es_trainer.get_best_policy()
        best_policy_fn = self._create_policy_fn(best_individual)
        
        ray_stats = self.ray_trainer.train_generation(
            best_policy_fn,
            episodes_per_actor=num_episodes_per_policy,
        )
        
        print(f"[Gen {self.generation}] Distributed training complete:")
        print(f"  Mean reward: {ray_stats['mean_reward']:.2f}")
        print(f"  Mean makespan: {ray_stats['mean_makespan']:.1f} min")
        print(f"  Mean setup count: {ray_stats['mean_setup']:.1f}")
        
        # 3. 進化下一代
        print(f"[Gen {self.generation}] Evolving next generation...")
        new_pop = self.es_trainer.evolve()
        
        # 4. 統計信息
        gen_stats = {
            "generation": self.generation,
            "timestamp": datetime.now().isoformat(),
            "es_eval": eval_stats,
            "ray_rollout": ray_stats,
            "best_individual_id": best_individual.individual_id,
            "best_fitness": eval_stats['best_fitness'],
            "mean_fitness": eval_stats['mean_fitness'],
        }
        
        self.training_log.append(gen_stats)
        self.generation += 1
        
        return gen_stats
    
    def _evaluate_policy(self, policy_network: PolicyNetwork) -> float:
        """
        真正運行環境來評估策略 (取消隨機數)
        """
        # 1. 建立一個獨立的測試環境
        env = MultiAgentMiniFabEnv(**self.env_config)
        obs, _ = env.reset()
        done = False
        
        # 2. 讓這個神經網路控制產線直到結束或超時
        while not done:
            # 將狀態轉換為神經網路輸入
            actions = {}
            for agent, agent_obs in obs.items():
                probs = policy_network.forward(agent_obs.reshape(1, -1))
                actions[agent] = int(np.argmax(probs[0]))
                
            obs, _, terminations, truncations, _ = env.step(actions)
            done = any(terminations.values()) or any(truncations.values())
            
        # 3. 取得最終完工時間 (Makespan)
        report = env.get_report()
        # ==========================================
        # 4. 提取四大 KPI 指標並計算綜合 Score (Reward)
        # ==========================================
        
        # (1) 最大化產出 (Outs): 完成的批次數量
        outs = report.get("finished_lots", 0)
        
        # (2) 最小化生產週期 (TPT): 平均花費時間
        avg_tpt = report.get("avg_tpt_min", 20000.0)
        
        # (3) 最小化在製品 (WIP): 提取 wip_log 中的平均值
        wip_df = report.get("wip_log")
        if wip_df is not None and not wip_df.empty:
            mean_wip = wip_df["wip"].mean()
        else:
            mean_wip = 84.0 # 若沒有紀錄，給予最差的預設值
            
        # (4) 最大化使用率 (Utilization): 計算所有機台的平均使用率 (0.0 ~ 1.0)
        util_dict = report.get("machine_util", {})
        if util_dict:
            mean_util = sum(util_dict.values()) / len(util_dict)
        else:
            mean_util = 0.0
            
        # 綜合計分公式 (您可以依據論文的需求調整這些權重數字)
        # 正向指標用加的 (+)，負向指標用減的 (-)
        score = (outs * 100) - (avg_tpt * 2) - (mean_wip * 5) + (mean_util * 1000)
        
        return float(score)
    
    def _create_policy_fn(self, individual) -> callable:
        """根據個體創建策略函數"""
        network = PolicyNetwork(16, 64, 4)
        network.set_weights(individual.weights)
        
        def policy_fn(agent, obs):
            probs = network.forward(obs.reshape(1, -1))
            action = int(np.argmax(probs[0]))
            return action
        
        return policy_fn
    
    def train(
        self,
        num_generations: int = 10,
        episodes_per_gen: int = 3,
        checkpoint_interval: int = 5,
        use_wandb: bool = True # 新增 WandB 開關
    ):
        """
        完整訓練流程
        
        Args:
            num_generations: 訓練代數
            episodes_per_gen: 每代的評估回合數
            checkpoint_interval: 檢查點保存間隔
        """
        print(f"\n{'='*60}")
        print(f"Starting Integrated Training")
        print(f"  Generations: {num_generations}")
        print(f"  Episodes per generation: {episodes_per_gen}")
        print(f"  Ray actors: {self.ray_info['num_cpus']}")
        print(f"  ES population size: {self.es_trainer.population_size}")
        print(f"{'='*60}")
        if use_wandb:
            wandb.init(
                project="minifab_es_training",
                name=f"ray_es_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                config={
                    "total_generations": num_generations,
                    "episodes_per_gen": episodes_per_gen,
                    "population_size": self.es_trainer.population_size,
                    "elite_size": self.es_trainer.elite_size,
                    "mutation_std": self.es_trainer.mutation_std,
                    "ray_actors": self.ray_info['num_cpus'],
                }
            )
        try:
            for gen in range(num_generations):
                # 訓練一代
                gen_stats = self.train_generation(episodes_per_gen)
                if use_wandb:
                    wandb.log({
                        "generation": gen_stats["generation"],
                        
                        "es/best_fitness": gen_stats["es_eval"]["best_fitness"],
                        "es/mean_fitness": gen_stats["es_eval"]["mean_fitness"],
                        "es/worst_fitness": gen_stats["es_eval"]["worst_fitness"],
                        
                        "rollout/mean_reward": gen_stats["ray_rollout"]["mean_reward"],
                        "rollout/mean_makespan": gen_stats["ray_rollout"]["mean_makespan"],
                        "rollout/mean_setup": gen_stats["ray_rollout"]["mean_setup"]
                    }, step=gen_stats["generation"])
                # 保存檢查點
                if (gen + 1) % checkpoint_interval == 0:
                    self.save_checkpoint(f"gen_{gen}_checkpoint.json")
                    print(f"[Checkpoint] Saved at generation {gen}")
            
            # 最終統計
            self.print_summary()
            if use_wandb:
                best_ind = self.es_trainer.get_best_policy()
                wandb.summary["best_individual_id"] = best_ind.individual_id
                wandb.summary["best_fitness_final"] = best_ind.fitness
                wandb.summary["wins"] = best_ind.wins
        except KeyboardInterrupt:
            print("\n[Training] Interrupted by user")
        
        finally:
            self.cleanup()
    
    def save_checkpoint(self, filename: str):
        """保存檢查點"""
        checkpoint = {
            "generation": self.generation,
            "training_log": self.training_log,
            "population_snapshot": self.es_trainer.get_population_snapshot(),
            "ray_info": self.ray_info,
        }
        
        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(checkpoint, f, indent=2)
    
    def print_summary(self):
        """打印訓練總結"""
        print(f"\n{'='*60}")
        print("Training Summary")
        print(f"{'='*60}")
        
        if not self.training_log:
            print("No training data available")
            return
        
        # 統計信息
        best_fitness_vals = [g["best_fitness"] for g in self.training_log]
        mean_fitness_vals = [g["mean_fitness"] for g in self.training_log]
        
        print(f"Total generations: {len(self.training_log)}")
        print(f"Best fitness (final): {best_fitness_vals[-1]:.2f}")
        print(f"Best fitness (overall): {max(best_fitness_vals):.2f}")
        print(f"Mean fitness (final): {mean_fitness_vals[-1]:.2f}")
        
        # 改進趨勢
        if len(best_fitness_vals) > 1:
            improvement = best_fitness_vals[-1] - best_fitness_vals[0]
            print(f"Fitness improvement: {improvement:.2f}")
        
        # 保存最終報告
        self.save_final_report()
    
    def save_final_report(self):
        """保存最終報告"""
        report = {
            "training_date": datetime.now().isoformat(),
            "total_generations": len(self.training_log),
            "ray_configuration": self.ray_info,
            "es_configuration": {
                "population_size": self.es_trainer.population_size,
                "elite_size": self.es_trainer.elite_size,
                "mutation_std": self.es_trainer.mutation_std,
            },
            "training_history": self.training_log,
            "best_individual": self.es_trainer.get_best_policy().to_dict(),
        }
        
        filepath = self.output_dir / "training_report.json"
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n[Summary] Report saved to {filepath}")
    
    def cleanup(self):
        """清理資源"""
        print("\n[Cleanup] Shutting down Ray...")
        self.ray_trainer.shutdown()
        print("[Cleanup] Done")


def main():
    """主函數"""
    parser = argparse.ArgumentParser(
        description="Integrated MiniFab Training with Ray + ES + Event-Driven System"
    )
    parser.add_argument(
        "--generations", type=int, default=10,
        help="Number of generations to train"
    )
    parser.add_argument(
        "--episodes-per-gen", type=int, default=3,
        help="Episodes to evaluate each policy per generation"
    )
    parser.add_argument(
        "--population-size", type=int, default=20,
        help="ES population size"
    )
    parser.add_argument(
        "--elite-size", type=int, default=4,
        help="ES elite size"
    )
    parser.add_argument(
        "--ray-actors", type=int, default=4,
        help="Number of Ray actors for parallel simulation"
    )
    parser.add_argument(
        "--output-dir", type=str, default="./training_results",
        help="Output directory for results"
    )
    # 🟢 [WANDB 新增] 命令列開關
    parser.add_argument("--no-wandb", action="store_true", help="Disable WandB logging")
    args = parser.parse_args()
    
    # 建立訓練器
    trainer = IntegratedTrainer(
        output_dir=args.output_dir,
        num_ray_actors=args.ray_actors,
        population_size=args.population_size,
        elite_size=args.elite_size,
    )
    
    # 開始訓練
    trainer.train(
        num_generations=args.generations,
        episodes_per_gen=args.episodes_per_gen,
        checkpoint_interval=5,
        use_wandb=not args.no_wandb
    )


if __name__ == "__main__":
    main()
