"""
MiniFab Simulation Core v2
===========================
改進的DES (Discrete Event Simulation) 核心
- 每個Agent擁有各自的任務池
- 實現更完善的策略決策邏輯
- 增強的維護和故障管理
"""

import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
import simpy

from minifab_config import (
    PROCESS_FLOW, PROCESS_TIME, STEP_TO_CELL, CELL_MACHINES,
    MACHINE_STEPS, MACHINE_CELL, BUFFER_CAPACITY, PRODUCT_MIX,
    CELL_DISTANCE, TRANSPORT_LOAD, TRANSPORT_UNLOAD, REWARD_WEIGHTS
)
from minifab_datastructures import Lot, MachineState, TransportTask


# ========== 任務定義 ==========

@dataclass
class DispatchTask:
    """派工任務"""
    lot: Lot
    priority: float = 0.0  # 優先級（用於排序）
    created_time: float = 0.0


@dataclass
class OperatorTask:
    """操作員任務"""
    lot: Lot
    machine_name: str
    step: str
    priority: float = 0.0
    created_time: float = 0.0


@dataclass
class TransportTask:
    """運輸任務 (增強版)"""
    lot: Lot
    from_location: str
    to_location: str
    ready_time: float = 0.0
    priority: float = 0.0
    wait_time: float = 0.0  # 追蹤等待時間


@dataclass
class MaintenanceTask:
    """維護任務"""
    machine: str
    task_type: str  # "PM" or "EM"
    duration: float
    priority: float
    created_time: float = 0.0


