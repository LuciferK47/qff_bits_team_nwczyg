import zipfile

import pytest

from qtrust import package as P


def test_sanitize_and_scan():
    assert "/home/" not in P.sanitize('File "/home/alice/work/x.py", line 3')
    assert P.scan("QISKIT_IBM_TOKEN=abcdef123456") and P.scan('{"token": "abcdefghijklmnop1234"}')
    assert not P.scan("QISKIT_IBM_TOKEN=") and not P.scan("hash 24098d91e191b4b827d961ca3e6485c5946fb6a0")
    assert "local home path" in P.scan("/home/bob/data")


def _tree(root):
    (root / "src").mkdir(); (root / "raw").mkdir(); (root / "configs").mkdir(); (root / ".venv").mkdir(); (root / "src/__pycache__").mkdir()
    (root / "src/a.py").write_text("x = 1\n"); (root / "src/__pycache__/a.pyc").write_bytes(b"x")
    (root / ".venv/big.txt").write_text("junk"); (root / "raw/queue.log").write_text('Traceback File "/home/carol/repo/y.py"\n')
    (root / "raw/data.json").write_text("{}")
    for f in ("README.md", "requirements.lock", "results.csv", "resources.csv", "metadata.json"):
        (root / f).write_text("ok\n")
    (root / "configs/team.yaml").write_text("team_name: my_team\n")


def test_build_excludes_venv_and_caches_and_sanitizes_logs(tmp_path):
    _tree(tmp_path)
    path, info = P.build(tmp_path)
    assert path.name == "my_team.zip" and not info["missing_required"] and not info["forbidden_present"]
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert "src/a.py" in names and not any(".venv" in n or "__pycache__" in n for n in names)
        assert "/home/" not in z.read("raw/queue.log").decode()
    assert info["sanitized_files"] >= 1


def test_build_refuses_a_credential(tmp_path):
    _tree(tmp_path)
    (tmp_path / "raw/oops.json").write_text('{"api_key": "abcdefghijklmnopqrst"}')
    with pytest.raises(RuntimeError, match="credential"):
        P.build(tmp_path)
    assert not (tmp_path / "dist/my_team.zip").exists()


def test_scan_ignores_empty_placeholders_but_catches_real_tokens():
    from qtrust.package import scan
    assert scan("QISKIT_IBM_TOKEN=\nQISKIT_IBM_INSTANCE=\n") == []
    assert scan("QISKIT_IBM_TOKEN=abcd1234abcd1234abcd")
    assert scan('api_key: "A1b2C3d4E5f6G7h8I9"')


def test_archive_never_contains_zip_files_so_a_committed_team_zip_cannot_nest_itself():
    from pathlib import Path
    from qtrust import package
    files = package.collect(Path(__file__).resolve().parents[1])
    assert files and not [f for f in files if f.suffix == ".zip"]
