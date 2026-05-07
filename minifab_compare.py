"""
Comparison and Benchmark Module
================================
不同策略的對比和基準測試
"""

import os

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import json


class StrategyComparator:
    """策略比較器"""
    
    def __init__(self, env):
        """
        初始化比較器
        
        Args:
            env: PettingZoo環境
        """
        self.env = env
        self.results = {}
    
    def run_strategy(
        self,
        dispatcher_strategy: str,
        operator_strategy: str,
        taskexecuter_strategy: str,
        maintenance_strategy: str = "status_first",
        num_runs: int = 5,
        seed_offset: int = 0
    ) -> Dict:
        """
        運行指定策略配置
        
        Args:
            dispatcher_strategy: 調度員策略名稱
            operator_strategy: 操作員策略名稱
            taskexecuter_strategy: 運輸執行員策略名稱
            maintenance_strategy: 維護策略名稱
            num_runs: 運行次數
            seed_offset: 種子偏移量
        
        Returns:
            性能統計
        """
        from minifab_env2 import MultiAgentMiniFabEnv
        
        metrics = {
            "makespan": [],
            "avg_tpt": [],
            "setup_count": [],
            "finished_lots": [],
            "ma_util": [],
            "mb_util": [],
            "me_util": [],
            "mc_util": [],
            "md_util": [],
        }
        
        for run in range(num_runs):
            env = MultiAgentMiniFabEnv(
                max_lots=84,
                decision_interval=30.0,
                max_time=20000.0,
                seed=42 + run + seed_offset,
            )
            
            obs, _ = env.reset(seed=42 + run + seed_offset)
            done = False
            step = 0
            
            # 獲取策略索引
            dispatcher_idx = env.core.DISPATCHER_STRATEGIES.index(dispatcher_strategy)
            operator_idx = env.core.OPERATOR_STRATEGIES.index(operator_strategy)
            taskexecuter_idx = env.core.TASKEXECUTER_STRATEGIES.index(taskexecuter_strategy)
            maintenance_idx = env.core.MAINTENANCE_STRATEGIES.index(maintenance_strategy)
            # 執行模擬
            while not done and step < 100:
                actions = {
                    "lot_dispatcher": dispatcher_idx,
                    "operator": operator_idx,
                    "taskexecuter": taskexecuter_idx,
                    "maintenance": maintenance_idx,
                }
                
                obs, rewards, terminations, truncations, _ = env.step(actions)
                done = any(terminations.values()) or any(truncations.values())
                step += 1
            
            # 收集指標
            report = env.get_report()
            metrics["makespan"].append(report["makespan_min"])
            metrics["avg_tpt"].append(report["avg_tpt_min"])
            metrics["setup_count"].append(report["setup_count"])
            metrics["finished_lots"].append(report["finished_lots"])
            
            for machine in ["Ma", "Mb", "Me", "Mc", "Md"]:
                metrics[f"{machine.lower()}_util"].append(report["machine_util"][machine])
            
            env.close()
        
        # 計算統計
        stats = {}
        for key, values in metrics.items():
            stats[f"{key}_mean"] = float(np.mean(values))
            stats[f"{key}_std"] = float(np.std(values))
            stats[f"{key}_min"] = float(np.min(values))
            stats[f"{key}_max"] = float(np.max(values))
        
        return stats
    
    def compare_all_strategies(self, num_runs: int = 3) -> pd.DataFrame:
        """
        比較所有策略組合
        
        Args:
            num_runs: 每個組合的運行次數
        
        Returns:
            比較結果表格
        """
        from minifab_sim_core_v2 import MiniFabSimCore
        
        dispatcher_strategies = MiniFabSimCore.DISPATCHER_STRATEGIES
        operator_strategies = MiniFabSimCore.OPERATOR_STRATEGIES
        taskexecuter_strategies = MiniFabSimCore.TASKEXECUTER_STRATEGIES
        
        results = []
        total = len(dispatcher_strategies) * len(operator_strategies) * len(taskexecuter_strategies)
        count = 0
        
        for d_strategy in dispatcher_strategies:
            for o_strategy in operator_strategies:
                for t_strategy in taskexecuter_strategies:
                    count += 1
                    print(f"Running {count}/{total}: "
                          f"D={d_strategy}, O={o_strategy}, T={t_strategy}")
                    
                    stats = self.run_strategy(
                        d_strategy,
                        o_strategy,
                        t_strategy,
                        maintenance_strategy="status_first",
                        num_runs=num_runs
                    )
                    
                    stats["dispatcher"] = d_strategy
                    stats["operator"] = o_strategy
                    stats["taskexecuter"] = t_strategy
                    stats["maintenance"] = "status_first"
                    
                    results.append(stats)
        
        df = pd.DataFrame(results)
        self.results = df
        return df
    
    def find_best_strategies(self, metric: str = "makespan_mean") -> Dict:
        """
        找出最佳策略
        
        Args:
            metric: 優化指標
        
        Returns:
            最佳策略配置
        """
        if self.results.empty:
            raise ValueError("No results available. Run compare_all_strategies first.")
        
        best_idx = self.results[metric].idxmin()
        best_config = self.results.iloc[best_idx]
        
        return {
            "dispatcher": best_config["dispatcher"],
            "operator": best_config["operator"],
            "taskexecuter": best_config["taskexecuter"],
            "maintenance": best_config.get("maintenance", "status_first"),
            "metrics": {k: v for k, v in best_config.items() 
                       if not isinstance(v, str)},
        }
    
    def export_results(self, filepath: str):
        """導出結果到CSV"""
        directory = os.path.dirname(filepath)
        
        # 2. 核心！如果資料夾不存在，就讓 Python 自動建立它
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        
        self.results.to_csv(filepath, index=False) 
        print(f"Results exported to {filepath}")


