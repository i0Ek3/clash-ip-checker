from pydantic import BaseModel
from typing import Dict, Any, List

class StartRequest(BaseModel):
    yaml_content: str
    config: Dict[str, Any] = {}

class UpdateNodeRequest(BaseModel):
    name: str

class ExportRequest(BaseModel):
    node_ids: List[int]

class RecheckRequest(BaseModel):
    config: Dict[str, Any] = {}
