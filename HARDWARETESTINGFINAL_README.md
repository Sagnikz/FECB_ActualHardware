# GMRT FECB – Hardware Testing

## Overview

This project is the **hardware-testing build** of the GMRT FECB control system.

Unlike the software-only stub version, this package does **not** contain `gmrt_hw_stub.py`. The FECB device server listens for the external hardware client on TCP port **3005**, making this build suitable for testing the control software against a real or externally provided FECB hardware endpoint.

The project includes:

- PyTango FECB device server
- PyTango FECB proxy
- GMRT binary protocol implementation
- TCP communication layer
- HDB++/MySQL archiver
- Flask web control GUI
- Start/stop scripts for the complete Tango system

## Architecture

```text
Browser
   │
   │ HTTP :5000
   ▼
Flask Web GUI (app.py)
   │
   │ Tango
   ▼
FECB Proxy (fecb/proxy/1)
   │
   │ Tango forwarding
   ▼
FECB Device Server (fecb/c01/1)
   │
   │ TCP :3005
   ▼
External / Real FECB Hardware

FECB Device ───────────────► FECB Archiver ───► MySQL/HDB++ database
```

## Files

| File | Purpose |
|---|---|
| `FECB.py` | PyTango FECB device server. Handles FECB commands and the TCP hardware connection. |
| `FECB_Proxy.py` | PyTango proxy forwarding commands to the main FECB device. |
| `FECB_Archiver.py` | Archives selected FECB attributes into MySQL/HDB++. |
| `gmrt_protocol.py` | Binary packet definitions, command construction and response parsing. |
| `gmrt_link.py` | TCP socket communication and response handling. |
| `app.py` | Flask GUI for command execution and status monitoring. |
| `templates/index.html` | Web control panel. |
| `start.sh` | Starts Tango database, FECB server, proxy, archiver and GUI. |
| `stop.sh` | Stops the local services. |
| `tango_database.db` | Local Tango database file included with this build. |

## Requirements

The runtime environment should provide:

- Linux
- Python 3
- PyTango
- Flask
- MySQL Connector/Python
- Tango
- A running/accessible FECB hardware endpoint
- `pixi` if using the supplied startup script unchanged

The external hardware must communicate using the GMRT command/response packet format implemented in:

```text
gmrt_protocol.py
```

## Network Configuration

The FECB server is configured by default with:

```text
Port: 3005
Subsystem ID: fecb
System IP: 127.0.0.1
```

The supplied `start.sh` registers the Tango devices:

```text
fecb/c01/1
fecb/proxy/1
fecb/archiver/1
```

The Tango database is started on:

```text
localhost:10000
```

### Important

In this version there is **no local hardware stub**. The line:

```text
FECB Device Server → TCP :3005 → External Hardware
```

must be satisfied by the real FECB hardware or another compatible hardware-side test program.

If the physical hardware is on another machine, review the FECB device properties in the startup configuration and use the appropriate hardware IP instead of the localhost configuration.

## Running

Make the scripts executable:

```bash
chmod +x start.sh stop.sh
```

Start the system:

```bash
./start.sh
```

The script:

1. Starts Tango DB.
2. Registers the FECB, proxy and archiver devices.
3. Starts `FECB.py`, listening for the hardware client on port 3005.
4. Starts `FECB_Proxy.py`.
5. Starts `FECB_Archiver.py`.
6. Starts the Flask GUI.

Open:

```text
http://localhost:5000
```

Stop the services with:

```bash
./stop.sh
```

## FECB Commands

The device server supports commands such as:

```text
NullCmd
RBReset
DoMon
SetAttn
SetRFSys
SetURFSys
SetDomonTimeInterval
SetMaintenance
SetReset
SetShutdown
SetTime
SetNoiseFreq
SetRFNoise
SetWalsh
SetWalshGrp
SetWalshFreq
RFCMSwitch
SelFEBox
SelUFEBox
RebootFPS
RebootSrv
ST32Dig
ST64Dig
```

The GUI exposes these operations and provides parameter fields where required.

## Monitoring and Archiving

The FECB device publishes attributes including:

- `last_message`
- `last_code`
- `band_select_ch1`
- `band_select_ch2`
- `sol_atten_ch1`
- `sol_atten_ch2`

The archiver polls these values at the configured interval, which defaults to **5 seconds**, and stores them in the MySQL/HDB++ backend.

## Logs

The startup script stores service logs under:

```text
/home/<username>/logs/version1/
```

Check the relevant log file when a Tango server, proxy, archiver or GUI fails to start.

## Hardware-Test Checklist

Before testing:

1. Confirm the Tango database is available on port `10000`.
2. Confirm the FECB server starts successfully.
3. Confirm the hardware endpoint can establish a TCP connection to port `3005`.
4. Confirm the proxy can reach `fecb/c01/1`.
5. Confirm the archiver can connect to MySQL/HDB++.
6. Open the GUI at `http://localhost:5000`.
7. Start with a safe command such as `NullCmd` to verify the complete command/response path.

## Notes

This package is the hardware-facing test build. It should be distinguished from the software-only `Hardware_Stub` version, which includes a simulated hardware client.

Python cache files under `__pycache__/` should normally be excluded from Git.
