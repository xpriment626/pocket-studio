"""Actual Chromium media and bridge checks; NOT Claude/Codex host certification."""

import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from support import fixture

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    importlib.util.find_spec("playwright") and importlib.util.find_spec("mcp"),
    "Install [mcp,test] for browser tests",
)
class Browser(unittest.TestCase):
    def test_media_and_review_bridge(self):
        asyncio.run(asyncio.wait_for(self.exercise(), 60))

    async def exercise(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from playwright.async_api import async_playwright
        from test_mcp import initialize

        tmp, root, item = fixture()
        with tmp, tempfile.TemporaryDirectory() as build:

            class Host(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<!doctype html><title>Review harness</title>")

                def log_message(self, *args):
                    pass

            host = ThreadingHTTPServer(("127.0.0.1", 0), Host)
            host_thread = threading.Thread(target=host.serve_forever, daemon=True)
            host_thread.start()
            self.addCleanup(host.server_close)
            self.addCleanup(host.shutdown)
            harness = Path(build) / "harness.js"
            subprocess.run(
                [
                    str(ROOT / "ui/node_modules/.bin/esbuild"),
                    str(ROOT / "ui/harness.js"),
                    "--bundle",
                    "--format=iife",
                    f"--outfile={harness}",
                ],
                check=True,
                capture_output=True,
            )
            params = StdioServerParameters(
                command=os.sys.executable,
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
                await initialize(session, True)
                result = await session.call_tool(
                    "review_show", {"ids": ["render-a", "render-b"]}
                )
                resource = (
                    await session.read_resource("ui://pocket-studio/review")
                ).contents[0]
                origin = resource.meta["ui"]["csp"]["resourceDomains"][0]
                # Enforce the media source declared by resources/read, not arbitrary network.
                csp = f"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; media-src {origin}"
                html = resource.text.replace(
                    "<head>",
                    f'<head><meta http-equiv="Content-Security-Policy" content="{csp}">',
                )
                submissions = []

                async def call(params):
                    submissions.append(params["arguments"])
                    response = await session.call_tool(
                        params["name"], params["arguments"]
                    )
                    return response.model_dump(by_alias=True, exclude_none=True)

                async with async_playwright() as pw:
                    executable = os.environ.get("POCKET_CHROMIUM") or shutil.which(
                        "chromium"
                    )
                    browser = await pw.chromium.launch(
                        executable_path=executable, args=["--no-sandbox"]
                    )
                    try:
                        page = await browser.new_page()
                        page.on(
                            "console",
                            lambda msg: (
                                print("BROWSER:", msg.text)
                                if msg.type == "error"
                                else None
                            ),
                        )
                        page.on(
                            "pageerror", lambda error: print("BROWSER ERROR:", error)
                        )
                        supported = await page.evaluate(
                            "() => document.createElement('video').canPlayType('video/mp4; codecs=\"avc1.64001f, mp4a.40.2\"')"
                        )
                        self.assertTrue(supported, "Browser must support fixture H.264/AAC; set POCKET_CHROMIUM to full Chrome")
                        await page.expose_function("callTool", call)
                        await page.goto(f"http://127.0.0.1:{host.server_port}")
                        await page.add_script_tag(content=harness.read_text())
                        await page.evaluate(
                            "([html,result]) => startReview(html,result)",
                            [html, result.model_dump(by_alias=True, exclude_none=True)],
                        )
                        frame = page.frame_locator("iframe")
                        await frame.locator("#approve").wait_for(state="visible")
                        await frame.locator("#version").select_option("0")
                        await frame.locator("#player").evaluate("(v) => v.play()")
                        await frame.locator("#player").evaluate(
                            "(v) => new Promise((resolve,reject)=>{if(v.readyState>=2)return resolve();v.onloadeddata=resolve;v.onerror=()=>reject(new Error(v.error.message));})"
                        )
                        self.assertEqual(
                            await frame.locator("#player").evaluate(
                                "(v)=>v.videoWidth"
                            ),
                            320,
                        )
                        self.assertTrue(
                            await frame.locator("#player").evaluate(
                                "(v)=>!v.muted && v.volume>0"
                            )
                        )
                        await frame.locator("#player").evaluate("(v)=>v.play()")
                        await page.wait_for_timeout(350)
                        self.assertGreater(
                            await frame.locator("#player").evaluate(
                                "(v)=>v.currentTime"
                            ),
                            0.1,
                        )
                        self.assertGreater(
                            await frame.locator("#player").evaluate(
                                "(v)=>v.webkitDecodedFrameCount"
                            ),
                            0,
                        )
                        self.assertGreater(
                            await frame.locator("#player").evaluate(
                                "(v)=>v.webkitAudioDecodedByteCount"
                            ),
                            0,
                        )
                        await frame.locator("#player").evaluate(
                            "(v)=>{v.pause();v.currentTime=1.2}"
                        )
                        await page.wait_for_timeout(150)
                        await frame.locator("#note").fill("Synthetic timestamp note")
                        await frame.locator("#revise").click()
                        await (
                            frame.locator("#status")
                            .filter(has_text="Saved feedback-")
                            .wait_for()
                        )
                        self.assertAlmostEqual(submissions[-1]["time"], 1.2, places=1)
                        self.assertIn(
                            "revision_requested",
                            await frame.locator("#approval").inner_text(),
                        )
                        await frame.locator("#version").select_option("1")
                        await frame.locator("#player").evaluate("(v)=>v.play()")
                        await frame.locator("#approve").focus()
                        await frame.locator("#approve").press("Enter")
                        await (
                            frame.locator("#status")
                            .filter(has_text="Saved feedback-")
                            .wait_for()
                        )
                        self.assertEqual(submissions[-1]["id"], "render-b")
                        self.assertIn(
                            "approved", await frame.locator("#approval").inner_text()
                        )
                        (root / "video.mp4").write_bytes(b"stale")
                        await frame.locator("#revise").click()
                        await (
                            frame.locator("#status")
                            .filter(has_text="Could not confirm save")
                            .wait_for()
                        )
                        self.assertIn(
                            "approved", await frame.locator("#approval").inner_text()
                        )
                        self.assertIn(
                            "approved",
                            json.loads((root / "motion.json").read_text())["renders"][
                                1
                            ]["creative_status"],
                        )
                    finally:
                        await browser.close()
