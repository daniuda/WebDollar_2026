import axios from 'axios'
import type { NodeTxBroadcaster } from './legacyPool.js'
import type { BuiltPaymentTx } from './txBuilder.js'

export type PaymentBroadcastResult = {
  ok: boolean
  txId: string
  method: 'socket' | 'http-chain' | 'http-json-rpc' | 'http-wallet-secret'
  message: string
}

function isValidTxId(value: unknown): value is string {
  return typeof value === 'string' && /^[a-fA-F0-9]{64}$/.test(value)
}

function truncateForMessage(value: unknown): string {
  try {
    const raw = typeof value === 'string' ? value : JSON.stringify(value)
    return raw.length > 240 ? `${raw.slice(0, 240)}...` : raw
  } catch {
    return String(value)
  }
}

function resolvePoolBaseFromConfig(poolUrl: string): string {
  const value = poolUrl.trim()
  if (!value) return ''

  if (value.startsWith('pool/')) {
    const parts = value.split('/')
    if (parts.length >= 8) {
      const rawUrl = parts.slice(7).join('/')
      return rawUrl.replace('$$', '//').replace(/\/$/, '')
    }
  }

  return value.replace('$$', '//').replace(/\/$/, '')
}

function normalizeHttpLikeUrl(value: string): string {
  return value.trim().replace('$$', '//').replace(/\/$/, '')
}

function resolvePaymentBaseFromConfig(poolUrl: string, paymentUrl?: string): string {
  const explicitPayment = normalizeHttpLikeUrl(paymentUrl || '')
  if (explicitPayment) return explicitPayment
  return resolvePoolBaseFromConfig(poolUrl)
}

/**
 * Extract node URL from pool config string.
 * Pool config format: pool/fee/min/max/poolName/0.001/publicKeyHex/https:$$nodeurl...
 * or direct HTTP URL like https://node.example.com:8080
 */
function extractNodeUrlFromPoolConfig(poolUrl: string): string | null {
  const value = poolUrl.trim()
  if (!value) return null

  // If it's already a direct HTTP(S) URL, return it as-is
  if (value.match(/^https?:\/\//i)) {
    return value
  }

  // If it's a pool config string, extract the node URL from the end
  if (value.startsWith('pool/')) {
    const parts = value.split('/')
    if (parts.length >= 8) {
      const nodeUrlPart = parts.slice(7).join('/')
      const normalized = nodeUrlPart.replace('$$', '//').replace(/\/$/, '')
      return normalized
    }
  }

  return null
}

/**
 * Lista de noduri WebDollar publice folosita ca fallback daca nodul primar din config esuaza.
 * Ordinea conteaza: primul disponibil cu handshake OK castiga.
 */
const FALLBACK_NODE_URLS = [
  'https://daniuda.ddns.net:8080',
  'https://node.spyclub.ro:8080',
]

/**
 * Construieste lista ordonata de candidati pentru broadcast:
 * 1. Nodul extras din configuratia pool-ului (daca exista)
 * 2. Fallback-urile hardcodate (fara duplicate)
 */
function buildNodeCandidates(poolUrl: string): string[] {
  const primary = extractNodeUrlFromPoolConfig(poolUrl)
  const candidates: string[] = []

  if (primary) {
    candidates.push(primary)
  }

  for (const fb of FALLBACK_NODE_URLS) {
    if (!candidates.includes(fb)) {
      candidates.push(fb)
    }
  }

  return candidates
}

function buildWalletSecretEndpoint(baseOrSecretUrl: string, tx: BuiltPaymentTx): string {
  const marker = '/wallets/create-transaction'
  const normalized = normalizeHttpLikeUrl(baseOrSecretUrl)
  const markerIndex = normalized.indexOf(marker)
  const root = markerIndex >= 0 ? normalized.slice(0, markerIndex) : normalized
  const endpointBase = `${root}${marker}`

  return `${endpointBase}/${encodeURIComponent(tx.tx.from[0].unencodedAddress)}/${encodeURIComponent(tx.tx.to[0].unencodedAddress)}/${(tx.amountUnits / 10000).toFixed(4)}/${(tx.feeUnits / 10000).toFixed(4)}`
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function isTxVisibleResponse(data: any, txId: string): boolean {
  if (!data || typeof data !== 'object') return false

  const txIdLower = txId.toLowerCase()
  const resultTxId = String(data?.txId || data?.transaction?.txId || '').toLowerCase()

  if (data?.result === true && resultTxId === txIdLower) return true
  if (resultTxId === txIdLower) return true
  if (data?.transaction && typeof data.transaction === 'object') {
    const nested = String(data.transaction.txId || data.transaction.id || '').toLowerCase()
    if (nested === txIdLower) return true
  }

  return false
}

async function waitForTransactionVisibility(nodeBaseUrl: string, txId: string, attempts = 6, delayMs = 1_000): Promise<boolean> {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const url = `${nodeBaseUrl}/transactions/get/${txId}`
      const response = await axios.get(url, { timeout: 4_000 })
      if (isTxVisibleResponse(response.data, txId)) {
        console.log('[broadcastPaymentTransaction] tx visibility confirmed', { txId: txId.slice(0, 12), attempt })
        return true
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err)
      console.log('[broadcastPaymentTransaction] tx visibility probe failed', { attempt, err: errMsg })
    }

    if (attempt < attempts) await sleep(delayMs)
  }

  return false
}

