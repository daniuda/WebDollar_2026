import { createHash } from 'node:crypto'
import nacl from 'tweetnacl'

const WEBD_UNITS = 10_000
const MIN_PAYMENT_FEE_WEBD = 10
const MIN_PAYMENT_AMOUNT_WEBD = 10 // protocol: MINIMUM_TRANSACTION_AMOUNT = 100000 units
const DEFAULT_TX_VERSION = 0x02
const WEBD_TOKEN_ID = Buffer.from([0x01])
const WIF_PREFIX = Buffer.from([0x58, 0x40, 0x43, 0xfe])
const WIF_SUFFIX = 0xff

export type PaymentWallet = {
  address: string
  secretHex: string
  publicKeyHex: string
  unencodedAddressHex: string
}

export type BuildPaymentTxRequest = {
  wallet: PaymentWallet
  recipientAddress: string
  amountWebd: number
  feeWebd: number
  nonce?: number
  timeLock?: number
}

export type BuiltPaymentTx = {
  txId: string
  nonce: number
  timeLock: number
  amountUnits: number
  feeUnits: number
  signatureHex: string
  serializedBuffer: Buffer
  serializedHex: string
  tx: {
    version: number
    nonce: number
    timeLock: number
    from: Array<{
      unencodedAddress: string
      publicKey: string
      amount: number
      signature: string
    }>
    to: Array<{
      unencodedAddress: string
      amount: number
    }>
    fee: number
  }
}

