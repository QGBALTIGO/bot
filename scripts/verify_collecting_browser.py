"""Source compiled UI + synthetic SDK/API. Real transaction tests live in the PG suite."""

from __future__ import annotations
import argparse, json, os, re, shutil, threading
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from uuid import uuid4, UUID
import verify_native_browser as base

PREFIX = "/api/v1_7b82/collecting"
S = {
    "settings": {
        "discoverable": False,
        "share_inline": False,
        "preserve_last": True,
        "can_manage_events": True,
    },
    "wishes": {2},
    "protected": {3},
    "fragments": 15,
    "equipped": None,
    "cosmetics": [],
    "claimed": False,
    "calls": [],
    "market": [],
    "events": [],
}


def card(n):
    return {
        "id": n,
        "name": f"Personagem {n:02}",
        "anime": "Obra de teste",
        "image": f"/fixture-art/{n}.svg",
        "quantity": 3,
        "wished": n in S["wishes"],
        "protected": n in S["protected"],
        "favorite": False,
        "reserved": False,
        "available": True,
    }


def calendar():
    today = datetime.now(timezone.utc).date()
    return {
        "today": str(today),
        "streak": 7,
        "claimed_today": S["claimed"],
        "days": [
            {
                "date": str(today - timedelta(days=6 - i)),
                "claimed": i < 6 or S["claimed"],
            }
            for i in range(7)
        ],
        "reward_rules": "1 a 3 Coins ou 1 dado.",
        "milestone": {"eligible": True, "label": "Presença semanal"},
    }


def init():
    S["market"] = [
        {
            "id": str(UUID(int=111)),
            "character": card(4),
            "quantity": 1,
            "kind": "fixed",
            "price": 10,
            "bid": 0,
            "minimum_bid": 10,
            "status": "active",
            "ends_at": "2099-01-01T00:00:00Z",
            "version": 1,
            "is_owner": False,
            "is_highest_bidder": False,
            "seller_name": "Colecionador de teste",
        }
    ]
    S["events"] = [
        {
            "id": str(UUID(int=222)),
            "title": "Expedição da comunidade",
            "description": "Evento de laboratório sem alterações em contas reais.",
            "status": "active",
            "starts_at": "2020-01-01T00:00:00Z",
            "ends_at": "2099-01-01T00:00:00Z",
            "goal": 2,
            "progress": 1,
            "contribution": 0,
            "today": 0,
            "daily_limit": 2,
            "reward_label": "Expedicionário",
            "claimed": False,
            "characters": [card(1), card(2)],
        }
    ]


