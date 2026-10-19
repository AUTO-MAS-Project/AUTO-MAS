import { QueryCache, QueryClient } from '@tanstack/vue-query'
import { message } from 'ant-design-vue'
import { ApiError } from '@/api'

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    // 同一查询失败只提示一次；页面通过 meta 显式选择由公共层提示。
    onError: (error, query) => {
      if (query.meta?.notifyOnError !== true) return
      const body = error instanceof ApiError ? error.body : null
      const errorMessage =
        body && typeof body === 'object' && typeof body.message === 'string'
          ? body.message
          : error.message
      window.electronAPI.getLogger('数据查询').error(errorMessage)
      message.error(errorMessage)
    },
  }),
  defaultOptions: {
    queries: {
      // 本地后端不依赖外网连通性，也不因窗口聚焦而额外请求。
      networkMode: 'always',
      retry: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    },
  },
})
