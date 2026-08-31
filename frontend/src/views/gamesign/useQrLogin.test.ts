import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useQrLogin } from './useQrLogin'

const createQr = vi.fn()
const checkQr = vi.fn()
const saveQr = vi.fn()

vi.mock('./useGameSignApi', () => ({
  useGameSignApi: () => ({
    listAccounts: vi.fn(),
    reorderAccounts: vi.fn(),
    manualSign: vi.fn(),
    createMiyousheQr: createQr,
    checkMiyousheQr: checkQr,
    saveMiyousheQr: saveQr,
  }),
}))

vi.mock('qrcode', () => ({
  default: { toDataURL: vi.fn(async () => 'data:image/png;base64,QR') },
}))

const showSuccess = vi.fn()
const showError = vi.fn()

vi.mock('ant-design-vue', () => ({
  message: {
    get success() {
      return showSuccess
    },
    get error() {
      return showError
    },
  },
}))

const logWarn = vi.fn()
const logError = vi.fn()

const logger = {
  debug: vi.fn(),
  info: vi.fn(),
  warn: logWarn,
  error: logError,
} as unknown as Parameters<typeof useQrLogin>[0]['logger']

/** 模拟 openapi 生成的 CancelablePromise：立即兑现，cancel 无副作用 */
const cancelable = <T>(value: T) => {
  const promise = Promise.resolve(value) as Promise<T> & { cancel: () => void }
  promise.cancel = vi.fn()
  return promise
}

/**
 * 模拟请求失败。
 * 必须在调用时才构造 promise（配合 mockImplementationOnce），
 * 提前 new 出来会在没人 await 的那一刻触发 unhandledRejection。
 */
const failing = (error: Error) => {
  const promise = Promise.reject(error) as Promise<never> & { cancel: () => void }
  promise.cancel = vi.fn()
  return promise
}

/** 可以手动控制兑现时机的请求，用来构造「响应在途时会话被换掉」 */
const pendingCancelable = <T>() => {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  }) as Promise<T> & { cancel: () => void }
  promise.cancel = vi.fn(() => reject(new Error('canceled')))
  return { promise, resolve }
}

const CREATED = {
  code: 200,
  status: 'Init',
  qr_url: 'https://miyoushe.example/qr',
  ticket: 'ticket-1',
  device: 'device-1',
}

const setup = (getAccountId: () => string | undefined = () => 'acc-1') => {
  const onSaved = vi.fn()
  const qr = useQrLogin({ getAccountId, onSaved, logger })
  return { ...qr, onSaved }
}

