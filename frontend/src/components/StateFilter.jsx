export default function StateFilter({ states, selectedState, onChange }) {
  return (
    <div className="dropdown-group">
      <label htmlFor="state-select">State</label>
      <select
        id="state-select"
        value={selectedState}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">All states</option>
        {states.map(state => (
          <option key={state} value={state}>{state}</option>
        ))}
      </select>
    </div>
  )
}
