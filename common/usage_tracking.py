"""Callback LangChain qui logge la consommation de tokens par agent dans output/usage.log,
quel que soit le projet cible en cours de traitement (log toujours au meme endroit)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_core.callbacks import BaseCallbackHandler

from common.paths import OUTPUT_DIR

_LOG_PATH = OUTPUT_DIR / "usage.log"


class UsageLogger(BaseCallbackHandler):
    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    def on_llm_end(self, response, **kwargs) -> None:
        for generation_list in response.generations:
            for generation in generation_list:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) if message else None
                if not usage:
                    continue
                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "agent": self.agent_name,
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                }
                _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def usage_callbacks(agent_name: str) -> list[BaseCallbackHandler]:
    return [UsageLogger(agent_name)]
