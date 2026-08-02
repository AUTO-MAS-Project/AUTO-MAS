/**
 * 智能下载服务
 * 重构版本 - 独立实现，支持单线程和多线程下载
 */

import * as fs from 'fs'
import * as https from 'https'
import * as http from 'http'

// 导入日志服务
import { getLogger } from './logger'
const logger = getLogger('下载服务')

// ==================== 类型定义 ====================

export interface DownloadProgress {
  progress: number // 百分比 0-100
  speed: number // 字节/秒
  downloadedSize: number
  totalSize: number
}

export type ProgressCallback = (progress: DownloadProgress) => void

interface DownloadChunk {
  start: number
  end: number
  index: number
  data: Buffer[]
  completed: boolean
}

export interface DownloadOptions {
  idleTimeoutMs?: number
  overallTimeoutMs?: number
  maxRedirects?: number
  maxBytes?: number
}

interface DownloadContext {
  options: DownloadOptions
  deadline?: number
  abortController: AbortController
}

function resolveHttpRedirect(currentUrl: string, location: string): string {
  let redirectUrl: URL
  try {
    redirectUrl = new URL(location, currentUrl)
  } catch {
    throw new Error(`无效的下载重定向地址: ${location}`)
  }

  if (redirectUrl.protocol !== 'http:' && redirectUrl.protocol !== 'https:') {
    throw new Error(`不支持的下载重定向协议: ${redirectUrl.protocol}`)
  }

  return redirectUrl.toString()
}

// ==================== 智能下载类 ====================

export class SmartDownloader {
  private readonly MIN_SIZE_FOR_MULTITHREAD = 10 * 1024 * 1024 // 10MB

