export interface SnapshotCoordinatorOptions<T> {
  load: () => Promise<T>
  apply: (snapshot: T) => void
  reportError: (error: unknown) => void
}

/**
 * 串行化 AppLayout 插件快照读取，并阻止旧 HTTP 响应覆盖较新的本地/WS 状态。
 */
export class AppLayoutSnapshotCoordinator<T> {
  private generation = 0
  private inFlight: Promise<void> | null = null
  private freshRequested = false

  constructor(private readonly options: SnapshotCoordinatorOptions<T>) {}

  /** 使当前在途 HTTP 响应失效，但不主动发起新的读取。 */
  invalidate(): void {
    this.generation++
  }

  /** 应用较新的 WS 或本地插件状态，并使旧 HTTP 响应失效。 */
  applyMutation(snapshot: T): void {
    this.invalidate()
    this.options.apply(snapshot)
  }

  /** 共享当前读取；同一时刻最多存在一个 HTTP 请求。 */
  refresh(): Promise<void> {
    if (this.inFlight) return this.inFlight
    this.inFlight = this.drainRefreshes()
    return this.inFlight
  }

  /**
   * 请求一份连接代次对应的新快照。
   *
   * 若旧代次仍在读取，先让其失效，待其结束后串行补取一次最新快照。
   */
  refreshFresh(): Promise<void> {
    this.invalidate()
    if (this.inFlight) this.freshRequested = true
    return this.refresh()
  }

  private async drainRefreshes(): Promise<void> {
    try {
      do {
        this.freshRequested = false
        const generation = this.generation
        try {
          const snapshot = await this.options.load()
          if (generation === this.generation) this.options.apply(snapshot)
        } catch (error) {
          if (generation === this.generation) this.options.reportError(error)
        }
      } while (this.freshRequested)
    } finally {
      this.inFlight = null
    }
  }
}
