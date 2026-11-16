/** 只允许公网 https 版本封面；非法地址返回空串，避免渲染进程替外部地址发请求。 */
const LOCAL_HOST_SUFFIXES = ['.localhost', '.local', '.internal', '.home.arpa', '.lan']

const NON_PUBLIC_IPV6_PREFIXES = ['::', '64:ff9b:', '2001:db8:', '2002:', '2001:0:', 'fec0:']

const isNumericLabel = (part: string): boolean => /^\d+$/.test(part) || /^0x[0-9a-f]+$/i.test(part)

const isNonPublicIpv6 = (host: string): boolean => {
  const value = host.toLowerCase()
  if (NON_PUBLIC_IPV6_PREFIXES.some(prefix => value.startsWith(prefix))) return true
  if (value.startsWith('fc') || value.startsWith('fd')) return true
  if (/^fe[89ab]/.test(value)) return true
  if (value.startsWith('ff')) return true
  return false
}

export const safeCoverUrl = (value?: string): string => {
  const text = (value || '').trim()
  if (!text) return ''
  let url: URL
  try {
    url = new URL(text)
  } catch {
    return ''
  }
  if (url.protocol !== 'https:' || url.username || url.password) return ''
  const host = url.hostname.toLowerCase().replace(/\.+$/, '')
  if (!host || host === 'localhost') return ''
  if (LOCAL_HOST_SUFFIXES.some(suffix => host.endsWith(suffix))) return ''
  const ipv6 = host.startsWith('[') && host.endsWith(']') ? host.slice(1, -1) : host
  if (ipv6.includes(':')) return isNonPublicIpv6(ipv6) ? '' : url.href
  if (host.split('.').every(isNumericLabel)) return ''
  if (!host.includes('.')) return ''
  return url.href
}
