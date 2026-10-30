"""Regenerate results.csv, resources.csv, metadata.json and EVERY figure from the saved data under raw/.
No QPU, no IBM account, no network: socket connections are blocked for the duration of the run.

    python scripts/reproduce_all.py
"""
import socket


def _no_network(*a, **k):
    raise RuntimeError("network access attempted during offline reproduction")


socket.socket.connect = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network

from qtrust import export, figures  # noqa: E402

if __name__ == "__main__":
    res, rsc, meta = export.build_all()
    figures.all_figures()
    print(f"results.csv: {len(res)} rows | resources.csv: {len(rsc)} rows | metadata.json keys: {len(meta)}")
    print(res.groupby(["source", "validation_status"]).size().to_string())
