import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api'
import type { UserInBase, UserCreateOut, UserUpdateIn, UserDeleteIn, UserGetIn, UserReorderIn } from '@/api'
import { getLogger } from '@/utils/logger'
import { useAudioPlayer } from '@/composables/useAudioPlayer'

const logger = getLogger('用户API')

export function useUserApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 添加用户
  const addUser = async (scriptId: string): Promise<UserCreateOut | null> => {
    loading.value = true
    error.value = null

    try {
      const requestData: UserInBase = {
        scriptId,
      }

      const response = await Service.addUserApiScriptsUserAddPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || '添加用户失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 播放添加用户成功音频
      const { playSound } = useAudioPlayer()
      await playSound('add_user')

      return response
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '添加用户失败'
      error.value = errorMsg
      if (err && err.message && !err.message.includes('HTTP error')) {
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
      const requestData: UserUpdateIn = {
        scriptId,
        userId,
        data: userData,
      }

      logger.debug('发送更新用户请求')
      const response = await Service.updateUserApiScriptsUserUpdatePost(requestData)
      logger.debug('更新用户响应:', response)

      if (response.code !== 200) {
        const errorMsg = response.message || '更新用户失败'
        logger.error('更新用户失败:', errorMsg)
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // message.success(response.message || '用户更新成功')
      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '更新用户失败'
      error.value = errorMsg
      if (err && err.message && !err.message.includes('HTTP error')) {
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
      const requestData: UserGetIn = {
        scriptId,
        userId: userId || null,
      }

      const response = await Service.getUserApiScriptsUserGetPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || '获取用户列表失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return response
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '获取用户列表失败'
      error.value = errorMsg
      if (err && err.message && !err.message.includes('HTTP error')) {
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
      const requestData: UserDeleteIn = {
        scriptId,
        userId,
      }

      const response = await Service.deleteUserApiScriptsUserDeletePost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || '删除用户失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      // 播放删除用户成功音频
      const { playSound } = useAudioPlayer()
      await playSound('delete_user')

      // message.success(response.message || '用户删除成功')
      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '删除用户失败'
      error.value = errorMsg
      if (err && err.message && !err.message.includes('HTTP error')) {
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
      const requestData: UserReorderIn = {
        scriptId,
        indexList: userIds,
      }

      const response = await Service.reorderUserApiScriptsUserOrderPost(requestData)

      if (response.code !== 200) {
        const errorMsg = response.message || '用户排序失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '用户排序失败'
      error.value = errorMsg
      if (err && err.message && !err.message.includes('HTTP error')) {
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
