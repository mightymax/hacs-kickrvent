## KickrVent 0.1.2

- Ship the KickrVent icon and high-resolution variant inside `custom_components/kickrvent/brand/`, so Home Assistant 2026.3+ can display them in integration cards and update lists.
- Include and validate PNG brand assets in the manual installation ZIP.
- Keep the repository-level branding for the README and marketplace metadata.

Update through HACS/Marketplace and restart Home Assistant. Refresh the browser if it still shows the cached placeholder. Older HACS versions that use the remote brands CDN rather than HA’s local brand endpoint may still show a placeholder in HACS itself.

No telemetry or connection behaviour changed.
