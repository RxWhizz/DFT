import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

export interface Serie {
  label: string
  values: (number | null)[]
  color: string
}

/**
 * Envoltorio de uPlot para series densas (trazas SCF).
 *
 * uPlot y no una librería de componentes React porque un job largo puede tener
 * cientos de iteraciones por etiqueta y varias etiquetas a la vez; el coste de
 * reconciliar ese número de nodos en el DOM no compensa.
 */
export function LineChart({
  x,
  series,
  height = 200,
  yLabel,
  xLabel,
}: {
  x: number[]
  series: Serie[]
  height?: number
  yLabel?: string
  xLabel?: string
}) {
  const host = useRef<HTMLDivElement>(null)
  const plot = useRef<uPlot | null>(null)

  useEffect(() => {
    if (!host.current || x.length === 0) return

    const opts: uPlot.Options = {
      width: host.current.clientWidth,
      height,
      padding: [8, 12, 0, 0],
      legend: { show: series.length > 1 },
      cursor: { drag: { x: true, y: false } },
      axes: [
        {
          label: xLabel,
          stroke: '#7d8da3',
          grid: { stroke: '#1a222d', width: 1 },
          ticks: { stroke: '#243040' },
          labelSize: xLabel ? 24 : 12,
          font: '11px ui-monospace, monospace',
          labelFont: '11px system-ui, sans-serif',
        },
        {
          label: yLabel,
          stroke: '#7d8da3',
          grid: { stroke: '#1a222d', width: 1 },
          ticks: { stroke: '#243040' },
          size: 64,
          labelSize: yLabel ? 24 : 12,
          font: '11px ui-monospace, monospace',
          labelFont: '11px system-ui, sans-serif',
        },
      ],
      series: [
        { label: xLabel ?? 'x' },
        ...series.map((s) => ({
          label: s.label,
          stroke: s.color,
          width: 1.75,
          points: { show: x.length < 60, size: 4, stroke: s.color, fill: s.color },
        })),
      ],
    }

    const data = [x, ...series.map((s) => s.values)] as uPlot.AlignedData
    plot.current = new uPlot(opts, data, host.current)

    const ro = new ResizeObserver(([entry]) => {
      plot.current?.setSize({ width: entry.contentRect.width, height })
    })
    ro.observe(host.current)

    return () => {
      ro.disconnect()
      plot.current?.destroy()
      plot.current = null
    }
  }, [x, series, height, yLabel, xLabel])

  if (x.length === 0) {
    return (
      <div
        style={{ height }}
        className="flex items-center justify-center rounded border border-ink-800 text-xs text-ink-400"
      >
        Sin datos
      </div>
    )
  }

  return <div ref={host} className="w-full [&_.u-legend]:!text-xs [&_.u-legend]:!text-ink-300" />
}
