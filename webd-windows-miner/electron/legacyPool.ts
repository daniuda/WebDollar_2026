import { randomBytes } from 'node:crypto'
import socketIo from 'socket.io-client'

type LegacyJob = {
  jobId: string
  height: number
  target: string
  blockHeader: string
  nonceStart: number
  nonceEnd: number
  expireAt: number
}

type ShareResult = {
  result: string
  message: string
}

type ParsedPoolAddress = {
  poolName: string
  poolFee: number
  poolPublicKeyHex: string
  poolUrl: string
}

function parsePoolAddress(poolAddress: string): ParsedPoolAddress | null {
  const parts = poolAddress.trim().split('/')
  if (parts.length < 8 || parts[0] !== 'pool') return null

  const poolName = parts[4]
  const poolFee = Number(parts[5]) || 0
  const poolPublicKeyHex = parts[6]
  const rawUrl = parts.slice(7).join('/')
  const poolUrl = rawUrl.replace('$$', '//')

  return { poolName, poolFee, poolPublicKeyHex, poolUrl }
}

function bytesFromAny(v: any): Buffer {
  if (!v) return Buffer.alloc(0)
  if (Buffer.isBuffer(v)) return v
  if (Array.isArray(v)) return Buffer.from(v)
  if (v?.type === 'Buffer' && Array.isArray(v.data)) return Buffer.from(v.data)
  return Buffer.alloc(0)
}

function parseLegacyWork(payload: any): LegacyJob | null {
  const work = payload?.work ?? payload
  if (!work) return null

  const height = Number(work.h ?? -1)
  if (!Number.isFinite(height) || height < 0) return null

  const target = bytesFromAny(work.t).toString('hex')
  const header = bytesFromAny(work.s).toString('hex')
  const blockId = Number(work.I ?? height)
  const nonceStart = Number(work.start ?? 0)
  const nonceEnd = Number(work.end ?? 0)

  return {
    jobId: String(blockId),
    height,
    target,
    blockHeader: header,
    nonceStart,
    nonceEnd,
    expireAt: Date.now() + 120_000,
  }
}

export class LegacyPoolBridge {
  private socket: any = null
  private parsed: ParsedPoolAddress | null = null
  private token = ''
  private workerId = ''
  private connected = false
  private lastError = ''
  private lastJob: LegacyJob | null = null
  private sharesAccepted = 0
  private sharesRejected = 0
  private sharesStale = 0

