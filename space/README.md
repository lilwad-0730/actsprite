---
title: ActSprite
emoji: 🌍
colorFrom: gray
colorTo: purple
sdk: gradio
sdk_version: 6.31.0
python_version: '3.12'
app_file: app.py
pinned: false
license: mit
short_description: Act out a move on your phone. Get a game-ready character.
---

# ActSprite: Act it out. Play it in.

Act out a move on your phone and get a consistent, game-ready animated character for Unity.

> **Before you generate: the default `pixel` style pixelates the final character, including your uploaded designs.**
> Fine details can be simplified or lost. The first-frame preview is shown before pixelation and can look
> sharper than the exported sprite. Read [the reasons and alternatives](#pixelation-and-artwork-fidelity).

Built for the Meta Global AI Developer Hackathon (Indie Developer track) with three Meta models:
SAM 3.1, Muse Image and Muse Spark 1.3.

Source code, tests and measured results: https://github.com/lilwad-0730/actsprite

## Pixelation and artwork fidelity

Early tests found that asking the model for pixel art could still produce high-resolution illustration.
ActSprite therefore applies pixelation in code for the `pixel` style: draw each pose, remove the background,
align the frames, reduce to a **64 × 64** grid, map colours to a shared palette of **up to 24 colours** from
the reference, then enlarge each pixel into a 2 × 2 block for **128 × 128** PNG frames.

This gives frames a consistent pixel scale, helps reduce small colour changes between frames, and provides
a predictable small-sprite appearance for games. It trades away fine lines, facial details, patterns,
textures and gradients. Enlarging the PNG does not restore the lost detail, and pixelation cannot fix bad poses.
Even a pixel-art reference is resampled onto this grid rather than preserving its original pixel arrangement.

Pixel knight and Hound use this processing. **My own design → Output style** defaults to `pixel`, so uploaded
characters do too. Choose `handdrawn`, `lineart` or `ink` **before Track** to avoid additional pixel-grid and
palette conversion; these styles export at **256 × 256**, and Line-art man uses `lineart`.
Non-pixel styles still resize and redraw the artwork: `handdrawn` requests ink outlines and flat shading,
so disabling pixelation does not guarantee preservation of the original art style or every detail.
Check the final animation and downloaded PNGs as well as the first-frame preview.

## Using the demo

Make a sprite in three checked steps: track your clip (SAM 3.1), draw the first frame, then draw every frame
and download the ZIP for the Unity importer in the repository.

Choose **Start at** and optional **End at** to use up to 5 seconds. For jump/attack, setting an end time
keeps the whole selected move; leaving it empty selects its most active part. Idle/walk/run find a cycle
inside the selected part. Walk/run need at least two full strides; cycle detection can still fail.

| Action | Frames (up to) | Playback |
| --- | --- | --- |
| idle | 8 | 8 fps |
| walk / run | 16 | Source timing |
| jump | 12 | Source timing |
| attack | 10 | 15 fps |

Tracking samples up to 30 fps. **Name** names the ZIP and its character; **Rename the ZIP (free)** changes
that name after generation without model calls. Names accept letters, digits, hyphens and underscores
(32 characters maximum).

The tracked run's output style is disclosed before drawing. Changing Output style after tracking requires
tracking again; see [pixelation and artwork fidelity](#pixelation-and-artwork-fidelity) before generating.

Limits: 5 tracking steps and 2 sprite runs per visitor per day, and $40 in the current cost log.
Counters and logs can reset when the Space restarts. This is not a persistent billing limit.
Narrow punch stances can still turn into wide lunges: a local attack check passed only 4/10 frames.
Review the preview and amber frames before using a result.

Clips and character images uploaded to this Space are sent to the Meta Model API for processing and are
deleted from the Space within an hour.
The dog walk in the showcase comes from a Pexels clip by Luis Adolfo Burgos
(https://www.pexels.com/video/close-up-shot-of-dog-walking-on-the-street-4300700/, Pexels License).
