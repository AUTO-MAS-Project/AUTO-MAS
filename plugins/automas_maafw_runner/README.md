# automas-maafw-runner

Isolated MaaFW runner service for AUTO-MAS.

It provides `maafw.runner.v1`. The service builds run plans in the host process
and runs MaaFW through a worker subprocess so importing the service does not load
`maa` into the AUTO-MAS main process.

The wheel includes the MaaFW runtime worker code. `maa` is imported only by the
worker subprocess entrypoint, not by `MaaFWRunnerService`.