describe('useQrLogin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('生成二维码后进入等待扫码态', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    const qr = setup()

    await qr.start()

    expect(qr.visible.value).toBe(true)
    expect(qr.status.value).toBe('waiting')
    expect(qr.qrCodeDataUrl.value).toBe('data:image/png;base64,QR')
    expect(qr.loading.value).toBe(false)
  })

  it('服务端少给 ticket/device 时报错，不进入轮询', async () => {
    createQr.mockReturnValueOnce(cancelable({ code: 200, qr_url: 'https://x' }))
    const qr = setup()

    await qr.start()
    await vi.advanceTimersByTimeAsync(6000)

    expect(qr.status.value).toBe('error')
    expect(qr.statusText.value).toContain('缺少登录信息')
    expect(checkQr).not.toHaveBeenCalled()
  })

  it('确认后保存凭据、提示成功，并在 1200ms 后自动关闭', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    checkQr.mockReturnValueOnce(cancelable({ code: 200, status: 'Confirmed', cookies_str: 'ck' }))
    saveQr.mockReturnValueOnce(cancelable({ code: 200, status: 'ok' }))
    const qr = setup()

    await qr.start()
    await vi.advanceTimersByTimeAsync(2000)

    expect(qr.onSaved).toHaveBeenCalledWith('acc-1', 'ck', expect.any(Function))
    expect(qr.status.value).toBe('done')
    expect(showSuccess).toHaveBeenCalledWith('米游社扫码登录成功')

    await vi.advanceTimersByTimeAsync(1200)
    expect(qr.visible.value).toBe(false)
    expect(qr.status.value).toBe('idle')
  })

  it('完整长 Cookie 不经截断传入原保存链路', async () => {
    const longCookie = `stoken_v2=v2_${'x'.repeat(4096)}.CAE=; mid=mid-value`
    createQr.mockReturnValueOnce(cancelable(CREATED))
    checkQr.mockReturnValueOnce(
      cancelable({ code: 200, status: 'Confirmed', cookies_str: longCookie })
    )
    saveQr.mockReturnValueOnce(cancelable({ code: 200, status: 'ok' }))
    const qr = setup()

    await qr.start()
    await vi.advanceTimersByTimeAsync(2000)

    expect(saveQr).toHaveBeenCalledWith('acc-1', longCookie)
    expect(qr.onSaved).toHaveBeenCalledWith('acc-1', longCookie, expect.any(Function))
  })

  it('取不到账号时跳过保存，直接进入成功态', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    checkQr.mockReturnValueOnce(cancelable({ code: 200, status: 'Confirmed', cookies_str: 'ck' }))
    const qr = setup(() => undefined)

    await qr.start()
    await vi.advanceTimersByTimeAsync(2000)

    expect(saveQr).not.toHaveBeenCalled()
    expect(qr.onSaved).not.toHaveBeenCalled()
    expect(qr.status.value).toBe('done')
  })

  it('确认了但没拿到 Cookie 时报错', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    checkQr.mockReturnValueOnce(cancelable({ code: 200, status: 'Confirmed', cookies_str: '' }))
    const qr = setup()

    await qr.start()
    await vi.advanceTimersByTimeAsync(2000)

    expect(qr.status.value).toBe('error')
    expect(qr.statusText.value).toContain('登录链路未返回完整凭据')
    expect(saveQr).not.toHaveBeenCalled()
  })

  it('已扫码但未确认时更新提示并继续轮询', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    checkQr.mockReturnValue(cancelable({ code: 200, status: 'Scanned' }))
    const qr = setup()

    await qr.start()
    await vi.advanceTimersByTimeAsync(2000)
    expect(qr.status.value).toBe('scanned')

    await vi.advanceTimersByTimeAsync(2000)
    expect(checkQr).toHaveBeenCalledTimes(2)
  })

  it('二维码过期时给出过期态，允许重新生成', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    checkQr.mockReturnValueOnce(cancelable({ code: 200, status: 'Expired' }))
    const qr = setup()

    await qr.start()
    await vi.advanceTimersByTimeAsync(2000)

    expect(qr.status.value).toBe('expired')
    expect(qr.qrCodeDataUrl.value).toBe('')
    // 过期后停轮询，等重新生成
    await vi.advanceTimersByTimeAsync(6000)
    expect(checkQr).toHaveBeenCalledTimes(1)

    createQr.mockReturnValueOnce(cancelable(CREATED))
    await qr.start()
    expect(qr.status.value).toBe('waiting')
  })

  it('后端报错文案带「二维码」时按过期处理，其它按查询失败', async () => {
    createQr.mockReturnValue(cancelable(CREATED))
    checkQr.mockReturnValueOnce(
      cancelable({ code: 500, status: 'error', message: '二维码不存在或已失效' })
    )
    const expiring = setup()
    await expiring.start()
    await vi.advanceTimersByTimeAsync(2000)
    expect(expiring.status.value).toBe('expired')

    checkQr.mockReturnValueOnce(cancelable({ code: 500, status: 'error', message: '服务繁忙' }))
    const failed = setup()
    await failed.start()
    await vi.advanceTimersByTimeAsync(2000)
    expect(failed.status.value).toBe('error')
    expect(failed.statusText.value).toBe('服务繁忙')
  })

  it('cancel() 停掉轮询并清空状态', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    const qr = setup()
    await qr.start()

    qr.cancel()
    await vi.advanceTimersByTimeAsync(6000)

    expect(checkQr).not.toHaveBeenCalled()
    expect(qr.visible.value).toBe(false)
    expect(qr.status.value).toBe('idle')
    expect(qr.qrCodeDataUrl.value).toBe('')
  })

  it('cancel() 幂等，连续调用不残留状态', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    const qr = setup()
    await qr.start()

    qr.cancel()
    qr.cancel()
    qr.cancel()

    expect(qr.visible.value).toBe(false)
    expect(qr.status.value).toBe('idle')
    expect(qr.statusText.value).toBe('')
  })

  it('创建请求在途时被取消，回来的响应不写状态', async () => {
    const inflight = pendingCancelable<typeof CREATED>()
    createQr.mockReturnValueOnce(inflight.promise)
    const qr = setup()

    const startPromise = qr.start()
    expect(qr.status.value).toBe('loading')

    // 取消会 abort 在途请求；即使响应随后回来也不能落到界面上
    qr.cancel()
    inflight.resolve(CREATED)
    await startPromise

    expect(qr.status.value).toBe('idle')
    expect(qr.qrCodeDataUrl.value).toBe('')
    expect(showError).not.toHaveBeenCalled()
  })

  it('轮询在途时被取消，回来的响应既不写状态也不弹提示', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    const inflight = pendingCancelable<{ code: number; status: string }>()
    checkQr.mockReturnValueOnce(inflight.promise)
    const qr = setup()

    await qr.start()
    await vi.advanceTimersByTimeAsync(2000)
    expect(checkQr).toHaveBeenCalledTimes(1)

    qr.cancel()
    inflight.resolve({ code: 200, status: 'Scanned' })
    await vi.advanceTimersByTimeAsync(0)

    expect(qr.status.value).toBe('idle')
    expect(qr.statusText.value).toBe('')
    expect(showError).not.toHaveBeenCalled()
  })

  it('轮询遇到临时网络错误时只记日志，继续轮询', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    checkQr.mockImplementationOnce(() => failing(new Error('network timeout')))
    checkQr.mockReturnValueOnce(cancelable({ code: 200, status: 'Scanned' }))
    const qr = setup()

    await qr.start()
    await vi.advanceTimersByTimeAsync(2000)
    // 网络抖动不改状态、不停轮询
    expect(qr.status.value).toBe('waiting')
    expect(logWarn).toHaveBeenCalledWith(expect.stringContaining('network timeout'))

    await vi.advanceTimersByTimeAsync(2000)
    expect(qr.status.value).toBe('scanned')
  })

  it('保存凭据失败时提示并转入错误态', async () => {
    createQr.mockReturnValueOnce(cancelable(CREATED))
    checkQr.mockReturnValueOnce(cancelable({ code: 200, status: 'Confirmed', cookies_str: 'ck' }))
    saveQr.mockReturnValueOnce(cancelable({ code: 500, status: 'error', message: '写库失败' }))
    const qr = setup()

    await qr.start()
    await vi.advanceTimersByTimeAsync(2000)

    expect(qr.status.value).toBe('error')
    expect(qr.statusText.value).toBe('扫码成功，但保存 Token 失败')
    expect(showError).toHaveBeenCalledWith('扫码成功，但保存 Token 失败')
    expect(showSuccess).not.toHaveBeenCalled()
    // 失败后不该留着自动关闭定时器
    await vi.advanceTimersByTimeAsync(2000)
    expect(qr.visible.value).toBe(true)
  })
})
