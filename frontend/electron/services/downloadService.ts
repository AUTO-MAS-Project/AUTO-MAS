import * as https from 'https'
import * as fs from 'fs'
import { BrowserWindow } from 'electron'
import * as http from 'http'
import * as path from 'path'

let mainWindow: BrowserWindow | null = null

export function setMainWindow(window: BrowserWindow) {
  mainWindow = window
}

export function downloadFile(url: string, outputPath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    console.log(`开始下载文件: ${url}`)
    console.log(`保存路径: ${outputPath}`)

    const file = fs.createWriteStream(outputPath)
    // 创建HTTP客户端，兼容https和http
    const client = url.startsWith('https') ? https : http

    client
      .get(url, response => {
        const totalSize = parseInt(response.headers['content-length'] || '0', 10)
        let downloadedSize = 0
        let startTime = Date.now()
        let lastTime = startTime
        let lastDownloaded = 0

        console.log(`文件大小: ${totalSize} bytes`)

        response.pipe(file)

        response.on('data', chunk => {
          downloadedSize += chunk.length
          const progress = totalSize ? Math.round((downloadedSize / totalSize) * 100) : 0

          // 计算下载速度
          const currentTime = Date.now()
          const timeDiff = (currentTime - lastTime) / 1000 // 转换为秒
          const sizeDiff = downloadedSize - lastDownloaded

          let speed = 0
          let speedText = ''

          if (timeDiff > 0.5) { // 每0.5秒更新一次速度
            speed = sizeDiff / timeDiff // bytes per second

            if (speed > 1024 * 1024) {
              speedText = `${(speed / (1024 * 1024)).toFixed(1)} MB/s`
            } else if (speed > 1024) {
              speedText = `${(speed / 1024).toFixed(1)} KB/s`
            } else {
              speedText = `${speed.toFixed(0)} B/s`
            }

            lastTime = currentTime
            lastDownloaded = downloadedSize
          }

          if (mainWindow) {
            mainWindow.webContents.send('download-progress', {
              progress,
              status: 'downloading',
              message: `下载中... ${progress}%`,
              speed: speedText,
              downloadedSize,
              totalSize,
            })
          }
        })

        file.on('finish', () => {
          file.close()
          console.log(`文件下载完成: ${outputPath}`)
          resolve()
        })

        file.on('error', err => {
          console.error(`文件写入错误: ${err.message}`)
          fs.unlink(outputPath, () => { }) // 删除不完整的文件
          reject(err)
        })
      })
      .on('error', err => {
        console.error(`下载错误: ${err.message}`)
        reject(err)
      })
  })
}

// 多线程下载接口
interface DownloadChunk {
  start: number
  end: number
  index: number
  data: Buffer[]
  completed: boolean
}

// 获取文件大小和是否支持范围请求
function getFileInfo(url: string): Promise<{ size: number; supportsRange: boolean }> {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http

    const req = client.request(url, { method: 'HEAD' }, (response) => {
      const size = parseInt(response.headers['content-length'] || '0', 10)
      const supportsRange = response.headers['accept-ranges'] === 'bytes'

      resolve({ size, supportsRange })
    })

    req.on('error', reject)
    req.end()
  })
}

// 下载单个分片
function downloadChunk(url: string, chunk: DownloadChunk): Promise<void> {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http

    const options = {
      headers: {
        'Range': `bytes=${chunk.start}-${chunk.end}`
      }
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
    req.end()
  })
}

// 多线程下载文件
export function downloadFileMultiThread(
  url: string,
  outputPath: string,
  threadCount: number = 4
): Promise<void> {
  return new Promise(async (resolve, reject) => {
    try {
      console.log(`开始多线程下载文件: ${url}`)
      console.log(`线程数: ${threadCount}`)
      console.log(`保存路径: ${outputPath}`)

      // 获取文件信息
      const { size: totalSize, supportsRange } = await getFileInfo(url)

      if (!supportsRange || totalSize === 0) {
        console.log('服务器不支持范围请求或文件大小未知，使用单线程下载')
        return downloadFile(url, outputPath).then(resolve).catch(reject)
      }

      console.log(`文件大小: ${totalSize} bytes`)
      console.log(`支持范围请求: ${supportsRange}`)

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

      console.log(`分片信息:`, chunks.map(c => `${c.index}: ${c.start}-${c.end}`))

      let downloadedSize = 0
      const startTime = Date.now()
      let lastTime = startTime
      let lastDownloaded = 0

      // 监控下载进度
      const progressInterval = setInterval(() => {
        const currentDownloaded = chunks.reduce((total, chunk) => {
          return total + chunk.data.reduce((sum, buffer) => sum + buffer.length, 0)
        }, 0)

        downloadedSize = currentDownloaded
        const progress = Math.round((downloadedSize / totalSize) * 100)

        // 计算下载速度
        const currentTime = Date.now()
        const timeDiff = (currentTime - lastTime) / 1000
        const sizeDiff = downloadedSize - lastDownloaded

        let speedText = ''
        if (timeDiff > 0.5) {
          const speed = sizeDiff / timeDiff

          if (speed > 1024 * 1024) {
            speedText = `${(speed / (1024 * 1024)).toFixed(1)} MB/s`
          } else if (speed > 1024) {
            speedText = `${(speed / 1024).toFixed(1)} KB/s`
          } else {
            speedText = `${speed.toFixed(0)} B/s`
          }

          lastTime = currentTime
          lastDownloaded = downloadedSize
        }

        if (mainWindow) {
          mainWindow.webContents.send('download-progress', {
            progress,
            status: 'downloading',
            message: `多线程下载中... ${progress}%`,
            speed: speedText,
            downloadedSize,
            totalSize,
            threadCount,
          })
        }
      }, 500)

      // 并行下载所有分片
      const downloadPromises = chunks.map(chunk => downloadChunk(url, chunk))

      await Promise.all(downloadPromises)

      clearInterval(progressInterval)

      console.log('所有分片下载完成，开始合并文件')

      // 合并分片到最终文件
      const writeStream = fs.createWriteStream(outputPath)

      for (const chunk of chunks) {
        for (const buffer of chunk.data) {
          writeStream.write(buffer)
        }
      }

      writeStream.end()

      writeStream.on('finish', () => {
        console.log(`多线程下载完成: ${outputPath}`)
        resolve()
      })

      writeStream.on('error', (err) => {
        console.error(`文件写入错误: ${err.message}`)
        fs.unlink(outputPath, () => { }) // 删除不完整的文件
        reject(err)
      })

    } catch (error) {
      console.error(`多线程下载错误: ${error}`)
      reject(error)
    }
  })
}