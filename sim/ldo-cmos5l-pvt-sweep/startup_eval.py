"""Deterministic startup/enable measurement evaluator (issue #69). stdlib only.

Implements the measurement contract of README.md "Startup campaign (issue
#69)" for the trace produced by testbench/tb_startup_cmos5l.spice.tmpl. It
is a proposed METHODOLOGY for DR-0007 row 9, not a ratified target: nothing
here closes row 9.

Input: a trace dict of equal-length float lists
    t, vout, en, vin            required
    eaout, ivin                 optional (stress / supply current; ivin is
                                the current INTO the Vin source's + node, so
                                the supply current is -ivin)
plus a Config. Output: a flat dict of metrics and a verdict in
{"pass", "fail", "insufficient"}. Fail-closed rules: a missing/short/gappy/
non-finite trace, a missing EN edge, or an observation window shorter than
the contract is "insufficient", and "insufficient" is never a pass.

Time zero of each case is the EN = VIN/2 crossing (linear interpolation).
Cases: "start" (first rising crossing) and "reen" (the rising crossing that
follows a falling one). The off state is the interval before the first
crossing (cold start).
"""
import dataclasses
import math

BAND_LO = 1.764
BAND_HI = 1.836
VNOM = 1.8


@dataclasses.dataclass(frozen=True)
class Config:
    vnom: float = VNOM
    band_lo: float = BAND_LO
    band_hi: float = BAND_HI
    settle_limit_s: float = 3e-3       # row 9: within 3 ms of enable
    min_observe_s: float = 5e-3        # contract: >= 5 ms after enable
    monotonic_tol_v: float = 1e-3      # proposed numerical tolerance
    sensitivity_tols_v: tuple = (1e-4, 1e-3, 1e-2)
    max_dt_s: float = 1e-6             # transient timestep cap
    dt_slack: float = 1.01             # float formatting slack on the cap
    off_vout_limit_v: float = 0.05     # proposed: no sustained driven output
    off_window_skip_s: float = 0.0     # nothing skipped: op point is exact
    stress_ref_v: float = 3.3          # DR-0002 VGS rating, informational
    expect_cases: tuple = ("start", "reen")


def _finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def validate_trace(tr, cfg):
    """Return a list of reasons the trace cannot be evaluated ([] if ok)."""
    why = []
    if not isinstance(tr, dict):
        return ["no trace (run did not produce data / non-convergent)"]
    for k in ("t", "vout", "en", "vin"):
        if k not in tr or tr[k] is None:
            why.append(f"missing column {k}")
    if why:
        return why
    n = len(tr["t"])
    if n < 10:
        return [f"too few samples ({n})"]
    for k in ("t", "vout", "en", "vin", "eaout", "ivin"):
        if k in tr and tr[k] is not None:
            if len(tr[k]) != n:
                why.append(f"column {k} has {len(tr[k])} samples, t has {n}")
            elif not all(_finite(v) for v in tr[k]):
                why.append(f"column {k} has non-finite samples")
    if why:
        return why
    t = tr["t"]
    for i in range(1, n):
        if not t[i] > t[i - 1]:
            return [f"time not strictly increasing at sample {i}"]
    return why


def _cross_up(t, y, lvl, i0=0):
    """First upward crossing of lvl at or after sample i0 -> (time, index of
    the sample at/after the crossing) or None."""
    for i in range(max(i0, 1), len(t)):
        if y[i - 1] < lvl <= y[i]:
            f = (lvl - y[i - 1]) / (y[i] - y[i - 1])
            return t[i - 1] + f * (t[i] - t[i - 1]), i
    return None


def _cross_down(t, y, lvl, i0=0):
    for i in range(max(i0, 1), len(t)):
        if y[i - 1] >= lvl > y[i]:
            f = (y[i - 1] - lvl) / (y[i - 1] - y[i])
            return t[i - 1] + f * (t[i] - t[i - 1]), i
    return None


def en_edges(tr):
    """Ordered list of ('rise'|'fall', time) EN = VIN/2 crossings."""
    t, en, vin = tr["t"], tr["en"], tr["vin"]
    half = [e - v / 2.0 for e, v in zip(en, vin)]
    out, i = [], 1
    while i < len(t):
        if half[i - 1] < 0 <= half[i]:
            f = -half[i - 1] / (half[i] - half[i - 1])
            out.append(("rise", t[i - 1] + f * (t[i] - t[i - 1])))
        elif half[i - 1] >= 0 > half[i]:
            f = half[i - 1] / (half[i - 1] - half[i])
            out.append(("fall", t[i - 1] + f * (t[i] - t[i - 1])))
        i += 1
    return out


def _interp(t, y, tq):
    """Linear interpolation of y at tq (tq inside the trace)."""
    lo, hi = 0, len(t) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if t[mid] <= tq:
            lo = mid
        else:
            hi = mid
    if t[hi] == t[lo]:
        return y[lo]
    return y[lo] + (y[hi] - y[lo]) * (tq - t[lo]) / (t[hi] - t[lo])


