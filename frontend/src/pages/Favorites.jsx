import { useState, useEffect, useCallback } from 'react'
import { useFavorites } from '../context/FavoritesContext'
import { fetchBreaks } from '../api'
import BreakCard from '../components/BreakCard'
import { BreakCardSkeleton } from '../components/Skeleton'

export default function Favorites() {
  const { favorites } = useFavorites()
  const [breaks, setBreaks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadBreaks = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const allBreaks = await fetchBreaks()
      setBreaks(allBreaks.filter(b => favorites.includes(b.name)))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [favorites])

  useEffect(() => {
    document.title = 'Favorites | wavereader'
    loadBreaks()
    return () => { document.title = 'wavereader' }
  }, [loadBreaks])

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="section-header">
          <h2>Favorites</h2>
        </div>
        <div className="breaks-grid">
          {[...Array(3)].map((_, i) => (
            <BreakCardSkeleton key={i} />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="animate-fade-in">
        <div className="section-header">
          <h2>Favorites</h2>
        </div>
        <div className="card error-card animate-fade-in">
          <p>Failed to load favorites: {error}</p>
          <button className="retry-btn" onClick={loadBreaks} style={{ marginTop: 12 }}>
            Try Again
          </button>
        </div>
      </div>
    )
  }

  if (favorites.length === 0) {
    return (
      <div className="animate-fade-in">
        <div className="section-header">
          <h2>Favorites</h2>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon">☆</div>
          <h3>No favorites yet</h3>
          <p>Click the star on any break to add it to your favorites</p>
        </div>
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      <div className="section-header">
        <h2>Favorites</h2>
        <span className="results-count">{breaks.length} breaks</span>
      </div>
      <div className="breaks-grid">
        {breaks.map((breakData, i) => (
          <BreakCard
            key={breakData.id}
            breakData={breakData}
            animationDelay={i * 50}
          />
        ))}
      </div>
    </div>
  )
}
