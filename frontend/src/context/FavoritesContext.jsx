import { createContext, useContext, useState, useEffect } from 'react'

const FavoritesContext = createContext()

const STORAGE_KEY = 'wavereader_favorites'

export function FavoritesProvider({ children }) {
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

  const addFavorite = (breakName) => {
    setFavorites(prev => {
      if (prev.includes(breakName)) return prev
      return [...prev, breakName]
    })
  }

  const removeFavorite = (breakName) => {
    setFavorites(prev => prev.filter(name => name !== breakName))
  }

  const toggleFavorite = (breakName) => {
    if (favorites.includes(breakName)) {
      removeFavorite(breakName)
    } else {
      addFavorite(breakName)
    }
  }

  const isFavorite = (breakName) => favorites.includes(breakName)

  return (
    <FavoritesContext.Provider value={{ favorites, addFavorite, removeFavorite, toggleFavorite, isFavorite }}>
      {children}
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
