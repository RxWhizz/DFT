import { useEffect, useRef } from 'react'

/**
 * Visor 3D de estructuras cristalinas sobre 3Dmol.js.
 *
 * Sustituye a los PNG estáticos `cell_3d_*.png` que genera matplotlib: aquí la
 * celda se puede girar, replicar y medir sin volver a lanzar un script.
 */
export function StructureViewer({
  cif,
  style,
  supercell,
  showCell,
  height = 460,
}: {
  cif: string
  style: 'ball-stick' | 'spacefill' | 'stick'
  supercell: number
  showCell: boolean
  height?: number
}) {
  const host = useRef<HTMLDivElement>(null)
  const viewer = useRef<any>(null)

  useEffect(() => {
    let cancelado = false

    async function montar() {
      if (!host.current || !cif) return
      // Import dinámico: 3Dmol pesa ~1 MB y solo hace falta en esta vista.
      const mod: any = await import('3dmol')
      if (cancelado || !host.current) return
      const $3Dmol = mod.default ?? mod

      viewer.current?.clear()
      host.current.innerHTML = ''

      const v = $3Dmol.createViewer(host.current, { backgroundColor: '#0a0d12' })
      viewer.current = v

      v.addModel(cif, 'cif', { doAssembly: true, duplicateAssemblyAtoms: true })

      if (supercell > 1) {
        v.replicateUnitCell(supercell, supercell, supercell)
      }
      if (showCell) {
        v.addUnitCell(v.getModel(), { box: { color: '#3b82f6' } })
      }

      const estilos: Record<string, unknown> = {
        'ball-stick': { stick: { radius: 0.12 }, sphere: { scale: 0.24 } },
        spacefill: { sphere: { scale: 0.8 } },
        stick: { stick: { radius: 0.16 } },
      }
      v.setStyle({}, estilos[style])
      v.zoomTo()
      v.render()
    }

    void montar()
    return () => {
      cancelado = true
      viewer.current?.clear()
      viewer.current = null
    }
  }, [cif, style, supercell, showCell])

  return (
    <div
      ref={host}
      style={{ height, position: 'relative' }}
      className="w-full overflow-hidden rounded border border-ink-800 bg-ink-950"
    />
  )
}
