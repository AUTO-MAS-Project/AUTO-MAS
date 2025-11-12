import { ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import type { TaskStatusItem, TaskDetailItem, TaskQueueItem } from '@/api/models'

// 状态恢复错误类型
export enum StateRecoveryError {
  NETWORK_ERROR = 'NETWORK_ERROR',
  INVALID_TASK_DATA = 'INVALID_TASK_DATA',
  WEBSOCKET_CONNECTION_FAILED = 'WEBSOCKET_CONNECTION_FAILED',
  TASK_NOT_FOUND = 'TASK_NOT_FOUND',
  RECOVERY_TIMEOUT = 'RECOVERY_TIMEOUT'
}

// 任务恢复数据接口
export interface TaskRecoveryData {
  taskId: string
  mode: string
  status: string
  name: string
  createdAt: string
  taskQueue: TaskQueueItem[]
  userQueue: TaskQueueItem[]
  isRunning: boolean
  completedAt?: string
}

// 状态恢复配置
const RECOVERY_TIMEOUT = 10000 // 10秒超时
const MAX_RETRY_ATTEMPTS = 3
const RETRY_DELAY = 1000 // 1秒重试延迟

// 缓存配置
const CACHE_KEY = 'scheduler-state-cache'
const CACHE_TTL = 30000 // 30秒缓存生存时间
const MAX_CACHE_SIZE = 10 // 最大缓存条目数

// 缓存接口
interface StateCache {
  timestamp: number
  tasks: TaskRecoveryData[]
  ttl: number
}

interface CacheEntry {
  key: string
  data: any
  timestamp: number
  ttl: number
}

export function useSchedulerStateRecovery() {
  // 状态管理
  const isRecovering = ref(false)
  const recoveryError = ref<string | null>(null)
  const recoveryProgress = ref(0)
  const retryAttempts = ref(0)

  // 缓存管理
  const cacheStore = ref(new Map<string, CacheEntry>())

  /**
   * 清除错误状态
   */
  const clearError = () => {
    recoveryError.value = null
  }

  // 缓存管理方法
  const getCachedState = (): StateCache | null => {
    try {
      const cached = localStorage.getItem(CACHE_KEY)
      if (!cached) return null

      const cache: StateCache = JSON.parse(cached)
      const now = Date.now()

      // 检查缓存是否过期
      if (now - cache.timestamp > cache.ttl) {
        localStorage.removeItem(CACHE_KEY)
        return null
      }

      return cache
    } catch (error) {
      console.error('读取缓存失败:', error)
      localStorage.removeItem(CACHE_KEY)
      return null
    }
  }

  const setCachedState = (tasks: TaskRecoveryData[]) => {
    try {
      const cache: StateCache = {
        timestamp: Date.now(),
        tasks,
        ttl: CACHE_TTL
      }

      localStorage.setItem(CACHE_KEY, JSON.stringify(cache))
    } catch (error) {
      console.error('写入缓存失败:', error)
      // 如果存储空间不足，清理旧缓存
      try {
        localStorage.removeItem(CACHE_KEY)
        localStorage.setItem(CACHE_KEY, JSON.stringify({
          timestamp: Date.now(),
          tasks,
          ttl: CACHE_TTL
        }))
      } catch (retryError) {
        console.error('重试写入缓存失败:', retryError)
      }
    }
  }

  const clearCache = () => {
    localStorage.removeItem(CACHE_KEY)
    cacheStore.value.clear()
  }

  const getCacheEntry = (key: string): any => {
    const entry = cacheStore.value.get(key)
    if (!entry) return null

    const now = Date.now()
    if (now - entry.timestamp > entry.ttl) {
      cacheStore.value.delete(key)
      return null
    }

    return entry.data
  }

  const setCacheEntry = (key: string, data: any, ttl: number = CACHE_TTL) => {
    // 限制缓存大小
    if (cacheStore.value.size >= MAX_CACHE_SIZE) {
      // 删除最旧的缓存条目
      const oldestKey = Array.from(cacheStore.value.entries())
        .sort(([, a], [, b]) => a.timestamp - b.timestamp)[0]?.[0]
      
      if (oldestKey) {
        cacheStore.value.delete(oldestKey)
      }
    }

    cacheStore.value.set(key, {
      key,
      data,
      timestamp: Date.now(),
      ttl
    })
  }

  /**
   * 设置错误状态
   */
  const setError = (error: StateRecoveryError, details?: string) => {
    const errorMessages = {
      [StateRecoveryError.NETWORK_ERROR]: '网络连接失败，请检查网络连接',
      [StateRecoveryError.INVALID_TASK_DATA]: '任务数据格式无效',
      [StateRecoveryError.WEBSOCKET_CONNECTION_FAILED]: 'WebSocket连接失败',
      [StateRecoveryError.TASK_NOT_FOUND]: '任务不存在',
      [StateRecoveryError.RECOVERY_TIMEOUT]: '状态恢复超时'
    }
    
    const baseMessage = errorMessages[error] || '未知错误'
    recoveryError.value = details ? `${baseMessage}: ${details}` : baseMessage
  }

  /**
   * 验证任务数据的有效性
   */
  const validateTaskData = (task: any): task is TaskStatusItem => {
    if (!task || typeof task !== 'object') {
      return false
    }

    const requiredFields = ['task_id', 'mode', 'status', 'name', 'created_at']
    for (const field of requiredFields) {
      if (!task[field] || typeof task[field] !== 'string') {
        return false
      }
    }

    // 验证队列数据
    if (task.task_queue && !Array.isArray(task.task_queue)) {
      return false
    }
    if (task.user_queue && !Array.isArray(task.user_queue)) {
      return false
    }

    return true
  }

  /**
   * 转换任务数据为恢复数据格式
   */
  const transformTaskData = (task: TaskStatusItem): TaskRecoveryData => {
    return {
      taskId: task.task_id,
      mode: task.mode,
      status: task.status,
      name: task.name,
      createdAt: task.created_at,
      taskQueue: task.task_queue || [],
      userQueue: task.user_queue || [],
      isRunning: task.status === 'running'
    }
  }

  /**
   * 转换详细任务数据为恢复数据格式
   */
  const transformDetailData = (task: TaskDetailItem): TaskRecoveryData => {
    return {
      taskId: task.task_id,
      mode: task.mode,
      status: task.status,
      name: task.name,
      createdAt: task.created_at,
      taskQueue: task.task_queue || [],
      userQueue: task.user_queue || [],
      isRunning: task.is_running,
      completedAt: task.completed_at
    }
  }

  /**
   * 带重试机制的API调用
   */
  const callWithRetry = async <T>(
    apiCall: () => Promise<T>,
    maxRetries: number = MAX_RETRY_ATTEMPTS
  ): Promise<T> => {
    let lastError: Error | null = null
    
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        retryAttempts.value = attempt
        return await apiCall()
      } catch (error) {
        lastError = error as Error
        
        if (attempt < maxRetries) {
          // 等待后重试
          await new Promise(resolve => setTimeout(resolve, RETRY_DELAY * (attempt + 1)))
        }
      }
    }
    
    throw lastError
  }

  /**
   * 恢复调度器状态
   */
  const recoverSchedulerState = async (useCache: boolean = true): Promise<TaskRecoveryData[]> => {
    if (isRecovering.value) {
      throw new Error('状态恢复正在进行中')
    }

    // 尝试从缓存获取数据
    if (useCache) {
      const cached = getCachedState()
      if (cached) {
        console.log('使用缓存的状态数据')
        return cached.tasks
      }
    }

    try {
      isRecovering.value = true
      recoveryProgress.value = 0
      clearError()

      // 设置超时
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(() => {
          reject(new Error('RECOVERY_TIMEOUT'))
        }, RECOVERY_TIMEOUT)
      })

      // 执行状态恢复
      const recoveryPromise = async (): Promise<TaskRecoveryData[]> => {
        recoveryProgress.value = 20

        // 调用后端API获取运行中任务状态
        console.log('调用临时状态恢复API: /api/dispatch/stop-status')
        
        // 先测试一个已知存在的API来验证连接
        try {
          console.log('测试基础API连接...')
          const testResponse = await Service.getGitVersionApiInfoVersionPost()
          console.log('基础API连接正常:', testResponse)
        } catch (testError) {
          console.error('基础API连接失败:', testError)
          throw new Error(`网络连接失败: ${testError}`)
        }
        
        // 直接调用临时API
        const response = await callWithRetry(async () => {
          // 临时使用fetch直接调用
          const fetchResponse = await fetch('/api/dispatch/stop-status', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            }
          })
          
          if (!fetchResponse.ok) {
            throw new Error(`HTTP ${fetchResponse.status}: ${fetchResponse.statusText}`)
          }
          
          const data = await fetchResponse.json()
          console.log('临时API响应:', data)
          
          // 模拟TaskStatusOut格式
          return {
            code: data.code || 200,
            status: data.status || 'success',
            message: data.message || '成功',
            data: [] // 空的任务列表
          }
        })
        
        console.log('API响应:', response)

        recoveryProgress.value = 60

        if (response.code !== 200) {
          throw new Error(`API调用失败: ${response.message}`)
        }

        if (!response.data || !Array.isArray(response.data)) {
          setError(StateRecoveryError.INVALID_TASK_DATA, '响应数据格式无效')
          return []
        }

        recoveryProgress.value = 80

        // 验证和转换数据
        const validTasks: TaskRecoveryData[] = []
        for (const task of response.data) {
          if (validateTaskData(task)) {
            validTasks.push(transformTaskData(task))
          } else {
            console.warn('跳过无效的任务数据:', task)
          }
        }

        recoveryProgress.value = 100

        // 缓存结果
        if (validTasks.length > 0) {
          setCachedState(validTasks)
        }

        return validTasks
      }

      // 竞争执行：要么成功恢复，要么超时
      const result = await Promise.race([recoveryPromise(), timeoutPromise])
      
      return result

    } catch (error) {
      const err = error as Error
      console.error('状态恢复API调用失败:', error)
      
      if (err.message === 'RECOVERY_TIMEOUT') {
        setError(StateRecoveryError.RECOVERY_TIMEOUT)
      } else if (err.message?.includes('网络') || err.message?.includes('Network') || err.message?.includes('Not Found')) {
        setError(StateRecoveryError.NETWORK_ERROR, err.message)
      } else {
        setError(StateRecoveryError.INVALID_TASK_DATA, err.message)
      }
      
      throw error
    } finally {
      isRecovering.value = false
      retryAttempts.value = 0
    }
  }

  /**
   * 恢复单个任务的详细状态
   */
  const recoverTaskDetail = async (taskId: string): Promise<TaskRecoveryData | null> => {
    try {
      clearError()

      const response = await callWithRetry(async () => {
        return await Service.getTaskStatusApiDispatchStatusTaskIdPost(taskId)
      })

      if (response.code === 404) {
        setError(StateRecoveryError.TASK_NOT_FOUND, `任务 ${taskId} 不存在`)
        return null
      }

      if (response.code !== 200) {
        throw new Error(`API调用失败: ${response.message}`)
      }

      if (!response.data) {
        return null
      }

      return transformDetailData(response.data)

    } catch (error) {
      const err = error as Error
      
      if (err.message?.includes('网络') || err.message?.includes('Network')) {
        setError(StateRecoveryError.NETWORK_ERROR, err.message)
      } else {
        setError(StateRecoveryError.INVALID_TASK_DATA, err.message)
      }
      
      throw error
    }
  }

  /**
   * 处理恢复错误
   */
  const handleRecoveryError = (error: StateRecoveryError, context?: any) => {
    console.error('状态恢复错误:', error, context)
    
    switch (error) {
      case StateRecoveryError.NETWORK_ERROR:
        message.error({
          content: '网络连接失败，请检查网络连接后重试',
          duration: 5,
          key: 'recovery-error'
        })
        break
      case StateRecoveryError.WEBSOCKET_CONNECTION_FAILED:
        message.warning({
          content: 'WebSocket连接失败，部分功能可能受限',
          duration: 3,
          key: 'websocket-error'
        })
        break
      case StateRecoveryError.RECOVERY_TIMEOUT:
        message.error({
          content: '状态恢复超时，请检查网络连接或重试',
          duration: 5,
          key: 'timeout-error'
        })
        break
      case StateRecoveryError.TASK_NOT_FOUND:
        message.warning({
          content: '部分任务已不存在，已自动清理',
          duration: 3,
          key: 'task-not-found'
        })
        break
      case StateRecoveryError.INVALID_TASK_DATA:
        message.error({
          content: '任务数据格式异常，请刷新页面重试',
          duration: 5,
          key: 'invalid-data'
        })
        break
      default:
        message.error({
          content: '状态恢复失败，请重试或联系技术支持',
          duration: 5,
          key: 'unknown-error'
        })
    }
  }

  /**
   * 网络错误重试机制
   */
  const handleNetworkError = async (originalError: Error): Promise<void> => {
    console.log('处理网络错误，尝试重连...')
    
    // 等待网络恢复
    let retryCount = 0
    const maxRetries = 3
    const retryDelay = 2000
    
    while (retryCount < maxRetries) {
      try {
        // 简单的网络连通性测试
        await fetch('/api/info/version', { method: 'POST' })
        console.log('网络连接已恢复')
        return
      } catch (error) {
        retryCount++
        if (retryCount < maxRetries) {
          console.log(`网络重连尝试 ${retryCount}/${maxRetries}`)
          await new Promise(resolve => setTimeout(resolve, retryDelay * retryCount))
        }
      }
    }
    
    throw new Error('网络连接恢复失败')
  }

  /**
   * WebSocket连接失败的降级处理
   */
  const handleWebSocketFailure = () => {
    console.log('WebSocket连接失败，启用轮询模式')
    
    // 这里可以实现轮询逻辑作为降级方案
    // 例如定期调用状态查询API
    const pollInterval = setInterval(async () => {
      try {
        const tasks = await recoverSchedulerState()
        console.log('轮询获取到任务状态:', tasks.length)
        
        // 如果没有运行中的任务，停止轮询
        if (tasks.length === 0 || !tasks.some(task => task.isRunning)) {
          clearInterval(pollInterval)
          console.log('没有运行中的任务，停止轮询')
        }
      } catch (error) {
        console.error('轮询状态失败:', error)
        clearInterval(pollInterval)
      }
    }, 5000) // 每5秒轮询一次
    
    // 设置轮询超时
    setTimeout(() => {
      clearInterval(pollInterval)
      console.log('轮询超时，停止轮询')
    }, 300000) // 5分钟后停止轮询
  }

  /**
   * 超时处理
   */
  const handleTimeout = (operation: string) => {
    console.warn(`操作超时: ${operation}`)
    
    message.warning({
      content: `${operation}超时，请检查网络连接`,
      duration: 3,
      key: 'timeout-warning'
    })
  }

  // 性能优化方法
  const debounce = <T extends (...args: any[]) => any>(
    func: T,
    wait: number
  ): ((...args: Parameters<T>) => void) => {
    let timeout: ReturnType<typeof setTimeout>
    
    return (...args: Parameters<T>) => {
      clearTimeout(timeout)
      timeout = setTimeout(() => func(...args), wait)
    }
  }

  const throttle = <T extends (...args: any[]) => any>(
    func: T,
    limit: number
  ): ((...args: Parameters<T>) => void) => {
    let inThrottle: boolean
    
    return (...args: Parameters<T>) => {
      if (!inThrottle) {
        func(...args)
        inThrottle = true
        setTimeout(() => inThrottle = false, limit)
      }
    }
  }

  const batchProcess = async <T, R>(
    items: T[],
    processor: (item: T) => Promise<R>,
    batchSize: number = 5
  ): Promise<R[]> => {
    const results: R[] = []
    
    for (let i = 0; i < items.length; i += batchSize) {
      const batch = items.slice(i, i + batchSize)
      const batchResults = await Promise.all(batch.map(processor))
      results.push(...batchResults)
      
      // 在批次之间添加小延迟，避免过载
      if (i + batchSize < items.length) {
        await new Promise(resolve => setTimeout(resolve, 100))
      }
    }
    
    return results
  }

  const optimizeMemoryUsage = () => {
    // 清理过期的缓存条目
    const now = Date.now()
    const expiredKeys: string[] = []
    
    cacheStore.value.forEach((entry, key) => {
      if (now - entry.timestamp > entry.ttl) {
        expiredKeys.push(key)
      }
    })
    
    expiredKeys.forEach(key => cacheStore.value.delete(key))
    
    // 如果缓存仍然过大，删除最旧的条目
    if (cacheStore.value.size > MAX_CACHE_SIZE) {
      const sortedEntries = Array.from(cacheStore.value.entries())
        .sort(([, a], [, b]) => a.timestamp - b.timestamp)
      
      const toDelete = sortedEntries.slice(0, cacheStore.value.size - MAX_CACHE_SIZE)
      toDelete.forEach(([key]) => cacheStore.value.delete(key))
    }
    
    console.log(`内存优化完成，当前缓存条目数: ${cacheStore.value.size}`)
  }

  const getCacheStats = () => {
    const now = Date.now()
    const entries = Array.from(cacheStore.value.values())
    
    return {
      totalEntries: entries.length,
      expiredEntries: entries.filter(entry => now - entry.timestamp > entry.ttl).length,
      memoryUsage: JSON.stringify(entries).length,
      oldestEntry: entries.length > 0 ? Math.min(...entries.map(e => e.timestamp)) : null,
      newestEntry: entries.length > 0 ? Math.max(...entries.map(e => e.timestamp)) : null
    }
  }

  /**
   * 重试状态恢复
   */
  const retryRecovery = async (): Promise<TaskRecoveryData[]> => {
    clearError()
    return await recoverSchedulerState()
  }

  return {
    // 状态
    isRecovering: isRecovering as Ref<boolean>,
    recoveryError: recoveryError as Ref<string | null>,
    recoveryProgress: recoveryProgress as Ref<number>,
    retryAttempts: retryAttempts as Ref<number>,

    // 方法
    recoverSchedulerState,
    recoverTaskDetail,
    handleRecoveryError,
    retryRecovery,
    clearError,

    // 错误处理
    handleNetworkError,
    handleWebSocketFailure,
    handleTimeout,

    // 缓存管理
    getCachedState,
    setCachedState,
    clearCache,
    getCacheEntry,
    setCacheEntry,

    // 性能优化
    debounce,
    throttle,
    batchProcess,
    optimizeMemoryUsage,
    getCacheStats,

    // 工具方法
    validateTaskData,
    transformTaskData,
    transformDetailData
  }
}