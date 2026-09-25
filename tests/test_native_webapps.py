"""Contracts for the unified entrypoint; no production accounts or network calls."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from webapp_routes import native_webapps as native

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "aninexus_frontend/src/native/routes.json").read_text())


def build_app(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "index.html").write_text(
        '<html><div id="root"></div><script src="/assets/native.js"></script></html>'
    )
    (runtime / "native-routes.json").write_text(json.dumps(MANIFEST))
    monkeypatch.setattr(native, "RUNTIME", runtime)
    app = FastAPI()
    for path in MANIFEST:
        app.add_api_route(path, lambda: HTMLResponse("legacy"), methods=["GET"])
    app.add_api_route("/api/untouched", lambda: {"api": True}, methods=["GET"])
    app.add_api_route("/cakto/callback", lambda: {"callback": True}, methods=["POST"])
    native.install_native_webapps(app)
    return app


@pytest.mark.parametrize("path", list(MANIFEST))
def test_every_legacy_html_path_delivers_same_react_app(tmp_path, monkeypatch, path):
    app = build_app(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.get(
        path, params={"uid": "123", "anime_id": "21", "q": "One Piece"}
    )
    assert response.status_code == 200
    assert response.headers["x-source-ui"] == "native"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.content == client.get("/menu").content
    assert "legacy" not in response.text
    assert response.url.path == '/menu'
    assert len(response.history) == (0 if path == '/menu' else 1)
    assert response.headers['x-source-ui-version'] == client.get('/api/native/version').json()['version']
    if path != '/menu':
        assert response.history[0].status_code == 307
        assert response.url.params['tab'] == MANIFEST[path]['tab']
        assert response.url.params['uid'] == '123'
        assert response.url.params['q'] == 'One Piece'
        for key, value in MANIFEST[path].get('params', {}).items():
            assert response.url.params[key] == value


def test_installation_is_idempotent_and_preserves_api(tmp_path, monkeypatch):
    app = build_app(tmp_path, monkeypatch)
    native.install_native_webapps(app)
    for path in MANIFEST:
        assert sum(getattr(route, "path", None) == path for route in app.routes) == 1
    client = TestClient(app)
    assert client.get("/api/untouched").json() == {"api": True}
    assert client.post("/cakto/callback").json() == {"callback": True}
    assert client.get("/not-a-page").status_code == 404


def test_manifest_covers_all_literal_html_routes():
    paths = set()
    for path in [ROOT / "webapp.py", *list((ROOT / "webapp_routes").glob("*.py"))]:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
            ):
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if any(
                        k.arg == "response_class"
                        and isinstance(k.value, ast.Name)
                        and k.value.id == "HTMLResponse"
                        for k in node.keywords
                    ):
                        paths.add(arg.value)
    assert paths <= set(MANIFEST), f"Unmigrated HTML routes: {paths - set(MANIFEST)}"
    assert len(MANIFEST) >= 25
    assert (
        "from webapp_entrypoint import app as web_app" in (ROOT / "bot.py").read_text()
    )


def test_manifest_cannot_replace_api(tmp_path, monkeypatch):
    app = build_app(tmp_path, monkeypatch)
    path = native.RUNTIME / "native-routes.json"
    path.write_text(
        json.dumps({"/menu": {"tab": "profile"}, "/api/payment": {"tab": "shop"}})
    )
    with pytest.raises(RuntimeError):
        native.install_native_webapps(app)


def test_missing_build_fails_explicitly(tmp_path, monkeypatch):
    monkeypatch.setattr(native, "RUNTIME", tmp_path)
    with pytest.raises(RuntimeError, match="Build nativo ausente"):
        native.install_native_webapps(FastAPI())


def test_nickname_requires_verified_identity(monkeypatch):
    monkeypatch.delenv("ALLOW_INSECURE_WEBAPP_UID_FALLBACK", raising=False)
    with pytest.raises(HTTPException) as exc:
        native.native_nickname({"uid": 123, "nickname": "Akira"}, "")
    assert exc.value.status_code == 401


def test_nickname_uses_signature_owner(monkeypatch):
    monkeypatch.setattr(native, "resolve_webapp_user", lambda **kwargs: {"user_id": 42})
    monkeypatch.setattr(
        native,
        "change_nickname_atomic",
        lambda uid, nickname: {"uid": uid, "nickname": nickname},
    )
    assert native.native_nickname({"nickname": "Akira"}, "signed") == {
        "uid": 42,
        "nickname": "Akira",
    }


def test_terms_are_native_structured_text_without_html_execution():
    parser = native._TermsSections()
    parser.feed(
        '<div class="section"><div class="sectionTitle">Privacidade &amp; dados</div><div class="sectionText">Seu <b>texto</b> original.</div></div>'
    )
    assert parser.sections == [
        {"title": "Privacidade & dados", "text": "Seu texto original."}
    ]


def test_new_screens_use_shared_components_not_legacy_html():
    folder = ROOT / "aninexus_frontend/src/native"
    text = "\n".join(p.read_text() for p in folder.glob("*.tsx"))
    for forbidden in [
        "<iframe",
        "dangerouslySetInnerHTML",
        "premium_webapp_ui",
        "document.write(",
    ]:
        assert forbidden not in text
    for required in [
        "components/ui/Button",
        "components/ui/Card",
        "NativePage",
        "sourcePost",
        "sourceFetch",
    ]:
        assert required in text or required in (folder / "api.ts").read_text()
    assert "install_native_webapps(app)" in (ROOT / "webapp_entrypoint.py").read_text()
    assert (ROOT / "webapp_entrypoint.py").read_text().rindex(
        "install_native_webapps(app)"
    ) > (ROOT / "webapp_entrypoint.py").read_text().rindex("_install_runtime_routes()")


def test_runtime_manifest_matches_source_when_built():
    compiled = ROOT / "aninexus_runtime/native-routes.json"
    assert compiled.is_file()
    assert json.loads(compiled.read_text()) == MANIFEST


def test_old_links_preserve_init_data_without_redirecting_apis(tmp_path, monkeypatch):
    app = build_app(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.get('/cards/search?uid=42&q=A%26B&tgWebAppData=user%3Dabc%26hash%3Ddef', follow_redirects=False)
    assert response.status_code == 307
    assert '#' not in response.headers['location']
    from urllib.parse import urlsplit, parse_qs
    query = parse_qs(urlsplit(response.headers['location']).query)
    assert query['tgWebAppData'] == ['user=abc&hash=def']
    assert query['q'] == ['A&B'] and query['view'] == ['characters']
    assert client.head('/menu').status_code == 200
    assert client.get('/api/untouched').json() == {'api': True}


def test_native_entries_precede_legacy_included_routers(tmp_path, monkeypatch):
    from fastapi import APIRouter
    app = build_app(tmp_path, monkeypatch)
    nested = APIRouter()
    nested.add_api_route('/memoria', lambda: HTMLResponse('old included memory'), methods=['GET'])
    nested.add_api_route('/api/inside-router', lambda: {'preserved': True}, methods=['GET'])
    app.include_router(nested)
    native.install_native_webapps(app)
    client = TestClient(app)
    response = client.get('/memoria')
    assert response.headers['x-source-ui'] == 'native'
    assert 'old included memory' not in response.text
    assert response.url.path == '/menu'
    assert client.get('/api/inside-router').json() == {'preserved': True}
