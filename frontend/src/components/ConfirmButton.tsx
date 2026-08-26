import { useEffect, useRef, useState } from 'react'

/**
 * Botón de dos pasos para acciones destructivas.
 *
 * Un solo clic no basta para matar procesos o relanzar un runner; y un modal
 * para esto interrumpe más de lo que protege. La confirmación caduca sola a los
 * 4 s para no dejar el botón «armado» si el usuario se distrae.
 */
export function ConfirmButton({
  onConfirm,
  children,
  confirmLabel = '¿Seguro?',
  className = 'btn',
  disabled,
  pending,
}: {
  onConfirm: () => void
  children: React.ReactNode
  confirmLabel?: string
  className?: string
  disabled?: boolean
  pending?: boolean
}) {
  const [armado, setArmado] = useState(false)
  const timer = useRef<number | null>(null)

  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current) }, [])

  function click() {
    if (armado) {
      if (timer.current) window.clearTimeout(timer.current)
      setArmado(false)
      onConfirm()
      return
    }
    setArmado(true)
    timer.current = window.setTimeout(() => setArmado(false), 4000)
  }

  return (
    <button
      onClick={click}
      disabled={disabled || pending}
      className={armado ? `${className} border-st-failed/60 bg-st-failed/20 text-red-200` : className}
    >
      {pending ? '…' : armado ? confirmLabel : children}
    </button>
  )
}
