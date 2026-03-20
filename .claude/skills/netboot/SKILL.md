---
name: netboot
description: TFTP-boot a firmware image from the Host PC into the AXN-2020 via U-Boot. Starts a TFTP server on the Host, configures U-Boot networking, downloads the image, and boots it. Device must already be at the Marvell>> U-Boot prompt.
---

# netboot

Transfers a firmware image from the Host PC to the AXN-2020 over TFTP and boots it from RAM via U-Boot. Does not flash — boots the image directly into memory.

## Prerequisites

- Device is stopped at `Marvell>>` U-Boot prompt (autoboot disabled or interrupted)
- Host has `tftpy` Python package installed (`"$PYTHON" -c "import tftpy"`)
- Firmware image is in `./tmp/` on the Host (fetch it with Step 1 below, or skip if already present)

## Environment Variables

```
HELPER     = .claude/skills/uart/serial_helper.py
TFTP_SRV   = .claude/skills/netboot/tftp_server.py
PORT       = COM200
BAUD       = 115200
PROMPT_UBT = Marvell>>
PROMPT_LNX = alphadiags:~#
HOST_IP    = 30.0.0.1
DUT_IP     = 30.0.0.100
LOAD_ADDR  = 0x210000000
FIT_CONF   = axn2020
IMAGE      = axn2020.0.0.2
IMAGE_DIR  = ./tmp
```

## Step-by-Step Workflow

### 1. Fetch Image from Build Server

Copy the firmware image from the remote build server to `./tmp/` on the Host:

```bash
mkdir -p ./tmp
scp chester@172.19.176.168:~/axn2020-diag/image/0.0.2/axn2020.0.0.2 \
    chester@172.19.176.168:~/axn2020-diag/image/0.0.2/axn2020.0.0.2.md5 \
    ./tmp/
```

Expected files (~47M total):

| File | Size | Description |
|------|------|-------------|
| `axn2020.0.0.2` | 47M | Firmware image |
| `axn2020.0.0.2.md5` | 48B | MD5 checksum |

> Skip this step if the image is already in `./tmp/`.

### 2. Start TFTP Server on Host (background)

```bash
"$PYTHON" .claude/skills/netboot/tftp_server.py \
  --dir ./tmp --ip 30.0.0.1 --port 69 --timeout 6
```

Run with `run_in_background: true`. The server exits automatically after 60s.

### 3. Configure U-Boot Networking

```bash
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 --baud 115200 --prompt "Marvell>>" --timeout 10 \
  --command "setenv bootargs 'console=ttyS0,115200'; setenv ipaddr 30.0.0.100; setenv serverip 30.0.0.1" \
  --logfile ./tmp/netboot.log
```

### 4. TFTP Download + Boot

```bash
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 --baud 115200 --prompt "alphadiags:~#" --timeout 60 \
  --command "tftpboot 0x210000000 axn2020.0.0.2; bootm \$fileaddr#axn2020" \
  --raw --logfile ./tmp/netboot.log
```

> **Why `0x210000000`?** The kernel's decompress target is `0x202000000`. Loading the FIT image at the same address causes a gzip inflate error (data corruption mid-decompress). `0x210000000` is safely above the decompressed kernel region.

> **Why `bootm $fileaddr#axn2020`?** `$fileaddr` is set by U-Boot after a successful `tftpboot`. `#axn2020` selects the named FIT configuration, ensuring the correct kernel/ramdisk/fdt combination is used.

---

## Complete Example

```bash
# 1. Fetch image from build server
mkdir -p ./tmp
scp chester@172.19.176.168:~/axn2020-diag/image/0.0.2/axn2020.0.0.2 \
    chester@172.19.176.168:~/axn2020-diag/image/0.0.2/axn2020.0.0.2.md5 \
    ./tmp/

# 2. Start TFTP server in background (60s window)
"$PYTHON" .claude/skills/netboot/tftp_server.py \
  --dir ./tmp --ip 30.0.0.1 --timeout 60
# (run_in_background: true)

# 3. Set U-Boot network config
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 --baud 115200 --prompt "Marvell>>" --timeout 10 \
  --command "setenv bootargs 'console=ttyS0,115200'; setenv ipaddr 30.0.0.100; setenv serverip 30.0.0.1" \
  --logfile ./tmp/netboot.log

# 4. Download and boot (waits up to 60s for Linux prompt)
PYTHONIOENCODING=utf-8 "$PYTHON" .claude/skills/uart/serial_helper.py \
  --device COM200 --baud 115200 --prompt "alphadiags:~#" --timeout 60 \
  --command "tftpboot 0x210000000 axn2020.0.0.2; bootm \$fileaddr#axn2020" \
  --raw --logfile ./tmp/netboot.log
```

Expected boot sequence:
1. PHY autoneg → TFTP transfer (~30s at ~1.5 MiB/s for 47M image)
2. FIT image parsing and CRC verification
3. Kernel decompress + ramdisk load
4. Linux boot messages
5. Python package install (`/alpha/whl/...`)
6. `alphadiags:~#` prompt ready

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `Waiting for PHY auto negotiation... FAILED` | No cable or wrong port | Check Ethernet cable between Host and DUT |
| `TFTP error: 'File not found'` | Wrong filename or TFTP server not started | Verify file is in `./tmp/` and server is running |
| `gzip: uncompress error -1` | FIT image loaded at overlapping address | Use `0x210000000`, not `0x202000000` |
| `Unknown configuration` | Wrong FIT config name | Check image configs with `iminfo 0x210000000` |
| TFTP transfer starts but stalls | TFTP server timeout expired | Restart server with longer `--timeout` |
| Linux prompt never appears | Boot failure mid-way | Add `--raw` flag to see full console output |
