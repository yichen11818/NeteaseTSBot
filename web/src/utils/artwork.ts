// Old search results and browser favorites can still contain HTTP CDN URLs.
export function artworkUrl(value: unknown): string {
  const raw = String(value ?? '').trim()
  const url = raw.startsWith('//') ? `https:${raw}` : raw
  try {
    const parsed = new URL(url)
    if (parsed.protocol === 'http:' && (parsed.hostname === 'hdslb.com' || parsed.hostname.endsWith('.hdslb.com'))) {
      return url.replace(/^http:/i, 'https:')
    }
  } catch { /* Keep local demo assets and relative URLs unchanged. */ }
  return url
}
