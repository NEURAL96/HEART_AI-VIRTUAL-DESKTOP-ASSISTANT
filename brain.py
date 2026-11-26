"""
H.E.A.R.T Brain v3.0 - Autonomous Decision Engine
Single-file Master Implementation for Zero-Latency Cognitive Processing.
Author: Senior Architect for Tilak Kumar (DarkDevil)
"""

from __future__ import annotations
import asyncio
import json
import os
import time
import psutil
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Awaitable, Optional, Dict


# ==============================================================================
# 1. CORE DATA MODELS
# ==============================================================================

class RiskLevel(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class DecisionType(Enum):
    EXECUTE = auto()
    CONFIRM = auto()
    CLARIFY = auto()
    BLOCK = auto()
    PLAN = auto()


@dataclass(slots=True)
class ToolMetadata:
    name: str
    description: str
    handler: Callable[..., Awaitable[str]]
    risk_level: RiskLevel = RiskLevel.LOW
    cooldown: float = 0.0
    priority: float = 1.0
    tags: list[str] = field(default_factory=list)
    requires_context: list[str] = field(default_factory=list)
    last_used: float = 0.0
    success_rate: float = 1.0
    avg_latency_ms: float = 50.0


@dataclass(slots=True)
class SystemState:
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    battery_percent: Optional[float] = None
    active_window: str = ""
    current_music: str = ""
    internet_connected: bool = True
    focused_app: str = ""


@dataclass(slots=True)
class CognitiveDecision:
    action: DecisionType
    tool_name: Optional[str] = None
    plan_steps: Optional[list[str]] = None
    confidence: float = 0.0
    voice_line: str = ""
    reasoning_trace: str = ""  # Internal only
    timestamp: float = field(default_factory=time.time)


# ==============================================================================
# 2. WORLD STATE MONITOR (The Eyes)
# ==============================================================================

class WorldStateMonitor:
    def __init__(self):
        self.state = SystemState()
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self):
        while self._running:
            try:
                self.state.cpu_percent = psutil.cpu_percent(interval=0.1)
                self.state.ram_percent = psutil.virtual_memory().percent
                if psutil.sensors_battery():
                    self.state.battery_percent = psutil.sensors_battery().percent
            except Exception:
                pass
            await asyncio.sleep(1.0)

    def get_snapshot(self) -> SystemState:
        return self.state


# ==============================================================================
# 3. MEMORY ENGINE (The Experience)
# ==============================================================================

class MemoryEngine:
    def __init__(self, path: str = "heart_memory.json"):
        self.path = path
        self.preferences: dict[str, float] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    data = json.load(f)
                    self.preferences.update(data.get("preferences", {}))
            except:
                pass

    def record_success(self, tool_name: str):
        self.preferences[tool_name] = self.preferences.get(tool_name, 0) + 0.1
        self._save()

    def record_failure(self, tool_name: str, reason: str):
        self.preferences[tool_name] = max(0, self.preferences.get(tool_name, 0) - 0.2)
        self._save()

    def get_preferences(self, category: str) -> dict:
        return {k: v for k, v in self.preferences.items() if category in k}

    def _save(self):
        with open(self.path, 'w') as f:
            json.dump({"preferences": self.preferences}, f)


# ==============================================================================
# 4. TOOL REGISTRY & SELECTOR (The Hands)
# ==============================================================================

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}

    def register(self, metadata: ToolMetadata):
        self._tools[metadata.name] = metadata

    def get_all(self) -> list[ToolMetadata]:
        return list(self._tools.values())

    def score_tool(self, tool: ToolMetadata, context: dict, memory_weights: dict) -> float:
        score = tool.priority
        if tool.name in memory_weights:
            score += memory_weights[tool.name] * 2.0
        if tool.risk_level == RiskLevel.HIGH:
            score -= 5.0
        elif tool.risk_level == RiskLevel.CRITICAL:
            score -= 10.0
        score += tool.success_rate
        if context.get("battery_low") and "power_save" in tool.tags:
            score += 3.0
        return score


# ==============================================================================
# 5. POLICY ENGINE (The Guardian)
# ==============================================================================

