import { useNavigate } from 'react-router-dom'
import { useFavorites } from '../context/FavoritesContext'

function capitalize(str) {
  if (!str) return str
  return str.charAt(0).toUpperCase() + str.slice(1)
}

export default function BreakCard({ breakData, animationDelay = 0 }) {
  const navigate = useNavigate()
  const { isFavorite, toggleFavorite } = useFavorites()
  const favorite = isFavorite(breakData.name)

  const handleClick = () => {
    const stateSlug = encodeURIComponent(breakData.state)
    const breakSlug = encodeURIComponent(breakData.name)
    navigate(`/${stateSlug}/${breakSlug}`)
  }

  const handleFavoriteClick = (e) => {
    e.stopPropagation()
    toggleFavorite(breakData.name)
  }

  return (
    <div
      className="break-card animate-fade-in"
      style={{ animationDelay: `${animationDelay}ms` }}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && handleClick()}
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
    </div>
  )
}
