---
title: Manim Agent Worker (TTS)
sdk: docker
app_port: 7860
---

Source monorepo: https://github.com/__GITHUB_REPOSITORY__

This Space mirrors the **TTS worker** slice and builds with **`docker/tts-worker/Dockerfile`** as `Dockerfile` (includes Piper + `docker/tts-worker/piper.docker.yaml` path). Health + Celery: `worker/worker_health.py`.
