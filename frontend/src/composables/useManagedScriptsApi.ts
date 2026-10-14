import { Service, TaskMode, type ScriptUpdateIn, type UserUpdateIn } from '@/api'
import { translate as t } from '@/i18n'
import { requestApi } from '@/utils/apiResult'

export function useManagedScriptsApi() {
  return {
    runUser: (scriptId: string, userId: string) =>
      requestApi(
        () =>
          Service.addTaskApiDispatchStartPost({
            mode: TaskMode.AUTO_PROXY,
            queueId: null,
            scriptId,
            userId,
          }),
        t('scripts.runUserFailed')
      ),
    getScripts: () =>
      requestApi(
        () => Service.getScriptsApiScriptsGetPost({ scriptId: null }),
        t('scripts.toast.loadFailed')
      ),
    getTypes: () =>
      requestApi(() => Service.listScriptTypesApiScriptsTypesPost(), t('scripts.toast.loadFailed')),
    updateScript: (body: ScriptUpdateIn) =>
      requestApi(
        () => Service.updateScriptApiScriptsUpdatePost(body),
        t('emulator.toast.saveFailed')
      ),
    updateUser: (body: UserUpdateIn) =>
      requestApi(
        () => Service.updateUserApiScriptsUserUpdatePost(body),
        t('emulator.toast.saveFailed')
      ),
    addScript: (type: string) =>
      requestApi(() => Service.addScriptApiScriptsAddPost({ type }), t('scripts.empty.desc')),
    deleteScript: (scriptId: string) =>
      requestApi(
        () => Service.deleteScriptApiScriptsDeletePost({ scriptId }),
        t('scripts.deleteScript')
      ),
    addUser: (scriptId: string) =>
      requestApi(() => Service.addUserApiScriptsUserAddPost({ scriptId }), t('scripts.addUser')),
    deleteUser: (scriptId: string, userId: string) =>
      requestApi(
        () => Service.deleteUserApiScriptsUserDeletePost({ scriptId, userId }),
        t('scripts.deleteUser')
      ),
    reorderScripts: (indexList: string[]) =>
      requestApi(
        () => Service.orderScriptsApiScriptsOrderPost({ indexList }),
        t('scripts.toast.loadFailed')
      ),
    reorderUsers: (scriptId: string, indexList: string[]) =>
      requestApi(
        () => Service.orderUsersApiScriptsUserOrderPost({ scriptId, indexList }),
        t('scripts.toast.loadFailed')
      ),
  }
}