async function broadcastHttpWalletSecret(baseUrl: string, tx: BuiltPaymentTx): Promise<PaymentBroadcastResult> {
  const walletSecretEndpoint = buildWalletSecretEndpoint(baseUrl, tx)

  try {
    const response = await axios.get(walletSecretEndpoint, {
      timeout: 15_000,
    })

    if (!response.data?.result) {
      throw new Error(`Wallet secret endpoint returnare false: ${truncateForMessage(response.data)}`)
    }

    const remoteTxId = response.data?.txId
    if (!isValidTxId(remoteTxId)) {
      throw new Error(`Wallet secret endpoint nu a returnat txId valid: ${truncateForMessage(response.data)}`)
    }

    return {
      ok: true,
      txId: remoteTxId,
      method: 'http-wallet-secret',
      message: `Tranzactie trimisa prin wallet secret endpoint. Raspuns: ${truncateForMessage(response.data)}`,
    }
  } catch (err) {
    const statusCode = (err as any)?.response?.status ? ` (HTTP ${(err as any).response.status})` : ''
    throw new Error(`URL: ${walletSecretEndpoint}${statusCode} - ${err instanceof Error ? err.message : String(err)}`)
  }
}

async function broadcastHttpChain(baseUrl: string, tx: BuiltPaymentTx): Promise<PaymentBroadcastResult> {
  const chainUrl = `${baseUrl}/chain/transactions/new`

  try {
    const response = await axios.post(chainUrl, {
      tx: tx.serializedHex,
      txJson: tx.tx,
    }, {
      timeout: 15_000,
    })

    const remoteTxId = response.data?.txId || response.data?.transaction
    if (!isValidTxId(remoteTxId)) {
      throw new Error(`Endpoint /chain/transactions/new nu a returnat txId valid: ${truncateForMessage(response.data)}`)
    }

    return {
      ok: true,
      txId: remoteTxId,
      method: 'http-chain',
      message: `Tranzactie trimisa prin endpoint HTTP /chain/transactions/new. Raspuns: ${truncateForMessage(response.data)}`,
    }
  } catch (err) {
    const statusCode = (err as any)?.response?.status ? ` (HTTP ${(err as any).response.status})` : ''
    throw new Error(`URL: ${chainUrl}${statusCode} - ${err instanceof Error ? err.message : String(err)}`)
  }
}

async function broadcastHttpJsonRpc(baseUrl: string, tx: BuiltPaymentTx): Promise<PaymentBroadcastResult> {
  const payload = {
    transaction: tx.serializedBuffer,
    signature: tx.signatureHex,
  }

  const encoded = Buffer.from(JSON.stringify(payload), 'utf8').toString('base64')
  const jsonRpcUrl = `${baseUrl}/json_rpc`

  try {
    const response = await axios.post(jsonRpcUrl, {
      jsonrpc: '2.0',
      method: 'sendRawTransaction',
      params: [encoded],
      id: Date.now(),
    }, {
      timeout: 15_000,
    })

    if (response.data?.error) {
      throw new Error(String(response.data.error?.message || 'sendRawTransaction failed'))
    }

    const remoteTxId = response.data?.result
    if (!isValidTxId(remoteTxId)) {
      throw new Error(`sendRawTransaction nu a returnat txId valid: ${truncateForMessage(response.data)}`)
    }

    return {
      ok: true,
      txId: remoteTxId,
      method: 'http-json-rpc',
      message: `Tranzactie trimisa prin JSON-RPC sendRawTransaction. Raspuns: ${truncateForMessage(response.data)}`,
    }
  } catch (err) {
    const statusCode = (err as any)?.response?.status ? ` (HTTP ${(err as any).response.status})` : ''
    throw new Error(`URL: ${jsonRpcUrl}${statusCode} - ${err instanceof Error ? err.message : String(err)}`)
  }
}

