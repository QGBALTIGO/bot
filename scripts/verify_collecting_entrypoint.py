"""Regression for real production router composition, not an isolated feature router.

Only the explicit disposable source_audit database is accepted. Requests use
locally signed synthetic sessions; external network transports are denied.
"""
from __future__ import annotations

import ast
import io
import itertools
import json
import os
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
url = os.environ.get("SOURCE_AUDIT_DATABASE_URL", "")
parsed = urlparse(url)
if parsed.hostname not in {"localhost", "127.0.0.1", "postgres"} or parsed.path != "/source_audit":
    raise SystemExit("Refusing any database except explicit disposable localhost/source_audit")
ADMIN = 997600000
os.environ.update(
    DATABASE_URL=url, BOT_TOKEN="999999999:synthetic-dispatch-test-only",
    BOT_USERNAME="SourceDispatchTestBot", BOT_OWNER_ID=str(ADMIN),
    BASE_URL="https://source.invalid", SOURCE_MINIAPP_URL="https://source.invalid/menu",
    REQUIRED_CHANNEL="", SOURCE_CATALOG_SAFE_ROLLOUT="false",
    CATALOG_RETIREMENT_APPLY_ON_START="false", CATALOG_USAGE_AUDIT_ON_START="false",
)
import httpx
import requests
from fastapi.testclient import TestClient
from PIL import Image


def denied_network(*args, **kwargs):
    raise RuntimeError("External HTTP is forbidden in the dispatch regression")


async def denied_async_network(*args, **kwargs):
    denied_network()


httpx.HTTPTransport.handle_request = denied_network
httpx.AsyncHTTPTransport.handle_async_request = denied_async_network
requests.sessions.Session.send = denied_network

from database_core import run, pool
import database as db

db.create_tables()
# Import the actual Railway entrypoint, retaining every legacy router and fallback.
from catalog_rollout_entrypoint import app
from webapp_routes.aninexus_compat import _issue_session
from cards_service import build_cards_final_data

CATALOG = build_cards_final_data()
C1, C2, C3 = sorted(CATALOG["characters_by_id"])[:3]
seq = itertools.count(100_000_000 + uuid4().int % 1_000_000_000_000)
results, dispatches, captured = [], [], []
PREFIX = "/api/v1_7b82/collecting"


class TraceEndpoint:
    """Observe which endpoint the unchanged production ASGI app actually chose."""
    async def __call__(self, scope, receive, send):
        try:
            await app(scope, receive, send)
        finally:
            if scope["type"] == "http":
                endpoint = scope.get("endpoint")
                captured.append({"module": getattr(endpoint, "__module__", ""),
                                 "handler": getattr(endpoint, "__name__", "")})


def user(uid=None):
    uid = next(seq) if uid is None else uid
    db.create_or_get_user(uid)
    run("UPDATE users SET coins=100,dado_balance=5,dado_slot=%s WHERE user_id=%s",
        (db._slot_number_from_dt(db._now_sp()), uid))
    for cid in (C1, C2, C3):
        run("INSERT INTO user_card_collection(user_id,character_id,quantity) VALUES(%s,%s,30)", (uid, cid))
    return uid


def headers(uid):
    return {"Authorization": "Bearer " + _issue_session({"id": uid, "first_name": "Teste"})}


def scalar(sql, params=()):
    return next(iter(run(sql, params, fetch="one").values()))


def check(fn):
    try:
        fn()
        result = {"case": fn.__name__, "passed": True}
    except Exception as exc:
        result = {"case": fn.__name__, "passed": False, "error": type(exc).__name__,
                  "detail": str(exc), "trace": traceback.format_exc()}
    results.append(result)
    print(result["case"], result["passed"], flush=True)


