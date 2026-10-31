import pytest

from qtrust import figures as F
from test_export import _mini_raw


@pytest.fixture()
def mini(patches, tmp_path, monkeypatch):
    raw = _mini_raw(tmp_path, {"P12": patches["P12"]})
    monkeypatch.setattr(F, "RAW", raw)
    monkeypatch.setattr(F, "FIG", tmp_path / "figs")
    return raw, tmp_path / "figs"


def test_figures_render_from_saved_data_only(mini):
    raw, figs = mini
    F.classical_accuracy(pids=("P12",))
    F.trajectories("P12")
    F.exact_overview(pids=("P12",))
    d = F.resources()
    names = {p.name for p in figs.iterdir()}
    assert {"classical_accuracy_P12.png", "trajectories_P12.png", "magnetisation.png", "classical_resources.png"} <= names
    assert len(d) == 1 and d.tree_gb.iloc[0] == pytest.approx(0.3)


def test_figures_never_read_exploratory_dt02_data(mini, tmp_path):
    raw, figs = mini
    (raw / "exploratory_dt0.2" / "classical").mkdir(parents=True)
    (raw / "exploratory_dt0.2" / "classical" / "P12_mps_chi64.csv").write_text("graph_id\nP12\n")
    assert F._runs(raw / "classical_dt0.1", "P12") and not F._runs(raw / "classical_dt0.1", "P99")


def test_showcase_figures_noop_without_hardware_and_render_with_it(mini, tmp_path, monkeypatch):
    from pathlib import Path

    from qtrust import showcase as S
    raw, figs = mini
    S.showcase_figures()                                   # no hardware table in the mini data: nothing is drawn, nothing fails
    assert not list(figs.glob("showcase_*"))
    real = Path(__file__).resolve().parents[1] / "raw"
    if (real / "hardware" / "hardware_results.csv").exists():
        monkeypatch.setattr(F, "RAW", real)
        S.rmse_surface_3d("P18"); S.drift_surface_3d("P18")
        assert {p.name for p in figs.glob("showcase_*")} == {"showcase_P18_rmse_surface_3d.png", "showcase_P18_drift_3d.png"}

