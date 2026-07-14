#!/usr/bin/env python3
"""Validate automatic Hunyuan shape and texture through the public API."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import httpx


def wait_for_job(
    client: httpx.Client, job_id: str, timeout: float
) -> tuple[dict, bool]:
    deadline = time.monotonic() + timeout
    shape_seen = False
    while time.monotonic() < deadline:
        response = client.get(f"/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        shape_seen = shape_seen or job.get("status") == "completed"
        if job.get("status") == "failed":
            raise RuntimeError(f"shape failed: {job.get('error') or 'unknown error'}")
        if job.get("texture_status") == "failed":
            raise RuntimeError(
                f"texture failed: {job.get('texture_error') or 'unknown error'}"
            )
        if job.get("texture_status") == "completed":
            return job, shape_seen
        time.sleep(3)
    raise TimeoutError("automatic texture pipeline timed out")


def download(client: httpx.Client, url: str, destination: Path) -> None:
    response = client.get(url)
    response.raise_for_status()
    destination.write_bytes(response.content)
    if destination.stat().st_size <= 0:
        raise RuntimeError(f"empty artifact: {destination.name}")
    if destination.read_bytes()[:4] != b"glTF":
        raise RuntimeError(f"invalid GLB header: {destination.name}")
    subprocess.run(["file", str(destination)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=Path("/workspace/forge3d-ai/examples/robot.png"),
    )
    parser.add_argument("--timeout", type=float, default=2400)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/forge3d-e2e"))
    args = parser.parse_args()
    image = args.image.expanduser().resolve()
    if not image.is_file():
        print(f"robot.png not found: {image}", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with httpx.Client(base_url=args.api_url.rstrip("/"), timeout=120) as client:
            with image.open("rb") as source:
                response = client.post(
                    "/jobs/generate",
                    data={"engine": "hunyuan"},
                    files={"file": ("robot.png", source, "image/png")},
                )
            response.raise_for_status()
            job_id = response.json()["job_id"]
            job, shape_seen = wait_for_job(client, job_id, args.timeout)
            if not shape_seen:
                raise RuntimeError("shape completion was not observed")
            white = args.output_dir / f"{job_id}-white.glb"
            textured = args.output_dir / f"{job_id}-textured.glb"
            download(client, f"/download/{job_id}", white)
            download(client, f"/download/{job_id}/textured", textured)
            print(
                f"job_id={job_id} white_bytes={white.stat().st_size} "
                f"textured_bytes={textured.stat().st_size} "
                f"texture_status={job['texture_status']}"
            )
        return 0
    except Exception as error:
        print(f"E2E failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
