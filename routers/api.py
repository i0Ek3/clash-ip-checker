from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from ruamel.yaml import YAML, YAMLError
import asyncio
import uuid
import json
import copy
import io
import os
from typing import Dict, List, Any

# Local imports
from state import state
from schemas import StartRequest, UpdateNodeRequest, ExportRequest, RecheckRequest
from core.clash_api import ClashController

router = APIRouter(prefix="/api")
yaml = YAML()
yaml.preserve_quotes = True

# --- Helper Function to run check in background ---
async def _run_check(proxies: List[Dict], config: Dict):
    """Background task: check all nodes using Clash API"""
    # Get config values
    api_url = config.get("clash_api_url", "http://127.0.0.1:9097")
    api_secret = config.get("clash_api_secret", "")
    selector = config.get("selector_name", "GLOBAL")
    fast_mode = config.get("fast_mode", True)
    source = config.get("source", "ping0")
    fallback = config.get("fallback", True)
    headless = config.get("headless", True)
    
    # Update checker headless setting dynamically
    state.checker.headless = headless
    
    # Check if empty
    if not proxies:
        state.is_running = False
        state.events.append({"type": "complete", "total": 0})
        return
        
    state.total = len(proxies)
    
    # Initialize Clash controller
    controller = ClashController(api_url, api_secret)
    
    try:
        # Set Global mode for testing
        await controller.set_mode("global")
        
        # Get proxy port from Clash API
        port = await controller.get_running_port()
        proxy_url = f"http://127.0.0.1:{port}"
        print(f"[Web] Using Clash proxy: {proxy_url}")
        
    except Exception as e:
        state.events.append({
            "type": "error",
            "node_name": "Clash API",
            "error": f"无法连接到 Clash API: {e}"
        })
        state.is_running = False
        state.checker.clear_cache() # Clear cache on error
        state.events.append({"type": "complete", "total": 0})
        return
    
    checked_count = 0
    
    for i, proxy in enumerate(proxies):
        if not state.is_running:
            break
        
        name = proxy.get("name", f"Node {i}")
        state.current_node = name
        
        try:
            # 1. Switch to this node via Clash API
            print(f"[Web] Switching to: {name}")
            switched = await controller.switch_proxy(selector, name)
            
            if not switched:
                node_data = {
                    "id": i,
                    "original_name": name,
                    "name": f"{name}【❌ 切换失败】",
                    "ip": "❓",
                    "status": "❌ 切换失败",
                    "proxy_config": proxy
                }
                state.nodes[i] = node_data
                state.events.append({"type": "progress", "progress": checked_count + 1, "total": state.total, "node": node_data})
                checked_count += 1
                continue
            
            # 2. Wait for switch to take effect
            await asyncio.sleep(1)
            
            # 3. Check IP through Clash proxy
            if fast_mode:
                result = await state.checker.check_fast(proxy_url, source=source, fallback=fallback)
            else:
                result = await state.checker.check_browser(proxy=proxy_url)
            
            node_data = {
                "id": i,
                "original_name": name,
                "name": f"{name}{result.get('full_string', '')}",
                "ip": result.get("ip", "❓"),
                "risk": result.get("pure_score", "❓"),
                "bot": result.get("bot_score", "N/A"),  # For non-fast mode
                "shared": result.get("shared_users", "N/A"),  # For fast mode
                "type": result.get("ip_attr", "❓"),
                "native": result.get("ip_src", "❓"),
                "source": result.get("source", "unknown"),
                "status": "✅" if result.get("source") == "ping0" else "⚠️ 降级",
                "proxy_config": proxy
            }
            state.nodes[i] = node_data
            
            # Push event
            checked_count += 1
            state.events.append({
                "type": "progress",
                "progress": checked_count,
                "total": state.total,
                "node": node_data
            })
            
        except Exception as e:
            node_data = {
                "id": i,
                "original_name": name,
                "name": f"{name}【❌ Error】",
                "ip": "❓",
                "status": "❌ 失败",
                "error": str(e),
                "proxy_config": proxy
            }
            state.nodes[i] = node_data
            checked_count += 1
            state.events.append({
                "type": "error",
                "node_name": name,
                "error": str(e)
            })
        
        state.progress = checked_count
    
    # Complete
    state.is_running = False
    state.checker.clear_cache() # Clear cache on completion
    state.events.append({"type": "complete", "total": len(state.nodes)})


