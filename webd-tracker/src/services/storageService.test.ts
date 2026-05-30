import { describe, it, expect, beforeEach } from 'vitest'
import { getEntries, saveEntry, deleteEntry } from './storageService'

beforeEach(() => {
  localStorage.clear()
})

describe('storageService', () => {
  it('returns empty array when no entries', () => {
    expect(getEntries()).toEqual([])
  })

  it('saves and retrieves an entry', () => {
    const entry = {
      address: 'WEBD$abc123',
      label: 'Test wallet',
      balance: 1000,
      lastBlock: 5000000,
      lastUpdated: '2026-05-29T10:00:00Z',
    }
    saveEntry(entry)
    const entries = getEntries()
    expect(entries).toHaveLength(1)
    expect(entries[0].address).toBe('WEBD$abc123')
  })

  it('updates existing entry by address', () => {
    const entry = { address: 'WEBD$abc', label: 'A', balance: 100, lastBlock: 1, lastUpdated: '' }
    saveEntry(entry)
    saveEntry({ ...entry, balance: 200, lastBlock: 2 })
    const entries = getEntries()
    expect(entries).toHaveLength(1)
    expect(entries[0].balance).toBe(200)
  })

  it('deletes entry by address', () => {
    saveEntry({ address: 'WEBD$abc', label: 'A', balance: 0, lastBlock: 0, lastUpdated: '' })
    deleteEntry('WEBD$abc')
    expect(getEntries()).toHaveLength(0)
  })

  it('ignores delete of non-existent address', () => {
    expect(() => deleteEntry('WEBD$notexist')).not.toThrow()
  })
})
