from __future__ import annotations

import subprocess
from typing import Optional


def query_gpu_memory() -> Optional[dict[str, int]]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        total, used, free = [
            int(value.strip()) for value in result.stdout.splitlines()[0].split(",")
        ]
        return {"total_mib": total, "used_mib": used, "free_mib": free}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