class BenchmarkSuite:
    """基準測試套件"""
    
    def __init__(self, env):
        """初始化基準測試"""
        self.env = env
        self.benchmarks = {}
    
    def baseline_random(self, num_runs: int = 10) -> Dict:
        """
        隨機策略基線
        
        Args:
            num_runs: 運行次數
        
        Returns:
            基線統計
        """
        metrics = {
            "makespan": [],
            "avg_tpt": [],
            "setup_count": [],
        }
        
        for run in range(num_runs):
            from minifab_env2 import MultiAgentMiniFabEnv
            
            env = MultiAgentMiniFabEnv(seed=42 + run)
            obs, _ = env.reset(seed=42 + run)
            done = False
            step = 0
            
            while not done and step < 100:
                actions = {
                    agent: env.action_space(agent).sample()
                    for agent in env.agents
                }
                obs, rewards, terminations, truncations, _ = env.step(actions)
                done = any(terminations.values()) or any(truncations.values())
                step += 1
            
            report = env.get_report()
            metrics["makespan"].append(report["makespan_min"])
            metrics["avg_tpt"].append(report["avg_tpt_min"])
            metrics["setup_count"].append(report["setup_count"])
            
            env.close()
        
        baseline = {
            "makespan_mean": float(np.mean(metrics["makespan"])),
            "makespan_std": float(np.std(metrics["makespan"])),
            "avg_tpt_mean": float(np.mean(metrics["avg_tpt"])),
            "setup_mean": float(np.mean(metrics["setup_count"])),
        }
        
        self.benchmarks["random"] = baseline
        return baseline
    
    def baseline_fifo(self, num_runs: int = 10) -> Dict:
        """
        FIFO策略基線 (所有FIFO)
        
        Args:
            num_runs: 運行次數
        
        Returns:
            基線統計
        """
        comparator = StrategyComparator(self.env)
        stats = comparator.run_strategy(
            "fifo",
            "fifo",
            "fifo",
            "status_first",
            num_runs=num_runs
        )
        
        baseline = {
            "makespan_mean": stats["makespan_mean"],
            "makespan_std": stats["makespan_std"],
            "avg_tpt_mean": stats["avg_tpt_mean"],
            "setup_mean": stats["setup_count_mean"],
        }
        
        self.benchmarks["fifo"] = baseline
        return baseline
    
    def get_all_baselines(self) -> Dict:
        """獲取所有基線"""
        return self.benchmarks
    
    def compare_to_baseline(self, new_result: dict, baseline_name: str = "fifo") -> dict:
        """
        與基線比較
        
        Args:
            new_result: 新結果
            baseline_name: 基線名稱
        
        Returns:
            改進情況
        """
        if baseline_name not in self.benchmarks:
            raise ValueError(f"Baseline '{baseline_name}' not found.")
        
        baseline = self.benchmarks[baseline_name]
        
        # 建立安全計算函式，避免分母為 0
        def safe_calc(base_val, new_val):
            # 如果基線數值為 0 或不存在，直接回傳 0.0 避免報錯
            if not base_val:
                return 0.0
            return (base_val - new_val) / base_val * 100

        improvement = {
            "makespan_improvement": safe_calc(
                baseline.get("makespan_mean", 0), 
                new_result.get("makespan_mean", 0)
            ),
            "avg_tpt_improvement": safe_calc(
                baseline.get("avg_tpt_mean", 0), 
                new_result.get("avg_tpt_mean", 0)
            ),
            "setup_improvement": safe_calc(
                baseline.get("setup_mean", 0), 
                new_result.get("setup_count_mean", 0)
            ),
        }
        
        return improvement


