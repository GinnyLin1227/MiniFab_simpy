"""
Ray-based Distributed Training
================================

使用Ray進行分散式訓練
- Ray Remote: 分散式環境並行執行
- Ray Tune: 超參數搜索和實驗管理
- Ray RLlib: (可選) 整合到標準RL框架
"""

import ray
from ray import air, tune
from ray.tune import CLIReporter, Stopper
from ray.air import session
from typing import Dict, List, Optional, Callable, Tuple
import numpy as np
import time
import os


class MiniFabSimulatorActor:
    """
    Ray Actor for parallel environment simulation
    
    每個Actor管理一個MiniFab環境實例，
    可以並行執行多個環境來加速訓練
    """
    
    def __init__(
        self,
        env_class,
        env_config: Dict,
        actor_id: int,
        seed: int,
    ):
        """
        初始化模擬器Actor
        
        Args:
            env_class: 環境類 (MultiAgentMiniFabEnv)
            env_config: 環境配置
            actor_id: Actor ID (用於區分)
            seed: 隨機種子
        """
        self.actor_id = actor_id
        self.env_config = env_config
        
        # 建立環境
        self.env = env_class(
            **env_config,
            seed=seed + actor_id,  # 不同Actor使用不同種子
        )
        
        self.episode_count = 0
        self.total_rewards = []
    
    def run_episode(
        self,
        policy_fn: Callable,
        num_steps: int = 1000,
    ) -> Dict:
        """
        執行一個完整的訓練回合
        
        Args:
            policy_fn: 策略函數 (接收obs，返回action)
            num_steps: 最大步數
        
        Returns:
            回合統計信息
        """
        observations, infos = self.env.reset()
        
        episode_reward = 0.0
        episode_length = 0
        done = False
        
        # 執行回合
        while not done and episode_length < num_steps:
            # 獲取動作
            actions = {}
            for agent in self.env.agents:
                obs = observations[agent]
                action = policy_fn(agent, obs)
                actions[agent] = action
            
            # 執行環境步驟
            observations, rewards, terminations, truncations, infos = self.env.step(actions)
            
            # 累計獎勵
            for agent in self.env.agents:
                episode_reward += rewards.get(agent, 0.0)
            
            done = any(terminations.values()) or any(truncations.values())
            episode_length += 1
        
        # 獲取最終報告
        report = self.env.get_report()
        
        episode_stats = {
            "episode_reward": float(episode_reward),
            "episode_length": episode_length,
            "finished_lots": report["finished_lots"],
            "makespan_min": report["makespan_min"],
            "avg_tpt_min": report["avg_tpt_min"],
            "setup_count": report["setup_count"],
            "machine_util": report["machine_util"],
        }
        
        self.episode_count += 1
        self.total_rewards.append(episode_reward)
        
        return episode_stats
    
    def get_stats(self) -> Dict:
        """獲取Actor統計信息"""
        return {
            "actor_id": self.actor_id,
            "episodes_completed": self.episode_count,
            "mean_reward": float(np.mean(self.total_rewards)) if self.total_rewards else 0.0,
            "max_reward": float(np.max(self.total_rewards)) if self.total_rewards else 0.0,
            "min_reward": float(np.min(self.total_rewards)) if self.total_rewards else 0.0,
        }


class RayDistributedTrainer:
    """Ray分散式訓練器"""
    
    def __init__(
        self,
        env_class,
        env_config: Dict,
        num_actors: int = 4,
        ray_address: Optional[str] = None,
    ):
        """
        初始化分散式訓練器
        
        Args:
            env_class: 環境類
            env_config: 環境配置
            num_actors: 並行Actor數量
            ray_address: Ray集群地址 (None = 本地)
        """
        # 初始化Ray
        if not ray.is_initialized():
            if ray_address:
                ray.init(address=ray_address)
            else:
                ray.init(
                    ignore_reinit_error=True,
                    num_cpus=num_actors,
                )
        
        self.env_class = env_class
        self.env_config = env_config
        self.num_actors = num_actors
        
        # 建立Actor池
        self.actors: List[MiniFabSimulatorActor] = []
        self._create_actor_pool()
        
        self.training_stats = []
    
    def _create_actor_pool(self):
        """建立Actor池"""
        # 將環境類轉換為Remote Actor
        RemoteSimulator = ray.remote(MiniFabSimulatorActor)
        
        for i in range(self.num_actors):
            actor = RemoteSimulator.remote(
                self.env_class,
                self.env_config,
                actor_id=i,
                seed=42 + i * 100,
            )
            self.actors.append(actor)
        
        print(f"[Ray] Created {self.num_actors} simulator actors")
    
    def train_generation(
        self,
        policy_fn: Callable,
        episodes_per_actor: int = 5,
    ) -> Dict:
        """
        訓練一代（並行執行所有Actor的回合）
        
        Args:
            policy_fn: 策略函數
            episodes_per_actor: 每個Actor的回合數
        
        Returns:
            代統計信息
        """
        futures = []
        
        # 發送所有訓練任務到Actor
        for actor in self.actors:
            for _ in range(episodes_per_actor):
                future = actor.run_episode.remote(policy_fn)
                futures.append(future)
        
        # 收集結果
        results = ray.get(futures)
        
        # 聚合統計
        gen_stats = self._aggregate_results(results)
        self.training_stats.append(gen_stats)
        
        return gen_stats
    
    def _aggregate_results(self, results: List[Dict]) -> Dict:
        """
        聚合多個回合的結果
        
        Args:
            results: 個別回合的結果列表
        
        Returns:
            聚合統計信息
        """
        rewards = [r["episode_reward"] for r in results]
        makespans = [r["makespan_min"] for r in results]
        setups = [r["setup_count"] for r in results]
        
        return {
            "generation": len(self.training_stats),
            "num_episodes": len(results),
            "mean_reward": float(np.mean(rewards)),
            "std_reward": float(np.std(rewards)),
            "max_reward": float(np.max(rewards)),
            "min_reward": float(np.min(rewards)),
            "mean_makespan": float(np.mean(makespans)),
            "std_makespan": float(np.std(makespans)),
            "mean_setup": float(np.mean(setups)),
        }
    
    def get_actor_stats(self) -> List[Dict]:
        """獲取所有Actor的統計信息"""
        futures = [actor.get_stats.remote() for actor in self.actors]
        stats = ray.get(futures)
        return stats
    
    def shutdown(self):
        """關閉Ray"""
        ray.shutdown()