def response(path, query, method, body):
    S["calls"].append({"path": path, "method": method, "body": body})
    p = path.removeprefix(PREFIX)
    if p == "/settings":
        if method == "PATCH":
            S["settings"].update(body)
        return S["settings"]
    if p == "/cosmetics/profile":
        return next(
            (c for c in S["cosmetics"] if c["cosmetic_id"] == S["equipped"]), None
        )
    if p == "/characters":
        rows = [card(n) for n in range(1, 31)]
        view = query.get("view", ["owned"])[0]
        q = query.get("q", [""])[0].lower()
        offset = int(query.get("offset", [0])[0])
        if q:
            rows = [c for c in rows if q in c["name"].lower() or q == str(c["id"])]
        if view == "wishes":
            rows = [c for c in rows if c["wished"]]
        if view == "protected":
            rows = [c for c in rows if c["protected"]]
        return {
            "items": rows[offset : offset + 24],
            "has_more": len(rows) > offset + 24,
        }
    if p == "/matches":
        return {
            "opt_in_required": not S["settings"]["discoverable"],
            "items": (
                [
                    {
                        "user_id": 88,
                        "name": "Parceiro de teste",
                        "receive": [card(2)],
                        "give": [card(1)],
                    }
                ]
                if S["settings"]["discoverable"]
                else []
            ),
            "has_more": False,
        }
    if p == "/wishes":
        for cid in body["ids"]:
            S["wishes"].add(cid) if body["enabled"] else S["wishes"].discard(cid)
        return {"ok": True}
    if p.startswith("/wishes/work/"):
        S["wishes"].update([4, 5])
        return {"ok": True, "added": 2}
    if p.endswith("/protection"):
        cid = int(p.split("/")[2])
        S["protected"].add(cid) if body["enabled"] else S["protected"].discard(cid)
        return {"ok": True, "protected": body["enabled"]}
    if p == "/workshop":
        return {
            "fragments": S["fragments"],
            "cosmetics": S["cosmetics"],
            "equipped": S["equipped"],
            "recipes": [
                {
                    "id": "frame-bronze",
                    "label": "Moldura Bronze",
                    "cost": 10,
                    "kind": "frame",
                }
            ],
        }
    if p == "/workshop/preview":
        return {
            "items": [
                {**card(i["character_id"]), "consume": i["quantity"]}
                for i in body["items"]
            ],
            "fragments": sum(i["quantity"] for i in body["items"]),
        }
    if p == "/workshop/recycle":
        S["fragments"] += sum(i["quantity"] for i in body["items"])
        return {"ok": True, "fragments": S["fragments"]}
    if p == "/workshop/craft":
        S["fragments"] -= 10
        S["cosmetics"].append(
            {"cosmetic_id": "frame-bronze", "label": "Moldura Bronze", "kind": "frame"}
        )
        return {"ok": True}
    if p == "/cosmetics/equipped":
        S["equipped"] = body["cosmetic_id"]
        return {"ok": True}
    if p == "/calendar":
        return calendar()
    if p == "/daily/claim":
        S["claimed"] = True
        return {"ok": True, "calendar": calendar()}
    if p == "/daily/milestone":
        return {"ok": True}
    if p == "/now":
        return {
            "items": [
                {
                    "id": "market",
                    "title": "Mercado",
                    "description": "Confira seus anúncios",
                    "ready": True,
                    "tab": "marketplace",
                },
                {
                    "id": "eggs",
                    "title": "Incubadora",
                    "description": "Acompanhe seus ovos",
                    "ready": False,
                    "tab": "incubation",
                },
            ]
        }
    if p == "/market":
        if method == "POST":
            S["market"].append(
                {
                    **S["market"][0],
                    "status": "active",
                    "id": str(uuid4()),
                    "character": card(body["character_id"]),
                    "quantity": body["quantity"],
                    "kind": body["kind"],
                    "price": body["price"],
                    "is_owner": True,
                }
            )
            return {"ok": True}
        return {
            "items": [
                m
                for m in S["market"]
                if query.get("mine", ["false"])[0] != "true" or m["is_owner"]
            ],
            "has_more": False,
        }
    if p.startswith("/market/"):
        m = next(m for m in S["market"] if m["id"] == p.split("/")[2])
        m["status"] = "cancelled" if body.get("action") == "cancel" else "sold"
        return {"ok": True}
    if p == "/events":
        if method == "POST":
            S["events"].append(
                {**S["events"][0], **body, "id": str(uuid4()), "status": "draft"}
            )
            return {"ok": True}
        return {"items": S["events"]}
    if p.startswith("/events/"):
        e = next(e for e in S["events"] if e["id"] == p.split("/")[2])
        if p.endswith("/contribute"):
            e["progress"] += 1
            e["contribution"] += 1
            e["today"] += 1
        elif p.endswith("/claim"):
            e["claimed"] = True
        elif p.endswith("/publish"):
            e["status"] = "active"
        return {"ok": True}
    if p == "/help":
        return {
            "items": [
                {
                    "id": "collection",
                    "title": "Coleção, desejos e proteção",
                    "text": "Um personagem protegido não sai da coleção sem desbloqueio.",
                    "tab": "collecting",
                    "command": "/colecionar",
                },
                {
                    "id": "market",
                    "title": "Mercado e leilões",
                    "text": "Confira o total do lote antes de confirmar.",
                    "tab": "marketplace",
                    "command": "/mercado",
                },
            ]
        }
    if p == "/dice-info":
        return {
            "rules": ["Cada personagem elegível da obra escolhida tem a mesma chance."],
            "guarantee_note": "As probabilidades existentes não foram alteradas.",
            "eligible_characters": 0,
            "character_probability": None,
            "history": [],
        }
    if p == "/identify":
        return {
            "items": [
                {
                    "anime_id": 1,
                    "title": "Obra identificada",
                    "episode": 1,
                    "similarity": 95.1,
                    "at_seconds": 34,
                }
            ]
        }
    raise ValueError("Unknown fixture endpoint " + p)