class MiniFabSimCore:
    """
    改進版PettingZoo環境的離散事件模擬核心
    
    Agent任務池:
        - lot_dispatcher: DispatchTask池
        - operator: OperatorTask池 (Op1 和 Op2分別管理)
        - taskexecuter: TransportTask池
        - maintenance: MaintenanceTask池
    
    主要接口:
        - reset()
        - set_joint_actions(actions: Dict[str, int])
        - run_for_interval()
        - get_observation()
        - compute_reward_delta()
        - is_done()
    """
    
    # ========== 策略定義 ==========
    
    DISPATCHER_STRATEGIES = [
        "fifo",  # 先進先出 (最早 ready 的優先)
        "spt",   # 最短加工時間優先 (Shortest Processing Time)
        "lwt",  # 最長等待時間優先 (Longest Waiting Time)  
        "hold_if_full",  #   如果 downstream 要運送到的地方 滿了就Hold，否則Push 
    ]
    
    OPERATOR_STRATEGIES = [
        "fifo",               # 先進先出
        "spt",                # 最短加工時間優先 (Shortest Processing Time)
        "lwt",                # 最長等待時間優先 (Longest Waiting Time)
        "shortest_distance",  # 距離優先：操作員當前位置與機台的距離
    ]
    
    TASKEXECUTER_STRATEGIES = [
        "fifo",                   # FIFO運輸
        "lowest_workload",        # 剩餘工時最短優先：目標 Cell 的堆積貨物數 * 加工時間
        "shortest_travel",        # 距離優先
    ]
    
    MAINTENANCE_STRATEGIES = [
        "status_first",      # 狀態優先：EM 絕對優先於 PM
        "bottleneck_first",  # 瓶頸優先：Me > Ma > Mc > Mb = Md
        "load_aware",        # 產線水位：上游少、下游多的優先
    ]
    
    def __init__(
        self,
        max_lots: int = 84,
        decision_interval: float = 30.0,  # 每30分鐘決策一次
        max_time: float = 200000.0,  # hour 最大模擬時間約333小時
        seed: int = 42,
    ):
        self.max_lots = max_lots
        self.decision_interval = decision_interval
        self.max_time = max_time
        self.seed = seed
        self.rng = random.Random(seed)
        
        self.env = None
        self.reset()
    
    def reset(self):
        """重置模擬環境"""
        self.rng.seed(self.seed)
        self.env = simpy.Environment()
        
        # ========== 策略初始化 ==========
        self.dispatcher_strategy = "fifo"
        self.operator_strategy = "fifo"
        self.taskexecuter_strategy = "fifo"
        self.maintenance_strategy = "priority_first"
        
        # ========== Agent任務池 ==========
        
        # Agent 1: Dispatcher任務池
        self.dispatcher_task_pool: List[DispatchTask] = []
        
        # Agent 2: Operator任務池 (改為全域任務池以符合後續邏輯)
        self.operator_task_pool: List[OperatorTask] = []
        
        # Agent 3: TaskExecuter運輸任務池
        self.transport_task_pool: List[TransportTask] = []
        
        # Agent 4: Maintenance維護任務池
        self.maintenance_task_pool: List[MaintenanceTask] = []
        
        # ========== 人員與維修資源 ==========
        self.operators = {
            "Op1": simpy.Resource(self.env, capacity=1),
            "Op2": simpy.Resource(self.env, capacity=1)
        }
        self.mt1 = simpy.Resource(self.env, capacity=1)

        # ========== 機器資源 ==========
        self.machines = {
            name: simpy.PriorityResource(self.env, capacity=1)
            for name in ["Ma", "Mb", "Me", "Mc", "Md"]
        }
        
        self.machine_state = {
            name: MachineState(name=name)
            for name in self.machines
        }
        
        self.machine_busy_flags = {
            name: False for name in self.machines
        }
        
        # ========== 隊列管理 ==========
        self.cell_queues: Dict[str, List[Lot]] = {
            "C1": [],
            "C2": [],
            "C3": [],
        }
        
        # ========== 批次管理 ==========
        self.all_lots: List[Lot] = []
        self.finished_lots: List[Lot] = []
        
        # ========== 記錄 ==========
        self.event_log = []
        self.wip_log = []
        self.task_pool_log = []  # 追蹤任務池狀態
        
        # ========== OHT位置 ==========
        self.oht_location = "SOURCE"
        
        # ========== 維護追蹤 ==========
        self.last_pm_time = {m: 0.0 for m in self.machines}
        self.em_schedule = {
            "Mc": self.rng.gauss(50 * 60, 26 * 60),
            "Md": self.rng.gauss(50 * 60, 26 * 60)
        }
        
        # ========== 操作員狀態追蹤 ==========
        self.operator_location = {"Op1": "C1", "Op2": "C2"}  # 當前所在位置
        self.operator_assigned_machine = {"Op1": None, "Op2": None}  # 當前指派的機台
        
        # ========== 獎勵計算用變數 ==========
        self.prev_finished = 0
        self.prev_wip = 0
        self.prev_setup_count = 0
        self.prev_transport_wait = 0
        self.prev_time = 0.0
        
        # ========== 啟動主要流程 ==========
        self._create_lots()
        self.env.process(self.dispatcher_agent_process())
        self.env.process(self.operator_agent_process())
        self.env.process(self.taskexecuter_agent_process())
        self.env.process(self.maintenance_agent_process())
    
    # ========== 批次生成 ==========
    
    def _create_lots(self):
        """根據產品組合生成批次"""
        product_pool = []
        for p, count in PRODUCT_MIX.items():
            product_pool += [p] * count
        
        self.rng.shuffle(product_pool)
        for lot_id, product in enumerate(product_pool[:self.max_lots]):
            lot = Lot(
                lot_id=lot_id,
                product=product,
                start_time=0.0,
                ready_time=0.0,
                location="SOURCE",
            )
            self.all_lots.append(lot)
            self.event_log.append((0.0, lot.lot_id, lot.product, "SOURCE_CREATED"))
    
    # ========== 策略設置 ==========
    
    def set_joint_actions(self, actions: Dict[str, int]):
        """設置四個Agent的動作"""
        d_action = int(actions.get("lot_dispatcher", 0))
        o_action = int(actions.get("operator", 0))
        t_action = int(actions.get("taskexecuter", 0))
        m_action = int(actions.get("maintenance", 0))
        
        # 邊界檢查
        d_action = max(0, min(d_action, len(self.DISPATCHER_STRATEGIES) - 1))
        o_action = max(0, min(o_action, len(self.OPERATOR_STRATEGIES) - 1))
        t_action = max(0, min(t_action, len(self.TASKEXECUTER_STRATEGIES) - 1))
        m_action = max(0, min(m_action, len(self.MAINTENANCE_STRATEGIES) - 1))
        
        self.dispatcher_strategy = self.DISPATCHER_STRATEGIES[d_action]
        self.operator_strategy = self.OPERATOR_STRATEGIES[o_action]
        self.taskexecuter_strategy = self.TASKEXECUTER_STRATEGIES[t_action]
        self.maintenance_strategy = self.MAINTENANCE_STRATEGIES[m_action]
        
        self.event_log.append(
            (
                self.env.now,
                -1,
                "AGENT_ACTION",
                f"D={self.dispatcher_strategy}|O={self.operator_strategy}|T={self.taskexecuter_strategy}|M={self.maintenance_strategy}",
            )
        )
    
    def run_for_interval(self):
        """執行模擬直到下一個決策點"""
        target = min(self.env.now + self.decision_interval, self.max_time)
        self.env.run(until=target)
    
    # ========== Agent 1: Dispatcher (派工員) ==========
    
    def dispatcher_agent_process(self):
        """
        派工員流程
        
        任務池邏輯:
        - 監控SOURCE中的批次
        - 依照策略決策是否派工
        - 將批次加入運輸任務池
        """
        while True:
            now = self.env.now
            
            # 1. 掃描所有待派工的批次
            available_lots = [lot for lot in self.all_lots 
                            if lot.location == "SOURCE" and lot.finish_time is None]
            
            if not available_lots:
                yield self.env.timeout(1)
                continue
            
            # 2. 為每個批次創建派工任務
            for lot in available_lots:
                # 檢查是否已有同樣的任務.
                existing_task = next((t for t in self.dispatcher_task_pool if t.lot.lot_id == lot.lot_id), None)
                if not any(task.lot.lot_id == lot.lot_id for task in self.dispatcher_task_pool):
                    task = DispatchTask(
                        lot=lot,
                        priority=self._calculate_dispatcher_priority(lot),
                        created_time=now
                    )
                    self.dispatcher_task_pool.append(task)
                else:
                    # 動態更新優先級 (因為 LWT 等待時間會隨時間改變)
                    existing_task.priority = self._calculate_dispatcher_priority(lot)
            
            # 3. 排序並挑選出貨物 (呼叫 _dispatcher_select_task)
            if self.dispatcher_task_pool:
                selected_task = self._dispatcher_select_task()
                
                if selected_task:
                    # 4. 根據限制判定是否 PUSH 給 TaskExecuter (呼叫 _dispatcher_make_decision)
                    decision = self._dispatcher_make_decision(selected_task)
                    
                    if decision == "PUSH":
                        # 執行 PUSH：移出派工池，丟給 TaskExecuter (OHT)
                        self.dispatcher_task_pool.remove(selected_task)
                        target_cell = STEP_TO_CELL[selected_task.lot.current_step]
                        self._add_transport_task(selected_task.lot, "SOURCE", target_cell)
                        self.event_log.append(
                            (now, selected_task.lot.lot_id, selected_task.lot.product, "DISPATCHER_PUSH")
                        )
                    # 若為 HOLD，則保留在 task_pool 中等待下次迴圈
            
            yield self.env.timeout(1)
    
    def _calculate_dispatcher_priority(self, lot: Lot) -> float:
        """
        計算派工優先級 (分數越高越優先)
        包含 LWT, SPT, FIFO 的計算方式
        """
        if self.dispatcher_strategy == "fifo":
            # 先進先出：數值越小代表越早到達，加上負號讓越早到達的貨物分數越高
            return -lot.ready_time
            
        elif self.dispatcher_strategy == "spt":
            # 最短加工時間 (Shortest Processing Time)：
            # 取得該工序的預期加工時間，時間越短優先級越高 (加上負號)
            p_time = PROCESS_TIME.get(lot.current_step, 200)
            return -p_time
            
        elif self.dispatcher_strategy == "lwt":
            # 最長等待時間 (Longest Waiting Time)：
            # 當前系統時間 - 貨物準備好的時間，數值越大代表等越久，分數越高
            wait_time = self.env.now - lot.ready_time
            return wait_time
            
        return -lot.ready_time
    
    def _dispatcher_select_task(self) -> Optional[DispatchTask]:
        """
        負責 Sorting：將任務池依據 priority 排序，並挑選出最高分的貨物
        """
        if not self.dispatcher_task_pool:
            return None
        
        # 依據優先級降冪排序 (分數大 -> 分數小)
        self.dispatcher_task_pool.sort(key=lambda t: t.priority, reverse=True)
        
        # 挑出這一次 Dispatcher 選出的貨物 (首位)
        return self.dispatcher_task_pool[0]
    
    def _dispatcher_make_decision(self, selected_task: DispatchTask) -> str:
        """
        判斷選出的貨物是否能 Push 給 TaskExecuter (加入運輸任務池)
        主要受限於 C1~C3 的下游容量限制
        """
        lot = selected_task.lot
        target_cell = STEP_TO_CELL.get(lot.current_step)
        
        # 檢查目標 Cell 是否存在於限制清單中
        if target_cell in self.cell_queues:
            # 若目標區域的在製品數量 >= 該區域的容量上限 (BUFFER_CAPACITY)
            if len(self.cell_queues[target_cell]) >= BUFFER_CAPACITY[target_cell]:
                return "HOLD"  # 容量受限，不推送至任務池
                
        return "PUSH"  # 符合條件，允許 push 給 TaskExecuter
        

    
    
    # ========== Agent 2: Operator (操作員) ==========
    
    def operator_agent_process(self):
        """
        操作員流程
        1. 掃描所有 Cell 找出可執行的任務，加入全域任務池。
        2. 若 Op1 空閒，讓 Op1 挑選任務 (排除 C2)。
        3. 若 Op2 空閒，讓 Op2 挑選任務 (排除 C1)。
        """
        while True:
            now = self.env.now
            
            # --- 1. 任務掃描與生成 ---
            # 掃描 C1 (批次)
            valid_batches = self._find_all_valid_batches_in_c1()
            for batch_info in valid_batches:
                # 只檢查批次的第一個 lot id 是否已在任務池
                if not any(t.lot.lot_id == batch_info["batch"][0].lot_id for t in self.operator_task_pool):
                    # 將整批打包成一個任務 (需要修改 OperatorTask dataclass 支援 batch)
                    # 這裡為了相容原本寫法，先為第一個 lot 建立代表性任務
                    lot = batch_info["batch"][0]
                    task = OperatorTask(
                        lot=lot,
                        machine_name=None,
                        step=batch_info["step"],
                        priority=self._calculate_operator_priority(lot, batch_info["step"]),
                        created_time=now
                    )
                    # 可在 task 內新增一個屬性暫存完整的 batch_lots，方便執行時呼叫
                    task.batch_lots = batch_info["batch"] 
                    self.operator_task_pool.append(task)
            
            # 掃描 C2, C3 (單件)
            for cell in ["C2", "C3"]:
                for lot in self.cell_queues[cell]:
                    if lot.current_step in ["S3", "S6"] and not any(t.lot.lot_id == lot.lot_id for t in self.operator_task_pool):
                        task = OperatorTask(
                            lot=lot,
                            machine_name=None,
                            step=lot.current_step,
                            priority=self._calculate_operator_priority(lot, lot.current_step),
                            created_time=now
                        )
                        task.batch_lots = [lot] # 單件也包成 list 以利統一處理
                        self.operator_task_pool.append(task)

            # --- 2. 任務指派與執行 ---
            
            # 嘗試指派任務給 Op1
            if self.operators["Op1"].count == 0: # Op1 目前空閒
                selected_op1 = self._operator_select_task("Op1")
                if selected_op1:
                    machine = self._get_idle_machine_for_step(selected_op1.step)
                    if machine:
                        selected_op1.machine_name = machine
                        self.operator_task_pool.remove(selected_op1)
                        self.env.process(self._operator_execute_task(selected_op1, "Op1"))

            # 嘗試指派任務給 Op2
            if self.operators["Op2"].count == 0: # Op2 目前空閒
                selected_op2 = self._operator_select_task("Op2")
                if selected_op2:
                    machine = self._get_idle_machine_for_step(selected_op2.step)
                    if machine:
                        selected_op2.machine_name = machine
                        self.operator_task_pool.remove(selected_op2)
                        self.env.process(self._operator_execute_task(selected_op2, "Op2"))
            
            yield self.env.timeout(2)
    
    def _calculate_operator_priority(self, lot: Lot, step: str) -> float:
        """計算操作員任務的基礎優先權 (不含距離)"""
        if self.operator_strategy == "fifo":
            return -lot.ready_time
        
        elif self.operator_strategy == "spt":
            # 取得該工序的加工時間
            p_time = PROCESS_TIME.get(step, 200)
            return -p_time
            
        elif self.operator_strategy == "lwt":
            # 等待時間 = 當前時間 - 進入緩衝區的時間
            return self.env.now - lot.ready_time
            
        return -lot.ready_time
    
    def _operator_select_task(self, op_name: str) -> Optional[OperatorTask]:
        """
        讓操作員 (Op1 或 Op2) 從全域任務池中挑選任務。
        實作了職責分配限制 (Op1: Ma/Mb/Mc/Md, Op2: Me/Mc/Md) 與策略。
        """
        valid_tasks = []
        
        for task in self.operator_task_pool:
            # 確定任務目標所在的 Cell
            target_cell = STEP_TO_CELL.get(task.step)
            
            # 限制式檢查：
            # Op1 負責 C1 (Ma/Mb)，支援 C3 (Mc/Md)，不負責 C2 (Me)
            if op_name == "Op1" and target_cell == "C2":
                continue
            # Op2 負責 C2 (Me)，支援 C3 (Mc/Md)，不負責 C1 (Ma/Mb)
            if op_name == "Op2" and target_cell == "C1":
                continue
                
            valid_tasks.append(task)
            
        if not valid_tasks:
            return None

        # 如果策略是距離優先，需要動態加入操作員當前位置的計算
        if self.operator_strategy == "shortest_distance":
            def distance_score(task):
                target_cell = STEP_TO_CELL.get(task.step)
                current_loc = self.operator_location.get(op_name, "C1")
                dist = self._get_transport_time(current_loc, target_cell)
                # 距離越短越好，但若距離相同，則比較任務本身的 priority
                return (-dist, task.priority)
            
            valid_tasks.sort(key=distance_score, reverse=True)
        else:
            # 否則單純按照基礎優先權排序
            valid_tasks.sort(key=lambda t: t.priority, reverse=True)

        return valid_tasks[0]
    
    def _operator_execute_task(self, task: OperatorTask, op_name: str):
        """執行操作員任務"""
        op_res = self.operators[op_name]
        machine_name = task.machine_name
        
        with op_res.request() as op_req:
            yield op_req
            
            # 根據機台類型決定時間
            if machine_name == "Me":
                setup_time = self._get_setup_time("Me", task.step, task.lot.product)
                load_time = 10
                unload_time = 10
            else:
                setup_time = 0
                load_time = 15
                unload_time = 15
            
            # 上貨
            with self.machines[machine_name].request() as m_req:
                yield m_req
                if setup_time > 0:
                    yield self.env.timeout(setup_time)
                yield self.env.timeout(load_time)
            
            # 加工 (操作員可離開)
            run_time = PROCESS_TIME.get(task.step, 200)
            yield self.env.timeout(run_time)
            
            # 卸貨
            with self.machines[machine_name].request() as m_req:
                yield m_req
                yield self.env.timeout(unload_time)
    
    def _is_valid_batch(self, step: str, lots: List[Lot]) -> bool:
        """驗證是否為有效批次"""
        if len(lots) != 3:
            return False
        
        if any(lot.current_step != step for lot in lots):
            return False
        
        products = [lot.product for lot in lots]
        tw_count = products.count("TW")
        
        if tw_count > 1:
            return False
        
        normal_products = [p for p in products if p != "TW"]
        
        if step == "S1":
            return True
        
        if step == "S5":
            return len(set(normal_products)) <= 1
        
        return False
    
    def _find_all_valid_batches_in_c1(self):
        """尋找C1中所有有效批次"""
        from itertools import combinations
        
        queue = self.cell_queues["C1"]
        valid_batches = []
        
        for step in ["S1", "S5"]:
            candidates = [lot for lot in queue if lot.current_step == step]
            if len(candidates) < 3:
                continue
            
            for combo in combinations(candidates, 3):
                batch = list(combo)
                if self._is_valid_batch(step, batch):
                    valid_batches.append({"step": step, "batch": batch})
        
        return valid_batches
    
    # ========== Agent 3: TaskExecuter (運輸執行員/OHT) ==========
    
    def taskexecuter_agent_process(self):
        """
        運輸執行員流程 (OHT)
        
        任務池邏輯:
        - 監控所有待運輸的批次
        - 依照策略選擇要運輸的批次
        - 檢查目的地容量，避免死鎖
        """
        while True:
            now = self.env.now
            
            # 1. 掃描所有待運輸的批次
            pending_lots = []
            for lot in self.all_lots:
                # 排除已經完成或已經在出口的貨物
                if lot.finish_time is not None or lot.location == "OUT":
                    continue
                
                # 動態計算該批次當前應該前往的目的地
                target_destination = "OUT" if lot.current_step == "OUT" else STEP_TO_CELL.get(lot.current_step)
                
                # 如果目前位置不等於目的地，就代表需要運輸
                if lot.location != target_destination:
                    pending_lots.append(lot)
            
            # 建立運輸任務
            for lot in pending_lots:
                if not any(task.lot.lot_id == lot.lot_id for task in self.transport_task_pool):
                    target = "OUT" if lot.current_step == "OUT" else STEP_TO_CELL.get(lot.current_step)
                    task = TransportTask(
                        lot=lot,
                        from_location=lot.location,
                        to_location=target,
                        ready_time=now,
                        priority=0.0,
                        wait_time=0.0
                    )
                    self.transport_task_pool.append(task)
            
            # 2. 更新任務等待時間和優先級
            for task in self.transport_task_pool:
                task.wait_time = now - task.ready_time
                task.priority = self._calculate_transport_priority(task)
            
            # 3. 選擇並執行任務
            selected_task = self._taskexecuter_select_task()
            
            if selected_task:
                # 驗證目的地容量
                if selected_task.to_location in self.cell_queues:
                    if len(self.cell_queues[selected_task.to_location]) >= BUFFER_CAPACITY[selected_task.to_location]:
                        yield self.env.timeout(2)
                        continue
                
                self.transport_task_pool.remove(selected_task)
                self.env.process(self._taskexecuter_execute_transport(selected_task))
            
            yield self.env.timeout(1)
    
    def _calculate_transport_priority(self, task: TransportTask) -> float:
        """
        計算運輸優先級 (分數越大越優先)
        """
        if self.taskexecuter_strategy == "fifo":
            # FIFO: ready_time 越小代表越早等待，加上負號讓早來的分數高
            return -task.ready_time
            
        elif self.taskexecuter_strategy == "shortest_distance":
            # 距離優先：計算目前 OHT 位置到「貨物所在起點」的距離時間
            # 距離越短越優先，加上負號
            dist_to_pickup = self._get_transport_time(self.oht_location, task.from_location)
            return -dist_to_pickup
            
        elif self.taskexecuter_strategy == "lowest_workload":
            # 剩餘工時最短：計算「目的地」的預計加工負擔，越輕越優先
            target = task.to_location
            if target == "OUT":
                return 0  # 出口不需要加工，優先級最高 (負擔為 0)
                
            # 預期工時 = 該目標 Cell 內的貨物數量 * 該貨物將進行的單站加工時間
            queue_len = len(self.cell_queues.get(target, []))
            p_time = PROCESS_TIME.get(task.lot.current_step, 200)
            workload_eta = queue_len * p_time
            
            # 工時越短越優先，加上負號
            return -workload_eta
            
        return -task.ready_time
    
    def _taskexecuter_select_task(self) -> Optional[TransportTask]:
        """
        根據策略選擇運輸任務，並嚴格執行 C1-C3 容量限制
        """
        valid_tasks = []
        for task in self.transport_task_pool:
            # 限制式：檢查目的地容量。若目的地已滿，該任務不具備執行資格
            if task.to_location in self.cell_queues:
                if len(self.cell_queues[task.to_location]) >= BUFFER_CAPACITY[task.to_location]:
                    continue  # 容量已滿，跳過此任務
            valid_tasks.append(task)
        
        if not valid_tasks:
            return None
            
        # 依據計算出的 priority 進行降冪排序 (分數大 -> 分數小)
        valid_tasks.sort(key=lambda t: t.priority, reverse=True)
        
        # 每次僅能搬運 1 批晶圓，回傳最優先的第一筆
        return valid_tasks[0]
    
    def _taskexecuter_execute_transport(self, task: TransportTask):
        """執行運輸任務"""
        lot = task.lot
        
        move_to_pickup = self._get_transport_time(self.oht_location, task.from_location)
        move_to_dropoff = self._get_transport_time(task.from_location, task.to_location)
        total_move = move_to_pickup + move_to_dropoff
        
        self.event_log.append((self.env.now, lot.lot_id, lot.product, 
                              f"OHT_START_{task.from_location}_TO_{task.to_location}"))
        yield self.env.timeout(total_move)
        
        self.oht_location = task.to_location
        lot.location = task.to_location
        
        self.event_log.append((self.env.now, lot.lot_id, lot.product, 
                              f"OHT_END_AT_{task.to_location}"))
        
        if task.to_location == "OUT":
            lot.finish_time = self.env.now
            self.finished_lots.append(lot)
            self.event_log.append((self.env.now, lot.lot_id, lot.product, "FINISH_OUT"))
        else:
            self.cell_queues[task.to_location].append(lot)
            self.event_log.append((self.env.now, lot.lot_id, lot.product, 
                                  f"ENTER_QUEUE_{task.to_location}_{lot.current_step}"))
        
        self._record_wip()
    
    # ========== Agent 4: Maintenance (維護) ==========
    
    def maintenance_agent_process(self):
        """維護Agent流程：監控所有機台的 PM 和 EM 需求"""
        while True:
            now = self.env.now
            maintenance_needs = []
            
            # 1. 檢查 EM (突發性故障) - 僅 Mc, Md
            for m in ["Mc", "Md"]:
                if now >= self.em_schedule[m] and not getattr(self.machine_state[m], 'down', False):
                    # 平均耗時 420±60 分鐘
                    repair_time = max(60, self.rng.gauss(420, 60))
                    task = MaintenanceTask(
                        machine=m, task_type="EM", duration=repair_time, priority=0.0, created_time=now
                    )
                    maintenance_needs.append(task)
            
            # 2. 檢查 PM (預防性保養)
            # 限制式 A：Ma, Mb 每天進行 75 分鐘，需等待 12 小時 (12 * 60) 才能再 PM
            for m in ["Ma", "Mb"]:
                time_since_pm = now - self.last_pm_time[m]
                if time_since_pm >= 12 * 60:
                    task = MaintenanceTask(
                        machine=m, task_type="PM", duration=75, priority=0.0, created_time=now
                    )
                    maintenance_needs.append(task)
            
            # 限制式 B：Mc, Md, Me 每次 PM 需等待 6 小時 (6 * 60) 才能再 PM
            for m in ["Mc", "Md", "Me"]:
                time_since_pm = now - self.last_pm_time[m]
                if time_since_pm >= 6 * 60:
                    # Mc, Md 每班次 120 分鐘；Me 僅需 30 分鐘
                    duration = 30 if m == "Me" else 120
                    task = MaintenanceTask(
                        machine=m, task_type="PM", duration=duration, priority=0.0, created_time=now
                    )
                    maintenance_needs.append(task)
            
            # 3. 加入任務池並更新優先權
            for task in maintenance_needs:
                if not any(t.machine == task.machine and t.task_type == task.task_type 
                          for t in self.maintenance_task_pool):
                    self.maintenance_task_pool.append(task)
            
            # 動態更新分數 (因為產線水位會變動)
            for task in self.maintenance_task_pool:
                task.priority = self._calculate_maintenance_priority(task)
            
            if not self.maintenance_task_pool:
                yield self.env.timeout(10)
                continue
            
            # 4. 根據策略排序並選擇任務
            selected_task = self._maintenance_select_task()
            
            if selected_task:
                self.maintenance_task_pool.remove(selected_task)
                yield self.env.process(self._maintenance_execute_task(selected_task))
            else:
                yield self.env.timeout(5)
    
    def _calculate_maintenance_priority(self, task: MaintenanceTask) -> float:
        """計算維護優先級分數 (分數越大越優先)"""
        # 1. 狀態絕對優先：EM 加 10000 分，確保任何情況下維修都大於保養
        status_score = 10000 if task.task_type == "EM" else 0
        
        # 2. 瓶頸優先級分數 (ME > MA > Mc > Mb = Md)
        bottleneck_mapping = {"Me": 50, "Ma": 40, "Mc": 30, "Mb": 20, "Md": 20}
        bottleneck_score = bottleneck_mapping.get(task.machine, 0)
        
        # 3. 產線水位分數 (上游貨少、下游貨多)
        # 用 (下游貨量 - 上游貨量) 計算，差值越大代表停機保養對產能的損失越小
        m = task.machine
        cell = MACHINE_CELL.get(m, "C1")
        upstream_q = len(self.cell_queues.get(cell, []))
        
        if cell == "C1":
            downstream_q = len(self.cell_queues.get("C2", []))
        elif cell == "C2":
            downstream_q = len(self.cell_queues.get("C3", []))
        else:
            downstream_q = 0  # C3 下游為出口
            
        load_score = downstream_q - upstream_q
        
        # 根據選擇的策略回傳最終分數
        if self.maintenance_strategy == "status_first":
            return status_score + (1.0 / (self.env.now - task.created_time + 1)) # 同狀態時先到的先做
            
        elif self.maintenance_strategy == "bottleneck_first":
            return status_score + bottleneck_score
            
        elif self.maintenance_strategy == "load_aware":
            return status_score + load_score
            
        return status_score
    
    def _maintenance_select_task(self) -> Optional[MaintenanceTask]:
        """依照計算出的 priority 排序並挑選任務"""
        if not self.maintenance_task_pool:
            return None
            
        # 依據優先級降冪排序
        self.maintenance_task_pool.sort(key=lambda t: t.priority, reverse=True)
        return self.maintenance_task_pool[0]
    
    def _maintenance_execute_task(self, task: MaintenanceTask):
        """執行維護任務"""
        with self.mt1.request() as mt_req:
            yield mt_req
            
            self.machine_state[task.machine].down = True
            
            with self.machines[task.machine].request(priority=-1) as m_req:
                yield m_req
                
                self.event_log.append((self.env.now, -1, "MAINT", 
                                      f"START_{task.task_type}_{task.machine}"))
                yield self.env.timeout(task.duration)
                self.event_log.append((self.env.now, -1, "MAINT", 
                                      f"END_{task.task_type}_{task.machine}"))
            
            self.machine_state[task.machine].down = False
            
            if task.task_type == "PM":
                self.last_pm_time[task.machine] = self.env.now
            elif task.task_type == "EM":
                # 重新排定下次故障時間 (平均 50*60 分鐘，標準差 26*60 分鐘)
                next_em_interval = max(60, self.rng.gauss(50 * 60, 26 * 60))
                self.em_schedule[task.machine] = self.env.now + next_em_interval
    
    # ========== 輔助方法 ==========
    
    def _add_transport_task(self, lot: Lot, from_loc: str, to_loc: str):
        """添加運輸任務到任務池"""
        task = TransportTask(
            lot=lot,
            from_location=from_loc,
            to_location=to_loc,
            ready_time=self.env.now,
            priority=0.0,
            wait_time=0.0
        )
        self.transport_task_pool.append(task)
        self.event_log.append((self.env.now, lot.lot_id, lot.product, 
                              f"WAIT_TRANSPORT_{from_loc}_TO_{to_loc}"))
    
    def _get_transport_time(self, from_location: str, to_location: str) -> float:
        """計算運輸時間"""
        if from_location == to_location:
            return 0.0
        
        base = CELL_DISTANCE.get((from_location, to_location))
        if base is None:
            base = CELL_DISTANCE.get((to_location, from_location), 8)
        
        return TRANSPORT_LOAD + base + TRANSPORT_UNLOAD
    
    def _get_setup_time(self, machine_name: str, step: str, product: str) -> int:
        """計算轉線時間 (僅Me機台)"""
        if machine_name != "Me":
            return 0
        
        state = self.machine_state[machine_name]
        if state.last_step is None:
            return 0
        
        step_changed = state.last_step != step
        product_changed = state.last_product != product
        
        if step_changed and product_changed:
            return 12
        if step_changed:
            return 10
        if product_changed:
            return 5
        return 0
    
    def _get_idle_machine_for_step(self, step: str) -> Optional[str]:
        """獲取閒置機器"""
        cell = STEP_TO_CELL[step]
        machines = CELL_MACHINES[cell]
        
        valid = [
            m for m in machines
            if step in MACHINE_STEPS[m]
            and not self.machine_busy_flags[m]
            and not self.machine_state[m].down
        ]
        
        if not valid:
            return None
        
        return self.rng.choice(valid)
    
    def _record_wip(self):
        """記錄在製品"""
        wip = len([lot for lot in self.all_lots if lot.finish_time is None])
        self.wip_log.append((self.env.now, wip))
    
    # ========== KPI & 觀測 ==========
    
    def total_wip(self) -> int:
        """計算總在製品"""
        return len([lot for lot in self.all_lots if lot.finish_time is None])
    
    def total_setup_count(self) -> int:
        """計算總轉線次數"""
        return sum(state.setup_count for state in self.machine_state.values())
    
    def get_observation_vector(self) -> np.ndarray:
        """獲取觀測向量"""
        time_norm = self.env.now / self.max_time
        source_q = len([lot for lot in self.all_lots if lot.location == "SOURCE"]) / self.max_lots
        trans_q = len(self.transport_task_pool) / max(1, self.max_lots)
        
        c1 = len(self.cell_queues["C1"]) / BUFFER_CAPACITY["C1"]
        c2 = len(self.cell_queues["C2"]) / BUFFER_CAPACITY["C2"]
        c3 = len(self.cell_queues["C3"]) / BUFFER_CAPACITY["C3"]
        
        machine_busy = [
            1.0 if self.machine_busy_flags[m] else 0.0
            for m in ["Ma", "Mb", "Me", "Mc", "Md"]
        ]
        
        finished = len(self.finished_lots) / self.max_lots
        wip = self.total_wip() / self.max_lots
        setup = self.total_setup_count() / 100.0
        
        # 任務池狀態
        dispatcher_tasks = len(self.dispatcher_task_pool) / max(1, self.max_lots)
        operator_tasks = len(self.operator_task_pool) / max(1, self.max_lots)
        
        obs = np.array(
            [
                time_norm,
                source_q,
                trans_q,
                c1,
                c2,
                c3,
                *machine_busy,
                finished,
                wip,
                setup,
                dispatcher_tasks,
                operator_tasks,
            ],
            dtype=np.float32,
        )
        
        return obs
    
    def compute_reward_delta(self) -> float:
        """計算獎勵"""
        now = self.env.now
        dt = now - self.prev_time
        
        finished_now = len(self.finished_lots)
        completed_delta = finished_now - self.prev_finished
        
        wip_now = self.total_wip()
        transport_wait_now = len(self.transport_task_pool)
        setup_now = self.total_setup_count()
        setup_delta = setup_now - self.prev_setup_count
        
        reward = (
            REWARD_WEIGHTS["completed_lot"] * completed_delta
            - REWARD_WEIGHTS["time_penalty"] * dt
            - REWARD_WEIGHTS["wip_penalty"] * wip_now
            - REWARD_WEIGHTS["transport_penalty"] * transport_wait_now
            - REWARD_WEIGHTS["setup_penalty"] * setup_delta
        )
        
        self.prev_time = now
        self.prev_finished = finished_now
        self.prev_wip = wip_now
        self.prev_transport_wait = transport_wait_now
        self.prev_setup_count = setup_now
        
        return float(reward)
    
    def is_done(self) -> bool:
        """檢查是否完成"""
        return len(self.finished_lots) >= self.max_lots or self.env.now >= self.max_time
    
    def final_report(self):
        """生成最終報告"""
        if self.finished_lots:
            tpts = [lot.finish_time - lot.start_time for lot in self.finished_lots]
            avg_tpt = sum(tpts) / len(tpts)
            makespan = max(lot.finish_time for lot in self.finished_lots)
        else:
            avg_tpt = 0.0
            makespan = self.env.now
        
        util = {
            name: state.busy_time / makespan if makespan > 0 else 0.0
            for name, state in self.machine_state.items()
        }
        
        return {
            "finished_lots": len(self.finished_lots),
            "makespan_min": makespan,
            "makespan_hr": makespan / 60.0,
            "avg_tpt_min": avg_tpt,
            "setup_count": self.total_setup_count(),
            "machine_util": util,
            "event_log": pd.DataFrame(self.event_log, columns=["time", "lot_id", "product", "event"]),
            "wip_log": pd.DataFrame(self.wip_log, columns=["time", "wip"]),
            "dispatcher_task_pool_size": len(self.dispatcher_task_pool),
            "operator_task_pool_size": len(self.operator_task_pool),
            "transport_task_pool_size": len(self.transport_task_pool),
            "maintenance_task_pool_size": len(self.maintenance_task_pool),
        }
