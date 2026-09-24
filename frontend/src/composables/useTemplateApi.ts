import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type ShareTemplateItem } from '@/api'

export type { ShareTemplateItem }

export interface TemplateQuery {
  page: number
  pageSize: number
  keyword: string
}

export interface TemplatePage {
  items: ShareTemplateItem[]
  page: number
  pageSize: number
  total: number
  hasNext: boolean
}

export const TEMPLATE_PAGE_SIZE = 10

const emptyPage = (query: TemplateQuery): TemplatePage => ({
  items: [],
  page: query.page,
  pageSize: query.pageSize,
  total: 0,
  hasNext: false,
})

export function useTemplateApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 拉取配置中心已审核发布的通用脚本配置；搜索与翻页都在服务端完成
  const getShareTemplates = async (query: TemplateQuery): Promise<TemplatePage> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.listShareTemplatesApiShareTemplatesPost({
        page: query.page,
        pageSize: query.pageSize,
        keyword: query.keyword || null,
      })

      if (response.code !== 200) {
        const errorMsg = response.message || '获取模板列表失败'
        error.value = errorMsg
        return emptyPage(query)
      }

      return {
        items: response.items ?? [],
        page: response.page ?? query.page,
        pageSize: response.pageSize ?? query.pageSize,
        total: response.total ?? 0,
        hasNext: response.hasNext ?? false,
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : '获取模板列表失败'
      return emptyPage(query)
    } finally {
      loading.value = false
    }
  }

  // 按配置中心的结构化标识导入配置，渲染进程不再提交下载地址
  const importScriptFromTemplate = async (
    scriptId: string,
    template: ShareTemplateItem
  ): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const response = await Service.importScriptFromWebApiScriptsImportWebPost({
        scriptId,
        configKey: template.configKey,
        versionNo: template.publishedVersionNo ?? null,
      })

      if (response.code !== 200) {
        const errorMsg = response.message || '导入配置失败'
        error.value = errorMsg
        message.error(errorMsg)
        return false
      }

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '导入配置失败'
      error.value = errorMsg
      message.error(errorMsg)
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    getShareTemplates,
    importScriptFromTemplate,
  }
}