class RayTuneExperiment:
    """
    Ray Tune 實驗管理
    
    用於超參數搜索和多次實驗運行
    """
    
    def __init__(
        self,
        name: str = "minifab_training",
        storage_path: str = "./ray_results",
    ):
        """
        初始化Tune實驗
        
        Args:
            name: 實驗名稱
            storage_path: 結果存儲路徑
        """
        self.name = name
        self.storage_path = storage_path
        
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
    
    def run_search(
        self,
        config: Dict,
        num_samples: int = 5,
        max_iterations: int = 10,
    ):
        """
        執行超參數搜索
        
        Args:
            config: Tune配置
            num_samples: 樣本數
            max_iterations: 最大迭代次數
        """
        tuner = tune.Tuner(
            self.trainable_fn,
            param_space=config,
            tune_config=tune.TuneConfig(
                num_samples=num_samples,
                max_concurrent_trials=4,
            ),
            run_config=air.RunConfig(
                name=self.name,
                storage_path=self.storage_path,
                stop={"training_iteration": max_iterations},
                checkpoint_config=air.CheckpointConfig(
                    num_to_keep=3,
                    checkpoint_score_attribute="mean_reward",
                ),
                progress_reporter=CLIReporter(
                    metric_columns=["mean_reward", "mean_makespan"]
                ),
            ),
        )
        
        results = tuner.fit()
        return results


class DistributedPolicyOptimizer:
    """
    分散式策略優化器
    
    整合Ray分散式訓練和ES進化策略
    """
    
    def __init__(
        self,
        env_class,
        env_config: Dict,
        es_trainer,
        num_actors: int = 4,
    ):
        """
        初始化優化器
        
        Args:
            env_class: 環境類
            env_config: 環境配置
            es_trainer: ES訓練器實例
            num_actors: Actor數量
        """
        self.env_class = env_class
        self.env_config = env_config
        self.es_trainer = es_trainer
        
        # 建立分散式訓練器
        self.ray_trainer = RayDistributedTrainer(
            env_class,
            env_config,
            num_actors=num_actors,
        )
    
    def train_generation(
        self,
        episodes_per_policy: int = 3,
    ) -> Dict:
        """
        訓練一代策略
        
        流程：
        1. 使用Ray並行評估ES種族中的所有策略
        2. 計算每個策略的適應度
        3. 返回統計信息
        
        Args:
            episodes_per_policy: 每個策略的評估回合數
        
        Returns:
            代統計信息
        """
        # 評估當前種族
        def evaluate_individual(individual):
            """評估單個個體"""
            from minifab_decision_system import FeatureVector
            
            # 將權重轉換為策略
            def policy_fn(agent, obs):
                # 簡化實現：使用obs的第一維作為動作
                # 實際應使用神經網路
                return int(obs[0] * 4) % 4
            
            # 使用Ray訓練
            stats = self.ray_trainer.train_generation(
                policy_fn,
                episodes_per_actor=episodes_per_policy,
            )
            
            return stats["mean_reward"]
        
        # 評估種族
        eval_stats = self.es_trainer.evaluate_population(
            evaluate_fn=evaluate_individual,
            num_trials=episodes_per_policy,
        )
        
        # 進化下一代
        new_pop = self.es_trainer.evolve()
        
        return {
            "generation": self.es_trainer.generation,
            "eval_stats": eval_stats,
            "population_size": len(new_pop),
        }
    
    def shutdown(self):
        """關閉訓練"""
        self.ray_trainer.shutdown()


# ============================================================
# 便捷函數
# ============================================================

def setup_ray_cluster(num_workers: int = 4) -> Dict:
    """
    設置Ray集群
    
    Args:
        num_workers: Worker數量
    
    Returns:
        集群信息
    """
    if not ray.is_initialized():
        ray.init(num_cpus=num_workers)
    
    cluster_info = {
        "initialized": ray.is_initialized(),
        "num_cpus": ray.cluster_resources()["CPU"],
        "num_gpus": ray.cluster_resources().get("GPU", 0),
        "nodes": len(ray.nodes()),
    }
    
    print("[Ray] Cluster Info:", cluster_info)
    return cluster_info


def parallel_env_rollout(
    env_factory: Callable,
    policy_fn: Callable,
    num_parallel: int = 4,
    num_episodes: int = 5,
) -> List[Dict]:
    """
    並行環境Rollout
    
    Args:
        env_factory: 環境工廠函數
        policy_fn: 策略函數
        num_parallel: 並行環境數
        num_episodes: 每環境的回合數
    
    Returns:
        所有回合的結果
    """
    # 建立Remote環境
    RemoteEnv = ray.remote(env_factory)
    
    environments = [RemoteEnv.remote() for _ in range(num_parallel)]
    
    # 執行Rollout
    futures = []
    for env in environments:
        for _ in range(num_episodes):
            # 簡化實現
            future = env.rollout.remote(policy_fn)
            futures.append(future)
    
    # 收集結果
    results = ray.get(futures)
    return results
