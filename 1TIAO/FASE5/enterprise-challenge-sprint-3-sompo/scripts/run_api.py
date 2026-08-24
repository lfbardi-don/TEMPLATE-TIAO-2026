"""Run the supported local-only preventive-inspection API server."""

from __future__ import annotations

import uvicorn

from tractor_usage.api.app import create_app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
