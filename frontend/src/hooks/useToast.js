import { useState } from 'react'

export default function useToast() {
  const [toast, setToast] = useState({ message: '', visible: false })

  const show = (message) => setToast({ message, visible: true })
  const hide = () => setToast(prev => ({ ...prev, visible: false }))

  return { toast, show, hide }
}
