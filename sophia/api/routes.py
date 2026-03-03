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
from sophia.core.loop import AgentLoop, _tree_to_dict
from sophia.core.tree_analysis import classify_risk
from sophia.tools.base import ToolResult

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

            # Step 1: Parse intent
            await websocket.send_json({"event": "processing", "stage": "input_gate"})
            intent = await loop.input_gate.parse(message)
            await websocket.send_json({
                "event": "intent_parsed",
                "data": asdict(intent),
            })

            # Step 2: Generate proposals
            await websocket.send_json({"event": "processing", "stage": "proposer"})
            proposal = await loop.proposer.propose(intent)
            await websocket.send_json({
                "event": "proposals_generated",
                "data": {"candidates": [asdict(c) for c in proposal.candidates]},
            })

            # Step 3: Generate consequence trees
            await websocket.send_json({"event": "processing", "stage": "consequence"})
            consequence_trees = []
            for candidate in proposal.candidates:
                tree = await loop.consequence_engine.analyze(candidate)
                consequence_trees.append(tree)

            top_tree = consequence_trees[0] if consequence_trees else None
            risk_tier = (
                classify_risk(
                    top_tree,
                    catastrophic_threshold=loop.settings.catastrophic_threshold,
                )
                if top_tree
                else "GREEN"
            )

            await websocket.send_json({
                "event": "consequences_analyzed",
                "data": {
                    "trees": [_tree_to_dict(t) for t in consequence_trees],
                    "risk_tier": risk_tier,
                },
            })

            # Step 4: Execute based on risk tier
            await websocket.send_json({"event": "processing", "stage": "executor"})
            if risk_tier == "RED":
                from sophia.core.executor import ExecutionResult
                from sophia.core.proposer import CandidateAction

                execution = ExecutionResult(
                    action_taken=proposal.candidates[0] if proposal.candidates else CandidateAction(
                        tool_name="none", reasoning="No candidates"
                    ),
                    tool_result=ToolResult(
                        success=False,
                        data=None,
                        message="Action refused: consequence analysis identified catastrophic risk.",
                    ),
                    risk_tier="RED",
                )
            else:
                execution = await loop.executor.execute(proposal)
                execution.risk_tier = risk_tier

            await websocket.send_json({
                "event": "action_executed",
                "data": {
                    "action_taken": asdict(execution.action_taken),
                    "tool_result": asdict(execution.tool_result),
                    "risk_tier": execution.risk_tier,
                },
            })

            # Final response
            response = loop._build_response(execution)
            await websocket.send_json({
                "event": "response_ready",
                "data": {"response": response},
            })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.exception("WebSocket error")
        try:
            await websocket.send_json({"event": "error", "data": {"message": str(e)}})
        except Exception:
            pass
