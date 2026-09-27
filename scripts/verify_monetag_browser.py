"""Compiled Source MiniApp + synthetic Monetag SDK/API browser regression.

No external ad is loaded. PostgreSQL/postback economics are verified separately
by verify_monetag_rewards.py.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import verify_collecting_browser as fixture
from playwright.sync_api import expect, sync_playwright

PREFIX = "/api/v1_7b82/monetization/rewarded"
SESSION_ID = "11111111-1111-4111-8111-111111111111"
STATE = {
    "rewarded_today": 0,
    "dado_balance": 4,
    "start_calls": [],
    "result_calls": 0,
    "selected": "coins",
}


def status():
    return {
        "enabled": True,
        "provider": "monetag",
        "sdkUrl": f"http://127.0.0.1:{fixture.base.PORT}/fixture-monetag-sdk.js",
        "zoneId": "123456",
        "sdkFunction": "show_123456",
        "requestVar": "source_rewarded_bonus",
        "rewards": {"coins": 15, "dado": 1},
        "dailyLimit": 3,
        "rewardedToday": STATE["rewarded_today"],
        "remainingToday": max(0, 3 - STATE["rewarded_today"]),
        "cooldownMinutes": 0,
        "cooldownUntil": None,
        "dadoBalance": STATE["dado_balance"],
        "dadoMax": 24,
        "canStart": STATE["rewarded_today"] < 3,
        "canStartCoins": STATE["rewarded_today"] < 3,
        "canStartDado": STATE["rewarded_today"] < 3 and STATE["dado_balance"] < 24,
        "pending": None,
    }


class Handler(fixture.Handler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/fixture-monetag-sdk.js":
            body = (
                "window.__monetagCalls=window.__monetagCalls||[];"
                "window.show_123456=async function(options){"
                "window.__monetagCalls.push(options);return undefined;};"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == PREFIX + "/status":
            self.send(status())
            return
        if parsed.path == PREFIX + "/" + SESSION_ID:
            STATE["result_calls"] += 1
            selected = STATE["selected"]
            rewarded_coins = 15 if selected == "coins" else 0
            rewarded_dados = 1 if selected == "dado" else 0
            if STATE["result_calls"] >= 1:
                STATE["rewarded_today"] += 1
                if selected == "dado":
                    STATE["dado_balance"] += 1
                self.send(
                    {
                        "id": SESSION_ID,
                        "status": "rewarded",
                        "rewardType": selected,
                        "rewardAmount": 15 if selected == "coins" else 1,
                        "rewardedDados": rewarded_dados,
                        "rewardedCoins": rewarded_coins,
                    }
                )
            else:
                self.send(
                    {
                        "id": SESSION_ID,
                        "status": "pending",
                        "rewardType": selected,
                        "rewardAmount": 15 if selected == "coins" else 1,
                        "rewardedDados": 0,
                        "rewardedCoins": 0,
                    }
                )
            return
        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == PREFIX + "/start":
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw or "{}")
            reward_type = body.get("rewardType")
            assert reward_type in {"coins", "dado"}, body
            STATE["selected"] = reward_type
            STATE["result_calls"] = 0
            STATE["start_calls"].append(body)
            self.send(
                {
                    "id": SESSION_ID,
                    "ymid": SESSION_ID,
                    "expiresAt": "2099-01-01T00:00:00Z",
                    "sdkUrl": f"http://127.0.0.1:{fixture.base.PORT}/fixture-monetag-sdk.js",
                    "zoneId": "123456",
                    "sdkFunction": "show_123456",
                    "requestVar": "source_rewarded_bonus",
                    "rewardType": reward_type,
                    "rewardAmount": 15 if reward_type == "coins" else 1,
                    "reused": False,
                }
            )
            return
        super().do_POST()


def run(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    fixture.init()
    STATE.update(rewarded_today=0, dado_balance=4, start_calls=[], result_calls=0, selected="coins")
    server = ThreadingHTTPServer(("127.0.0.1", fixture.base.PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {
        "scope": "Compiled Source UI; synthetic Monetag SDK and HTTP API; no external ads or real accounts.",
        "viewports": [],
        "flows": [],
        "page_errors": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.getenv("CHROMIUM_PATH") or shutil.which("chromium"),
            args=["--no-sandbox"],
        )
        page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
        page.set_default_timeout(12000)
        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))

        def goto_activity(case: int):
            page.goto(
                f"http://127.0.0.1:{fixture.base.PORT}/menu?monetag_case={case}#activity"
            )
            page.get_by_role("heading", name="Disponível agora", exact=True).wait_for()
            page.get_by_text("Recompensa por anúncio", exact=True).wait_for()

        try:
            for width in [320, 390, 768]:
                page.set_viewport_size({"width": width, "height": 844})
                goto_activity(width)
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1"), width
                expect(page.get_by_text("0/3", exact=True)).to_be_visible()
                report["viewports"].append(width)
                if width == 390:
                    page.screenshot(path=str(output / "rewarded-card-mobile.png"))

            page.set_viewport_size({"width": 390, "height": 844})
            goto_activity(1001)
            page.get_by_role("radio", name="+15 Coins Sempre disponível").click()
            page.get_by_role("button", name="Assistir e ganhar +15 Coins", exact=True).click()
            expect(page.get_by_text("1/3", exact=True)).to_be_visible(timeout=10000)
            calls = page.evaluate("window.__monetagCalls")
            assert len(calls) == 1
            assert calls[0]["ymid"] == SESSION_ID
            assert calls[0]["requestVar"] == "source_rewarded_bonus"
            assert STATE["start_calls"][-1] == {"rewardType": "coins"}
            report["flows"].append("coin choice -> SDK -> server-confirmed reward")

            goto_activity(1002)
            page.get_by_role("radio", name="+1 Dado").click()
            page.get_by_role("button", name="Assistir e ganhar +1 Dado", exact=True).click()
            expect(page.get_by_text("2/3", exact=True)).to_be_visible(timeout=10000)
            assert STATE["start_calls"][-1] == {"rewardType": "dado"}
            assert STATE["dado_balance"] == 5
            report["flows"].append("dado choice -> SDK -> server-confirmed reward")

            STATE["rewarded_today"] = 3
            goto_activity(1003)
            expect(page.get_by_role("button", name="Limite diário atingido", exact=True)).to_be_disabled()
            report["flows"].append("three-per-day cap disables further ad starts")

            STATE["rewarded_today"] = 0
            STATE["dado_balance"] = 24
            goto_activity(1004)
            dado = page.get_by_role("radio", name="+1 Dado Saldo já está cheio")
            expect(dado).to_be_disabled()
            page.get_by_role("radio", name="+15 Coins Sempre disponível").click()
            expect(page.get_by_role("button", name="Assistir e ganhar +15 Coins", exact=True)).to_be_enabled()
            report["flows"].append("full Dado balance keeps Coins choice available")

            assert not report["page_errors"], report["page_errors"]
        except Exception as exc:
            report["failure"] = str(exc)
            try:
                page.screenshot(path=str(output / "failure.png"))
            except Exception:
                pass
            raise
        finally:
            (output / "monetag-browser.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2)
            )
            browser.close()
            server.shutdown()
            server.server_close()

    print(json.dumps({"passed": True, **report}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/source-monetag-browser"))
    run(parser.parse_args().output)
