const DEFAULT_POOL_ADDRESS = 'pool/1/1/1/SpyClub/0.0001/374d24d549e73f05280b239d96d7c6b28f15aabb5d41e89818b660a9ebc3276e/https:$$node.spyclub.ro:8080'
const DEFAULT_HTTP_API = 'http://127.0.0.1:3001'

export function getDefaultPoolAddress(): string {
  return DEFAULT_POOL_ADDRESS
}

export function resolvePoolApiBase(input: string): string {
  const value = input.trim()
  if (!value) return DEFAULT_POOL_ADDRESS

  if (value.startsWith('pool/')) {
    const parts = value.split('/')
    if (parts.length >= 8) {
      const rawUrl = parts.slice(7).join('/')
      return rawUrl.replace('$$', '//').replace(/\/$/, '')
    }
    return value
  }

  if (value.includes('$$')) {
    return value.replace('$$', '//').replace(/\/$/, '')
  }

  return value.replace(/\/$/, '')
}

export function resolvePoolApiCandidates(input: string): string[] {
  const value = input.trim()
  const primary = resolvePoolApiBase(value)

  if (value.startsWith('pool/')) {
    // Legacy pool strings may point to a Socket.IO endpoint that doesn't expose /worker/* REST.
    return [primary, DEFAULT_HTTP_API]
  }

  return [primary]
}