class Handler(base.Handler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith(PREFIX):
            self.send(response(parsed.path, parse_qs(parsed.query), "GET", {}))
            return
        if parsed.path == "/api/v1_7b82/trade/offers":
            self.send([])
            return
        super().do_GET()

    def mutate(self, method):
        parsed = urlparse(self.path)
        if not parsed.path.startswith(PREFIX):
            return super().do_POST()
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = (
            {"image_bytes": len(raw), "consent": self.headers.get("X-Scene-Consent")}
            if parsed.path.endswith("/identify")
            else json.loads(raw or "{}")
        )
        self.send(response(parsed.path, parse_qs(parsed.query), method, body))

    def do_POST(self):
        self.mutate("POST")

    def do_PATCH(self):
        self.mutate("PATCH")

    def do_PUT(self):
        self.mutate("PUT")


def run(output):
    from playwright.sync_api import sync_playwright

    output.mkdir(parents=True, exist_ok=True)
    init()
    server = ThreadingHTTPServer(("127.0.0.1", base.PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {
        "scope": "Real compiled UI; synthetic API, SDK and images. PostgreSQL checked separately.",
        "routes": [],
        "flows": [],
        "page_errors": [],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.getenv("CHROMIUM_PATH") or shutil.which("chromium"),
            args=["--no-sandbox"],
        )
        page = browser.new_page(
            viewport={"width": 390, "height": 844}, reduced_motion="reduce"
        )
        page.set_default_timeout(10000)
        page.on("pageerror", lambda e: report["page_errors"].append(str(e)))

        def goto(tab):
            page.goto(f"http://127.0.0.1:{base.PORT}/menu#{tab}")
            page.wait_for_selector("main h1")
            page.wait_for_timeout(120)

        try:
            for width in [320, 390, 768, 1280]:
                page.set_viewport_size({"width": width, "height": 844})
                for tab in [
                    "collecting",
                    "workshop",
                    "marketplace",
                    "events",
                    "activity",
                    "help",
                    "identify",
                    "dice_info",
                ]:
                    goto(tab)
                    assert (
                        page.locator("[data-source-shell]").count() == 1
                        and page.locator("iframe").count() == 0
                    )
                    assert page.evaluate(
                        "document.documentElement.scrollWidth<=innerWidth+1"
                    ), (width, tab)
                    report["routes"].append({"tab": tab, "width": width})
                    if width == 390:
                        page.screenshot(path=str(output / (tab + ".png")))
            page.set_viewport_size({"width": 390, "height": 844})
            goto("collecting")
            page.get_by_role("button", name="Encontrar", exact=True).click()
            page.get_by_role("button", name="Quero este", exact=True).first.click()
            page.get_by_role("button", name="Desejos", exact=True).click()
            page.get_by_text("Personagem 01", exact=True).wait_for()
            page.get_by_role("button", name="Proteger", exact=True).first.click()
            page.get_by_role("button", name="Cofre", exact=True).click()
            page.get_by_role("button", name="Desbloquear", exact=True).first.click()
            page.get_by_role("dialog").wait_for()
            before = len([c for c in S["calls"] if c["path"].endswith("/protection")])
            page.get_by_role("button", name="Confirmar desbloqueio", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            assert (
                len([c for c in S["calls"] if c["path"].endswith("/protection")])
                == before + 1
            )
            report["flows"].append("wishlist, protection and explicit unlock")
            page.get_by_role("button", name="Preferências", exact=True).click()
            page.get_by_role("checkbox").first.check()
            page.wait_for_timeout(180)
            page.get_by_role("checkbox").nth(1).check()
            page.wait_for_timeout(180)
            page.keyboard.press("Escape")
            page.get_by_role("dialog").wait_for(state="hidden")
            page.get_by_role("button", name="Combinações", exact=True).click()
            page.get_by_text("Parceiro de teste", exact=True).wait_for()
            report["flows"].append("privacy opt-ins and reciprocal matches")
            goto("workshop")
            page.get_by_role("spinbutton").first.fill("1")
            page.get_by_role("button", name="Revisar 1 cópia(s)", exact=True).click()
            page.get_by_role("dialog").wait_for()
            page.get_by_role(
                "button", name="Confirmar e receber fragmentos", exact=True
            ).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            page.get_by_role("button", name="Criar", exact=True).first.click()
            page.get_by_role("button", name="Moldura Bronze", exact=True).click()
            report["flows"].append("workshop preview, consume, craft and equip")
            goto("marketplace")
            page.get_by_role("button", name="Revisar compra", exact=True).first.click()
            page.get_by_role("button", name="Confirmar compra", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            page.get_by_role("button", name="Criar anúncio", exact=True).click()
            page.get_by_role("dialog").get_by_role("button").filter(
                has_text="Personagem 02"
            ).first.click()
            page.get_by_role("button", name="Confirmar anúncio", exact=True).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            page.get_by_role("button", name="Meus anúncios", exact=True).click()
            page.get_by_role(
                "button", name="Cancelar anúncio", exact=True
            ).first.click()
            page.get_by_role(
                "button", name="Confirmar cancelamento", exact=True
            ).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            report["flows"].append("market buy, create and owner cancellation")
            goto("events")
            page.get_by_role("button", name="Contribuir", exact=True).first.click()
            page.get_by_role("dialog").get_by_role("button").filter(
                has_text="Personagem 01"
            ).click()
            page.get_by_role("dialog").wait_for(state="hidden")
            page.get_by_role("button", name="Resgatar emblema", exact=True).click()
            page.get_by_role("button", name="Resgatado", exact=True).wait_for()
            report["flows"].append("event contribution and cosmetic claim")
            goto("activity")
            page.get_by_role(
                "button", name="Resgatar recompensa diária", exact=True
            ).click()
            page.get_by_role("button", name="Resgatado hoje", exact=True).wait_for()
            page.get_by_role(
                "button", name="Resgatar emblema semanal", exact=True
            ).click()
            report["flows"].append("daily and weekly cosmetic")
            goto("help")
            page.get_by_role("button", name="Mercado e leilões", exact=True).click()
            assert (
                page.get_by_role(
                    "button", name="Coleção, desejos e proteção", exact=True
                ).get_attribute("aria-expanded")
                == "false"
            )
            boot = page.evaluate("__bootCount")
            page.get_by_role(
                "button", name="Abrir recurso · /mercado", exact=True
            ).click()
            page.get_by_role("heading", name="Mercado", exact=True).wait_for()
            assert page.evaluate("__bootCount") == boot
            report["flows"].append("accordion and same-document navigation")
            goto("identify")
            assert page.get_by_role(
                "button", name="Identificar cena", exact=True
            ).is_disabled()
            from PIL import Image
            import io

            image = io.BytesIO()
            Image.new("RGB", (32, 32)).save(image, format="PNG")
            page.locator("input[type=file]").set_input_files(
                {
                    "name": "scene.png",
                    "mimeType": "image/png",
                    "buffer": image.getvalue(),
                }
            )
            assert page.get_by_role(
                "button", name="Identificar cena", exact=True
            ).is_disabled()
            page.get_by_role("checkbox").check()
            page.get_by_role("button", name="Identificar cena", exact=True).click()
            page.get_by_text("Obra identificada", exact=True).wait_for()
            report["flows"].append("explicit image consent and scene result")
            writes = [c for c in S["calls"] if c["method"] != "GET"]
            assert writes
            for c in writes:
                assert "user_id" not in c["body"] and "uid" not in c["body"]
                if "request_id" in c["body"]:
                    UUID(c["body"]["request_id"])
            assert not report["page_errors"], report["page_errors"]
        except Exception as exc:
            report["failure"] = str(exc)
            try:
                page.screenshot(path=str(output / "failure.png"))
            except Exception:
                pass
            raise
        finally:
            report["requests"] = S["calls"]
            (output / "collecting-browser.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False)
            )
            browser.close()
            server.shutdown()
            server.server_close()
    print(
        json.dumps(
            {
                "routes": len(report["routes"]),
                "flows": report["flows"],
                "errors": report["page_errors"],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/source-collecting-browser")
    )
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.serve:
        init()
        ThreadingHTTPServer(("127.0.0.1", base.PORT), Handler).serve_forever()
    else:
        run(args.output)
