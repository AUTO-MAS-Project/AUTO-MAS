# automas-maafw-controller-adb

ADB controller provider for the AUTO-MAS MaaFW plugin group.

This package declares the ADB controller capability without importing `maa` at
plugin startup. Runtime device resolution remains owned by the MaaFW script
adapter until the host controller path is fully split.
