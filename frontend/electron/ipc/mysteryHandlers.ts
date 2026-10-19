import { ipcMain } from 'electron'
import { verifyMysteryAccessCode } from '../services/mysteryAccessCode'

export function registerMysteryHandlers(): void {
  ipcMain.handle('mystery:verify', (_event, accessCode: unknown, context: unknown) =>
    verifyMysteryAccessCode(accessCode, context)
  )
}
