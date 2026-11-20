## KickrVent 0.1.0

First experimental release of the read-only Home Assistant integration.

- Local WFTNP/DIRCON discovery and setup, with serial-based identity.
- Speed, power, cadence, connectivity and activity entities.
- Default five-second publication limit, unchanged-state suppression and independent field freshness.
- Read-only heartbeat, request timeouts, reconnect backoff and cleanup on unload.
- English and Dutch setup and entity translations.
- Regression tests for protocol, HA lifecycle, idle publication, stale data and recovery.

### Install

Add `https://github.com/mightymax/hacs-kickrvent` to HACS as an **Integration**, download, restart Home Assistant, then add **KickrVent**. The README contains My Home Assistant installation buttons.

The attached ZIP is for manual installation: extract it into the HA configuration directory so the component lives at `custom_components/kickrvent/`.

### Validation limits

Valid stationary readings were received from a physical KICKR v6. Pedalling, long-running Recorder measurements and simultaneous use with ROUVY have not yet been hardware-verified. This release never requests trainer control or changes resistance.
