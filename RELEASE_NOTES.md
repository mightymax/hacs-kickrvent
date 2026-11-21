## KickrVent 0.1.1

- Setup now actively searches for WFTNP trainers using Home Assistant’s shared mDNS instance.
- Select a discovered trainer without typing its IP address, port or serial number.
- Scan again or fall back to manual configuration when discovery cannot reach a device.
- HA-discovered trainers now use a simple confirmation step.
- Discovery is bounded and cancels its browser on completion or cancellation.

Validated with HA 2026.2.3 and 2026.10.4 test environments. The scan also found a physical KICKR v6 and resolved its address, port and serial number. Cross-VLAN discovery still requires mDNS forwarding or manual setup.

Update in HACS/Marketplace, restart Home Assistant, then start a new KickrVent setup flow.
