import { computed, ref, toValue, onScopeDispose, type MaybeRefOrGetter } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { BetterGiService, type BetterGIPathingNode, type ComboBoxItem } from '@/api'
import { openExternalUrl } from '@/utils/openExternal'

/** 页面与添加选择器共享同一份目录快照；不持久化，也不合并保存队列。 */
export function useBettergiCatalogs(scriptId: string, userId: MaybeRefOrGetter<string>) {
  const { t } = useI18n()
  const logger = window.electronAPI.getLogger('BetterGI用户编辑')
  let active = true
  let sequence = 0
  const versions = new Map<string, number>()
  const trackRead = (key: string) => {
    const version = ++sequence
    versions.set(key, version)
    return () => active && versions.get(key) === version
  }
  const invalidateReads = () => versions.clear()
  onScopeDispose(() => {
    active = false
    invalidateReads()
  })
  // 可加入一条龙的 BetterGI 自定义 JS 脚本候选。
  // value=脚本目录名（BetterGI 按目录名定位任务，落库/执行用它）；label=manifest 中文显示名（展示用）。
  const jsScriptOptions = ref<{ label: string; value: string }[]>([])

  // CustomGroups 中某名字是否命中 BetterGI JsScript 目录（来源为 JS 脚本时队列行标为 js 前缀）
  const isJsScriptName = (name: string): boolean =>
    jsScriptOptions.value.some(o => o.value === name)

  // BetterGI「配置组」候选：{RootPath}/User/ScriptGroup/*.json 的文件名（即组名）。
  // value/label 均用文件名（不含 .json），BetterGI 一条龙按该名引用配置组。
  const scriptGroupOptions = ref<{ label: string; value: string }[]>([])

  // CustomGroups 中某名字是否命中 BetterGI ScriptGroup 配置组目录
  const isScriptGroupName = (name: string): boolean =>
    scriptGroupOptions.value.some(o => o.value === name)

  // MAS 自建的配置组：运行期物化产物（MAS-{短id}-自定义配置组N / MAS-{短id}-执行层段N）
  // 与切号组（MAS切换账号）、执行层资源模板组（MAS一条龙）。它们只应存在于运行期或
  // BGI 副本目录，不该出现在「添加配置组」弹窗的「配置组」候选里。
  const isMasOwnGroup = (name: string): boolean =>
    name.startsWith('MAS-') || name === 'MAS切换账号' || name === 'MAS一条龙'

  // BetterGI「录制」候选：{RootPath}/User/KeyMouseScript/*.json 的文件名（即脚本名）。
  const keyMouseOptions = ref<{ label: string; value: string }[]>([])

  // CustomGroups 中某名字是否命中 BetterGI KeyMouseScript 录制目录（来源为录制时队列行标为录制前缀）
  const isKeyMouseName = (name: string): boolean =>
    keyMouseOptions.value.some(o => o.value === name)

  // JS 目录名 → manifest 中文显示名（候选/队列展示用；找不到时回退目录名）
  const jsDisplayName = (folder: string): string =>
    jsScriptOptions.value.find(o => o.value === folder)?.label || folder

  // 地图追踪目录树（BetterGIPathingNode）与常用目录/可执行文件路径的加载状态
  const pathingTreeRoot = ref('')

  const pathingTreeDirs = ref<BetterGIPathingNode[]>([])

  const bettergiDirs = ref<{
    repoDir?: string
    jsScriptDir?: string
    autoPathingDir?: string
    oneDragonDir?: string
    scriptGroupDir?: string
    keyMouseScriptDir?: string
    autoFightDir?: string
    exePath?: string
  }>({})

  // 当前选中的目录节点 key（相对路径）
  const selectedPathingKey = ref('')

  // AutoPathing 目录树所有文件的相对路径集合（用于识别 pathing 行）
  const pathingFileSet = computed<Set<string>>(() => {
    const set = new Set<string>()
    const walk = (nodes: BetterGIPathingNode[] | undefined) => {
      for (const n of nodes || []) {
        for (const f of n.files || []) set.add(f)
        walk(n.dirs)
      }
    }
    walk(pathingTreeDirs.value)
    return set
  })

  // CustomGroups 中某名字是否命中 AutoPathing 文件相对路径（来源为地图追踪时队列行标为 pathing 前缀）
  const isPathingName = (name: string): boolean =>
    pathingTreeDirs.value.length > 0 && pathingFileSet.value.has(name)

  // 加载可加入一条龙的 BetterGI 自定义 JS 脚本（实时扫描，反映玩家手工放置/订阅的脚本）
  const loadJsScripts = async () => {
    const current = trackRead('js')
    try {
      const resp =
        await BetterGiService.getBettergiJsScriptsApiApiScriptsBettergiJsScriptsGet(scriptId)
      if (!current()) return
      jsScriptOptions.value = (resp.data || [])
        .filter(
          (item): item is ComboBoxItem & { label: string; value: string } =>
            item.label != null && item.value != null
        )
        .map(item => ({ label: item.label, value: item.value }))
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }

  // 加载 BetterGI「配置组」候选（BGI User/ScriptGroup + 该用户 per-user 副本的文件名并集）。
  // userId 非空时后端把 MAS 独立配置下用户自建的副本名一并返回，复制出的新组才能被识别为可编辑 scriptgroup。
  const loadScriptGroups = async () => {
    const current = trackRead('groups')
    const contextUserId = toValue(userId)
    try {
      const resp =
        await BetterGiService.getBettergiScriptGroupsApiApiScriptsBettergiScriptGroupsGet(
          scriptId,
          contextUserId || undefined
        )
      if (!current() || contextUserId !== toValue(userId)) return
      scriptGroupOptions.value = (resp.data || [])
        .filter(
          (item): item is ComboBoxItem & { label: string; value: string } =>
            item.label != null && item.value != null
        )
        .map(item => ({ label: item.label, value: item.value }))
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }

  // 加载 BetterGI「录制」候选（BGI User/KeyMouseScript 下的键鼠脚本文件名）。
  const loadKeyMouseScripts = async () => {
    const current = trackRead('recordings')
    try {
      const resp =
        await BetterGiService.getBettergiKeyMouseScriptsApiApiScriptsBettergiKeyMouseScriptsGet(
          scriptId
        )
      if (!current()) return
      keyMouseOptions.value = (resp.data || [])
        .filter(
          (item): item is ComboBoxItem & { label: string; value: string } =>
            item.label != null && item.value != null
        )
        .map(item => ({ label: item.label, value: item.value }))
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }

  // ---- 地图追踪（AutoPathing）目录树浏览 ----
  // 树数据节点：key 为「目录路径」，files 为该目录下路径文件（不含 .json、含目录前缀）
  type PathingTreeNode = {
    key: string
    title: string
    files?: string[]
    children?: PathingTreeNode[]
  }

  // 加载三个常用目录（打开按钮用）与 AutoPathing 目录树
  const loadBettergiDirs = async () => {
    const current = trackRead('directories')
    try {
      const resp = await BetterGiService.getBettergiScriptDirsApiApiScriptsBettergiDirsGet(scriptId)
      if (current() && resp && resp.repoDir != null) {
        bettergiDirs.value = {
          repoDir: resp.repoDir,
          jsScriptDir: resp.jsScriptDir ?? undefined,
          autoPathingDir: resp.autoPathingDir ?? undefined,
          oneDragonDir: resp.oneDragonDir ?? undefined,
          scriptGroupDir: resp.scriptGroupDir ?? undefined,
          keyMouseScriptDir: resp.keyMouseScriptDir ?? undefined,
          autoFightDir: resp.autoFightDir ?? undefined,
          exePath: resp.exePath ?? undefined,
        }
      }
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }

  // BetterGI 官方在线脚本站（本地检出目录无法跳转其内部页面，改用网页版脚本仓库）
  const BGI_SCRIPT_SITE = 'https://s.bettergi.com/'

  // 打开某目录（脚本目录 / 路径目录 / 录制 / 配置组）；脚本仓库走在线网页
  const openBettergiDir = async (
    kind: 'jsScript' | 'autoPathing' | 'keyMouse' | 'scriptGroup' | 'autoFight'
  ) => {
    if (!bettergiDirs.value.jsScriptDir) await loadBettergiDirs()
    const target =
      kind === 'jsScript'
        ? bettergiDirs.value.jsScriptDir
        : kind === 'autoPathing'
          ? bettergiDirs.value.autoPathingDir
          : kind === 'keyMouse'
            ? bettergiDirs.value.keyMouseScriptDir
            : kind === 'autoFight'
              ? bettergiDirs.value.autoFightDir
              : bettergiDirs.value.scriptGroupDir
    if (!target) {
      message.warning(t('core.edit.bettergiPathingEmptyTree'))
      return
    }
    try {
      await window.electronAPI.openFile(target)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }

  // 打开 BetterGI 在线脚本仓库（官方网页版）
  const openBettergiScriptSite = () => {
    void openExternalUrl(BGI_SCRIPT_SITE)
  }

  // 打开 BetterGI 调度器：启动 BGI 主程序（其 GUI 内置一条龙/调度入口）
  const openBettergiScheduler = async () => {
    if (!bettergiDirs.value.exePath) await loadBettergiDirs()
    const exe = bettergiDirs.value.exePath
    if (!exe) {
      message.warning(t('core.edit.bettergiPathingEmptyTree'))
      return
    }
    try {
      await window.electronAPI.openFile(exe)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }

  // 加载 AutoPathing 目录树
  const loadPathingTree = async () => {
    const current = trackRead('pathing')
    try {
      const resp =
        await BetterGiService.getBettergiAutoPathingTreeApiApiScriptsBettergiAutoPathingTreeGet(
          scriptId
        )
      if (!current()) return
      pathingTreeRoot.value = resp.root || ''
      pathingTreeDirs.value = resp.dirs || []
      // 默认选中第一个顶层目录，让右表立刻有内容
      const first = resp.dirs?.[0]
      if (first) selectedPathingKey.value = first.name
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }

  // 把后端目录树转为 a-tree 数据（key=目录相对路径，title=目录名，files 供右表）
  const buildPathingTreeData = (nodes: BetterGIPathingNode[], parentKey = ''): PathingTreeNode[] =>
    nodes.map(n => {
      const key = parentKey ? `${parentKey}/${n.name}` : n.name
      return {
        key,
        title: n.name,
        files: n.files || [],
        children: buildPathingTreeData(n.dirs || [], key),
      }
    })

  const pathingTreeData = computed<PathingTreeNode[]>(() =>
    buildPathingTreeData(pathingTreeDirs.value)
  )

  // 当前选中的目录节点（展示其下文件）
  const selectedPathingNode = computed<PathingTreeNode | null>(() => {
    const findNode = (nodes: PathingTreeNode[], key: string): PathingTreeNode | null => {
      for (const n of nodes) {
        if (n.key === key) return n
        const hit = findNode(n.children || [], key)
        if (hit) return hit
      }
      return null
    }
    return findNode(pathingTreeData.value, selectedPathingKey.value)
  })

  // 选中目录（含其全部子目录）下的路径文件，去重保序
  const selectedPathingFiles = computed<string[]>(() => {
    const collect = (node: PathingTreeNode | null): string[] => {
      if (!node) return []
      const own = node.files || []
      const childFiles = (node.children || []).flatMap(c => collect(c))
      return [...new Set([...own, ...childFiles])]
    }
    return collect(selectedPathingNode.value)
  })
  return {
    invalidateReads,
    jsScriptOptions,
    isJsScriptName,
    scriptGroupOptions,
    isScriptGroupName,
    isMasOwnGroup,
    keyMouseOptions,
    isKeyMouseName,
    jsDisplayName,
    pathingTreeRoot,
    pathingTreeDirs,
    bettergiDirs,
    selectedPathingKey,
    pathingFileSet,
    isPathingName,
    loadJsScripts,
    loadScriptGroups,
    loadKeyMouseScripts,
    loadBettergiDirs,
    openBettergiDir,
    openBettergiScriptSite,
    openBettergiScheduler,
    loadPathingTree,
    pathingTreeData,
    selectedPathingFiles,
  }
}
