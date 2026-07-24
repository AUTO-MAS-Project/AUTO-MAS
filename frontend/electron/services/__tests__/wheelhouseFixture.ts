import * as crypto from 'crypto'
import * as fs from 'fs'
import * as path from 'path'

interface PluginFixtureDefinition {
  distribution: string
  version: string
  entryPoint?: { group: string; name: string; value: string }
}

export const LOCKED_PLUGIN_FIXTURES: PluginFixtureDefinition[] = [
  {
    distribution: 'auto-mas-core',
    version: '6.0.0a1',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'auto_mas_core',
      value: 'auto_mas_core.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-plugin-browser',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'browser',
      value: 'automas_plugin_browser.plugin:Plugin',
    },
  },
  {
    distribution: 'automas_plugin_ok_script_adapter',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'ok_script_adapter',
      value: 'ok_script_adapter.plugin:Plugin',
    },
  },
  {
    distribution: 'automas_plugin_okww_adapter',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'okww_adapter',
      value: 'okww_adapter.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-maafw-interface',
    version: '0.1.1',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_maafw_interface',
      value: 'automas_maafw_interface.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-maafw-agent-env',
    version: '0.1.1',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_maafw_agent_env',
      value: 'automas_maafw_agent_env.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-maafw-controller-adb',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_maafw_controller_adb',
      value: 'automas_maafw_controller_adb.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-maafw-controller-win32',
    version: '0.1.1',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_maafw_controller_win32',
      value: 'automas_maafw_controller_win32.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-maafw-project-update',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_maafw_project_update',
      value: 'automas_maafw_project_update.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-maafw-project-store',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_maafw_project_store',
      value: 'automas_maafw_project_store.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-maafw-runtime-pool',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_maafw_runtime_pool',
      value: 'automas_maafw_runtime_pool.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-maafw-runner',
    version: '0.2.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_maafw_runner',
      value: 'automas_maafw_runner.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-script-maafw',
    version: '0.1.5',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_script_maafw',
      value: 'automas_script_maafw.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-script-maafw-managed',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_script_maafw_managed',
      value: 'automas_script_maafw_managed.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-script-maafw-pack-m9a',
    version: '0.1.2',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_script_maafw_pack_m9a',
      value: 'automas_script_maafw_pack_m9a.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-script-hsr',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_script_hsr',
      value: 'automas_script_hsr.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-hsr-adapter-sra',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_hsr_adapter_sra',
      value: 'automas_hsr_adapter_sra.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-hsr-adapter-m7a',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'automas_hsr_adapter_m7a',
      value: 'automas_hsr_adapter_m7a.plugin:Plugin',
    },
  },
  {
    distribution: 'automas-plugin-mxu-import',
    version: '0.1.0',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'mxu_import',
      value: 'automas_plugin_mxu_import.plugin:Plugin',
    },
  },
  {
    distribution: 'automas_plugin_maaend_adapter',
    version: '0.0.2',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'maaend_adapter',
      value: 'maaend_adapter.plugin:Plugin',
    },
  },
  {
    distribution: 'automas_script_maa',
    version: '0.0.5',
    entryPoint: {
      group: 'auto_mas.plugins',
      name: 'script_MAA',
      value: 'script_maa.plugin:Plugin',
    },
  },
  { distribution: 'automas-hsr', version: '0.1.0' },
  { distribution: 'automas-m9a', version: '0.1.0' },
]

function sha256(content: Buffer | string): string {
  return crypto.createHash('sha256').update(content).digest('hex')
}

