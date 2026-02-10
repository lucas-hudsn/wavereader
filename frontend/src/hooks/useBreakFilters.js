import { useState, useMemo } from 'react'

export default function useBreakFilters(breaks) {
  const [search, setSearch] = useState('')
  const [selectedState, setSelectedState] = useState('')
  const [selectedSkill, setSelectedSkill] = useState('')

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

  return {
    search, setSearch,
    selectedState, setSelectedState,
    selectedSkill, setSelectedSkill,
    filteredBreaks,
    groupedBreaks,
  }
}
