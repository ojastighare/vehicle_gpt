"""Optional local Small Language Model (SLM) service integration.

Works with locally installed Ollama or llama.cpp OpenAI-compatible servers.
Never connects to external cloud AI APIs. Gracefully falls back when unavailable.
"""

import time
from typing import Any, Optional
import httpx

from backend.config import settings
from backend.schemas import EvidenceRecord

SYSTEM_PROMPT = """You are VehicleGPT, a privacy-preserving automotive edge assistant running inside the vehicle's electronic control architecture.
Answer the driver or service technician question strictly and only using the provided telemetry, event records, and computed statistics.

MANDATORY RULES:
1. Ground every claim directly in the supplied evidence. Cite exact timestamps, values, and engineering units.
2. NEVER invent, extrapolate, or hallucinate numerical values. All calculations provided in the prompt are authoritative.
3. Clearly distinguish between observed facts and correlations. Do NOT state that an event caused another event merely because it happened earlier unless verified diagnostic evidence exists.
4. If the evidence is insufficient or missing, explicitly state your uncertainty.
5. Keep your answer professional, concise, and structured.
"""


class LocalLLMService:
    """Manages communication with local Ollama or edge inference endpoints."""

    def __init__(
        self,
        base_url: str = settings.OLLAMA_BASE_URL,
        model_name: str = settings.OLLAMA_MODEL,
        timeout: float = settings.LLM_TIMEOUT_SECONDS,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout

    async def check_health(self) -> dict[str, Any]:
        """Verify whether local Ollama or llama.cpp service is currently running."""
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    models = [m.get("name") for m in res.json().get("models", [])]
                    model_present = any(self.model_name in m for m in models)
                    return {
                        "available": True,
                        "configured_model": self.model_name,
                        "model_installed": model_present,
                        "detected_models": models,
                    }
        except Exception:
            pass

        return {
            "available": False,
            "configured_model": self.model_name,
            "model_installed": False,
            "detected_models": [],
        }

    async def generate_explanation(
        self,
        question: str,
        intent: str,
        deterministic_summary: str,
        evidence: list[EvidenceRecord],
        stats: dict[str, Any],
    ) -> tuple[Optional[str], float]:
        """Send prompt with structured evidence to local SLM.

        Returns (explanation_text, latency_ms). If unavailable or fails, returns (None, latency_ms).
        """
        start_time = time.perf_counter()

        # Format evidence as structured context
        evidence_lines = []
        for e in evidence[:12]:
            val_str = f"{e.value} {e.unit}" if e.value is not None else ""
            desc = e.details or e.label
            evidence_lines.append(f"- [{e.timestamp}] {e.record_type.upper()}: {desc} {val_str}".strip())

        evidence_text = "\n".join(evidence_lines) if evidence_lines else "No specific records found."

        user_prompt = f"""Question: {question}
Detected Intent: {intent}

Authoritative Computed Analytics:
{deterministic_summary}

Supporting Vehicle Evidence:
{evidence_text}

Provide an evidence-grounded, clear explanation for the driver or service engineer:"""

        payload = {
            "model": self.model_name,
            "system": SYSTEM_PROMPT,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,  # Low temperature for strict factual adherence
                "top_p": 0.9,
                "num_predict": 256,
            },
        }

        url = f"{self.base_url}/api/generate"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                if response.status_code == 200:
                    data = response.json()
                    text = data.get("response", "").strip()
                    if text:
                        return text, elapsed_ms
        except Exception:
            pass

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return None, elapsed_ms


local_llm_service = LocalLLMService()
