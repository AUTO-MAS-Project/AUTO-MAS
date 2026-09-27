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

// 重定向最大跟随次数：超限按下载失败处理，交给上层镜像轮换，防止重定向成环导致下载永久卡死
const MAX_REDIRECT_DEPTH = 10

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
  downloaded: number
  completed: boolean
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
    onProgress?: ProgressCallback
  ): Promise<{ success: boolean; error?: string }> {
    logger.info('=== 开始智能下载 ===')
    logger.info(`URL: ${url}`)
    logger.info(`保存路径: ${savePath}`)

    try {
      // 1. 获取文件头信息
      const fileInfo = await this.getFileInfo(url)

      if (!fileInfo.isFile) {
        throw new Error('URL 返回的不是文件类型')
      }

      logger.info(`文件大小: ${(fileInfo.size / 1024 / 1024).toFixed(2)} MB`)
      logger.info(`支持 Range: ${fileInfo.supportsRange}`)

      // 2. 判断下载方式
      const useMultiThread = fileInfo.supportsRange && fileInfo.size > this.MIN_SIZE_FOR_MULTITHREAD

      if (useMultiThread) {
        logger.info('使用多线程下载')
        return await this.multiThreadDownload(url, savePath, fileInfo.size, onProgress)
      } else {
        logger.info('使用单线程下载')
        return await this.singleThreadDownload(url, savePath, fileInfo.size, onProgress)
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
    depth: number = 0
  ): Promise<{
    isFile: boolean
    size: number
    supportsRange: boolean
  }> {
    return new Promise((resolve, reject) => {
      if (depth > MAX_REDIRECT_DEPTH) {
        reject(new Error('重定向次数超过上限'))
        return
      }

      const client = url.startsWith('https') ? https : http

      const req = client.request(url, { method: 'HEAD', timeout: 10000 }, response => {
        // 处理重定向 (301, 302, 307, 308)
        if (response.statusCode && [301, 302, 307, 308].includes(response.statusCode)) {
          const redirectUrl = response.headers.location
          if (redirectUrl) {
            logger.debug(`跟随重定向: ${response.statusCode} -> ${redirectUrl}`)
            req.destroy() // 销毁原请求
            this.getFileInfo(redirectUrl, depth + 1).then(resolve).catch(reject)
            return
          }
        }

        const contentType = response.headers['content-type'] || ''
        const contentLength = response.headers['content-length']
        const acceptRanges = response.headers['accept-ranges']

        // 判断是否为文件
        const isFile = !contentType.includes('text/html') && contentLength !== undefined

        resolve({
          isFile,
          size: parseInt(contentLength || '0', 10),
          supportsRange: acceptRanges === 'bytes',
        })
      })

      req.on('error', reject)
      req.on('timeout', () => {
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
    depth: number = 0
  ): Promise<{ success: boolean; error?: string }> {
    return new Promise(resolve => {
      if (depth > MAX_REDIRECT_DEPTH) {
        resolve({ success: false, error: '重定向次数超过上限' })
        return
      }

      const client = url.startsWith('https') ? https : http
      const file = fs.createWriteStream(savePath)

      let downloadedSize = 0
      let lastTime = Date.now()
      let lastDownloaded = 0

      // 禁用 keep-alive 连接池：与 downloadChunk 同理，避免半截响应后连接静默悬死
      const req = client.get(url, { agent: false }, response => {
        // 处理重定向 (301, 302, 307, 308)
        if (response.statusCode && [301, 302, 307, 308].includes(response.statusCode)) {
          const redirectUrl = response.headers.location
          if (redirectUrl) {
            logger.info(`跟随重定向: ${response.statusCode} -> ${redirectUrl}`)
            req.destroy() // 销毁原请求
            file.close()
            this.singleThreadDownload(redirectUrl, savePath, totalSize, onProgress, depth + 1)
              .then(resolve)
              .catch(error => resolve({ success: false, error: error.message }))
            return
          }
        }

        if (response.statusCode !== 200) {
          file.close()
          fs.unlinkSync(savePath)
          resolve({ success: false, error: `HTTP ${response.statusCode}` })
          return
        }

        response.pipe(file)

        response.on('data', (chunk: Buffer) => {
          downloadedSize += chunk.length

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
          file.close()
          if (fs.existsSync(savePath)) {
            fs.unlinkSync(savePath)
          }
          resolve({ success: false, error: `网络错误: ${err.message}` })
        })

        file.on('finish', () => {
          file.close()

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
          resolve({ success: true })
        })

        file.on('error', err => {
          logger.error(`文件写入错误: ${err.message}`)
          req.destroy()
          file.close()
          if (fs.existsSync(savePath)) {
            fs.unlinkSync(savePath)
          }
          resolve({ success: false, error: `文件写入错误: ${err.message}` })
        })
      })

      req.on('error', err => {
        logger.error(`请求错误: ${err.message}`)
        file.close()
        if (fs.existsSync(savePath)) {
          fs.unlinkSync(savePath)
        }
        resolve({ success: false, error: `网络连接错误: ${err.message}` })
      })

      req.on('timeout', () => {
        logger.warn('请求超时')
        req.destroy()
        file.close()
        if (fs.existsSync(savePath)) {
          fs.unlinkSync(savePath)
        }
        resolve({ success: false, error: '下载超时' })
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
    threadCount: number = 4
  ): Promise<{ success: boolean; error?: string }> {
    // 分片数据按位置直接写入目标文件，不再把整个文件缓冲在内存
    let fileHandle: number
    try {
      fileHandle = fs.openSync(savePath, 'w')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`❌ 多线程下载失败: ${errorMsg}`)
      return { success: false, error: errorMsg }
    }

    let fileClosed = false
    const closeFile = () => {
      if (!fileClosed) {
        fileClosed = true
        fs.closeSync(fileHandle)
      }
    }

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
          downloaded: 0,
          completed: false,
        })
      }

      logger.info(`分片信息: ${chunks.length} 个分片`)

      // 进度监控
      let lastTime = Date.now()
      let lastDownloaded = 0

      const progressInterval = setInterval(() => {
        const downloadedSize = chunks.reduce((total, chunk) => total + chunk.downloaded, 0)

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
        const downloadPromises = chunks.map(chunk => this.downloadChunk(url, chunk, fileHandle))
        await Promise.all(downloadPromises)

        clearInterval(progressInterval)
        closeFile()

        // 下载完成时，无论是否达到上报间隔，都执行最后一次进度上报
        if (onProgress) {
          const currentTime = Date.now()
          const timeDiff = (currentTime - lastTime) / 1000
          const speed = timeDiff > 0 ? (totalSize - lastDownloaded) / timeDiff : 0

          onProgress({
            progress: 100,
            speed,
            downloadedSize: totalSize,
            totalSize,
          })
        }

        logger.info('多线程下载完成')
        return { success: true }
      } catch (downloadError) {
        // 确保清理进度定时器并关闭文件句柄
        clearInterval(progressInterval)
        closeFile()

        const errorMsg =
          downloadError instanceof Error ? downloadError.message : String(downloadError)
        logger.error(`❌ 分片下载失败: ${errorMsg}`)
        throw downloadError
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`❌ 多线程下载失败: ${errorMsg}`)

      // 清理不完整的文件
      closeFile()
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
    fileHandle: number,
    depth: number = 0
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      if (depth > MAX_REDIRECT_DEPTH) {
        reject(new Error(`分片 ${chunk.index} 重定向次数超过上限`))
        return
      }

      const client = url.startsWith('https') ? https : http

      const options = {
        headers: {
          Range: `bytes=${chunk.start}-${chunk.end}`,
        },
        timeout: 30000,
        // 禁用 keep-alive 连接池：默认 agent 会吞掉「响应未满 Content-Length 就收到 FIN」的
        // 连接关闭，res 上不触发 end/aborted/error/close，分片 Promise 永久挂起；
        // 独立连接下这些事件正常触发，由下面的 close/error 兜底快速失败
        agent: false,
      }

      const req = client.get(url, options, response => {
        // 处理重定向 (301, 302, 307, 308)
        if (response.statusCode && [301, 302, 307, 308].includes(response.statusCode)) {
          const redirectUrl = response.headers.location
          if (redirectUrl) {
            logger.debug(`分片 ${chunk.index} 跟随重定向: ${response.statusCode} -> ${redirectUrl}`)
            req.destroy() // 销毁原请求
            this.downloadChunk(redirectUrl, chunk, fileHandle, depth + 1)
              .then(resolve)
              .catch(reject)
            return
          }
        }

        if (response.statusCode !== 206) {
          reject(new Error(`分片下载失败，状态码: ${response.statusCode}`))
          return
        }

        // 统一收口：end 与 close 都会触发（正常完成时 close 在 end 之后），用 settled
        // 保证只结算一次；连接在 end/error 之前断掉时由 close 兜底，避免 Promise 永久挂起
        let settled = false
        const settle = (error?: Error) => {
          if (settled) {
            return
          }
          settled = true
          if (error) {
            reject(error)
          } else {
            resolve()
          }
        }

        response.on('data', (data: Buffer) => {
          try {
            // 按分片起始位置顺序写入；循环写满整个缓冲，部分写时补写剩余段，防静默丢尾
            let written = 0
            while (written < data.length) {
              const count = fs.writeSync(
                fileHandle,
                data,
                written,
                data.length - written,
                chunk.start + chunk.downloaded + written
              )
              if (count <= 0) {
                throw new Error(`writeSync 写入 0 字节`)
              }
              written += count
            }
            chunk.downloaded += data.length
          } catch (writeError) {
            const errorMsg = writeError instanceof Error ? writeError.message : String(writeError)
            logger.error(`分片 ${chunk.index} 写入失败: ${errorMsg}`)
            req.destroy()
            settle(new Error(`分片 ${chunk.index} 文件写入错误: ${errorMsg}`))
          }
        })

        response.on('end', () => {
          // 校验分片实际收到的字节数：短响应（chunked 提前收尾、close-delimited）不算成功，
          // 否则文件会在对应区间留下零空洞，损坏要到解压时才暴露
          const expectedLength = chunk.end - chunk.start + 1
          if (chunk.downloaded !== expectedLength) {
            settle(
              new Error(
                `分片 ${chunk.index} 数据不完整: 预期 ${expectedLength} 字节，实际 ${chunk.downloaded} 字节`
              )
            )
            return
          }
          chunk.completed = true
          settle()
        })

        response.on('error', err => {
          logger.error(`分片 ${chunk.index} 响应错误: ${err.message}`)
          req.destroy()
          settle(new Error(`分片 ${chunk.index} 网络错误: ${err.message}`))
        })

        response.on('close', () => {
          settle(new Error(`分片 ${chunk.index} 连接提前断开`))
        })
      })

      req.on('error', err => {
        logger.error(`分片 ${chunk.index} 请求错误: ${err.message}`)
        reject(new Error(`分片 ${chunk.index} 网络连接错误: ${err.message}`))
      })

      req.on('timeout', () => {
        logger.warn(`分片 ${chunk.index} 请求超时`)
        req.destroy()
        reject(new Error(`分片 ${chunk.index} 下载超时`))
      })
    })
  }
}
