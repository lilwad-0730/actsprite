"""Spike 0: is the key valid, are the three models enabled, does structured output work?

Run: .venv\\Scripts\\python -m spikes.spike_0_smoke
Cost: list_models is free; one tiny Muse Spark call (< $0.001).
"""

from __future__ import annotations

from actsprite import config
from actsprite.meta_client import MetaClient
from spikes.common import OUT, estimate, write_json


def main() -> None:
    client = MetaClient()
    models = client.list_models()
    needed = [config.MODEL_SAM, config.MODEL_IMAGE, config.MODEL_CRITIC]
    missing = [m for m in needed if m not in models]
    print("models enabled:", ", ".join(models))
    print("missing:", missing or "none")

    estimate("1 Muse Spark structured-output call", 0.001)
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "model": {"type": "string"}},
        "required": ["ok", "model"],
        "additionalProperties": False,
    }
    reply, result = client.critic(
        ['Reply with {"ok": true, "model": "<your model name>"}.'], schema, schema_name="smoke", note="spike0"
    )
    print("critic reply:", reply, f"cost=${result.cost_usd:.5f} latency={result.latency_s:.1f}s")
    print("spent so far:", f"${client.cost_log.total():.4f}")
    write_json(OUT / "0_smoke" / "summary.json", {"models": models, "missing": missing, "critic_reply": reply,
                                                  "usage": result.data.get("usage")})


if __name__ == "__main__":
    main()
