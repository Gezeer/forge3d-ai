#!/usr/bin/env python3
"""Validate Shape pause, Paint, Shape restart and both GLB downloads on RunPod."""

from __future__ import annotations

import argparse
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import httpx


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def validate_glb(path: Path) -> None:
    if not path.is_file() or path.stat().st_size <= 20:
        raise RuntimeError(f"GLB ausente ou vazio: {path.name}")
    magic, version = struct.unpack("<4sI", path.read_bytes()[:8])
    if magic != b"glTF" or version != 2:
        raise RuntimeError(f"GLB 2.0 inválido: {path.name}")
    subprocess.run(["file", str(path)], check=True)


def wait_shape_ready(client: httpx.Client, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_health = None
    last_error = None
    while time.monotonic() < deadline:
        try:
            response = client.get("/health")
            response.raise_for_status()
            health = response.json()
            last_health = health
            if health["engines"]["hunyuan"]["status"] == "healthy":
                return
        except Exception as error:
            last_error = error
        time.sleep(2)
    details = f"last_health={last_health!r} last_error={last_error!r}"
    timeout_error = TimeoutError(
        f"Hunyuan Shape não voltou ao estado healthy; {details}"
    )
    if last_error is not None:
        raise timeout_error from last_error
    raise timeout_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--image",
        type=Path,
        default=Path("/workspace/forge3d-ai/examples/robot.png"),
    )
    parser.add_argument("--shape-port", type=int, default=8080)
    parser.add_argument("--timeout", type=float, default=2700)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("/tmp/forge3d-full-e2e")
    )
    args = parser.parse_args()
    image = args.image.expanduser().resolve()
    if not image.is_file():
        print(f"robot.png não encontrado: {image}", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    shape_completed_at = None
    texture_started_at = None
    port_was_stopped = False
    try:
        with httpx.Client(base_url=args.api_url.rstrip("/"), timeout=120) as client:
            wait_shape_ready(client, 60)
            with image.open("rb") as source:
                response = client.post(
                    "/jobs/generate",
                    data={"engine": "hunyuan"},
                    files={"file": ("robot.png", source, "image/png")},
                )
            response.raise_for_status()
            job_id = response.json()["job_id"]
            deadline = time.monotonic() + args.timeout
            job = None
            while time.monotonic() < deadline:
                response = client.get(f"/jobs/{job_id}")
                response.raise_for_status()
                job = response.json()
                if job["status"] == "failed":
                    raise RuntimeError(f"Shape falhou: {job.get('error')}")
                if job["status"] == "completed" and shape_completed_at is None:
                    shape_completed_at = time.monotonic()
                if job.get("texture_status") == "texturing":
                    texture_started_at = texture_started_at or time.monotonic()
                    port_was_stopped = port_was_stopped or not port_open(
                        args.shape_port
                    )
                if job.get("texture_status") == "failed":
                    raise RuntimeError(f"Textura falhou: {job.get('texture_error')}")
                if job.get("texture_status") == "completed":
                    break
                time.sleep(2)
            else:
                raise TimeoutError("Pipeline completo excedeu o timeout")
            if shape_completed_at is None or texture_started_at is None:
                raise RuntimeError(
                    "Transições completed/texturing não foram observadas"
                )
            if not port_was_stopped:
                raise RuntimeError(
                    "A porta 8080 não foi observada parada durante o Paint"
                )
            wait_shape_ready(client, 300)
            if not port_open(args.shape_port):
                raise RuntimeError("A porta do Shape não voltou após o Paint")
            white = args.output_dir / f"{job_id}-white.glb"
            textured = args.output_dir / f"{job_id}-textured.glb"
            white.write_bytes(
                client.get(f"/download/{job_id}").raise_for_status().content
            )
            textured.write_bytes(
                client.get(f"/download/{job_id}/textured").raise_for_status().content
            )
            validate_glb(white)
            validate_glb(textured)
            finished = time.monotonic()
            print(
                f"job_id={job_id} shape_seconds={shape_completed_at - started:.1f} "
                f"texture_seconds={finished - texture_started_at:.1f} "
                f"total_seconds={finished - started:.1f} "
                f"white_bytes={white.stat().st_size} "
                f"textured_bytes={textured.stat().st_size} port_restarted=yes"
            )
        return 0
    except Exception as error:
        print(f"E2E falhou: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
