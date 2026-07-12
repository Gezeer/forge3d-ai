#!/usr/bin/env python3
"""Inspect the live Gradio API on RunPod without downloading any model."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()

    try:
        from gradio_client import Client
    except ImportError as exc:
        raise SystemExit("Instale o extra 'hunyuan' para usar este script") from exc

    client = Client(args.url)
    client.view_api(all_endpoints=True, print_info=True)


if __name__ == "__main__":
    main()
