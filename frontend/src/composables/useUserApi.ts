import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'
import { beginUserChanges, rememberUserAnalytics } from '@/utils/userAnalytics'
import { getApiErrorCode, getApiErrorMessage } from '@/utils/apiError'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { Service } from '@/api'
import type {
  UserInBase,
  UserCreateOut,
  UserUpdateIn,
  UserDeleteIn,
  UserGetIn,
  UserReorderIn,
  UserConfigDirIn,
} from '@/api'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { getTaskRuntimeStates } from '@/composables/useTaskRuntimeState'
import { isScriptConfigLocked } from '@/utils/scriptConfigLock'
import {
  analyticsConfigSection,
  analyticsCountBucket,
  beginAnalyticsOperation,
  getAnalyticsScriptType,
} from '@/utils/analytics'

const logger = window.electronAPI.getLogger('用户API')

interface AddUserOptions {
  showError?: boolean
}

export function useUserApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const addUserErrorCode = ref<number | null>(null)

  // 添加用户
  const addUser = async (
    scriptId: string,
    options: AddUserOptions = {}
  ): Promise<UserCreateOut | null> => {
    const operation = beginAnalyticsOperation('user_create_finished')
    const script_type = getAnalyticsScriptType(scriptId)
    if (isScriptConfigLocked(getTaskRuntimeStates(), scriptId)) {
      operation.finish({ script_type, outcome: 'blocked' })
      const errorMsg = t('edit.configLocked')
      error.value = errorMsg
      addUserErrorCode.value = null
      if (options.showError ?? true) message.warning(errorMsg)
      return null
    }

    loading.value = true
    error.value = null
    addUserErrorCode.value = null
    const showError = options.showError ?? true

    try {
      const requestData: UserInBase = {
        scriptId,
      }

      const response = await Service.addUserApiScriptsUserAddPost(requestData)

      if (response.code !== 200) {
        addUserErrorCode.value = response.code ?? null
        const errorMsg = response.message || t('apiErrors.userAddFailed')
        throw new Error(errorMsg)
      }

      operation.finish({ script_type, outcome: response.userId ? 'success' : 'failure' })
      // 播放添加用户成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_user')

      return response
    } catch (err) {
      operation.finish({ script_type, outcome: 'failure' })
      addUserErrorCode.value ??= getApiErrorCode(err)
      const errorMsg = getApiErrorMessage(err, t('apiErrors.userAddFailed'))
      error.value = errorMsg
      if (showError) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  // 更新用户
  const updateUser = async (
    scriptId: string,
    userId: string,
    userData: UserUpdateIn['data']
  ): Promise<boolean> => {
    const finishChanges = beginUserChanges(
      scriptId,
      userId,
      getAnalyticsScriptType(scriptId),
      userData.Info
    )
    const operation = beginAnalyticsOperation('config_write_finished')
    const dimensions = {
      owner_kind: 'user' as const,
      section_kind: analyticsConfigSection(userData),
      script_type: getAnalyticsScriptType(scriptId),
    }
    if (isScriptConfigLocked(getTaskRuntimeStates(), scriptId)) {
      finishChanges('blocked')
      operation.finish({ ...dimensions, outcome: 'blocked' })
      const errorMsg = t('edit.configLocked')
      error.value = errorMsg
      message.warning(errorMsg)
      return false
    }

    loading.value = true
    error.value = null

    try {
      const requestData: UserUpdateIn = {
        scriptId,
        userId,
        data: userData,
      }

      logger.debug('发送更新用户请求')
      const response = await Service.updateUserApiScriptsUserUpdatePost(requestData)
      logger.debug(`更新用户响应: ${JSON.stringify(response)}`)

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.userSaveFailed')
        logger.error(`更新用户失败: ${errorMsg}`)
        throw new Error(errorMsg)
      }

      finishChanges('success')
      operation.finish({ ...dimensions, outcome: 'success' })
      return true
    } catch (err) {
      finishChanges('failure')
      operation.finish({ ...dimensions, outcome: 'failure' })
      const errorMsg = getApiErrorMessage(err, t('apiErrors.userSaveFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return false
    } finally {
      loading.value = false
    }
  }

  // 获取用户列表
  const getUsers = async (scriptId: string, userId?: string) => {
    loading.value = true
    error.value = null

    try {
      const requestData: UserGetIn = {
        scriptId,
        userId: userId || null,
      }

      const response = await Service.getUserApiScriptsUserGetPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.userListFailed')
        throw new Error(errorMsg)
      }

      for (const [id, user] of Object.entries(response.data))
        rememberUserAnalytics(scriptId, id, user.Info)
      return response
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.userListFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return null
    } finally {
      loading.value = false
    }
  }

  // 删除用户
  const deleteUser = async (scriptId: string, userId: string): Promise<boolean> => {
    if (isScriptConfigLocked(getTaskRuntimeStates(), scriptId)) {
      const errorMsg = t('edit.configLocked')
      error.value = errorMsg
      message.warning(errorMsg)
      return false
    }

    loading.value = true
    error.value = null

    try {
      const requestData: UserDeleteIn = {
        scriptId,
        userId,
      }

      const response = await observeFeature(
        'user_manage_finished',
        { action: 'delete', script_type: getAnalyticsScriptType(scriptId), count_bucket: '1' },
        () => Service.deleteUserApiScriptsUserDeletePost(requestData),
        apiOutcome
      )

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.userDeleteFailed')
        throw new Error(errorMsg)
      }

      // 播放删除用户成功音频
      const { playSound } = useAudioPlayer()
      await playSound('delete_user')

      return true
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.userDeleteFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return false
    } finally {
      loading.value = false
    }
  }

  // 重新排序用户
  const reorderUser = async (scriptId: string, userIds: string[]): Promise<boolean> => {
    if (isScriptConfigLocked(getTaskRuntimeStates(), scriptId)) {
      const errorMsg = t('edit.configLocked')
      error.value = errorMsg
      message.warning(errorMsg)
      return false
    }

    // loading.value = true
    error.value = null

    try {
      const requestData: UserReorderIn = {
        scriptId,
        indexList: userIds,
      }

      const response = await observeFeature(
        'user_manage_finished',
        {
          action: 'reorder',
          script_type: getAnalyticsScriptType(scriptId),
          count_bucket: analyticsCountBucket(userIds.length),
        },
        () => Service.reorderUserApiScriptsUserOrderPost(requestData),
        apiOutcome
      )

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.userOrderFailed')
        throw new Error(errorMsg)
      }

      return true
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.userOrderFailed'))
      error.value = errorMsg
      message.error(errorMsg)
      return false
    } finally {
      // loading.value = false
    }
  }

  // 打开用户配置目录
  const openUserConfigFolder = async (scriptId: string, userId: string): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const requestData: UserConfigDirIn = {
        scriptId,
        userId,
      }

      const response = await Service.getUserConfigDirApiScriptsUserConfigDirPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || t('apiErrors.userConfigPathFailed')
        throw new Error(errorMsg)
      }

      if (!response.path) {
        throw new Error(t('apiErrors.userConfigPathFailed'))
      }

      const result = await window.electronAPI.openFile(response.path)
      if (!result.success) {
        const openError = result.error || t('apiErrors.userConfigOpenFailed')
        logger.error(`打开用户配置目录失败: ${openError}`)
        throw new Error(openError)
      }

      return true
    } catch (err) {
      const errorMsg = getApiErrorMessage(err, t('apiErrors.userConfigOpenFailed'))
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
    addUserErrorCode,
    addUser,
    getUsers,
    updateUser,
    deleteUser,
    reorderUser,
    openUserConfigFolder,
  }
}
