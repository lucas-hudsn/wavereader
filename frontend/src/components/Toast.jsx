import { useEffect } from 'react'

export default function Toast({ message, visible, onHide }) {
  useEffect(() => {
    if (visible) {
      const timer = setTimeout(onHide, 2000)
      return () => clearTimeout(timer)
    }
  }, [visible, onHide])

  if (!visible) return null

  return (
    <div className="toast" role="status" aria-live="polite">
      {message}
    </div>
  )
}
