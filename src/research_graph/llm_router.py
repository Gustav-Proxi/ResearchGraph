from __future__ import annotations

import json
import os
from typing import Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


OPENAI_COMPATIBLE = {
    "openai",
    "groq",
    "together",
    "fireworks",
    "openrouter",
    "cerebras",
    "sambanova",
    "lm-studio",
    "vllm",
    "custom-openai-compatible",
}


class LLMRouter:
    def __init__(self, settings: Dict[str, object]) -> None:
        self.settings = settings

    def generate_stage_text(self, stage_id: str, stage_name: str, role: str, context: Dict[str, object]) -> Dict[str, str]:
        provider, model = self._resolve_route(stage_id, role)
        prompt = _build_prompt(stage_name, role, context)

        if provider == "ollama":
            return self._ollama_generate(model, prompt)
        if provider in OPENAI_COMPATIBLE:
            return self._openai_compatible_generate(provider, model, prompt)
        return {
            "provider": provider,
            "model": model,
            "mode": "fallback",
            "text": "",
            "error": f"Provider {provider} is not wired for direct runtime generation yet.",
        }

    def _resolve_route(self, stage_id: str, role: str) -> tuple[str, str]:
        provider = str(self.settings.get("primary_provider", "openai"))
        model = str(self.settings.get("primary_model", "gpt-4.1"))
        routing = self.settings.get("stage_model_routing", {}) or {}
        if not isinstance(routing, dict) or not routing.get("enabled"):
            return provider, model
        routes = routing.get("routes", {}) or {}
        if not isinstance(routes, dict):
            return provider, model
        stage_route = routes.get(stage_id)
        role_route = routes.get(role)
        default_route = routes.get("default")
        for route in [stage_route, role_route, default_route]:
            if isinstance(route, dict) and route.get("provider") and route.get("model"):
                return str(route["provider"]), str(route["model"])
        return provider, model

    def _ollama_generate(self, model: str, prompt: str) -> Dict[str, str]:
        base_url = str(self.settings.get("ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
        payload = {"model": model, "prompt": prompt, "stream": False}
        request = Request(
            f"{base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
            return {
                "provider": "ollama",
                "model": model,
                "mode": "live",
                "text": raw.get("response", "").strip(),
                "error": "",
            }
        except Exception as exc:
            return {
                "provider": "ollama",
                "model": model,
                "mode": "fallback",
                "text": "",
                "error": str(exc),
            }

    def _openai_compatible_generate(self, provider: str, model: str, prompt: str) -> Dict[str, str]:
        base_url = self._base_url_for_provider(provider)
        api_key = self._api_key_for_provider(provider)
        if not base_url:
            return {
                "provider": provider,
                "model": model,
                "mode": "fallback",
                "text": "",
                "error": f"No base URL configured for provider {provider}.",
            }
        if provider not in {"lm-studio", "vllm", "custom-openai-compatible"} and not api_key:
            return {
                "provider": provider,
                "model": model,
                "mode": "fallback",
                "text": "",
                "error": f"No API key available for provider {provider}.",
            }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are helping an end-to-end research operating system. Be concise, concrete, and structured."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                raw = json.loads(response.read().decode("utf-8"))
            text = (
                raw.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return {
                "provider": provider,
                "model": model,
                "mode": "live",
                "text": text,
                "error": "",
            }
        except Exception as exc:
            return {
                "provider": provider,
                "model": model,
                "mode": "fallback",
                "text": "",
                "error": str(exc),
            }

    def _base_url_for_provider(self, provider: str) -> str:
        settings = self.settings
        mapping = {
            "openai": "https://api.openai.com/v1",
            "groq": "https://api.groq.com/openai/v1",
            "together": "https://api.together.xyz/v1",
            "fireworks": "https://api.fireworks.ai/inference/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "cerebras": "https://api.cerebras.ai/v1",
            "sambanova": "https://api.sambanova.ai/v1",
            "lm-studio": str(settings.get("lm_studio_base_url", "")),
            "vllm": str(settings.get("custom_openai_base_url", "")),
            "custom-openai-compatible": str(settings.get("custom_openai_base_url", "")),
        }
        return mapping.get(provider, "")

    def _api_key_for_provider(self, provider: str) -> str:
        providers_config = self.settings.get("providers_config", {}) or {}
        if isinstance(providers_config, dict):
            entry = providers_config.get(provider, {})
            if isinstance(entry, dict) and entry.get("api_key"):
                return str(entry["api_key"])
        env_mapping = {
            "openai": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY",
            "together": "TOGETHER_API_KEY",
            "fireworks": "FIREWORKS_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "sambanova": "SAMBANOVA_API_KEY",
        }
        env_var = env_mapping.get(provider)
        return os.getenv(env_var, "") if env_var else ""


def _build_prompt(stage_name: str, role: str, context: Dict[str, object]) -> str:
    # If tools.py passed a direct prompt, use it as-is
    if "__direct_prompt__" in context:
        return str(context["__direct_prompt__"])
    return (
        f"Stage: {stage_name}\n"
        f"Role: {role}\n"
        "Use the following JSON context to produce a concise structured contribution for the stage.\n"
        f"{json.dumps(context, indent=2)}\n"
        "Return short bullet-style content or a compact paragraph that can be embedded into the run artifacts."
    )