with TestClient(TraceEndpoint(), raise_server_exceptions=True) as client:
    def call(method, path, uid, payload=None, status=200, **kwargs):
        h = headers(uid)
        h.update(kwargs.pop("headers", {}))
        response = client.request(method, PREFIX + path, headers=h, json=payload, **kwargs)
        assert response.status_code == status, (method, path, response.status_code, response.text[:400])
        data = response.json()
        assert not (isinstance(data, dict) and isinstance(data.get("error"), dict)
                    and data["error"].get("code") == "source_not_connected"), (method, path, data)
        return data

    @check
    def every_feature_route_dispatches_to_its_real_handler():
        tree = ast.parse((ROOT / "source_features/router.py").read_text())
        specs = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                        and isinstance(deco.func.value, ast.Name) and deco.func.value.id == "router"
                        and deco.func.attr in {"get", "post", "patch", "put", "delete"}):
                    specs.append((deco.func.attr.upper(), ast.literal_eval(deco.args[0]), node.name))
        assert len(specs) >= 25, "Unexpected feature route inventory"
        for method, path, name in specs:
            sample = path.replace("{character_id}", str(C1)).replace("{anime_id}", "1")
            sample = re.sub(r"\{[^}]+\}", "00000000-0000-4000-8000-000000000001", sample)
            response = client.request(method, PREFIX + sample, headers=headers(user()),
                                      json={} if method != "GET" else None)
            actual = captured[-1]
            dispatches.append({"method": method, "path": path, "expected_handler": name,
                               **actual, "status": response.status_code})
        failures = [r for r in dispatches if r["module"] != "source_features.router"
                    or r["handler"] != r["expected_handler"] or r["status"] >= 500]
        assert not failures, failures

    @check
    def authentication_validation_and_legacy_block_are_preserved():
        uid = user()
        assert client.post(PREFIX + "/wishes", json={"ids": [C1]}).status_code == 401
        assert client.patch(PREFIX + "/settings", headers={"Authorization": "Bearer invalid"}, json={}).status_code == 401
        call("POST", "/market", uid, {"character_id": True, "quantity": 1, "price": 1, "request_id": str(uuid4())}, 422)
        call("PATCH", "/settings", uid, {"user_id": uid + 1, "share_inline": True}, 422)
        call("POST", "/events/" + str(uuid4()) + "/publish", uid, {}, 403)
        for method in ("POST", "PATCH"):
            response = client.request(method, "/api/v1_7b82/unimplemented-test-only", headers=headers(uid), json={})
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "source_not_connected"

    if "--dispatch-only" not in sys.argv:
        @check
        def preferences_wishes_and_protection_persist_via_full_app():
            uid = user()
            call("PATCH", "/settings", uid, {"discoverable": True, "share_inline": True})
            assert call("GET", "/settings", uid)["share_inline"] is True
            call("POST", "/wishes", uid, {"ids": [C2]})
            assert C2 in [r["id"] for r in call("GET", "/characters?view=wishes", uid)["items"]]
            call("POST", "/wishes", uid, {"ids": [C2], "enabled": False})
            assert not call("GET", "/characters?view=wishes", uid)["items"]
            aid = next(a for a, rows in CATALOG["characters_by_anime"].items() if 0 < len(rows) < 20)
            call("POST", f"/wishes/work/{aid}", uid)
            call("PUT", f"/characters/{C1}/protection", uid, {"enabled": True})
            assert call("GET", "/characters?view=protected", uid)["items"]
            data = call("POST", "/workshop/preview", uid, {"items": [{"character_id": C1, "quantity": 1}]}, 409)
            assert data["error"]["code"] == "card_protected"
            call("PUT", f"/characters/{C1}/protection", uid, {"enabled": False})

        @check
        def workshop_preview_recycle_replay_craft_and_equip():
            uid = user()
            items = [{"character_id": C1, "quantity": 10}]
            assert call("POST", "/workshop/preview", uid, {"items": items})["fragments"] == 10
            payload = {"items": items, "request_id": str(uuid4())}
            receipt = call("POST", "/workshop/recycle", uid, payload)
            assert call("POST", "/workshop/recycle", uid, payload) == receipt
            assert db.get_user_card_quantity(uid, C1) == 20
            cosmetic = call("POST", "/workshop/craft", uid, {"recipe": "frame-bronze", "request_id": str(uuid4())})
            call("PUT", "/cosmetics/equipped", uid, {"cosmetic_id": cosmetic["cosmetic_id"]})
            assert call("GET", "/cosmetics/profile", uid)["cosmetic_id"] == "frame-bronze"

        @check
        def fixed_market_purchase_and_replay_change_balance_once():
            seller, buyer = user(), user()
            payload = {"character_id": C1, "quantity": 1, "price": 10, "request_id": str(uuid4())}
            listing = call("POST", "/market", seller, payload)
            assert call("POST", "/market", seller, payload) == listing
            action = {"action": "buy", "version": 1, "request_id": str(uuid4())}
            receipt = call("POST", f"/market/{listing['id']}/action", buyer, action)
            assert call("POST", f"/market/{listing['id']}/action", buyer, action) == receipt
            assert scalar("SELECT coins FROM users WHERE user_id=%s", (seller,)) == 110
            assert scalar("SELECT coins FROM users WHERE user_id=%s", (buyer,)) == 90
            assert db.get_user_card_quantity(seller, C1) == 29
            assert db.get_user_card_quantity(buyer, C1) == 31

        @check
        def auction_refund_settlement_and_cancellation():
            seller, first, second = user(), user(), user()
            listing = call("POST", "/market", seller, {"character_id": C2, "quantity": 1, "kind": "auction", "price": 10, "request_id": str(uuid4())})
            path = f"/market/{listing['id']}"
            call("POST", path + "/action", first, {"action": "bid", "version": 1, "amount": 10, "request_id": str(uuid4())})
            call("POST", path + "/action", second, {"action": "bid", "version": 2, "amount": 11, "request_id": str(uuid4())})
            assert scalar("SELECT coins FROM users WHERE user_id=%s", (first,)) == 100
            run("UPDATE source_market SET ends_at=NOW()-INTERVAL '1 second' WHERE id=%s", (listing["id"],))
            call("POST", path + "/settle", seller)
            call("POST", path + "/settle", seller)
            assert db.get_user_card_quantity(second, C2) == 31
            assert scalar("SELECT SUM(coins) FROM users WHERE user_id=ANY(%s)", ([seller, first, second],)) == 300
            listing = call("POST", "/market", seller, {"character_id": C3, "quantity": 1, "price": 10, "request_id": str(uuid4())})
            assert call("POST", f"/market/{listing['id']}/action", seller, {"action": "cancel", "version": 1, "request_id": str(uuid4())})["status"] == "cancelled"

        @check
        def daily_and_weekly_milestone_share_existing_ledger():
            uid = user()
            assert call("POST", "/daily/claim", uid)["already_claimed"] is False
            assert call("POST", "/daily/claim", uid)["already_claimed"] is True
            day = db._daily_day_start_ts_sp()
            for n in range(1, 7):
                run("INSERT INTO daily_rewards(user_id,day_start_ts,reward_type,reward_amount) VALUES(%s,%s,'coins',1)", (uid, day - n * 86400))
            assert call("POST", "/daily/milestone", uid)["already_claimed"] is False
            assert call("POST", "/daily/milestone", uid)["already_claimed"] is True

        @check
        def event_draft_publish_contribute_and_claim():
            admin, participant = user(ADMIN), user()
            now = datetime.now(timezone.utc)
            payload = {"title": "Evento sintético", "description": "Somente no banco descartável de teste", "character_ids": [C1], "goal": 1, "reward_label": "Teste", "starts_at": (now-timedelta(minutes=1)).isoformat(), "ends_at": (now+timedelta(hours=1)).isoformat(), "request_id": str(uuid4())}
            event = call("POST", "/events", admin, payload)
            assert event["id"] not in [x["id"] for x in call("GET", "/events", participant)["items"]]
            call("POST", f"/events/{event['id']}/publish", admin)
            call("POST", f"/events/{event['id']}/contribute", participant, {"character_id": C1, "request_id": str(uuid4())})
            assert call("POST", f"/events/{event['id']}/claim", participant)["already_claimed"] is False
            assert call("POST", f"/events/{event['id']}/claim", participant)["already_claimed"] is True
            assert db.get_user_card_quantity(participant, C1) == 30

        @check
        def identify_checks_consent_and_uses_only_mocked_external_provider():
            import webapp
            uid = user()
            call("POST", "/identify", uid, status=400, content=b"no consent")
            buf = io.BytesIO()
            Image.new("RGB", (20, 20)).save(buf, format="PNG")
            external = AsyncMock()
            external.post.return_value = httpx.Response(200, json={"result": [{"anilist": {"id": 20, "title": {"romaji": "Naruto"}, "isAdult": False}, "episode": 1, "similarity": 0.95, "from": 10}]}, request=httpx.Request("POST", "https://api.trace.moe/search"))
            with patch.object(webapp, "_get_http_client", return_value=external):
                data = call("POST", "/identify", uid, content=buf.getvalue(), headers={"X-Scene-Consent": "yes", "Content-Type": "image/png"})
            assert data["items"][0]["anime_id"] == 20
            external.post.assert_awaited_once()

report = {"passed": all(r["passed"] for r in results), "cases": results, "dispatches": dispatches,
          "scope": "Full production ASGI composition; real disposable PostgreSQL; locally signed synthetic sessions. External HTTP blocked; trace.moe response mocked. No production accounts or transactions."}
out = Path(sys.argv[1] if len(sys.argv) > 1 else "entrypoint-proof.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
pool.close()
raise SystemExit(0 if report["passed"] else 1)
