// BetterGI 自定义配置组管理（名称 + 启用开关，表格化管理）
import { computed, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { TableColumnsType } from 'ant-design-vue'
import { BetterGiService } from '@/api'

const logger = window.electronAPI.getLogger('BetterGI自定义配置组')

export interface BettergiCustomGroupRow {
  name: string
  enabled: boolean
}

export interface BettergiCustomGroupOptions {
  /** 所在脚本，用于从 BetterGI 现有配置读取自定义组 */
  scriptId: string
  /** 父组件表单 OneDragon 区块的读取器——须是 getter，父组件在 loadUser 时会整体替换
   *  formData.OneDragon，若传静态引用则本 composable 一直读写失效的旧对象，开关不再生效 */
  oneDragon: () => { CustomGroups: string | any[]; IfUseCustomGroups: boolean }
  /** 一条龙配置名（Task.OneDragonConfigName），决定从 BetterGI 哪份配置读取自定义组 */
  configName: () => string
  /** 用户独立配置（Info.IfUseMasConfig）：为 true 时改读 MAS 槽位「MAS独立配置」而非同名实配 */
  masConfig: () => boolean
  /** 是否处于「脚本直控配置」之外（可编辑）。为 true 时允许交互 */
  editable: () => boolean
  /** 保存某字段到后端（形如 'OneDragon.CustomGroups'），返回是否保存成功 */
  saveField: (key: string, value: unknown) => Promise<boolean>
}

/**
 * BetterGI 自定义配置组管理：总开关、表格（名称 + 启用）、批量删除与添加。
 *
 * 状态与 `oneDragon.CustomGroups`（JSON 字符串）保持同步：每次 `persist` 既写回表单
 * 又经 `saveField` 落库；首次开启总开关且表格为空时，从 BetterGI 现有配置自动加载。
 */
export function useBettergiCustomGroups(options: BettergiCustomGroupOptions) {
  const { t } = useI18n()
  const { scriptId, oneDragon: getOneDragon, configName, masConfig, editable, saveField } = options
  const oneDragon = () => getOneDragon()

  const table = ref<BettergiCustomGroupRow[]>([])
  const selectedKeys = ref<string[]>([])
  const modal = reactive({
    open: false,
    name: '',
    saving: false,
    // 「添加配置组」弹窗的下拉候选项：BGI 现有的自定义配置组名（已入表的排除）
    addOptions: [] as Array<{ value: string; label: string }>,
  })

  const columns = computed<TableColumnsType>(() => [
    { title: t('edit.bettergiGroupNameColumn'), dataIndex: 'name', key: 'name' },
    {
      title: t('edit.bettergiGroupEnabledColumn'),
      dataIndex: 'enabled',
      key: 'enabled',
      width: 120,
    },
  ])

  const rowSelection = computed(() => ({
    selectedRowKeys: selectedKeys.value,
    onChange: (keys: (string | number)[]) => {
      selectedKeys.value = keys.map(String)
    },
  }))

  const parseList = (raw: unknown): BettergiCustomGroupRow[] => {
    let arr: unknown = raw
    if (typeof raw === 'string') {
      try {
        arr = JSON.parse(raw)
      } catch {
        return []
      }
    }
    if (!Array.isArray(arr)) return []
    return arr
      .filter((x): x is Record<string, unknown> => !!x && typeof x.name === 'string')
      // enabled 缺失时与后端 parse_custom_groups 默认一致视为启用（仅显式 false 禁用）
      .map(x => ({ name: x.name as string, enabled: x.enabled !== false }))
  }

  const syncFromForm = () => {
    table.value = parseList(oneDragon().CustomGroups)
  }

  const mergeRows = (rows: BettergiCustomGroupRow[]) => {
    const existing = new Map(table.value.map(r => [r.name, r]))
    for (const r of rows) {
      if (!existing.has(r.name)) existing.set(r.name, r)
    }
    table.value = Array.from(existing.values())
  }

  const fetchBettergiGroups = async (): Promise<BettergiCustomGroupRow[]> => {
    try {
      const resp =
        await BetterGiService.getBettergiCustomGroupsApiApiScriptsBettergiOneDragonCustomGroupsGet(
          scriptId,
          configName(),
          masConfig()
        )
      return resp.code === 200 && Array.isArray(resp.data) ? resp.data : []
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
      return []
    }
  }

  const loadFromBettergi = async () => {
    mergeRows(await fetchBettergiGroups())
  }

  /** 拉取「添加配置组」下拉候选：BGI 现有自定义组名，剔除已入表的 */
  const refreshAddOptions = async () => {
    const existing = new Set(table.value.map(r => r.name))
    const groups = await fetchBettergiGroups()
    modal.addOptions = groups
      .filter(g => !existing.has(g.name))
      .map(g => ({ value: g.name, label: g.name }))
  }

  const persist = () => {
    const str = JSON.stringify(table.value)
    oneDragon().CustomGroups = str
    void saveField('OneDragon.CustomGroups', str)
  }

  const toggleMaster = () => {
    if (!editable()) return
    const cur = oneDragon()
    const next = !cur.IfUseCustomGroups
    cur.IfUseCustomGroups = next
    void saveField('OneDragon.IfUseCustomGroups', next)
    // 首次开启且表格为空时，从 BetterGI 自动加载现有自定义组
    if (next && table.value.length === 0) {
      void loadFromBettergi()
    }
  }

  const openAdd = async () => {
    modal.name = ''
    // 每次打开都刷新候选，保证已新增/删除的组名在下拉里即时反映
    await refreshAddOptions()
    modal.open = true
  }

  const confirmAdd = async () => {
    const name = modal.name.trim()
    if (!name) {
      message.warning(t('edit.bettergiEnterGroupName'))
      return
    }
    if (table.value.some(r => r.name === name)) {
      message.warning(t('edit.bettergiGroupExists'))
      return
    }
    modal.saving = true
    try {
      table.value.push({ name, enabled: true })
      persist()
      modal.open = false
    } finally {
      modal.saving = false
    }
  }

  const deleteSelected = () => {
    const removed = new Set(selectedKeys.value)
    table.value = table.value.filter(r => !removed.has(r.name))
    selectedKeys.value = []
    persist()
  }

  const toggleEnabled = (record: BettergiCustomGroupRow) => {
    record.enabled = !record.enabled
    persist()
  }

  /** 按名称把配置组加入自定义组（供一条龙队列「加入」复用）；已存在返回 false */
  const addByName = (name: string): boolean => {
    const trimmed = (name || '').trim()
    if (!trimmed) return false
    if (table.value.some(r => r.name === trimmed)) return false
    table.value.push({ name: trimmed, enabled: true })
    persist()
    return true
  }

  return {
    table,
    selectedKeys,
    modal,
    columns,
    rowSelection,
    syncFromForm,
    loadFromBettergi,
    toggleMaster,
    openAdd,
    confirmAdd,
    deleteSelected,
    toggleEnabled,
    addByName,
  }
}
