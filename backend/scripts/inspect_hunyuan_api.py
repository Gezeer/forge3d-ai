#!/usr/bin/env python3
"""Inspect the live Gradio 5 OpenAPI used by Hunyuan Shape."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from typing import Any
from urllib.parse import urlparse

import httpx

OPENAPI_PATH = "/gradio_api/openapi.json"
TARGET_ENDPOINT = "/run/shape_generation"
SENSITIVE_KEYS = {"token", "authorization", "cookie", "path", "url"}


def redact(value: Any, key: str = "") -> Any:
    if key.lower() in SENSITIVE_KEYS and value:
        return "[redacted]"
    if isinstance(value, dict):
        return {item: redact(content, item) for item, content in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and "token=" in value.lower():
        return "[redacted]"
    return value


def check_port(url: str, timeout: float) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL Hunyuan inválida")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    with socket.create_connection((parsed.hostname, port), timeout=timeout):
        pass


def resolve_schema(schema: dict[str, Any], openapi: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        target: Any = openapi
        for part in schema["$ref"][2:].split("/"):
            target = target[part]
        schema = target
    return schema


def request_properties(openapi: dict[str, Any]) -> dict[str, Any]:
    operation = openapi["paths"][TARGET_ENDPOINT]["post"]
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    return resolve_schema(schema, openapi).get("properties", {})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    try:
        check_port(args.url, args.timeout)
        response = httpx.get(
            f"{args.url.rstrip('/')}{OPENAPI_PATH}", timeout=args.timeout
        )
        response.raise_for_status()
        openapi = response.json()
        paths = openapi.get("paths", {})
        print("Endpoints POST disponíveis:")
        for name, methods in sorted(paths.items()):
            if "post" in methods:
                print(f"- {name}")
        if TARGET_ENDPOINT not in paths or "post" not in paths[TARGET_ENDPOINT]:
            raise RuntimeError(f"Endpoint {TARGET_ENDPOINT} não encontrado")
        print(f"\nJSON publicado por {TARGET_ENDPOINT}:")
        for name, raw_schema in request_properties(openapi).items():
            schema = resolve_schema(raw_schema, openapi)
            print(
                f"- name={name} type={schema.get('type', 'object')} "
                f"default={json.dumps(redact(schema.get('default')))}"
            )
        print("\nFORGE3D_HUNYUAN_ENDPOINT=/run/shape_generation")
        return 0
    except Exception as error:
        print(f"Falha segura na inspeção: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