def _window(tr, t0, t1):
    """Sample index range [a, b) with t0 <= t <= t1 (inclusive)."""
    t = tr["t"]
    a = next((i for i, x in enumerate(t) if x >= t0), len(t))
    b = next((i for i, x in enumerate(t) if x > t1), len(t))
    return a, b


def _excursion(v, upto):
    """Largest drop of v[i] below its running maximum over v[0..upto]."""
    rm, worst = -math.inf, 0.0
    for i in range(upto + 1):
        rm = max(rm, v[i])
        worst = max(worst, rm - v[i])
    return worst


def _count_reversals(v, upto, tol):
    """Number of distinct reversals: maximal runs where v sits more than tol
    below the running maximum."""
    rm, n, inside = -math.inf, 0, False
    for i in range(upto + 1):
        rm = max(rm, v[i])
        below = rm - v[i] > tol
        if below and not inside:
            n += 1
        inside = below
    return n


def evaluate_case(tr, cfg, t0, t_end, prefix):
    """Evaluate one enable case on [t0, t_end]. Returns (metrics, reasons,
    insufficient_reasons)."""
    t, vout = tr["t"], tr["vout"]
    m, fails, insuff = {}, [], []
    p = prefix
    a, b = _window(tr, t0, t_end)
    observed = t_end - t0
    m[p + "observed_s"] = observed
    if observed < cfg.min_observe_s * (1 - 1e-9):
        insuff.append(f"{p}observation {observed:.6g} s < {cfg.min_observe_s:g} s")
    if b - a < 3:
        insuff.append(f"{p}fewer than 3 samples in the window")
        return m, fails, insuff
    # Missing-sample check: the transient timestep cap must hold throughout
    # the window (a gap means the solver skipped or the trace is truncated).
    seg = t[max(a - 1, 0):b + 1 if b < len(t) else b]
    gaps = [seg[i + 1] - seg[i] for i in range(len(seg) - 1)]
    max_dt = max(gaps) if gaps else math.inf
    m[p + "max_dt_s"] = max_dt
    if max_dt > cfg.max_dt_s * cfg.dt_slack:
        insuff.append(f"{p}sample gap {max_dt:.6g} s exceeds the {cfg.max_dt_s:g} s cap")
    if t[b - 1] < t_end - cfg.max_dt_s * cfg.dt_slack:
        insuff.append(f"{p}trace ends {t_end - t[b - 1]:.6g} s before the window end")
    ts = [t[i] - t0 for i in range(a, b)]
    vs = [vout[i] for i in range(a, b)]
    # start the window at the interpolated EN crossing
    v0 = _interp(t, vout, t0)
    ts = [0.0] + ts
    vs = [v0] + vs
    m[p + "vout_at_enable_v"] = v0
    peak = max(vs)
    m[p + "peak_vout_v"] = peak
    m[p + "overshoot_v"] = peak - cfg.vnom
    m[p + "peak_time_s"] = ts[vs.index(peak)]
    final = vs[-1]
    m[p + "final_vout_v"] = final
    # first band entry vs settling
    first_in = next((i for i, v in enumerate(vs) if cfg.band_lo <= v <= cfg.band_hi), None)
    m[p + "first_band_entry_s"] = None if first_in is None else ts[first_in]
    last_out = None
    for i in range(len(vs) - 1, -1, -1):
        if not (cfg.band_lo <= vs[i] <= cfg.band_hi):
            last_out = i
            break
    settled = last_out is None or last_out < len(vs) - 1
    if last_out is None:
        t_settle, i_settle = ts[0], 0
    elif last_out == len(vs) - 1:
        settled = False
        t_settle, i_settle = None, None
    else:
        # re-entry crossing between last_out and last_out + 1
        lvl = cfg.band_lo if vs[last_out] < cfg.band_lo else cfg.band_hi
        y0, y1 = vs[last_out], vs[last_out + 1]
        f = (lvl - y0) / (y1 - y0)
        t_settle = ts[last_out] + f * (ts[last_out + 1] - ts[last_out])
        i_settle = last_out + 1
    m[p + "settled"] = settled
    m[p + "settle_time_s"] = t_settle
    if first_in is not None and settled and ts[first_in] < (t_settle or 0) - 1e-12:
        m[p + "early_entry_then_exit"] = True
    else:
        m[p + "early_entry_then_exit"] = False
    if not settled:
        fails.append(f"{p}not settled in band by end of window (final {final:.6f} V)")
    elif t_settle > cfg.settle_limit_s:
        fails.append(f"{p}settles at {t_settle * 1e3:.4f} ms > {cfg.settle_limit_s * 1e3:g} ms")
    if peak > cfg.band_hi:
        fails.append(f"{p}peak {peak:.6f} V above {cfg.band_hi} V")
    # rise times 10/90 % of vnom (first crossings)
    def first_cross(lvl):
        for i in range(1, len(vs)):
            if vs[i - 1] < lvl <= vs[i]:
                f = (lvl - vs[i - 1]) / (vs[i] - vs[i - 1])
                return ts[i - 1] + f * (ts[i] - ts[i - 1])
        return None
    t10, t90 = first_cross(0.1 * cfg.vnom), first_cross(0.9 * cfg.vnom)
    m[p + "t10_s"], m[p + "t90_s"] = t10, t90
    m[p + "rise_10_90_s"] = None if t10 is None or t90 is None else t90 - t10
    # monotonicity until settling (whole window if unsettled)
    upto = len(vs) - 1 if i_settle is None else i_settle
    exc = _excursion(vs, upto)
    m[p + "max_down_excursion_v"] = exc
    for tol in cfg.sensitivity_tols_v:
        m[p + f"reversals_gt_{tol * 1e3:g}mV"] = _count_reversals(vs, upto, tol)
    m[p + "monotonic"] = exc <= cfg.monotonic_tol_v
    if exc > cfg.monotonic_tol_v:
        fails.append(f"{p}downward excursion {exc * 1e3:.4f} mV > {cfg.monotonic_tol_v * 1e3:g} mV")
    # stress over the window
    if tr.get("eaout") is not None:
        vsg = [tr["vin"][i] - tr["eaout"][i] for i in range(a, b)]
        vgd = [tr["eaout"][i] - vout[i] for i in range(a, b)]
        m[p + "max_vsg_pass_v"] = max(vsg)
        m[p + "max_vgd_pass_v"] = max(vgd)
        m[p + "min_eaout_v"] = min(tr["eaout"][a:b])
    m[p + "max_vds_pass_v"] = max(tr["vin"][i] - vout[i] for i in range(a, b))
    if tr.get("ivin") is not None:
        m[p + "peak_supply_current_a"] = max(-x for x in tr["ivin"][a:b])
    return m, fails, insuff


