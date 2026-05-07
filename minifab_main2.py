"""
Main Execution Script
=====================
MiniFab環境的主執行腳本，包含範例和測試
"""

import sys
import argparse
import pandas as pd
import numpy as np
from minifab_env2 import MultiAgentMiniFabEnv
from minifab_rl import RLTrainer, PolicyAnalyzer
from minifab_compare import StrategyComparator, BenchmarkSuite, PerformanceAnalyzer


def test_random_policy(num_episodes: int = 5):
    """
    測試隨機策略
    
    Args:
        num_episodes: 測試回合數
    """
    print("=" * 60)
    print("TEST: Random Policy")
    print("=" * 60)
    
    env = MultiAgentMiniFabEnv(
        max_lots=84,
        decision_interval=30.0,
        max_time=20000.0,
        seed=42,
    )
    
    results = []
    
    for episode in range(num_episodes):
        observations, infos = env.reset()
        done = False
        step = 0
        
        while not done and step < 100:
            actions = {
                agent: env.action_space(agent).sample()
                for agent in env.agents
            }
            
            observations, rewards, terminations, truncations, infos = env.step(actions)
            done = any(terminations.values()) or any(truncations.values())
            step += 1
        
        report = env.get_report()
        results.append({
            "episode": episode,
            "makespan_min": report["makespan_min"],
            "avg_tpt_min": report["avg_tpt_min"],
            "setup_count": report["setup_count"],
            "finished_lots": report["finished_lots"],
        })
        
        print(f"Episode {episode}: "
              f"Makespan={report['makespan_min']:.1f} min, "
              f"Setup={report['setup_count']}, "
              f"Finished={report['finished_lots']}")
    
    env.close()
    
    print(f"\nAverage Makespan: {np.mean([r['makespan_min'] for r in results]):.1f} min")
    print(f"Average Setup Count: {np.mean([r['setup_count'] for r in results]):.1f}")


def test_fifo_policy(num_episodes: int = 5):
    """
    測試貪心策略 (全FIFO)
    
    Args:
        num_episodes: 測試回合數
    """
    print("\n" + "=" * 60)
    print("TEST: Greedy Policy (FIFO)")
    print("=" * 60)
    
    env = MultiAgentMiniFabEnv(
        max_lots=84,
        decision_interval=30.0,
        max_time=20000.0,
        seed=42,
    )
    
    results = []
    
    for episode in range(num_episodes):
        observations, infos = env.reset()
        done = False
        step = 0
        
        # 固定策略：所有FIFO
        actions_fixed = {
            "lot_dispatcher": 0,  # fifo
            "operator": 0,        # fifo
            "taskexecuter": 0,    # fifo
            "maintenance": 0,      # no-op
        }
        
        while not done and step < 100:
            observations, rewards, terminations, truncations, infos = env.step(actions_fixed)
            done = any(terminations.values()) or any(truncations.values())
            step += 1
        
        report = env.get_report()
        results.append({
            "episode": episode,
            "makespan_min": report["makespan_min"],
            "avg_tpt_min": report["avg_tpt_min"],
            "setup_count": report["setup_count"],
            "finished_lots": report["finished_lots"],
        })
        
        print(f"Episode {episode}: "
              f"Makespan={report['makespan_min']:.1f} min, "
              f"Setup={report['setup_count']}, "
              f"Finished={report['finished_lots']}")
    
    env.close()
    
    print(f"\nAverage Makespan: {np.mean([r['makespan_min'] for r in results]):.1f} min")
    print(f"Average Setup Count: {np.mean([r['setup_count'] for r in results]):.1f}")


def compare_strategies(num_runs: int = 3):
    """
    比較所有策略組合
    
    Args:
        num_runs: 每個組合的運行次數
    """
    print("\n" + "=" * 60)
    print("COMPARISON: All Strategy Combinations")
    print("=" * 60)
    
    env = MultiAgentMiniFabEnv()
    comparator = StrategyComparator(env)
    
    print(f"Comparing {4 * 4 * 5} strategy combinations with {num_runs} runs each...")
    results_df = comparator.compare_all_strategies(num_runs=num_runs)
    
    # 找最佳策略
    best = comparator.find_best_strategies(metric="makespan_mean")
    print("\nBest Strategy (by makespan):")
    print(f"  Dispatcher: {best['dispatcher']}")
    print(f"  Operator: {best['operator']}")
    print(f"  TaskExecuter: {best['taskexecuter']}")
    print(f"  Makespan: {best['metrics']['makespan_mean']:.1f} ± {best['metrics']['makespan_std']:.1f} min")
    
    # 導出結果
    comparator.export_results("./outputs/strategy_comparison.csv")
    print("\nResults exported to strategy_comparison.csv")


