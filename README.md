<div align="center">
  <img src="brand/icon.png" alt="KickrVent" width="112" height="112">
  <h1>KickrVent</h1>
  <p><strong>Your ride. Your airflow. All in Home Assistant.</strong></p>
  <p>Local, read-only telemetry from your Wi-Fi KICKR — ready for your own cooling automations.</p>

  <a href="https://github.com/mightymax/hacs-kickrvent/releases"><img alt="Latest release" src="https://img.shields.io/github/v/release/mightymax/hacs-kickrvent?style=flat-square&color=41bdf5"></a>
  <a href="https://www.hacs.xyz/"><img alt="HACS custom integration" src="https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat-square"></a>
  <a href="https://www.home-assistant.io/"><img alt="Home Assistant 2026.2+" src="https://img.shields.io/badge/Home_Assistant-2026.2%2B-18BCF2?style=flat-square&logo=homeassistant&logoColor=white"></a>
  <a href="https://github.com/mightymax/hacs-kickrvent/actions/workflows/validate.yml"><img alt="Validation" src="https://github.com/mightymax/hacs-kickrvent/actions/workflows/validate.yml/badge.svg"></a>

  <br><br>
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=mightymax&repository=hacs-kickrvent&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open KickrVent in HACS"></a>
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=kickrvent"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Set up KickrVent in Home Assistant"></a>

  <p><a href="#installation">Install</a> · <a href="#entities">Entities</a> · <a href="#built-to-stay-quiet">Database & connection behaviour</a> · <a href="#compatibility">Compatibility</a> · <a href="docs/home-assistant.md">Nederlandse handleiding</a></p>
</div>

---

## What it does

KickrVent connects to your trainer over your local network using **WFTNP / DIRCON** and exposes speed, power and cadence as Home Assistant sensors. Use those sensors with your existing smart plug or fan integration to build your preferred cooling automation.

```mermaid
flowchart LR
    K["KICKR · Wi-Fi"] --> I["KickrVent"]
    I --> S["HA sensors"]
    S --> A["Your automation"]
    A --> F["Smart plug or variable-speed fan"]
```

- **Local connection** — no vendor cloud or account required by KickrVent.
- **Read-only** — no ERG commands, resistance changes or requests for trainer control.
- **Recorder-conscious** — rate-limited, rounded measurements; unchanged data is not republished.
- **Automatic recovery** — connection checks, request timeouts and reconnect backoff.
- **Stable identity** — serial-based device and entity IDs survive a change of IP address.
- **English & Dutch** — translated setup, options and entity names.

> **Early release:** the Python client has received valid stationary readings from a physical KICKR v6. Pedalling, long-running Recorder behaviour and simultaneous use with ROUVY have not yet been verified on hardware. Automated tests cover the protocol, HA lifecycle and recovery paths; this is not an official Wahoo integration.

## Installation

### 1. Download with HACS

