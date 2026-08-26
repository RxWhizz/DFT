"""Surrogate composicional expuesto por la API.

El modelo se carga una sola vez y de forma perezosa: el pickle son ~6 MB y
arrastra scikit-learn al proceso del servidor, así que no compensa hacerlo en el
arranque de una app cuya función principal es monitorizar.
"""
from __future__ import annotations

import statistics
import time

import re

import json
import logging
import threading
from pathlib import Path
from typing import Any

from .. import paths

log = logging.getLogger(__name__)



def models_dir() -> Path:
    """Modelos del surrogate: empaquetados en el binario, o en el repo."""
    return paths.find_resource("models")

_lock = threading.Lock()
_model: Any = None
_load_error: str | None = None


class SurrogateUnavailableError(RuntimeError):
    """El modelo no se pudo cargar (ausente, o pickle incompatible)."""


def _load() -> Any:
    """Carga el SurrogateEnsemble. Cachea también el fallo para no reintentar."""
    global _model, _load_error

    with _lock:
        if _model is not None:
            return _model
        if _load_error is not None:
            raise SurrogateUnavailableError(_load_error)

        try:
            from ml_surrogate.config import SurrogateConfig
            from ml_surrogate.predict import load_model

            # `SurrogateConfig.model_path` hace `root / model_dir` con su propia
            # raíz, que congelado apunta al directorio de extracción. Se le pasa
            # el directorio absoluto —el empaquetado o el del repositorio— y el
            # suyo queda sin efecto porque una ruta absoluta gana en `/`.
            _model = load_model(SurrogateConfig(model_dir=str(models_dir())))
            log.info("Surrogate cargado (%d features)", len(_model.feature_cols))
            return _model
        except Exception as exc:
            # Causa habitual: el pickle se generó con otra versión de
            # scikit-learn. Se incluye la instalada para que el mensaje sirva.
            try:
                import sklearn

                version = sklearn.__version__
            except Exception:
                version = "no instalado"
            _load_error = (
                f"{type(exc).__name__}: {exc}. "
                f"scikit-learn instalado: {version}; los modelos de models/*.pkl "
                f"se serializaron con 1.8.0."
            )
            log.warning("No se pudo cargar el surrogate — %s", _load_error)
            raise SurrogateUnavailableError(_load_error) from exc


def reset_cache() -> None:
    """Olvida el modelo y el error cacheados (para tests)."""
    global _model, _load_error
    with _lock:
        _model = None
        _load_error = None


# A/B/X en mayúscula son los sitios cristalográficos de ABX3; así coinciden con
# la firma de ml_surrogate.predict.predict_one y con las columnas de los CSV.
def predict(
    A: str,  # noqa: N803
    B: str,  # noqa: N803
    X: str,  # noqa: N803
    *,
    a_lat: float | None = None,
    e_mace_ev_atom: float | None = None,
    band_gap_gga_ev: float | None = None,
    eform_ev_atom: float | None = None,
    material: str | None = None,
) -> dict[str, Any]:
    """Bandgap predicho con su incertidumbre bootstrap para una composición."""
    from ml_surrogate.predict import predict_one

    return predict_one(
        _load(),
        A,
        B,
        X,
        a_lat=a_lat,
        E_mace_eV_atom=e_mace_ev_atom,
        band_gap_gga=band_gap_gga_ev,
        Eform_eV_atom=eform_ev_atom,
        mat=material,
    )


def top8_reference() -> list[dict[str, Any]]:
    """Predicción del surrogate frente a DFT y experimento para los top-8.

    Las referencias viven en `DFT_REF` de src/ml_surrogate/predict.py; se leen
    de ahí en vez de duplicarlas.
    """
    from ml_surrogate.predict import DFT_REF, TOP8_MATS

    filas = []
    for material, sitios in TOP8_MATS.items():
        fila: dict[str, Any] = {"material": material, **sitios, **DFT_REF.get(material, {})}
        try:
            pred = predict(sitios["A"], sitios["B"], sitios["X"], material=material)
            fila.update(
                {
                    "Eg_ml_eV": pred.get("bandgap_pred"),
                    "Eg_ml_std_eV": pred.get("bandgap_uncertainty"),
                    "stability_score": pred.get("stability_score"),
                    "solar_score": pred.get("solar_score"),
                    "in_pv_window": pred.get("in_pv_window"),
                }
            )
        except SurrogateUnavailableError:
            fila["error"] = "modelo no disponible"
        filas.append(fila)
    return filas


