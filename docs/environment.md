# LLM Studio Environment Inspection

This file is intentionally a placeholder in the source tree. On the target VPS,
run:

```bash
make inspect
```

or run the full idempotent setup:

```bash
sudo make setup
```

`scripts/setup.sh` runs the read-only inspection first and replaces this file
before it creates directories, builds images, or starts containers. Review the
generated report to confirm the detected Hermes paths, mounts, networks, ports,
OpenVPN interface, available disk, and host resources.

Do not treat a report generated on a development workstation as a VPS report.

