"""Structural invariants complement the compiled-browser viewport regressions."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aninexus_frontend/src"


def test_all_registered_native_routes_use_the_shared_main():
    routes = json.loads((SRC / "native/routes.json").read_text())
    assert all(route in routes for route in ["/", "/menu", "/cards", "/shop", "/dado", "/terms"])
    main = (SRC / "main.tsx").read_text()
    assert main.count("installTelegramViewport();") == 1
    assert main.index("installTelegramViewport();") < main.index("createRoot(container)")


def test_fullscreen_is_version_gated_not_a_route_side_effect():
    controller = (SRC / "telegram/viewport.ts").read_text()
    assert "supports('8.0')" in controller
    assert "requestFullscreen" not in (SRC / "App.tsx").read_text()
    assert "setInterval" not in controller
    for event in ["fullscreenChanged", "fullscreenFailed", "safeAreaChanged", "contentSafeAreaChanged", "viewportChanged"]:
        assert event in controller
    assert "offEvent" in controller


def test_fixed_layers_respect_the_same_safe_area():
    for path in ["components/character/Modal.tsx", "components/pet/PetActionModal.tsx", "components/ui/GachaReveal.tsx", "components/minigames/RewardModal.tsx", "components/IntroLoading.tsx", "native/ui.tsx"]:
        assert "source-safe-overlay" in (SRC / path).read_text(), path
    assert "source-navigation-drawer" in (SRC / "components/NavigationDrawer.tsx").read_text()
    assert "source-toast-viewport" in (SRC / "components/ui/Toast.tsx").read_text()
    css = (SRC / "index.css").read_text()
    for side in ["top", "bottom", "left", "right"]:
        assert f"--source-safe-{side}: calc(max(env(safe-area-inset-{side}" in css
        assert f"var(--source-content-{side}, 0px)" in css