export async function broadcastPaymentTransaction(poolUrl: string, paymentUrl: string | undefined, tx: BuiltPaymentTx, nodeTxBroadcaster: NodeTxBroadcaster): Promise<PaymentBroadcastResult> {
  console.log('[broadcastPaymentTransaction] START', { txId: tx.txId.slice(0, 12), poolUrl: poolUrl.slice(0, 50) })
  const errors: string[] = []

  // Build ordered list of node candidates (primary from config + hardcoded fallbacks)
  const nodeCandidates = buildNodeCandidates(poolUrl)
  console.log('[broadcastPaymentTransaction] node candidates:', nodeCandidates)

  // Try socket broadcast on each candidate in order
  for (const nodeUrl of nodeCandidates) {
    try {
      console.log('[broadcastPaymentTransaction] trying node socket:', nodeUrl)
      await nodeTxBroadcaster.connectToNode(nodeUrl)
      const socketResult = await nodeTxBroadcaster.broadcastTransaction(tx.serializedBuffer)
      console.log('[broadcastPaymentTransaction] socket result from', nodeUrl, ':', { accepted: socketResult.accepted, message: socketResult.message })

      if (socketResult.accepted) {
        const isVisible = await waitForTransactionVisibility(nodeUrl, tx.txId)
        console.log('[broadcastPaymentTransaction] socket post-check visibility', { txId: tx.txId.slice(0, 12), visible: isVisible, nodeUrl })

        console.log('[broadcastPaymentTransaction] SUCCESS via node socket', nodeUrl)
        return {
          ok: true,
          txId: tx.txId,
          method: 'socket',
          message: isVisible
            ? `Tranzactie trimisa via socket nod (${nodeUrl}) si confirmata. txId: ${tx.txId}`
            : `Tranzactie trimisa via socket nod (${nodeUrl}), fara confirmare explicita din fereastra de verificare. txId: ${tx.txId}`,
        }
      }
      errors.push(`Node socket ${nodeUrl}: ${socketResult.message}`)
    } catch (nodeErr) {
      const msg = nodeErr instanceof Error ? nodeErr.message : String(nodeErr)
      console.log('[broadcastPaymentTransaction] node socket error pentru', nodeUrl, ':', msg)
      errors.push(`Node socket error ${nodeUrl}: ${msg}`)
    }
  }

  const paymentBaseUrl = resolvePaymentBaseFromConfig(poolUrl, paymentUrl)
  console.log('[broadcastPaymentTransaction] trying HTTP fallback', { paymentBaseUrl: paymentBaseUrl?.slice(0, 50) })

  if (!paymentBaseUrl || !/^https?:\/\//i.test(paymentBaseUrl)) {
    const errMsg = `Plata nu poate fi trimisa. Socket neconectat: ${errors.join('; ')}. Configureaza un endpoint HTTP de payment valid.`
    console.log('[broadcastPaymentTransaction] ERROR: no valid payment URL', errMsg)
    throw new Error(errMsg)
  }

  try {
    console.log('[broadcastPaymentTransaction] trying JSON-RPC broadcast...')
    return await broadcastHttpJsonRpc(paymentBaseUrl, tx)
  } catch (rpcError) {
    const rpcMessage = rpcError instanceof Error ? rpcError.message : String(rpcError)
    console.log('[broadcastPaymentTransaction] JSON-RPC failed:', rpcMessage)
    errors.push(`JSON-RPC: ${rpcMessage}`)
  }

  try {
    console.log('[broadcastPaymentTransaction] trying /chain/transactions/new broadcast...')
    return await broadcastHttpChain(paymentBaseUrl, tx)
  } catch (chainError) {
    const chainMessage = chainError instanceof Error ? chainError.message : String(chainError)
    console.log('[broadcastPaymentTransaction] /chain/transactions/new failed:', chainMessage)
    errors.push(`HTTP /chain/transactions/new: ${chainMessage}`)
  }

  try {
    console.log('[broadcastPaymentTransaction] trying wallet-secret broadcast...')
    return await broadcastHttpWalletSecret(paymentBaseUrl, tx)
  } catch (walletSecretError) {
    const wsMessage = walletSecretError instanceof Error ? walletSecretError.message : String(walletSecretError)
    console.log('[broadcastPaymentTransaction] wallet-secret failed:', wsMessage)
    errors.push(`Wallet secret endpoint: ${wsMessage}`)
  }

  const finalErr = `Plata nu poate fi trimisa. Endpoint-ul de payment configurat (${paymentBaseUrl}) nu expune un submit compatibil. Pentru desktop app, varianta corecta este un nod cu JSON-RPC activ (sendRawTransaction) deoarece tranzactia este semnata local. Endpoint-ul privat WALLET_SECRET_URL functioneaza doar daca nodul are deja wallet-ul importat si semneaza el tranzactia. Configureaza un endpoint JSON-RPC valid sau un nod propriu. Esecuri detaliate: ${errors.join('; ')}`
  console.log('[broadcastPaymentTransaction] ALL METHODS FAILED:', finalErr)
  throw new Error(finalErr)
}
