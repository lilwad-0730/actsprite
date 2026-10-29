"""Meta Model API wrapper: one place for timeouts, retries, caching and cost logging.

Every paid call goes through `MetaClient._call`, which
1. returns a cached response when the exact same request was made before (no charge),
2. refuses to run if the running total would pass the hard budget stop,
3. appends the real cost to logs/cost.csv.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from actsprite import config

COST_FIELDS = ["timestamp", "model", "operation", "units", "cost_usd", "cached", "latency_s", "note"]

# A prompt part is either text or an image (PNG/JPEG/WebP bytes).
Part = str | bytes


class MissingApiKey(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class CostLog:
    """Append-only CSV of every API call and its cost. Safe to share between threads."""

    _lock = threading.Lock()  # one lock for every log, so parallel redraws never interleave rows

    def __init__(self, path: Path = config.COST_LOG) -> None:
        self.path = path

    def total(self) -> float:
        with self._lock:
            if not self.path.exists():
                return 0.0
            with self.path.open(newline="", encoding="utf-8") as f:
                return sum(float(row["cost_usd"]) for row in csv.DictReader(f))

    def append(
        self,
        model: str,
        operation: str,
        units: float,
        cost_usd: float,
        cached: bool,
        latency_s: float,
        note: str = "",
    ) -> None:
        with self._lock:
            self._append_row(model, operation, units, cost_usd, cached, latency_s, note)

    def _append_row(
        self, model: str, operation: str, units: float, cost_usd: float, cached: bool, latency_s: float, note: str
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COST_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "model": model,
                    "operation": operation,
                    "units": units,
                    "cost_usd": f"{cost_usd:.6f}",
                    "cached": int(cached),
                    "latency_s": f"{latency_s:.2f}",
                    "note": note,
                }
            )


def request_key(payload: dict[str, Any]) -> str:
    """Stable hash of a request body, used as the cache key."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()
    return hashlib.sha256(blob).hexdigest()


def sniff_mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        return "video/mp4"
    raise ValueError("Unknown media type: pass PNG, JPEG, WebP or MP4 bytes.")


def data_url(data: bytes, mime: str | None = None) -> str:
    return f"data:{mime or sniff_mime(data)};base64,{base64.b64encode(data).decode()}"


def response_text(data: dict[str, Any]) -> str:
    """Concatenate all output_text parts of a Responses API result."""
    chunks: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                chunks.append(part.get("text") or "")
    return "".join(chunks)


def response_images(data: dict[str, Any]) -> list[bytes]:
    return [
        base64.b64decode(item["result"])
        for item in data.get("output") or []
        if item.get("type") == "image_generation_call" and item.get("result")
    ]