class PolicyEngine:
    BLOCKED_ACTIONS = {"format_drive", "delete_system32", "rm_rf_root"}
    CONFIRMATION_REQUIRED = {"shutdown", "restart", "delete_all", "send_email", "system_control"}

    def evaluate(self, tool: ToolMetadata, command: str) -> CognitiveDecision:
        cmd_lower = command.lower()
        if tool.name in self.BLOCKED_ACTIONS:
            return CognitiveDecision(
                action=DecisionType.BLOCK,
                voice_line="Yeh action permanently blocked hai safety reasons ki wajah se.",
                reasoning_trace=f"Blocked by policy: {tool.name}"
            )
        if tool.name in self.CONFIRMATION_REQUIRED or tool.risk_level >= RiskLevel.HIGH:
            return CognitiveDecision(
                action=DecisionType.CONFIRM,
                tool_name=tool.name,
                voice_line=f"Dark, yeh {tool.risk_level.name} risk action hai. Confirm karo?",
                reasoning_trace="Requires confirmation due to risk level"
            )
        return CognitiveDecision(action=DecisionType.EXECUTE, tool_name=tool.name)


# ==============================================================================
# 6. CONTEXT ENGINE (The Awareness)
# ==============================================================================

class ContextEngine:
    def __init__(self, world_state: WorldStateMonitor):
        self.world_state = world_state

    def get_current_context(self, raw_input: str) -> dict:
        state = self.world_state.get_snapshot()
        ctx = {
            "cpu_load": state.cpu_percent,
            "battery_low": state.battery_percent is not None and state.battery_percent < 20,
            "internet": state.internet_connected,
            "raw_input": raw_input
        }
        if "music" in raw_input.lower():
            ctx["intent_category"] = "music"
        elif "code" in raw_input.lower():
            ctx["intent_category"] = "coding"
        else:
            ctx["intent_category"] = "general"
        return ctx


# ==============================================================================
# 7. MASTER BRAIN ORCHESTRATOR
# ==============================================================================

class HeartBrain:
    def __init__(self):
        self.world_state = WorldStateMonitor()
        self.registry = ToolRegistry()
        self.policy = PolicyEngine()
        self.context = ContextEngine(self.world_state)
        self.memory = MemoryEngine()

    async def initialize(self):
        await self.world_state.start()

    async def think(self, raw_input: str) -> CognitiveDecision:
        """Main cognitive loop. Target: <20ms"""
        ctx = self.context.get_current_context(raw_input)
        mem_weights = self.memory.get_preferences(ctx.get("intent_category", "general"))

        candidates = []
        for tool in self.registry.get_all():
            score = self.registry.score_tool(tool, ctx, mem_weights)
            candidates.append((score, tool))

        candidates.sort(key=lambda x: x[0], reverse=True)

        if not candidates or candidates[0][0] < 0.3:
            return CognitiveDecision(
                action=DecisionType.CLARIFY,
                voice_line="Mujhe samajh nahi aaya. Kya tum thoda detail mein bata sakte ho?",
                confidence=0.2
            )

        best_score, best_tool = candidates[0]
        decision = self.policy.evaluate(best_tool, raw_input)
        decision.confidence = min(best_score, 1.0)

        if decision.action == DecisionType.EXECUTE:
            if decision.confidence < 0.75:
                decision.action = DecisionType.CONFIRM
                decision.voice_line = f"Main {best_tool.name} use karne wali hoon, par sure nahi hoon. Sahi hai?"

        return decision

    async def execute(self, decision: CognitiveDecision, params: dict) -> str:
        """Execution Manager with Observation & Reflection"""
        if decision.action != DecisionType.EXECUTE:
            return decision.voice_line

        tool = self.registry._tools.get(decision.tool_name)
        if not tool:
            return "Tool not found."

        try:
            result = await asyncio.wait_for(tool.handler(**params), timeout=10.0)
            self.memory.record_success(tool.name)
            return result
        except asyncio.TimeoutError:
            self.memory.record_failure(tool.name, "timeout")
            return f"{tool.name} timed out. Trying fallback..."
        except Exception as e:
            self.memory.record_failure(tool.name, str(e))
            return f"Error: {str(e)}"