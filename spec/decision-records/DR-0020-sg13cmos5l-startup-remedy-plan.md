# DR-0020: SG13CMOS5L startup overshoot remedy — mechanism, candidate comparison and validation plan for row 9

> **Numbering note.** DR-0020 is the next free number. DR-0010, DR-0011 and
> DR-0013 stay skipped for the reason given in
> [`DR-0012`](DR-0012-row4-dropout-measurement.md): `spec/porting-plan.md`
> cites those numbers. DR-0019 (startup record log anchor, issue #238) is on
> `origin/main`. No open pull request or remote branch carried a DR-0020 when
> this record was written (checked against `origin` at `a8910ef5` on
> 2026-11-16, by `git ls-tree -r --name-only <ref> -- spec/decision-records/`
> over `origin/main` and every remote branch, and against
> `gh pr list --state open`).

- **Status**: **Proposed** (a builder-drafted record; operator approval of the
  pull request that carries it is the acceptance act). **No target-spec row is
  ratified, relaxed or changed by this record. `DR-0007` row 9 (startup)
  stays Open**, and row 7 (Iq) and row 10 (stability) keep their states. The
  candidate device values below are unvalidated candidates, not a design.
  This record changes no schematic, netlist, testbench, layout, measurement
  record, row state, target, threshold or verdict. **Zero simulations were
  run for this record**: every number is quoted from committed evidence or
  calculated from committed traces, and tagged by where it comes from (see
  "Evidence tags").
- **Date**: 2026-11-16
- **Scope**: the SG13CMOS5L branch only (`design/sg13cmos5l/`), plan-only
  (issue #221). It states the mechanism of the row-9 startup overshoot from
  committed evidence, compares four candidate remedies, recommends one with
  its bounded confirm/reject experiment, and lists the consumers a follow-up
  implementation would make stale. It is the row-9 counterpart of
  [`DR-0017`](DR-0017-sg13cmos5l-current-limiter-plan.md) (row 8's plan-only
  record) and follows its structure and tagging conventions. It does not
  implement anything, does not add a soft start to the netlist (that is the
  follow-up implementation's work, on its own record-approved basis), and
  does not touch the SG13G2 branch.
- **Related**: [`DR-0007`](DR-0007-target-spec-row-ratification.md) (row 9
  Open; row 7 and row 10 Open; the target table),
  [`DR-0009`](DR-0009-sg13cmos5l-startup-measurement-methodology.md) (the
  startup measurement methodology this record argues under; it "does not add
  a soft start, a discharge path or a current limit"),
  [`DR-0008`](DR-0008-sg13cmos5l-enable-interface.md) (the `EN` interface and
  its over-rating record),
  [`DR-0017`](DR-0017-sg13cmos5l-current-limiter-plan.md) (the row-8 limiter
  plan; its `|Vsg|` gate classification and its deferred integration),
  [`DR-0002`](DR-0002-sg13cmos5l-device-topology.md) (the `VGS <= 3.3 V`
  rating), [`DR-0015`](DR-0015-sg13cmos5l-dynamic-window-stability-diagnosis.md)
  (the E1 operating points),
  [`DR-0012`](DR-0012-row4-dropout-measurement.md) /
  [`DR-0014`](DR-0014-row10-stability-margin-classification.md) (the skipped
  numbering rule), `spec/porting-plan.md` §1.2, §2.3, §4 item 6.

## Evidence tags

Each quantity carries one tag:

- **[M]** measured: a committed record or a PDK file, cited by path. The
  measurement is quoted, not re-run.
- **[C]** calculated in this record from [M] values and/or [A] values. The
  arithmetic is shown so it can be checked.
- **[A]** assumption. It must be replaced by a measurement in the
  implementation work before any claim depends on it.
- **[U]** unmeasured or unknown, with no defensible value yet. It is listed
  under "Missing characterization".

## Context

### What this branch has today [M]

`design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` at `origin/main` `a8910ef5`:

```
.subckt ldo_core_cmos5l VIN VOUT VSS VREF IBIAS EN
XMpass VOUT EAOUT VIN VIN sg13_hv_pmos w=2800u l=0.5u ng=1 m=1
XRtop VOUT FB VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7
XRbot FB VSS VSS rhigh w=1e-6 l=25.43e-6 m=1 b=7
Xamp FB VREF EAOUT VIN VSS IBIAS EN ldo_erramp_cmos5l
XMen EAOUT EN VIN VIN sg13_hv_pmos w=40u l=0.5u ng=1 m=1
XMbdis IBIAS EN VIN VIN sg13_hv_pmos w=5u l=0.5u ng=1 m=1
```

There is no soft start, no discharge device and no current limiter (the
limiter exists only as `DR-0017`'s plan and the deferred `ldo_ilimit_cmos5l`
work). `EAOUT` is the integration node: `Mpass`'s gate, the amplifier's
second-stage output, and `XMen`'s drain. With `EN` low, `XMen` holds `EAOUT`
at `VIN` (pass device off, `Vsg` 8-14 mV) and `XMbdis` parks the bias
(`DR-0008`). The startup bench
(`sim/ldo-cmos5l-pvt-sweep/testbench/tb_startup_cmos5l.spice.tmpl`) applies
one enable profile per run [M]: `EN = VIN x CTL`, with CTL a PWL that
enables at 1 ms (1 us edge), disables at 7 ms, re-enables at 9 ms; time zero
of each case is the `EN = VIN/2` crossing (`DR-0009` decision 2). The
startup methodology is `DR-0009` (proposed): row 9 reads as (a) VOUT inside
1.764-1.836 V within 3 ms of enable and staying there, and (b) a monotonic
rise (no downward excursion from the running maximum above 1 mV, recovery
from overshoot counting as a reversal).

### Measured anchors this plan argues from

Startup grid — `sim/ldo-cmos5l-pvt-sweep/records/20261010-104827-91e92aa-startup-grid.{csv,md}`
(135 points: 5 MOS corners x 3 resistor corners x 3 temperatures x 3 supplies,
at 1 mA / 1000 nF / 0 mohm; verdicts pass 0 / fail 135):

| Quantity | Value | Tag |
|---|---|---|
| Start overshoot above 1.8 V | 0.0677 … 0.5386 V | [M] grid `.md` extrema |
| Start peak VOUT | 1.8678 … 2.3386 V | [M] grid `.md` |
| Start peak time (after the `EN` crossing) | 4.58 … 8.95 us | [M] grid `.csv` `start_peak_time_s` |
| Start 10-90 % rise | 1.93 … 5.43 us | [M] grid `.md` |
| Start settle time (last in-band re-entry) | 36.9 … 439.8 us | [M] grid `.md` |
| Start max downward excursion | 0.0326 … 0.5032 V | [M] grid `.md` |
| Re-enable overshoot | 0.0842 … 0.4920 V | [M] grid `.md` |
| Re-enable max downward excursion | 0.0489 … 0.4569 V | [M] grid `.md` |
| Failure reasons | `start_peak overshoot`, `start_downward excursion`, `reen_peak overshoot`, `reen_downward excursion`, each at **135 of 135** points | [M] grid `.md` "Failure reasons" |
| Start peak supply current | 0.2835 … 0.7746 A | [M] grid `.md` |
| Start max `Vsg(Mpass)` | 2.9620 … 3.6271 V | [M] grid `.md` |
| Start max `Vds(Mpass)` | 2.9695 … 3.63 V | [M] grid `.md` |

The grid's `load_ma`, `cout_nf` and `esr_mohm` columns each hold exactly one
distinct value (1 mA, 1000 nF, 0 mohm) [M, column-distinct check over the
`.csv`], so the grid varies only MOS corner, resistor corner, temperature
and supply. **`DR-0009`'s "settling in 37-440 us" is therefore a
single-output-network figure, not a bound on any other Cout/ESR.** [C]

Startup ext — `…/20261010-104827-91e92aa-startup-ext.{csv,md}` (24 points:
0 and 50 mA x 330 and 4700 nF x 0 and 500 mohm at `v3630mv`, plus corner
coverage; verdicts pass 4 / fail 20 / insufficient 0):

| Quantity | Value | Tag |
|---|---|---|
| Start overshoot | 0.0212 … 0.9421 V | [M] ext `.md` |
| Overshoot by output network | 330 nF/0 mohm 0.499 … 0.942 V; 330 nF/500 mohm 0.414 … 0.809 V; 4700 nF/0 mohm 0.057 … 0.129 V; 4700 nF/500 mohm 0.021 … 0.044 V | [M] ext `.csv`, grouped `start_overshoot_v` |
| Points already passing row 9 with no circuit change | 4 of 24, all `c4700nf_e500mohm`: `st_ff_27c_rtyp_v3630mv_i{0,50}ma` and `st_ss_-40c_rtyp_v3630mv_i{0,50}ma`; peaks 1.8212-1.8334 V, `start_monotonic=True`, `start_settled=True`, verdict `pass` | [M] ext `.csv`; count corroborated by ext `.md` "pass 4, fail 20" |
| **Hot/`rwcs` miss at that same network** | both `st_ff_125c_rwcs_v3630mv_i{0,50}ma_c4700nf_e500mohm` points **fail**: `start_peak` 1.8440 / 1.8420 V above the 1.836 V edge, `start_downward excursion` 6.83 / 6.47 mV > 1 mV, `reen_peak` 1.8360 / 1.8409 V, and the 0 mA point additionally logs `off-state |VOUT| 0.185718 V > 0.05 V` and `start_not settled in band by end of window (final 1.837210 V)` | [M] ext `.csv` `reasons` column |
| Start settle time, the eight 4700 nF points | 11.08, 11.82, 14.34, 15.49, 20.96, 21.04, 24.84, 25.26 us (i.e. **11.1 … 25.3 us**); the four passing `c4700nf_e500mohm` points are 11.1 … 15.5 us | [M] ext `.csv` `start_settle_time_s` |
| Start settle time, the one over-budget point | `st_ss_-40c_rtyp_v3630mv_i50ma_c330nf_e0mohm_t1000ns` settles at **5.999 ms** — over the 3 ms budget, at the *small*-Cout end | [M] ext `.csv` |
| Points never settling in the window | `start_settled=False` at **15 of 24**; `start_monotonic=True` at 4 of 24 | [M] ext `.csv` |
| Start peak supply current | 0.5172 … 0.6911 A | [M] ext `.md` |
| Start max `Vsg(Mpass)` | 3.6224 … 3.6276 V | [M] ext `.md` |

The 135-point grid contains **no 4700 nF point at all** [M, `cout_nf`
column-distinct check], so the large-Cout behaviour has no committed
full-PVT evidence.

Nominal single point — `…/20261010-104827-91e92aa-startup-nominal.{csv,md}`
(tt, 27 C, 3.30 V, 1 mA, 1000 nF): peak 2.0558 V, overshoot 0.2558 V,
settle 209.0 us, re-enable overshoot 0.1977 V, peak supply current
0.4846 A, verdict fail [M].

Step convergence — `…/20261010-104827-91e92aa-startup-halfstep.{csv,md}`:
halving the max timestep to 0.5 us moves the overshoot by up to 0.15 V at
the binding points without changing any verdict [M]; also stated in
`DR-0009` §"What the first evidence shows".

Amplifier in regulation — `sim/ldo-cmos5l-pvt-sweep/records/20261012-115531-cfa681f9.e1op.{csv,md,manifest.tsv}`
(`DR-0015` experiment E1, VIN = 3.3 V, 1 uF, ESR 0): the regulated `EAOUT`
sits at 2.67-3.03 V across the four points P1/P2/P5/P6 (P6 is the 1 mA
point), i.e. `Vsg(Mpass)` = `VIN - EAOUT` = **0.27 … 0.63 V** in regulation
[M, from the CSV `op:v(eaout)` column against `op:v(en)` = `VIN`]. The
minimum measured divider current is 1.974 uA (P2, ff/wcs/-40 C) [M, same
CSV `op:i(vdivsense)`]. Worst no-load Iq on this branch is 24.72 uA over
the 45-point DC grid [M, `sim/ldo-cmos5l-pvt-sweep/records/20261011-070111-5391c68.csv`
`iq_a`, quoted in `DR-0017`].

Rating frame — HV PMOS `VGS <= 3.3 V @ 27 C, LG >= 0.5 um` (process spec
§2.1.5, quoted in `DR-0002`) [M]. `DR-0017` §"Terminal stress" classifies a
transient exceedance of the steady-state `|Vsg(Mpass)| <= 3.3 V` gate as a
**FAIL against the published maximum**, reported with its duration, until a
transient rating or a separate record rules on it [C, classification
carried from `DR-0017`]. `DR-0008` already records the same kind of
over-rating for `XMen`/`XMbdis` (`Vsg = VIN - EN = 3.63 V` at `EN = 0`,
`VIN = 3.63 V`) and does not fix it [M]. The measured startup
`Vsg(Mpass)` of 3.62-3.63 V on every startup axis (grid max 3.6271 V, ext
max 3.6276 V) is inside that already-recorded exceedance territory: this
record cites it as a second effect every candidate has, and does not
re-litigate the rating.

### The failure mechanism, from the committed traces

The grid and ext reduced traces
(`…/20261010-104827-91e92aa-startup-{grid,ext}.traces/*.csv.gz`, columns
`t,vout,en,vin,eaout,ivin` [M]) carry the amplifier output and the supply
current per point. The reduction below was computed over **all 135 grid
traces** with this method [C, so it can be re-run against the committed
files]: parse each gzipped trace; time zero is the first `en > vin/2`
sample; the start window runs to the next `en < vin/2` sample (the 7 ms
disable, per the bench profile); report the minimum `eaout` in the window,
the first later sample with `eaout > 0.5 V` ("rail exit"), and the window's
`vout` maximum with its time.

1. **The amplifier rails low at every point.** After the enable crossing,
   `EAOUT` collapses from `VIN` to **0.0029 … 0.0086 V** at **135 of 135**
   grid points [C]. The collapse is the loop's correct response to
   `FB = 0 < VREF = 0.9 V`: maximum commanded gate drive. While `EAOUT`
   sits at the rail, `Vsg(Mpass) = VIN - EAOUT = 3.622 … 3.627 V` at the
   3.63 V supply points — the measured transient exceedance of the 3.3 V
   rating [M, grid/ext `.md` max `Vsg`; the rail collapse is its direct
   cause [C]].
2. **The inrush is the fully-on pass device.** Peak supply current
   0.2835-0.7746 A (grid) / 0.5172-0.6911 A (ext) [M] flows while `EAOUT`
   is railed [C]. Against the E1 regulation locus (`Vsg` 0.27-0.63 V [M]),
   the startup excursion is a full rail-to-rail swing of the amplifier
   output.
3. **The rise outruns the loop.** VOUT crosses the band 3.6-4.4 us after
   the enable crossing and peaks at 4.58-8.95 us (grid `.csv`, normative;
   the decimated traces give 4.50-8.86 us [C, consistent]) at
   1.868-2.339 V [M]. `EAOUT` leaves the rail at 3.05-7.83 us [C] — up to
   ~1.5 us *before* the peak at some points, but always while VOUT is
   still far above the band edge: the amplifier then has to slew the full
   ~3.6 V rail-to-rail span through the pass device's 6.3-6.9 pF gate
   [`DR-0017`-derived gate cap, [C]] while the output keeps rising. The
   overshoot is the integral of the uncontrolled excess current during
   this slew [C]. The 10-90 % rise of 1.93-5.43 us [M] against the ~5-9 us
   peak time leaves the loop no linear-range time in which to catch the
   output.
4. **The recovery is an uncontrolled decay.** After the peak, `FB >
   VREF` and the loop drives `EAOUT` to the *positive* rail: in the
   worst-overshoot point (`st_ff_27c_rtyp_v3630mv_i1ma_c1000nf_e0mohm_t1000ns`)
   the trace shows `EAOUT` pinned at `VIN + ~3 mV` — Mpass fully **off** —
   while VOUT decays from 2.32 V back to 1.80 V over ~470 us on the load's
   own RC [M, trace]. The decay time agrees with the passive estimate:
   `R_load x Cout = (1.8 V / 1 mA) x 1 uF = 1.8 ms`, and
   `t = tau x ln(V_peak/1.836 V) = 1.8 ms x ln(2.3386/1.836) = 436 us`
   against the measured 439.8 us settle of exactly that point [C, 0.9 %
   off]. The grid's whole 36.9-439.8 us settle range is this decay wait:
   `1.8 ms x ln(V_peak/1.836)` spans 31-436 us over the grid's
   1.868-2.339 V peaks [C]. The measured max downward excursion of
   0.0326-0.5032 V [M] is that decay from the running maximum back to —
   and through — the band: the monotonicity failure.
5. **Re-enable repeats the sequence.** The bench disables at 7 ms and
   re-enables at 9 ms [M, template]; all four failure reasons are logged
   at 135 of 135 grid points with re-enable overshoot 0.084-0.492 V and
   re-enable downward excursion 0.049-0.457 V [M]; on the ext axis the
   re-enable failures are co-located with the start failures (the two
   hot/`rwcs` `c4700nf_e500mohm` points fail both windows [M, `reasons`
   column]). A remedy that arms only at power-on would leave half the
   measured failure untouched.

**Mechanism statement.** Row 9's two failure modes are both symptoms of
one thing: with a full-step reference and a discharged output, the loop
spends the whole transient saturated at one rail or the other, and VOUT is
controlled only in between — too late for the peak, and only after a
passive decay through the band [C, from (1)-(5)]. Overshoot (peak above
1.836 V) and non-monotonicity (the decay reversal) fail together at 135 of
135 grid points [M]; the four ext points that pass are exactly those where
the output network keeps the peak inside the band, so no rail-to-rail
recovery is ever triggered [C, reading of the ladder]. Any remedy must
therefore either bound the loop's commanded excursion (keep the amplifier
in its linear range) or absorb the consequences (network/limiter), and
must do so on every enable edge, not only the first.

## Decision (proposed)

### The candidate set

Four candidates are compared. AC-mandated dimensions for each: effect on
row 7 (Iq), row 9 and row 10 and on the `DR-0008` enable interface; the
settling-time cost at the Cout/ESR the candidate assumes; whether it fixes
the re-enable case; and its effect on the transient `Vsg(Mpass)`
exceedance.

**Settling-time figures used below** (the corrected reading, per the
ext record): 11.1-25.3 us at 4700 nF (11.1-15.5 us at the four passing
`c4700nf_e500mohm` points — about 2.985 ms of the 3 ms budget unused);
the single 330 nF / ESR 0 point at **5.999 ms** is the one measured
over-budget case and sits at the *small*-Cout end; 15 of 24 ext points
never settle in the window. `DR-0009`'s 37-440 us is grid-only
(1 mA / 1000 nF / 0 mohm) and is not a bound on any other output network.
On the grid the settle time is the rail-to-rail recovery decay
(mechanism item 4 [C]); a remedy that removes the rail excursion removes
that decay term, which is why the settling column below is about the
candidate's *added* time, not today's decay.

#### Candidate 1 — output-network specification (minimum Cout / minimum ESR as a row-9 operating condition)

The remedy is a specification, not a circuit: state a minimum output
capacitance and ESR in row 9's eventual operating conditions.

- **Mechanism fit.** The evidence ladder shows overshoot falling by more
  than an order of magnitude with Cout and ESR (0.414-0.942 V at
  330 nF -> 0.057-0.129 V at 4700 nF/0 mohm -> 0.021-0.044 V at
  4700 nF/500 mohm [M]), and 4 of 24 ext points already pass with no
  circuit change [M]. A larger Cout slows the rise into the loop's slew
  budget; ESR damps. The mechanism (rail excursion) is *not* removed —
  the network only keeps the peak near the band so the recovery is small
  [C, reading of the ladder].
- **Not shown sufficient over PVT.** At exactly its best network
  (4700 nF / 500 mohm) 2 of 6 ext points still fail — both
  `ff`/125 C/`rwcs`, peaks 1.8440 / 1.8420 V against the 1.836 V edge with
  6.83 / 6.47 mV downward excursions, plus the 0 mA point's off-state
  `|VOUT| 0.185718 V > 0.05 V` and no in-band settle [M]. The 135-point
  grid has no 4700 nF point, so there is no committed full-grid evidence
  for any large-Cout network [M]. The candidate must be compared with
  this miss stated, not presented as solved.
- **Row 7 (Iq).** No circuit change; Iq unchanged [C]. The off-state
  bound of `DR-0009` decision 5 (max `|VOUT| <= 50 mV`) is independent of
  Cout/ESR, and the hot/`rwcs` off-state miss above happens *with* the
  large network — it is a corner behaviour of today's disabled core at no
  load, not something this candidate fixes [C].
- **Row 9.** Turns 20 of 24 ext failures into (at best) 2, on committed
  evidence; the residual hot/`rwcs` failures are 6-8 mV overshoots with
  6.5-6.8 mV downward excursions — the mechanism is still active, just
  attenuated [M/C].
- **Row 10.** ESR adds an output zero and larger Cout moves the output
  pole; the stability margins move by an unmeasured amount [U]. Note the
  coupling: the row-10 target text in `DR-0007` spans `C_out 0.33-4.7 uF
  effective, ESR 0-500 mohm` [M, root `README.md` target table]; a row-9
  *minimum* network would contradict that envelope at its small-Cout end
  unless the row-10 wording is revised in the same future spec change.
  Both rows are Open; reconciling them is ratification work, out of scope
  here.
- **`DR-0008` enable interface.** No change [C].
- **Settling cost at the assumed network.** Measured: 11.1-25.3 us at
  4700 nF; 11.1-15.5 us at the four passing points; the 5.999 ms
  over-budget point is at 330 nF/ESR 0 — a network this candidate would
  forbid, which is consistent with the remedy but also means the remedy's
  own settling evidence is the benign end of its own range [M]. At any
  network the candidate permits, the decay-dominated settling of today
  remains whenever the peak exceeds the band (hot/`rwcs` [M]).
- **Re-enable.** Improves exactly where cold start improves; the two
  hot/`rwcs` points fail both windows [M]. Not a per-edge mechanism — it
  passes or fails with the network, identically for both windows [C].
- **Transient `Vsg(Mpass)`.** **No effect.** The amplifier still rails
  low at every enable and `Vsg` still reaches `VIN - EAOUT_min` = 3.62-3.63
  V [C, from mechanism item 1; the ext `Vsg` maxima 3.6224-3.6276 V were
  measured *at* the networks where this candidate passes [M]]. The rating
  exceedance remains at every point, every window.

#### Candidate 2 — internal reference ramp (soft start on the internal command)

Shape the command, not the supply: feed the amplifier's reference input
from an internal node `VREFR` that rises from ~0 to the external `VREF`
along a controlled ramp after **every** `EN` rising edge, instead of
stepping. The loop then regulates `VOUT` onto a rising target
(`VOUT = VREFR / 0.5` through the 0.5 : 1 divider [C, divider ratio from
the equal `Rtop`/`Rbot` legs [M]]) instead of onto a step.

- **Mechanism fit.** The commanded error is bounded by the ramp increment,
  so the amplifier stays near its regulation locus instead of railing:
  `EAOUT` tracks 2.67-3.03 V [M, E1] instead of swinging ~3.6 V
  rail-to-rail [M/C]. Both failure modes are addressed at the cause: the
  overshoot (no rail-low inrush phase) and the decay reversal (no
  rail-high held-off phase — the loop never commands Mpass hard off while
  VOUT is in or near the band) [A, confirmed or rejected by the bounded
  experiment].
- **Row 9.** Expected: monotonic by construction (tracking a rising
  bounded ramp), peak inside the band, no downward excursion [A]. The
  inrush is bounded by the ramp rate instead of the pass device's fully-on
  current: `I_pk ~ Cout x dVOUT/dt + I_load = Cout x 2 x VREF / T_ramp +
  I_load`; at `T_ramp = 450 us`: ~4 mA into 1 uF, ~18.8 mA into 4.7 uF
  [C] against today's 0.28-0.77 A [M].
- **Row 7 (Iq).** The ramp branch is a mirror of the external `IBIAS`
  charging `C_ss` — nA-class by design (candidate values below). Added
  static Iq is budgeted **< 1 uA** [A] (one mirror branch plus leakage),
  against the row-7 target `< 30 uA` with 24.72 uA measured worst no-load
  Iq today [M] — about 5 uA of headroom [C]. Row 7 stays Open; the
  implementation must re-measure Iq over the grid, including the ramp
  branch's disabled state (the reset device must add only leakage when
  `EN` is low [A]).
- **Row 10.** At regulation the ramp is done and `VREFR = VREF`, so the
  small-signal loop the rows 6/10 benches see is unchanged **if** the
  ramp branch presents only a negligible impedance at `VREFR` [A]. The
  large-signal reference step the loop was tuned against is gone, which
  changes phase-margin-relevant behaviour only if the clamp/ramp devices
  load the reference node [A/U]. Rows 6 and 10 must be re-run on the new
  netlist; no margin claim is made here.
- **`DR-0008` enable interface.** `EN` semantics unchanged: rail-to-rail
  `VIN`-domain, `XMen`/`XMbdis` untouched, `VREF` pin untouched — the
  ramp is entirely internal to the core. But `DR-0008` records "No output
  discharge, no soft start" as today's state [M], so adding one **needs a
  `DR-0008` addendum** stating the new internal reference node, the
  per-enable re-arm, and the unchanged port list (the six-port invariant
  holds). Stated here, not hidden; the addendum is follow-up work.
- **Settling cost at the Cout/ESR it assumes.** The added time is
  `T_ramp` itself plus the loop's in-band catch. With the candidate
  `T_ramp = 180-450 us` [A] and today's in-band settle behaviour
  (11.1-25.3 us at 4700 nF [M]; 36.9-439.8 us on the grid — but that
  range *is* the decay this candidate removes [C]), the estimate is
  `T_ramp + <~450 us <= ~0.9 ms` at the worst measured corner — inside
  the 3 ms budget with the 0.5 us-step convergence caveat carried from
  `DR-0009` (overshoot figures move up to 0.15 V with timestep; settle
  verdicts did not [M]) [C/A]. At 330 nF — today's 5.999 ms over-budget
  point — the candidate removes the decay phase that produces that
  5.999 ms, so the estimate is `T_ramp + small`, i.e. it fixes the one
  measured over-budget case rather than forbidding its network [C/A].
  These are estimates; the bounded experiment measures.
- **Re-enable.** Armed on **every** `EN` rising edge by construction (the
  reset device discharges `C_ss` when `EN` is low). A re-enable onto a
  still-charged output (the bench gives 2 ms of disabled time; the output
  decays only through the divider and load per `DR-0008` [M]) holds the
  pass device off while `VOUT/2 > VREFR(t)`, then tracks up the rest of
  the ramp [A] — controlled, with no rail excursion, which is exactly the
  half of the measured failure that a power-on-only remedy would miss [C,
  from mechanism item 5]. Behaviour at partial discharge is [U] (missing
  characterization).
- **Transient `Vsg(Mpass)`.** This is the candidate's distinguishing
  effect: with the loop kept out of saturation, `EAOUT` is expected to
  stay near its regulation locus (`Vsg ~ 0.3-0.6 V` [M, E1]) for the
  whole transient, so the 3.62-3.63 V exceedance closes rather than being
  absorbed [A — the single most important thing the bounded experiment
  must confirm; no rating claim is made, and `DR-0001`'s carried gate
  stays open until it is measured].
- **New devices** (candidate values, all [A] unvalidated): a ramp current
  `I_ramp` mirrored from the external `IBIAS` (the repo convention keeps
  the external reference ideal at block level, so the slope derives from
  the block's own bias), a ramp capacitor `C_ss` (`cap_cmomi`), a reset
  device driven by the local `EN` (the `DR-0008` addendum pattern), and
  optional clamp devices bounding `VREFR <= VREF`. The amplifier's
  reference pin moves from `VREF` to `VREFR` inside the core; the
  `ldo_erramp_cmos5l` cell and the port list are unchanged. Candidate
  arithmetic [C]: `T_ramp = C_ss x VREF / I_ramp` — 10 pF / 20 nA gives
  450 us; 10 pF / 50 nA gives 180 us; 22 pF / 50 nA gives 396 us. The
  constraint is `T_ramp <= ~500 us` so the total stays inside 3 ms at the
  slowest measured corner [C]. `I_ramp` must dominate `C_ss` leakage at
  125 C for the slope to hold [U].
- **Risks.** nA-class currents are leak-prone at 125 C junction
  temperature [U]; the ramp's interaction with the 1 us `EN` edge (the
  reset device must fully discharge `C_ss` in the 2 ms disabled window —
  easy — and must not trickle-charge it while `EN` is low [A]); the
  loop's re-catch at ramp end [U]; mismatch of the mirror that sets
  `I_ramp` [U]. All belong to the bounded experiment and the follow-up
  grid.

#### Candidate 3 — pass-gate slew limit (bound `dEAOUT/dt`)

Limit how fast `EAOUT` can fall (series resistance, a controlled sink, or
a larger effective integration capacitance during startup), so the pass
gate cannot collapse at the amplifier's native rate.

- **Mechanism fit.** Bounds the inrush *rate* [A], but the commanded
  endpoint while `FB < VREF` is still the negative rail: the loop still
  saturates, only later [C]. The same limit slows the turn-off slew
  (recovery) and the loop's normal large-signal response, because `EAOUT`
  is the dominant-pole node — the remedy taxes exactly the path rows 6
  and 10 are graded on [A/U].
- **Row 7.** Zero if passive [A]; uA-class if active [A].
- **Row 9.** Overshoot reduced but not removed; the decay reversal
  mechanism is untouched (the loop still ends up railed high after the
  peak) [A]. Monotonicity is not addressed by construction.
- **Row 10.** Highest risk of the four: a slew limit on the integration
  node degrades both large-signal settling and possibly small-signal
  phase margin [A/U]; unmeasured.
- **`DR-0008`.** No interface change [C].
- **Settling cost.** Not defensible from committed evidence: the slower
  gate lengthens both the rise and the recovery [U]. No figure claimed.
- **Re-enable.** Circuit property — armed always, both windows [C]. This
  is the candidate's one clean advantage over a power-on-armed variant of
  Candidate 2 (which this record does not propose).
- **Transient `Vsg(Mpass)`.** Shortens the exceedance's duration; does
  not bound its peak (a slew limit delays the rail, it does not prevent
  reaching it while `FB < VREF`) [C]. Not a rating remedy.

#### Candidate 4 — rely on the `DR-0017` current limiter

`DR-0017`'s limiter caps `I_out` at its candidate `I_lim` (72.32 mA
nominal, **unvalidated** [A]); the output then charges at
`I_lim - I_load` instead of at the fully-on pass current.

- **Mechanism fit.** Bounds the inrush amplitude — `DR-0017` itself
  predicts the change: "today's 0.283-0.775 A [M] would become ~=
  `I_lim`. The 1 uF charge at roughly `I_lim - I_load` then takes tens of
  us [C] instead of today's 2-5 us rise [M], which changes row-9
  behaviour" [M, quoted from `DR-0017` §5]. But the *voltage* loop is
  still saturated rail-to-rail during the charge (`FB < VREF` the whole
  time), and at handoff (`FB` crossing `VREF`) the loop takes over from a
  railed state through a plateau-to-regulation transition whose overshoot
  is unmeasured [A/U].
- **Row 7.** The limiter's comparator tail adds ~1 uA typical, ~3-4 uA
  worst [C/A, `DR-0017` §5]; worst-case total ~28-29 uA against `< 30 uA`
  — a thin margin `DR-0017` already flags [M/C].
- **Row 9.** Peak amplitude bounded; monotonicity and handoff overshoot
  unproven [A/U]. `DR-0017` explicitly makes row-9 re-verification a
  consumer of the limiter (its startup campaign must be re-run) [M].
- **Row 10.** Main loop unchanged while the limiter idles (`DR-0017`'s
  <= 0.9 % `EAOUT` cap argument [C/A]); the limiter loop needs its own
  stability bench [A, `DR-0017` §5].
- **`DR-0008`.** The limiter adds no new enable semantics (`DR-0017` §6)
  [M/C].
- **Settling cost at the assumed network.** Charge time
  `Cout x 1.8 V / (I_lim - I_load)`: ~26 us at 1 uF, ~121 us at 4.7 uF
  (at the 72.32 mA candidate and 1 mA load) [C], plus the unmeasured
  handoff [U]. Fits the 3 ms window on the charge term alone.
- **Re-enable.** Circuit property — the limiter arms whenever the core is
  enabled [C]. Both windows covered, if the limiter works.
- **Transient `Vsg(Mpass)`.** During the limiter's clamp delay
  (0.2-1.8 us estimate [C/A, `DR-0017` §5]) `EAOUT` still collapses, so
  the exceedance persists, shortened [U]. Not a rating remedy.
- **Contingency (stated, as required).** The limiter is **not in the
  core**. Its implementation (#164), row-8 benches (#166) and
  layout/LVS (#168) are all parked, and #190 — the authorization to
  integrate it into the core, which is also what would refresh the
  startup evidence — is an open **operator decision**. Recommending this
  candidate for row 9 would chain row 9's remedy to that entire queue and
  to a row-8-sized design change, for a remedy that (i) leaves the
  voltage-loop saturation and handoff unaddressed [A/U], (ii) does not
  close the `Vsg` exceedance [U], and (iii) thins an already thin row-7
  margin [C]. It remains row 8's remedy; row 9 borrows nothing from it
  in this record. **This record takes no action on #190/#164/#166/#168.**

### Recommendation

**Candidate 2, the internal reference ramp, is the recommended remedy**,
with candidate device values marked unvalidated above and the bounded
experiment below as its confirm/reject gate. The grounds, argued from the
mechanism:

1. **It is the only candidate that changes what the mechanism indicts.**
   The measured failure is a rail-to-rail saturation of the loop driven
   by a full-step command (mechanism items 1-5). Candidates 1 and 4 leave
   the step and the saturation in place and manage the consequences
   (absorb the peak; bound the current); Candidate 3 slows one edge.
   Only Candidate 2 replaces the step with a bounded excitation, so both
   failure modes — and the recovery decay — are addressed at the cause
   rather than by margin [C/A].
2. **It is the only candidate expected to pass by construction, in both
   windows.** Tracking a rising bounded ramp is monotonic and in-band if
   the ramp is slow relative to the loop (the bounded experiment measures
   the actual margin [A]); the per-enable re-arm covers the re-enable
   half of the measured failure, which the fifth grid finding makes
   mandatory (all four failure reasons at 135 of 135 points in both
   windows [M]). Candidate 1 is measured *insufficient* at hot/`rwcs` on
   its best network [M]; Candidate 4's handoff is unmeasured [U].
3. **It is the only candidate that plausibly closes the transient
   `Vsg(Mpass)` exceedance** — a measured FAIL against a published
   maximum (3.62-3.63 V on every startup axis [M]) that Candidate 1
   leaves untouched and Candidates 3 and 4 only shorten [C]. Closing it
   would also discharge part of the `DR-0001` carried-gate exposure;
   until measured, no claim is made [A].
4. **Its costs land inside the budgets that exist.** Settling: the added
   time is `T_ramp` (candidate <= ~500 us) against a 3 ms window — at
   every network the record must serve, including 330 nF/ESR 0 where
   today's 5.999 ms settle is itself the decay this candidate removes
   [C/A]. Iq: a sub-uA-class branch [A] against ~5 uA of measured
   headroom under the row-7 target [M/C] — budget pressure stated, row 7
   stays Open. Rows 6/10: no small-signal change expected at regulation
   [A], re-run mandatory. `DR-0008`: an internal node, an unchanged port
   list, and an addendum to a record that is itself Proposed [M/C].

**Compared and not recommended here:** Candidate 1 is real and evidenced,
but it is a customer-visible operating-conditions constraint that does
not close the mechanism, is already measured insufficient at
hot/`rwcs`, does nothing for the `Vsg` exceedance, and collides with the
row-10 envelope wording at its small-Cout end. This record still proposes
its substance as a **companion operating-conditions note**: the eventual
row-9 ratification packet should carry a recommended minimum output
network (order 4.7 uF / 500 mohm) as an operating requirement alongside
whatever circuit remedy lands. `DR-0007` is not edited by this record,
and proposing that note ratifies nothing. Candidate 4's contingency is
stated above; Candidate 3 is held as the fallback if the ramp's added
devices fail their review, at which point a successor record re-ranks
Candidates 3 and 4 with measured limiter/ramp evidence.

### Candidate structure and values (unvalidated)

Reference the existing convention: external `VREF` and `IBIAS` are ideal
at block level; the ramp derives its slope from the block's own bias
mirror, not from a new pin. Proposed cell (name and placement are the
implementation's to finalize):

```
(sub-circuit inside ldo_core_cmos5l, no port change)
VREFR: internal reference node fed to Xamp in place of VREF
Iss:   IBIAS-mirrored ramp current, candidate 10-50 nA [A]
Css:   cap_cmomi on VREFR, candidate 10-22 pF [A]
       (Iss and Css are a paired choice, not independent ranges: pick a
        pairing with T_ramp = Css*VREF/Iss <= ~500 us; candidate pairings
        10 pF/20 nA = 450 us, 10 pF/50 nA = 180 us, 22 pF/50 nA = 396 us)
Xrst:  reset device (EN-driven), discharges Css when EN is low [A]
Xclmp: optional clamp bounding VREFR <= VREF once the ramp completes [A]
Xamp:  reference pin moves VREF -> VREFR (cell unchanged, six-port invariant holds)
```

Device count ~3-4 MOS + 1 `cap_cmomi`. All values are candidates [A]; the
`T_ramp <= ~500 us` constraint and the leakage question at 125 C [U] are
the binding ones. The mirror ratio that sets `Iss` corners with the MOS
grid [U — the bounded experiment must measure `T_ramp` at its corners,
not assume nominal].

## Validation specification (requirements for the later work, not results)

### The bounded experiment (confirm/reject gate)

One implementation-independent experiment decides the recommendation.
Wrap the core plus the ramp cell in a testbench-local subckt (the #165
smoke pattern: `design/` stays untouched until the experiment passes), and
run the **existing** startup bench and evaluator unchanged — `DR-0009`'s
methodology, `startup_eval.py` verdicts, the 1 ms / 7 ms / 9 ms enable
profile, max step 1 us with the binding points at 0.5 us. Points
(~8, one `klt sim` batch request, batch fleet, not local):

1. Nominal: tt / 27 C / 3.30 V / 1 mA / 1000 nF / 0 mohm (the nominal
   record's conditions — direct comparison against its committed
   2.0558 V peak / 209 us settle [M]).
2. Worst grid overshoot: ff / 27 C / `rtyp` / 3.63 V / 1 mA / 1000 nF /
   0 mohm (committed peak 2.3386 V [M]).
3. Slow corner: ss / -40 C / `rtyp` / 3.63 V / 1 mA / 1000 nF / 0 mohm
   (committed `Vsg` max 3.6271 V [M]).
4. The four ext networks at tt / 27 C / 3.63 V, 0 and 50 mA:
   330 nF / 0 mohm (today's 5.999 ms settle point's network [M]) and
   4700 nF / 500 mohm.

**Confirm** means, at every point, measured on the new traces with the
unchanged evaluator: (a) verdict `pass` in both windows — monotonic at
the 1 mV tolerance, peak <= 1.836 V, settled in band within 3 ms; (b)
`start_peak_supply_current_a` <= the ramp-scaled bound
`Cout x 2 x VREF / T_ramp + I_load` plus a stated measurement margin [C,
definition; the bound's value comes from the measured `T_ramp`];
(c) **`start_max_vsg_pass_v <= 3.3 V` at every point and both windows**;
(d) `T_ramp` measured on the `VREFR` (or equivalent) trace within the
grid-corner range the implementation claims. **Reject** on any failed
clause: the recommendation falls to a successor record re-ranking
Candidates 3 and 4 on this experiment's evidence, and the ramp cell is
not integrated.

After a confirm, the follow-up implementation issue owns the real
evidence: the full 135-point grid and the 24-point ext campaign on the
integrated core, the off-state benches, and the rows 6/10 loop-gain
re-runs — each under `DR-0009`'s fail-closed rules, with no threshold,
verdict or record edited.

### Metrics per point

Same evaluator columns as the committed records (peak, overshoot, peak
time, rise, settle, downward excursion, `Vsg`/`Vgd`/`Vds` maxima, peak
supply current, off-state metrics, and the `reen_*` set), plus two
additions the ramp needs: the `VREFR` trace (or its equivalent) for the
measured `T_ramp`, and the min/max of `EAOUT` over the transient (the
rail-excursion check — mechanism item 1's direct negate). The reduced
trace column list gains `vrefr` if the cell is wrapped for the
experiment; the evaluator itself is not modified.

### What the experiment must not do

No design-directory edit, no template edit beyond the local wrapper, no
evaluator edit, no threshold change, no record edit; `sim/` stays
append-only and any new record is a new run id. If the batch fleet is
unavailable, the experiment waits; nothing falls back to local grids
(the startup campaign's own rule [M, `sim/ldo-cmos5l-pvt-sweep/README.md`]).

## Row 9 cannot be reported satisfied without all of

1. The ramp implemented in the core (or a successor record's remedy),
   `python3 design/netlist.py --design sg13cmos5l --check` clean.
2. The 135-point grid and 24-point ext campaign re-run on the new
   netlist, **every point `pass` on the unchanged evaluator**, both
   windows.
3. The off-state benches re-run (`DR-0009` decision 5, the 50 mV bound),
   including the hot/`rwcs` no-load corner where today's core misses it
   (0.185718 V [M]) — that miss must be explained or fixed by the
   implementation; it is not excused by the ramp.
4. `|Vsg(Mpass)| <= 3.3 V` at every point, every window, every phase of
   every transient — or a separate rating record ruling on the residual,
   in the `DR-0017` terminal-stress classification style.
5. Rows 1-8 and 10 regression on the new netlist plus the off-state
   benches (the `DR-0017` §"Row 8" list's structure, applied to row 9's
   consumers).
6. The `DR-0008` addendum recorded (internal reference node, per-enable
   re-arm, unchanged ports), and this record's consumer inventory
   refreshed at implementation time.
7. Both review keys, for any ratification move — which is a separate,
   later record-and-evidence effort, not this plan.

## Follow-up boundaries

- **Implementation** (new issue, after this record's review): the ramp
  cell in `design/sg13cmos5l/`, the core's `Xamp` reference rewiring,
  regenerated netlists (outputs, not sources), the `design/README.md`
  soft-start section, the bounded experiment of this record, then the
  full evidence re-runs. The `DR-0008` addendum travels with it.
- **#55** owns the deterministic coverage inventory update; **#56** owns
  any statistical evidence. Neither exists for row 9 today; nothing here
  changes that.
- **#190 / #164 / #166 / #168** (the `DR-0017` limiter chain) are
  untouched by this record; Candidate 4's contingency above is a
  statement, not an action. #190 is a human's decision.
- **Cout/ESR extremes beyond the ext axis, supply transients during
  startup, and post-layout extraction of `C_ss`** are follow-up
  coverage, not part of the first deliverable.

## Consumer inventory

Command, run against `origin/main` `a8910ef5`:
`git grep -l 'ldo_core_cmos5l' origin/main -- design sim layout` gives
**6325 paths** (design 7, layout 15, sim 6303). Grouped the `DR-0017`
way:

**Sources and generated outputs that the implementation changes or regenerates:**

- `design/sg13cmos5l/ldo_core_cmos5l.sch`: the ramp cell instance and the
  `Xamp` reference rewiring (`VREF` -> `VREFR`). `.sym` unchanged (same
  six ports). `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice` is
  regenerated. `ldo_erramp_cmos5l.{sch,sym}` and its netlist are
  unchanged (the cell keeps its `VREF`-named pin; the core feeds it
  `VREFR`).
- `design/netlist.py` (the six-port invariant holds; check run),
  `design/README.md`, `design/xschemrc`.

**Benches with a flattened copy of the core body** (must be updated by
hand; `run_sweep.sh`'s topology guard rejects them until they are):

- `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh` (`LOOPGAIN_EXPECTED_BODY` and
  its negative controls), `testbench/tb_loopgain_cmos5l.spice.tmpl`,
  `tb_loopgain2v_cmos5l.spice.tmpl`, `tb_loopgain2i_cmos5l.spice.tmpl`,
  `tb_e1op_cmos5l.spice.tmpl`.

**Benches that include the netlist** (they pick up the ramp, then need
re-running and re-recording):

- `testbench/tb_dcsweep_cmos5l.spice.tmpl`, `tb_dropout_cmos5l.spice.tmpl`,
  `tb_psrr_cmos5l.spice.tmpl`, `tb_startup_cmos5l.spice.tmpl`,
  `run_e1op.sh`, `run_loopgain2.sh`, `startup_campaign.py`,
  `dropout_campaign.py`, `item5_evidence.py`, `test_ac_sweep.py`,
  `test_batch_backend.py`.
- `sim/ldo-cmos5l-monte-carlo/` (its benches, tests, `README.md`).
- `sim/ldo-cmos5l-enable/` (benches and `README.md`; the pre-#67 baseline
  stays as the historical baseline).
- `sim/characterization/` (`selection.json`, the generated report) — its
  netlist sha256 pins go stale, so item 8 needs re-selection after
  re-runs, per `signoff/README.md#regenerating`.
- `sim/README.md`, `sim/ldo-cmos5l-pvt-sweep/README.md`,
  `sim/migration-inventory-155.md`.

**Layout** (regenerated in the layout follow-up):
`layout/sg13cmos5l-ldo_core_cmos5l/generate.py` (the ramp devices are
drawn), `layout/lvs_reference.py`, `layout/run_flow.sh`,
`layout/README.md`, and the GDS / extracted netlist / LVS reference /
DRC / LVS / ERC / PEX reports and `lvs_request.json` in that directory.
`C_ss` (`cap_cmomi`) inherits today's name-equality LVS compare
[`DR-0017` layout note]. The nA-class `Iss` mirror layout is a matching
and leakage question [U].

**Append-only evidence that is NOT edited** (each item stays tied to the
netlist it was made from): `sim/ldo-cmos5l-pvt-sweep/{records,corners,netlist-snapshots,evidence,startup,backend-validation}/`,
`sim/ldo-cmos5l-enable/records/`, `sim/ldo-cmos5l-monte-carlo/{records,evidence}/`
— about 6300 paths in total, including every record this record cites.

**Signoff chain** (the pins a follow-up implementation moves, in
addition to the above): item 1 (design sources), item 8
(characterization re-selection), item 5 (row-4 envelope re-run), items
2/3/4/11 (layout set) — per `signoff/README.md#regenerating`. This
record itself moves only item 10 (`spec/README.md`), regenerated in the
PR that carries it.

## Missing characterization (explicit list)

1. `Iss` feasibility at 10-50 nA at 125 C junction temperature (leakage
   of `C_ss` and the mirror vs the ramp slope), and the mirror ratio's
   corner spread.
2. The loop's re-catch at ramp end: in-band settle after `VREFR` reaches
   `VREF`, per corner (the bounded experiment measures it at 8 points;
   the grid measures it everywhere later).
3. Re-enable onto a partially discharged output: the hold-off + track
   waveform vs the disabled-window length (the bench's 2 ms is one
   point [M]) — is `C_ss`'s discharge complete and is the re-arm clean?
4. `Vsg(Mpass)` over the whole transient with the ramp armed — the claim
   this record most wants measured, and the `DR-0001` carried gate's
   residual exposure.
5. The hot/`rwcs` no-load off-state miss (0.185718 V > 0.05 V [M]) — its
   mechanism is un-diagnosed on this branch; the implementation must
   explain it regardless of the ramp.
6. `C_ss` (`cap_cmomi`) post-layout extraction and its LVS treatment at
   the new instance.
7. Whether the ramp branch's loading of `VREFR` moves rows 6/10 margins
   at regulation (expected negligible [A], unmeasured).

## Alternatives considered

- **Candidate 1 alone (output-network specification).** Compared above;
  rejected as the *sole* remedy on the hot/`rwcs` evidence [M], the
  `Vsg` non-effect [C], and the row-10 envelope coupling. Kept as the
  companion operating-conditions note.
- **Candidate 4 (the `DR-0017` limiter) as the row-9 remedy.** Rejected
  for this record: the integration contingency (#190 operator decision;
  #164/#166/#168 parked), the unmeasured handoff, the row-7 margin, and
  the `Vsg` residual [C/A/U, stated in the candidate]. Row 9 should not
  wait on row 8's chain.
- **Candidate 3 (pass-gate slew limit).** Held as fallback; inferior to
  Candidate 2 on mechanism (saturation remains) and riskiest on rows
  6/10 [A/U].
- **External soft start (the integrator ramps `VREF`).** Rejected: it
  breaks the block-level convention that the external references are
  ideal (`sim/ldo-cmos5l-monte-carlo/README.md`'s row-2 exclusion, which
  `DR-0017` §1 cites), it moves the interface `DR-0008` records, and
  row 9 is a *block* claim. A product integrator may still ramp `VREF`;
  the block must not need it.
- **Re-compensation (larger/different `Cc`).** Rejected: the measured
  failure is large-signal saturation, not small-signal instability — the
  loop is stable in regulation (rows 6/10 evidence exists [M]) — and
  compensation changes to fix a startup transient would tax the
  ratified-row and stability evidence for no mechanism gain [C].
- **Do nothing until the limiter lands (#190).** Rejected: it leaves row
  9 with no path and leaves the re-enable half and the `Vsg` exceedance
  scheduled behind a row-8 decision.
- **Ramp armed at power-on only.** Rejected inside Candidate 2's
  definition: the grid logs all four failure reasons at 135 of 135 points
  in *both* windows [M]; a power-on-only arm leaves the re-enable half
  unserved by construction.

## Consequences

- This record changes exactly two source files and the signoff chain
  they move: this file, one new index bullet in `spec/README.md`, and the
  item-10 inventory/envelope/manifest-citation + T1 re-grade those move.
  No design, bench, layout or evidence file is touched. Row 9, row 7 and
  row 10 stay Open in `DR-0007` and the root `README.md`; no target,
  threshold, verdict or record state moves; the signoff exit code stays
  3 (honest non-T1), and no grader pin is bumped by this PR.
- `reuse.lock.json` is not changed; no sibling block is referenced.
- If the recommendation is confirmed, the follow-up implementation
  proceeds as its own issue (cell + integration + `DR-0008` addendum),
  then the evidence re-runs, then ratification — in that order, with
  row 9 released only by the two review keys, on evidence.

## References

- `sim/ldo-cmos5l-pvt-sweep/records/20261010-104827-91e92aa-startup-grid.{csv,md}`
  and `-startup-ext.{csv,md}`, `-startup-nominal.{csv,md}`,
  `-startup-halfstep.{csv,md}` and the two `.traces/` directories (the
  mechanism reduction's inputs).
- `sim/ldo-cmos5l-pvt-sweep/records/20261012-115531-cfa681f9.e1op.{csv,md,manifest.tsv}`
  (`DR-0015` E1 operating points), `…/20261011-070111-5391c68.csv`
  (Iq/divider anchors, quoted in `DR-0017`).
- `sim/ldo-cmos5l-pvt-sweep/testbench/tb_startup_cmos5l.spice.tmpl`
  (the enable profile), `startup_eval.py`, `startup_campaign.py`,
  `sim/ldo-cmos5l-pvt-sweep/README.md` §"Startup campaign (issue #69)".
- `design/sg13cmos5l/netlist/ldo_core_cmos5l.spice`,
  `ldo_erramp_cmos5l.spice`.
- Records: `DR-0001` (the `|Vsg|` gate), `DR-0002` (ratings table),
  `DR-0003` (`Mpass` sizing), `DR-0007` (row states), `DR-0008` (enable
  interface and over-rating record), `DR-0009` (methodology),
  `DR-0012`/`DR-0014` (numbering rule), `DR-0015` (E1),
  `DR-0017` (row-8 precedent; terminal-stress classification; consumer
  inventory shape), `DR-0018` (row-4 branch note).
- `spec/porting-plan.md` §1.2, §2.3, §4 item 6; root `README.md` target
  table (rows 7, 9, 10 wordings).
- Issues: #221 (this record), #69 (the startup campaign), #67 (`EN`
  interface), #165/#190/#164/#166/#168 (the limiter chain; untouched
  here), #130 (the `DR-0009` amendment), #55/#56 (coverage; untouched).


## Addendum 2026-11-23: bounded experiment result — **REJECT** (issue #314)

**Result: REJECT.** The operator authorised this experiment only (ruling of
2026-11-23 on #314, `authorize_experiment`). DR-0020 **stays Proposed**,
`DR-0007` row 9 **stays Open**, `design/sg13cmos5l/` is byte-unchanged, and no
threshold, verdict rule or existing record is edited. The ramp cell is not
integrated. Per this record's own rule, the recommendation now falls to a
successor record re-ranking Candidates 3 and 4 on this evidence; that record is
not written here.

**What was run.** The 7 points listed under "The bounded experiment" (no eighth
invented), one `klt sim --batch-set` on the batch fleet (`--wait-for-capacity
600`, runner klt 0.9.0, ngspice 47, jobs klt-sim-6fb629a85fbd, -85a10603813b, -c4ce2bd5ac69, -dd55fbc2ac75, -7a6e6944f76a, -0c4394b298da, -b387d7cc8a40), the unchanged startup bench
and `startup_eval.py`, the testbench-local netlist
`sim/ldo-cmos5l-startup-ramp/core_with_ramp.spice` (candidate values 40 nA /
~10 pF, a reset device, and a clamp realised with a second committed
`ldo_erramp_cmos5l`). Record: `sim/ldo-cmos5l-pvt-sweep/records/20261123-212501-9e332bb0-startup-ramp.*`
(per-point clause table in `….clauses.md`). Clauses (b) and (d) were fixed
before the run: (b) bound `(Cout*2*VREF/T_ramp + I_load)*1.25 + 1 mA`, (d) claimed
range 180-450 us (the DR's candidate pairings). A first attempt
(`20261123-212200-433395a5`) failed all 7 jobs (`exit_code: 4`). The committed
attempt-1 artifacts do not show `osdi_load_failed`, so the diagnosis is inferred,
not re-derivable from them: the campaign's deck-side OSDI preamble conflicts with
the runner's own `osdi_preload` (per `batch_backend.py`, #313; closed
2AMLogic/klayout-tools#5766). Its direct support is that omitting the preamble
made the same 7-request set pass. The driver now omits the preamble (and with it
`set num_threads=1`, harmless for single-corner requests); the decks are otherwise
identical. The preamble remains in `startup_campaign.py`: tracked in #330.

**Deviation from "Metrics per point".** "The reduced trace column list gains
`vrefr`" was not done: the committed reduced traces carry no `vrefr`
(`startup_campaign.py` hard-codes the column set and was kept unchanged by scope).
`T_ramp`, the clause-(b) bound and `VREFR max V` below were read from uncommitted
rawfiles (sha256 in the record's `raw_sha256` column) and are not re-derivable
from committed traces. REJECT does not depend on them: clause (a) fails at 5 of
7 points from the committed CSV.

**What the ramp did.** Mechanism item 1 is negated: minimum `EAOUT` over the
transient is 2.1-2.8 V (it was 0.003-0.009 V), so `Vsg(Mpass)` is **0.80-1.51 V
at every point in both windows** (**clause (c) holds**, against 3.62-3.63 V
before). Start peaks are 1.834-1.839 V (before: 1.87-2.34 V), no start
rail-to-rail excursion. The clauses that fail:

| point (mos/T/Vin/load/Cout/ESR) | start peak V | start settle us | start down-exc mV | reen peak V | reen down-exc mV | min EAOUT V | start/reen result |
|---|---|---|---|---|---|---|---|
| ff/27C/3.63V/1mA/1000nF/0m | 1.835 | 471 | 0.00 | 1.836 | 47.04 | 2.747 | pass/fail |
| ss/-40C/3.63V/1mA/1000nF/0m | 1.834 | 456 | 0.00 | 1.834 | 45.82 | 2.602 | pass/fail |
| tt/27C/3.63V/0mA/330nF/0m | 1.838 | 705 | 2.02 | 1.822 | 0.00 | 2.827 | fail/pass |
| tt/27C/3.63V/0mA/4700nF/500m | 1.836 | 486 | 0.19 | 1.829 | 0.00 | 2.399 | fail/pass |
| tt/27C/3.30V/1mA/1000nF/0m | 1.839 | 489 | 3.13 | 1.836 | 46.62 | 2.34 | fail/fail |
| tt/27C/3.63V/50mA/330nF/0m | 1.836 | 465 | 0.00 | 1.834 | 0.00 | 2.242 | pass/pass |
| tt/27C/3.63V/50mA/4700nF/500m | 1.835 | 465 | 0.00 | 1.836 | 0.00 | 2.125 | pass/pass |

**Clauses per point** (c holds everywhere; a, b, d fail as listed):

| point | (a) start/reen verdict | (b) Ipk A / bound A | (c) Vsg start/reen V | (d) T_ramp us (start/reen) | VREFR max V |
|---|---|---|---|---|---|
| `st_ff_27c_rtyp_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | fail/False FAIL | 0.01083 / 0.006898 FAIL | 0.8826/0.82 ok | 484.1/484.2 FAIL | 0.9168 |
| `st_ss_-40c_rtyp_v3630mv_i1ma_c1000nf_e0mohm_t500ns` | fail/False FAIL | 0.009442 / 0.007048 FAIL | 1.028/0.9871 ok | 468.9/469 FAIL | 0.9157 |
| `st_tt_27c_rtyp_v3630mv_i0ma_c330nf_e0mohm_t1000ns` | fail/True FAIL | 0.004017 / 0.002554 FAIL | 0.8028/0.7557 ok | 477.8/477.9 FAIL | 0.9176 |
| `st_tt_27c_rtyp_v3630mv_i0ma_c4700nf_e500mohm_t1000ns` | fail/True FAIL | 0.0345 / 0.02313 FAIL | 1.231/0.001441 ok | 477.8/477.9 FAIL | 0.9178 |
| `st_tt_27c_rtyp_v3300mv_i1ma_c1000nf_e0mohm_t1000ns` | fail/False FAIL | 0.01126 / 0.006955 FAIL | 0.9604/0.894 ok | 478.2/478.3 FAIL | 0.9179 |
| `st_tt_27c_rtyp_v3630mv_i50ma_c330nf_e0mohm_t1000ns` | pass/True ok | 0.05256 / 0.06505 ok | 1.388/1.397 ok | 477.8/477.8 FAIL | 0.9179 |
| `st_tt_27c_rtyp_v3630mv_i50ma_c4700nf_e500mohm_t1000ns` | pass/True ok | 0.0686 / 0.08563 ok | 1.505/1.505 ok | 477.8/477.8 FAIL | 0.9177 |

**Overall: REJECT** (7 of 7 points)

**Which clause failed where.**

- (a) verdict: the start window passes at 5 of 7 points but **re-enable fails at 3**
  (ff/27C and ss/-40C at 1 mA/1000 nF show a 46-47 mV downward excursion; tt/3.30 V
  1 mA the same, 46.6 mV): re-enable onto a still-charged output holds the pass device off
  while `VOUT/2 > VREFR`, and the output decays through the load before the ramp
  catches it, a non-monotonic dip. This is the partial-discharge case DR-0020 listed as [U].
  The start window itself fails at 3 points on 1.5-3 mV (peak 1.836-1.839 V against the
  1.836 V edge, 2-3 mV downward excursion), at the tt points with 0 mA / 330 nF and
  1 mA / 3.30 V. Settle times are 456-705 us, well inside 3 ms.
- (b) peak supply current exceeds the pre-registered bound at the 5 points with 0-1 mA
  load (4.0-34.5 mA against 2.6-23.1 mA). It holds at both 50 mA points. The excess is not
  explained by this experiment (the bound uses the measured T_ramp and a 25 % + 1 mA margin).
- (d) measured `T_ramp` is 469-484 us in both windows at every point, above the claimed
  180-450 us. The nominal pairing estimate (225 us) was low by about 2x; the gap is the
  mirror ratio and `Css`, which this experiment did not tune. `VREFR` overshoots `VREF` by
  up to 18 mV (max 0.9179 V), which the clamp realisation does not fully hold.

**Reading.** The ramp removes the failure DR-0020 indicts (the rail excursion and the
`Vsg` exceedance) but, as drawn, does not meet the confirm bar. This addendum does not say
the Candidate 2 mechanism is wrong: four of the five failed clauses read as sizing and
clamp-quality issues. But the confirm gate is defined as pass-at-every-point, so the outcome
is reject, and re-tuning the ramp is a new decision, not part of this experiment.
The follow-up integration issue is **not** filed (that happens on confirm only).
The clamp used here costs a full amplifier's static current, so the row-7 budget in
this record's Candidate 2 text is not demonstrated either way.
