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
GUIDE_FILL_GRAY = 205  # silhouette fill when the guide is drawn filled
GUIDE_HEAD_FRACTION = 0.18  # top share of the figure with interior lines removed (no faces)
PALETTE_SIZE = 24

# --- Verification loop (Day 1 values from spikes/REPORT.md; recalibrate 10-30) ---
IOU_MIN = 0.55  # silhouette IoU, height-normalised, feet aligned, with tolerance
IOU_TOLERANCE_PX = 6  # both silhouettes dilated by this much on a CELL_SIZE-high canvas
POSE_MIN = 7  # Muse Spark pose score
IDENTITY_MIN = 7  # Muse Spark identity score
PALETTE_DRIFT_MAX = 0.15
PALETTE_MATCH_DISTANCE = 40.0  # RGB distance that still counts as "in palette"
MAX_REGENERATIONS = 2
SCORE_WEIGHT_IOU = 0.3
SCORE_WEIGHT_POSE = 0.2
SCORE_WEIGHT_IDENTITY = 0.3
SCORE_WEIGHT_PALETTE = 0.2

# --- Cutout -----------------------------------------------------------------
CUTOUT_WHITE_TOLERANCE = 18  # pixels with min(R,G,B) > 255 - this count as background
CUTOUT_MIN_SPECK = 0.0005  # drop islands smaller than this share of the image

# --- Capture (video sent to SAM) ------------------------------------------------
SAM_VIDEO_MAX_SHORT_SIDE = 480  # px; the SAM mask decoder is pure Python (cost ~ pixels), 480 still gives a ~700 px tall figure
SAM_VIDEO_FPS = 30  # phone clips are often 60 fps; every 2nd frame is enough and halves the cost
FULL_BODY_EDGE_PX = 2  # a mask this close to the frame edge counts as cut off
FULL_BODY_MIN_FRAMES = 6  # shortest usable stretch with the whole body in frame
FULL_BODY_EDGES = ("top", "bottom", "left", "right")  # edges the subject must not touch

# --- Action window (one-shot actions such as jump/attack inside a longer clip) --------
ACTION_SMOOTH_S = 0.15  # moving-average width on the motion curve
ACTION_LEVEL = 0.25  # active = smoothed motion above median + this share of (max - median)
ACTION_MERGE_GAP_S = 0.3  # quiet gaps shorter than this stay inside one action (e.g. the airborne part)
ACTION_PAD_S = 0.1  # extra time kept before and after the action

# --- Keyframes ----------------------------------------------------------------
CYCLE_MIN_SIMILARITY = 0.75  # IoU with the first frame that closes a loop
CYCLE_MIN_FRAMES = 6
CYCLE_MAX_S = 2.5  # longest loop we look for (walk/run strides and idle bobs are shorter)
CYCLE_MIN_CHANGE = 0.08  # 1 - IoU the clip must reach at least once, or it is "standing still"
CYCLE_AWAY_SHARE = 0.5  # moved away = similarity fell by half of this clip's range
CYCLE_RETURN_SHARE = 0.35  # back = similarity within 35% of the range from a perfect match
