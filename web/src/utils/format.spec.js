import { describe, expect, it } from 'vitest'
import {
  TF2_CLASSES,
  classesLabel,
  errorMessage,
  formatAccuracy,
  formatDate,
  formatDuration,
  formatMinutes,
  formatNumber,
  matchPath,
  playerPath,
} from './format'

describe('formatNumber', () => {
  it('formats finite numbers to the requested precision', () => {
    expect(formatNumber(3.14159)).toBe('3.14')
    expect(formatNumber(320.55, 1)).toBe('320.6')
  })

  it('accepts numeric strings', () => {
    expect(formatNumber('12')).toBe('12.00')
  })

  it('renders an em dash for missing or non-numeric values', () => {
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber(undefined)).toBe('—')
    expect(formatNumber('')).toBe('—')
    expect(formatNumber('abc')).toBe('—')
    expect(formatNumber(Number.NaN)).toBe('—')
  })
})

describe('formatDate', () => {
  it('returns an em dash for empty values', () => {
    expect(formatDate('')).toBe('—')
    expect(formatDate(null)).toBe('—')
  })

  it('echoes unparseable input instead of "Invalid Date"', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date')
  })

  it('formats valid ISO strings with the locale formatter', () => {
    const iso = '2024-05-01T12:00:00Z'
    expect(formatDate(iso)).toBe(new Date(iso).toLocaleString())
  })
})

describe('formatDuration / formatMinutes', () => {
  it('renders minutes and zero-padded seconds', () => {
    expect(formatDuration(754)).toBe('12m 34s')
    expect(formatDuration(5)).toBe('0m 05s')
  })

  it('treats invalid or negative input as zero', () => {
    expect(formatDuration(undefined)).toBe('0m 00s')
    expect(formatDuration(-30)).toBe('0m 00s')
  })

  it('renders compact minutes', () => {
    expect(formatMinutes(754)).toBe('12m')
    expect(formatMinutes(null)).toBe('0m')
  })
})

describe('formatAccuracy', () => {
  it('converts fractions to percentages', () => {
    expect(formatAccuracy(0.456)).toBe('45.6%')
  })

  it('keeps values already expressed as percentages', () => {
    expect(formatAccuracy(45.6)).toBe('45.6%')
  })

  it('returns an em dash for zero or invalid values', () => {
    expect(formatAccuracy(0)).toBe('—')
    expect(formatAccuracy('abc')).toBe('—')
  })
})

describe('classesLabel', () => {
  it('joins played classes', () => {
    expect(classesLabel(['scout', 'soldier'])).toBe('scout, soldier')
  })

  it('returns an em dash when empty', () => {
    expect(classesLabel([])).toBe('—')
    expect(classesLabel(null)).toBe('—')
  })
})

describe('errorMessage', () => {
  it('uses the Error message when present', () => {
    expect(errorMessage(new Error('boom'), 'fallback')).toBe('boom')
  })

  it('falls back for non-Error values', () => {
    expect(errorMessage('nope', 'fallback')).toBe('fallback')
  })
})

describe('route helpers', () => {
  it('encodes ids into match and player paths', () => {
    expect(matchPath('abc-1')).toBe('/match/abc-1')
    expect(playerPath('[U:1:22]')).toBe('/player/%5BU%3A1%3A22%5D')
  })

  it('lists the nine TF2 classes', () => {
    expect(TF2_CLASSES).toHaveLength(9)
    expect(TF2_CLASSES).toContain('heavyweapons')
  })
})
