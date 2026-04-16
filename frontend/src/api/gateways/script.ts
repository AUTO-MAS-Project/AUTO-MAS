import {
  createScriptApiScriptsPost,
  createUserApiScriptsScriptIdUsersPost,
  deleteScriptApiScriptsScriptIdDelete,
  deleteUserApiScriptsScriptIdUsersUserIdDelete,
  exportScriptToFileApiScriptsScriptIdActionsExportFilePost,
  getScriptApiScriptsScriptIdGet,
  getUserApiScriptsScriptIdUsersUserIdGet,
  getUserInfrastructureOptionsApiScriptsScriptIdUsersUserIdInfrastructureOptionsGet,
  importInfrastructureApiScriptsScriptIdUsersUserIdActionsImportInfrastructurePost,
  importScriptFromFileApiScriptsScriptIdActionsImportFilePost,
  importScriptFromWebApiScriptsImportWebPost,
  importScriptFromWebApiScriptsScriptIdActionsImportWebPost,
  listScriptsApiScriptsGet,
  listUsersApiScriptsScriptIdUsersGet,
  reorderScriptsApiScriptsOrderPatch,
  reorderUsersApiScriptsScriptIdUsersOrderPatch,
  updateScriptApiScriptsScriptIdPatch,
  updateUserApiScriptsScriptIdUsersUserIdPatch,
  uploadScriptToWebApiScriptsScriptIdActionsUploadWebPost,
  uploadScriptToWebApiScriptsUploadWebPost,
} from '../generated/sdk.gen'
import type {
  IndexOrderPatch,
  InfrastructureImportBody,
  ScriptCreateIn,
  ScriptPatchBody,
  ScriptUploadBody,
  ScriptUrlBody,
  UserPatchBody,
} from '../generated/types.gen'

export const scriptApi = {
  list() {
    return listScriptsApiScriptsGet()
  },

  create(payload: ScriptCreateIn) {
    return createScriptApiScriptsPost({ body: payload })
  },

  get(scriptId: string) {
    return getScriptApiScriptsScriptIdGet({ path: { script_id: scriptId } })
  },

  update(scriptId: string, payload: ScriptPatchBody) {
    return updateScriptApiScriptsScriptIdPatch({
      path: { script_id: scriptId },
      body: payload,
    })
  },

  remove(scriptId: string) {
    return deleteScriptApiScriptsScriptIdDelete({ path: { script_id: scriptId } })
  },

  reorder(payload: IndexOrderPatch) {
    return reorderScriptsApiScriptsOrderPatch({ body: payload })
  },

  importFromFile(scriptId: string, path: string) {
    return importScriptFromFileApiScriptsScriptIdActionsImportFilePost({
      path: { script_id: scriptId },
      body: { path },
    })
  },

  exportToFile(scriptId: string, path: string) {
    return exportScriptToFileApiScriptsScriptIdActionsExportFilePost({
      path: { script_id: scriptId },
      body: { path },
    })
  },

  importFromWeb(scriptId: string, body: ScriptUrlBody) {
    return importScriptFromWebApiScriptsScriptIdActionsImportWebPost({
      path: { script_id: scriptId },
      body,
    })
  },

  importTemplateFromWeb(body: ScriptUrlBody) {
    return importScriptFromWebApiScriptsImportWebPost({ body })
  },

  uploadToWeb(scriptId: string, body: ScriptUploadBody) {
    return uploadScriptToWebApiScriptsScriptIdActionsUploadWebPost({
      path: { script_id: scriptId },
      body,
    })
  },

  uploadTemplateToWeb(body: ScriptUploadBody) {
    return uploadScriptToWebApiScriptsUploadWebPost({ body })
  },
}

export const userApi = {
  list(scriptId: string) {
    return listUsersApiScriptsScriptIdUsersGet({
      path: { script_id: scriptId },
    })
  },

  create(scriptId: string) {
    return createUserApiScriptsScriptIdUsersPost({ path: { script_id: scriptId } })
  },

  get(scriptId: string, userId: string) {
    return getUserApiScriptsScriptIdUsersUserIdGet({
      path: { script_id: scriptId, user_id: userId },
    })
  },

  update(scriptId: string, userId: string, payload: UserPatchBody) {
    return updateUserApiScriptsScriptIdUsersUserIdPatch({
      path: { script_id: scriptId, user_id: userId },
      body: payload,
    })
  },

  remove(scriptId: string, userId: string) {
    return deleteUserApiScriptsScriptIdUsersUserIdDelete({
      path: { script_id: scriptId, user_id: userId },
    })
  },

  reorder(scriptId: string, payload: IndexOrderPatch) {
    return reorderUsersApiScriptsScriptIdUsersOrderPatch({
      path: { script_id: scriptId },
      body: payload,
    })
  },

  importInfrastructure(scriptId: string, userId: string, body: InfrastructureImportBody) {
    return importInfrastructureApiScriptsScriptIdUsersUserIdActionsImportInfrastructurePost({
      path: { script_id: scriptId, user_id: userId },
      body,
    })
  },

  getInfrastructureOptions(scriptId: string, userId: string) {
    return getUserInfrastructureOptionsApiScriptsScriptIdUsersUserIdInfrastructureOptionsGet({
      path: { script_id: scriptId, user_id: userId },
    })
  },
}
