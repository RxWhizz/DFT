/** Formato compartido con el backend. */

const SUB: Record<string, string> = {
  '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
  '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
}

/**
 * FA0.75MA0.25PbBr3 → FA₀.₇₅MA₀.₂₅PbBr₃
 *
 * Port de `fmt_formula()` en src/monitor_api/utils.py: solo los dígitos que
 * siguen a una letra pasan a subíndice, y el punto decimal se conserva.
 */
export function fmtFormula(formula: string | null | undefined): string {
  if (!formula) return '—'
  return formula.replace(/(?<=[A-Za-z])(\d+(?:\.\d+)?)/g, (m) =>
    m.replace(/\d/g, (d) => SUB[d] ?? d),
  )
}

/** Duración legible a partir de minutos. */
export function fmtDuration(minutes: number | null | undefined): string {
  if (minutes == null) return '—'
  if (minutes < 1) return `${Math.round(minutes * 60)}s`
  if (minutes < 60) return `${Math.round(minutes)}min`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return m ? `${h}h ${m}min` : `${h}h`
}

export function fmtEnergy(ev: number | null | undefined, digits = 4): string {
  return ev == null ? '—' : `${ev.toFixed(digits)} eV`
}

export function fmtNumber(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : v.toFixed(digits)
}

/** Segundos → "3h 12min" / "45min" / "20s", para las ETA. */
export function fmtEta(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  return fmtDuration(seconds / 60)
}
