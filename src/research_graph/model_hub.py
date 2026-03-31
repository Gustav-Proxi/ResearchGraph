from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import subprocess
import threading
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4


@dataclass
class ProviderSpec:
    id: str
    name: str
    category: str
    api_style: str
    supports: List[str]
    setup_fields: List[str]
    model_hints: List[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class LocalModelPreset:
    id: str
    name: str
    model: str
    provider: str
    model_type: str
    size_hint: str
    description: str
    install_method: str = "ollama"
    source_url: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class InstallJob:
    id: str
    model: str
    provider: str
    status: str
    log: str = ""
    created_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class ModelHub:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._data_dir = root / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._settings_path = self._data_dir / "model_hub.json"
        self._lock = threading.Lock()
        self._jobs: Dict[str, InstallJob] = {}
        self._providers = _provider_specs()
        self._local_presets = _local_presets()
        self._embedding_presets = _embedding_presets()
        self._settings = self._load_settings()

    def catalog(self) -> Dict[str, object]:
        return {
            "providers": [provider.to_dict() for provider in self._providers],
            "local_model_presets": [preset.to_dict() for preset in self._local_presets],
            "embedding_presets": [preset.to_dict() for preset in self._embedding_presets],
        }

    def settings(self) -> Dict[str, object]:
        return _sanitize_settings(self._settings)

    def runtime_settings(self) -> Dict[str, object]:
        return deepcopy(self._settings)

    def update_settings(self, payload: Dict[str, object]) -> Dict[str, object]:
        with self._lock:
            for key in [
                "primary_provider",
                "primary_model",
                "embedding_provider",
                "embedding_model",
                "ollama_base_url",
                "lm_studio_base_url",
                "custom_openai_base_url",
                "providers_config",
                "stage_model_routing",
            ]:
                if key in payload:
                    self._settings[key] = payload[key]
            self._persist_settings()
            return deepcopy(self._settings)

    def add_custom_model(self, payload: Dict[str, str]) -> Dict[str, object]:
        item = {
            "id": "custom-" + uuid4().hex[:8],
            "provider": payload.get("provider", "custom-openai-compatible"),
            "name": payload.get("name", "").strip(),
            "model": payload.get("model", "").strip(),
            "model_type": payload.get("model_type", "chat").strip() or "chat",
            "notes": payload.get("notes", "").strip(),
        }
        if not item["name"] or not item["model"]:
            raise ValueError("Custom model requires name and model.")
        with self._lock:
            models = self._settings.setdefault("custom_models", [])
            for existing in models:
                if (
                    existing.get("provider") == item["provider"]
                    and existing.get("model") == item["model"]
                    and existing.get("model_type") == item["model_type"]
                ):
                    existing["name"] = item["name"]
                    existing["notes"] = item["notes"]
                    self._persist_settings()
                    return deepcopy(existing)
            models.append(item)
            self._settings["custom_models"] = _dedupe_custom_models(models)
            self._persist_settings()
        return item

    def list_install_jobs(self) -> List[Dict[str, object]]:
        with self._lock:
            jobs = [job.to_dict() for job in self._jobs.values()]
        return sorted(jobs, key=lambda item: item["created_at"], reverse=True)

    def start_ollama_install(self, model: str) -> Dict[str, object]:
        job = InstallJob(
            id="job-" + uuid4().hex[:10],
            model=model,
            provider="ollama",
            status="queued",
            created_at=_utc_now(),
        )
        with self._lock:
            self._jobs[job.id] = job
        thread = threading.Thread(target=self._run_ollama_pull, args=(job.id, model), daemon=True)
        thread.start()
        return job.to_dict()

    def ollama_status(self, base_url: Optional[str] = None) -> Dict[str, object]:
        url = (base_url or self._settings.get("ollama_base_url") or "http://127.0.0.1:11434").rstrip("/")
        request = Request(f"{url}/api/tags", method="GET")
        try:
            with urlopen(request, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = payload.get("models", [])
            return {
                "reachable": True,
                "base_url": url,
                "installed_models": [
                    {
                        "name": item.get("name", ""),
                        "size": item.get("size", 0),
                        "modified_at": item.get("modified_at", ""),
                    }
                    for item in models
                ],
            }
        except URLError as exc:
            return {
                "reachable": False,
                "base_url": url,
                "installed_models": [],
                "error": str(getattr(exc, "reason", exc)),
            }
        except Exception as exc:
            return {
                "reachable": False,
                "base_url": url,
                "installed_models": [],
                "error": str(exc),
            }

    def connect_ollama(self, base_url: str) -> Dict[str, object]:
        status = self.ollama_status(base_url=base_url)
        with self._lock:
            self._settings["ollama_base_url"] = base_url
            self._persist_settings()
        return status

    def dashboard_state(self) -> Dict[str, object]:
        return {
            "catalog": self.catalog(),
            "settings": self.settings(),
            "ollama": self.ollama_status(),
            "install_jobs": self.list_install_jobs(),
        }

    def _load_settings(self) -> Dict[str, object]:
        if self._settings_path.exists():
            settings = json.loads(self._settings_path.read_text(encoding="utf-8"))
            settings["custom_models"] = _dedupe_custom_models(settings.get("custom_models", []))
            settings.setdefault("stage_model_routing", {"enabled": False, "routes": {}})
            self._settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
            return settings
        settings = {
            "primary_provider": "openai",
            "primary_model": "gpt-4.1",
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "ollama_base_url": "http://127.0.0.1:11434",
            "lm_studio_base_url": "http://127.0.0.1:1234/v1",
            "custom_openai_base_url": "http://127.0.0.1:8001/v1",
            "providers_config": {},
            "stage_model_routing": {
                "enabled": False,
                "routes": {},
            },
            "custom_models": [],
        }
        self._settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        return settings

    def _persist_settings(self) -> None:
        self._settings_path.write_text(json.dumps(self._settings, indent=2), encoding="utf-8")

    def _run_ollama_pull(self, job_id: str, model: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.log = f"Starting ollama pull for {model}\n"
        try:
            process = subprocess.run(
                ["ollama", "pull", model],
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
            with self._lock:
                job = self._jobs[job_id]
                job.log += (process.stdout or "") + (process.stderr or "")
                job.status = "completed" if process.returncode == 0 else "failed"
                job.finished_at = _utc_now()
        except FileNotFoundError:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.log += "Ollama CLI not found on PATH.\n"
                job.finished_at = _utc_now()
        except subprocess.TimeoutExpired:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.log += "Install timed out after 30 minutes.\n"
                job.finished_at = _utc_now()
        except Exception as exc:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.log += f"{exc}\n"
                job.finished_at = _utc_now()


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dedupe_custom_models(items: List[Dict[str, object]]) -> List[Dict[str, object]]:
    seen = {}
    for item in items:
        key = (
            item.get("provider", ""),
            item.get("model", ""),
            item.get("model_type", ""),
        )
        seen[key] = item
    return list(seen.values())


def _sanitize_settings(settings: Dict[str, object]) -> Dict[str, object]:
    payload = deepcopy(settings)
    providers_config = payload.get("providers_config", {}) or {}
    if isinstance(providers_config, dict):
        sanitized = {}
        for provider, entry in providers_config.items():
            if isinstance(entry, dict):
                sanitized[provider] = {
                    key: ("configured" if key == "api_key" and value else value)
                    for key, value in entry.items()
                }
            else:
                sanitized[provider] = entry
        payload["providers_config"] = sanitized
    return payload


def _provider_specs() -> List[ProviderSpec]:
    return [
        ProviderSpec("openai", "OpenAI", "cloud", "native", ["chat", "reasoning", "vision", "embeddings"], ["api_key"], ["gpt-4.1", "gpt-4o", "o4-mini"], "Frontier hosted models and embeddings."),
        ProviderSpec("anthropic", "Anthropic", "cloud", "native", ["chat", "reasoning", "vision"], ["api_key"], ["Claude Sonnet", "Claude Opus", "Claude Haiku"], "Claude family models."),
        ProviderSpec("google", "Google Gemini", "cloud", "native", ["chat", "reasoning", "vision", "embeddings"], ["api_key"], ["Gemini 2.5 Pro", "Gemini 2.5 Flash"], "Gemini API and multimodal models."),
        ProviderSpec("azure-openai", "Azure OpenAI", "cloud", "openai-compatible", ["chat", "reasoning", "embeddings"], ["api_key", "base_url", "api_version"], ["gpt-4.1", "gpt-4o"], "Azure-hosted OpenAI deployments."),
        ProviderSpec("aws-bedrock", "AWS Bedrock", "cloud", "native", ["chat", "embeddings"], ["access_key", "secret_key", "region"], ["Claude via Bedrock", "Llama", "Titan"], "Managed foundation models on AWS."),
        ProviderSpec("vertex-ai", "Vertex AI", "cloud", "native", ["chat", "vision", "embeddings"], ["project_id", "location", "credentials"], ["Gemini", "text embeddings"], "Google Cloud managed model access."),
        ProviderSpec("cohere", "Cohere", "cloud", "native", ["chat", "embeddings", "rerank"], ["api_key"], ["Command", "Embed"], "Cohere models and embeddings."),
        ProviderSpec("voyageai", "Voyage AI", "cloud", "native", ["embeddings", "rerank"], ["api_key"], ["voyage-large-2", "voyage-3-large"], "Embedding-first provider."),
        ProviderSpec("mistral", "Mistral", "cloud", "native", ["chat", "embeddings"], ["api_key"], ["Mistral Large", "Codestral"], "Mistral hosted models."),
        ProviderSpec("groq", "Groq", "cloud", "openai-compatible", ["chat", "reasoning"], ["api_key"], ["Llama", "Qwen", "DeepSeek"], "Low-latency inference."),
        ProviderSpec("together", "Together AI", "cloud", "openai-compatible", ["chat", "vision", "embeddings"], ["api_key"], ["Llama", "Qwen", "Mistral"], "Hosted open-weight models."),
        ProviderSpec("fireworks", "Fireworks AI", "cloud", "openai-compatible", ["chat", "vision", "embeddings"], ["api_key"], ["Llama", "DeepSeek", "Qwen"], "High-performance hosted inference."),
        ProviderSpec("openrouter", "OpenRouter", "cloud", "openai-compatible", ["chat", "reasoning", "vision"], ["api_key"], ["multi-provider routing"], "Unified access to many hosted providers."),
        ProviderSpec("deepseek", "DeepSeek", "cloud", "native", ["chat", "reasoning"], ["api_key"], ["DeepSeek Chat", "DeepSeek Reasoner"], "DeepSeek hosted APIs."),
        ProviderSpec("xai", "xAI", "cloud", "native", ["chat", "reasoning", "vision"], ["api_key"], ["Grok"], "xAI hosted models."),
        ProviderSpec("huggingface", "Hugging Face Inference", "cloud", "custom", ["chat", "embeddings"], ["api_key", "model"], ["serverless / endpoint"], "Inference Endpoints or HF serverless."),
        ProviderSpec("cerebras", "Cerebras", "cloud", "openai-compatible", ["chat", "reasoning"], ["api_key"], ["Llama", "Qwen"], "Fast hosted inference."),
        ProviderSpec("sambanova", "SambaNova", "cloud", "openai-compatible", ["chat", "reasoning"], ["api_key"], ["Meta and reasoning models"], "Hosted inference on SambaNova Cloud."),
        ProviderSpec("ollama", "Ollama", "local", "native", ["chat", "vision", "embeddings"], ["base_url"], ["llama3.2", "qwen2.5", "gemma3", "embeddinggemma"], "Run models locally and pull by click."),
        ProviderSpec("lm-studio", "LM Studio", "local", "openai-compatible", ["chat", "embeddings"], ["base_url"], ["openai-compatible local server"], "Connect to LM Studio local server."),
        ProviderSpec("vllm", "vLLM", "self-hosted", "openai-compatible", ["chat", "embeddings"], ["base_url"], ["self-hosted openai-compatible"], "Serve open-weight models yourself."),
        ProviderSpec("custom-openai-compatible", "Custom OpenAI-Compatible", "custom", "openai-compatible", ["chat", "reasoning", "vision", "embeddings"], ["base_url"], ["bring your own endpoint"], "Any service that speaks the OpenAI-style API."),
    ]


def _local_presets() -> List[LocalModelPreset]:
    return [
        LocalModelPreset("preset-llama32-1b", "Llama 3.2 1B", "llama3.2:1b", "ollama", "chat", "1.3GB", "Small multilingual local assistant model.", source_url="https://ollama.com/library/llama3.2:1b"),
        LocalModelPreset("preset-qwen25-05b", "Qwen 2.5 0.5B", "qwen2.5:0.5b", "ollama", "chat", "397MB", "Very small local chat model for lightweight experiments.", source_url="https://ollama.com/library/qwen2.5:0.5b"),
        LocalModelPreset("preset-gemma3-1b", "Gemma 3 1B", "gemma3:1b", "ollama", "chat", "815MB", "Compact Google open model for local use.", source_url="https://ollama.com/library/gemma3"),
        LocalModelPreset("preset-phi4-mini", "Phi 4 Mini", "phi4-mini", "ollama", "chat", "2.5GB", "Small reasoning-oriented local model.", source_url="https://ollama.com/library/phi4-mini"),
    ]


def _embedding_presets() -> List[LocalModelPreset]:
    return [
        LocalModelPreset("embed-nomic", "Nomic Embed Text", "nomic-embed-text", "ollama", "embeddings", "274MB", "Open embedding model for semantic search.", source_url="https://ollama.com/library/nomic-embed-text"),
        LocalModelPreset("embed-nomic-v2", "Nomic Embed Text v2 MoE", "nomic-embed-text-v2-moe", "ollama", "embeddings", "958MB", "Multilingual MoE embedding model.", source_url="https://ollama.com/library/nomic-embed-text-v2-moe"),
        LocalModelPreset("embed-gemma", "EmbeddingGemma", "embeddinggemma", "ollama", "embeddings", "338MB", "Small Google embedding model for local use.", source_url="https://ollama.com/library/embeddinggemma"),
        LocalModelPreset("embed-mxbai", "mxbai Embed Large", "mxbai-embed-large:v1", "ollama", "embeddings", "670MB", "High quality open embedding model.", source_url="https://ollama.com/library/mxbai-embed-large:v1"),
    ]
