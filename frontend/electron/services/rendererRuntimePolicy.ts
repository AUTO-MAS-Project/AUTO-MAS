/** A packaged application must never load a renderer supplied by an inherited dev-server variable. */
export function getRendererDevServerUrl(
  isPackaged: boolean,
  configuredUrl: string | undefined = process.env.VITE_DEV_SERVER_URL
): string | undefined {
  if (isPackaged) return undefined
  const normalized = configuredUrl?.trim()
  return normalized || undefined
}
