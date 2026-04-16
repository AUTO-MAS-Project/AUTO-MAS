import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { userApi } from '@/api'
import { useAudioPlayer } from '@/composables/useAudioPlayer'

const logger = window.electronAPI.getLogger('用户API')

export function useUserApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 添加用户
  const addUser = async (scriptId: string): Promise<any | null> => {
    loading.value = true
    error.value = null

    try {
      const response = await userApi.create(scriptId)

      if (response.code !== 200) {
        const errorMsg = response.message || '添加用户失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 播放添加用户成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_user')

      return {
        ...response,
        userId: response.id,
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '添加用户失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  // 更新用户
  const updateUser = async (scriptId: string, userId: string, userData: any): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      logger.debug('发送更新用户请求')
      const response = await userApi.update(scriptId, userId, {
        data: userData,
      })
      logger.debug(`更新用户响应: ${JSON.stringify(response)}`)

      if (response.code !== 200) {
        const errorMsg = response.message || '更新用户失败'
        logger.error(`更新用户失败: ${errorMsg}`)
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '更新用户失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
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
      let response: any
      if (userId) {
        const itemResponse = await userApi.get(scriptId, userId)
        response = {
          code: itemResponse.code,
          status: itemResponse.status,
          message: itemResponse.message,
          index: [{ uid: userId, type: 'UserConfig' }],
          data: { [userId]: itemResponse.data },
        }
      } else {
        response = await userApi.list(scriptId)
      }

      if (response.code !== 200) {
        const errorMsg = response.message || '获取用户列表失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return response
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取用户列表失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  // 删除用户
  const deleteUser = async (scriptId: string, userId: string): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const response = await userApi.remove(scriptId, userId)

      if (response.code !== 200) {
        const errorMsg = response.message || '删除用户失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 播放删除用户成功音频
      const { playSound } = useAudioPlayer()
      await playSound('delete_user')

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '删除用户失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      loading.value = false
    }
  }

  // 重新排序用户
  const reorderUser = async (scriptId: string, userIds: string[]): Promise<boolean> => {
    // loading.value = true
    error.value = null

    try {
      const response = await userApi.reorder(scriptId, {
        index_list: userIds,
      })

      if (response.code !== 200) {
        const errorMsg = response.message || '用户排序失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '用户排序失败'
      error.value = errorMsg
      if (err instanceof Error && !err.message.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      // loading.value = false
    }
  }

  return {
    loading,
    error,
    addUser,
    getUsers,
    updateUser,
    deleteUser,
    reorderUser,
  }
}
