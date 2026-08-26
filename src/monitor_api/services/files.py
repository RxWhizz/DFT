"""Acceso controlado a estructuras, reportes y figuras del repositorio.

Estos endpoints sirven archivos elegidos por el cliente, así que son los más
expuestos a path traversal. Todo pasa por `safe_join()`: raíz permitida
explícita, sin componentes `..`, sin rutas absolutas, sin symlinks que se
escapen del árbol y con lista blanca de extensiones.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .. import paths

log = logging.getLogger(__name__)


# Funciones y no constantes: la raíz de datos se puede fijar en tiempo de
# ejecución (--data-root), y una constante de módulo congelaría el valor que
# hubiera al importar.

def structures_dir() -> Path:
    """Estructuras de referencia: viajan en el binario, o están en el repo."""
    return paths.find_resource("structures")


def reports_dirs() -> tuple[Path, ...]:
    """Salidas del usuario — siempre en su raíz de datos, nunca empaquetadas."""
    return (paths.resolve_data("reports"), paths.resolve_data("imagenes"))

EXT_ESTRUCTURA = {".cif", ".json", ".xyz", ".extxyz"}
EXT_REPORTE = {".md", ".json"}
EXT_FIGURA = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}
_BATCH_RE = re.compile(r"^batch_\d+$")
_JOB_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".cif": "chemical/x-cif",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
}


class UnsafePathError(ValueError):
    """La ruta pedida se sale del árbol permitido o no está en la lista blanca."""


def safe_join(root: Path, relative: str, allowed_ext: set[str] | None = None) -> Path:
    """Resuelve `relative` dentro de `root`, o lanza UnsafePathError."""
    if not relative or relative.startswith(("/", "\\")):
        raise UnsafePathError(relative)

    partes = Path(relative).parts
    if any(p in ("..", "") for p in partes) or Path(relative).is_absolute():
        raise UnsafePathError(relative)

    root_r = root.resolve()
    destino = (root_r / relative).resolve()

    # `resolve()` sigue symlinks: esto también atrapa un enlace que apunte fuera.
    if root_r != destino and root_r not in destino.parents:
        raise UnsafePathError(relative)
    if allowed_ext is not None and destino.suffix.lower() not in allowed_ext:
        raise UnsafePathError(relative)
    return destino


# ── Estructuras ──────────────────────────────────────────────────────────────

def list_structures(runs_dir: Path) -> list[dict[str, Any]]:
    """Estructuras disponibles: fases de referencia, top-8 y las de cada job."""
    items: list[dict[str, Any]] = []

    raiz_estructuras = structures_dir()
    for path in sorted(raiz_estructuras.rglob("*")):
        if path.is_file() and path.suffix.lower() in EXT_ESTRUCTURA:
            items.append(
                {
                    "id": f"repo:{path.relative_to(raiz_estructuras)}",
                    "name": path.stem,
                    "group": "top8" if path.parent.name == "top8" else "fases",
                    "format": path.suffix.lstrip("."),
                    "mtime": path.stat().st_mtime,
                }
            )

    # «Jobs actuales» debe ser el lote que se está calculando, no el `runs_dir`
    # fijado al arrancar el motor: con la configuración apuntando a un lote
    # viejo, esta sección enseñaba estructuras de hace días bajo un rótulo que
    # decía «actuales».
    lote = _lote_activo(runs_dir)
    vistos: set[str] = set()
    if lote is not None and lote.is_dir():
        for path in sorted(lote.glob("*/structure.cif")):
            # Mismo filtro que las recientes: el visor enseña lo que pasó la
            # selección ML, no todo lo que quedó en el directorio. Saltárselo
            # aquí colaba candidatos crudos bajo el rótulo del lote en curso.
            if not _passed_ml_tiers(path.parent):
                continue
            vistos.add(str(path.resolve()))
            items.append(
                {
                    "id": (f"job:{path.parent.name}" if lote == runs_dir
                           else f"batch:current:{lote.name}/{path.parent.name}"),
                    "name": _structure_name(path.parent),
                    "group": "jobs",
                    "format": "cif",
                    "detail": f"{lote.name} · {path.parent.name[:12]}",
                    "mtime": path.stat().st_mtime,
                }
            )

    # Las recientes no repiten lo que ya está arriba: verlas dos veces alarga la
    # lista sin añadir nada.
    for extra in _recent_structures(runs_dir, limit=40):
        ruta = extra.pop("_path", None)
        if ruta and ruta in vistos:
            continue
        items.append(extra)
    return items


def _lote_activo(runs_dir: Path) -> Path | None:
    """El lote que un runner está calculando; si no, el más nuevo con datos.

    Se cae a `runs_dir` para no dejar la sección vacía cuando no hay lotes
    hermanos que inspeccionar.
    """
    try:
        from .activity import runners_activos

        for r in runners_activos():
            batch = r.get("batch")
            if batch is not None and Path(batch).is_dir():
                return Path(batch)
    except Exception:                                  # noqa: BLE001
        pass

    raiz = runs_dir.parent if _BATCH_RE.match(runs_dir.name) else runs_dir
    lotes = [d for d in raiz.glob("batch_*")
             if d.is_dir() and any(d.glob("*/structure.cif"))]
    if lotes:
        return max(lotes, key=lambda d: d.stat().st_mtime)
    return runs_dir if runs_dir.is_dir() else None


def read_structure(runs_dir: Path, ident: str) -> tuple[str, str, dict[str, Any]]:
    """Devuelve (texto CIF, nombre, metadata). Convierte desde JSON de ASE si hace falta."""
    if ident.startswith("job:"):
        job = ident[4:]
        from .jobs import UnsafeJobIdError, resolve_job_dir

        try:
            job_dir = resolve_job_dir(runs_dir, job)
        except UnsafeJobIdError as exc:
            raise UnsafePathError(ident) from exc
        if job_dir is None:
            raise FileNotFoundError(ident)
        cif = job_dir / "structure.cif"
        if not cif.is_file():
            raise FileNotFoundError(ident)
        return (
            cif.read_text(encoding="utf-8", errors="replace"),
            _structure_name(job_dir),
            _structure_metadata(job_dir),
        )

    if ident.startswith("batch:") or ident.startswith("run:"):
        path = _resolve_generated_structure(runs_dir, ident)
        if not path.is_file():
            raise FileNotFoundError(ident)
        return _read_structure_file(path), _structure_name(path.parent), _structure_metadata(path.parent)

    if not ident.startswith("repo:"):
        raise UnsafePathError(ident)

    path = safe_join(structures_dir(), ident[5:], EXT_ESTRUCTURA)
    if not path.is_file():
        raise FileNotFoundError(ident)

    if path.suffix.lower() == ".cif":
        return path.read_text(encoding="utf-8", errors="replace"), path.stem, {}

    # Los structures/*.json son el formato de base de datos de ASE; el visor
    # necesita CIF, así que se convierte al vuelo.
    return _ase_json_a_cif(path), path.stem, {}


def _read_structure_file(path: Path) -> str:
    if path.suffix.lower() == ".cif":
        return path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        return _ase_json_a_cif(path)
    if path.suffix.lower() in {".xyz", ".extxyz"}:
        import io

        from ase.io import read, write

        atoms = read(str(path))
        buf = io.BytesIO()
        write(buf, atoms, format="cif")
        return buf.getvalue().decode("utf-8")
    raise UnsafePathError(str(path))


def _structure_name(job_dir: Path) -> str:
    data = _job_metadata(job_dir)
    formula = data.get("formula") or data.get("reduced_formula")
    if formula:
        return str(formula)
    return job_dir.name[:12]


def _structure_metadata(job_dir: Path) -> dict[str, Any]:
    data = _job_metadata(job_dir)
    if not data:
        return {}

    out = {
        key: data.get(key)
        for key in (
            "candidate_id",
            "formula",
            "reduced_formula",
            "generation_mode",
            "A_site_species",
            "B_site_species",
            "X_site_species",
            "fractions",
            "molecular_A_placeholder",
            "organic_A_warning",
            "screening_passed_tiers",
            "screening_run_id",
            "supercell",
            "n_atoms",
        )
        if key in data
    }
    if out.get("molecular_A_placeholder") and not out.get("organic_A_warning"):
        out["organic_A_warning"] = (
            "MA/FA se representa con un placeholder inorganico en el CIF; "
            "la composicion sigue siendo organica en metadata."
        )
    return out


def _job_metadata(job_dir: Path) -> dict[str, Any]:
    meta = job_dir / "metadata.json"
    if not meta.is_file():
        return {}
    try:
        return json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _passed_ml_tiers(job_dir: Path) -> bool:
    """True si el job viene de la selección final posterior a los tiers ML."""
    data = _job_metadata(job_dir)
    screening_passed = data.get("screening_passed_tiers")
    if screening_passed is True or str(screening_passed).lower() == "true":
        return True

    selection = data.get("selection_row")
    if isinstance(selection, dict):
        source_type = str(selection.get("source_type") or "").lower()
        source_file = str(selection.get("source_file") or "").lower()
        return source_type == "cascade" and "selected_for_dft" in source_file

    return False


def _structure_roots(runs_dir: Path) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    if runs_dir.is_dir():
        roots["current"] = runs_dir.parent if _BATCH_RE.match(runs_dir.name) else runs_dir

    candidates = {
        "phase2": paths.resolve_data("local_runs/phase2_force"),
        "batches": paths.resolve_data("runs/batches"),
        "relax": paths.resolve_data("runs/relax_basic"),
    }
    for key, root in candidates.items():
        if root.is_dir():
            roots.setdefault(key, root)
    return roots


def _recent_structures(runs_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    seen: set[Path] = set()
    found: list[tuple[float, dict[str, Any]]] = []

    for key, root in _structure_roots(runs_dir).items():
        patterns = ["batch_*/*/structure.cif"]
        if not any(_BATCH_RE.match(p.name) for p in root.iterdir() if p.is_dir()):
            patterns.append("*/structure.cif")
        for pattern in patterns:
            for path in root.glob(pattern):
                if not path.is_file():
                    continue
                real = path.resolve()
                if real in seen:
                    continue
                if not _passed_ml_tiers(path.parent):
                    continue
                seen.add(real)
                mtime = path.stat().st_mtime
                try:
                    rel = path.relative_to(root)
                except ValueError:
                    continue
                if len(rel.parts) == 3 and _BATCH_RE.match(rel.parts[0]):
                    ident = f"batch:{key}:{rel.parts[0]}/{rel.parts[1]}"
                    detail = f"{rel.parts[0]} · {rel.parts[1][:12]}"
                elif len(rel.parts) == 2:
                    ident = f"run:{key}:{rel.parts[0]}"
                    detail = rel.parts[0][:12]
                else:
                    continue
                found.append((
                    mtime,
                    {
                        "id": ident,
                        "name": _structure_name(path.parent),
                        "group": "recientes",
                        "format": "cif",
                        "detail": detail,
                        "mtime": mtime,
                        "_path": str(path.resolve()),
                    },
                ))

    found.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in found[:limit]]


def _resolve_generated_structure(runs_dir: Path, ident: str) -> Path:
    try:
        kind, rest = ident.split(":", 1)
        key, rel = rest.split(":", 1)
    except ValueError as exc:
        raise UnsafePathError(ident) from exc

    roots = _structure_roots(runs_dir)
    root = roots.get(key)
    if root is None:
        raise FileNotFoundError(ident)

    parts = Path(rel).parts
    if kind == "batch":
        if len(parts) != 2 or not _BATCH_RE.match(parts[0]) or not _JOB_RE.match(parts[1]):
            raise UnsafePathError(ident)
        return safe_join(root, f"{parts[0]}/{parts[1]}/structure.cif", {".cif"})
    if kind == "run":
        if len(parts) != 1 or not _JOB_RE.match(parts[0]):
            raise UnsafePathError(ident)
        return safe_join(root, f"{parts[0]}/structure.cif", {".cif"})
    raise UnsafePathError(ident)


def _ase_json_a_cif(path: Path) -> str:
    import io

    from ase import Atoms
    from ase.io import write

    data = json.loads(path.read_text())
    entrada = data.get("1") if "1" in data else data
    atoms = Atoms(
        numbers=entrada["numbers"],
        positions=entrada["positions"],
        cell=entrada["cell"],
        pbc=entrada.get("pbc", [True, True, True]),
    )
    # ase.io.cif.write_cif escribe en binario y llama a fd.detach(), así que
    # StringIO no sirve.
    buf = io.BytesIO()
    write(buf, atoms, format="cif")
    return buf.getvalue().decode("utf-8")


# ── Reportes y figuras ───────────────────────────────────────────────────────

def list_reports() -> dict[str, Any]:
    """Reportes Markdown y figuras declaradas en los visualization_manifest.json.

    Cada figura indica si está realmente en disco: los PNG/PDF están en
    .gitignore, así que un manifest completo con cero archivos presentes es el
    estado normal tras un clon, no un error.
    """
    documentos = []
    for base in reports_dirs():
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            documentos.append(
                {
                    "path": str(path.relative_to(paths.data_root())),
                    "name": path.stem,
                    "group": str(path.parent.relative_to(paths.data_root())),
                    "size_bytes": path.stat().st_size,
                }
            )

    galerias = []
    for base in reports_dirs():
        if not base.is_dir():
            continue
        for manifest in sorted(base.rglob("visualization_manifest.json")):
            try:
                data = json.loads(manifest.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            figuras = []
            for rel in data.get("generated_files", []):
                p = paths.data_root() / rel
                if p.suffix.lower() not in EXT_FIGURA:
                    continue
                figuras.append(
                    {"path": rel, "name": Path(rel).stem, "present": p.is_file()}
                )
            galerias.append(
                {
                    "name": str(manifest.parent.relative_to(paths.data_root())),
                    "calculation_dir": data.get("calculation_dir"),
                    "figures": figuras,
                    "n_declared": len(figuras),
                    "n_present": sum(1 for f in figuras if f["present"]),
                }
            )

    return {"documents": documentos, "galleries": galerias}


def _resolver_en_reportes(relative: str, allowed_ext: set[str]) -> Path:
    """Resuelve una ruta como `reports/x.md` contra su propia base.

    La resolución va CONTRA LA BASE, no contra la raíz de datos: `reports/` e
    `imagenes/` pueden ser symlinks a otro volumen —lo son en esta máquina desde
    que los datos se movieron al disco externo— y `safe_join` sigue los enlaces
    con `resolve()`. Compararlos con `data_root` los rechazaba todos con un 400,
    dejando la vista de Resultados sin un solo documento.

    La protección no se debilita: `safe_join` sigue vetando `..`, rutas
    absolutas y symlinks internos que se salgan de la base.
    """
    partes = Path(relative).parts
    if not partes:
        raise UnsafePathError(relative)

    for base in reports_dirs():
        if partes[0] != base.name:
            continue
        resto = str(Path(*partes[1:])) if len(partes) > 1 else ""
        return safe_join(base, resto, allowed_ext)

    raise UnsafePathError(relative)


def read_report(relative: str) -> tuple[str, str]:
    path = _resolver_en_reportes(relative, EXT_REPORTE)
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path.read_text(encoding="utf-8", errors="replace"), path.name


def resolve_figure(relative: str) -> tuple[Path, str]:
    path = _resolver_en_reportes(relative, EXT_FIGURA)
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path, MIME.get(path.suffix.lower(), "application/octet-stream")