# --- Routes ---

@router.post("/validate")
async def validate_yaml(request: StartRequest):
    """Validate YAML format"""
    try:
        data = yaml.load(request.yaml_content)
        if not data:
            return JSONResponse({"valid": False, "error": "YAML 内容为空"}, status_code=400)
        
        proxies = data.get("proxies", [])
        if not proxies:
            return JSONResponse({"valid": False, "error": "未找到 proxies 节点"}, status_code=400)
        
        return {"valid": True, "node_count": len(proxies)}
    
    except YAMLError as e:
        return JSONResponse({"valid": False, "error": f"YAML 解析错误: {str(e)}"}, status_code=400)


@router.post("/start")
async def start_check(request: StartRequest):
    """Start node checking task"""
    if state.is_running:
        raise HTTPException(status_code=409, detail="任务正在运行中")
    
    try:
        data = yaml.load(request.yaml_content)
        proxies = data.get("proxies", [])
        
        if not proxies:
            raise HTTPException(status_code=400, detail="未找到 proxies 节点")
        
        # Initialize state
        state.task_id = str(uuid.uuid4())
        state.is_running = True
        state.original_yaml = data
        state.nodes = []
        state.events = []  # Clear previous events
        state.progress = 0
        # Filter proxies based on skip keywords
        skip_keywords_str = request.config.get("skip_keywords_str", "")
        skip_keywords = [kw.strip() for kw in skip_keywords_str.split(",") if kw.strip()]
        
        active_proxies = []
        for p in proxies:
            name = p.get("name", "")
            if skip_keywords and any(kw in name for kw in skip_keywords):
                print(f"[Web] Skipping (in start): {name}")
                continue
            active_proxies.append(p)
            
            # Pre-fill node for immediate display
            state.nodes.append({
                "id": len(active_proxies) - 1,
                "original_name": name,
                "name": name,
                "ip": "...",
                "risk": "",
                "shared": "",
                "type": "",
                "native": "",
                "source": "",
                "status": "pending",
                "proxy_config": p
            })

        state.total = len(active_proxies)
        
        # Start background task with filtered proxies
        asyncio.create_task(_run_check(active_proxies, request.config))
        
        return {"task_id": state.task_id, "total": state.total}
    
    except YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML 解析错误: {str(e)}")


@router.get("/progress")
async def progress_stream():
    """SSE endpoint for progress updates"""
    async def event_generator():
        last_sent = 0
        while True:
            # Send new events
            while last_sent < len(state.events):
                event = state.events[last_sent]
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                last_sent += 1
            
            # Check if complete
            if not state.is_running and last_sent >= len(state.events):
                break
            
            await asyncio.sleep(0.1)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@router.post("/stop")
async def stop_check():
    """Stop running task"""
    if not state.is_running:
        raise HTTPException(status_code=400, detail="没有正在运行的任务")
    
    state.is_running = False
    state.events.append({"type": "stopped"})
    return {"status": "stopped"}


@router.get("/nodes")
async def get_nodes():
    """Get all nodes"""
    return {"nodes": state.nodes, "is_running": state.is_running}


@router.put("/nodes/{node_id}")
async def update_node(node_id: int, request: UpdateNodeRequest):
    """Update node name"""
    for node in state.nodes:
        if node["id"] == node_id:
            node["name"] = request.name
            return {"status": "updated", "node": node}
    
    raise HTTPException(status_code=404, detail="节点不存在")


@router.delete("/nodes/{node_id}")
async def delete_node(node_id: int):
    """Delete node"""
    for i, node in enumerate(state.nodes):
        if node["id"] == node_id:
            state.nodes.pop(i)
            return {"status": "deleted"}
    
    raise HTTPException(status_code=404, detail="节点不存在")


