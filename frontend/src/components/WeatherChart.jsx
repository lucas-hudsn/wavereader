import { useState, useRef, useMemo } from 'react'

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function processHourlyData(hourlyData) {
  const times = hourlyData.time || []
  const waveHeights = hourlyData.wave_height || []
  const windSpeeds = hourlyData.wind_speed || []
  const windDirections = hourlyData.wind_direction || []

  const dailyData = []
  for (let day = 0; day < 7; day++) {
    const startIdx = day * 24
    const endIdx = Math.min(startIdx + 24, times.length)
    if (startIdx >= times.length) break

    const dayWaves = waveHeights.slice(startIdx, endIdx).filter(v => v != null)
    const dayWinds = windSpeeds.slice(startIdx, endIdx).filter(v => v != null)
    const dayWindDirs = windDirections.slice(startIdx, endIdx).filter(v => v != null)

    dailyData.push({
      time: times[startIdx],
      waveHeight: dayWaves.length > 0 ? Math.max(...dayWaves) : null,
      avgWaveHeight: dayWaves.length > 0 ? dayWaves.reduce((a, b) => a + b) / dayWaves.length : null,
      avgWindSpeed: dayWinds.length > 0 ? dayWinds.reduce((a, b) => a + b) / dayWinds.length : null,
      maxWindSpeed: dayWinds.length > 0 ? Math.max(...dayWinds) : null,
      windDir: dayWindDirs.length > 0 ? dayWindDirs[Math.floor(dayWindDirs.length / 2)] : null,
    })
  }
  return dailyData
}

function getWindDirection(degrees) {
  if (degrees == null) return ''
  const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  const index = Math.round(degrees / 45) % 8
  return directions[index]
}

const CHART_HEIGHT = 120
const PADDING = { top: 20, bottom: 20, left: 5, right: 5 }
const INNER_HEIGHT = CHART_HEIGHT - PADDING.top - PADDING.bottom

export default function WeatherChart({ hourlyData }) {
  const [tooltip, setTooltip] = useState({ visible: false, content: '', x: 0, y: 0 })
  const swellContainerRef = useRef(null)
  const windContainerRef = useRef(null)

  const dailyData = useMemo(() => hourlyData ? processHourlyData(hourlyData) : [], [hourlyData])
  const maxWaveHeight = useMemo(() => Math.max(...dailyData.map(d => d.waveHeight).filter(v => v != null), 1), [dailyData])
  const maxWindSpeed = useMemo(() => Math.max(...dailyData.map(d => d.maxWindSpeed).filter(v => v != null), 1), [dailyData])

  const { points, linePath, areaPath } = useMemo(() => {
    if (dailyData.length === 0) return { points: [], linePath: '', areaPath: '' }
    const pts = dailyData.map((d, i) => {
      const x = PADDING.left + (i / Math.max(dailyData.length - 1, 1)) * (100 - PADDING.left - PADDING.right)
      const normalizedValue = d.waveHeight != null ? d.waveHeight / maxWaveHeight : 0
      const y = PADDING.top + INNER_HEIGHT - (normalizedValue * INNER_HEIGHT)
      return { x, y, value: d.waveHeight, time: d.time }
    })
    const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
    const area = `${line} L ${pts[pts.length - 1].x} ${CHART_HEIGHT - PADDING.bottom} L ${pts[0].x} ${CHART_HEIGHT - PADDING.bottom} Z`
    return { points: pts, linePath: line, areaPath: area }
  }, [dailyData, maxWaveHeight])

  if (!hourlyData) return null

  const today = new Date().toDateString()

  const handleSwellHover = (point) => {
    if (!swellContainerRef.current) return
    const rect = swellContainerRef.current.getBoundingClientRect()
    const date = new Date(point.time)
    const dayName = DAY_NAMES[date.getDay()]
    const dateStr = `${date.getDate()}/${date.getMonth() + 1}`

    setTooltip({
      visible: true,
      content: `${dayName} ${dateStr}: ${point.value?.toFixed(1)}m max`,
      x: (point.x / 100) * rect.width,
      y: (point.y / 100) * rect.height - 35,
    })
  }

  const handleWindHover = (data, index) => {
    if (!windContainerRef.current) return
    const rect = windContainerRef.current.getBoundingClientRect()
    const barWidth = rect.width / dailyData.length
    const date = new Date(data.time)
    const dayName = DAY_NAMES[date.getDay()]
    const dateStr = `${date.getDate()}/${date.getMonth() + 1}`
    const dirLabel = getWindDirection(data.windDir)

    setTooltip({
      visible: true,
      content: `${dayName} ${dateStr}: ${Math.round(data.avgWindSpeed || 0)} km/h avg ${dirLabel}`,
      x: (index + 0.5) * barWidth,
      y: -25,
    })
  }

  const hideTooltip = () => setTooltip({ ...tooltip, visible: false })

  return (
    <div className="card chart-card animate-fade-in stagger-3">
      <h3>7-Day Forecast</h3>

      <div className="chart-section">
        <div className="chart-label">Wave Height (max per day)</div>
        <div className="swell-chart-container" ref={swellContainerRef}>
          <div className={`chart-tooltip ${tooltip.visible ? 'visible' : ''}`} style={{ left: tooltip.x, top: tooltip.y }}>
            {tooltip.content}
          </div>
          <svg viewBox={`0 0 100 ${CHART_HEIGHT}`} preserveAspectRatio="none">
            <path className="swell-area" d={areaPath} />
            <path className="swell-line" d={linePath} />
            {points.map((p, i) => (
              <circle
                key={i}
                className="swell-point"
                cx={p.x}
                cy={p.y}
                r="4"
                onMouseEnter={() => handleSwellHover(p)}
                onMouseLeave={hideTooltip}
              />
            ))}
          </svg>
        </div>
      </div>

      <div className="chart-section">
        <div className="chart-label">Wind Speed & Direction</div>
        <div className="wind-chart-container" ref={windContainerRef}>
          {dailyData.map((d, i) => {
            const speedRatio = d.avgWindSpeed != null ? d.avgWindSpeed / maxWindSpeed : 0
            const arrowSize = 16 + speedRatio * 20
            const heightPct = 25 + speedRatio * 70
            const rotation = d.windDir != null ? d.windDir : 0

            return (
              <div
                key={i}
                className="wind-bar"
                onMouseEnter={() => handleWindHover(d, i)}
                onMouseLeave={hideTooltip}
              >
                <div className="wind-arrow-container" style={{ height: `${heightPct}%` }}>
                  <span
                    className="wind-arrow"
                    style={{ fontSize: `${arrowSize}px`, transform: `rotate(${rotation}deg)` }}
                  >
                    ↓
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="chart-times">
        {dailyData.map((d, i) => {
          const date = new Date(d.time)
          const isToday = date.toDateString() === today
          return (
            <div key={i} className={`chart-time ${isToday ? 'today' : ''}`}>
              {DAY_NAMES[date.getDay()]}
            </div>
          )
        })}
      </div>
    </div>
  )
}
