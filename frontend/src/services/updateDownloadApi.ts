import { Service } from '@/api'
export type { AppUpdateSnapshot as UpdateDownloadSnapshot } from '../../electron/services/appUpdateTypes'

const input = async () => {
  // 读取后端保存的更新来源、渠道和代理设置，并附上当前前端版本供主进程更新业务使用。
  const response = await Service.getScriptsApiSettingGetPost()
  if (response.code !== 200 || !response.data?.Update)
    throw new Error(response.message || '读取更新设置失败')
  const { Source, Channel, MirrorChyanCDK, ProxyAddress } = response.data.Update
  return {
    currentVersion: import.meta.env.VITE_APP_VERSION,
    settings: { Source, Channel, MirrorChyanCDK, ProxyAddress },
  }
}
export const updateDownloadApi = {
  status: () => /* 从桌面主进程读取应用更新状态快照。 */ window.electronAPI.appUpdateStatus(),
  start: async (version: string, downloader?: 'builtin' | 'fluxdown') =>
    /* 读取当前设置后，请求主进程按指定版本及可选下载渠道启动应用更新下载。 */ window.electronAPI.appUpdateStart(
      version,
      await input(),
      downloader
    ),
  check: async (forceCheck = false) =>
    /* 读取当前设置并携带强制检查标记，请求主进程查询可用应用版本。 */ window.electronAPI.appUpdateCheck(
      { ...(await input()), forceCheck }
    ),
  cancel: () =>
    /* 请求主进程取消应用更新下载并等待资源收尾。 */ window.electronAPI.appUpdateCancel(),
  switchToCnb: () =>
    /* 请求主进程将当前下载切换到 CNB 来源。 */ window.electronAPI.appUpdateSwitch(),
  install: () => /* 请求主进程执行已准备更新包的安装流程。 */ window.electronAPI.appUpdateInstall(),
}
