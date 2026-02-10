import { useState, useEffect, useMemo } from 'react'
import { fetchBreaks, fetchStates } from '../api'
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

  const [search, setSearch] = useState('')
  const [selectedState, setSelectedState] = useState('')
  const [selectedSkill, setSelectedSkill] = useState('')

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true)
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
    loadData()
  }, [])

  const filteredBreaks = useMemo(() => {
    return breaks.filter(b => {
      const matchesSearch = !search ||
        b.name.toLowerCase().includes(search.toLowerCase()) ||
        b.state.toLowerCase().includes(search.toLowerCase())
      const matchesState = !selectedState || b.state === selectedState
      const matchesSkill = !selectedSkill || b.skill_level === selectedSkill
      return matchesSearch && matchesState && matchesSkill
    })
  }, [breaks, search, selectedState, selectedSkill])

  const groupedBreaks = useMemo(() => {
    const groups = {}
    filteredBreaks.forEach(b => {
      if (!groups[b.state]) groups[b.state] = []
      groups[b.state].push(b)
    })
    return Object.entries(groups).sort((a, b) => a[0].localeCompare(b[0]))
  }, [filteredBreaks])

  if (error) {
    return (
      <div className="card error-card animate-fade-in">
        <p>Failed to load breaks: {error}</p>
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
