"""OghmaNano device package generation for the DFT workflow.

OghmaNano is not an ML model. It is a deterministic optoelectronic device
solver, so this module keeps it as an optional DFT/device-analysis step rather
than part of the ML-only AINAGENT scoring path.
"""

from __future__ import annotations

import json
import html
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class OghmaDeviceResult:
    """Summary of the OghmaNano DFT handoff step."""

    status: str
    method_type: str = "device_physics_drift_diffusion_not_ml"
    pce_pct: Optional[float] = None
    voc_V: Optional[float] = None
    jsc_mA_cm2: Optional[float] = None
    ff: Optional[float] = None
    runner: Optional[str] = None
    manifest_path: Optional[str] = None
    stack_path: Optional[str] = None
    comparison_report_path: Optional[str] = None
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "method_type": self.method_type,
            "pce_pct": self.pce_pct,
            "voc_V": self.voc_V,
            "jsc_mA_cm2": self.jsc_mA_cm2,
            "ff": self.ff,
            "runner": self.runner,
            "manifest_path": self.manifest_path,
            "stack_path": self.stack_path,
            "comparison_report_path": self.comparison_report_path,
            "flags": list(self.flags),
        }


def prepare_oghma_device_step(
    phase_dir: str | Path,
    step_dir: str | Path,
    *,
    phase: str,
    config: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> OghmaDeviceResult:
    """Prepare a DFT-derived OghmaNano device handoff package.

    The function always writes JSON inputs. It only launches OghmaNano when
    ``oghma_device.execute`` is true, because Linux OghmaNano commonly launches
    through Wine and the project format must be validated by the GUI/core.
    """
    phase_dir = Path(phase_dir)
    step_dir = Path(step_dir)
    step_dir.mkdir(parents=True, exist_ok=True)
    cfg = config or {}

    stack = build_device_stack_from_dft(phase_dir, phase=phase, config=cfg)
    stack_path = step_dir / "device_stack.json"
    stack_path.write_text(json.dumps(stack, indent=2))

    runner = resolve_oghma_runner(cfg.get("executable"))
    execute = bool(cfg.get("execute", False)) and not dry_run
    manifest_path = step_dir / "oghma_manifest.json"
    result_path = step_dir / "oghma_device_result.json"
    sim_info_path = step_dir / "sim_info.dat"

    flags = [
        "OGHMANANO_IS_DEVICE_PHYSICS_NOT_ML",
        "GUI_PROJECT_FORMAT_REQUIRES_VALIDATION",
    ]
    if not runner:
        flags.append("OGHMANANO_RUNNER_NOT_FOUND")
    if not execute:
        flags.append("OGHMANANO_EXECUTION_NOT_REQUESTED")

    manifest = {
        "phase": phase,
        "method_type": "device_physics_drift_diffusion_not_ml",
        "status": "prepared",
        "runner": runner,
        "execute_requested": execute,
        "stack_path": str(stack_path),
        "expected_oghma_outputs": ["sim_info.dat", "jv.dat", "out.txt"],
        "notes": [
            "OghmaNano is GUI-first on Linux but ships a core executable via Wine.",
            "Use device_stack.json to configure the Oghma project or a validated json.inp template.",
            "If sim_info.dat is produced later, rerun this step to parse PCE/FF/Voc/Jsc.",
        ],
        "flags": flags,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    _write_readme(step_dir, runner=runner)

    parsed = parse_oghma_sim_info(sim_info_path)
    if parsed:
        out = OghmaDeviceResult(
            status="parsed_existing_result",
            pce_pct=parsed.get("pce_pct"),
            voc_V=parsed.get("voc_V"),
            jsc_mA_cm2=parsed.get("jsc_mA_cm2"),
            ff=parsed.get("ff"),
            runner=runner,
            manifest_path=str(manifest_path),
            stack_path=str(stack_path),
            flags=flags,
        )
        out.comparison_report_path = str(write_oghma_method_comparison(step_dir, stack, out))
        result_path.write_text(json.dumps(out.to_dict(), indent=2))
        return out

    if execute and runner:
        completed = subprocess.run(
            [runner],
            cwd=str(step_dir),
            check=False,
            capture_output=True,
            text=True,
            timeout=int(cfg.get("timeout_s", 600)),
        )
        (step_dir / "oghma_stdout.log").write_text(completed.stdout)
        (step_dir / "oghma_stderr.log").write_text(completed.stderr)
        parsed = parse_oghma_sim_info(sim_info_path)
        status = "completed" if completed.returncode == 0 else "failed"
        if completed.returncode != 0:
            flags.append(f"OGHMANANO_RETURN_CODE:{completed.returncode}")
        out = OghmaDeviceResult(
            status=status,
            pce_pct=parsed.get("pce_pct") if parsed else None,
            voc_V=parsed.get("voc_V") if parsed else None,
            jsc_mA_cm2=parsed.get("jsc_mA_cm2") if parsed else None,
            ff=parsed.get("ff") if parsed else None,
            runner=runner,
            manifest_path=str(manifest_path),
            stack_path=str(stack_path),
            flags=flags,
        )
        out.comparison_report_path = str(write_oghma_method_comparison(step_dir, stack, out))
        result_path.write_text(json.dumps(out.to_dict(), indent=2))
        return out

    out = OghmaDeviceResult(
        status="prepared",
        runner=runner,
        manifest_path=str(manifest_path),
        stack_path=str(stack_path),
        flags=flags,
    )
    out.comparison_report_path = str(write_oghma_method_comparison(step_dir, stack, out))
    result_path.write_text(json.dumps(out.to_dict(), indent=2))
    return out


def write_oghma_method_comparison(
    step_dir: str | Path,
    stack: dict[str, Any],
    oghma_result: OghmaDeviceResult,
) -> Path:
    """Write an HTML comparison of DFT, optional Oghma, and ML placeholders."""
    step_dir = Path(step_dir)
    sq_ref = stack.get("dft_inputs", {}).get("sq_limit_reference", {})
    records = [
        {
            "name": "DFT SQ limit",
            "method_type": "dft_postprocessed_detailed_balance",
            "pce_pct": sq_ref.get("pce_pct"),
            "voc_V": sq_ref.get("voc_V"),
            "jsc_mA_cm2": sq_ref.get("jsc_mA_cm2"),
            "ff": sq_ref.get("ff"),
            "flags": ["REFERENCE_FROM_13_SQ_LIMIT"],
        },
        {
            "name": "OghmaNano",
            "method_type": oghma_result.method_type,
            "pce_pct": oghma_result.pce_pct,
            "voc_V": oghma_result.voc_V,
            "jsc_mA_cm2": oghma_result.jsc_mA_cm2,
            "ff": oghma_result.ff,
            "flags": oghma_result.flags,
        },
        {
            "name": "AINAGENT ML surrogate",
            "method_type": "ml_property_model",
            "pce_pct": None,
            "voc_V": None,
            "jsc_mA_cm2": None,
            "ff": None,
            "flags": ["IMPORT_AINAGENT_RESULT_JSON_FOR_SIDE_BY_SIDE_COMPARISON"],
        },
    ]
    report_path = step_dir / "method_comparison.html"
    report_path.write_text(_render_comparison_html(records, title="DFT/Oghma/AINAGENT PV Comparison"))
    return report_path


def build_device_stack_from_dft(
    phase_dir: str | Path,
    *,
    phase: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a simple perovskite device stack from completed DFT outputs."""
    phase_dir = Path(phase_dir)
    cfg = config or {}
    score = _read_json(phase_dir / "12_score" / "solar_score.json")
    sq = _read_json(phase_dir / "13_sq_limit" / "sq_limit.json")
    electronic = _read_json(phase_dir / "10_effective_masses" / "electronic_analysis.json")

    absorber_thickness = cfg.get("absorber_thickness_nm")
    if absorber_thickness is None:
        absorber_thickness = sq.get("thickness_nm", cfg.get("thickness_nm", 500.0))

    bandgap = (
        score.get("inputs", {}).get("bandgap_eV")
        or electronic.get("gap_eV")
        or cfg.get("absorber_bandgap_eV")
    )
    eps_r = score.get("inputs", {}).get("eps_r") or cfg.get("absorber_eps_r")

    default_layers = [
        {"name": "FTO", "role": "front_contact", "thickness_nm": 500.0},
        {"name": "SnO2", "role": "ETL", "thickness_nm": 50.0, "bandgap_eV": 3.6},
        {
            "name": "CsPbI3",
            "role": "absorber",
            "thickness_nm": float(absorber_thickness),
            "bandgap_eV": bandgap,
            "dielectric_constant": eps_r,
        },
        {"name": "Spiro-OMeTAD", "role": "HTL", "thickness_nm": 200.0, "bandgap_eV": 3.0},
        {"name": "Au", "role": "back_contact", "thickness_nm": 80.0},
    ]
    layers = cfg.get("layers", default_layers)

    return {
        "simulator": "OghmaNano",
        "phase": phase,
        "formula": cfg.get("formula", "CsPbI3"),
        "method_type": "device_physics_drift_diffusion_not_ml",
        "layers": layers,
        "dft_inputs": {
            "bandgap_eV": bandgap,
            "dielectric_constant": eps_r,
            "effective_masses": {
                "m_e_m0": electronic.get("m_e_soc_m0") or electronic.get("m_e_m0"),
                "m_h_m0": electronic.get("m_h_soc_m0") or electronic.get("m_h_m0"),
            },
            "sq_limit_reference": {
                "pce_pct": sq.get("pce_pct"),
                "jsc_mA_cm2": sq.get("jsc_mA_cm2"),
                "voc_V": sq.get("voc_V"),
                "ff": sq.get("ff"),
            },
        },
        "source_files": {
            "solar_score": str(phase_dir / "12_score" / "solar_score.json"),
            "sq_limit": str(phase_dir / "13_sq_limit" / "sq_limit.json"),
            "electronic_analysis": str(phase_dir / "10_effective_masses" / "electronic_analysis.json"),
            "optical_frequencies": str(phase_dir / "11_optical" / "optical_frequencies.npy"),
            "absorption": str(phase_dir / "11_optical" / "absorption_cm1.npy"),
        },
    }


def parse_oghma_sim_info(path: str | Path) -> dict[str, float] | None:
    """Parse OghmaNano ``sim_info.dat`` when a GUI/core run has produced one."""
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return {
        "pce_pct": _float_or_none(data.get("pce") or data.get("pce_pct") or data.get("PCE")),
        "voc_V": _float_or_none(data.get("voc") or data.get("Voc") or data.get("voc_V")),
        "jsc_mA_cm2": _float_or_none(data.get("jsc") or data.get("Jsc") or data.get("jsc_mA_cm2")),
        "ff": _float_or_none(data.get("ff") or data.get("FF")),
    }


def _render_comparison_html(records: list[dict[str, Any]], *, title: str) -> str:
    max_pce = max([_float_or_none(row.get("pce_pct")) or 0.0 for row in records] + [30.0])
    cards = "\n".join(_render_card(row, max_pce=max_pce) for row in records)
    payload = html.escape(json.dumps(records, indent=2))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f7f8fa; color: #17202a; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px; }}
    h1 {{ font-size: 28px; margin: 0 0 8px; }}
    p {{ color: #4c5967; line-height: 1.5; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
    .card {{ background: white; border: 1px solid #d8dee6; border-radius: 8px; padding: 16px; }}
    .name {{ font-size: 18px; font-weight: 700; margin-bottom: 6px; }}
    .method {{ font-family: monospace; font-size: 13px; color: #526070; }}
    .metric {{ display: flex; justify-content: space-between; margin: 12px 0 4px; }}
    .bar {{ height: 10px; background: #e5e9ef; border-radius: 999px; overflow: hidden; }}
    .fill {{ height: 100%; background: #2374ab; }}
    .flags {{ margin-top: 12px; font-size: 12px; color: #8a4b08; }}
    pre {{ overflow: auto; background: #111827; color: #e5e7eb; padding: 16px; border-radius: 8px; }}
  </style>
</head>
<body>
<main>
  <h1>{html.escape(title)}</h1>
  <p>DFT postprocessing, OghmaNano device physics, and AINAGENT ML are shown together for comparison. OghmaNano is not ML and should not be mixed into strict ML-only scoring.</p>
  <section class="grid">
    {cards}
  </section>
  <h2>Raw Records</h2>
  <pre>{payload}</pre>
</main>
</body>
</html>
"""


def _render_card(row: dict[str, Any], *, max_pce: float) -> str:
    pce = _float_or_none(row.get("pce_pct"))
    width = 0.0 if pce is None else max(0.0, min(100.0, 100.0 * pce / max_pce))
    pce_label = "missing" if pce is None else f"{pce:.2f}%"
    flags = ", ".join(str(flag) for flag in row.get("flags", [])) or "none"
    return f"""<article class="card">
  <div class="name">{html.escape(str(row.get("name", "unknown")))}</div>
  <div class="method">{html.escape(str(row.get("method_type", "missing")))}</div>
  <div class="metric"><span>PCE</span><strong>{html.escape(pce_label)}</strong></div>
  <div class="bar"><div class="fill" style="width: {width:.1f}%"></div></div>
  <div class="metric"><span>Voc</span><span>{_fmt(_float_or_none(row.get("voc_V")), " V")}</span></div>
  <div class="metric"><span>Jsc</span><span>{_fmt(_float_or_none(row.get("jsc_mA_cm2")), " mA/cm2")}</span></div>
  <div class="metric"><span>FF</span><span>{_fmt(_float_or_none(row.get("ff")), "")}</span></div>
  <div class="flags">Flags: {html.escape(flags)}</div>
</article>"""


def _fmt(value: float | None, suffix: str) -> str:
    return "missing" if value is None else f"{value:.3g}{suffix}"


def resolve_oghma_runner(explicit: str | None = None) -> str | None:
    """Resolve an OghmaNano runner if one is available."""
    candidates = [
        explicit,
        os.environ.get("OGHMA_EXECUTABLE"),
        shutil.which("oghma_core"),
        shutil.which("oghma"),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def _write_readme(step_dir: Path, *, runner: str | None) -> None:
    runner_text = runner or "<install OghmaNano first: bash scripts/install_oghma_ubuntu.sh>"
    (step_dir / "README_oghma_device.md").write_text(
        "# OghmaNano device step\n\n"
        "OghmaNano is not ML; it is a device-physics drift-diffusion/optics solver.\n\n"
        "This step prepares DFT-derived device inputs in `device_stack.json`.\n"
        "Use the GUI to create or validate the Oghma project, then map the absorber\n"
        "band gap, thickness, dielectric constant, and optical data from this folder.\n\n"
        "Detected runner:\n\n"
        f"```bash\n{runner_text}\n```\n\n"
        "If a validated Oghma project writes `sim_info.dat` in this directory,\n"
        "rerun the workflow step to parse PCE, Voc, Jsc, and FF into\n"
        "`oghma_device_result.json`.\n"
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
