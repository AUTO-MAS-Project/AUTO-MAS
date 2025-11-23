/**
 * 智能下载服务
 * 重构版本 - 独立实现，支持单线程和多线程下载
 */

import * as fs from 'fs'
import * as https from 'https'
import * as http from 'http'

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
        console.log('=== 开始智能下载 ===')
        console.log(`URL: ${url}`)
        console.log(`保存路径: ${savePath}`)

        try {
            // 1. 获取文件头信息
            const fileInfo = await this.getFileInfo(url)

            if (!fileInfo.isFile) {
                throw new Error('URL 返回的不是文件类型')
            }

            console.log(`文件大小: ${(fileInfo.size / 1024 / 1024).toFixed(2)} MB`)
            console.log(`支持 Range: ${fileInfo.supportsRange}`)

            // 2. 判断下载方式
            const useMultiThread =
                fileInfo.supportsRange &&
                fileInfo.size > this.MIN_SIZE_FOR_MULTITHREAD

            if (useMultiThread) {
                console.log('✅ 使用多线程下载')
                return await this.multiThreadDownload(url, savePath, fileInfo.size, onProgress)
            } else {
                console.log('✅ 使用单线程下载')
                return await this.singleThreadDownload(url, savePath, fileInfo.size, onProgress)
            }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            console.error('❌ 下载失败:', errorMsg)
            return { success: false, error: errorMsg }
        }
    }

    /**
     * 获取文件信息
     */
    private getFileInfo(url: string): Promise<{
        isFile: boolean
        size: number
        supportsRange: boolean
    }> {
        return new Promise((resolve, reject) => {
            const client = url.startsWith('https') ? https : http

            const req = client.request(url, { method: 'HEAD', timeout: 10000 }, (response) => {
                const contentType = response.headers['content-type'] || ''
                const contentLength = response.headers['content-length']
                const acceptRanges = response.headers['accept-ranges']

                // 判断是否为文件
                const isFile = !contentType.includes('text/html') && contentLength !== undefined

                resolve({
                    isFile,
                    size: parseInt(contentLength || '0', 10),
                    supportsRange: acceptRanges === 'bytes'
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
        onProgress?: ProgressCallback
    ): Promise<{ success: boolean; error?: string }> {
        return new Promise((resolve) => {
            const client = url.startsWith('https') ? https : http
            const file = fs.createWriteStream(savePath)

            let downloadedSize = 0
            let lastTime = Date.now()
            let lastDownloaded = 0

            const req = client.get(url, (response) => {
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
                            totalSize
                        })

                        lastTime = currentTime
                        lastDownloaded = downloadedSize
                    }
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
                            totalSize
                        })
                    }

                    console.log('✅ 单线程下载完成')
                    resolve({ success: true })
                })

                file.on('error', (err) => {
                    file.close()
                    fs.unlinkSync(savePath)
                    resolve({ success: false, error: err.message })
                })
            })

            req.on('error', (err) => {
                file.close()
                if (fs.existsSync(savePath)) {
                    fs.unlinkSync(savePath)
                }
                resolve({ success: false, error: err.message })
            })

            req.on('timeout', () => {
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
                    completed: false
                })
            }

            console.log(`分片信息: ${chunks.length} 个分片`)

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
                        totalSize
                    })

                    lastTime = currentTime
                    lastDownloaded = downloadedSize
                }
            }, 500)

            // 并行下载所有分片
            const downloadPromises = chunks.map(chunk => this.downloadChunk(url, chunk))
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
                    totalSize
                })
            }

            // 合并分片
            console.log('开始合并分片...')
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

            console.log('✅ 多线程下载完成')
            return { success: true }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            console.error('❌ 多线程下载失败:', errorMsg)

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
    private downloadChunk(url: string, chunk: DownloadChunk): Promise<void> {
        return new Promise((resolve, reject) => {
            const client = url.startsWith('https') ? https : http

            const options = {
                headers: {
                    Range: `bytes=${chunk.start}-${chunk.end}`
                },
                timeout: 30000
            }

            const req = client.get(url, options, (response) => {
                if (response.statusCode !== 206) {
                    reject(new Error(`分片下载失败，状态码: ${response.statusCode}`))
                    return
                }

                chunk.data = []

                response.on('data', (data: Buffer) => {
                    chunk.data.push(data)
                })

                response.on('end', () => {
                    chunk.completed = true
                    resolve()
                })

                response.on('error', reject)
            })

            req.on('error', reject)
            req.on('timeout', () => {
                req.destroy()
                reject(new Error('分片下载超时'))
            })
        })
    }
}
