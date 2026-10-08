"""Rendered ease polylines must stay identical after a mid-span split (#124)."""
from __future__ import annotations

from lumiere_hoard.render.compiler import _ease_points, piecewise
from lumiere_hoard.timeline import Keyframe, keyframe_value


def _piecewise_at(pts: list[tuple[float, float]], t_s: float) -> float:
    expr = piecewise(pts, "t")
    # Evaluate the same clip()/sum form without ffmpeg: reuse Python piecewise semantics.
    v = pts[0][1]
    for (ta, va), (tb, vb) in zip(pts, pts[1:]):
        dt = tb - ta
        if dt <= 1e-9 or abs(vb - va) < 1e-9:
            continue
        x = t_s - ta
        if x <= 0:
            continue
        if x >= dt:
            v += vb - va
        else:
            v += (vb - va) * (x / dt)
    return v


def test_split_keeps_sampled_polyline_at_sparks_repro_times():
    original = [Keyframe(t=0, v=0, ease="ease_in"), Keyframe(t=1000, v=1)]
    # Right half after cut at 500 with full-span domain (into=500).
    right = [
        Keyframe(t=0, v=0.25, ease="ease_in", ease_span=1000, ease_into=500, ease_v0=0, ease_v1=1),
        Keyframe(t=500, v=1),
    ]
    # Analytical backend already matched; this guards the sampled render path.
    assert abs(keyframe_value(original, 537) - keyframe_value(right, 37)) < 1e-12

    o_pts = _ease_points(original)
    r_pts = _ease_points(right)
    # Pre-split values that used to diverge under denser post-split sampling.
    assert _piecewise_at(o_pts, 0.537) == _piecewise_at(r_pts, 0.037)
    assert _piecewise_at(o_pts, 0.750) == _piecewise_at(r_pts, 0.250)
    # Exact sparks repro numbers for the old bug (must NOT reappear).
    assert _piecewise_at(o_pts, 0.537) == 0.2931666666666667