def evaluate(tr, cfg=Config()):
    """Evaluate a startup trace. Always returns a dict with `verdict`."""
    out = {"verdict": "insufficient", "reasons": []}
    bad = validate_trace(tr, cfg)
    if bad:
        out["reasons"] = bad
        out["pass"] = False
        return out
    t, vout = tr["t"], tr["vout"]
    edges = en_edges(tr)
    out["en_edges"] = [(k, v) for k, v in edges]
    kinds = [k for k, _ in edges]
    want = ["rise", "fall", "rise"][:len(cfg.expect_cases) + (1 if len(cfg.expect_cases) > 1 else 0)]
    if kinds != want:
        out["reasons"] = [f"EN edges {kinds} != expected {want}"]
        out["pass"] = False
        return out
    fails, insuff = [], []
    vin_v = tr["vin"][0]
    out["vin_v"] = vin_v
    t_rise = edges[0][1]
    # off state: everything before the EN edge's start (t < t_rise)
    ia, ib = _window(tr, cfg.off_window_skip_s, t_rise)
    offv = vout[ia:ib]
    if not offv or t[0] > 0.5 * t_rise:
        insuff.append("no cold-start off-state window")
    else:
        out["off_vout_max_v"] = max(offv)
        out["off_vout_min_v"] = min(offv)
        out["off_vout_end_v"] = offv[-1]
        if tr.get("ivin") is not None:
            out["off_supply_current_a"] = -tr["ivin"][ib - 1]
        if max(abs(v) for v in offv) > cfg.off_vout_limit_v:
            fails.append(f"off-state |VOUT| {max(abs(v) for v in offv):.6g} V > {cfg.off_vout_limit_v:g} V")
    t_end = t[-1]
    end_start = edges[1][1] if len(edges) > 1 else t_end
    m, f, i = evaluate_case(tr, cfg, t_rise, end_start, "start_")
    out.update(m)
    fails += f
    insuff += i
    reen_fails, reen_insuff = [], []
    if len(edges) == 3:
        # disabled interval between the fall and the second rise
        ja, jb = _window(tr, edges[1][1], edges[2][1])
        out["reen_off_vout_start_v"] = _interp(t, vout, edges[1][1])
        out["reen_off_vout_end_v"] = vout[jb - 1] if jb > ja else None
        m2, f2, i2 = evaluate_case(tr, cfg, edges[2][1], t_end, "reen_")
        out.update(m2)
        reen_fails, reen_insuff = f2, i2
    out["start_pass"] = not f and not i and not [x for x in fails if x.startswith("off-state")]
    out["reen_pass"] = bool(len(edges) == 3 and not reen_fails and not reen_insuff)
    allf = fails + reen_fails
    alli = insuff + reen_insuff
    # stress against the DR-0002 reference (informational, not a verdict term)
    cols = ("max_vsg_pass_v", "max_vgd_pass_v")
    out["stress_gt_ref"] = any(
        out.get(pre + c, 0) > cfg.stress_ref_v for pre in ("start_", "reen_") for c in cols)
    if tr.get("vin") is not None:
        out["max_vsg_men_v"] = max(v - e for v, e in zip(tr["vin"], tr["en"]))
    out["reasons"] = alli + allf
    if alli:
        out["verdict"] = "insufficient"
    elif allf:
        out["verdict"] = "fail"
    else:
        out["verdict"] = "pass"
    # Headline pass is the cold-start + off-state contract; re-enable is
    # reported separately (reen_pass) but a full "pass" verdict needs both.
    out["pass"] = out["verdict"] == "pass"
    return out
