import { createCipheriv, createDecipheriv, createHash, pbkdf2Sync, randomBytes } from 'node:crypto'
import nacl from 'tweetnacl'

const WIF_PREFIX = Buffer.from([0x58, 0x40, 0x43, 0xfe])
const WIF_VERSION = Buffer.from([0x00])
const WIF_SUFFIX = Buffer.from([0xff])
const LOCAL_MAGIC = 'WEBD_LOCAL_WALLET_V1'
const LOCAL_ITER = 120_000
const LOCAL_KEY_BITS = 32

export interface GeneratedWallet {
  address: string
  secretHex: string
  publicKeyHex: string
  unencodedAddressHex: string
}

interface LegacyWalletFile {
  version: '0.1'
  address: string
  privateKey: string
  publicKey: string
  unencodedAddress?: string
}

interface LocalWalletEnvelope {
  magic: string
  salt: string
  iv: string
  data: string
}

export function generateWallet(): GeneratedWallet {
  const seed = randomBytes(32)
  return fromSeed(seed)
}

export function importWalletRaw(raw: string): GeneratedWallet {
  const text = raw.trim()

  if (text.startsWith('{')) {
    const parsed = JSON.parse(text) as LegacyWalletFile
    if (parsed.version === '0.1') {
      const privateKey = parsed.privateKey.trim()
      if (/^[0-9a-fA-F]{64}$/.test(privateKey)) {
        return fromSecretHex(privateKey)
      }
      if (/^[0-9a-fA-F]{138}$/.test(privateKey)) {
        return fromLegacyPrivateKeyHex(privateKey)
      }
    }

    throw new Error('Format JSON legacy invalid')
  }

  if (/^[0-9a-fA-F]{138}$/.test(text)) {
    return fromLegacyPrivateKeyHex(text)
  }

  if (/^[0-9a-fA-F]{64}$/.test(text)) {
    return fromSecretHex(text)
  }

  return fromPrivateKeyWif(text)
}

export function exportLegacyWallet(secretHex: string): string {
  const wallet = fromSecretHex(secretHex)
  const legacyWallet: LegacyWalletFile = {
    version: '0.1',
    address: wallet.address,
    privateKey: legacyPrivateKeyHexFromSecretHex(wallet.secretHex),
    publicKey: wallet.publicKeyHex,
    unencodedAddress: wallet.unencodedAddressHex,
  }

  return JSON.stringify(legacyWallet, null, 2)
}

export function encryptSecret(secretHex: string, passphrase: string): string {
  if (passphrase.length < 8) {
    throw new Error('Parola trebuie sa aiba minim 8 caractere')
  }

  const salt = randomBytes(16)
  const iv = randomBytes(12)
  const key = deriveKey(passphrase, salt)
  const cipher = createCipheriv('aes-256-gcm', key, iv)
  const encrypted = Buffer.concat([cipher.update(secretHex, 'utf8'), cipher.final()])
  const tag = cipher.getAuthTag()

  const envelope: LocalWalletEnvelope = {
    magic: LOCAL_MAGIC,
    salt: salt.toString('base64'),
    iv: iv.toString('base64'),
    data: Buffer.concat([encrypted, tag]).toString('base64'),
  }

  return JSON.stringify(envelope)
}

export function decryptSecret(envelopeJson: string, passphrase: string): string {
  const env = JSON.parse(envelopeJson) as LocalWalletEnvelope
  if (env.magic !== LOCAL_MAGIC) {
    throw new Error('Format wallet local invalid')
  }

  const salt = Buffer.from(env.salt, 'base64')
  const iv = Buffer.from(env.iv, 'base64')
  const payload = Buffer.from(env.data, 'base64')
  const encrypted = payload.subarray(0, payload.length - 16)
  const tag = payload.subarray(payload.length - 16)
  const key = deriveKey(passphrase, salt)
  const decipher = createDecipheriv('aes-256-gcm', key, iv)
  decipher.setAuthTag(tag)
  const plain = Buffer.concat([decipher.update(encrypted), decipher.final()])

  return plain.toString('utf8')
}

