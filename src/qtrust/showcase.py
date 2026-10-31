"""3-D showcase figures drawn only from the saved hardware tables (no new computation of any verdict).

Layouts are a deterministic force layout of the patch graph (same family as `figures/patch_*.png`); heights are measured quantities."""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from matplotlib import cm
from matplotlib.colors import Normalize

from . import figures as F

HWNOTE = "Computed from raw/hardware/hardware_results.csv (frozen analysis output); ibm_fez, accounts 1 and 2, 16 384 shots per circuit. Heights are measured values, not model output."
ACC = {1: "#1b9e77", 2: "#7570b3"}


def _hw() -> pd.DataFrame | None:
    return F._hw()


def _graph(pid: str):
    p = json.loads((F.RAW / "patches" / f"{pid}.json").read_text())
    G = nx.Graph(); G.add_nodes_from(range(p["n"])); G.add_edges_from(map(tuple, p["edges"]))
    return p, G, nx.kamada_kawai_layout(G)


def _style(ax):
    ax.xaxis.set_pane_color((1, 1, 1, 0)); ax.yaxis.set_pane_color((1, 1, 1, 0)); ax.zaxis.set_pane_color((0.96, 0.96, 0.96, 1))
    ax.set_xticks([]); ax.set_yticks([])


def patch_error_3d(pid: str = "P18", Jt: float = 0.8):
    """Qubit stems = |m_i - exact| (readout-corrected); edge colour = |C_ij - exact|; one panel per account."""
    h = _hw()
    if h is None:
        return
    p, G, pos = _graph(pid)
    d = h[(h.graph_id == pid) & (h.method == "readout") & (h.Jt == Jt)]
    fig = plt.figure(figsize=(12.5, 5.8))
    norm = Normalize(0, 0.25); zmax = 0.4
    for k, acct in enumerate((1, 2), 1):
        ax = fig.add_subplot(1, 2, k, projection="3d"); _style(ax)
        m = d[(d.account == acct) & (d.observable == "m")].assign(i=lambda x: x.sites.astype(int)).set_index("i")
        c = d[(d.account == acct) & (d.observable == "C")]
        for _, r in c.iterrows():
            a, b = map(int, str(r.sites).split("-")); err = abs(r.estimate - r.reference)
            ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]], [0, 0], color=cm.magma_r(norm(err)), lw=3.2 if err > 0.1 else 1.8, solid_capstyle="round")
        for v in G:
            e = abs(m.loc[v].estimate - m.loc[v].reference); x, y = pos[v]
            ax.plot([x, x], [y, y], [0, e], color=ACC[acct], lw=2.4); ax.scatter([x], [y], [e], s=26, color=ACC[acct], depthshade=False)
        if pid == "P18":
            (x0, y0), (x1, y1) = pos[0], pos[4]
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, 0.0, "pair 0-4 (phys. 16-23)", fontsize=6.5, color="#b30000", ha="center", bbox=dict(fc="white", ec="none", alpha=.7, pad=1))
        ax.set_zlim(0, zmax); ax.set_zlabel("|m_i - exact|", fontsize=8); ax.view_init(elev=24, azim=-58)
        ax.set_title(f"account {acct}", fontsize=10, color=ACC[acct])
    sm = cm.ScalarMappable(norm=norm, cmap="magma_r")
    cax = fig.add_axes([0.36, 0.12, 0.28, 0.014]); fig.colorbar(sm, cax=cax, orientation="horizontal", label="edge colour: |C_ij - exact| (clipped at 0.25)")
    fig.suptitle(f"{pid} patch on ibm_fez at Jt = {Jt}: readout-corrected single-site error (stems) and edge-covariance error (edge colour), same circuits in two windows", fontsize=9.5)
    F._save(fig, f"showcase_{pid}_patch_error_3d.png", HWNOTE)


