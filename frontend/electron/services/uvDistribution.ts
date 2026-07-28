import type { MirrorSource } from './mirrorService'

export const UV_ARCHIVE_NAME = 'uv-x86_64-pc-windows-msvc.zip'
export const UV_FALLBACK_VERSION = '0.11.33'
export const UV_FALLBACK_SHA256 = 'c253ce868ad48d29327b661452ce184c9e333e6d6f5bc8d6fcfbf4dd52b83442'
export const UV_LATEST_METADATA_URL = 'https://uv.agentsmirror.com/metadata/uv-latest.json'
export const UV_GITHUB_LATEST_API_URL = 'https://api.github.com/repos/astral-sh/uv/releases/latest'

function getGithubReleaseUrl(version: string): string {
  return `https://github.com/astral-sh/uv/releases/download/${version}/${UV_ARCHIVE_NAME}`
}

/**
 * 为已解析出的 uv 版本创建下载源。
 *
 * 先解析 latest 为具体版本，再生成固定 URL，避免各镜像的 latest 同步时差。
 */
export function createUvMirrors(version: string = UV_FALLBACK_VERSION): MirrorSource[] {
  const githubReleaseUrl = getGithubReleaseUrl(version)

  return [
    {
      key: 'github_agentsmirror',
      name: 'uv-custom 公益镜像',
      url: `https://uv.agentsmirror.com/github/astral-sh/uv/releases/download/${version}/${UV_ARCHIVE_NAME}`,
      type: 'mirror',
      description: '面向中国大陆的 uv release 公益镜像',
    },
    {
      key: 'ghproxy_fastly',
      name: 'gh-proxy (Fastly CDN)',
      url: `https://cdn.gh-proxy.com/${githubReleaseUrl}`,
      type: 'mirror',
      description: 'Fastly CDN 镜像',
    },
    {
      key: 'ghproxy_cloudflare',
      name: 'gh-proxy (Cloudflare)',
      url: `https://gh-proxy.com/${githubReleaseUrl}`,
      type: 'mirror',
      description: 'Cloudflare CDN 镜像',
    },
    {
      key: 'ghproxy_edgeone',
      name: 'gh-proxy (EdgeOne)',
      url: `https://edgeone.gh-proxy.com/${githubReleaseUrl}`,
      type: 'mirror',
      description: 'EdgeOne CDN 镜像',
    },
    {
      key: 'ghfast',
      name: 'ghfast 镜像',
      url: `https://ghfast.top/${githubReleaseUrl}`,
      type: 'mirror',
      description: '第三方 GitHub Release 镜像，低优先级尝试',
    },
    {
      key: 'github',
      name: 'GitHub 官方',
      url: githubReleaseUrl,
      type: 'official',
      description: 'Astral 官方 GitHub Release，作为最终兜底',
    },
  ]
}

export function createUvChecksumUrls(version: string): string[] {
  const githubChecksumUrl = `${getGithubReleaseUrl(version)}.sha256`

  return [
    `https://uv.agentsmirror.com/github/astral-sh/uv/releases/download/${version}/${UV_ARCHIVE_NAME}.sha256`,
    `https://cdn.gh-proxy.com/${githubChecksumUrl}`,
    `https://gh-proxy.com/${githubChecksumUrl}`,
    `https://edgeone.gh-proxy.com/${githubChecksumUrl}`,
    `https://ghfast.top/${githubChecksumUrl}`,
    githubChecksumUrl,
    `https://releases.astral.sh/github/uv/releases/download/${version}/${UV_ARCHIVE_NAME}.sha256`,
  ]
}
