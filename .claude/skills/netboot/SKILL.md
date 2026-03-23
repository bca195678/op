---
name: netboot
description: TFTP-boot a firmware image from the Host PC into the STARK via U-Boot. Starts a TFTP server on the Host, configures U-Boot networking, downloads the image, and boots it. Device must already be at the u-boot> U-Boot prompt.
---

# netboot

Transfers a firmware image from the Host PC to the STARK over TFTP and boots it from RAM via U-Boot. Does not flash — boots the image directly into memory.

## Prerequisites

- Device is stopped at `u-boot>` U-Boot prompt (autoboot disabled or interrupted)
- Host has `tftpy` Python package installed (`"$PYTHON" -c "import tftpy"`)
- Firmware image is in `./tmp/` on the Host (fetch it with Step 1 below, or skip if already present)

## Environment Variables

```
HELPER      = .claude/skills/uart/serial_helper.py
TFTP_SRV    = .claude/skills/netboot/tftp_server.py
PORT        = COM200
BAUD        = 115200
PROMPT_UBT  = u-boot>
PROMPT_LNX  = alphadiags:/#
HOST_IP     = 30.0.0.1
DUT_IP      = 30.0.0.100
LOAD_ADDR   = 0x70000000
BUILD_SERVER = chester@172.31.230.36
IMAGE_REMOTE = ~/project/opdiag/summit-stark/image
IMAGE_DIR    = ./tmp
```

> **IMAGE is not hardcoded.** The image name changes between builds. Always discover it dynamically in Step 1.

## Step-by-Step Workflow

### 1. Discover and Fetch Image from Build Server

List available images on the remote server, then fetch the latest:

```bash
# Discover image name (exclude .md5 and .gz files)
IMAGE=$(ssh chester@172.31.230.36 'ls ~/project/opdiag/summit-stark/image/ | grep -v -E "\.(md5|gz)$"')
echo "Image found: $IMAGE"

# Fetch image and checksum
mkdir -p ./tmp
scp chester@172.31.230.36:~/project/opdiag/summit-stark/image/"$IMAGE" \
    chester@172.31.230.36:~/project/opdiag/summit-stark/image/"$IMAGE".md5 \
    ./tmp/
```

> Skip this step if the image is already in `./tmp/`. To find the image name locally: `ls ./tmp/*.md5 | sed 's/\.md5$//' | xargs -I{} basename {}`

### 2. Start TFTP Server on Host (background)

```bash
"$PYTHON" .claude/skills/netboot/tftp_server.py \
  --dir ./tmp --ip 30.0.0.1 --port 69 --timeout 6
```

Run with `run_in_background: true`. The server exits automatically after 60s.

### 3. Configure U-Boot Networking

```bash
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 --baud 115200 --prompt "u-boot>" --timeout 10 \
  --command "setenv bootargs 'console=ttyS0,115200'; setenv ipaddr 30.0.0.100; setenv serverip 30.0.0.1" \
  --logfile ./tmp/netboot.log
```

> **Operational diag images (summit-\*)** require `opdiag_mode=normal` in bootargs:
> ```bash
> --command "setenv bootargs 'console=ttyS0,115200 opdiag_mode=normal'; setenv ipaddr 30.0.0.100; setenv serverip 30.0.0.1"
> ```
> Without this parameter, the image will print `"Running Power On Self Test...(Unknown mode)"` and reboot immediately. Valid values: `normal`, `extended`. Manufacturing images (stark-diag) do not need this parameter.

### 4. TFTP Download + Boot

Use the `$IMAGE` variable discovered in Step 1:

```bash
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 --baud 115200 --prompt "alphadiags:/#" --timeout 180 \
  --command "tftpboot 0x70000000 $IMAGE && bootm 0x70000000" \
  --raw --logfile ./tmp/netboot.log
```

> **Why `0x70000000`?** This is the platform's default `loadaddr`. DRAM spans `0x60000000–0xdfffffff` (2 GiB). The kernel loads at `0x61200000` and ramdisk at `0x68000000` — loading the FIT at `0x70000000` keeps it clear of both.

> **Why `bootm 0x70000000` (no `#config`)?** The FIT image's default configuration is `stark`, so U-Boot selects the correct kernel/ramdisk/fdt combination automatically.

---

## Complete Example

```bash
# 1. Discover and fetch image
IMAGE=$(ssh chester@172.31.230.36 'ls ~/project/opdiag/summit-stark/image/ | grep -v -E "\.(md5|gz)$"')
echo "Image: $IMAGE"
mkdir -p ./tmp
scp chester@172.31.230.36:~/project/opdiag/summit-stark/image/"$IMAGE" \
    chester@172.31.230.36:~/project/opdiag/summit-stark/image/"$IMAGE".md5 \
    ./tmp/

# 2. Start TFTP server in background (60s window)
"$PYTHON" .claude/skills/netboot/tftp_server.py \
  --dir ./tmp --ip 30.0.0.1 --timeout 60
# (run_in_background: true)

# 3. Set U-Boot network config
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 --baud 115200 --prompt "u-boot>" --timeout 10 \
  --command "setenv bootargs 'console=ttyS0,115200'; setenv ipaddr 30.0.0.100; setenv serverip 30.0.0.1" \
  --logfile ./tmp/netboot.log

# 4. Download and boot (waits up to 180s for Linux prompt)
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 --baud 115200 --prompt "alphadiags:/#" --timeout 180 \
  --command "tftpboot 0x70000000 $IMAGE && bootm 0x70000000" \
  --raw --logfile ./tmp/netboot.log
```

Expected boot sequence:
1. PHY autoneg → TFTP transfer (~25s at ~1.9 MiB/s for ~45M image)
2. FIT image parsing and CRC verification
3. Kernel decompress + ramdisk load
4. Linux boot messages
5. Python package install (`/alpha/whl/...`)
6. `alphadiags:/#` prompt ready

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `Waiting for PHY auto negotiation... FAILED` | No cable or wrong port | Check Ethernet cable between Host and DUT |
| `TFTP error: 'File not found'` | Wrong filename or TFTP server not started | Verify file is in `./tmp/` and server is running |
| `trying to overwrite reserved memory` | Load address outside DRAM range | Use `0x70000000` (platform default `loadaddr`) |
| `Could not find configuration node` | Wrong FIT config name | Omit `#config` to use default, or check with `iminfo 0x70000000` |
| TFTP transfer starts but stalls | TFTP server timeout expired | Restart server with longer `--timeout` |
| Linux prompt never appears | Boot failure mid-way | Add `--raw` flag to see full console output |
| `Running Power On Self Test...(Unknown mode)` then reboot | Missing `opdiag_mode` bootarg | Add `opdiag_mode=normal` to bootargs (required for summit-* opdiag images) |