def train_rl_policy(num_episodes: int = 100):
    """
    訓練強化學習策略
    
    Args:
        num_episodes: 訓練回合數
    """
    print("\n" + "=" * 60)
    print("TRAINING: RL Policy")
    print("=" * 60)
    
    env = MultiAgentMiniFabEnv(
        max_lots=84,
        decision_interval=30.0,
        max_time=20000.0,
        seed=42,
    )
    
    trainer = RLTrainer(
        env,
        agent_names=["lot_dispatcher", "operator", "taskexecuter"],
        learning_rate=0.01,
        gamma=0.99,
        epsilon=1.0,
        epsilon_decay=0.995,
    )
    
    print(f"Training for {num_episodes} episodes...")
    training_results = trainer.train(num_episodes=num_episodes, render_freq=20)
    
    # 評估訓練後的策略
    print("\nEvaluating trained policy...")
    eval_results = trainer.evaluate(num_episodes=10)
    
    print("\nEvaluation Results:")
    print(f"  Avg Episode Reward: {eval_results['avg_episode_reward']:.2f}")
    print(f"  Avg Makespan: {eval_results['avg_makespan']:.1f} ± {eval_results['std_makespan']:.1f} min")
    print(f"  Avg Setup Count: {eval_results['avg_setups']:.1f}")
    
    # 保存Q表
    trainer.save_q_tables("./outputs/q_tables.json")
    print("\nQ-tables saved to q_tables.json")
    
    env.close()
    
    return trainer


def benchmark_suite_test():
    """
    運行完整基準測試
    """
    print("\n" + "=" * 60)
    print("BENCHMARK: Complete Test Suite")
    print("=" * 60)
    
    env = MultiAgentMiniFabEnv()
    suite = BenchmarkSuite(env)
    
    print("Generating random policy baseline...")
    random_baseline = suite.baseline_random(num_runs=5)
    print(f"  Random Makespan: {random_baseline['makespan_mean']:.1f} min")
    
    print("Generating Fifo policy baseline...")
    fifo_baseline = suite.baseline_fifo(num_runs=5)
    print(f"  Fifo Makespan: {fifo_baseline['makespan_mean']:.1f} min")
    
    # 分析改進
    improvement = suite.compare_to_baseline(fifo_baseline, "random")
    print(f"\nFifo vs Random Improvement:")
    print(f"  Makespan: {improvement['makespan_improvement']:.2f}%")
    print(f"  Avg TPT: {improvement['avg_tpt_improvement']:.2f}%")


def main():
    """主函數"""
    parser = argparse.ArgumentParser(description="MiniFab Multi-Agent Environment Test Suite")
    parser.add_argument(
        "--test",
        choices=["random", "fifo", "compare", "train", "benchmark", "all"],
        default="all",
        help="Select which test to run"
    )
    parser.add_argument("--episodes", type=int, default=5, help="Number of episodes")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per test")
    
    args = parser.parse_args()
    
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " MiniFab Multi-Agent Manufacturing Simulation ".center(58) + "║")
    print("║" + " Test & Evaluation Suite ".center(58) + "║")
    print("╚" + "=" * 58 + "╝")
    
    if args.test in ["random", "all"]:
        test_random_policy(num_episodes=args.episodes)
    
    if args.test in ["fifo", "all"]:
        test_fifo_policy(num_episodes=args.episodes)
    
    if args.test in ["compare", "all"]:
        compare_strategies(num_runs=args.runs)
    
    if args.test in ["train", "all"]:
        train_rl_policy(num_episodes=args.episodes)
    
    if args.test in ["benchmark", "all"]:
        benchmark_suite_test()
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
