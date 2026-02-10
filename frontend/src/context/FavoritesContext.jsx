import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import { STORAGE_KEY } from '../constants'
import Toast from '../components/Toast'
import useToast from '../hooks/useToast'

const FavoritesContext = createContext()

export function FavoritesProvider({ children }) {
  const { toast, show: showToast, hide: hideToast } = useToast()

  const [favorites, setFavorites] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      return stored ? JSON.parse(stored) : []
    } catch {
      return []
    }
  })

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(favorites))
  }, [favorites])

  const addFavorite = useCallback((breakName) => {
    setFavorites(prev => {
      if (prev.includes(breakName)) return prev
      return [...prev, breakName]
    })
  }, [])

  const removeFavorite = useCallback((breakName) => {
    setFavorites(prev => prev.filter(name => name !== breakName))
  }, [])

  const toggleFavorite = useCallback((breakName) => {
    setFavorites(prev => {
      const removing = prev.includes(breakName)
      showToast(removing ? `Removed ${breakName} from favorites` : `Added ${breakName} to favorites`)
      return removing
        ? prev.filter(name => name !== breakName)
        : [...prev, breakName]
    })
  }, [showToast])

  const isFavorite = useCallback((breakName) => favorites.includes(breakName), [favorites])

  const value = useMemo(
    () => ({ favorites, addFavorite, removeFavorite, toggleFavorite, isFavorite }),
    [favorites, addFavorite, removeFavorite, toggleFavorite, isFavorite]
  )

  return (
    <FavoritesContext.Provider value={value}>
      {children}
      <Toast message={toast.message} visible={toast.visible} onHide={hideToast} />
    </FavoritesContext.Provider>
  )
}

export function useFavorites() {
  const context = useContext(FavoritesContext)
  if (!context) {
    throw new Error('useFavorites must be used within a FavoritesProvider')
  }
  return context
}
