import * as fs from 'node:fs/promises'
import * as path from 'node:path'
import { execFile } from 'node:child_process'
import { getLogger } from './logger'

const logger = getLogger('更新暂存')

interface ProcessIdentity {
  pid: number
  started: string | null
  executable: string | null
}

interface UpdateProcess extends ProcessIdentity {
  name: string
  command: string | null
}

interface MaterialState {
  kind: 'package' | 'runtime'
  version: string
  phase: 'preparing' | 'ready' | 'handoff'
  owner: ProcessIdentity
  installer?: ProcessIdentity
}

async function listProcesses(): Promise<UpdateProcess[]> {
  // 一次读取 Windows 进程身份和命令行，供持有者校验及安装器交接窗口恢复使用。
  const script = `
    $ErrorActionPreference = 'Stop'
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    @(Get-CimInstance Win32_Process | ForEach-Object {
      [PSCustomObject]@{
        pid = [int]$_.ProcessId
        name = $_.Name
        started = if ($_.CreationDate) { $_.CreationDate.ToUniversalTime().ToString('o') } else { $null }
        executable = $_.ExecutablePath
        command = $_.CommandLine
      }
    }) | ConvertTo-Json -Compress
  `
  const stdout = await new Promise<string>((resolve, reject) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', script],
      {
        windowsHide: true,
        timeout: 10_000,
        maxBuffer: 8 * 1024 * 1024,
        encoding: 'utf8',
      },
      (error, output) => {
        // 查询超时或失败不能转换成空进程列表，否则会误删仍在使用的材料。
        if (error) reject(error)
        else resolve(output)
      }
    )
  })
  const records: unknown = JSON.parse(stdout.replace(/^\uFEFF/, ''))
  if (
    !Array.isArray(records) ||
    !records.every(
      record =>
        record &&
        typeof record === 'object' &&
        Number.isInteger(record.pid) &&
        typeof record.name === 'string' &&
        (record.started === null || typeof record.started === 'string') &&
        (record.executable === null || typeof record.executable === 'string') &&
        (record.command === null || typeof record.command === 'string')
    )
  )
    throw new Error('无法读取更新材料的进程持有状态')
  return records
}

function validIdentity(value: unknown): value is ProcessIdentity {
  // 校验落盘的进程身份；缺失启动时间意味着身份未确认，恢复时采取保留策略。
  if (!value || typeof value !== 'object') return false
  const item = value as ProcessIdentity
  return (
    Number.isInteger(item.pid) &&
    item.pid > 0 &&
    (item.started === null || typeof item.started === 'string') &&
    (item.executable === null || typeof item.executable === 'string')
  )
}

function isAlive(identity: ProcessIdentity, processes: UpdateProcess[]): boolean {
  // 用 PID、启动时间和可读取的路径判断原进程是否仍存在，信息不全时保留材料。
  const found = processes.find(item => item.pid === identity.pid)
  if (!found) return false
  if (!identity.started || !found.started) return true
  if (found.started !== identity.started) return false
  return (
    !identity.executable ||
    !found.executable ||
    path.normalize(found.executable).toLowerCase() ===
      path.normalize(identity.executable).toLowerCase()
  )
}

