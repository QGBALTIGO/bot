"""Additional compiled-UI flows. All accounts, APIs and Telegram calls are synthetic."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import verify_collecting_browser as fixture
from playwright.sync_api import sync_playwright, expect

TRADES = []
CALLS = []


def trade():
    def character(i):
        return {"id": str(i), "name": f"Personagem {i:02}", "anime": "Obra de teste",
                "img_url": f"/fixture-art/{i}.svg", "count": 3}
    return {"id": "901", "sender_id": 88, "receiver_id": 77,
            "sender_name": "Parceiro de teste", "receiver_name": "Tester",
            "sender_char": character(1), "receiver_char": character(2),
            "status": "pending", "revision": 1,
            "sender_confirmed": True, "receiver_confirmed": False}


class Handler(fixture.Handler):
    def do_GET(self):
        if urlparse(self.path).path == "/api/v1_7b82/trade/offers":
            self.send(TRADES)
        else:
            super().do_GET()

    def mutate(self, method):
        path = urlparse(self.path).path
        if path.startswith("/api/v1_7b82/trade/"):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or "{}")
            CALLS.append({"path": path, "method": method, "body": body})
            row = TRADES[0]
            if method == "PATCH":
                assert body["expected_revision"] == row["revision"]
                row["revision"] += 1
                row["sender_confirmed"] = row["receiver_confirmed"] = False
                row["receiver_char"] = {**row["receiver_char"], "id": str(body["character_id"]),
                                        "name": f"Personagem {body['character_id']:02}"}
                self.send({"ok": True, "revision": row["revision"], "confirmations_cleared": True})
            else:
                assert body["expected_revision"] == row["revision"]
                row["receiver_confirmed"] = True
                row["status"] = "completed" if row["sender_confirmed"] else "pending"
                self.send({"ok": True, "status": row["status"], "revision": row["revision"]})
            return
        if "/collecting/market/" in path and method == "POST":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or "{}")
            CALLS.append({"path": path, "method": method, "body": body})
            row = fixture.S["market"][0]
            if body.get("action") == "bid":
                row.update(bid=body["amount"], minimum_bid=body["amount"] + 1,
                           is_highest_bidder=True, version=row["version"] + 1)
            self.send({"ok": True, "status": row["status"]})
            return
        super().mutate(method)


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    fixture.init()
    TRADES[:] = [trade()]
    server = ThreadingHTTPServer(("127.0.0.1", fixture.base.PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {"scope": "Compiled application; synthetic accounts, HTTP APIs and SDK. No production operations.",
              "flows": [], "page_errors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH") or shutil.which("chromium"),
                                    args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
        page.set_default_timeout(12000)
        page.on("pageerror", lambda e: report["page_errors"].append(str(e)))

        def goto(tab):
            page.goto(f"http://127.0.0.1:{fixture.base.PORT}/menu#{tab}")
            page.wait_for_selector("main h1")

        try:
            fixture.S["market"][0].update(kind="auction", bid=0, minimum_bid=10)
            goto("marketplace")
            page.get_by_role("button", name="Dar lance", exact=True).click()
            expect(page.get_by_role("dialog")).to_be_visible()
            page.get_by_role("spinbutton").fill("9")
            expect(page.get_by_role("button", name="Confirmar lance", exact=True)).to_be_disabled()
            page.get_by_role("spinbutton").fill("12")
            page.get_by_role("button", name="Confirmar lance", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            expect(page.get_by_role("button", name="Dar outro lance", exact=True)).to_be_visible()
            assert CALLS[-1]["body"]["amount"] == 12 and CALLS[-1]["body"]["version"] == 1
            UUID(CALLS[-1]["body"]["request_id"])
            page.screenshot(path=str(output / "auction-confirmed.png"))
            report["flows"].append("auction minimum, explicit bid confirmation, version and updated high-bid state")

            fixture.S["market"][0]["is_owner"] = True
            goto("marketplace")
            expect(page.get_by_role("button", name="Cancelar anúncio", exact=True)).to_be_disabled()
            report["flows"].append("auction with bids cannot be cancelled in the owner interface")

            goto("events")
            page.get_by_role("button", name="Preparar evento", exact=True).click()
            page.get_by_label("Nome", exact=True).fill("Expedição revisada")
            page.get_by_label("Descrição", exact=True).fill("Evento preparado e revisado na interface de administração.")
            page.get_by_label("IDs de personagens do catálogo, separados por vírgula", exact=True).fill("1, 2")
            now = datetime.now(timezone.utc)
            page.get_by_label("Início (horário do seu aparelho)", exact=True).fill((now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M"))
            page.get_by_label("Fim (até 30 dias depois)", exact=True).fill((now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"))
            page.get_by_role("button", name="Salvar rascunho", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            page.get_by_role("button", name="Revisar publicação", exact=True).click()
            expect(page.get_by_role("dialog")).to_contain_text("Expedição revisada")
            page.get_by_role("button", name="Confirmar publicação", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            assert fixture.S["events"][-1]["status"] == "active"
            report["flows"].append("admin data-only event draft and separate publication confirmation")

            fixture.S["settings"]["can_manage_events"] = False
            goto("events")
            expect(page.get_by_role("button", name="Preparar evento", exact=True)).to_have_count(0)
            report["flows"].append("event authoring controls are hidden without admin capability")

            goto("trading")
            page.get_by_role("button", name="Confirmar", exact=True).click()
            expect(page.get_by_role("dialog")).to_contain_text("Você entrega")
            assert not CALLS[-1]["path"].startswith("/api/v1_7b82/trade/")
            page.get_by_role("button", name="Confirmar esta versão", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            assert TRADES[0]["status"] == "completed" and CALLS[-1]["body"]["expected_revision"] == 1
            report["flows"].append("trade confirmation sends the exact reviewed version, only after explicit confirmation")

            TRADES[:] = [trade()]
            goto("trading")
            page.get_by_role("button", name="Alterar minha oferta", exact=True).click()
            page.get_by_role("dialog").get_by_role("button").filter(has_text="Personagem 04").click()
            page.get_by_role("button", name="Salvar nova proposta", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            assert TRADES[0]["revision"] == 2 and not TRADES[0]["sender_confirmed"] and not TRADES[0]["receiver_confirmed"]
            page.get_by_role("button", name="Confirmar", exact=True).click()
            expect(page.get_by_role("dialog")).to_contain_text("Personagem 04")
            page.get_by_role("button", name="Confirmar esta versão", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            expect(page.get_by_role("button", name="Confirmado", exact=True)).to_be_disabled()
            assert TRADES[0]["status"] == "pending" and CALLS[-1]["body"]["expected_revision"] == 2
            page.screenshot(path=str(output / "trade-reconfirmation.png"))
            report["flows"].append("amend own side, clear both confirmations, display new character and await second participant")

            async_error = "Teste: serviço temporariamente indisponível."
            page.route("**/collecting/market?*", lambda route: route.fulfill(status=503, json={"detail": async_error}))
            goto("marketplace")
            expect(page.get_by_text(async_error, exact=True)).to_be_visible()
            assert page.locator("[data-source-shell]").count() == 1
            page.unroute("**/collecting/market?*")
            report["flows"].append("server failure is visible inside the existing shell, not a blank screen")

            fixture.S["settings"]["discoverable"] = False
            page.route("**/collecting/settings", lambda route: (
                route.fulfill(status=409, json={"detail": "Teste: preferência não foi salva."})
                if route.request.method == "PATCH" else route.continue_()))
            goto("collecting")
            page.get_by_role("button", name="Preferências", exact=True).click()
            page.get_by_role("checkbox").first.click()
            expect(page.get_by_text("Teste: preferência não foi salva.", exact=True)).to_be_visible()
            expect(page.get_by_role("checkbox").first).not_to_be_checked()
            page.unroute("**/collecting/settings")
            report["flows"].append("optimistic preference feedback rolls back when the server rejects the change")
            assert not report["page_errors"], report["page_errors"]
        except Exception as exc:
            report["failure"] = str(exc)
            try:
                page.screenshot(path=str(output / "failure.png"))
            except Exception:
                pass
            raise
        finally:
            report["calls"] = CALLS
            (output / "extended-browser.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            browser.close()
            server.shutdown()
            server.server_close()
    print(json.dumps({"passed": True, "flows": len(report["flows"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/source-collecting-extended"))
    run(parser.parse_args().output)
