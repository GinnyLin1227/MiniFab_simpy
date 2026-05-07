"""
PettingZoo Environment
======================
多智能體並行環境實現
"""

from typing import Dict, Optional
import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

from minifab_sim_core_v2 import MiniFabSimCore


class MultiAgentMiniFabEnv(ParallelEnv):
    """
    MiniFab 多智能體並行環境 (PettingZoo)
    
    三個智能體:
    - lot_dispatcher: 批次調度員
    - operator: 操作員 (C1批處理)
    - taskexecuter: 運輸執行員 (OHT)
    """
    
    metadata = {
        "name": "multi_agent_minifab_v0",
        "render_modes": ["human"],
    }
    
    def __init__(
        self,
        max_lots: int = 84,
        decision_interval: float = 30.0,
        max_time: float = 20000.0,
        seed: int = 42,
        render_mode: Optional[str] = None,
    ):
        """
        初始化環境
        
        Args:
            max_lots: 最大批次數
            decision_interval: 決策時間間隔 (分鐘)
            max_time: 模擬最大時間 (分鐘)
            seed: 隨機種子
            render_mode: 渲染模式
        """
        super().__init__()
        
        self.possible_agents = ["lot_dispatcher", "operator", "taskexecuter","maintenance"]
        self.agents = self.possible_agents[:]
        
        self.max_lots = max_lots
        self.decision_interval = decision_interval
        self.max_time = max_time
        self.seed_value = seed
        self.render_mode = render_mode
        
        # 初始化模擬核心
        self.core = MiniFabSimCore(
            max_lots=max_lots,
            decision_interval=decision_interval,
            max_time=max_time,
            seed=seed,
        )
        
        # 定義觀測空間和動作空間
        obs_dim = len(self.core.get_observation_vector())
        self._observation_spaces = {
            agent: spaces.Box(low=0.0, high=np.inf, shape=(obs_dim,), dtype=np.float32)
            for agent in self.possible_agents
        }
        # 4. 對應 V2 核心的策略數量
        self._action_spaces = {
            "lot_dispatcher": spaces.Discrete(len(MiniFabSimCore.DISPATCHER_STRATEGIES)),
            "operator": spaces.Discrete(len(MiniFabSimCore.OPERATOR_STRATEGIES)),
            "taskexecuter": spaces.Discrete(len(MiniFabSimCore.TASKEXECUTER_STRATEGIES)),
            "maintenance": spaces.Discrete(len(MiniFabSimCore.MAINTENANCE_STRATEGIES)),
        }
    
    def observation_space(self, agent):
        """獲取指定智能體的觀測空間"""
        return self._observation_spaces[agent]
    
    def action_space(self, agent):
        """獲取指定智能體的動作空間"""
        return self._action_spaces[agent]
    
    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        """
        重置環境
        
        Returns:
            observations: 字典，鍵為智能體名稱，值為觀測向量
            infos: 字典，鍵為智能體名稱，值為額外信息
        """
        if seed is not None:
            self.seed_value = seed
        
        self.agents = self.possible_agents[:]
        self.core = MiniFabSimCore(
            max_lots=self.max_lots,
            decision_interval=self.decision_interval,
            max_time=self.max_time,
            seed=self.seed_value,
        )
        
        obs_vec = self.core.get_observation_vector()
        observations = {agent: obs_vec.copy() for agent in self.agents}
        infos = {agent: {} for agent in self.agents}
        
        return observations, infos
    
    def step(self, actions: Dict[str, int]):
        """
        環境步進
        
        Args:
            actions: 字典，鍵為智能體名稱，值為動作索引
        
        Returns:
            observations: 新的觀測
            rewards: 獎勵
            terminations: 終止信號
            truncations: 超時信號
            infos: 額外信息
        """
        if not self.agents:
            return {}, {}, {}, {}, {}
        
        # 設置動作並執行模擬
        self.core.set_joint_actions(actions)
        self.core.run_for_interval()
        
        # 計算獎勵
        reward = self.core.compute_reward_delta()
        done = self.core.is_done()
        
        # 獲取新觀測
        obs_vec = self.core.get_observation_vector()
        
        # 為所有智能體構建返回值
        observations = {agent: obs_vec.copy() for agent in self.agents}
        rewards = {agent: reward for agent in self.agents}
        terminations = {agent: done for agent in self.agents}
        truncations = {agent: False for agent in self.agents}
        
        infos = {
            agent: {
                "time": self.core.env.now,
                "finished_lots": len(self.core.finished_lots),
            }
            for agent in self.agents
        }
        
        # 完成後清空智能體列表
        if done:
            self.agents = []
        
        return observations, rewards, terminations, truncations, infos
    
    def render(self):
        """渲染環境狀態"""
        report = self.core.final_report()
        print(
            f"time={self.core.env.now:.1f}, "
            f"finished={report['finished_lots']}, "
            f"makespan_hr={report['makespan_hr']:.2f}, "
            f"setup={report['setup_count']}"
        )
    
    def close(self):
        """關閉環境"""
        pass
    
    def get_report(self):
        """獲取模擬最終報告"""
        return self.core.final_report()
