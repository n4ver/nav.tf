import { describe, expect, it } from 'vitest'
import { convertToSteamID64, createSteamURL, formatPlayerLabel } from './steam'

describe('convertToSteamID64', () => {
  it('passes SteamID64 through unchanged', () => {
    expect(convertToSteamID64('76561197960287930')).toBe('76561197960287930')
  })

  it('converts SteamID3', () => {
    expect(convertToSteamID64('[U:1:22202]')).toBe('76561197960287930')
  })

  it('converts legacy SteamID2 (case-insensitive)', () => {
    expect(convertToSteamID64('STEAM_0:0:11101')).toBe('76561197960287930')
    expect(convertToSteamID64('steam_1:1:12345')).toBe('76561197960290419')
  })

  it('returns null for empty or unrecognised input', () => {
    expect(convertToSteamID64('')).toBeNull()
    expect(convertToSteamID64(null)).toBeNull()
    expect(convertToSteamID64('player-name')).toBeNull()
  })
})

describe('createSteamURL', () => {
  it('builds a profile URL from any supported id format', () => {
    expect(createSteamURL('[U:1:22202]')).toBe('https://steamcommunity.com/profiles/76561197960287930')
  })

  it('returns null when there is no id', () => {
    expect(createSteamURL('')).toBeNull()
  })
})

describe('formatPlayerLabel', () => {
  it('prefers display name, then persona name, then steam id', () => {
    expect(formatPlayerLabel({ display_name: ' Tomahawk ', steam_id: 'x' })).toBe('Tomahawk')
    expect(formatPlayerLabel({ persona_name: 'Persona', steam_id: 'x' })).toBe('Persona')
    expect(formatPlayerLabel({ display_name: '   ', steam_id: 'STEAM_0:0:1' })).toBe('STEAM_0:0:1')
  })

  it('renders an em dash for missing entries', () => {
    expect(formatPlayerLabel(null)).toBe('—')
    expect(formatPlayerLabel({})).toBe('—')
  })
})