  /**
   * 智能下载方法
   * 自动判断是否使用多线程下载
   */
  async download(
    url: string,
    savePath: string,
    onProgress?: ProgressCallback,
    options: DownloadOptions = {}
  ): Promise<{ success: boolean; error?: string }> {
    logger.info('=== 开始智能下载 ===')
    logger.info(`URL: ${url}`)
    logger.info(`保存路径: ${savePath}`)

    try {
      const context: DownloadContext = {
        options,
        deadline:
          options.overallTimeoutMs === undefined
            ? undefined
            : Date.now() + options.overallTimeoutMs,
        abortController: new AbortController(),
      }

      // 1. 获取文件头信息
      const fileInfo = await this.getFileInfo(url, context)

      if (!fileInfo.isFile) {
        throw new Error('URL 返回的不是文件类型')
      }

      logger.info(`文件大小: ${(fileInfo.size / 1024 / 1024).toFixed(2)} MB`)
      logger.info(`支持 Range: ${fileInfo.supportsRange}`)

      // 2. 判断下载方式
      const useMultiThread = fileInfo.supportsRange && fileInfo.size > this.MIN_SIZE_FOR_MULTITHREAD

      if (useMultiThread) {
        logger.info('使用多线程下载')
        return await this.multiThreadDownload(url, savePath, fileInfo.size, onProgress, 4, context)
      } else {
        logger.info('使用单线程下载')
        return await this.singleThreadDownload(url, savePath, fileInfo.size, onProgress, context)
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`❌ 下载失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }
  }

  /**
   * 获取文件信息
   */
  private getFileInfo(
    url: string,
    context: DownloadContext,
    redirectCount: number = 0
  ): Promise<{
    isFile: boolean
    size: number
    supportsRange: boolean
  }> {
    return new Promise((resolve, reject) => {
      const client = url.startsWith('https') ? https : http
      const remaining = this.getRemainingTime(context)
      if (remaining !== undefined && remaining <= 0) {
        reject(new Error('下载总时限已用尽'))
        return
      }

      const req = client.request(
        url,
        {
          method: 'HEAD',
          timeout: context.options.idleTimeoutMs ?? 10000,
          signal: context.abortController.signal,
        },
        response => {
          if (overallTimer) clearTimeout(overallTimer)

          // 处理重定向 (301, 302, 307, 308)
          if (response.statusCode && [301, 302, 307, 308].includes(response.statusCode)) {
            const redirectUrl = response.headers.location
            if (redirectUrl) {
              if (
                context.options.maxRedirects !== undefined &&
                redirectCount >= context.options.maxRedirects
              ) {
                req.destroy()
                reject(new Error(`获取文件信息重定向超过 ${context.options.maxRedirects} 次`))
                return
              }
              logger.debug(`跟随重定向: ${response.statusCode} -> ${redirectUrl}`)
              req.destroy() // 销毁原请求
              let nextUrl: string
              try {
                nextUrl = resolveHttpRedirect(url, redirectUrl)
              } catch (error) {
                reject(error)
                return
              }
              this.getFileInfo(nextUrl, context, redirectCount + 1)
                .then(resolve)
                .catch(reject)
              return
            }
          }

          const contentType = response.headers['content-type'] || ''
          const contentLength = response.headers['content-length']
          const acceptRanges = response.headers['accept-ranges']
          const size = parseInt(contentLength || '0', 10)

          if (context.options.maxBytes !== undefined && size > context.options.maxBytes) {
            reject(new Error(`下载文件超过大小限制 ${context.options.maxBytes} 字节`))
            return
          }

          // 判断是否为文件
          const isFile = !contentType.includes('text/html') && contentLength !== undefined

          resolve({
            isFile,
            size,
            supportsRange: acceptRanges === 'bytes',
          })
        }
      )
      const overallTimer =
        remaining === undefined
          ? undefined
          : setTimeout(() => {
              req.destroy()
              reject(new Error('下载总时限已用尽'))
            }, remaining)

      req.on('error', error => {
        if (overallTimer) clearTimeout(overallTimer)
        reject(error)
      })
      req.on('timeout', () => {
        if (overallTimer) clearTimeout(overallTimer)
        req.destroy()
        reject(new Error('获取文件信息超时'))
      })
      req.end()
    })
  }

  /**
   * 单线程下载
   */
  private singleThreadDownload(
    url: string,
    savePath: string,
    totalSize: number,
    onProgress?: ProgressCallback,
    context: DownloadContext = { options: {}, abortController: new AbortController() },
    redirectCount: number = 0
  ): Promise<{ success: boolean; error?: string }> {
    return new Promise(resolve => {
      const client = url.startsWith('https') ? https : http
      let file: fs.WriteStream | undefined
      let activeResponse: http.IncomingMessage | undefined
      let settled = false

      let downloadedSize = 0
      let lastTime = Date.now()
      let lastDownloaded = 0

      const remaining = this.getRemainingTime(context)
      if (remaining !== undefined && remaining <= 0) {
        resolve({ success: false, error: '下载总时限已用尽' })
        return
      }

      const finish = (
        result: { success: boolean; error?: string },
        removePartial: boolean = false
      ): void => {
        if (settled) return
        settled = true
        if (overallTimer) clearTimeout(overallTimer)

        const complete = (): void => {
          if (removePartial && file && fs.existsSync(savePath)) {
            try {
              fs.rmSync(savePath, { force: true })
            } catch (error) {
              logger.warn(`清理未完成下载失败: ${error}`)
            }
          }
          resolve(result)
        }

        if (file && !file.closed) {
          file.once('close', complete)
          if (removePartial) {
            activeResponse?.destroy()
            file.destroy()
          } else {
            file.close()
          }
          return
        }

        complete()
      }

      const requestOptions =
        context.options.idleTimeoutMs === undefined
          ? { signal: context.abortController.signal }
          : {
              timeout: context.options.idleTimeoutMs,
              signal: context.abortController.signal,
            }
      const req = client.get(url, requestOptions, response => {
        activeResponse = response
        // 处理重定向 (301, 302, 307, 308)
        if (response.statusCode && [301, 302, 307, 308].includes(response.statusCode)) {
          const redirectUrl = response.headers.location
          if (redirectUrl) {
            if (
              context.options.maxRedirects !== undefined &&
              redirectCount >= context.options.maxRedirects
            ) {
              req.destroy()
              finish({
                success: false,
                error: `下载重定向超过 ${context.options.maxRedirects} 次`,
              })
              return
            }
            logger.info(`跟随重定向: ${response.statusCode} -> ${redirectUrl}`)
            settled = true
            if (overallTimer) clearTimeout(overallTimer)
            req.destroy() // 销毁原请求
            let nextUrl: string
            try {
              nextUrl = resolveHttpRedirect(url, redirectUrl)
            } catch (error) {
              resolve({
                success: false,
                error: error instanceof Error ? error.message : String(error),
              })
              return
            }
            this.singleThreadDownload(
              nextUrl,
              savePath,
              totalSize,
              onProgress,
              context,
              redirectCount + 1
            )
              .then(resolve)
              .catch(error => resolve({ success: false, error: error.message }))
            return
          }
        }

        if (response.statusCode !== 200) {
          response.destroy()
          finish({ success: false, error: `HTTP ${response.statusCode}` })
          return
        }

        file = fs.createWriteStream(savePath)
        response.pipe(file)

        response.on('data', (chunk: Buffer) => {
          downloadedSize += chunk.length
          if (context.options.maxBytes !== undefined && downloadedSize > context.options.maxBytes) {
            response.destroy()
            req.destroy()
            finish(
              {
                success: false,
                error: `下载文件超过大小限制 ${context.options.maxBytes} 字节`,
              },
              true
            )
            return
          }

          // 计算进度和速度
          const currentTime = Date.now()
          const timeDiff = (currentTime - lastTime) / 1000

          if (timeDiff >= 0.5 && onProgress) {
            const speed = (downloadedSize - lastDownloaded) / timeDiff
            const progress = totalSize > 0 ? (downloadedSize / totalSize) * 100 : 0

            onProgress({
              progress: Math.min(progress, 100),
              speed,
              downloadedSize,
              totalSize,
            })

            lastTime = currentTime
            lastDownloaded = downloadedSize
          }
        })

        response.on('end', () => {
          // response 的 end 事件会在数据传输完成时触发
          // 但 file 的 finish 事件会在文件写入完成时触发
          // 需要等待 file.close() 或 file.end() 触发 finish
        })

        response.on('error', err => {
          logger.error(`响应流错误: ${err.message}`)
          req.destroy()
          finish({ success: false, error: `网络错误: ${err.message}` }, true)
        })

        file.on('finish', () => {
          // 下载完成时，无论是否达到上报间隔，都执行最后一次进度上报
          if (onProgress) {
            const currentTime = Date.now()
            const timeDiff = (currentTime - lastTime) / 1000
            const speed = timeDiff > 0 ? (downloadedSize - lastDownloaded) / timeDiff : 0

            onProgress({
              progress: 100,
              speed,
              downloadedSize,
              totalSize,
            })
          }

          logger.info('单线程下载完成')
          finish({ success: true })
        })

        file.on('error', err => {
          logger.error(`文件写入错误: ${err.message}`)
          req.destroy()
          finish({ success: false, error: `文件写入错误: ${err.message}` }, true)
        })
      })
      const overallTimer =
        remaining === undefined
          ? undefined
          : setTimeout(() => {
              req.destroy()
              finish({ success: false, error: '下载总时限已用尽' }, true)
            }, remaining)

      req.on('error', err => {
        if (settled) return
        logger.error(`请求错误: ${err.message}`)
        finish({ success: false, error: `网络连接错误: ${err.message}` }, true)
      })

      req.on('timeout', () => {
        logger.warn('请求超时')
        req.destroy()
        finish({ success: false, error: '下载超时' }, true)
      })
    })
  }

  /**
   * 多线程下载
   */
  private async multiThreadDownload(
    url: string,
    savePath: string,
    totalSize: number,
    onProgress?: ProgressCallback,
    threadCount: number = 4,
    context: DownloadContext = { options: {}, abortController: new AbortController() }
  ): Promise<{ success: boolean; error?: string }> {
    try {
      // 计算每个分片的大小
      const chunkSize = Math.ceil(totalSize / threadCount)
      const chunks: DownloadChunk[] = []

      for (let i = 0; i < threadCount; i++) {
        const start = i * chunkSize
        const end = Math.min(start + chunkSize - 1, totalSize - 1)

        chunks.push({
          start,
          end,
          index: i,
          data: [],
          completed: false,
        })
      }

      logger.info(`分片信息: ${chunks.length} 个分片`)

      // 进度监控
      let lastTime = Date.now()
      let lastDownloaded = 0

      const progressInterval = setInterval(() => {
        const downloadedSize = chunks.reduce((total, chunk) => {
          return total + chunk.data.reduce((sum, buffer) => sum + buffer.length, 0)
        }, 0)

        const currentTime = Date.now()
        const timeDiff = (currentTime - lastTime) / 1000

        if (timeDiff >= 0.5 && onProgress) {
          const speed = (downloadedSize - lastDownloaded) / timeDiff
          const progress = (downloadedSize / totalSize) * 100

          onProgress({
            progress: Math.min(progress, 100),
            speed,
            downloadedSize,
            totalSize,
          })

          lastTime = currentTime
          lastDownloaded = downloadedSize
        }
      }, 500)

      try {
        // 并行下载所有分片
        const downloadPromises = chunks.map(chunk => this.downloadChunk(url, chunk, context))
        await Promise.all(downloadPromises)

        clearInterval(progressInterval)

        // 下载完成时，无论是否达到上报间隔，都执行最后一次进度上报
        if (onProgress) {
          const downloadedSize = chunks.reduce((total, chunk) => {
            return total + chunk.data.reduce((sum, buffer) => sum + buffer.length, 0)
          }, 0)

          const currentTime = Date.now()
          const timeDiff = (currentTime - lastTime) / 1000
          const speed = timeDiff > 0 ? (downloadedSize - lastDownloaded) / timeDiff : 0

          onProgress({
            progress: 100,
            speed,
            downloadedSize: totalSize,
            totalSize,
          })
        }

        // 合并分片
        logger.info('开始合并分片...')
        const writeStream = fs.createWriteStream(savePath)

        for (const chunk of chunks) {
          for (const buffer of chunk.data) {
            writeStream.write(buffer)
          }
        }

        await new Promise<void>((resolve, reject) => {
          writeStream.end()
          writeStream.on('finish', resolve)
          writeStream.on('error', reject)
        })

        logger.info('多线程下载完成')
        return { success: true }
      } catch (downloadError) {
        // 确保清理进度定时器
        clearInterval(progressInterval)
        context.abortController.abort()

        const errorMsg =
          downloadError instanceof Error ? downloadError.message : String(downloadError)
        logger.error(`❌ 分片下载失败: ${errorMsg}`)
        throw downloadError
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`❌ 多线程下载失败: ${errorMsg}`)

      // 清理不完整的文件
      if (fs.existsSync(savePath)) {
        fs.unlinkSync(savePath)
      }

      return { success: false, error: errorMsg }
    }
  }

  /**
   * 下载单个分片
   */
  private downloadChunk(
    url: string,
    chunk: DownloadChunk,
    context: DownloadContext = { options: {}, abortController: new AbortController() },
    redirectCount: number = 0
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const client = url.startsWith('https') ? https : http
      let settled = false
      let downloadedSize = 0
      const remaining = this.getRemainingTime(context)

      if (remaining !== undefined && remaining <= 0) {
        reject(new Error('下载总时限已用尽'))
        return
      }

      const options = {
        headers: {
          Range: `bytes=${chunk.start}-${chunk.end}`,
        },
        timeout: context.options.idleTimeoutMs ?? 30000,
        signal: context.abortController.signal,
      }

      const finish = (error?: Error): void => {
        if (settled) return
        settled = true
        if (overallTimer) clearTimeout(overallTimer)
        if (error) {
          reject(error)
        } else {
          resolve()
        }
      }

      const req = client.get(url, options, response => {
        // 处理重定向 (301, 302, 307, 308)
        if (response.statusCode && [301, 302, 307, 308].includes(response.statusCode)) {
          const redirectUrl = response.headers.location
          if (redirectUrl) {
            if (
              context.options.maxRedirects !== undefined &&
              redirectCount >= context.options.maxRedirects
            ) {
              req.destroy()
              finish(new Error(`分片 ${chunk.index} 重定向超过 ${context.options.maxRedirects} 次`))
              return
            }
            logger.debug(`分片 ${chunk.index} 跟随重定向: ${response.statusCode} -> ${redirectUrl}`)
            settled = true
            if (overallTimer) clearTimeout(overallTimer)
            req.destroy() // 销毁原请求
            let nextUrl: string
            try {
              nextUrl = resolveHttpRedirect(url, redirectUrl)
            } catch (error) {
              reject(error)
              return
            }
            this.downloadChunk(nextUrl, chunk, context, redirectCount + 1)
              .then(resolve)
              .catch(reject)
            return
          }
        }

        if (response.statusCode !== 206) {
          response.destroy()
          finish(new Error(`分片下载失败，状态码: ${response.statusCode}`))
          return
        }

        chunk.data = []

        response.on('data', (data: Buffer) => {
          downloadedSize += data.length
          if (downloadedSize > chunk.end - chunk.start + 1) {
            response.destroy()
            req.destroy()
            finish(new Error(`分片 ${chunk.index} 返回数据超过请求范围`))
            return
          }
          chunk.data.push(data)
        })

        response.on('end', () => {
          chunk.completed = true
          finish()
        })

        response.on('error', err => {
          if (settled) return
          logger.error(`分片 ${chunk.index} 响应错误: ${err.message}`)
          req.destroy()
          finish(new Error(`分片 ${chunk.index} 网络错误: ${err.message}`))
        })
      })
      const overallTimer =
        remaining === undefined
          ? undefined
          : setTimeout(() => {
              req.destroy()
              finish(new Error('下载总时限已用尽'))
            }, remaining)

      req.on('error', err => {
        if (settled) return
        logger.error(`分片 ${chunk.index} 请求错误: ${err.message}`)
        finish(new Error(`分片 ${chunk.index} 网络连接错误: ${err.message}`))
      })

      req.on('timeout', () => {
        logger.warn(`分片 ${chunk.index} 请求超时`)
        req.destroy()
        finish(new Error(`分片 ${chunk.index} 下载超时`))
      })
    })
  }

  private getRemainingTime(context: DownloadContext): number | undefined {
    return context.deadline === undefined ? undefined : Math.max(0, context.deadline - Date.now())
  }
}
