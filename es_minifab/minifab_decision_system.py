"""
Event-Driven Decision System with Feature Extraction
====================================================

決策點事件驅動系統 - 在時間跳到決策點時：
1. 處理觸發事件 (例如機台加工完畢)
2. 狀態計算與特徵提取 (12個特徵)
3. 神經網路決策 (獲得最高分Lot配對)
4. 註冊未來事件 (排程下一個加工完成)
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum


class EventType(Enum):
    """事件類型"""
    MACHINE_AVAILABLE = "machine_available"  # 機台可用
    LOT_ARRIVAL = "lot_arrival"              # Lot到達
    DECISION_POINT = "decision_point"        # 決策點


@dataclass
class DecisionContext:
    """決策上下文"""
    current_time: float
    machine_name: str
    event_type: EventType
    machine_state: Dict  # 機台狀態
    cell_queues: Dict[str, List]  # 各Cell等候區
    pending_transport: List  # 待運輸任務
    wip_summary: Dict  # WIP統計


@dataclass
class DispatchingContext(DecisionContext):
    """派工決策上下文"""
    available_machines: List[str]
    candidates_in_source: List  # 源點候選Lot


@dataclass
class FeatureVector:
    """12維特徵向量"""
    # Machine-related features (4)
    machine_utilization: float      # 機台利用率
    machine_setup_count: float      # 換線次數
    machine_pending_lots: float     # 待處理Lot數
    machine_idle_time: float        # 閒置時間
    
    # Queue-related features (4)
    queue_length: float             # 隊列長度
    queue_age_max: float            # 隊列中最長等待時間
    queue_product_variety: float    # 隊列中的產品多樣性
    downstream_buffer_util: float   # 下一工序Buffer利用率
    
    # Lot-related features (4)
    lot_remaining_steps: float      # Lot剩餘步驟數
    lot_wait_time: float            # Lot當前等待時間
    lot_product_type: float         # 產品類型編碼
    lot_batch_potential: float      # 配批可能性
    
    def to_array(self) -> np.ndarray:
        """轉換為numpy數組"""
        return np.array([
            self.machine_utilization,
            self.machine_setup_count,
            self.machine_pending_lots,
            self.machine_idle_time,
            self.queue_length,
            self.queue_age_max,
            self.queue_product_variety,
            self.downstream_buffer_util,
            self.lot_remaining_steps,
            self.lot_wait_time,
            self.lot_product_type,
            self.lot_batch_potential,
        ], dtype=np.float32)
    
    @staticmethod
    def from_array(arr: np.ndarray) -> 'FeatureVector':
        """從numpy數組構建"""
        return FeatureVector(
            machine_utilization=arr[0],
            machine_setup_count=arr[1],
            machine_pending_lots=arr[2],
            machine_idle_time=arr[3],
            queue_length=arr[4],
            queue_age_max=arr[5],
            queue_product_variety=arr[6],
            downstream_buffer_util=arr[7],
            lot_remaining_steps=arr[8],
            lot_wait_time=arr[9],
            lot_product_type=arr[10],
            lot_batch_potential=arr[11],
        )


class FeatureExtractor:
    """特徵提取器"""
    
    def __init__(self, config: Dict):
        """
        初始化特徵提取器
        
        Args:
            config: 系統配置 (包含PROCESS_FLOW, PRODUCT_MIX等)
        """
        self.config = config
        self.process_flow = config["PROCESS_FLOW"]
        self.process_time = config["PROCESS_TIME"]
        self.buffer_capacity = config["BUFFER_CAPACITY"]
        self.step_to_cell = config["STEP_TO_CELL"]
    
    def extract_lot_features(
        self,
        lot,
        current_time: float,
        machine_name: str,
        queue_context: Dict,
    ) -> FeatureVector:
        """
        提取單個Lot的特徵
        
        Args:
            lot: Lot對象
            current_time: 當前時間
            machine_name: 目標機台名稱
            queue_context: 隊列上下文信息
        
        Returns:
            12維特徵向量
        """
        # 1. Machine-related features
        machine_util = queue_context.get("machine_utilization", 0.0)
        machine_setup = queue_context.get("setup_count", 0)
        machine_pending = queue_context.get("pending_lots", 0)
        machine_idle = queue_context.get("idle_time", 0.0)
        
        # 2. Queue-related features
        queue_length = len(queue_context.get("queue", []))
        queue_ages = [
            current_time - lot_in_queue.ready_time
            for lot_in_queue in queue_context.get("queue", [])
        ]
        queue_age_max = max(queue_ages) if queue_ages else 0.0
        
        # 產品多樣性 (0-1: 只有一種產品 -> 多種產品)
        products = [l.product for l in queue_context.get("queue", [])]
        product_variety = len(set(products)) / max(len(products), 1)
        
        # 下游Buffer利用率
        next_cell = self._get_next_cell(lot.current_step)
        downstream_util = (
            len(queue_context.get("next_queue", [])) / 
            self.buffer_capacity.get(next_cell, 12)
            if next_cell else 0.0
        )
        
        # 3. Lot-related features
        remaining_steps = len(self.process_flow) - lot.step_index
        wait_time = current_time - lot.ready_time
        
        # 產品類型編碼
        product_code = self._encode_product(lot.product)
        
        # 配批可能性 (用於C1的批次操作)
        batch_potential = self._calculate_batch_potential(
            lot,
            queue_context.get("queue", [])
        )
        
        return FeatureVector(
            machine_utilization=float(machine_util),
            machine_setup_count=float(machine_setup) / 100.0,  # 歸一化
            machine_pending_lots=float(machine_pending),
            machine_idle_time=float(machine_idle) / 100.0,
            queue_length=float(queue_length),
            queue_age_max=float(queue_age_max) / 100.0,  # 歸一化
            queue_product_variety=float(product_variety),
            downstream_buffer_util=float(downstream_util),
            lot_remaining_steps=float(remaining_steps),
            lot_wait_time=float(wait_time) / 100.0,  # 歸一化
            lot_product_type=float(product_code),
            lot_batch_potential=float(batch_potential),
        )
    
    def extract_batch_features(
        self,
        candidates: List[Tuple],
        current_time: float,
        context: Dict,
    ) -> List[FeatureVector]:
        """
        批量提取Lot特徵
        
        Args:
            candidates: [(lot, machine_name), ...]候選列表
            current_time: 當前時間
            context: 上下文信息
        
        Returns:
            特徵向量列表
        """
        features = []
        for lot, machine_name in candidates:
            queue_context = context.get(machine_name, {})
            feature = self.extract_lot_features(
                lot, current_time, machine_name, queue_context
            )
            features.append(feature)
        return features
    
    def _get_next_cell(self, current_step: str) -> Optional[str]:
        """取得下一個工序的Cell"""
        step_idx = self.process_flow.index(current_step)
        if step_idx + 1 >= len(self.process_flow):
            return None
        next_step = self.process_flow[step_idx + 1]
        return self.step_to_cell.get(next_step)
    
    def _encode_product(self, product: str) -> float:
        """編碼產品類型為0-1之間的數值"""
        product_map = {"Pa": 0.0, "Pb": 0.5, "TW": 1.0}
        return product_map.get(product, 0.0)
    
    def _calculate_batch_potential(self, lot: str, queue: List) -> float:
        """
        計算配批可能性 (0-1)
        - 如果Lot可以跟隊列中其他Lot配批，返回高分
        """
        if lot.current_step not in ["S1", "S5"]:
            return 0.0
        
        compatible_count = sum(
            1 for q_lot in queue
            if q_lot.current_step == lot.current_step
            and self._is_compatible_for_batch(lot, q_lot)
        )
        
        # 配批潛力 = (相容Lot數 / 3)，最多3個Lot可配批
        return min(1.0, compatible_count / 3.0)
    
    def _is_compatible_for_batch(self, lot1, lot2) -> bool:
        """檢查兩個Lot是否相容配批"""
        # 簡化邏輯：同一步驟的Lot都可配批
        # 實際應檢查產品和時間約束
        return lot1.current_step == lot2.current_step


class EventDrivenScheduler:
    """事件驅動的決策調度器"""
    
    def __init__(self, config: Dict):
        """初始化調度器"""
        self.config = config
        self.feature_extractor = FeatureExtractor(config)
        self.decision_log = []
    
    def trigger_decision(
        self,
        context: DecisionContext,
        policy_network=None,  # 神經網路模型
    ) -> Tuple[int, Dict]:
        """
        觸發決策點
        
        Flow:
        1. 處理觸發事件
        2. 提取特徵 (12個特徵)
        3. 神經網路決策 (最高分)
        4. 返回決策動作和元數據
        
        Args:
            context: 決策上下文
            policy_network: 神經網路策略 (如果None則返回默認)
        
        Returns:
            (action_idx, decision_metadata)
        """
        # 1. 處理觸發事件
        event_processed = self._process_trigger_event(context)
        
        # 2. 提取特徵
        features = self._extract_decision_features(context)
        
        # 3. 神經網路決策
        if policy_network is not None:
            scores = policy_network(features)  # 獲取各候選的評分
            action_idx = int(np.argmax(scores))
        else:
            # 默認：FIFO
            action_idx = 0
        
        # 4. 記錄決策
        decision_metadata = {
            "time": context.current_time,
            "event_type": context.event_type.value,
            "event_processed": event_processed,
            "features": features,
            "action_idx": action_idx,
        }
        self.decision_log.append(decision_metadata)
        
        return action_idx, decision_metadata
    
    def _process_trigger_event(self, context: DecisionContext) -> Dict:
        """
        1. 處理觸發事件
        
        如果是MACHINE_AVAILABLE事件：
        - 機台狀態改為「閒置」
        - 已完成的Lot進入下一步驟等候區
        """
        if context.event_type == EventType.MACHINE_AVAILABLE:
            return {
                "machine_available": context.machine_name,
                "lots_released": 0,  # 實際應計算釋放的Lot數
            }
        return {}
    
    def _extract_decision_features(self, context: DecisionContext) -> np.ndarray:
        """
        2. 狀態計算與特徵提取
        
        從上下文中提取12個特徵
        """
        # 建立隊列上下文
        queue_context = {
            "machine_utilization": 0.5,  # 示例
            "setup_count": 0,
            "pending_lots": 0,
            "idle_time": 0.0,
            "queue": [],
            "next_queue": [],
        }
        
        # 簡化版：返回12維向量 (實際應從context提取真實值)
        features = np.array([
            0.5,  # machine_utilization
            0.0,  # machine_setup_count
            1.0,  # machine_pending_lots
            0.0,  # machine_idle_time
            2.0,  # queue_length
            50.0, # queue_age_max
            0.5,  # queue_product_variety
            0.3,  # downstream_buffer_util
            4.0,  # lot_remaining_steps
            30.0, # lot_wait_time
            0.0,  # lot_product_type
            0.5,  # lot_batch_potential
        ], dtype=np.float32)
        
        return features
    
    def schedule_future_event(
        self,
        current_time: float,
        processing_time: float,
        event_type: EventType,
        lot_id: int,
    ) -> Dict:
        """
        4. 註冊未來事件 (排程)
        
        Args:
            current_time: 當前時間
            processing_time: 處理時間
            event_type: 事件類型
            lot_id: Lot ID
        
        Returns:
            已排程的事件信息
        """
        future_time = current_time + processing_time
        
        event = {
            "scheduled_time": future_time,
            "event_type": event_type.value,
            "lot_id": lot_id,
            "processing_time": processing_time,
        }
        
        return event
