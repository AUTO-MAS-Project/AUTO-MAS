/**
 * 初始化写操作互斥锁。
 *
 * Electron 主进程内只允许一个安装、更新或插件引导操作修改运行时目录。
 */

export class InitializationOperationBusyError extends Error {
  constructor(public readonly activeOperation: string) {
    super(`初始化操作正在执行: ${activeOperation}`)
    this.name = 'InitializationOperationBusyError'
  }
}

export class InitializationOperationLock {
  private activeOperation: string | null = null

  async runExclusive<T>(operationName: string, operation: () => Promise<T>): Promise<T> {
    if (this.activeOperation) {
      throw new InitializationOperationBusyError(this.activeOperation)
    }

    this.activeOperation = operationName
    try {
      return await operation()
    } finally {
      this.activeOperation = null
    }
  }

  getActiveOperation(): string | null {
    return this.activeOperation
  }
}
