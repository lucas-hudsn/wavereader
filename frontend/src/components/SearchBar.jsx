import { useRef, useEffect } from 'react'

export default function SearchBar({ value, onChange, placeholder = 'Search breaks...' }) {
  const inputRef = useRef(null)

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === '/' && document.activeElement !== inputRef.current) {
        e.preventDefault()
        inputRef.current?.focus()
      }
      if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        inputRef.current?.blur()
        onChange('')
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onChange])

  return (
    <div className="search-container">
      <label htmlFor="search-breaks" className="sr-only">Search surf breaks</label>
      <span className="search-icon">/</span>
      <input
        ref={inputRef}
        id="search-breaks"
        type="text"
        className="search-input"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button className="search-clear" onClick={() => onChange('')} aria-label="Clear search">
          x
        </button>
      )}
    </div>
  )
}
