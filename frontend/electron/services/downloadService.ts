import * as https from 'https'
import * as fs from 'fs'
import { BrowserWindow } from 'electron'
import * as http from 'http'

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
          fs.unlink(outputPath, () => {}) // 删除不完整的文件
          reject(err)
        })
      })
      .on('error', err => {
        console.error(`下载错误: ${err.message}`)
        reject(err)
      })
  })
}
