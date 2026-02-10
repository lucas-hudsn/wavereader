import { useState, useEffect } from 'react'
import { fetchBreaks, fetchStates } from '../api'
import useBreakFilters from '../hooks/useBreakFilters'
import SearchBar from '../components/SearchBar'
import StateFilter from '../components/StateFilter'
import SkillFilter from '../components/SkillFilter'
import BreakCard from '../components/BreakCard'
import { BreakCardSkeleton } from '../components/Skeleton'

export default function Landing() {
  const [breaks, setBreaks] = useState([])
  const [states, setStates] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const {
    search, setSearch,
    selectedState, setSelectedState,
    selectedSkill, setSelectedSkill,
    filteredBreaks,
    groupedBreaks,
  } = useBreakFilters(breaks)

  const loadData = async () => {
    try {
      setLoading(true)
      setError(null)
      const [breaksData, statesData] = await Promise.all([
        fetchBreaks(),
        fetchStates(),
      ])
      setBreaks(breaksData)
      setStates(statesData)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  if (error) {
    return (
      <div className="card error-card animate-fade-in">
        <p>Failed to load breaks: {error}</p>
        <button className="retry-btn" onClick={loadData} style={{ marginTop: 12 }}>
          Try Again
        </button>
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      <SearchBar
        value={search}
        onChange={setSearch}
        placeholder="Search breaks... (press / to focus)"
      />

      <div className="dropdown-section">
        <StateFilter
          states={states}
          selectedState={selectedState}
          onChange={setSelectedState}
        />
        <SkillFilter
          selectedSkill={selectedSkill}
          onChange={setSelectedSkill}
        />
      </div>

      {loading ? (
        <div className="breaks-grid">
          {[...Array(6)].map((_, i) => (
            <BreakCardSkeleton key={i} />
          ))}
        </div>
      ) : filteredBreaks.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">~</div>
          <h3>No breaks found</h3>
          <p>Try adjusting your search or filters</p>
        </div>
      ) : (
        groupedBreaks.map(([state, stateBreaks]) => (
          <div key={state} className="animate-fade-in" style={{ marginBottom: 32 }}>
            <div className="section-header">
              <h2>{state}</h2>
              <span className="results-count">{stateBreaks.length} breaks</span>
            </div>
            <div className="breaks-grid">
              {stateBreaks.map((breakData, i) => (
                <BreakCard
                  key={breakData.id}
                  breakData={breakData}
                  animationDelay={i * 50}
                />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
