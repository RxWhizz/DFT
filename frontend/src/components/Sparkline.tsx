/**
 * Sparkline en SVG puro.
 *
 * Para series pequeñas (métricas de hardware al minuto) no compensa arrancar
 * uPlot: se reserva para las trazas SCF densas de la vista de detalle.
 */
export function Sparkline({
  values,
  width = 96,
  height = 24,
  className = 'text-st-running',
  max,
}: {
  values: number[]
  width?: number
  height?: number
  className?: string
  max?: number
}) {
  if (values.length < 2) {
    return <div style={{ width, height }} className="rounded bg-ink-850" />
  }

  const hi = max ?? Math.max(...values)
  const lo = Math.min(...values, 0)
  const span = hi - lo || 1
  const step = width / (values.length - 1)

  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - lo) / span) * height).toFixed(1)}`)
    .join(' ')

  return (
    <svg width={width} height={height} className={className} aria-hidden>
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
