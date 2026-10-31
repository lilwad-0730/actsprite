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
Built for the Meta Global AI Developer Hackathon (Indie Developer track) with three Meta models:
SAM 3.1, Muse Image and Muse Spark 1.3.

Source code, tests and measured results: https://github.com/lilwad-0730/actsprite

Make a sprite in three checked steps: track your clip (SAM 3.1), draw the first frame, then draw every frame
and download the ZIP for the Unity importer in the repository.

Clips and character images uploaded to this Space are sent to the Meta Model API for processing and are
deleted from the Space within an hour.
The dog walk in the showcase comes from a Pexels clip by Luis Adolfo Burgos
(https://www.pexels.com/video/close-up-shot-of-dog-walking-on-the-street-4300700/, Pexels License).
