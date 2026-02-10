import { Link } from 'react-router-dom'
import { useFavorites } from '../context/FavoritesContext'
import { capitalize } from '../utils/formatters'

export default function BreakCard({ breakData, animationDelay = 0 }) {
  const { isFavorite, toggleFavorite } = useFavorites()
  const favorite = isFavorite(breakData.name)
  const stateSlug = encodeURIComponent(breakData.state)
  const breakSlug = encodeURIComponent(breakData.name)

  const handleFavoriteClick = (e) => {
    e.preventDefault()
    e.stopPropagation()
    toggleFavorite(breakData.name)
  }

  return (
    <Link
      to={`/${stateSlug}/${breakSlug}`}
      className="break-card animate-fade-in"
      style={{ animationDelay: `${animationDelay}ms`, textDecoration: 'none', color: 'inherit' }}
    >
      <button
        className={`favorite-btn ${favorite ? 'active' : ''}`}
        onClick={handleFavoriteClick}
        aria-label={favorite ? 'Remove from favorites' : 'Add to favorites'}
      >
        {favorite ? '★' : '☆'}
      </button>
      <h3>{breakData.name}</h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.9em' }}>
        {breakData.state}
      </p>
      <div className="break-card-meta">
        {breakData.skill_level && (
          <span className={`break-card-tag skill-${breakData.skill_level}`}>
            {capitalize(breakData.skill_level)}
          </span>
        )}
      </div>
    </Link>
  )
}
