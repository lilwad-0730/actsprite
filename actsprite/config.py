"""All tunable numbers live here: endpoints, prices, thresholds, weights."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Meta Model API -------------------------------------------------------
BASE_URL = "https://api.meta.ai/v1"
API_KEY_ENV = "META_API_KEY"
OFFLINE_ENV = "ACTSPRITE_OFFLINE"  # "1": answer only from the cache, never call the API (replay, tests)
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
CRITIC_MEAN_USD = 0.022  # measured: mean of 161 critic calls (four images each), 10/29-10/30 runs

BUDGET_HARD_STOP_USD = 140.0

CACHE_DIR = ROOT / "cache"
COST_LOG = ROOT / "logs" / "cost.csv"

# --- Muse Image -----------------------------------------------------------
IMAGE_SIZE = "1024x1024"  # sets aspect ratio only
IMAGE_REASONING = "high"
IMAGE_FORMAT = "png"

# --- Pipeline -------------------------------------------------------------
EXTRACT_FPS = 12
FRAMES_PER_ACTION = 8  # spikes/ only; the pipeline uses FRAMES_IDLE / FRAMES_ACTION
CELL_SIZE = 256
CELL_MARGIN = 12  # px kept free above the head and at the sides
GUIDE_SIZE = 512  # pose guide image sent to Muse Image
GUIDE_FILL_GRAY = 205  # silhouette fill when the guide is drawn filled
GUIDE_HEAD_FRACTION = 0.18  # top share of the figure with interior lines removed (no faces)
# ...measured from the top of the head, not of the raised hands: limbs thinner than this share of the figure
# height are opened away before finding the top. 10/30 dance clip: with arms overhead the old band held only the
# hands and the face lines reached Muse Image; 0.06 and 0.08 both found the head on every saved keyframe.
GUIDE_LIMB_OPEN = 0.08
# Head direction (actsprite/head.py): SAM 3.1 tracks "face"; the face's place inside the head gives the turn.
# Checked by eye on the 10/30 dance clip: turns of about 45-60 degrees measured 0.20-0.31, facing the camera
# 0.00-0.14 (spikes/REPORT.md). Tilt is not estimated: the face mask's axis follows the jaw and neck once the
# head turns (it read 40-49 degrees on frames with little tilt).
SAM_FACE_PROMPT = "face"
HEAD_HEIGHT_SHARE = 0.14  # head = this share of the body height below the top of the head
HEAD_FACE_MIN_SHARE = 0.08  # face area / head area below this = no face seen (turned away)
HEAD_YAW_FRONT = 0.12  # face centre offset (share of the head half-width) below this = facing the viewer
HEAD_YAW_HALF = 0.20  # from here: three-quarter view; between FRONT and HALF: turned slightly
HEAD_YAW_PROFILE = 0.40  # from here: profile
GUIDE_FACE_GRAY = 140  # the face patch on the pose guide (darker than GUIDE_FILL_GRAY)
PALETTE_SIZE = 24
SPRITE_PIXEL_SIZE = 64  # pixel styles: the art is drawn at this resolution (the showcase look)
# Muse Image draws the figure at full canvas height in every frame, so an idle's up-down bob is lost in the redraw
# (10/31 refilmed idle: guide head moved 4.3-11.5% of the canvas, every redraw 2.9-3.5%). In these modes each
# redraw is squashed so its height follows its pose guide (pack.follow_guide_height); 10/31, user-approved for
# idle, then for one-shot actions (the knight's jump guides crouch to 79% of standing, every redraw stayed 90%+).
HEIGHT_FOLLOW_MODES = ("loop", "once", "span")
# Output contract (docs/02_product_spec.md 4.1-4.3): cell 128 for pixel art (each art pixel = 2x2), else CELL_SIZE;
# fps idle 8, every other action 15 (10/31, user-approved: 10 frames at 15 fps keep the clip's speed).
CELL_PIXEL_ART = 128
FPS_IDLE = 8
FPS_ACTION = 15
FRAMES_IDLE = 8  # default frames per action when --frames is not given
FRAMES_ACTION = 10
ACTION_ORDER = ("idle", "run", "walk", "jump", "attack")  # sheet rows; other actions follow alphabetically
# User settings (10/30, approved to go beyond the spec's 6-12 frames / 8-24 fps so a whole dance fits):
# frames per action and playback fps. "auto" fps plays the frames at the clip's own speed.
FRAMES_MIN = 2
FRAMES_MAX = 48
FPS_MIN = 1.0
FPS_MAX = 30.0
UNITY_IMPORTER = ROOT / "unity" / "ActSpriteImporter.cs"  # copied into the ZIP once it exists (10/31)

# --- Verification loop (Day 1 values from spikes/REPORT.md; recalibrate 10-30) ---
IOU_MIN = 0.55  # silhouette IoU, height-normalised, feet aligned, with tolerance
IOU_TOLERANCE_PX = 6  # both silhouettes dilated by this much on a CELL_SIZE-high canvas
POSE_MIN = 7  # Muse Spark pose score
IDENTITY_MIN = 7  # Muse Spark identity score
PALETTE_DRIFT_MAX = 0.15
PALETTE_MATCH_DISTANCE = 40.0  # RGB distance that still counts as "in palette"
MAX_REGENERATIONS = 2
# Anchor mode: frames 1-7 all refer to the approved frame 0, so they are redrawn at the same time.
# Muse Image allows 150 requests per minute per team (pricing-rate-limits page, checked 2026-10-30).
REDRAW_WORKERS = 7
# Legs copied from the previous frame (10/29 dog clip: 6 frozen frames passed IoU and the critic).
# leg motion = leg-zone change from the previous frame, redraw / pose guide. Copies measured <= 0.16,
# real moves >= 0.30 (pet, jump, attack: spikes/check_frozen_legs.py).
LEG_ZONE_SHARE = 0.35  # bottom share of the figure height counted as legs
LEG_MOTION_MIN = 0.25
LEG_MOTION_GUIDE_MIN = 0.10  # guide legs changed less than this (idle): nothing to check
# In-place loops (idle): the legs should stay as in frame 0, so frame 0 is sent whole and copying it is not a fault.
# 10/30 knight idle: guide legs moved 0.09-0.23 from frame 0 and copies of frame 0 were the best frames, while
# real copies elsewhere had guide changes of 0.24-0.98 (spikes/REPORT.md Day 4).
LEGS_STAY_MODES = ("loop",)
# ...but there the legs must not wander: a redraw whose legs moved from frame 0 more than the guide's legs did,
# plus this margin, is redrawn. 10/30 knight idle: frames holding the stance moved 0.02-0.06 (guide 0.09-0.23),
# frames that stepped or lunged moved 0.41-0.69.
LEG_STAY_MARGIN = 0.15
SCORE_WEIGHT_IOU = 0.3
SCORE_WEIGHT_POSE = 0.2
SCORE_WEIGHT_IDENTITY = 0.3
SCORE_WEIGHT_PALETTE = 0.2

# --- Cutout -----------------------------------------------------------------
CUTOUT_WHITE_TOLERANCE = 18  # pixels with min(R,G,B) > 255 - this count as background
CUTOUT_MIN_SPECK = 0.0005  # drop islands smaller than this share of the image
CUTOUT_LINE_GAP = 0.006  # line-art styles: outline breaks up to this share of image height are closed (~10 px at 1600)

# --- Capture (video sent to SAM) ------------------------------------------------
SAM_VIDEO_MAX_SHORT_SIDE = 480  # px; the SAM mask decoder is pure Python (cost ~ pixels), 480 still gives a ~700 px tall figure
SAM_VIDEO_FPS = 30  # phone clips are often 60 fps; every 2nd frame is enough and halves the cost
SAM_PARSE_WORKERS_MAX = 8  # decode processes for a SAM video (each loads OpenCV; 32 ran out of page file)
SAMPLE_FPS_MIN = 1.0  # --sample-fps range: frames per second of the clip sent to SAM 3.1 for tracking
SAMPLE_FPS_MAX = 60.0  # (never more than the clip has)
FULL_BODY_EDGE_PX = 2  # a mask this close to the frame edge counts as cut off
FULL_BODY_MIN_FRAMES = 6  # shortest usable stretch with the whole body in frame
FULL_BODY_EDGES = ("top", "bottom", "left", "right")  # edges the subject must not touch

# --- Web demo (Hugging Face Space) -----------------------------------------------------
DEMO_SPEND_CAP_USD = 40.0  # the public Space stops calling Meta models once its cost log reaches this
DEMO_MAX_CLIP_S = 5.0  # only the first seconds of an upload are used
DEMO_SAM_FPS = 30  # frames per second sent to SAM from the web, as the command line (a 16-frame stride needs it)
DEMO_SAM_CHECKS_PER_DAY = 5  # tracking checks (step 1) per visitor per day
DEMO_RUNS_PER_DAY = 2  # sprite runs (steps 2-3) per visitor per day (11/1, user-approved)
# Web settings per action, from the runs the author accepted (11/1, user-approved; replaces the spec's 8 frames):
# idle 8 frames at 8 fps (knight idle); walk/run 16 at the clip's speed (line-art run 20 at 20 fps); jump 12 over
# takeoff to standing at the clip's speed (knight jump); attack 10 at 15 fps, the command-line default (15 frames
# with the feet planted passed 2 of 15 on the punch clip through the web, so the user chose this).
# span: with an end time the whole start-end part is used; without one the most active part is (mode once).
DEMO_RECIPES = {
    "idle": {"frames": 8},
    "walk": {"frames": 16, "fps": "auto"},
    "run": {"frames": 16, "fps": "auto"},
    "jump": {"frames": 12, "fps": "auto", "span": True},
    "attack": {"frames": 10, "fps": 15, "span": True},
}
DEMO_QUEUE_SIZE = 8  # visitors waiting at once; one job runs at a time

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
# Walk/run: one stride = two steps. Half way the silhouette nearly matches the start again (the
# other leg leads), so a stride needs a mid peak that climbs this share from the trough to the end match.
GAIT_MID_SHARE = 0.5
DRIFT_SMOOTH_S = 1.0  # walk/run: height smoothed this long counts as camera distance and is removed