function installerUses(directory: string, processes: UpdateProcess[]): boolean {
  // 安装加载器及实际安装进程的命令均引用原始目录，PID 未落盘或加载器退出时仍能识别。
  const marker = path.resolve(directory).replace(/\//g, '\\').toLowerCase() + '\\'
  if (
    processes.some(
      item =>
        !item.command &&
        (item.name.toLowerCase().endsWith('.tmp') ||
          item.name.toLowerCase() === 'auto-mas-setup.exe')
    )
  ) {
    logger.warn('安装进程命令不可读取，暂时保留更新材料', directory)
    return true
  }
  return processes.some(item =>
    [item.executable, item.command].some(value =>
      value?.replace(/\//g, '\\').toLowerCase().includes(marker)
    )
  )
}

async function removeDirectory(directory: string): Promise<void> {
  // 仅删除暂存根目录内的真实子目录；文件已不存在也算完成，占用等错误留待下次回收。
  try {
    const root = await fs.realpath(path.dirname(directory))
    const resolved = await fs.realpath(directory)
    const relative = path.relative(root, resolved)
    if (
      !relative ||
      relative.startsWith('..') ||
      path.isAbsolute(relative) ||
      path.basename(root) !== '.frontend-updates'
    )
      throw new Error('更新材料目录不在暂存根目录内')
    await fs.rm(directory, { recursive: true, force: true })
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT')
      logger.warn('更新材料暂未清理，将在下次启动重试', directory, error)
  }
}

export class UpdateMaterial {
  private constructor(
    readonly directory: string,
    private state: MaterialState
  ) {
    // 将本次更新材料与唯一操作目录及持有记录绑定。
  }

  static async create(
    dataRoot: string,
    kind: MaterialState['kind'],
    version: string
  ): Promise<UpdateMaterial> {
    // 创建独立操作目录并记录当前前端身份，写入失败时立即回收尚未交付的目录。
    const owner = (await listProcesses()).find(item => item.pid === process.pid)
    if (!owner?.started || !owner.executable) throw new Error('无法确认当前前端进程身份')
    const root = path.join(dataRoot, '.frontend-updates')
    await fs.mkdir(root, { recursive: true })
    const directory = await fs.mkdtemp(path.join(root, `${kind}-`))
    const material = new UpdateMaterial(directory, {
      kind,
      version,
      phase: 'preparing',
      owner: { pid: owner.pid, started: owner.started, executable: owner.executable },
    })
    try {
      await material.setPhase('preparing')
      return material
    } catch (error) {
      await material.dispose()
      throw error
    }
  }

  async setPhase(phase: MaterialState['phase']): Promise<void> {
    // 原子保存准备、可用或安装交接阶段，写入成功后再改变内存归属。
    const state = { ...this.state, phase }
    await fs.writeFile(path.join(this.directory, 'state.json.part'), JSON.stringify(state))
    await fs.rename(
      path.join(this.directory, 'state.json.part'),
      path.join(this.directory, 'state.json')
    )
    this.state = state
  }

  async recordInstaller(pid: number): Promise<void> {
    // 安装器已启动后补充身份；写入失败也保留交接状态，不能误当启动失败恢复后端。
    try {
      const found = (await listProcesses()).find(item => item.pid === pid)
      this.state.installer = {
        pid,
        started: found?.started ?? null,
        executable: found?.executable ?? null,
      }
      await this.setPhase('handoff')
    } catch (error) {
      logger.warn('安装器已启动，暂存交接信息将在下次启动核对', error)
    }
  }

  async dispose(): Promise<void> {
    // 未交给安装器的材料由原持有者释放；交接中的材料仅由启动恢复确认无人使用后回收。
    if (this.state.phase !== 'handoff') await removeDirectory(this.directory)
  }

  async installerExited(): Promise<void> {
    // 原前端仍运行时响应加载器退出；实际安装进程仍使用材料或无法查询时继续保留。
    try {
      if (!installerUses(this.directory, await listProcesses()))
        await removeDirectory(this.directory)
    } catch (error) {
      logger.warn('安装进程退出后的材料暂未回收，将在下次启动重试', error)
    }
  }
}

export async function recoverUpdateMaterials(dataRoot: string): Promise<void> {
  // 启动时回收无人持有的操作目录；进程查询、记录损坏或安装器归属不明时保留并记录原因。
  const root = path.join(dataRoot, '.frontend-updates')
  try {
    const directories = await fs.readdir(root, { withFileTypes: true })
    if (!directories.length) return
    const processes = await listProcesses()
    for (const entry of directories) {
      if (!entry.isDirectory() || !/^(package|runtime)-[\w-]+$/.test(entry.name)) continue
      const directory = path.join(root, entry.name)
      try {
        const state: unknown = JSON.parse(
          await fs.readFile(path.join(directory, 'state.json'), 'utf8')
        )
        if (!state || typeof state !== 'object') throw new Error('更新材料记录无效')
        const record = state as MaterialState
        if (
          !['package', 'runtime'].includes(record.kind) ||
          typeof record.version !== 'string' ||
          !['preparing', 'ready', 'handoff'].includes(record.phase) ||
          !validIdentity(record.owner) ||
          (record.installer !== undefined && !validIdentity(record.installer))
        )
          throw new Error('更新材料记录无效')
        if (
          isAlive(record.owner, processes) ||
          (record.installer && isAlive(record.installer, processes))
        )
          continue
        if (record.phase === 'handoff' && installerUses(directory, processes)) continue
        await removeDirectory(directory)
      } catch (error) {
        logger.warn('更新材料记录暂不可恢复，保留目录', directory, error)
      }
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT')
      logger.warn('暂存材料回收未完成，保留至下次启动', error)
  }
}
