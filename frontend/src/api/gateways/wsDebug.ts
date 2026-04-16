import {
  clearHistoryApiWsDebugHistoryClearPost,
  connectClientApiWsDebugClientConnectPost,
  createClientApiWsDebugClientCreatePost,
  disconnectClientApiWsDebugClientDisconnectPost,
  getHistoryApiWsDebugHistoryGet,
  listClientsApiWsDebugClientListGet,
  removeClientApiWsDebugClientRemovePost,
  sendAuthApiWsDebugMessageAuthPost,
  sendJsonMessageApiWsDebugMessageSendJsonPost,
  sendMessageApiWsDebugMessageSendPost,
} from '../generated/sdk.gen'
import type {
  WsClearHistoryIn,
  WsClientAuthIn,
  WsClientConnectIn,
  WsClientCreateIn,
  WsClientDisconnectIn,
  WsClientRemoveIn,
  WsClientSendIn,
  WsClientSendJsonIn,
} from '../generated/types.gen'

export const wsDebugApi = {
  listClients() {
    return listClientsApiWsDebugClientListGet()
  },

  createClient(payload: WsClientCreateIn) {
    return createClientApiWsDebugClientCreatePost({ body: payload })
  },

  connectClient(payload: WsClientConnectIn) {
    return connectClientApiWsDebugClientConnectPost({ body: payload })
  },

  disconnectClient(payload: WsClientDisconnectIn) {
    return disconnectClientApiWsDebugClientDisconnectPost({ body: payload })
  },

  removeClient(payload: WsClientRemoveIn) {
    return removeClientApiWsDebugClientRemovePost({ body: payload })
  },

  sendJson(payload: WsClientSendJsonIn) {
    return sendJsonMessageApiWsDebugMessageSendJsonPost({ body: payload })
  },

  sendMessage(payload: WsClientSendIn) {
    return sendMessageApiWsDebugMessageSendPost({ body: payload })
  },

  sendAuth(payload: WsClientAuthIn) {
    return sendAuthApiWsDebugMessageAuthPost({ body: payload })
  },

  clearHistory(payload: WsClearHistoryIn) {
    return clearHistoryApiWsDebugHistoryClearPost({ body: payload })
  },

  getHistory() {
    return getHistoryApiWsDebugHistoryGet()
  },
}
