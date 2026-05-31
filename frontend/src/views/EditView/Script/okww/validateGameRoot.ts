import { OpenAPI } from '@/api'

type ValidateGameRootResponse = {
  valid: boolean
  message?: string
}

/** 调用 Okww 专项后端接口校验鸣潮游戏根目录 */
export async function validateWutheringGameRootSelection(
  pickedFolder: string,
): Promise<ValidateGameRootResponse> {
  const response = await fetch(`${OpenAPI.BASE}/api/okww/validate-game-root`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pickedFolder }),
  })
  if (!response.ok) {
    throw new Error(`校验游戏根目录失败: HTTP ${response.status}`)
  }
  return response.json() as Promise<ValidateGameRootResponse>
}
