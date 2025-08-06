import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api'
import type { UserInBase, UserCreateOut, UserUpdateIn, UserDeleteIn } from '@/api'

export function useUserApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 添加用户
  const addUser = async (scriptId: string): Promise<UserCreateOut | null> => {
    loading.value = true
    error.value = null

    try {
      const requestData: UserInBase = {
        scriptId
      }

      const response = await Service.addUserApiScriptsUserAddPost(requestData)
      
      if (response.code !== 200) {
        const errorMsg = response.message || '添加用户失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      return response
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '添加用户失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return null
    } finally {
      loading.value = false
    }
  }

  // 更新用户
  const updateUser = async (scriptId: string, userId: string, userData: Record<string, Record<string, any>>): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      const requestData: UserUpdateIn = {
        scriptId,
        userId,
        data: userData
      }

      const response = await Service.updateUserApiScriptsUserUpdatePost(requestData)
      
      if (response.code !== 200) {
        const errorMsg = response.message || '更新用户失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      message.success(response.message || '用户更新成功')
      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '更新用户失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
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
        userId
      }

      const response = await Service.deleteUserApiScriptsUserDeletePost(requestData)
      
      if (response.code !== 200) {
        const errorMsg = response.message || '删除用户失败'
        message.error(errorMsg)
        throw new Error(errorMsg)
      }

      message.success(response.message || '用户删除成功')
      return true
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '删除用户失败'
      error.value = errorMsg
      if (!err.message?.includes('HTTP error')) {
        message.error(errorMsg)
      }
      return false
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    error,
    addUser,
    updateUser,
    deleteUser,
  }
}