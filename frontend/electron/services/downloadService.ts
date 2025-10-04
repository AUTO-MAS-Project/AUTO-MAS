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

        console.log(`文件大小: ${totalSize} bytes`)

        response.pipe(file)

        response.on('data', chunk => {
          downloadedSize += chunk.length
          const progress = totalSize ? Math.round((downloadedSize / totalSize) * 100) : 0

          // console.log(`下载进度: ${progress}% (${downloadedSize}/${totalSize})`)

          if (mainWindow) {
            mainWindow.webContents.send('download-progress', {
              progress,
              status: 'downloading',
              message: `下载中... ${progress}%`,
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
