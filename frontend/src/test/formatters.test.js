import { capitalize } from '../utils/formatters'
import { describe, it, expect } from 'vitest'

describe('capitalize', () => {
  it('capitalizes the first letter', () => {
    expect(capitalize('hello')).toBe('Hello')
  })

  it('returns dash for empty string', () => {
    expect(capitalize('')).toBe('-')
  })

  it('returns dash for null', () => {
    expect(capitalize(null)).toBe('-')
  })

  it('returns dash for undefined', () => {
    expect(capitalize(undefined)).toBe('-')
  })

  it('handles single character', () => {
    expect(capitalize('a')).toBe('A')
  })
})
