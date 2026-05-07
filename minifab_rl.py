"""
Reinforcement Learning Module
==============================
強化學習訓練、評估和策略管理
"""

import os

import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import deque
import json


class ExperienceBuffer:
    """經驗回放緩衝區"""
    
    def __init__(self, capacity: int = 10000):
        """
        Args:
            capacity: 緩衝區容量
        """
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)
    
    def add(self, transition: Tuple):
        """添加經驗"""
        self.buffer.append(transition)
    
    def sample(self, batch_size: int) -> List[Tuple]:
        """隨機採樣批次"""
        indices = np.random.choice(len(self.buffer), batch_size, replace=False)
        return [self.buffer[i] for i in indices]
    
    def __len__(self) -> int:
        return len(self.buffer)


class RLTrainer:
    """強化學習訓練器"""
    
    def __init__(
        self,
        env,
        agent_names: List[str],
        learning_rate: float = 0.001,
        gamma: float = 0.99,
        epsilon: float = 1.0,
        epsilon_decay: float = 0.995,
        epsilon_min: float = 0.01,
    ):
        """
        初始化訓練器
        
        Args:
            env: PettingZoo環境
            agent_names: 智能體名稱列表
            learning_rate: 學習率
            gamma: 折扣因子
            epsilon: 探索率
            epsilon_decay: 探索率衰減
            epsilon_min: 最小探索率
        """
        self.env = env
        self.agent_names = agent_names
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        
        # 初始化Q表 (表格型方法)
        self.q_tables = {agent: {} for agent in agent_names}
        
        # 統計信息
        self.episode_rewards = []
        self.episode_makespan = []
        self.episode_setups = []
    
    def select_action(self, agent: str, obs: np.ndarray, training: bool = True) -> int:
        """
        選擇動作 (ε-貪心)
        
        Args:
            agent: 智能體名稱
            obs: 觀測向量
            training: 是否在訓練模式
        
        Returns:
            動作索引
        """
        action_space = self.env.action_space(agent)
        
        if training and np.random.random() < self.epsilon:
            # 探索：隨機動作
            return action_space.sample()
        else:
            # 利用：最優動作
            # 簡化實現：使用觀測向量的雜湊作為狀態鍵
            state_key = self._state_to_key(obs)
            
            if state_key not in self.q_tables[agent]:
                self.q_tables[agent][state_key] = np.zeros(action_space.n)
            
            q_values = self.q_tables[agent][state_key]
            return np.argmax(q_values)
    
    def _state_to_key(self, obs: np.ndarray) -> str:
        """將連續觀測轉換為離散狀態鍵"""
        # 簡化：將觀測量化為整數
        quantized = np.round(obs * 10).astype(int)
        return str(tuple(quantized))
    
    def update_q_table(
        self,
        agent: str,
        obs: np.ndarray,
        action: int,
        reward: float,
        next_obs: np.ndarray,
        done: bool
    ):
        """更新Q表"""
        state_key = self._state_to_key(obs)
        next_state_key = self._state_to_key(next_obs)
        
        if state_key not in self.q_tables[agent]:
            action_space = self.env.action_space(agent)
            self.q_tables[agent][state_key] = np.zeros(action_space.n)
        
        if next_state_key not in self.q_tables[agent]:
            action_space = self.env.action_space(agent)
            self.q_tables[agent][next_state_key] = np.zeros(action_space.n)
        
        # Q學習更新
        current_q = self.q_tables[agent][state_key][action]
        max_next_q = np.max(self.q_tables[agent][next_state_key])
        
        new_q = current_q + self.learning_rate * (
            reward + (self.gamma * max_next_q if not done else 0) - current_q
        )
        
        self.q_tables[agent][state_key][action] = new_q
    
    def train_episode(self, render: bool = False) -> Dict:
        """
        訓練一個回合
        
        Returns:
            統計字典
        """
        observations, _ = self.env.reset()
        episode_reward = {agent: 0.0 for agent in self.agent_names}
        done = False
        step = 0
        
        while not done and step < 100:  # 最多100步決策
            # 各智能體選擇動作
            actions = {}
            for agent in self.agent_names:
                actions[agent] = self.select_action(agent, observations[agent], training=True)
            
            # 執行環境步進
            next_obs, rewards, terminations, truncations, infos = self.env.step(actions)
            done = any(terminations.values()) or any(truncations.values())
            
            # 更新Q表
            for agent in self.agent_names:
                self.update_q_table(
                    agent,
                    observations[agent],
                    actions[agent],
                    rewards[agent],
                    next_obs.get(agent, observations[agent]),
                    done
                )
                episode_reward[agent] += rewards[agent]
            
            observations = next_obs
            step += 1
        
        # 衰減探索率
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        # 記錄統計
        report = self.env.get_report()
        total_reward = sum(episode_reward.values())
        self.episode_rewards.append(total_reward)
        self.episode_makespan.append(report["makespan_min"])
        self.episode_setups.append(report["setup_count"])
        
        if render:
            self.env.render()
        
        return {
            "episode_reward": total_reward,
            "avg_agent_reward": total_reward / len(self.agent_names),
            "makespan": report["makespan_min"],
            "finished_lots": report["finished_lots"],
            "setup_count": report["setup_count"],
            "epsilon": self.epsilon,
        }
    
    def train(self, num_episodes: int = 100, render_freq: int = 20) -> List[Dict]:
        """
        訓練多個回合
        
        Args:
            num_episodes: 訓練回合數
            render_freq: 渲染頻率
        
        Returns:
            每個回合的統計列表
        """
        results = []
        
        for episode in range(num_episodes):
            render = (episode % render_freq == 0)
            stats = self.train_episode(render=render)
            stats["episode"] = episode
            results.append(stats)
            
            if (episode + 1) % 10 == 0:
                avg_reward = np.mean(self.episode_rewards[-10:])
                avg_makespan = np.mean(self.episode_makespan[-10:])
                print(
                    f"Episode {episode + 1}: "
                    f"Avg Reward={avg_reward:.2f}, "
                    f"Avg Makespan={avg_makespan:.1f} min, "
                    f"Epsilon={self.epsilon:.4f}"
                )
        
        return results
    
    def evaluate(self, num_episodes: int = 10) -> Dict:
        """
        評估當前策略 (無探索)
        
        Args:
            num_episodes: 評估回合數
        
        Returns:
            評估統計
        """
        old_epsilon = self.epsilon
        self.epsilon = 0.0  # 無探索
        
        total_rewards = []
        total_makespans = []
        total_setups = []
        
        for _ in range(num_episodes):
            observations, _ = self.env.reset()
            episode_reward = 0.0
            done = False
            step = 0
            
            while not done and step < 100:
                actions = {
                    agent: self.select_action(agent, observations[agent], training=False)
                    for agent in self.agent_names
                }
                
                next_obs, rewards, terminations, truncations, _ = self.env.step(actions)
                done = any(terminations.values()) or any(truncations.values())
                
                episode_reward += sum(rewards.values())
                observations = next_obs
                step += 1
            
            report = self.env.get_report()
            total_rewards.append(episode_reward)
            total_makespans.append(report["makespan_min"])
            total_setups.append(report["setup_count"])
        
        self.epsilon = old_epsilon
        
        return {
            "avg_episode_reward": np.mean(total_rewards),
            "std_episode_reward": np.std(total_rewards),
            "avg_makespan": np.mean(total_makespans),
            "std_makespan": np.std(total_makespans),
            "avg_setups": np.mean(total_setups),
            "std_setups": np.std(total_setups),
        }
    
    def save_q_tables(self, filepath: str):
        """保存Q表"""
        # 轉換為JSON序列化的格式
        q_tables_serializable = {}
        for agent, q_table in self.q_tables.items():
            q_tables_serializable[agent] = {
                k: v.tolist() for k, v in q_table.items()
            }
        
        directory = os.path.dirname(filepath)
        
        # 2. 核心！如果資料夾不存在，就讓 Python 自動建立它
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        
        with open(filepath, 'w') as f:
            json.dump(q_tables_serializable, f, indent=2)
    
    def load_q_tables(self, filepath: str):
        """載入Q表"""
        with open(filepath, 'r') as f:
            q_tables_serializable = json.load(f)
        
        for agent, q_table in q_tables_serializable.items():
            self.q_tables[agent] = {
                k: np.array(v) for k, v in q_table.items()
            }
    
    def get_policy(self) -> Dict:
        """獲取當前策略 (貪心)"""
        policy = {}
        for agent in self.agent_names:
            policy[agent] = {}
            for state_key, q_values in self.q_tables[agent].items():
                policy[agent][state_key] = int(np.argmax(q_values))
        
        return policy


