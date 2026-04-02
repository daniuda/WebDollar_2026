import { sha256 } from '@noble/hashes/sha2.js'
import type { MiningJob } from '../types/miner'

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

function concatBytes(...chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((sum, c) => sum + c.length, 0)
  const out = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    out.set(chunk, offset)
    offset += chunk.length
  }
  return out
}

function longToBytes(value: number): Uint8Array {
  let v = BigInt(value)
  const out = new Uint8Array(8)
  for (let i = 7; i >= 0; i -= 1) {
    out[i] = Number(v & 0xffn)
    v >>= 8n
  }
  return out
}

function targetLeadingZeros(target: string): number {
  const zeros = (target.match(/^(0+)/)?.[1]?.length ?? 0)
  return Math.max(1, Math.floor(zeros / 2))
}

function meetsTarget(hashHex: string, requiredZeros: number): boolean {
  return hashHex.slice(0, requiredZeros).split('').every((ch) => ch === '0')
}

export async function mineRange(
  job: MiningJob,
  onHash: () => void,
  shouldStop: () => boolean,
): Promise<{ nonce: number; hashHex: string } | null> {
  const header = new TextEncoder().encode(job.blockHeader)
  const requiredZeros = targetLeadingZeros(job.target)

  for (let nonce = job.nonceStart; nonce < job.nonceEnd; nonce += 1) {
    if (shouldStop()) return null
    if (Date.now() > job.expireAt) return null

    const input = concatBytes(header, longToBytes(nonce))
    const hash1 = sha256(input)
    const hash2 = sha256(hash1)
    const hashHex = toHex(hash2)
    onHash()

    if (meetsTarget(hashHex, requiredZeros)) {
      return { nonce, hashHex }
    }

    if (nonce % 2048 === 0) {
      await new Promise((resolve) => setTimeout(resolve, 0))
    }
  }

  return null
}
