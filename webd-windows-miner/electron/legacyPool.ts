import { randomBytes } from 'node:crypto'

// Use require() so tsup emits a bare require() and does NOT wrap this CJS-only
// module with __toESM().  With `import socketIo from 'socket.io-client'`, tsup
// wraps it and socketIo becomes { default: fn } instead of fn itself, causing:
//   TypeError: Cannot read properties of undefined (reading 'length')
// eslint-disable-next-line @typescript-eslint/no-require-imports, @typescript-eslint/no-var-requires
const socketIo: (url: string, opts?: Record<string, unknown>) => any = require('socket.io-client')

// Pool uses a self-signed TLS cert; disable validation for the whole miner process.
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'

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

/**
 * Build the socket.io-client 2.x `query` OBJECT for the Node-WebDollar pool.
 * The pool server immediately disconnects sockets without msg=HelloNode and
 * nodeConsensusType=1 (NODE_CONSENSUS_SERVER).  Query is passed as an object
 * to match how the official Node-WebDollar miner client sends it.
 */
function buildQuery(): Record<string, string | number> {
  const uuid = randomBytes(16).toString('hex')
  return {
    msg: 'HelloNode',
    version: '1.3.24',
    uuid,
    nodeType: 0,        // NODE_WEB_PEER  (browser-like client)
    nodeConsensusType: 1, // NODE_CONSENSUS_SERVER (required when pool is active)
    domain: 'browser',
  }
}

function bytesFromAny(v: any): Buffer {
  if (!v) return Buffer.alloc(0)
  if (Buffer.isBuffer(v)) return v
  if (Array.isArray(v)) return Buffer.from(v)
  if (v?.type === 'Buffer' && Array.isArray(v.data)) return Buffer.from(v.data)
  return Buffer.alloc(0)
}

