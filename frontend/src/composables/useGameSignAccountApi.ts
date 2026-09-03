import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { GameSignService, Service, type GameSignAccountGroupConfig } from '@/api'

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
      const response = await Service.addGameSignAccountApiToolsSignAccountAddPost()
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
   * 使用森空岛手机号密码一次性换取并保存凭据。
   * 密码只在本次请求中存在，不写入前端状态或日志。
   */
  const loginSkland = async (accountId: string, phone: string, password: string): Promise<void> => {
    try {
      const response = await Service.loginSklandApiToolsSignAccountSklandLoginPost({
        accountId,
        phone,
        password,
      })
      if (Number(response.code) !== 200 || response.status !== 'success') {
        throw new Error(response.message || '森空岛手机号密码登录失败')
      }
      message.success(response.message || '森空岛登录成功，Token 已保存')
    } catch (error) {
      logger.error('森空岛手机号密码登录失败')
      message.error(error instanceof Error ? error.message : '森空岛手机号密码登录失败')
      throw error
    }
  }

  /**
   * 发送库街区短信验证码并返回短期会话。
   * 手机号只发送给后端和库街区，不写入配置或日志。
   */
  const sendKuroSmsCode = async (
    accountId: string,
    phone: string
  ): Promise<{ sessionId: string; expiresIn: number; requiresVerification: boolean }> => {
    let publicMessage = t('gamesign.toast.kuroSmsSendFailed')
    try {
      const response = await GameSignService.sendKuroSmsCodeApiToolsSignAccountKuroSmsSendPost({
        accountId,
        phone,
      })
      const requiresVerification =
        Number(response.code) === 409 && response.status === 'captcha_required'
      if (
        (!requiresVerification &&
          (Number(response.code) !== 200 || response.status !== 'success')) ||
        !response.sessionId
      ) {
        publicMessage = response.message || publicMessage
        throw new Error(publicMessage)
      }
      if (!requiresVerification) {
        message.success(response.message || '验证码已发送')
      }
      return {
        sessionId: response.sessionId,
        expiresIn: Number(response.expiresIn) || 600,
        requiresVerification,
      }
    } catch (error) {
      logger.error('库街区短信验证码发送失败')
      message.error(publicMessage)
      throw error
    }
  }

  /**
   * 使用短期会话和短信验证码换取并保存库街区 Token。
   * 验证码只存在于本次调用，不写入配置或日志。
   */
  const loginKuroSms = async (
    accountId: string,
    sessionId: string,
    phone: string,
    code: string
  ): Promise<void> => {
    let publicMessage = t('gamesign.toast.kuroSmsLoginFailed')
    try {
      const response = await GameSignService.loginKuroSmsApiToolsSignAccountKuroSmsLoginPost({
        accountId,
        sessionId,
        phone,
        code,
      })
      if (Number(response.code) !== 200 || response.status !== 'success') {
        publicMessage = response.message || publicMessage
        throw new Error(publicMessage)
      }
      message.success(response.message || '库街区登录成功，Token 已保存')
    } catch (error) {
      logger.error('库街区短信验证码登录失败')
      message.error(publicMessage)
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
    sendKuroSmsCode,
    loginKuroSms,
    loginTaygedo,
    loginSkland,
    deleteAccount,
  }
}
