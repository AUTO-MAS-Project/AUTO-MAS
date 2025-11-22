/**
 * 镜像源 API 接口
 * 用于从后端获取最新的镜像源配置
 */

import { OpenAPI } from '@/api'
import type { MirrorConfig } from '@/types/mirror'

export interface MirrorApiResponse {
  git?: MirrorConfig[]
  python?: MirrorConfig[]
  pip?: MirrorConfig[]
  apiEndpoints?: {
    local?: string
    production?: string
    proxy?: string
  }
  downloadLinks?: {
    [category: string]: {
      [key: string]: string
    }
  }
}

/**
 * 获取镜像源配置
 */
export async function fetchMirrorConfig(): Promise<MirrorApiResponse> {
  try {
    const response = await fetch(`${OpenAPI.BASE}/api/mirrors`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return await response.json()
  } catch (error) {
    console.warn('获取镜像源配置失败，使用默认配置:', error)
    throw error
  }
}

/**
 * 测试镜像源连通性
 */
export async function testMirrorConnectivity(
  url: string,
  timeout: number = 5000
): Promise<{
  success: boolean
  speed: number
  error?: string
}> {
  try {
    const startTime = Date.now()
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    const response = await fetch(url, {
      method: 'HEAD',
      signal: controller.signal,
      cache: 'no-cache',
      mode: 'no-cors', // 避免 CORS 问题
    })

    clearTimeout(timeoutId)
    const speed = Date.now() - startTime

    return {
      success: true,
      speed,
    }
  } catch (error) {
    return {
      success: false,
      speed: 9999,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

/**
 * 批量测试镜像源
 */
export async function batchTestMirrors(mirrors: MirrorConfig[]): Promise<MirrorConfig[]> {
  const promises = mirrors.map(async mirror => {
    const result = await testMirrorConnectivity(mirror.url)
    return {
      ...mirror,
      speed: result.speed,
    }
  })

  const results = await Promise.all(promises)

  // 按速度排序
  return results.sort((a, b) => (a.speed || 9999) - (b.speed || 9999))
}
