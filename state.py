from typing import Dict, List, Optional
from core.ip_checker import IPChecker

class AppState:
    def __init__(self):
        self.checker = IPChecker(headless=True)
        self.task_id: Optional[str] = None
        self.is_running: bool = False
        self.nodes: List[Dict] = []
        self.original_yaml: Dict = {}
        self.progress: int = 0
        self.total: int = 0
        self.current_node: str = ""
        self.events: List[Dict] = []

# Global instance
state = AppState()
