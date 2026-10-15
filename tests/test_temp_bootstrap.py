"""Exercise real pytest startup without an existing configured temp parent."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("absolute", [False, True], ids=["relative", "absolute"])
def test_missing_basetemp_parent_in_fresh_session(tmp_path, absolute):
    checkout = tmp_path / "checkout"
    tests = checkout / "tests"
    tests.mkdir(parents=True)
    (checkout / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tests / "conftest.py").write_text(
        Path(__file__).with_name("conftest.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tests / "test_fixture.py").write_text(
        "def test_real_tmp_path(tmp_path):\n"
        "    target = tmp_path / 'synthetic.txt'\n"
        "    target.write_text('synthetic', encoding='utf-8')\n"
        "    assert target.read_text(encoding='utf-8') == 'synthetic'\n",
        encoding="utf-8",
    )
    parent = checkout / ".tmp"
    assert not parent.exists()
    basetemp = parent / "pytest" if absolute else Path(".tmp/pytest")
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "-q", "--basetemp", str(basetemp), "tests"],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert parent.is_dir()
