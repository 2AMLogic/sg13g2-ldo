# Source me:  source sim/env.sh
#
# Resolves the PDK environment the same way sg13g2-bandgap's and
# sg13g2-opamp's sim/env.sh (and this repo's own design/xschemrc) do
# (PDK_ROOT/PDK env vars, falling back to the usual open_pdks install
# prefixes: /usr/share/pdk, /usr/local/share/pdk, ~/share/pdk, ~/.ciel,
# ~/.volare), so an interactive ngspice session and every sim/*/run_*.sh
# script agree on which PDK install is in use. Safe to source from any
# directory; does not require `klt` to be installed (this repo's
# testbenches must remain runnable in a sandbox that has ngspice but not
# klayout-tools).
#
# PDK-agnostic by construction, not just for the default `ihp-sg13g2`
# (SG13G2 branch, `design/`): every path below is built from `${PDK}` /
# `${PDK_ROOT}`, so `PDK=ihp-sg13cmos5l source sim/env.sh` resolves the
# SG13CMOS5L branch's install the same way (design/README.md "Install
# shape is a dispatch hazard" -- install BOTH `ihp-sg13g2` and
# `ihp-sg13cmos5l` under the same `PDK_ROOT`, since the latter's device
# symbols/HV model cards symlink into the former). Verified working end to
# end by `sim/ldo-cmos5l-pvt-sweep/run_sweep.sh` (issue #21) -- see
# `sim/pdk-cmos5l.json` for the SG13CMOS5L revision that experiment's
# evidence pins. The `SG13G2_*` exported variable names below predate that
# second PDK and are kept as-is for backward compatibility with every
# existing `sim/*/run_*.sh` consumer; they hold whichever PDK `${PDK}`
# names at source time, not literally SG13G2 only.
#
# This file is sourced, not executed, so it has no shebang; the directive
# below tells shellcheck which dialect to assume.
# shellcheck shell=bash

# ${(%):-%x} is the zsh equivalent of ${BASH_SOURCE[0]} -- sourced from both
# shells; shellcheck cannot parse the zsh half.
# shellcheck disable=SC2296
_sg13g2_env_self="${BASH_SOURCE[0]:-${(%):-%x}}"
_sg13g2_sim_dir="$(cd "$(dirname "${_sg13g2_env_self}")" && pwd)"
_sg13g2_repo_root="$(cd "${_sg13g2_sim_dir}/.." && pwd)"

export PDK="${PDK:-ihp-sg13g2}"

if [[ -z "${PDK_ROOT:-}" ]]; then
  for _sg13g2_candidate in /usr/share/pdk /usr/local/share/pdk \
                           "${HOME}/share/pdk" "${HOME}/.ciel" "${HOME}/.volare"; do
    if [[ -d "${_sg13g2_candidate}/${PDK}/libs.tech/ngspice" ]]; then
      export PDK_ROOT="${_sg13g2_candidate}"
      break
    fi
  done
fi

if [[ -n "${PDK_ROOT:-}" && -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  export SG13G2_NGSPICE_MODELS="${PDK_ROOT}/${PDK}/libs.tech/ngspice/models"
  # OSDI-compiled Verilog-A device models (PSP103 MOS, r3_cmc resistors).
  # This directory is where the PDK's own .spiceinit/install.py expect them
  # and where sim/tools/build-osdi.sh writes them; it does NOT exist in a
  # freshly-unpacked IHP-Open-PDK v0.3.0 tree, because that release ships
  # the Verilog-A sources but no prebuilt .osdi binaries. Every testbench
  # that instantiates a MOS loads from here via `pre_osdi`.
  export SG13G2_OSDI_DIR="${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi"
  echo "${PDK}: PDK_ROOT=${PDK_ROOT} PDK=${PDK}"
  if [[ ! -f "${SG13G2_OSDI_DIR}/psp103.osdi" ]]; then
    echo "${PDK}: OSDI device models not built yet in ${SG13G2_OSDI_DIR}" >&2
    echo "${PDK}: MOS devices (sg13_hv_*) will not simulate until they are." >&2
    echo "${PDK}: Build them with:  PDK=${PDK} sim/tools/build-osdi.sh" >&2
    echo "${PDK}: (see sim/README.md 'OSDI device models' for why this step exists)." >&2
  fi
else
  echo "${PDK}: no ${PDK} install found under PDK_ROOT or the usual prefixes." >&2
  echo "${PDK}: set PDK_ROOT to an open_pdks-shaped IHP-Open-PDK checkout and re-source," >&2
  echo "${PDK}: e.g. via klayout-tools' scripts/fetch-ihp-sg13g2.sh (SG13G2) or the" >&2
  echo "${PDK}: separate IHP-GmbH/ihp-sg13cmos5l checkout (SG13CMOS5L, see" >&2
  echo "${PDK}: sim/pdk-cmos5l.json), then:" >&2
  echo "${PDK}:   export PDK_ROOT=/path/to/pdk/parent PDK=${PDK}" >&2
  echo "${PDK}: see sim/pdk.json (SG13G2) / sim/pdk-cmos5l.json (SG13CMOS5L) for the" >&2
  echo "${PDK}: pinned releases this repo's evidence records target." >&2
fi

unset _sg13g2_env_self _sg13g2_sim_dir _sg13g2_candidate
# _sg13g2_repo_root intentionally left exported-free but available to callers
# that source this file inline; not exported to avoid leaking into child envs.
