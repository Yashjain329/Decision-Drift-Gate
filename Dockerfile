# Sandbox image for DDG check execution.
# Build: docker build -t ddg-sandbox:latest .
# Base pinned by digest (python:3.12-slim index, resolved 2026-10-12); refresh with
#   docker buildx imagetools inspect python:3.12-slim
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

USER 65534:65534
WORKDIR /tmp