[![Open KickrVent in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mightymax&repository=hacs-kickrvent&category=integration)

This is a **custom repository**, not a listing in the default HACS catalogue. The button opens the repository flow in your own Home Assistant. If prompted, set your instance URL in My Home Assistant first.

If the button does not work:

1. Open **HACS** (or **Marketplace**, depending on your HA version).
2. Open **Custom repositories** from the menu.
3. Add `https://github.com/mightymax/hacs-kickrvent` with category **Integration**.
4. Find **KickrVent**, download the latest release, and restart Home Assistant.

### 2. Add the integration

After downloading and restarting:

[![Set up KickrVent](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=kickrvent)

Alternatively, go to **Settings → Devices & services → Add integration → KickrVent**. Setup scans your network for three seconds and lets you select a discovered trainer, without typing an address or serial number. Choose **Scan again** to refresh or **Enter address manually** if discovery cannot reach your trainer. A trainer discovered by HA itself only needs confirmation.

| Field | What to enter |
| --- | --- |
| Host | Your trainer's IP address or hostname |
| TCP port | **36866** by default; discovery uses the advertised port |
| Name | A friendly name, for example `Indoor bike` |
| Serial number | Leave blank unless the trainer does not report one. Discovery fills it from mDNS when available. For manual setup, use the label's serial number if asked. |

Use **Reconfigure** in the integration menu to change the address later. The serial number must still match the original device.

<details>
<summary><strong>Manual installation without HACS</strong></summary>

Download `kickrvent-0.1.2.zip` from the [release page](https://github.com/mightymax/hacs-kickrvent/releases/latest) and extract it into your HA configuration directory. The resulting path must be:

```text
config/
└── custom_components/
    └── kickrvent/
        ├── __init__.py
        ├── manifest.json
        └── ...
```

Do not add an extra `custom_components` directory inside the existing one. Restart Home Assistant and follow step 2 above.

</details>

## Entities

| Entity | Unit | Behaviour |
| --- | --- | --- |
| **Speed** | km/h | Trainer-reported speed, rounded to 0.1 km/h |
| **Power** | W | Instantaneous power, rounded to whole watts |
| **Cadence** | rpm | Rounded to 0.1 rpm |
| **Connection** | on/off | Diagnostic sensor for the initialized TCP session |
| **Activity** | on/off | Positive speed, power or cadence received within the activity timeout |

Home Assistant chooses the actual entity IDs based on your language, device name and existing entities. Use the entity picker in your automations.

If the trainer only offers **Cycling Power**, KickrVent exposes power; speed and cadence remain unavailable. Missing or stale data becomes **unavailable**, never an invented zero. Speed is the trainer's speed and may differ from the virtual speed shown in ROUVY or Zwift.

## Built to stay quiet

A trainer can send many notifications per second. Recording every notification — or attaching a changing `last_seen` timestamp — can grow the HA database unnecessarily. KickrVent keeps receiving data but publishes only meaningful, bounded updates.

| Setting | Default | Adjustable range |
| --- | --- | --- |
| **Publish interval** | 5 seconds | 2–60 seconds |
| **Measurement freshness timeout** | 30 seconds | 15–300 seconds |
| **Activity timeout** | 15 seconds | 5–120 seconds |

Change these in the integration's **Options**. Saving reloads the integration and reconnects it.

- A fixed-size buffer holds only the latest speed, power and cadence; no per-packet task or unbounded queue.
- Changed numeric readings are published at the configured interval. Connection and stale-data transitions invalidate old readings immediately.
- Equal snapshots are suppressed by the coordinator. There are no `force_update` entities or constantly changing timestamp attributes.
- Idle zero readings keep the connection alive without repeated state publications. The automated test for a simulated day of zeros produces one changed snapshot.
- Each measurement expires independently, so a fresh power packet cannot keep an old speed reading alive.
- Read-only service discovery checks connection health every 20 seconds. Failed connections retry with exponential backoff from 2 to 60 seconds, plus jitter.
- Disconnects clear the sample buffer. Unloading closes the socket and cancels the background tasks.

**This limits unnecessary writes; it does not disable Recorder.** Changing readings during a ride can still produce history and statistics. Your existing Recorder configuration is left untouched.

## Fan automation

KickrVent supplies telemetry; your fan stays under its own Home Assistant integration.

- With a **smart plug**, use Activity or Power to turn cooling on and add a cooldown before switching it off.
- With a **variable-speed fan**, map smoothed power to a percentage using your preferred automation.
- Handle `unavailable` explicitly rather than treating missing telemetry as a zero-watt measurement.

No fan is switched and no automation is created just by installing KickrVent.

## Compatibility

| Item | Status |
| --- | --- |
| Home Assistant | Minimum 2026.2; test environments: 2026.2.3 and 2026.10.4 |
| KICKR v6 over Wi-Fi | Physical trainer reached; valid stationary FTMS data received |
| Other WFTNP / DIRCON trainers | May work; not hardware-tested |
| Bluetooth / ANT+ | Not supported by this integration |
| Simultaneous ROUVY / Zwift connection | Not yet verified; depends on trainer/client behaviour |

The trainer must already be connected to Wi-Fi, and Home Assistant must be able to reach its TCP port. mDNS discovery may not cross VLANs; manual host configuration is available.

## Troubleshooting

**HACS cannot install a release**  
Check that the selected release is from this repository. Each release validates JSON metadata and builds a manual installation ZIP. The tag and `manifest.json` version must agree.

**Cannot connect**  
Check power, network access and port **36866** (or the advertised port). For a first test, stop other trainer clients and disable the other WFTNP integration. Then test simultaneous use separately.

**Connected, but readings are unavailable**  
Pedal briefly. Sensors become available only after a valid measurement is received and become unavailable again when it expires. Unsupported fields stay unavailable.

**Serial number requested during setup**  
Some trainers do not expose Device Information over DIRCON. Use automatic discovery to obtain the mDNS serial, or enter the serial printed on the trainer. Keep it stable across address changes.

**Need help?**  
[Open an issue](https://github.com/mightymax/hacs-kickrvent/issues/new/choose) with your HA version, trainer model, integration version and relevant logs. Redact network details or identifiers you do not want to share.

## Development

```sh
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python \
  --override test-overrides.txt -r requirements-test.txt
.venv/bin/pytest tests -q
python3 scripts/package_ha.py
```

The test-only `lru-dict` override provides a compatible wheel on the original macOS test machine. It does not modify Home Assistant packages on the deployed instance. The integration itself has no additional Python package requirements.

Validation runs in GitHub Actions on Python 3.13/HA 2026.2.3 and Python 3.14/HA 2026.10.4. A tag matching the manifest version creates a GitHub release with the manual installation ZIP.

## Acknowledgements

Built from our TypeScript proof of concept and the [unofficial WFTNP/DIRCON protocol specification by elfrances](https://github.com/elfrances/wahoo-fitness-tnp). The database-growth and reconnection reports in [kilianyp/hacs-wahoo-wftnp#2](https://github.com/kilianyp/hacs-wahoo-wftnp/issues/2) informed the publication and recovery design. This is an independent implementation, not a fork of that integration.
