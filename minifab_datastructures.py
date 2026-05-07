"""
Data Structures Module
======================
定義模擬環境中使用的所有數據結構
"""

from dataclasses import dataclass
from typing import Optional
from minifab_config import PROCESS_FLOW


@dataclass
class Lot:
    """
    代表一批次產品
    
    屬性:
        lot_id: 批次ID
        product: 產品型號 (Pa, Pb, TW)
        start_time: 批次創建時間
        step_index: 當前製程步驟索引
        location: 當前位置 (SOURCE, C1, C2, C3, OUT)
        ready_time: 準備完成時間
        finish_time: 完成時間
    """
    lot_id: int
    product: str
    start_time: float
    step_index: int = 0
    location: str = "SOURCE"
    ready_time: float = 0.0
    finish_time: Optional[float] = None

    @property
    def current_step(self) -> str:
        """獲取當前製程步驟"""
        if self.step_index >= len(PROCESS_FLOW):
            return "OUT"
        return PROCESS_FLOW[self.step_index]


@dataclass
class MachineState:
    """
    機器狀態追蹤
    
    屬性:
        name: 機器名稱
        last_step: 上一個製程步驟
        last_product: 上一個產品
        busy_time: 機器繁忙時間
        setup_count: 轉線次數
        down: 機器是否故障
    """
    name: str
    last_step: Optional[str] = None
    last_product: Optional[str] = None
    busy_time: float = 0.0
    setup_count: int = 0
    down: bool = False


@dataclass
class TransportTask:
    """
    運輸任務
    
    屬性:
        lot: 批次物件
        from_location: 出發位置
        to_location: 目的地
        ready_time: 任務準備完成時間
    """
    lot: Lot
    from_location: str
    to_location: str
    ready_time: float
