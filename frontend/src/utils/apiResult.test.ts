import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api'
import { apiErrorMessage, requestApi, responseError } from './apiResult'

describe('api result helpers', () => {
  it('keeps ordinary errors and fallback messages predictable', () => {
    expect(apiErrorMessage(new Error('failed'), 'fallback')).toBe('failed')
    expect(apiErrorMessage({}, 'fallback')).toBe('fallback')
  })

  it('normalizes the standard response envelope', () => {
    expect(responseError({ code: 200 }, 'failed')).toBeNull()
    expect(responseError({ code: 500, message: 'backend failed' }, 'failed')?.message).toBe(
      'backend failed'
    )
  })

  it('reports validation fields without exposing rejected credentials', () => {
    const error = new ApiError(
      { method: 'POST', url: '/setting' },
      {
        url: '/setting',
        ok: false,
        status: 422,
        statusText: 'Unprocessable Entity',
        body: {
          detail: [
            { loc: ['body', 'data', 'password'], msg: 'Invalid value', input: 'secret-password' },
          ],
        },
      },
      'Validation failed'
    )
    expect(apiErrorMessage(error, 'fallback')).toBe('body.data.password: Invalid value')
    expect(apiErrorMessage(error, 'fallback')).not.toContain('secret-password')
  })

  it('returns successful data and rejects a business failure', async () => {
    const result = { code: 200, data: { enabled: true } }
    await expect(requestApi(async () => result, 'fallback')).resolves.toBe(result)
    await expect(
      requestApi(async () => ({ code: 409, message: 'Task locked' }), 'fallback')
    ).rejects.toThrow('Task locked')
  })

  it('does not retry failed triggers and preserves backend error messages', async () => {
    const request = vi.fn(async () => {
      throw new ApiError(
        { method: 'POST', url: '/update' },
        {
          url: '/update',
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
          body: { message: 'Trigger failed' },
        },
        'HTTP failed'
      )
    })
    await expect(requestApi(request, 'fallback')).rejects.toThrow('Trigger failed')
    expect(request).toHaveBeenCalledTimes(1)
  })
})