function decodeWebdBase64(input: string): Buffer {
  // WebDollar replaces O->#, l->@, /->$ in base64 representation.
  const normalized = input
    .replace(/#/g, 'O')
    .replace(/@/g, 'l')
    .replace(/\$/g, '/')
  return Buffer.from(normalized, 'base64')
}

function getUnencodedAddressHexFromWalletAddress(walletAddress: string): string {
  try {
    const raw = decodeWebdBase64(walletAddress.trim())
    // AddressWIF bytes format: WEBD$ prefix(4) + version(1) + addr(20) + checksum(4) + suffix(1)
    if (raw.length < 30) return ''

    const prefix = raw.subarray(0, 4)
    const suffix = raw.subarray(raw.length - 1)
    if (!prefix.equals(Buffer.from([0x58, 0x40, 0x43, 0xfe])) || suffix[0] !== 0xff) {
      return ''
    }

    const unencoded = raw.subarray(5, 25)
    if (unencoded.length !== 20) return ''
    return unencoded.toString('hex')
  } catch {
    return ''
  }
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
  private walletAddress = ''
  private connected = false
  private lastError = ''
  private lastJob: LegacyJob | null = null
  private protocolEvents: string[] = []
  private sharesAccepted = 0
  private sharesRejected = 0
  private sharesStale = 0
  private rewardPending = 0
  private rewardConfirmed = 0

  private pushProtocolEvent(message: string) {
    const stamp = new Date().toLocaleTimeString('ro-RO')
    const entry = `${stamp} ${message}`
    if (this.protocolEvents[0] === entry) return
    this.protocolEvents = [entry, ...this.protocolEvents].slice(0, 20)
  }

  private updateRewardStats(payload: any) {
    if (!payload || typeof payload !== 'object') return

    if (payload.reward !== undefined) {
      const rewardPending = Number(payload.reward)
      if (Number.isFinite(rewardPending) && rewardPending >= 0) {
        this.rewardPending = rewardPending
      }
    }

    if (payload.confirmed !== undefined) {
      const rewardConfirmed = Number(payload.confirmed)
      if (Number.isFinite(rewardConfirmed) && rewardConfirmed >= 0) {
        this.rewardConfirmed = rewardConfirmed
      }
    }
  }

  async connect(poolAddress: string, walletAddress: string): Promise<{ token: string; workerId: string; poolName: string; poolFee: number }> {
    if (typeof poolAddress !== 'string' || !poolAddress.trim()) {
      throw new Error('Adresa pool legacy lipseste sau este invalida')
    }

    if (typeof walletAddress !== 'string' || !walletAddress.trim()) {
      throw new Error('Wallet address lipseste pentru conectarea la pool')
    }

    const parsed = parsePoolAddress(poolAddress)
    if (!parsed) {
      throw new Error('Adresa pool legacy invalida')
    }

    const poolUrl = parsed.poolUrl?.trim()
    if (!poolUrl || !/^https?:\/\//i.test(poolUrl)) {
      throw new Error(`URL pool legacy invalid: ${String(parsed.poolUrl ?? '')}`)
    }

    this.disconnect()
    this.parsed = parsed
    this.walletAddress = walletAddress.trim()
    this.lastError = ''
    this.lastJob = null
    this.protocolEvents = []
    this.rewardPending = 0
    this.rewardConfirmed = 0
    this.pushProtocolEvent(`connect ${poolUrl}`)

    // Pass query as an OBJECT, exactly as the official Node-WebDollar miner client does.
    // Polling (HTTP) is blocked/failing on this pool; use websocket only.
    let s: any
    try {
      s = socketIo(poolUrl, {
        reconnection: true,
        reconnectionAttempts: Number.MAX_SAFE_INTEGER,
        reconnectionDelay: 3000,
        reconnectionDelayMax: 10000,
        timeout: 30000,
        transports: ['websocket'],
        query: buildQuery(),
      })
    } catch (err) {
      const msg = err instanceof Error ? `${err.message}${err.stack ? `\n${err.stack}` : ''}` : String(err)
      throw new Error(`Init socket.io legacy esuat pentru ${poolUrl}: ${msg}`)
    }
    this.socket = s

    // Pool server sends HelloNode after accepting the connection and registering
    // our socket in its NodesList.  We send hello-pool only after that so the
    // pool's hello-pool event handler is guaranteed to exist.
    let helloSent = false
    const doSendHello = () => {
      if (!helloSent) {
        helloSent = true
        this.sendHello(walletAddress)
      }
    }

    s.on('connect', () => {
      this.connected = true
      this.workerId = s.id || `legacy-${Date.now()}`
      this.pushProtocolEvent(`socket connected ${this.workerId}`)
      // Fallback: if HelloNode from server never arrives, send hello-pool after 1.5s
      setTimeout(doSendHello, 1500)
    })

    // Primary trigger: server sends HelloNode once it has registered our socket
    s.on('HelloNode', () => {
      this.pushProtocolEvent('received HelloNode from pool')
      setTimeout(doSendHello, 150)
    })

    s.on('disconnect', () => {
      this.connected = false
      this.pushProtocolEvent('socket disconnected')
    })

    s.on('connect_error', (err: any) => {
      const reason = [
        err?.message,
        err?.description,
        err?.type,
        err?.context?.status,
      ].filter(Boolean).join(' | ') || String(err ?? 'unknown')
      this.lastError = `Eroare conectare: ${reason}`
      this.connected = false
      this.pushProtocolEvent(`connect_error ${reason}`)
    })

    s.on('mining-pool/new-work', (payload: any) => {
      this.updateRewardStats(payload)
      const parsedWork = parseLegacyWork(payload)
      if (parsedWork) {
        this.lastJob = parsedWork
        this.pushProtocolEvent(`received new-work job=${parsedWork.jobId} h=${parsedWork.height}`)
      }
    })

    s.on('mining-pool/get-work/answer', (payload: any) => {
      this.updateRewardStats(payload)
      const parsedWork = parseLegacyWork(payload)
      if (parsedWork) {
        this.lastJob = parsedWork
        this.pushProtocolEvent(`received get-work answer job=${parsedWork.jobId} h=${parsedWork.height}`)
      }
    })

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(this.lastError || 'Timeout conectare legacy pool')), 30_000)

      s.once('mining-pool/hello-pool/answer', (answer: any) => {
        clearTimeout(timer)
        if (!answer?.result) {
          this.pushProtocolEvent(`hello-pool rejected ${String(answer?.message || 'unknown')}`)
          reject(new Error(answer?.message || 'Pool refuzat'))
          return
        }

        this.updateRewardStats(answer)
        this.pushProtocolEvent('received hello-pool answer result=true')

        // Step 3 of the 3-way handshake: confirm we accepted the pool's answer.
        // Without this, the pool never calls addConnectedMinerPool and won't send work.
        s.emit('mining-pool/hello-pool/answer/confirmation', { result: true })
        this.pushProtocolEvent('sent hello-pool confirmation')

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
    this.walletAddress = ''
    this.lastJob = null
    this.rewardPending = 0
    this.rewardConfirmed = 0
  }

  private sendHello(walletAddress: string) {
    if (!this.socket || !this.parsed) return
    const unencodedAddressHex = getUnencodedAddressHexFromWalletAddress(walletAddress)

    this.pushProtocolEvent(`sent hello-pool addr=${walletAddress.slice(0, 18)}... pos=${unencodedAddressHex ? 'yes' : 'no'}`)
    this.socket.emit('mining-pool/hello-pool', {
      message: randomBytes(32),
      pool: Buffer.from(this.parsed.poolPublicKeyHex, 'hex'),
      minerAddress: walletAddress,
      // For PoS pools, server-side work generation expects minerInstance.addresses.
      addresses: unencodedAddressHex ? [unencodedAddressHex] : [],
    })
  }

  private requestWork() {
    this.pushProtocolEvent('sent get-work')
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
        this.updateRewardStats(answer)
        this.pushProtocolEvent(`received work-done answer result=${String(answer?.result)} msg=${String(answer?.message || '-')}`)
        resolve(answer)
      }

      this.socket?.on('mining-pool/work-done/answer', listener)
      this.pushProtocolEvent(`sent work-done job=${jobId} nonce=${nonce}`)
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
      walletAddress: this.walletAddress,
      lastSeen: Date.now(),
      online: this.connected,
      sharesAccepted: this.sharesAccepted,
      sharesRejected: this.sharesRejected,
      sharesStale: this.sharesStale,
      rewardPending: this.rewardPending,
      rewardConfirmed: this.rewardConfirmed,
      protocolEvents: [...this.protocolEvents],
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
