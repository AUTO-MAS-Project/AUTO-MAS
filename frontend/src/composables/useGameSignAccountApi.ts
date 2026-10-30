import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'
import { communityAccountAction } from '@/utils/communityAnalytics'
import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type GameSignAccountGroupConfig } from '@/api'

export function useGameSignAccountApi() {
  const loading = ref(false)
  const logger = window.electronAPI.getLogger('签到账号API')

  /**
   * 添加账号组
   */
  const addAccount = async (): Promise<{
    accountId: string
    data: GameSignAccountGroupConfig
  } | null> => {
    loading.value = true
    try {
      const response = await observeFeature(
        'community_account_manage_finished',
        { action: 'create' },
        () => Service.addGameSignAccountApiToolsSignAccountAddPost(),
        result => (result.code === 200 && result.accountId && result.data ? 'success' : 'failure')
      )
      if (response.code !== 200) {
        throw new Error(response.message || '添加账号组失败')
      }
      if (!response.accountId || !response.data) {
        throw new Error('添加账号组失败：服务端响应缺少账号信息')
      }
      logger.info('账号组添加成功')
      return { accountId: response.accountId, data: response.data }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`添加账号组失败: ${errorMsg}`)
      message.error(t('core.misc.couldNotAddAccount'))
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
    data: Partial<GameSignAccountGroupConfig>
  ): Promise<void> => {
    // 只提交改动字段：账号组里的凭据是页面加载时的快照，全量回写会把
    // 后台在这期间轮换出的新凭据覆盖回旧值（一次性 refreshToken 尤其致命）。
    try {
      const response = await observeFeature(
        'community_account_manage_finished',
        {
          action: communityAccountAction(data),
        },
        () =>
          Service.updateGameSignAccountApiToolsSignAccountUpdatePost({
            accountId,
            data,
          }),
        apiOutcome
      )
      if (response.code !== 200) {
        throw new Error(response.message || '更新账号组失败')
      }
      logger.info('账号组更新成功')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新账号组失败: ${errorMsg}`)
      throw error
    }
  }

  /**
   * 删除账号组
   */
  const deleteAccount = async (accountId: string): Promise<void> => {
    loading.value = true
    try {
      const response = await observeFeature(
        'community_account_manage_finished',
        { action: 'delete' },
        () =>
          Service.deleteGameSignAccountApiToolsSignAccountDeletePost({
            accountId,
          }),
        apiOutcome
      )
      if (response.code !== 200) {
        throw new Error(response.message || '删除账号组失败')
      }
      logger.info('账号组删除成功')
      message.success(t('core.misc.accountGroupDeleted'))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`删除账号组失败: ${errorMsg}`)
      message.error(t('core.misc.couldNotDeleteAccount'))
      throw error
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    addAccount,
    updateAccount,
    deleteAccount,
  }
}
