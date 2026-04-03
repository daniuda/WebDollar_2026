import { argon2d } from '@noble/hashes/argon2.js'
import type { MiningJob, MiningResult } from '../types/miner'

const ARGON2_SALT = 'Satoshi_is_Finney'
const ARGON2_OPTS = {
  t: 2,
  m: 256,
  p: 2,
  dkLen: 32,
} as const

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

function fromHex(hex: string): Uint8Array {
  const normalized = hex.trim()
  if (!normalized || normalized.length % 2 !== 0) {
    return new Uint8Array()
  }

  const out = new Uint8Array(normalized.length / 2)
  for (let i = 0; i < out.length; i += 1) {
    out[i] = Number.parseInt(normalized.slice(i * 2, i * 2 + 2), 16)
  }
  return out
}

function compareBytes(left: Uint8Array, right: Uint8Array): number {
  const size = Math.min(left.length, right.length)
  for (let index = 0; index < size; index += 1) {
    if (left[index] < right[index]) return -1
    if (left[index] > right[index]) return 1
  }

  if (left.length < right.length) return -1
  if (left.length > right.length) return 1
  return 0
}

function writeNonce4(buffer: Uint8Array, offset: number, nonce: number) {
  buffer[offset] = nonce >>> 24 & 0xff
  buffer[offset + 1] = nonce >>> 16 & 0xff
  buffer[offset + 2] = nonce >>> 8 & 0xff
  buffer[offset + 3] = nonce & 0xff
}

export async function mineRange(
  job: MiningJob,
  onHash: () => void,
  shouldStop: () => boolean,
): Promise<MiningResult | null> {
  const header = fromHex(job.blockHeader)
  const target = fromHex(job.target)
  if (header.length === 0 || target.length === 0) {
    return null
  }

  const pass = new Uint8Array(header.length + 4)
  pass.set(header, 0)
  const nonceOffset = header.length
  const startedAt = Date.now()
  let hashesTried = 0

  for (let nonce = job.nonceStart; nonce < job.nonceEnd; nonce += 1) {
    if (shouldStop()) return null
    if (Date.now() > job.expireAt) return null

    writeNonce4(pass, nonceOffset, nonce)
    const hash = argon2d(pass, ARGON2_SALT, ARGON2_OPTS)
    hashesTried += 1
    onHash()

    if (compareBytes(hash, target) <= 0) {
      return {
        nonce,
        hashHex: toHex(hash),
        hashesTried,
        timeDiffMs: Date.now() - startedAt,
      }
    }

    if (nonce % 2048 === 0) {
      await new Promise((resolve) => setTimeout(resolve, 0))
    }
  }

  return null
}