class PolicyAnalyzer:
    """策略分析器"""
    
    def __init__(self, trainer: RLTrainer):
        """初始化分析器"""
        self.trainer = trainer
    
    def analyze_convergence(self) -> Dict:
        """分析收斂性"""
        rewards = self.trainer.episode_rewards
        
        if len(rewards) < 10:
            return {"converged": False, "reason": "Not enough episodes"}
        
        recent_rewards = rewards[-10:]
        earlier_rewards = rewards[:10]
        
        improvement = (np.mean(recent_rewards) - np.mean(earlier_rewards))
        std_recent = np.std(recent_rewards)
        
        converged = improvement < 1.0 and std_recent < 5.0
        
        return {
            "converged": converged,
            "improvement": improvement,
            "recent_std": std_recent,
            "recent_avg": np.mean(recent_rewards),
        }
    
    def compare_strategies(
        self,
        strategy_configs: List[Dict],
        num_runs: int = 5
    ) -> Dict:
        """
        比較不同策略配置
        
        Args:
            strategy_configs: 策略配置列表
            num_runs: 每個策略運行次數
        
        Returns:
            比較結果
        """
        results = {}
        
        for config in strategy_configs:
            name = config.get("name", "unnamed")
            config_copy = config.copy()
            config_copy.pop("name", None)
            
            # 創建新的訓練器
            trainer = RLTrainer(self.trainer.env, **config_copy)
            
            run_results = []
            for _ in range(num_runs):
                observations, _ = self.trainer.env.reset()
                episode_reward = 0.0
                done = False
                step = 0
                
                while not done and step < 100:
                    actions = {
                        agent: trainer.select_action(agent, observations[agent], training=False)
                        for agent in self.trainer.agent_names
                    }
                    
                    next_obs, rewards, terminations, truncations, _ = self.trainer.env.step(actions)
                    done = any(terminations.values()) or any(truncations.values())
                    
                    episode_reward += sum(rewards.values())
                    observations = next_obs
                    step += 1
                
                report = self.trainer.env.get_report()
                run_results.append({
                    "reward": episode_reward,
                    "makespan": report["makespan_min"],
                    "setups": report["setup_count"],
                })
            
            # 統計
            results[name] = {
                "avg_reward": np.mean([r["reward"] for r in run_results]),
                "std_reward": np.std([r["reward"] for r in run_results]),
                "avg_makespan": np.mean([r["makespan"] for r in run_results]),
                "std_makespan": np.std([r["makespan"] for r in run_results]),
                "avg_setups": np.mean([r["setups"] for r in run_results]),
                "std_setups": np.std([r["setups"] for r in run_results]),
            }
        
        return results
