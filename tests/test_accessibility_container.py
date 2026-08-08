from pathlib import Path

from app.services.accessibility.rule_catalog import AXE_CORE_VERSION, AXE_SOURCE_PATH


def test_render_image_contains_exact_pinned_axe_core() -> None:
    dockerfile = (Path(__file__).parents[1] / "Dockerfile.render").read_text()

    assert f"npm pack axe-core@{AXE_CORE_VERSION}" in dockerfile
    assert f"/opt/axe/axe.min.js {AXE_SOURCE_PATH}" in dockerfile
    assert "/opt/axe/LICENSE" in dockerfile
    assert "http" not in next(
        line for line in dockerfile.splitlines() if "npm pack axe-core@" in line
    )
