// yarn build:main 后使用本机原生探针、导出收集器和本地 HTTP 接收器验收。
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const net = require('node:net')
const http = require('node:http')
const { once } = require('node:events')
const { setTimeout: delay } = require('node:timers/promises')
const AdmZip = require('adm-zip')
const { AnalyticsService } = require('../dist-electron/services/analytics')
const { addDirectory } = require('../dist-electron/services/issueReportCore')
const hardware = require('../dist-electron/services/startupHardware/monitor')
const { runtimeStartupSample } = require('../dist-electron/services/startupHardware/pipe')
const { StartupHardwareLog } = require('../dist-electron/services/startupHardware/localLog')

async function check() {
  const root = await fs.mkdtemp(path.join(process.argv[2] ?? os.tmpdir(), 'startup-hardware-'))
  const debug = path.join(root, 'debug'),
    log = new StartupHardwareLog(debug)
  const bodies = []
  const receiver = http.createServer(async (req, res) => {
    let body = ''
    for await (const chunk of req) body += chunk
    bodies.push(JSON.parse(body))
    res.writeHead(204)
    res.end()
  })
  receiver.listen(0, '127.0.0.1')
  await once(receiver, 'listening')
  const analytics = new AnalyticsService({
    isAllowed: () => true,
    systemProps: () => ({}),
    onDisabled: hardware.revokeHardwareUpload,
    send: async (payload, signal) => {
      await fetch('http://127.0.0.1:' + receiver.address().port, {
        method: 'POST',
        body: JSON.stringify(payload),
        signal,
      })
    },
  })
  const config = {
    log,
    executable:
      process.platform === 'win32'
        ? path.join(__dirname, '../dist-electron/startup-probe.exe')
        : undefined,
    directories: Array(9).fill(root),
    scope: 'managed',
    acceleration: 'unknown',
    graphics: async () => ({ gpuDevice: [] }),
  }
  const finishEvent = {
    name: 'initialization_finished_v2',
    props: {
      flow_kind: 'startup',
      outcome: 'failure',
      runtime_mode: 'managed',
      failed_stage: 'backend',
      duration_bucket: '1-5s',
    },
  }
  const waitForSamples = async () => {
    const end = performance.now() + 15000
    while (hardware.localStartupAttempt().snapshot().coverage !== 'sampled') {
      if (performance.now() > end) throw Error('no measured interval')
      await delay(200)
    }
  }
  try {
    hardware.setupStartupHardware(
      () => config,
      () => analytics.getContext()
    )
    const local = hardware.claimStartupAttempt()
    assert.equal(hardware.claimStartupAttempt(), local)
    const initialMonitor = hardware.localStartupAttempt()
    assert.equal(hardware.claimStartupAttempt(), local)
    assert.equal(hardware.localStartupAttempt(), initialMonitor)
    await waitForSamples()
    assert.equal(hardware.startupAttempt(), undefined)
    const silent = hardware.inStartupOperation(() => runtimeStartupSample())
    assert.equal(silent.token, 'local')
    analytics.setEnabled(true)
    assert.equal(hardware.startupAttempt(), undefined)
    assert.deepEqual(hardware.finishStartupAttempt(local, 'failure', 'backend'), {})
    await log.drain()
    const zip = new AdmZip()
    assert.ok(
      addDirectory(
        { zip, entries: [], archiveBytes: 0, maxEntryBytes: Infinity, maxArchiveBytes: Infinity },
        debug,
        ''
      )
    )
    const archive = path.join(root, 'logs.zip')
    zip.writeZip(archive)
    const exported = new AdmZip(archive).readAsText('startup-hardware.log')
    const rows = exported
      .trim()
      .split('\n')
      .map(line => JSON.parse(line))
    const samples = rows.find(row => row.event === '失败前15秒').samples
    assert.ok(
      samples.some(
        s => typeof s.readings.cpu === 'number' && typeof s.readings.install_free === 'number'
      )
    )
    assert.equal(bodies.length, 0)

    const active = hardware.claimStartupAttempt()
    const generation = analytics.getContext()
    await waitForSamples()
    if (process.platform === 'win32') {
      const pipe = hardware.inStartupOperation(() => runtimeStartupSample())
      const evt = {
        operationId: 'fixture',
        command: 'bootstrap',
        stage: 'bootstrap',
        details: {},
        success: false,
      }
      pipe.event({ ...evt, type: 'hello', capabilities: ['startup.resources.v1'] })
      pipe.event({ ...evt, type: 'result' })
      const socket = net.connect('\\\\.\\pipe\\auto-mas-startup-' + pipe.token.slice(0, 32))
      socket.setTimeout(1500, () => socket.destroy(Error('pipe timed out')))
      let reply = ''
      socket.on('data', chunk => (reply += chunk))
      socket.write(pipe.token.slice(32) + '\n')
      await once(socket, 'end')
      assert.equal(JSON.parse(reply).coverage, 'sampled')
      analytics.setEnabled(false)
      analytics.setEnabled(true)
      assert.equal(hardware.startupAttempt(), undefined)
      assert.equal(hardware.inStartupOperation(() => runtimeStartupSample()).token, 'local')
      assert.deepEqual(hardware.finishStartupAttempt(active, 'cancelled', 'none'), {})
      analytics.recordRendererEvent(generation, finishEvent)
    } else hardware.finishStartupAttempt(active, 'cancelled', 'none')
    const retry = hardware.claimStartupAttempt()
    await waitForSamples()
    const done = hardware.finishStartupAttempt(retry, 'failure', 'backend')
    analytics.recordRendererEvent(analytics.getContext(), finishEvent, () => done)
    for (let i = 0; i < 40 && !bodies.length; i++) await delay(50)
    assert.equal(bodies.length, 1)
    assert.equal(bodies[0].props.coverage, 'sampled')
    assert.equal(typeof bodies[0].props.cpu_avg, 'string')
    assert.ok(!JSON.stringify(bodies).includes(root))
    console.log(
      JSON.stringify({
        archive,
        localSamples: samples.length,
        localOnlyUploads: 0,
        retryUploads: bodies.length,
        graphics: done.graphics_layout ?? 'unknown',
        disk: done.install_media ?? 'unknown',
      })
    )
  } finally {
    hardware.clearStartupHardware()
    analytics.dispose()
    await log.drain()
    receiver.closeAllConnections()
    receiver.close()
  }
}
check().catch(error => {
  console.error(error)
  process.exitCode = 1
})
