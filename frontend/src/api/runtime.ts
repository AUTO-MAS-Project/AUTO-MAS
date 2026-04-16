import { client } from './generated/client.gen'

client.setConfig({
  responseStyle: 'data',
  throwOnError: true,
})

export const apiClient = client

export const apiRuntime = {
  get baseUrl(): string {
    return apiClient.getConfig().baseUrl ?? ''
  },
  set baseUrl(value: string) {
    apiClient.setConfig({ baseUrl: value })
  },
}
