import { ipcMain, type BrowserWindow } from 'electron'
import { analyzeBannerWithCodex } from '../services/bannerCodexService'
import { isApplicationWindowSender } from './analyticsHandlers'

export function registerBannerCodexHandlers(getMainWindow: () => BrowserWindow | null): void {
  ipcMain.handle('banner-watch:analyze-with-codex', (event, prompt: unknown) => {
    if (!isApplicationWindowSender(event, getMainWindow())) return { status: 'unavailable' }
    return analyzeBannerWithCodex(prompt)
  })
}