  async connect(poolAddress: string, walletAddress: string): Promise<{ token: string; workerId: string; poolName: string; poolFee: number }> {
    const parsed = parsePoolAddress(poolAddress)
    if (!parsed) {
      throw new Error('Adresa pool legacy invalida')
    }

    this.disconnect()
    this.parsed = parsed
    this.lastError = ''
    this.lastJob = null

    const s = socketIo(parsed.poolUrl, {
      reconnection: true,
      reconnectionAttempts: Number.MAX_SAFE_INTEGER,
      reconnectionDelay: 3000,
      reconnectionDelayMax: 10000,
      timeout: 30000,
      transports: ['websocket', 'polling'],
      rejectUnauthorized: false,
    })
    this.socket = s

    s.on('connect', () => {
      this.connected = true
      this.workerId = s.id || `legacy-${Date.now()}`
      this.sendHello(walletAddress)
    })

    s.on('disconnect', () => {
      this.connected = false
    })

    s.on('connect_error', (err: any) => {
      const reason = String(err?.message ?? err ?? 'unknown')
      this.lastError = `Eroare conectare: ${reason}`
      this.connected = false
    })

    s.on('mining-pool/new-work', (payload: any) => {
      const parsedWork = parseLegacyWork(payload)
      if (parsedWork) this.lastJob = parsedWork
    })

    s.on('mining-pool/get-work/answer', (payload: any) => {
      const parsedWork = parseLegacyWork(payload)
      if (parsedWork) this.lastJob = parsedWork
    })

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(this.lastError || 'Timeout conectare legacy pool')), 30_000)

      s.once('mining-pool/hello-pool/answer', (answer: any) => {
        clearTimeout(timer)
        if (!answer?.result) {
          reject(new Error(answer?.message || 'Pool refuzat'))
          return
        }

        this.connected = true
        this.token = `legacy-${Date.now()}`
        this.workerId = s.id || this.workerId
        this.requestWork()
        resolve()
      })
    })

    return {
      token: this.token,
      workerId: this.workerId,
      poolName: parsed.poolName,
      poolFee: parsed.poolFee,
    }
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
    this.connected = false
    this.lastJob = null
  }

  private sendHello(walletAddress: string) {
    if (!this.socket || !this.parsed) return
    this.socket.emit('mining-pool/hello-pool', {
      message: randomBytes(32),
      pool: Buffer.from(this.parsed.poolPublicKeyHex, 'hex'),
      minerAddress: walletAddress,
      addresses: [],
    })
  }

  private requestWork() {
    this.socket?.emit('mining-pool/get-work', {})
  }

  async getJob(token: string): Promise<LegacyJob> {
    if (!this.connected || token !== this.token) {
      throw new Error('Worker legacy neautentificat')
    }

    if (this.lastJob && Date.now() <= this.lastJob.expireAt) {
      return this.lastJob
    }

    this.requestWork()

    await new Promise<void>((resolve, reject) => {
      const start = Date.now()
      const timer = setInterval(() => {
        if (this.lastJob) {
          clearInterval(timer)
          resolve()
          return
        }

        if (Date.now() - start > 10_000) {
          clearInterval(timer)
          reject(new Error('Nu a venit work de la pool'))
        }
      }, 200)
    })

    return this.lastJob as LegacyJob
  }

  async submitShare(token: string, jobId: string, nonce: number, hashHex: string): Promise<ShareResult> {
    if (!this.connected || token !== this.token) {
      throw new Error('Worker legacy neautentificat')
    }

    const currentJob = this.lastJob
    if (!currentJob || currentJob.jobId !== jobId) {
      return { result: 'stale', message: 'Job legacy expirat sau schimbat' }
    }

    const response = await new Promise<any>((resolve) => {
      const timer = setTimeout(() => resolve({ result: false, message: 'Timeout work-done answer' }), 10_000)
      const listener = (answer: any) => {
        clearTimeout(timer)
        this.socket?.off('mining-pool/work-done/answer', listener)
        resolve(answer)
      }

      this.socket?.on('mining-pool/work-done/answer', listener)
      this.socket?.emit('mining-pool/work-done', {
        hash: Buffer.from(hashHex, 'hex'),
        nonce,
        hashes: 1,
        id: Number(jobId),
        h: currentJob.height,
        timeDiff: 0,
        result: false,
      })
    })

    const msg = String(response?.message || '')
    if (response?.result === true) {
      this.sharesAccepted += 1
      return { result: 'accepted', message: msg || 'Share acceptat' }
    }

    if (/stale/i.test(msg)) {
      this.sharesStale += 1
      return { result: 'stale', message: msg || 'Share stale' }
    }

    this.sharesRejected += 1
    return { result: 'invalid', message: msg || 'Share respins' }
  }

  getWorkerStats(token: string) {
    if (token !== this.token) {
      throw new Error('Worker legacy neautentificat')
    }

    return {
      workerId: this.workerId || 'legacy-worker',
      walletAddress: '',
      lastSeen: Date.now(),
      online: this.connected,
      sharesAccepted: this.sharesAccepted,
      sharesRejected: this.sharesRejected,
      sharesStale: this.sharesStale,
      rewardPending: 0,
      rewardConfirmed: 0,
    }
  }

  getPoolStats() {
    return {
      workersTotal: this.connected ? 1 : 0,
      workersOnline: this.connected ? 1 : 0,
      totalShares: this.sharesAccepted + this.sharesRejected + this.sharesStale,
      poolName: this.parsed?.poolName || 'Legacy pool',
      height: this.lastJob?.height || 0,
      keyRequired: false,
    }
  }
}
