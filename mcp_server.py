"""MCP server exposing Keyframe Transcription as a tool.

Usage with Claude Desktop — add to ~/Library/Application Support/Claude/claude_desktop_config.json:
{
  "mcpServers": {
    "keyframe-transcribe": {
      "command": "python",
      "args": ["/path/to/keyframe/mcp_server.py"],
      "env": {
        "KEYFRAME_API_KEY": "kf_live_...",
        "KEYFRAME_API_BASE": "https://keyframe-transcribe.up.railway.app"
      }
    }
  }
}

Or, to run against the local server:
  KEYFRAME_API_KEY=kf_live_... KEYFRAME_API_BASE=http://localhost:8000 python mcp_server.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

API_BASE = os.getenv("KEYFRAME_API_BASE", "https://keyframe-transcribe.up.railway.app")
API_KEY = os.getenv("KEYFRAME_API_KEY", "")

server = Server("keyframe-transcription")


def _headers() -> dict:
    if not API_KEY:
        raise RuntimeError("KEYFRAME_API_KEY environment variable is not set.")
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="transcribe_video",
            description=(
                "Transcribe a video or audio file from a public URL. "
                "Returns a structured transcript with speaker labels (creator, ai, narrator, person1..N), "
                "per-segment language detection, English translation, and audio mode classification. "
                "Processing takes 10–60 seconds. This tool handles polling automatically."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Public URL of the video or audio file to transcribe. Max 100MB.",
                    },
                    "model": {
                        "type": "string",
                        "description": "Optional: force a specific Gemini model (e.g. 'gemini-2.5-pro').",
                    },
                },
                "required": ["url"],
            },
        ),
        Tool(
            name="check_quota",
            description="Check remaining transcription quota (audio-minutes) for your API key.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "transcribe_video":
        return await _transcribe_video(arguments)
    if name == "check_quota":
        return await _check_quota()
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _transcribe_video(arguments: dict) -> list[TextContent]:
    url = arguments.get("url")
    model = arguments.get("model")

    payload: dict = {"url": url}
    if model:
        payload["model"] = model

    async with httpx.AsyncClient(timeout=30) as client:
        # Submit job
        resp = await client.post(f"{API_BASE}/jobs", json=payload, headers=_headers())
        if resp.status_code not in (200, 202):
            err = resp.json()
            return [TextContent(type="text", text=f"Error submitting job: {json.dumps(err, indent=2)}")]

        job = resp.json()
        job_id = job["job_id"]

        # Poll for completion
        max_wait = 180  # seconds
        elapsed = 0
        poll_interval = 5

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            status_resp = await client.get(f"{API_BASE}/jobs/{job_id}", headers=_headers())
            status_data = status_resp.json()
            current_status = status_data.get("status")

            if current_status == "completed":
                result_resp = await client.get(f"{API_BASE}/jobs/{job_id}/result", headers=_headers())
                result = result_resp.json()
                return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

            if current_status == "failed":
                error = status_data.get("error", {})
                return [TextContent(type="text", text=f"Transcription failed: {json.dumps(error, indent=2)}")]

    return [TextContent(type="text", text=f"Timed out after {max_wait}s waiting for job {job_id}.")]


async def _check_quota() -> list[TextContent]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{API_BASE}/keys/me/usage", headers=_headers())
        if resp.status_code != 200:
            return [TextContent(type="text", text=f"Error: {resp.text}")]
        return [TextContent(type="text", text=json.dumps(resp.json(), indent=2))]


async def main():
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