def model_metrics() -> dict[str, Any]:
    """Métricas de todos los models/*.metrics.json más el estado de carga."""
    modelos = []
    for path in sorted(models_dir().glob("*.metrics.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            data = {"error": str(exc)}
        pkl = path.with_name(path.name.replace(".metrics.json", ".pkl"))
        modelos.append(
            {
                "name": path.name.removesuffix(".metrics.json"),
                "metrics": data,
                "has_pickle": pkl.is_file(),
                "size_mb": round(pkl.stat().st_size / 1e6, 1) if pkl.is_file() else None,
            }
        )

    try:
        _load()
        estado, detalle = "ok", None
    except SurrogateUnavailableError as exc:
        estado, detalle = "error", str(exc)

    return {"models": modelos, "surrogate_status": estado, "surrogate_error": detalle}


# ── Paridad contra el DFT del lote ───────────────────────────────────────────

_RE_GAP = re.compile(r"^\s*Gap:\s*([0-9.]+)\s*eV", re.M)
_PARITY_CACHE: dict[str, Any] = {"t": 0.0, "clave": None, "valor": None}
_PARITY_TTL = 20.0     # leer decenas de logs de GPAW en un disco lento no es gratis

# Centro de la ventana fotovoltaica: el criterio con el que se ordena el «top».
_PV_CENTRO = 1.45


def _gap_dft(job_dir: Path) -> float | None:
    """Bandgap que GPAW dejó en su log.

    No está en `status.json` —que guarda energías, no gaps— pero sí en la
    salida del cálculo, como `Gap: 0.879 eV`.
    """
    for log in job_dir.glob("*.txt"):
        if log.name == "error.txt":
            continue
        try:
            m = _RE_GAP.search(log.read_text(errors="replace"))
        except OSError:
            continue
        if m:
            return float(m.group(1))
    return None


def parity_from_batch(batch_dir: Path, limit: int = 8) -> dict[str, Any]:
    """Los `limit` mejores del lote según el predictor, frente a su DFT.

    Sustituye a la comparación contra referencias de literatura: aquello medía
    un modelo entrenado en gaps PBE contra valores experimentales, así que
    arrastraba el error del método además del error del modelo. Aquí las dos
    columnas son la misma magnitud —gap PBE— y la diferencia es solo del
    predictor.

    La predicción **no** recibe el gap DFT como característica, aunque
    `predict_one` lo admita: dárselo haría la comparación circular.
    """
    ahora = time.time()
    # El límite entra en la clave: sin él, pedir 50 devolvía los 8 cacheados.
    clave = f"{batch_dir}|{limit}"
    if (_PARITY_CACHE["clave"] == clave
            and ahora - _PARITY_CACHE["t"] < _PARITY_TTL
            and _PARITY_CACHE["valor"] is not None):
        return _PARITY_CACHE["valor"]

    import pandas as pd
    from types import SimpleNamespace

    from buho.screening.cascade import ScreeningCascade
    from ml_surrogate.features import build_X

    n_convergidos = 0
    filas: list[dict[str, Any]] = []
    feats: list[dict[str, Any]] = []

    for status in sorted(batch_dir.glob("*/status.json")):
        try:
            estado = json.loads(status.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if estado.get("status") != "converged":
            continue
        n_convergidos += 1

        gap = _gap_dft(status.parent)
        if gap is None:
            continue
        try:
            meta = json.loads((status.parent / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not meta.get("fractions"):
            continue

        # Se reutiliza el constructor de features de la cascada en vez de
        # replicarlo: si allí cambia, esto lo sigue en vez de divergir en
        # silencio, y el «predicho» es el mismo número que rankeó al candidato.
        candidato = SimpleNamespace(
            fractions=meta["fractions"],
            is_organic_A=bool(meta.get("molecular_A_placeholder")),
        )
        try:
            feats.append(ScreeningCascade._features(candidato))
        except (KeyError, TypeError):
            continue
        filas.append({
            "job_id": status.parent.name,
            "formula": meta.get("formula", status.parent.name),
            "eg_dft_ev": gap,
            "xc": estado.get("xc_method"),
            "kpts": estado.get("kpts"),
        })

    resultado: dict[str, Any] = {
        "batch": batch_dir.name,
        "items": [],
        "n_converged": n_convergidos,
        "n_with_gap": len(filas),
        "dft_range_ev": None,
        "n_dft_distintos": 0,
        "scissor_ev": None,
        "mae_raw_ev": None,
        "mae_scissor_ev": None,
        "rmse_scissor_ev": None,
        "n_fit": 0,
        "error": None,
    }

    if filas:
        try:
            modelo = _load()
            Xm = build_X(pd.DataFrame(feats), modelo.feature_cols)
            medias, sigmas = modelo.predict_batch(Xm)
            for fila, m, s in zip(filas, medias, sigmas):
                fila["eg_pred_ev"] = float(m)
                fila["eg_pred_std_ev"] = float(s)
                fila["pv_distance"] = abs(float(m) - _PV_CENTRO)

            # ── Scissor ──────────────────────────────────────────────────────
            # Desplazamiento rígido, como el `corrected_gap` de
            # dft_cspbi3.bandgap_correction: Eg_corregido = Eg + Δ. Δ sale de la
            # MEDIANA de los residuos, no de la media, para que un par de
            # materiales mal predichos no arrastren la corrección entera.
            #
            # Se ajusta sobre TODOS los jobs emparejados del lote, no sobre los
            # `limit` que se muestran: ajustar y evaluar sobre los mismos ocho
            # daría un error residual artificialmente bueno.
            residuos = [f["eg_dft_ev"] - f["eg_pred_ev"] for f in filas]
            scissor = statistics.median(residuos)
            for fila in filas:
                fila["eg_pred_scissor_ev"] = fila["eg_pred_ev"] + scissor

            crudos = [abs(r) for r in residuos]
            corregidos = [abs(r - scissor) for r in residuos]
            gaps = [f["eg_dft_ev"] for f in filas]
            rango_dft = max(gaps) - min(gaps)
            resultado.update(
                dft_range_ev=round(rango_dft, 4),
                n_dft_distintos=len({round(g, 3) for g in gaps}),
                scissor_ev=round(scissor, 4),
                mae_raw_ev=round(statistics.mean(crudos), 4),
                mae_scissor_ev=round(statistics.mean(corregidos), 4),
                rmse_scissor_ev=round(
                    (sum(x * x for x in corregidos) / len(corregidos)) ** 0.5, 4),
                n_fit=len(filas),
            )

            # «Top» = los que el predictor sitúa más cerca de la ventana
            # fotovoltaica, que es el criterio con el que se criban.
            filas.sort(key=lambda f: f["pv_distance"])
            resultado["items"] = filas[:limit]
        except SurrogateUnavailableError as exc:
            resultado["error"] = str(exc)
        except Exception as exc:                      # noqa: BLE001
            resultado["error"] = f"{type(exc).__name__}: {exc}"

    _PARITY_CACHE.update(t=ahora, clave=clave, valor=resultado)
    return resultado
