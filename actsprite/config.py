"""All tunable numbers live here: endpoints, prices, thresholds, weights."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Meta Model API -------------------------------------------------------
BASE_URL = "https://api.meta.ai/v1"
API_KEY_ENV = "META_API_KEY"
MODEL_SAM = "sam-3.1"
MODEL_IMAGE = "muse-image-1.0"
MODEL_CRITIC = "muse-spark-1.3"

REQUEST_TIMEOUT_S = 300.0  # image generation with reasoning can be slow
MAX_RETRIES = 2  # SDK retries 429/5xx with backoff

# Prices in USD (dev.meta.ai/docs/pricing-rate-limits, checked 2026-10-28)
PRICE_SAM_IMAGE = 2.50 / 1000
PRICE_SAM_VIDEO_FRAME = 0.20 / 1000
SAM_VIDEO_MIN_FRAMES = 50
PRICE_IMAGE = 0.01
PRICE_CRITIC_INPUT_TOKEN = 1.25 / 1_000_000
PRICE_CRITIC_OUTPUT_TOKEN = 4.25 / 1_000_000
CRITIC_EST_INPUT_TOKENS = 6000  # used only for the pre-call estimate
CRITIC_EST_OUTPUT_TOKENS = 400

BUDGET_HARD_STOP_USD = 140.0

CACHE_DIR = ROOT / "cache"
COST_LOG = ROOT / "logs" / "cost.csv"

# --- Muse Image -----------------------------------------------------------
IMAGE_SIZE = "1024x1024"  # sets aspect ratio only
IMAGE_REASONING = "high"
IMAGE_FORMAT = "png"

# --- Pipeline -------------------------------------------------------------
EXTRACT_FPS = 12
FRAMES_PER_ACTION = 8
CELL_SIZE = 256
CELL_MARGIN = 12  # px kept free above the head and at the sides
GUIDE_SIZE = 512  # pose guide image sent to Muse Image
PALETTE_SIZE = 24

# --- Verification loop (provisional, calibrate on Day 1 / 10-30) -----------
IOU_MIN = 0.70
IDENTITY_MIN = 7
PALETTE_DRIFT_MAX = 0.15
PALETTE_MATCH_DISTANCE = 40.0  # RGB distance that still counts as "in palette"
MAX_REGENERATIONS = 2
SCORE_WEIGHT_IOU = 0.4
SCORE_WEIGHT_IDENTITY = 0.4
SCORE_WEIGHT_PALETTE = 0.2