def rmse_surface_3d(pid: str = "P18"):
    """RMSE of the readout-corrected estimates by observable class and Jt, with the 0.05 policy tolerance as a plane."""
    h = _hw()
    if h is None:
        return
    jts = sorted(j for j in h[h.graph_id == pid].Jt.unique() if j >= 0.4); classes = [c for c, _ in F.CLASSES]
    fig = plt.figure(figsize=(12.5, 5.6))
    for k, acct in enumerate((1, 2), 1):
        ax = fig.add_subplot(1, 2, k, projection="3d"); _style(ax)
        d = h[(h.graph_id == pid) & (h.method == "readout") & (h.account == acct)]
        for iy, cl in enumerate(classes):
            for ix, jt in enumerate(jts):
                g = d[(d.observable == cl) & (d.Jt == jt)]; e = (g.estimate - g.reference).to_numpy(); e = e[np.isfinite(e)]
                if len(e):
                    r = float(np.sqrt(np.mean(e ** 2)))
                    ax.bar3d(ix - .3, iy - .3, 0, .6, .6, r, color=cm.viridis(Normalize(0, .2)(r)), alpha=.92, edgecolor="#333333", linewidth=.25)
        xx, yy = np.meshgrid([-.5, len(jts) - .5], [-.5, len(classes) - .5])
        ax.plot_surface(xx, yy, np.full_like(xx, .05, dtype=float), color="#d62728", alpha=.18)
        ax.set_xticks(range(len(jts))); ax.set_xticklabels([f"{j:g}" for j in jts], fontsize=7); ax.set_xlabel("Jt", fontsize=8)
        ax.set_yticks(range(len(classes))); ax.set_yticklabels(["m", "C", "G", "κ"], fontsize=8); ax.set_zlabel("RMSE vs exact", fontsize=8)
        ax.set_zlim(0, .2); ax.view_init(elev=26, azim=-52); ax.set_title(f"account {acct}", fontsize=10, color=ACC[acct])
    fig.suptitle(f"{pid}, readout-corrected: RMSE by observable class and Jt (red plane = 0.05 policy tolerance). Four-site classes have the smaller error but also the smaller signal", fontsize=9.5)
    F._save(fig, f"showcase_{pid}_rmse_surface_3d.png", HWNOTE)


def p40_jt0_3d():
    """P40 at Jt = 0 (no entangling gates): raw |m_i - 1| per qubit in the two windows; isolates readout/preparation from dynamics."""
    h = _hw()
    if h is None:
        return
    p, G, pos = _graph("P40")
    d = h[(h.graph_id == "P40") & (h.method == "raw") & (h.Jt == 0) & (h.observable == "m")]
    fig = plt.figure(figsize=(12.5, 5.6))
    for k, acct in enumerate((1, 2), 1):
        ax = fig.add_subplot(1, 2, k, projection="3d"); _style(ax)
        m = d[d.account == acct].assign(i=lambda x: x.sites.astype(int)).set_index("i")
        for a, b in G.edges:
            ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]], [0, 0], color="#bbbbbb", lw=1)
        for v in G:
            e = abs(m.loc[v].estimate - 1.0); x, y = pos[v]
            ax.plot([x, x], [y, y], [0, e], color=ACC[acct], lw=2); ax.scatter([x], [y], [e], s=18, color=ACC[acct], depthshade=False)
        ax.set_zlim(0, .6); ax.set_zlabel("|m_i - 1| (raw)", fontsize=8); ax.view_init(elev=26, azim=-60)
        ax.set_title(f"account {acct}: max {float((m.estimate - 1).abs().max()):.2f}", fontsize=10, color=ACC[acct])
    fig.suptitle("P40 (40 qubits) at Jt = 0, raw counts: with no entangling gates every |m_i - 1| is preparation/readout error. Heights differ between the two windows", fontsize=9.5)
    F._save(fig, "showcase_P40_Jt0_3d.png", HWNOTE)


def drift_surface_3d(pid: str = "P18"):
    """Fraction of matched estimates beyond 4 shot-noise SEs between the two windows, by class and Jt (correlated comparisons)."""
    f = F.RAW / "hardware" / "drift_account2_vs_1.csv"
    if not f.exists():
        return
    d = pd.read_csv(f); d = d[(d.graph_id == pid) & d.method.isin(["raw", "readout"])]
    jts = sorted(d.assign(Jt=d.N * F._dt()).Jt.round(3).unique()); classes = [c for c, _ in F.CLASSES]
    d = d.assign(Jt=(d.N * F._dt()).round(3))
    fig = plt.figure(figsize=(7.5, 5.6)); ax = fig.add_subplot(projection="3d"); _style(ax)
    for iy, cl in enumerate(classes):
        for ix, jt in enumerate(jts):
            g = d[(d.observable == cl) & (d.Jt == jt)]
            if len(g):
                fr = float(g.drift_flag.mean()); ax.bar3d(ix - .3, iy - .3, 0, .6, .6, fr, color=cm.plasma(fr), alpha=.92, edgecolor="#333333", linewidth=.25)
    ax.set_xticks(range(len(jts))); ax.set_xticklabels([f"{j:g}" for j in jts], fontsize=7); ax.set_xlabel("Jt", fontsize=8)
    ax.set_yticks(range(len(classes))); ax.set_yticklabels(["m", "C", "G", "κ"], fontsize=8); ax.set_zlim(0, 1); ax.set_zlabel("fraction beyond 4 SE", fontsize=8)
    ax.view_init(elev=26, azim=-50)
    fig.suptitle(f"{pid}: window-to-window disagreement (raw + readout rows)\ncorrelated comparisons; account and calibration window are confounded", fontsize=9)
    F._save(fig, f"showcase_{pid}_drift_3d.png", "Computed from raw/hardware/drift_account2_vs_1.csv (frozen analysis output).")


def showcase_figures():
    patch_error_3d("P18"); rmse_surface_3d("P18"); p40_jt0_3d(); drift_surface_3d("P18")
