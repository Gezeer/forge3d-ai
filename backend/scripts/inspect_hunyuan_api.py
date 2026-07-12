#!/usr/bin/env python3
"""Inspect the live Hunyuan Gradio API without exposing sensitive values."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from typing import Any, Optional
from urllib.parse import urlparse

TARGET_ENDPOINT = "/shape_generation"
SENSITIVE_KEYS = {"token", "authorization", "cookie", "path", "url"}


def redact(value: Any, key: str = "") -> Any:
    if key.lower() in SENSITIVE_KEYS and value:
        return "[redacted]"
    if isinstance(value, dict):
        return {item: redact(content, item) for item, content in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and ("token=" in value.lower() or value.startswith("/")):
        return "[redacted]"
    return value


def check_port(url: str, timeout: float) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL Hunyuan inválida")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    with socket.create_connection((parsed.hostname, port), timeout=timeout):
        pass


def endpoint_map(api_info: Any) -> dict[str, Any]:
    if not isinstance(api_info, dict):
        return {}
    for key in ("named_endpoints", "endpoints"):
        endpoints = api_info.get(key)
        if isinstance(endpoints, dict):
            return endpoints
    return {key: value for key, value in api_info.items() if str(key).startswith("/")}


def image_marker(parameter: dict[str, Any]) -> Optional[dict[str, str]]:
    component = str(
        parameter.get("component")
        or parameter.get("component_type")
        or parameter.get("type", "")
    ).lower()
    if "imageeditor" in component or "image_editor" in component:
        return {"$image": "imageeditor"}
    if "imagedata" in component:
        return {"$image": "imagedata"}
    if "image" in component:
        return {"$image": "simple"}
    return None


def build_signature(endpoint: dict[str, Any]) -> dict[str, Any]:
    parameters = endpoint.get("parameters", [])
    if not isinstance(parameters, list):
        raise ValueError("Endpoint sem lista de parâmetros")
    args = []
    for parameter in parameters:
        marker = image_marker(parameter)
        if marker:
            args.append(marker)
        elif parameter.get("parameter_has_default") or "default" in parameter:
            args.append(parameter.get("parameter_default", parameter.get("default")))
        else:
            args.append(None)
    return {"args": args, "kwargs": {}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    try:
        check_port(args.url, args.timeout)
        from gradio_client import Client

        client = Client(args.url)
        api_info = client.view_api(
            all_endpoints=True, print_info=False, return_format="dict"
        )
        endpoints = endpoint_map(api_info)
        print("Endpoints disponíveis:")
        for name in sorted(endpoints):
            print(f"- {name}")
        endpoint = endpoints.get(TARGET_ENDPOINT)
        if endpoint is None:
            raise RuntimeError(f"Endpoint {TARGET_ENDPOINT} não encontrado")
        print(f"\nParâmetros de {TARGET_ENDPOINT}:")
        for index, parameter in enumerate(endpoint.get("parameters", [])):
            safe = redact(parameter)
            print(
                f"{index}: name={safe.get('parameter_name', safe.get('label', '?'))} "
                f"type={safe.get('component', safe.get('type', '?'))} "
                f"default={safe.get('parameter_default', safe.get('default', None))}"
            )
        signature = build_signature(endpoint)
        print("\nFORGE3D_HUNYUAN_SIGNATURE_JSON=")
        print(json.dumps(signature, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        print(f"Falha segura na inspeção: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
