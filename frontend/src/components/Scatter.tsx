import { useMemo, useState } from 'react'

export interface Punto {
  x: number
  y: number
  label: string
  value?: number | null
  dim?: boolean
}

export interface Banda {
  min: number
  max: number
}

/**
 * Scatter en SVG con zonas de aceptación.
 *
 * Se dibuja a mano en vez de con una librería porque lo que aporta valor aquí
 * es superponer las cotas de los filtros de config/generator.yaml sobre la
 * nube de candidatos — no las utilidades genéricas de una librería de charts.
 */
export function Scatter({
  puntos,
  bandaX,
  bandaY,
  xLabel,
  yLabel,
  height = 340,
}: {
  puntos: Punto[]
  bandaX?: Banda
  bandaY?: Banda
  xLabel: string
  yLabel: string
  height?: number
}) {
  const [hover, setHover] = useState<Punto | null>(null)

  const { xs, ys, escalaX, escalaY, W, H, pad } = useMemo(() => {
    const W = 640
    const H = height
    const pad = { t: 12, r: 12, b: 40, l: 56 }

    const xv = puntos.map((p) => p.x)
    const yv = puntos.map((p) => p.y)
    const x0 = Math.min(...xv, bandaX?.min ?? Infinity)
    const x1 = Math.max(...xv, bandaX?.max ?? -Infinity)
    const y0 = Math.min(...yv, bandaY?.min ?? Infinity)
    const y1 = Math.max(...yv, bandaY?.max ?? -Infinity)

    const mx = (x1 - x0) * 0.06 || 0.05
    const my = (y1 - y0) * 0.06 || 0.05
    const xa = x0 - mx
    const xb = x1 + mx
    const ya = y0 - my
    const yb = y1 + my

    const escalaX = (v: number) => pad.l + ((v - xa) / (xb - xa)) * (W - pad.l - pad.r)
    const escalaY = (v: number) => H - pad.b - ((v - ya) / (yb - ya)) * (H - pad.t - pad.b)

    const ticks = (a: number, b: number) =>
      Array.from({ length: 5 }, (_, i) => a + ((b - a) * i) / 4)

    return { xs: ticks(xa, xb), ys: ticks(ya, yb), escalaX, escalaY, W, H, pad }
  }, [puntos, bandaX, bandaY, height])

  if (!puntos.length) {
    return (
      <div
        style={{ height }}
        className="flex items-center justify-center rounded border border-ink-800 text-sm text-ink-400"
      >
        Sin candidatos que mostrar
      </div>
    )
  }

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${xLabel} vs ${yLabel}`}>
        {/* Zona de aceptación de los filtros físicos */}
        {bandaX && bandaY && (
          <rect
            x={escalaX(bandaX.min)}
            y={escalaY(bandaY.max)}
            width={escalaX(bandaX.max) - escalaX(bandaX.min)}
            height={escalaY(bandaY.min) - escalaY(bandaY.max)}
            fill="#22c55e"
            opacity={0.07}
            stroke="#22c55e"
            strokeOpacity={0.3}
            strokeDasharray="4 3"
          />
        )}

        {/* Rejilla y ejes */}
        {xs.map((v) => (
          <g key={`x${v}`}>
            <line
              x1={escalaX(v)}
              x2={escalaX(v)}
              y1={pad.t}
              y2={H - pad.b}
              stroke="#1a222d"
            />
            <text
              x={escalaX(v)}
              y={H - pad.b + 16}
              textAnchor="middle"
              className="fill-ink-400 text-[10px]"
              style={{ fontFamily: 'ui-monospace, monospace' }}
            >
              {v.toFixed(2)}
            </text>
          </g>
        ))}
        {ys.map((v) => (
          <g key={`y${v}`}>
            <line x1={pad.l} x2={W - pad.r} y1={escalaY(v)} y2={escalaY(v)} stroke="#1a222d" />
            <text
              x={pad.l - 8}
              y={escalaY(v) + 3}
              textAnchor="end"
              className="fill-ink-400 text-[10px]"
              style={{ fontFamily: 'ui-monospace, monospace' }}
            >
              {v.toFixed(2)}
            </text>
          </g>
        ))}

        {puntos.map((p, i) => (
          <circle
            key={i}
            cx={escalaX(p.x)}
            cy={escalaY(p.y)}
            r={hover === p ? 5.5 : 3.5}
            fill={p.dim ? '#475569' : colorPorScore(p.value)}
            fillOpacity={p.dim ? 0.5 : 0.85}
            stroke={hover === p ? '#e6ecf5' : 'none'}
            strokeWidth={1}
            onMouseEnter={() => setHover(p)}
            onMouseLeave={() => setHover(null)}
            className="cursor-pointer"
          />
        ))}

        <text
          x={(W + pad.l) / 2}
          y={H - 6}
          textAnchor="middle"
          className="fill-ink-400 text-[11px]"
        >
          {xLabel}
        </text>
        <text
          x={-H / 2}
          y={13}
          transform="rotate(-90)"
          textAnchor="middle"
          className="fill-ink-400 text-[11px]"
        >
          {yLabel}
        </text>
      </svg>

      {hover && (
        <div className="pointer-events-none absolute left-3 top-3 rounded border border-ink-700 bg-ink-950/95 px-2.5 py-1.5 text-xs shadow-lg">
          <div className="font-medium">{hover.label}</div>
          <div className="tnum text-ink-400">
            {xLabel} {hover.x.toFixed(3)} · {yLabel} {hover.y.toFixed(3)}
            {hover.value != null && ` · score ${hover.value.toFixed(3)}`}
          </div>
        </div>
      )}
    </div>
  )
}

/** Verde = score alto, ámbar = medio, gris = bajo. */
function colorPorScore(v: number | null | undefined): string {
  if (v == null) return '#64748b'
  if (v >= 0.9) return '#22c55e'
  if (v >= 0.75) return '#84cc16'
  if (v >= 0.5) return '#f59e0b'
  return '#64748b'
}
