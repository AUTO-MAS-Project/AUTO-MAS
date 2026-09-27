import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type GameSignAccountGroupConfig } from '@/api'
import { useConfigEditSession } from '@/composables/useConfigEditSession'

export function useGameSignAccountApi() {
  const loading = ref(false)
  const logger = window.electronAPI.getLogger('签到账号API')
  const { ensureConfigEditSession, markConfigEditSaved } = useConfigEditSession()

  /**
   * 添加账号组
   */
  const addAccount = async (): Promise<{
    accountId: string
    data: GameSignAccountGroupConfig
  } | null> => {
    loading.value = true
    try {
      const editSession = await ensureConfigEditSession('ToolsConfig')
      if (!editSession) return null
      const response = await Service.addGameSignAccountApiToolsSignAccountAddPost(editSession)
      if (response.code !== 200) {
        throw new Error(response.message || '添加账号组失败')
      }
      if (!response.accountId || !response.data) {
        throw new Error('添加账号组失败：服务端响应缺少账号信息')
      }
      await markConfigEditSaved('ToolsConfig')
      logger.info('账号组添加成功')
      return { accountId: response.accountId, data: response.data }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`添加账号组失败: ${errorMsg}`)
      message.error(t('misc.couldNotAddAccount'))
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 更新账号组
   */
  const updateAccount = async (
    accountId: string,
    data: GameSignAccountGroupConfig
  ): Promise<void> => {
    try {
      const editSession = await ensureConfigEditSession('ToolsConfig')
      if (!editSession) throw new Error('有其他用户正在编辑该配置')
      const response = await Service.updateGameSignAccountApiToolsSignAccountUpdatePost({
        accountId,
        data,
        ...editSession,
      })
      if (response.code !== 200) {
        throw new Error(response.message || '更新账号组失败')
      }
      await markConfigEditSaved('ToolsConfig')
      logger.info('账号组更新成功')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新账号组失败: ${errorMsg}`)
      throw error
    }
  }

  /**
   * 使用塔吉多账号密码一次性换取并保存 Token。
   * 密码只在本次请求中存在，不写入前端状态或日志。
   */
  const loginTaygedo = async (
    accountId: string,
    phone: string,
    password: string
  ): Promise<void> => {
    try {
      const response = await Service.loginTaygedoApiToolsSignAccountTaygedoLoginPost({
        accountId,
        phone,
        password,
      })
      if (Number(response.code) !== 200 || response.status !== 'success') {
        throw new Error(response.message || '塔吉多账号密码登录失败')
      }
      message.success(response.message || '塔吉多登录成功，Token 已保存')
    } catch (error) {
      logger.error('塔吉多账号密码登录失败')
      message.error(error instanceof Error ? error.message : '塔吉多账号密码登录失败')
      throw error
    }
  }

  /**
   * 删除账号组
   */
  const deleteAccount = async (accountId: string): Promise<void> => {
    loading.value = true
    try {
      const editSession = await ensureConfigEditSession('ToolsConfig')
      if (!editSession) throw new Error('有其他用户正在编辑该配置')
      const response = await Service.deleteGameSignAccountApiToolsSignAccountDeletePost({
        accountId,
        ...editSession,
      })
      if (response.code !== 200) {
        throw new Error(response.message || '删除账号组失败')
      }
      await markConfigEditSaved('ToolsConfig')
      logger.info('账号组删除成功')
      message.success(t('misc.accountGroupDeleted'))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`删除账号组失败: ${errorMsg}`)
      message.error(t('misc.couldNotDeleteAccount'))
      throw error
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    addAccount,
    updateAccount,
    loginTaygedo,
    deleteAccount,
  }
}
