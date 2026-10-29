"""Optional stdio adapter. Install pocket-studio[mcp] to use it."""

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path

from .core import inspect_project, review_versions, root_at, submit_feedback
from .media import MediaServer

URI = "ui://pocket-studio/review"
MIME = "text/html;profile=mcp-app"


def create_server(root, media=None):
    from mcp import types
    from mcp.server.lowlevel import Server
    from mcp.server.lowlevel.helper_types import ReadResourceContents

    server = Server("pocket-studio")

    def ui_supported():
        caps = server.request_context.session.client_params.capabilities.model_dump()
        extension = (caps.get("extensions") or {}).get("io.modelcontextprotocol/ui", {})
        return media is not None and MIME in extension.get("mimeTypes", [])

    def schema(properties, required=()):
        return dict(
            type="object",
            properties=properties,
            required=list(required),
            additionalProperties=False,
        )

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name="project_inspect",
                description="Inspect this configured project and validate registered artifact bytes.",
                inputSchema=schema({}),
            ),
            types.Tool(
                name="review_show",
                description="Review one or two exact versions. Open file_uri in a local player if inline media is unavailable.",
                inputSchema=schema(
                    {
                        "ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": 2,
                        }
                    },
                    ["ids"],
                ),
                **({"_meta": {"ui": {"resourceUri": URI}}} if ui_supported() else {}),
            ),
            types.Tool(
                name="feedback_submit",
                description="Record actual human feedback, never agent critique. Human is caller attribution, not authenticated identity. Retry with the same request_id and identical arguments.",
                inputSchema=schema(
                    {
                        "id": {"type": "string"},
                        "sha256": {"type": "string"},
                        "decision": {"type": "string", "enum": ["approve", "revise"]},
                        "time": {"type": "number"},
                        "note": {"type": "string", "maxLength": 100000},
                        "author": {"const": "human", "type": "string"},
                        "request_id": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 200,
                        },
                    },
                    [
                        "id",
                        "sha256",
                        "decision",
                        "time",
                        "note",
                        "author",
                        "request_id",
                    ],
                ),
            ),
        ]

    @server.list_resources()
    async def list_resources():
        return (
            [types.Resource(uri=URI, name="Version review", mimeType=MIME)]
            if ui_supported()
            else []
        )

    @server.read_resource()
    async def read_resource(uri):
        if str(uri) != URI or not ui_supported():
            raise ValueError(
                "Inline review unavailable; use review_show file_uri and feedback_submit"
            )
        return [
            ReadResourceContents(
                content=(Path(__file__).parent / "ui/review.html").read_text(),
                mime_type=MIME,
                meta={
                    "ui": {
                        "csp": {"resourceDomains": [media.origin]},
                        "prefersBorder": True,
                    }
                },
            )
        ]

    @server.call_tool()
    async def call_tool(name, arguments):
        try:
            if name == "project_inspect":
                result = await asyncio.to_thread(inspect_project, root)
            elif name == "review_show":
                versions = await asyncio.to_thread(
                    review_versions, root, arguments["ids"]
                )
                if ui_supported():
                    for item in versions:
                        item["media_url"] = media.register(item)
                result = {
                    "versions": versions,
                    "inline_available": ui_supported(),
                    "fallback": "Open file_uri in a local player, then call feedback_submit with the displayed id and sha256. Render and assemble remain CLI commands.",
                }
            elif name == "feedback_submit":
                result = await asyncio.to_thread(submit_feedback, root, arguments)
            else:
                raise ValueError("Unknown tool")
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(result))],
                structuredContent=result,
            )
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return types.CallToolResult(
                isError=True, content=[types.TextContent(type="text", text=str(exc))]
            )

    return server


async def serve(root, inline):
    from mcp.server.stdio import stdio_server

    media = MediaServer(root) if inline else None
    try:
        server = create_server(root, media)
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())
    finally:
        if media:
            media.close()


def stop_server(*_):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(
        description="Local project-scoped MCP over stdio (macOS/Linux)."
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--inline",
        action="store_true",
        help="Enable optional MCP Apps resource and session loopback media server",
    )
    args = parser.parse_args()
    try:
        import mcp  # noqa: F401

        root = root_at(args.project)
        signal.signal(signal.SIGTERM, stop_server)
        asyncio.run(serve(root, args.inline))
    except ImportError:
        print(
            'Install optional adapter: pip install "pocket-studio[mcp]"',
            file=sys.stderr,
        )
        sys.exit(1)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
