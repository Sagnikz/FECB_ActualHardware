SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
cd "${SCRIPT_DIR}"

DIR_LOG=/home/$(whoami)/logs/version1
TANGO_HOST=localhost:10000

if [ ! -d "${DIR_LOG}" ]; then
    mkdir -p "${DIR_LOG}"
    chmod a+rw "${DIR_LOG}"
fi

cur_date=$(date +%d-%m-%Y-%H%M%S)

echo "=============================================="
echo " GMRT FECB Control System"
echo " Started: $(date)"
echo " Script dir: ${SCRIPT_DIR}"
echo "=============================================="

export TANGO_HOST=${TANGO_HOST}

# ── Stop any existing Tango processes ─────────────────────────────────────────
echo ""
echo "Stopping any existing processes..."
pkill -f "tango.databaseds.database" 2>/dev/null
pkill -f "FECB.py"                   2>/dev/null
pkill -f "FECB_Proxy.py"             2>/dev/null
pkill -f "FECB_Archiver.py"          2>/dev/null
pkill -f "app.py"                    2>/dev/null
sleep 2

# ── Step 1: Start Tango DB ────────────────────────────────────────────────────
echo ""
echo "[1/5] Starting Tango Database..."
cd "${SCRIPT_DIR}"
pixi run python3 -m tango.databaseds.database 2 --port 10000 \
    >> "${DIR_LOG}/tangoDb_${cur_date}.log" 2>&1 &
DB_PID=$!
sleep 3

if ps -p ${DB_PID} > /dev/null 2>&1; then
    echo "      Tango DB started (PID=${DB_PID})"
else
    echo "      ### ERROR: Tango DB failed."
    echo "      Check ${DIR_LOG}/tangoDb_${cur_date}.log"
    exit 1
fi
sleep 2

# ── Step 2: Register devices ──────────────────────────────────────────────────
echo ""
echo "[2/5] Registering devices..."
cd "${SCRIPT_DIR}"
pixi run python3 - << 'PYEOF'
import tango
db = tango.Database()
db.set_timeout_millis(10000)

devices = {
    "fecb/c01/1":      ("FECB",         "FECB/test"),
    "fecb/proxy/1":    ("FECBProxy",    "FECBProxy/test"),
    "fecb/archiver/1": ("FECBArchiver", "FECBArchiver/test"),
}

for dev_name, (class_name, server) in devices.items():
    try:
        db.get_device_info(dev_name)
        print(f"      {dev_name} already registered")
    except tango.DevFailed:
        try:
            di = tango.DbDevInfo()
            di.name   = dev_name
            di._class = class_name
            di.server = server
            db.add_device(di)
            print(f"      {dev_name} registered")
        except Exception as e:
            print(f"      WARNING: Could not register {dev_name}: {e}")

try:
    db.put_device_property("fecb/c01/1",      {"port": ["3005"], "subsystemId": ["fecb"], "systemIp": [""]})
    db.put_device_property("fecb/proxy/1",    {"fecb_device": ["fecb/c01/1"]})
    db.put_device_property("fecb/archiver/1", {"fecb_device": ["fecb/c01/1"]})
    print("      Properties set")
except Exception as e:
    print(f"      WARNING: Could not set properties: {e}")
PYEOF
sleep 1

# ── Step 3: Start FECB Device Server ─────────────────────────────────────────
echo ""
echo "[3/5] Starting FECB Device Server (listening on port 3005)..."
cd "${SCRIPT_DIR}"
pixi run python3 FECB.py test \
    -ORBendPoint giop:tcp::45678 \
    >> "${DIR_LOG}/fecb_${cur_date}.log" 2>&1 &
FECB_PID=$!
sleep 2

if ps -p ${FECB_PID} > /dev/null 2>&1; then
    echo "      FECB Device Server started (PID=${FECB_PID})"
    echo "      Waiting for hardware client to connect on port 3005..."
else
    echo "      ### ERROR: FECB Device Server failed."
    cat "${DIR_LOG}/fecb_${cur_date}.log"
    exit 1
fi
sleep 2

# ── Step 4: Start FECB Proxy ─────────────────────────────────────────────────
echo ""
echo "[4/5] Starting FECB Proxy..."
cd "${SCRIPT_DIR}"
pixi run python3 FECB_Proxy.py test \
    -ORBendPoint giop:tcp::45679 \
    >> "${DIR_LOG}/proxy_${cur_date}.log" 2>&1 &
PROXY_PID=$!
sleep 2

if ps -p ${PROXY_PID} > /dev/null 2>&1; then
    echo "      FECB Proxy started (PID=${PROXY_PID})"
else
    echo "      ### ERROR: FECB Proxy failed."
    cat "${DIR_LOG}/proxy_${cur_date}.log"
    exit 1
fi
sleep 2

# ── Step 5: Start Archiver ────────────────────────────────────────────────────
echo ""
echo "[5/6] Starting Archiver..."
cd "${SCRIPT_DIR}"
pixi run python3 FECB_Archiver.py test \
    -ORBendPoint giop:tcp::45680 \
    >> "${DIR_LOG}/archiver_${cur_date}.log" 2>&1 &
ARCH_PID=$!
sleep 2

if ps -p ${ARCH_PID} > /dev/null 2>&1; then
    echo "      Archiver started (PID=${ARCH_PID})"
    echo "      Will poll FECB every 5s once hardware connects"
else
    echo "      ### WARNING: Archiver failed."
    echo "      Check ${DIR_LOG}/archiver_${cur_date}.log"
    ARCH_PID="N/A"
fi

# ── Step 6: Start Web GUI ─────────────────────────────────────────────────────
echo ""
echo "[6/6] Starting Web GUI..."
cd "${SCRIPT_DIR}"
pixi run python3 app.py \
    >> "${DIR_LOG}/webgui_${cur_date}.log" 2>&1 &
GUI_PID=$!
sleep 2

if ps -p ${GUI_PID} > /dev/null 2>&1; then
    echo "      Web GUI started (PID=${GUI_PID})"
else
    echo "      ### ERROR: Web GUI failed."
    cat "${DIR_LOG}/webgui_${cur_date}.log"
    exit 1
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo " All Tango services started!"
echo " Open http://localhost:5000 in your browser"
echo ""
echo " PIDs:"
echo "   Tango DB    : ${DB_PID}"
echo "   FECB Server : ${FECB_PID}"
echo "   Proxy       : ${PROXY_PID}"
echo "   Archiver    : ${ARCH_PID}"
echo "   Web GUI     : ${GUI_PID}"
echo ""
echo " Logs: ${DIR_LOG}/"
echo "=============================================="

echo "${DB_PID} ${FECB_PID} ${PROXY_PID} ${ARCH_PID} ${GUI_PID}" \
    > /tmp/gmrt_v1_pids.txt
