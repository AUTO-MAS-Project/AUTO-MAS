import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, type GameSignAccountGroupConfig } from '@/api'

export function useGameSignAccountApi() {
    const loading = ref(false)
    const logger = window.electronAPI.getLogger('签到账号API')

    /**
     * 添加账号组
     */
    const addAccount = async (): Promise<{ accountId: string; data: GameSignAccountGroupConfig } | null> => {
        loading.value = true
        try {
            const response = await Service.addGameSignAccountApiToolsSignAccountAddPost()
            if (response.code !== 200) {
                throw new Error(response.message || '添加账号组失败')
            }
            logger.info('账号组添加成功')
            return { accountId: response.accountId, data: response.data }
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error(`添加账号组失败: ${errorMsg}`)
            message.error('添加账号组失败')
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
            const response = await Service.updateGameSignAccountApiToolsSignAccountUpdatePost({
                accountId,
                data,
            })
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
            const response = await Service.deleteGameSignAccountApiToolsSignAccountDeletePost({
                accountId,
            })
            if (response.code !== 200) {
                throw new Error(response.message || '删除账号组失败')
            }
            logger.info('账号组删除成功')
            message.success('账号组已删除')
        } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error)
            logger.error(`删除账号组失败: ${errorMsg}`)
            message.error('删除账号组失败')
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
