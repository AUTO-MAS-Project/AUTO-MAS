import { ApiError, MysteryService, type MysteryContextData } from '@/api'

export class MysteryContextError extends Error {}

export async function getMysteryContext(): Promise<MysteryContextData> {
  try {
    const response = await MysteryService.getMysteryContextApiMysteryContextGet()
    if (response.code !== 200 || !response.data) {
      throw new MysteryContextError(response.errorCode || 'CONTEXT_UNAVAILABLE')
    }
    return response.data
  } catch (error) {
    if (error instanceof ApiError) {
      const body: unknown = error.body
      if (
        body &&
        typeof body === 'object' &&
        'errorCode' in body &&
        typeof body.errorCode === 'string'
      ) {
        throw new MysteryContextError(body.errorCode)
      }
    }
    throw error
  }
}
