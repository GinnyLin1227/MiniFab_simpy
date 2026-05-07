"""
Evolution Strategies (ES) Trainer
==================================

演化策略訓練器 - 使用跟同儕（其他突變的網路模型）比較，而不是標準答案

核心思想：
1. 維護一個種族 (population) 的策略網路
2. 每一代評估所有個體相對於同儕的表現
3. 適應度 = 在同儕對手中的勝率
4. 通過自然選擇和突變演化下一代
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
import copy
import json
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class PolicyIndividual:
    """策略個體"""
    individual_id: int
    generation: int
    weights: np.ndarray  # 神經網路權重
    fitness: float = 0.0  # 適應度（相對於同儕）
    wins: int = 0  # 勝場數
    losses: int = 0  # 負場數
    mean_reward: float = 0.0  # 平均獎勵
    parent_id: Optional[int] = None  # 父代ID
    mutation_std: float = 0.1  # 突變標準差
    creation_time: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """轉換為可序列化的字典"""
        return {
            "individual_id": self.individual_id,
            "generation": self.generation,
            "fitness": float(self.fitness),
            "wins": self.wins,
            "losses": self.losses,
            "mean_reward": float(self.mean_reward),
            "parent_id": self.parent_id,
            "mutation_std": float(self.mutation_std),
            "creation_time": self.creation_time,
        }


class PolicyNetwork:
    """簡單的策略網路 (1層隱層)"""
    
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int, seed: int = 42):
        """
        初始化網路
        
        Args:
            input_dim: 輸入維度 (特徵維度)
            hidden_dim: 隱層維度
            output_dim: 輸出維度 (動作數)
        """
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.rng = np.random.RandomState(seed)
        
        # 初始化權重
        self.w1 = self.rng.randn(input_dim, hidden_dim) * 0.01
        self.b1 = np.zeros(hidden_dim)
        self.w2 = self.rng.randn(hidden_dim, output_dim) * 0.01
        self.b2 = np.zeros(output_dim)
    
    def forward(self, x: np.ndarray) -> np.ndarray:
        """前向傳播"""
        # x shape: (batch_size, input_dim) or (input_dim,)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        
        # 隱層 + ReLU
        h = np.dot(x, self.w1) + self.b1
        h = np.maximum(0, h)
        
        # 輸出層 (softmax用於策略)
        logits = np.dot(h, self.w2) + self.b2
        
        # Softmax
        exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
        
        return probs
    
    def get_action(self, x: np.ndarray) -> int:
        """獲取動作 (最高概率)"""
        probs = self.forward(x)
        action = np.argmax(probs[0])
        return action
    
    def get_weights(self) -> np.ndarray:
        """獲取所有權重（展平）"""
        weights = np.concatenate([
            self.w1.flatten(),
            self.b1.flatten(),
            self.w2.flatten(),
            self.b2.flatten(),
        ])
        return weights
    
    def set_weights(self, weights: np.ndarray):
        """設置權重"""
        idx = 0
        
        # w1
        w1_size = self.input_dim * self.hidden_dim
        self.w1 = weights[idx:idx+w1_size].reshape(self.input_dim, self.hidden_dim)
        idx += w1_size
        
        # b1
        b1_size = self.hidden_dim
        self.b1 = weights[idx:idx+b1_size]
        idx += b1_size
        
        # w2
        w2_size = self.hidden_dim * self.output_dim
        self.w2 = weights[idx:idx+w2_size].reshape(self.hidden_dim, self.output_dim)
        idx += w2_size
        
        # b2
        self.b2 = weights[idx:]


class EvolutionStrategies:
    """演化策略訓練器"""
    
    def __init__(
        self,
        input_dim: int = 12,  # 特徵維度
        hidden_dim: int = 64,
        output_dim: int = 4,  # 動作數
        population_size: int = 20,
        elite_size: int = 4,
        mutation_std: float = 0.1,
        seed: int = 42,
    ):
        """
        初始化ES訓練器
        
        Args:
            input_dim: 輸入特徵維度
            hidden_dim: 隱層維度
            output_dim: 輸出動作數
            population_size: 種族大小
            elite_size: 精英個體數
            mutation_std: 初始突變標準差
            seed: 隨機種子
        """
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.population_size = population_size
        self.elite_size = elite_size
        self.mutation_std = mutation_std
        self.rng = np.random.RandomState(seed)
        
        self.generation = 0
        self.individual_counter = 0
        
        # 初始化種族
        self.population: List[PolicyIndividual] = []
        self._initialize_population()
        
        # 統計信息
        self.generation_stats = []
        self.battle_records = []  # 戰鬥結果記錄
    
    def _initialize_population(self):
        """初始化種族"""
        for i in range(self.population_size):
            network = PolicyNetwork(
                self.input_dim,
                self.hidden_dim,
                self.output_dim,
                seed=self.rng.randint(0, 10000),
            )
            
            individual = PolicyIndividual(
                individual_id=self.individual_counter,
                generation=0,
                weights=network.get_weights(),
                fitness=0.0,
                mutation_std=self.mutation_std,
                creation_time=datetime.now().isoformat(),
            )
            
            self.population.append(individual)
            self.individual_counter += 1
    
    def evaluate_population(
        self,
        evaluate_fn,  # function(policy_network) -> reward
        num_trials: int = 3,
    ) -> Dict:
        """
        評估整個種族
        
        跟同儕比較的邏輯：
        - 每個個體與其他個體進行戰鬥
        - 適應度 = 勝率 + 平均獎勵
        
        Args:
            evaluate_fn: 評估函數，接收網路和對手網路，返回自我獎勵
            num_trials: 每對對手的試驗次數
        
        Returns:
            評估統計信息
        """
        # 重置適應度
        for ind in self.population:
            ind.fitness = 0.0
            ind.wins = 0
            ind.losses = 0
            ind.mean_reward = 0.0
        
        total_battles = 0
        
        # 相對評估：每個個體 vs 其他個體
        for i, individual in enumerate(self.population):
            individual_rewards = []
            
            for j, opponent in enumerate(self.population):
                if i == j:
                    continue
                
                # 執行num_trials次戰鬥
                for trial in range(num_trials):
                    # 建立網路
                    my_network = self._create_network(individual.weights)
                    opp_network = self._create_network(opponent.weights)
                    
                    # 評估（簡化：直接比較回合獎勵）
                    my_reward = self._simulate_match(my_network, opp_network)
                    
                    individual_rewards.append(my_reward)
                    total_battles += 1
                    
                    # 記錄戰鬥結果
                    if my_reward >= 0:
                        individual.wins += 1
                    else:
                        individual.losses += 1
                    
                    self.battle_records.append({
                        "generation": self.generation,
                        "individual_a": individual.individual_id,
                        "individual_b": opponent.individual_id,
                        "reward_a": float(my_reward),
                    })
            
            # 計算適應度
            if individual_rewards:
                individual.mean_reward = np.mean(individual_rewards)
                # 適應度 = 標準化獎勵 + 勝率
                win_rate = individual.wins / max(individual.wins + individual.losses, 1)
                individual.fitness = individual.mean_reward + win_rate * 100
        
        # 統計信息
        stats = {
            "generation": self.generation,
            "population_size": len(self.population),
            "total_battles": total_battles,
            "best_fitness": max(ind.fitness for ind in self.population),
            "mean_fitness": np.mean([ind.fitness for ind in self.population]),
            "worst_fitness": min(ind.fitness for ind in self.population),
            "best_individual": max(self.population, key=lambda x: x.fitness).individual_id,
        }
        
        self.generation_stats.append(stats)
        return stats
    
    def evolve(self) -> List[PolicyIndividual]:
        """
        演化下一代
        
        步驟：
        1. 選擇精英個體
        2. 通過突變產生後代
        3. 返回新種族
        """
        # 1. 按適應度排序
        sorted_pop = sorted(self.population, key=lambda x: x.fitness, reverse=True)
        
        # 2. 選擇精英
        elite = sorted_pop[:self.elite_size]
        
        # 3. 產生後代（突變+重組）
        new_population = []
        
        # 精英直接進入下一代
        for elite_ind in elite:
            new_ind = copy.deepcopy(elite_ind)
            new_ind.generation = self.generation + 1
            new_population.append(new_ind)
        
        # 填補剩餘種族
        while len(new_population) < self.population_size:
            # 從精英中隨機選擇父代
            parent = self.rng.choice(elite)
            
            # 突變
            mutated_weights = self._mutate(parent.weights, parent.mutation_std)
            
            # 自適應變異速率 (簡單策略：好個體降低變異率)
            new_mutation_std = parent.mutation_std * (0.95 if parent.fitness > np.median([ind.fitness for ind in self.population]) else 1.05)
            
            child = PolicyIndividual(
                individual_id=self.individual_counter,
                generation=self.generation + 1,
                weights=mutated_weights,
                fitness=0.0,
                parent_id=parent.individual_id,
                mutation_std=new_mutation_std,
                creation_time=datetime.now().isoformat(),
            )
            
            new_population.append(child)
            self.individual_counter += 1
        
        self.population = new_population[:self.population_size]
        self.generation += 1
        
        return self.population
    
    def _mutate(self, weights: np.ndarray, std: float) -> np.ndarray:
        """
        突變操作
        
        Args:
            weights: 當前權重
            std: 高斯噪聲標準差
        
        Returns:
            突變後的權重
        """
        noise = self.rng.randn(*weights.shape) * std
        mutated = weights + noise
        return mutated
    
    def _create_network(self, weights: np.ndarray) -> PolicyNetwork:
        """根據權重創建網路"""
        network = PolicyNetwork(
            self.input_dim,
            self.hidden_dim,
            self.output_dim,
        )
        network.set_weights(weights)
        return network
    
    def _simulate_match(self, network_a: PolicyNetwork, network_b: PolicyNetwork) -> float:
        """
        模擬兩個策略的對戰
        
        Args:
            network_a: 策略A
            network_b: 策略B (對手)
        
        Returns:
            策略A的相對獎勵 (正數表示勝，負數表示負)
        """
        # 簡化實現：隨機生成特徵並比較動作選擇
        dummy_features = self.rng.randn(self.input_dim)
        
        # 獲取動作
        action_a = network_a.get_action(dummy_features)
        action_b = network_b.get_action(dummy_features)
        
        # 簡單評估：動作接近 dummy_features 的最高維度者更優
        best_action = np.argmax(dummy_features)
        
        reward_a = 1.0 if action_a == best_action else -0.5
        reward_a += 0.1 if action_a != action_b else 0.0  # 鼓勵多樣性
        
        return reward_a
    
    def get_best_policy(self) -> PolicyIndividual:
        """獲取當前最佳策略"""
        return max(self.population, key=lambda x: x.fitness)
    
    def get_population_snapshot(self) -> List[Dict]:
        """獲取種族快照"""
        return [ind.to_dict() for ind in self.population]
    
    def save_checkpoint(self, filepath: str):
        """保存檢查點"""
        checkpoint = {
            "generation": self.generation,
            "population": self.get_population_snapshot(),
            "generation_stats": self.generation_stats,
            "battle_records": self.battle_records[-1000:],  # 保留最近1000場戰鬥
        }
        
        with open(filepath, 'w') as f:
            json.dump(checkpoint, f, indent=2)
    
    def load_checkpoint(self, filepath: str):
        """載入檢查點"""
        with open(filepath, 'r') as f:
            checkpoint = json.load(f)
        
        self.generation = checkpoint["generation"]
        self.generation_stats = checkpoint["generation_stats"]
        
        # 重建種族
        self.population = []
        for ind_dict in checkpoint["population"]:
            ind = PolicyIndividual(
                individual_id=ind_dict["individual_id"],
                generation=ind_dict["generation"],
                weights=np.zeros(1),  # 實際應載入權重
                fitness=ind_dict["fitness"],
                wins=ind_dict["wins"],
                losses=ind_dict["losses"],
                mean_reward=ind_dict["mean_reward"],
                parent_id=ind_dict["parent_id"],
                mutation_std=ind_dict["mutation_std"],
                creation_time=ind_dict["creation_time"],
            )
            self.population.append(ind)
