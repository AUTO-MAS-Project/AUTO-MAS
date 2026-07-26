const retryButton = document.getElementById('app-boot-retry')
const quitButton = document.getElementById('app-boot-quit')

retryButton?.addEventListener('click', () => {
  window.location.reload()
})

quitButton?.addEventListener('click', () => {
  void window.electronAPI?.appQuit?.()
})

// 主进程发送 startup-error 时，把启动 spinner 替换为结构化错误。
window.electronAPI?.onStartupError?.(error => {
  const fallback = document.getElementById('app-boot-fallback')
  const errorDetail = document.getElementById('app-boot-error-detail')
  const errorPanel = document.getElementById('app-boot-error')

  fallback?.classList.add('has-error')
  if (errorDetail) {
    errorDetail.textContent = `错误代码: ${error.errorCode} — ${error.errorDescription}`
  }
  errorPanel?.classList.add('visible')
})
