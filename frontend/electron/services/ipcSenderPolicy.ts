import type { BrowserWindow, IpcMainInvokeEvent } from 'electron'

export interface IpcSenderIdentity {
  senderWebContentsId: number
  senderFrameProcessId: number
  senderFrameRoutingId: number
  mainFrameProcessId: number
  mainFrameRoutingId: number
}

/** Privileged IPC is accepted only from an explicitly allowed window's top-level frame. */
export function isAllowedMainFrameSender(
  identity: IpcSenderIdentity,
  allowedWebContentsIds: readonly number[]
): boolean {
  return (
    allowedWebContentsIds.includes(identity.senderWebContentsId) &&
    identity.senderFrameProcessId === identity.mainFrameProcessId &&
    identity.senderFrameRoutingId === identity.mainFrameRoutingId
  )
}

export function assertAllowedMainFrameSender(
  event: IpcMainInvokeEvent,
  allowedWindows: readonly (BrowserWindow | null)[]
): void {
  const senderFrame = event.senderFrame
  const mainFrame = event.sender.mainFrame
  const allowedWebContentsIds = allowedWindows
    .filter((window): window is BrowserWindow => Boolean(window && !window.isDestroyed()))
    .map(window => window.webContents.id)

  if (
    !senderFrame ||
    !mainFrame ||
    !isAllowedMainFrameSender(
      {
        senderWebContentsId: event.sender.id,
        senderFrameProcessId: senderFrame.processId,
        senderFrameRoutingId: senderFrame.routingId,
        mainFrameProcessId: mainFrame.processId,
        mainFrameRoutingId: mainFrame.routingId,
      },
      allowedWebContentsIds
    )
  ) {
    throw new Error('Privileged IPC is limited to the trusted top-level renderer')
  }
}
