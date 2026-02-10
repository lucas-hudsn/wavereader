import { useParams, Link } from 'react-router-dom'
import DOMPurify from 'dompurify'
import { useFavorites } from '../context/FavoritesContext'
import { capitalize } from '../utils/formatters'
import useBreakDetail from '../hooks/useBreakDetail'
import WeatherChart from '../components/WeatherChart'
import { BreakDetailSkeleton } from '../components/Skeleton'

function formatForecast(text) {
  if (!text) return ''
  const raw = text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
  return DOMPurify.sanitize(raw, { ALLOWED_TAGS: ['strong', 'br'] })
}

export default function BreakDetail() {
  const { breakName } = useParams()
  const decodedBreakName = decodeURIComponent(breakName)
  const { data, loading, error, retry } = useBreakDetail(decodedBreakName)
  const { isFavorite, toggleFavorite } = useFavorites()

  if (loading) {
    return (
      <div>
        <Link to="/" className="back-link">
          ← back to all breaks
        </Link>
        <BreakDetailSkeleton />
      </div>
    )
  }

  if (error) {
    return (
      <div>
        <Link to="/" className="back-link">
          ← back to all breaks
        </Link>
        <div className="card error-card animate-fade-in">
          <p>Failed to load break: {error}</p>
          <button className="retry-btn" onClick={retry} style={{ marginTop: 12 }}>
            Try Again
          </button>
        </div>
      </div>
    )
  }

  const favorite = isFavorite(data.name)

  return (
    <div>
      <Link to="/" className="back-link">
        ← back to all breaks
      </Link>

      <div className="card animate-fade-in stagger-1">
        <div className="break-header">
          <h2>{data.name}</h2>
          <button
            className={`favorite-btn ${favorite ? 'active' : ''}`}
            onClick={() => toggleFavorite(data.name)}
            aria-label={favorite ? 'Remove from favorites' : 'Add to favorites'}
            style={{ position: 'static', fontSize: '1.5em' }}
          >
            {favorite ? '★' : '☆'}
          </button>
        </div>

        {data.description && (
          <div className="description-box">{data.description}</div>
        )}

        <div className="details-grid">
          <div className="detail-item">
            <span className="detail-label">State</span>
            <span className="detail-value">{data.state || '-'}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Coordinates</span>
            <span className="detail-value">
              {data.latitude && data.longitude
                ? `${data.latitude.toFixed(4)}, ${data.longitude.toFixed(4)}`
                : '-'}
            </span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Wave Direction</span>
            <span className="detail-value">{capitalize(data.wave_direction)}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Bottom</span>
            <span className="detail-value">{capitalize(data.bottom_type)}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Break Type</span>
            <span className="detail-value">{capitalize(data.break_type)}</span>
          </div>
          <div className="detail-item">
            <span className="detail-label">Skill Level</span>
            <span className="detail-value">{capitalize(data.skill_level)}</span>
          </div>
        </div>
      </div>

      <div className="card conditions-card animate-fade-in stagger-2" style={{ marginTop: 20 }}>
        <h3>Ideal Conditions</h3>
        <div className="conditions-grid">
          <div className="condition-item">
            <span className="condition-label">Wind</span>
            <span className="condition-value">{data.ideal_wind || '-'}</span>
          </div>
          <div className="condition-item">
            <span className="condition-label">Tide</span>
            <span className="condition-value">{data.ideal_tide || '-'}</span>
          </div>
          <div className="condition-item">
            <span className="condition-label">Swell Size</span>
            <span className="condition-value">{data.ideal_swell_size || '-'}</span>
          </div>
        </div>
      </div>

      {data.weather_data?.hourly && (
        <div style={{ marginTop: 20 }}>
          <WeatherChart hourlyData={data.weather_data.hourly} />
        </div>
      )}

      <div className="card forecast-card animate-fade-in stagger-4" style={{ marginTop: 20 }}>
        <h3>Daily Surf Report</h3>
        {data.forecast ? (
          <div
            className="forecast-text"
            dangerouslySetInnerHTML={{ __html: formatForecast(data.forecast) }}
          />
        ) : (
          <p style={{ color: 'var(--text-secondary)' }}>
            Forecast unavailable
          </p>
        )}
      </div>
    </div>
  )
}