@router.post("/nodes/{node_id}/recheck")
async def recheck_node(node_id: int, request: RecheckRequest):
    """Recheck a specific node"""
    if state.is_running:
        raise HTTPException(status_code=409, detail="请先停止当前的批量检测任务")
    
    # Find the node
    target_node = None
    target_index = -1
    for i, node in enumerate(state.nodes):
        if node["id"] == node_id:
            target_node = node
            target_index = i
            break
    
    if not target_node:
        raise HTTPException(status_code=404, detail="节点不存在")
        
    name = target_node["name"]
    original_name = target_node.get("original_name", name)
    
    # Get config from request
    config = request.config
    print(f"[Debug] Recheck config received: {config}") # Debug print
    if not config:
        print("[Warning] Received EMPTY config for recheck! This usually means frontend app.js is outdated (cached).")

    api_url = config.get("clash_api_url", "http://127.0.0.1:9097")
    api_secret = config.get("clash_api_secret", "")
    selector = config.get("selector_name", "GLOBAL")
    fast_mode = config.get("fast_mode", True)
    source = config.get("source", "ping0")
    fallback = config.get("fallback", True)
    headless = config.get("headless", True)
    
    # Update checker headless setting dynamically
    state.checker.headless = headless
   



    controller = ClashController(api_url, api_secret)
    
    try:
        # 1. Switch
        print(f"[Recheck] Switching to: {original_name}")
        await controller.set_mode("global")
        switched = await controller.switch_proxy(selector, original_name)
        
        if not switched:
             raise Exception("切换节点失败")
             
        # 2. Wait
        await asyncio.sleep(1)
 
        
        
        # 3. Check
        port = await controller.get_running_port()
        proxy_url = f"http://127.0.0.1:{port}"
        
         # 3. Check IP through Clash proxy
        if fast_mode:
            result = await state.checker.check_fast(proxy_url, source=source, fallback=fallback)
        else:
            result = await state.checker.check_browser(proxy=proxy_url)
        
        # 4. Update Node
        node_data = target_node.copy()
        node_data.update({
            "name": f"{original_name}{result.get('full_string', '')}",
            "ip": result.get("ip", "❓"),
            "risk": result.get("pure_score", "❓"),
            "bot": result.get("bot_score", "N/A"),
            "shared": result.get("shared_users", "N/A"),
            "type": result.get("ip_attr", "❓"),
            "native": result.get("ip_src", "❓"),
            "source": result.get("source", "unknown"),
            "status": "✅" if result.get("source") == "ping0" else "⚠️ 降级",
        })
        
        state.nodes[target_index] = node_data
        
        # 5. Push Event manually to trigger UI update
        event = {
            "type": "update", # New event type for single update
            "node": node_data
        }
        state.events.append(event)
        
        return {"status": "success", "node": node_data}

    except Exception as e:
        print(f"[Recheck] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export")
async def export_yaml(request: ExportRequest):
    """Export selected nodes as YAML"""
    selected_nodes = [n for n in state.nodes if n["id"] in request.node_ids]
    
    if not selected_nodes:
        raise HTTPException(status_code=400, detail="请选择要导出的节点")
    
    # Build name mapping for proxy-groups sync
    name_map = {n["original_name"]: n["name"] for n in selected_nodes}
    deleted_names = set(n["original_name"] for n in state.nodes if n["id"] not in request.node_ids)
    
    # Clone original YAML (Deep Copy to avoid mutating state)
    export_data = copy.deepcopy(state.original_yaml)
    
    # Replace proxies with updated config and name
    new_proxies = []
    for node in selected_nodes:
        proxy = node["proxy_config"].copy()
        proxy["name"] = node["name"]
        new_proxies.append(proxy)
    
    export_data["proxies"] = new_proxies
    
    # Update proxy-groups
    for group in export_data.get("proxy-groups", []):
        new_group_proxies = []
        for proxy_name in group.get("proxies", []):
            if proxy_name in deleted_names:
                continue  # Skip deleted nodes
            if proxy_name in name_map:
                new_group_proxies.append(name_map[proxy_name])
            else:
                new_group_proxies.append(proxy_name)  # Keep DIRECT, REJECT, etc.
        group["proxies"] = new_group_proxies
    
    # Generate YAML
    stream = io.StringIO()
    yaml.dump(export_data, stream)
    yaml_content = stream.getvalue()
    
    # Save to file system for URL access
    task_id = state.task_id or str(uuid.uuid4())
    filename = f"clash_checked_{task_id[:8]}.yaml"
    filepath = os.path.join("exports", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    return {
        "yaml": yaml_content,
        "filename": filename,
        "url": f"/exports/{filename}"
    }
