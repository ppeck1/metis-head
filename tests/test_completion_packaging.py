from pathlib import Path


def test_distribution_includes_only_application_packages_and_static_assets():
    manifest = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["metis_head*"]' in manifest
    assert 'exclude = ["artifacts*", "models*", "tests*"]' in manifest
    assert 'metis_head = ["static/*.html", "static/*.js"]' in manifest
    assert '"python-multipart>=0.0.9"' in manifest