def _parts_to_content(parts: Sequence[Part]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    for part in parts:
        if isinstance(part, str):
            content.append({"type": "input_text", "text": part})
        else:
            content.append({"type": "input_image", "image_url": data_url(part)})
    return content


def critic_cost(data: dict[str, Any]) -> float:
    usage = data.get("usage") or {}
    return (usage.get("input_tokens") or 0) * config.PRICE_CRITIC_INPUT_TOKEN + (
        usage.get("output_tokens") or 0
    ) * config.PRICE_CRITIC_OUTPUT_TOKEN


def estimate_sam_video_cost(frame_count: int) -> float:
    return max(frame_count, config.SAM_VIDEO_MIN_FRAMES) * config.PRICE_SAM_VIDEO_FRAME


@dataclass
class CallResult:
    data: dict[str, Any]
    cost_usd: float
    latency_s: float
    cached: bool


class MetaClient:
    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path = config.CACHE_DIR,
        cost_log: CostLog | None = None,
        budget_usd: float = config.BUDGET_HARD_STOP_USD,
    ) -> None:
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv(config.ROOT / ".env")
        key = api_key or os.environ.get(config.API_KEY_ENV, "").strip()
        if not key:
            raise MissingApiKey(
                f"{config.API_KEY_ENV} is not set. Copy {config.ROOT / '.env.example'} to "
                f"{config.ROOT / '.env'} and paste your Meta Model API key after '{config.API_KEY_ENV}='."
            )
        self._client = OpenAI(
            base_url=config.BASE_URL,
            api_key=key,
            timeout=config.REQUEST_TIMEOUT_S,
            max_retries=config.MAX_RETRIES,
        )
        self.cache_dir = cache_dir
        self.cost_log = cost_log or CostLog()
        self.budget_usd = budget_usd

    # ------------------------------------------------------------------ core
    def check_budget(self, estimate_usd: float) -> None:
        spent = self.cost_log.total()
        if spent + estimate_usd > self.budget_usd:
            raise BudgetExceeded(
                f"Spent ${spent:.2f}; this call (~${estimate_usd:.2f}) would pass the "
                f"${self.budget_usd:.0f} hard stop. Raise BUDGET_HARD_STOP_USD in config.py only if intended."
            )

    def _call(
        self,
        payload: dict[str, Any],
        *,
        operation: str,
        estimate_usd: float,
        units: float,
        cost_fn: Callable[[dict[str, Any]], float],
        note: str = "",
    ) -> CallResult:
        key = request_key(payload)
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            self.cost_log.append(payload["model"], operation, units, 0.0, True, 0.0, note)
            return CallResult(data, 0.0, 0.0, True)

        self.check_budget(estimate_usd)
        t0 = time.perf_counter()
        response = self._client.responses.create(**payload)
        latency = time.perf_counter() - t0
        data = response.model_dump(mode="json")
        cost = cost_fn(data)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data), encoding="utf-8")
        self.cost_log.append(payload["model"], operation, units, cost, False, latency, note)
        return CallResult(data, cost, latency, False)

    # ------------------------------------------------------------- models
    def list_models(self) -> list[str]:
        """Free call, used as a key / connectivity check."""
        return sorted(m.id for m in self._client.models.list())

    def segment(
        self,
        media: bytes,
        prompt: str,
        *,
        video_frame_count: int | None = None,
        note: str = "",
    ) -> tuple[str, CallResult]:
        """Run SAM 3.1 on an image or MP4 clip; returns the raw segmentation text."""
        mime = sniff_mime(media)
        is_video = mime.startswith("video/")
        if is_video:
            if video_frame_count is None:
                raise ValueError("Pass video_frame_count so the SAM video cost can be estimated.")
            media_part = {"type": "input_video", "video_url": data_url(media, mime)}
            cost = estimate_sam_video_cost(video_frame_count)
            units = float(video_frame_count)
        else:
            media_part = {"type": "input_image", "image_url": data_url(media, mime)}
            cost = config.PRICE_SAM_IMAGE
            units = 1.0
        payload = {
            "model": config.MODEL_SAM,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}, media_part],
                }
            ],
            "metadata": {"mask_encoding": "one_bit"},
            "store": False,
        }
        result = self._call(
            payload,
            operation="segment_video" if is_video else "segment_image",
            estimate_usd=cost,
            units=units,
            cost_fn=lambda _data: cost,
            note=note,
        )
        return response_text(result.data), result

    def generate_image(
        self,
        parts: Sequence[Part],
        *,
        size: str = config.IMAGE_SIZE,
        reasoning: str = config.IMAGE_REASONING,
        note: str = "",
    ) -> tuple[bytes, CallResult]:
        """Muse Image via the Responses API with interleaved text and reference images.

        Web/image search and the shell tool are off: we never want outside
        references leaking into an original character.
        """
        payload = {
            "model": config.MODEL_IMAGE,
            "input": [{"role": "user", "content": _parts_to_content(parts)}],
            "tools": [
                {
                    "type": "image_generation",
                    "enable_image_search": False,
                    "enable_web_search": False,
                    "enable_shell": False,
                    "reasoning_strength": reasoning,
                    "size": size,
                    "output_format": config.IMAGE_FORMAT,
                }
            ],
            "store": False,
        }
        result = self._call(
            payload,
            operation="generate_image",
            estimate_usd=config.PRICE_IMAGE,
            units=1.0,
            cost_fn=lambda data: config.PRICE_IMAGE * max(1, len(response_images(data))),
            note=note,
        )
        images = response_images(result.data)
        if not images:
            raise RuntimeError(
                "Muse Image returned no image. Response text: " + response_text(result.data)[:500]
            )
        return images[0], result

    def critic(
        self,
        parts: Sequence[Part],
        schema: dict[str, Any],
        *,
        schema_name: str = "critique",
        note: str = "",
    ) -> tuple[dict[str, Any], CallResult]:
        """Muse Spark 1.3 with images in, strict JSON out."""
        estimate = (
            config.CRITIC_EST_INPUT_TOKENS * config.PRICE_CRITIC_INPUT_TOKEN
            + config.CRITIC_EST_OUTPUT_TOKENS * config.PRICE_CRITIC_OUTPUT_TOKEN
        )
        payload = {
            "model": config.MODEL_CRITIC,
            "input": [{"role": "user", "content": _parts_to_content(parts)}],
            "text": {
                "format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}
            },
            "store": False,
        }
        result = self._call(
            payload,
            operation="critic",
            estimate_usd=estimate,
            units=1.0,
            cost_fn=critic_cost,
            note=note,
        )
        return parse_json_reply(response_text(result.data)), result


def parse_json_reply(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating a markdown fence around it."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else body
        body = body.rsplit("```", 1)[0]
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"Critic reply has no JSON object: {text[:300]!r}")
    return json.loads(body[start : end + 1])
