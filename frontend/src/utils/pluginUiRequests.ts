import { OpenAPI, type FrontendSurfaceMount } from '@/api'
import { request } from '@/api/core/request'

export type PluginUiActivation = Pick<FrontendSurfaceMount, 'pluginName' | 'activationId'>

export function pluginUiPost<T>(
  url: string,
  body: object,
  { pluginName, activationId }: PluginUiActivation
) {
  return request<T>(OpenAPI, {
    method: 'POST',
    url,
    body,
    mediaType: 'application/json',
    headers: {
      'X-Plugin-Ui-Provider': pluginName,
      'X-Plugin-Ui-Activation': activationId,
    },
  })
}