export function writeCompleteWheelhouse(
  wheelsDir: string,
  options: {
    uppercaseFirstWheelExtension?: boolean
    hostRuntime?: Array<{ distribution: string; version: string }>
    pluginRuntime?: Array<{ distribution: string; version: string }>
  } = {}
): {
  filenames: string[]
  hostFilenames: string[]
  pluginRuntimeFilenames: string[]
  manifestSha256: string
  runtimeLockSha256: string
  coreVersion: string
} {
  fs.mkdirSync(wheelsDir, { recursive: true })
  const pluginEntries = LOCKED_PLUGIN_FIXTURES.map((definition, index) => {
    const extension = options.uppercaseFirstWheelExtension && index === 0 ? '.WHL' : '.whl'
    const filename = `${definition.distribution.replace(/[-.]/g, '_')}-${definition.version}-py3-none-any${extension}`
    const content = Buffer.from(`fixture:${definition.distribution}:${definition.version}`)
    fs.writeFileSync(path.join(wheelsDir, filename), content)
    return {
      distribution: definition.distribution,
      version: definition.version,
      scope: 'plugin',
      filename,
      size_bytes: content.length,
      sha256: sha256(content),
      entry_points: definition.entryPoint ? [definition.entryPoint] : [],
    }
  })
  const expectedEntryPoints = LOCKED_PLUGIN_FIXTURES.flatMap(definition =>
    definition.entryPoint ? [definition.entryPoint] : []
  )
  const createRuntimeEntries = (
    definitions: Array<{ distribution: string; version: string }>,
    scope: 'host_runtime' | 'plugin_runtime'
  ) =>
    definitions.map(definition => {
      const filename = `${definition.distribution.replace(/[-.]/g, '_')}-${definition.version}-py3-none-any.whl`
      const content = Buffer.from(
        `fixture:${scope}:${definition.distribution}:${definition.version}`
      )
      fs.writeFileSync(path.join(wheelsDir, filename), content)
      return {
        distribution: definition.distribution,
        version: definition.version,
        scope,
        filename,
        size_bytes: content.length,
        sha256: sha256(content),
      }
    })
  const hostEntries = createRuntimeEntries(options.hostRuntime ?? [], 'host_runtime')
  const pluginRuntimeEntries = createRuntimeEntries(options.pluginRuntime ?? [], 'plugin_runtime')
  const runtimeLock = {
    schema_version: 1,
    target: {
      implementation: 'cpython',
      python_version: '3.12',
      platform: 'win32',
      architecture: 'x86_64',
      uv_platform: 'x86_64-pc-windows-msvc',
    },
    install_contract: {
      resolver_allowed: false,
      index_allowed: false,
      required_arguments: ['--no-index', '--no-deps'],
      forbidden_arguments: [
        '--upgrade',
        '--index',
        '--index-url',
        '--default-index',
        '--extra-index-url',
      ],
      host_target: '.venv',
      plugin_target: 'plugins/pypi/site-packages',
      protected_host_distributions: hostEntries.map(entry => entry.distribution),
    },
    host_runtime: hostEntries,
    plugin_runtime: pluginRuntimeEntries,
    plugins: pluginEntries,
    expected_plugin_entry_points: expectedEntryPoints,
  }
  const runtimeLockContent = `${JSON.stringify(runtimeLock, null, 2)}\n`
  fs.writeFileSync(path.join(wheelsDir, 'runtime-lock.json'), runtimeLockContent)
  fs.writeFileSync(path.join(wheelsDir, 'pylock.host.toml'), 'lock-version = "1.0"\n')
  fs.writeFileSync(path.join(wheelsDir, 'pylock.combined.toml'), 'lock-version = "1.0"\n')

  const manifest = {
    schema_version: 3,
    artifact_scope: 'complete-windows-x64-runtime-wheelhouse',
    expected_plugin_distribution_count: 23,
    expected_plugin_entry_point_count: 21,
    runtime_lock: {
      filename: 'runtime-lock.json',
      size_bytes: Buffer.byteLength(runtimeLockContent),
      sha256: sha256(runtimeLockContent),
    },
    wheels: [
      ...pluginEntries.map(entry => ({
        kind: 'plugin',
        scopes: ['plugin'],
        distribution: entry.distribution,
        version: entry.version,
        entry_points: entry.entry_points,
        filename: entry.filename,
        size_bytes: entry.size_bytes,
        sha256: entry.sha256,
      })),
      ...[...hostEntries, ...pluginRuntimeEntries].map(entry => ({
        kind: 'runtime_dependency',
        scopes: [entry.scope],
        distribution: entry.distribution,
        version: entry.version,
        entry_points: [],
        filename: entry.filename,
        size_bytes: entry.size_bytes,
        sha256: entry.sha256,
      })),
    ],
  }
  const manifestContent = JSON.stringify(manifest, null, 2)
  fs.writeFileSync(path.join(wheelsDir, 'manifest.json'), manifestContent)
  return {
    filenames: [...pluginEntries, ...hostEntries, ...pluginRuntimeEntries].map(
      entry => entry.filename
    ),
    hostFilenames: hostEntries.map(entry => entry.filename),
    pluginRuntimeFilenames: pluginRuntimeEntries.map(entry => entry.filename),
    manifestSha256: sha256(manifestContent),
    runtimeLockSha256: sha256(runtimeLockContent),
    coreVersion:
      LOCKED_PLUGIN_FIXTURES.find(definition => definition.distribution === 'auto-mas-core')
        ?.version ?? '',
  }
}
