import { SKILL_LEVELS } from '../constants'

export default function SkillFilter({ selectedSkill, onChange }) {
  return (
    <div className="dropdown-group">
      <label htmlFor="skill-select">Skill level</label>
      <select
        id="skill-select"
        value={selectedSkill}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">All levels</option>
        {SKILL_LEVELS.map(skill => (
          <option key={skill} value={skill}>{skill}</option>
        ))}
      </select>
    </div>
  )
}
