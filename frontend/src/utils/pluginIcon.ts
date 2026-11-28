export function pluginIconSrc(png?: string | null): string | undefined {
  return png ? `data:image/png;base64,${png}` : undefined
}