function normalizeWebdBase64(input: string): string {
  return input.trim().replace(/\$/g, '/').replace(/#/g, 'O').replace(/@/g, 'l')
}

function decodeAddressToUnencodedHex(address: string): string {
  const raw = Buffer.from(normalizeWebdBase64(address), 'base64')
  if (raw.length < 30) {
    throw new Error('Adresa destinatar invalida (lungime prea mica)')
  }

  const prefix = raw.subarray(0, 4)
  const suffix = raw[raw.length - 1]
  if (!prefix.equals(WIF_PREFIX) || suffix !== WIF_SUFFIX) {
    throw new Error('Adresa destinatar invalida (prefix/suffix)')
  }

  const unencoded = raw.subarray(5, 25)
  if (unencoded.length !== 20) {
    throw new Error('Adresa destinatar invalida (unencoded != 20 bytes)')
  }

  return unencoded.toString('hex')
}

function serializeNumber1(value: number): Buffer {
  const b = Buffer.alloc(1)
  b[0] = value & 0xff
  return b
}

function serializeNumber2(value: number): Buffer {
  const b = Buffer.alloc(2)
  b[1] = value & 0xff
  b[0] = (value >> 8) & 0xff
  return b
}

function serializeNumber3(value: number): Buffer {
  const b = Buffer.alloc(3)
  b[2] = value & 0xff
  b[1] = (value >> 8) & 0xff
  b[0] = (value >> 16) & 0xff
  return b
}

function serializeNumber7(value: number): Buffer {
  if (!Number.isFinite(value) || value < 0) {
    throw new Error('Valoare invalida pentru serializare pe 7 bytes')
  }

  const out = Buffer.alloc(7)
  let n = Math.floor(value)
  for (let i = 0; i < out.length; i += 1) {
    const byte = n & 0xff
    out[i] = byte
    n = (n - byte) / 256
  }
  return out
}

function serializeToSection(unencodedAddress: Buffer, amountUnits: number): Buffer {
  return Buffer.concat([
    serializeNumber1(1),
    unencodedAddress,
    serializeNumber7(amountUnits),
  ])
}

function serializeFromSection(publicKey: Buffer, signature: Buffer, amountUnits: number): Buffer {
  return Buffer.concat([
    serializeNumber1(1),
    publicKey,
    signature,
    serializeNumber7(amountUnits),
    serializeNumber1(WEBD_TOKEN_ID.length),
    WEBD_TOKEN_ID,
  ])
}

function serializeForSigning(
  version: number,
  nonce: number,
  timeLock: number,
  fromUnencoded: Buffer,
  fromPublicKey: Buffer,
  fromAmountUnits: number,
  toUnencoded: Buffer,
  toAmountUnits: number,
): Buffer {
  return Buffer.concat([
    serializeNumber1(version),
    serializeNumber2(nonce),
    serializeNumber3(timeLock),
    fromUnencoded,
    fromPublicKey,
    fromPublicKey,
    serializeNumber1(1),
    serializeNumber7(fromAmountUnits),
    serializeToSection(toUnencoded, toAmountUnits),
  ])
}

function toUnits(valueWebd: number, label: string): number {
  if (!Number.isFinite(valueWebd) || valueWebd <= 0) {
    throw new Error(`${label} trebuie sa fie > 0`) 
  }

  const units = Math.round(valueWebd * WEBD_UNITS)
  if (units <= 0) {
    throw new Error(`${label} este prea mic`) 
  }

  return units
}

function validateMinimumFee(feeWebd: number): void {
  if (!Number.isFinite(feeWebd) || feeWebd < MIN_PAYMENT_FEE_WEBD) {
    throw new Error(`Fee minim este ${MIN_PAYMENT_FEE_WEBD} WEBD`)
  }
}

export function buildSignedPaymentTransaction(input: BuildPaymentTxRequest): BuiltPaymentTx {
  if (!input.wallet?.secretHex || !input.wallet.publicKeyHex || !input.wallet.unencodedAddressHex) {
    throw new Error('Wallet deblocat invalid sau incomplet pentru plata')
  }

  const amountUnits = toUnits(input.amountWebd, 'Suma')
  if (input.amountWebd < MIN_PAYMENT_AMOUNT_WEBD) {
    throw new Error(`Suma minima este ${MIN_PAYMENT_AMOUNT_WEBD} WEBD (limita protocolului WebDollar)`)
  }
  validateMinimumFee(input.feeWebd)
  const feeUnits = toUnits(input.feeWebd, 'Fee')
  const fromAmountUnits = amountUnits + feeUnits

  const fromUnencoded = Buffer.from(input.wallet.unencodedAddressHex, 'hex')
  const fromPublicKey = Buffer.from(input.wallet.publicKeyHex, 'hex')
  const toUnencoded = Buffer.from(decodeAddressToUnencodedHex(input.recipientAddress), 'hex')

  if (fromUnencoded.length !== 20 || toUnencoded.length !== 20) {
    throw new Error('Adresa sursa/destinatar invalida pentru tranzactie')
  }

  if (fromPublicKey.length !== 32) {
    throw new Error('Cheie publica wallet invalida (trebuie 32 bytes)')
  }

  const secretSeed = Buffer.from(input.wallet.secretHex, 'hex')
  if (secretSeed.length !== 32) {
    throw new Error('Secret wallet invalid (trebuie 32 bytes)')
  }

  const nonce = Number(input.nonce)
  if (!Number.isInteger(nonce) || nonce < 0 || nonce > 0xffff) {
    throw new Error('Nonce invalid pentru tranzactie (trebuie 0..65535)')
  }

  const timeLock = Number(input.timeLock ?? 0)
  if (!Number.isInteger(timeLock) || timeLock < 0 || timeLock > 0xffffff) {
    throw new Error('timeLock invalid pentru tranzactie (trebuie 0..16777215)')
  }

  const signingPayload = serializeForSigning(
    DEFAULT_TX_VERSION,
    nonce,
    timeLock,
    fromUnencoded,
    fromPublicKey,
    fromAmountUnits,
    toUnencoded,
    amountUnits,
  )

  const keyPair = nacl.sign.keyPair.fromSeed(secretSeed)
  const signature = Buffer.from(nacl.sign.detached(signingPayload, keyPair.secretKey))

  const serializedTx = Buffer.concat([
    serializeNumber1(DEFAULT_TX_VERSION),
    serializeNumber2(nonce),
    serializeNumber3(timeLock),
    serializeFromSection(fromPublicKey, signature, fromAmountUnits),
    serializeToSection(toUnencoded, amountUnits),
  ])

  const txId = createHash('sha256').update(createHash('sha256').update(serializedTx).digest()).digest('hex')

  return {
    txId,
    nonce,
    timeLock,
    amountUnits,
    feeUnits,
    signatureHex: signature.toString('hex'),
    serializedBuffer: serializedTx,
    serializedHex: serializedTx.toString('hex'),
    tx: {
      version: DEFAULT_TX_VERSION,
      nonce,
      timeLock,
      from: [
        {
          unencodedAddress: fromUnencoded.toString('hex'),
          publicKey: fromPublicKey.toString('hex'),
          amount: fromAmountUnits,
          signature: signature.toString('hex'),
        },
      ],
      to: [
        {
          unencodedAddress: toUnencoded.toString('hex'),
          amount: amountUnits,
        },
      ],
      fee: feeUnits,
    },
  }
}