function fromSecretHex(secretHex: string): GeneratedWallet {
  const clean = secretHex.trim().toLowerCase()
  if (!/^[0-9a-f]{64}$/.test(clean)) {
    throw new Error('Secret invalid: trebuie 64 caractere hex')
  }

  return fromSeed(Buffer.from(clean, 'hex'))
}

function fromSeed(seed: Buffer): GeneratedWallet {
  if (seed.length !== 32) {
    throw new Error('Seed trebuie sa aiba 32 bytes')
  }

  const keyPair = nacl.sign.keyPair.fromSeed(seed)
  const publicKey = Buffer.from(keyPair.publicKey)
  const sha256 = createHash('sha256').update(publicKey).digest()
  const unencodedAddress = createHash('ripemd160').update(sha256).digest()
  const versionAndAddr = Buffer.concat([WIF_VERSION, unencodedAddress])
  const checksum = sha256d(versionAndAddr).subarray(0, 4)
  const wifBytes = Buffer.concat([WIF_PREFIX, versionAndAddr, checksum, WIF_SUFFIX])

  return {
    address: wifBytes.toString('base64'),
    secretHex: seed.toString('hex'),
    publicKeyHex: publicKey.toString('hex'),
    unencodedAddressHex: unencodedAddress.toString('hex'),
  }
}

function privateKeyWifFromSecretHex(secretHex: string): string {
  const seed = Buffer.from(secretHex.trim().toLowerCase(), 'hex')
  if (seed.length !== 32) {
    throw new Error('Secret invalid')
  }

  const versionAndKey = Buffer.concat([Buffer.from([0x80]), seed])
  const checksum = sha256d(versionAndKey).subarray(0, 4)
  return Buffer.concat([versionAndKey, checksum]).toString('base64')
}

function fromPrivateKeyWif(privateKeyWif: string): GeneratedWallet {
  const raw = Buffer.from(privateKeyWif.trim(), 'base64')
  if (raw.length !== 37) {
    throw new Error('privateKeyWIF invalid')
  }
  if (raw[0] !== 0x80) {
    throw new Error('privateKeyWIF prefix invalid')
  }

  const body = raw.subarray(0, 33)
  const checksum = raw.subarray(33, 37)
  const expected = sha256d(body).subarray(0, 4)
  if (!checksum.equals(expected)) {
    throw new Error('privateKeyWIF checksum invalid')
  }

  return fromSeed(raw.subarray(1, 33))
}

function legacyPrivateKeyHexFromSecretHex(secretHex: string): string {
  const seed = Buffer.from(secretHex.trim().toLowerCase(), 'hex')
  if (seed.length !== 32) {
    throw new Error('Secret invalid')
  }

  const keyPair = nacl.sign.keyPair.fromSeed(seed)
  const publicKey = Buffer.from(keyPair.publicKey)
  const body = Buffer.concat([Buffer.from([0x80]), seed, publicKey])
  const checksum = sha256d(body).subarray(0, 4)
  return Buffer.concat([body, checksum]).toString('hex')
}

function fromLegacyPrivateKeyHex(privateKeyHex: string): GeneratedWallet {
  const raw = Buffer.from(privateKeyHex.trim().toLowerCase(), 'hex')
  if (raw.length !== 69) {
    throw new Error('privateKey legacy invalid')
  }
  if (raw[0] !== 0x80) {
    throw new Error('privateKey legacy prefix invalid')
  }

  const body = raw.subarray(0, 65)
  const checksum = raw.subarray(65, 69)
  const expected = sha256d(body).subarray(0, 4)
  if (!checksum.equals(expected)) {
    throw new Error('privateKey legacy checksum invalid')
  }

  return fromSeed(raw.subarray(1, 33))
}

function deriveKey(passphrase: string, salt: Buffer): Buffer {
  return pbkdf2Sync(passphrase, salt, LOCAL_ITER, LOCAL_KEY_BITS, 'sha256')
}

function sha256d(data: Buffer): Buffer {
  return createHash('sha256').update(createHash('sha256').update(data).digest()).digest()
}

export const walletInternals = {
  privateKeyWifFromSecretHex,
  legacyPrivateKeyHexFromSecretHex,
}