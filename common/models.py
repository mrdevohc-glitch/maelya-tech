"""Charge config/models.yaml et .env, construit les chat models LangChain a la demande.

C'est le SEUL endroit qui doit changer pour brancher un autre fournisseur de modele
(OpenAI, OpenRouter, etc.) sur un agent donne : modifier config/models.yaml, rien dans
le code des agents n'a besoin de bouger.
"""
from __future__ import annotations

import os
import random
import time
from functools import lru_cache

import yaml
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from common.paths import AGENTS_ROOT, CONFIG_DIR

_RETRY_ATTEMPTS = 4
_RETRY_BASE_DELAY_SECONDS = 2.0


def _with_retry(model, agent_name: str):
    """Ajoute une relance automatique sur `_generate` (l'appel reel au modele).

    Ne PAS utiliser Runnable.with_retry() ici : il renvoie un objet RunnableRetry qui n'a
    pas `.bind_tools`, ce qui casse create_react_agent (il appelle model.bind_tools(...)
    directement). En patchant `_generate` sur l'instance, le type reste ChatOpenAI et tout
    le reste (bind_tools, isinstance BaseChatModel, etc.) continue de fonctionner normalement.

    Necessaire car certaines passerelles (OpenRouter) renvoient parfois une erreur de
    surcharge temporaire du fournisseur dans un corps de reponse HTTP 200 (ex: "Upstream
    error ... Service temporarily overloaded") -- le retry integre du client HTTP ne se
    declenche pas dans ce cas puisqu'il ne regarde que le code de statut HTTP.
    """
    original_generate = model._generate

    def patched_generate(*args, **kwargs):
        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                return original_generate(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - on relance volontairement large ici
                last_exc = exc
                if attempt < _RETRY_ATTEMPTS - 1:
                    delay = _RETRY_BASE_DELAY_SECONDS * (2**attempt) + random.uniform(0, 1)
                    print(
                        f"[{agent_name}] appel modele echoue ({exc}), "
                        f"nouvelle tentative dans {delay:.1f}s ({attempt + 1}/{_RETRY_ATTEMPTS})..."
                    )
                    time.sleep(delay)
        raise last_exc

    model._generate = patched_generate
    return model

load_dotenv(AGENTS_ROOT / ".env")

_MODELS_CONFIG_PATH = CONFIG_DIR / "models.yaml"


@lru_cache(maxsize=1)
def _load_config() -> dict:
    with open(_MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_agent_config(agent_name: str) -> dict:
    config = _load_config()
    if agent_name not in config:
        raise KeyError(
            f"Aucune config pour l'agent '{agent_name}' dans {_MODELS_CONFIG_PATH}. "
            f"Agents connus: {sorted(config)}"
        )
    return config[agent_name]


@lru_cache(maxsize=None)
def get_model(agent_name: str):
    """Retourne une instance de chat model LangChain configuree pour cet agent.

    Le champ `model` de config/models.yaml suit le format "provider:model_id"
    (ex: "anthropic:claude-sonnet-5", "openai:gpt-5.1"). Deux champs optionnels
    permettent de router un agent vers une passerelle compatible OpenAI (OpenRouter,
    un serveur local, etc.) au lieu du vrai OpenAI :
    - `base_url` : URL de l'API compatible OpenAI (ex: "https://openrouter.ai/api/v1")
    - `api_key_env` : nom de la variable d'environnement (dans .env) contenant la cle
      de cette passerelle -- utiliser `model: "openai:<id-tel-que-la-passerelle-l-attend>"`
      avec ces deux champs pour passer par OpenRouter ou equivalent.
    """
    cfg = get_agent_config(agent_name)
    kwargs = {"max_tokens": cfg.get("max_tokens", 4000)}

    if "base_url" in cfg:
        kwargs["base_url"] = cfg["base_url"]
    if "api_key_env" in cfg:
        api_key = os.environ.get(cfg["api_key_env"])
        if not api_key:
            raise RuntimeError(
                f"Variable d'environnement '{cfg['api_key_env']}' manquante ou vide dans .env "
                f"(requise pour l'agent '{agent_name}' d'apres config/models.yaml)."
            )
        kwargs["api_key"] = api_key

    model = init_chat_model(cfg["model"], **kwargs)
    return _with_retry(model, agent_name)


def get_max_iterations(agent_name: str) -> int:
    return get_agent_config(agent_name).get("max_iterations", 15)
