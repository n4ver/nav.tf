import { describe, expect, it } from 'vitest'
import { formatRating, ratingTone, sortByRatingDesc, toRating } from './rating'

describe('toRating', () => {
  it('parses numeric input', () => {
    expect(toRating('1.25')).toBe(1.25)
    expect(toRating(0)).toBe(0)
  })

  it('returns null for non-finite input', () => {
    expect(toRating('abc')).toBeNull()
    expect(toRating(Infinity)).toBeNull()
    expect(toRating(undefined)).toBeNull()
  })

  it('treats null and empty string as missing rather than zero', () => {
    expect(toRating(null)).toBeNull()
    expect(toRating('')).toBeNull()
  })
})

describe('formatRating', () => {
  it('formats to three decimals by default', () => {
    expect(formatRating(1)).toBe('1.000')
    expect(formatRating(1.23456, 2)).toBe('1.23')
  })

  it('renders an em dash for missing ratings', () => {
    expect(formatRating(null)).toBe('—')
  })
})

describe('ratingTone', () => {
  it.each([
    [0.5, 'low'],
    [0.85, 'mid'],
    [1, 'mid'],
    [1.15, 'mid'],
    [1.5, 'high'],
    [null, 'unknown'],
  ])('maps %s to %s', (value, tone) => {
    expect(ratingTone(value)).toBe(tone)
  })
})

describe('sortByRatingDesc', () => {
  it('sorts highest first, treating missing ratings as neutral, without mutating input', () => {
    // Arrange
    const rows = [{ id: 'a', rating: 0.8 }, { id: 'b' }, { id: 'c', rating: 1.4 }]

    // Act
    const sorted = sortByRatingDesc(rows)

    // Assert
    expect(sorted.map((row) => row.id)).toEqual(['c', 'b', 'a'])
    expect(rows[0].id).toBe('a')
  })

  it('supports a custom key and tolerates null input', () => {
    expect(sortByRatingDesc([{ r: 1 }, { r: 2 }], 'r')[0].r).toBe(2)
    expect(sortByRatingDesc(null)).toEqual([])
  })
})
