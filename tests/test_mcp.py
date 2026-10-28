import asyncio
import importlib.util
import sys
import unittest

from support import entry, fixture


async def initialize(session, ui=False):
    from mcp import types

    caps = (
        {
            "extensions": {
                "io.modelcontextprotocol/ui": {
                    "mimeTypes": ["text/html;profile=mcp-app"]
                }
            }
        }
        if ui
        else {}
    )
    result = await session.send_request(
        types.ClientRequest(
            types.InitializeRequest(
                params=types.InitializeRequestParams(
                    protocolVersion=types.LATEST_PROTOCOL_VERSION,
                    capabilities=types.ClientCapabilities(**caps),
                    clientInfo=types.Implementation(name="test", version="1"),
                )
            )
        ),
        types.InitializeResult,
    )
    await session.send_notification(
        types.ClientNotification(types.InitializedNotification())
    )
    return result


@unittest.skipUnless(
    importlib.util.find_spec("mcp"), "Install [mcp] for protocol tests"
)
class Protocol(unittest.TestCase):
    def test_stdio_text_and_ui(self):
        asyncio.run(self.exercise())

    async def exercise(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        tmp, root, item = fixture()
        with tmp:
            for ui in (False, True):
                params = StdioServerParameters(
                    command=sys.executable,
                    args=[
                        "-m",
                        "pocket_studio.mcp_server",
                        "--project",
                        str(root),
                        "--inline",
                    ],
                )
                async with (
                    stdio_client(params) as (reader, writer),
                    ClientSession(reader, writer) as session,
                ):
                    await initialize(session, ui)
                    tools = (await session.list_tools()).tools
                    self.assertEqual(
                        {t.name for t in tools},
                        {"project_inspect", "review_show", "feedback_submit"},
                    )
                    for tool in tools:
                        self.assertEqual(
                            bool(tool.meta), ui and tool.name == "review_show"
                        )
                    inspected = await session.call_tool("project_inspect", {})
                    self.assertEqual(
                        inspected.structuredContent["title"], "Synthetic test"
                    )
                    result = await session.call_tool(
                        "review_show", {"ids": [item["id"], "render-b"]}
                    )
                    self.assertFalse(result.isError)
                    self.assertEqual(result.structuredContent["inline_available"], ui)
                    self.assertTrue(
                        result.structuredContent["versions"][0]["file_uri"].startswith(
                            "file:"
                        )
                    )
                    if ui:
                        resource = await session.read_resource(
                            "ui://pocket-studio/review"
                        )
                        self.assertEqual(
                            resource.contents[0].mimeType, "text/html;profile=mcp-app"
                        )
                        self.assertIn("127.0.0.1", str(resource.contents[0].meta))
                    saved = await session.call_tool(
                        "feedback_submit", entry(item, str(ui))
                    )
                    self.assertFalse(saved.isError)
                    self.assertEqual(
                        saved.structuredContent["current_status"], "revision_requested"
                    )
                    bad = await session.call_tool(
                        "feedback_submit", entry(item, "bad", sha256="stale")
                    )
                    self.assertTrue(bad.isError)
