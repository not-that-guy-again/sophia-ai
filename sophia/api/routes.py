import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from sophia.api.schemas import (
    ChatRequest,
    ChatResponse,
    HatActiveResponse,
    HatSummaryResponse,
    HealthResponse,
    ToolDefinitionResponse,
)
from sophia.core.loop import AgentLoop, _tree_to_dict, _evaluation_to_dict, _classification_to_dict

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazily initialized agent loop (created on first request)
_agent_loop: AgentLoop | None = None


def get_agent_loop() -> AgentLoop:
    global _agent_loop
    if _agent_loop is None:
        _agent_loop = AgentLoop()
    return _agent_loop


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version="0.1.0")


@router.get("/tools", response_model=list[ToolDefinitionResponse])
async def list_tools():
    loop = get_agent_loop()
    return loop.tool_registry.get_definitions()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    loop = get_agent_loop()
    result = await loop.process(request.message)
    return result.to_dict()


# --- Hat management endpoints ---


@router.get("/hats", response_model=list[HatSummaryResponse])
async def list_hats():
    """List all available hats."""
    loop = get_agent_loop()
    manifests = loop.hat_registry.list_available()
    return [
        HatSummaryResponse(
            name=m.name,
            display_name=m.display_name or m.name,
            description=m.description,
            version=m.version,
            tools=m.tools,
        )
        for m in manifests
    ]


@router.get("/hats/active", response_model=HatActiveResponse)
async def active_hat():
    """Get the currently equipped hat."""
    loop = get_agent_loop()
    hat = loop.hat_registry.get_active()
    if hat is None:
        raise HTTPException(status_code=404, detail="No hat is currently equipped")
    return HatActiveResponse(
        name=hat.name,
        display_name=hat.display_name,
        description=hat.manifest.description,
        version=hat.manifest.version,
        tools=hat.manifest.tools,
        constraints=hat.constraints,
        stakeholder_count=len(hat.stakeholders.stakeholders),
    )


@router.post("/hats/{hat_name}/equip", response_model=HatActiveResponse)
async def equip_hat(hat_name: str):
    """Equip a different hat, switching tools and domain context."""
    loop = get_agent_loop()
    try:
        hat = loop.equip_hat(hat_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return HatActiveResponse(
        name=hat.name,
        display_name=hat.display_name,
        description=hat.manifest.description,
        version=hat.manifest.version,
        tools=hat.manifest.tools,
        constraints=hat.constraints,
        stakeholder_count=len(hat.stakeholders.stakeholders),
    )


# --- WebSocket ---


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    loop = get_agent_loop()

    try:
        # Notify client which hat is equipped
        hat = loop.hat_registry.get_active()
        if hat:
            await websocket.send_json({
                "event": "hat_equipped",
                "data": {"name": hat.name, "display_name": hat.display_name},
            })

        while True:
            data = await websocket.receive_text()
            message = json.loads(data).get("message", data)

            # Run the full pipeline (includes evaluation panel)
            result = await loop.process(message)

            # Emit pipeline stage events for UI visualization
            await websocket.send_json({
                "event": "intent_parsed",
                "data": asdict(result.intent),
            })

            await websocket.send_json({
                "event": "proposals_generated",
                "data": {"candidates": [asdict(c) for c in result.proposal.candidates]},
            })

            await websocket.send_json({
                "event": "consequences_analyzed",
                "data": {
                    "trees": [_tree_to_dict(t) for t in result.consequence_trees],
                },
            })

            # Emit individual evaluator results
            for eval_result in result.evaluation_results:
                await websocket.send_json({
                    "event": "evaluator_complete",
                    "data": _evaluation_to_dict(eval_result),
                })

            # Emit risk classification
            await websocket.send_json({
                "event": "risk_classified",
                "data": _classification_to_dict(result.risk_classification),
            })

            await websocket.send_json({
                "event": "action_executed",
                "data": {
                    "action_taken": asdict(result.execution.action_taken),
                    "tool_result": asdict(result.execution.tool_result),
                    "risk_tier": result.execution.risk_tier,
                },
            })

            # Final response
            await websocket.send_json({
                "event": "response_ready",
                "data": {"response": result.response},
            })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.exception("WebSocket error")
        try:
            await websocket.send_json({"event": "error", "data": {"message": str(e)}})
        except Exception:
            pass