class PerformanceAnalyzer:
    """性能分析器"""
    
    @staticmethod
    def compute_efficiency_metrics(report: Dict) -> Dict:
        """
        計算效率指標
        
        Args:
            report: 模擬報告
        
        Returns:
            效率指標
        """
        makespan = report["makespan_min"]
        
        # 機器利用率加權平均
        total_util = sum(report["machine_util"].values()) / len(report["machine_util"])
        
        # 效率指標
        efficiency = {
            "makespan_min": makespan,
            "makespan_hr": makespan / 60,
            "avg_tpt_min": report["avg_tpt_min"],
            "machine_util_avg": total_util,
            "setup_count": report["setup_count"],
            "finished_lots": report["finished_lots"],
            "setup_per_lot": (
                report["setup_count"] / report["finished_lots"] 
                if report["finished_lots"] > 0 else 0
            ),
        }
        
        return efficiency
    
    @staticmethod
    def compute_robustness(results: List[Dict]) -> Dict:
        """
        計算鯁健性指標
        
        Args:
            results: 多次運行結果列表
        
        Returns:
            鯁健性指標
        """
        makespans = [r["makespan_min"] for r in results if "makespan_min" in r]
        
        robustness = {
            "mean_makespan": float(np.mean(makespans)),
            "std_makespan": float(np.std(makespans)),
            "cv_makespan": float(np.std(makespans) / np.mean(makespans)) if np.mean(makespans) > 0 else 0,
            "min_makespan": float(np.min(makespans)),
            "max_makespan": float(np.max(makespans)),
        }
        
        return robustness
    
    @staticmethod
    def analyze_tradeoffs(
        results_df: pd.DataFrame,
        metrics: List[str] = ["makespan_mean", "setup_count_mean"]
    ) -> Dict:
        """
        分析指標間的權衡
        
        Args:
            results_df: 結果數據框
            metrics: 要分析的指標
        
        Returns:
            權衡分析
        """
        analysis = {}
        
        for metric in metrics:
            if metric in results_df.columns:
                values = results_df[metric].values
                normalized = (values - np.min(values)) / (np.max(values) - np.min(values))
                
                analysis[metric] = {
                    "mean": float(np.mean(values)),
                    "std": float(np.std(values)),
                    "min": float(np.min(values)),
                    "max": float(np.max(values)),
                    "normalized_mean": float(np.mean(normalized)),
                }
        
        return analysis
    
    @staticmethod
    def identify_pareto_front(
        results_df: pd.DataFrame,
        objectives: List[Tuple[str, str]]
    ) -> pd.DataFrame:
        """
        識別帕累托前沿
        
        Args:
            results_df: 結果數據框
            objectives: 目標列表，格式為 (指標名, '最小化'或'最大化')
        
        Returns:
            帕累托最優解
        """
        df = results_df.copy()
        
        # 標記非支配解
        is_pareto = np.ones(len(df), dtype=bool)
        
        for i in range(len(df)):
            for j in range(len(df)):
                if i == j:
                    continue
                
                dominates = True
                for metric, direction in objectives:
                    if direction == "minimize":
                        if df.iloc[j][metric] >= df.iloc[i][metric]:
                            dominates = False
                            break
                    else:  # maximize
                        if df.iloc[j][metric] <= df.iloc[i][metric]:
                            dominates = False
                            break
                
                if dominates:
                    is_pareto[i] = False
                    break
        
        return df[is_pareto]
