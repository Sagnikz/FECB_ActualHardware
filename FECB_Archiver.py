import threading
import datetime
import time
import tango
from tango import DevState, AttrWriteType
from tango.server import Device, attribute, command, device_property

FECB_URL = "fecb/c01/1"

ATTRS_TO_ARCHIVE = [
    "last_message",
    "last_code",
    "band_select_ch1",
    "band_select_ch2",
    "sol_atten_ch1",
    "sol_atten_ch2",
]


def get_db():
    import mysql.connector
    return mysql.connector.connect(
        host="localhost", user="hdbpp",
        password="hdbpp", database="hdbpp"
    )


def init_schema():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hdb_fecb (
            id        BIGINT AUTO_INCREMENT PRIMARY KEY,
            device    VARCHAR(255) NOT NULL,
            attribute VARCHAR(255) NOT NULL,
            value     TEXT,
            quality   VARCHAR(32) DEFAULT 'VALID',
            timestamp DATETIME(6) NOT NULL,
            INDEX idx_device_attr (device, attribute),
            INDEX idx_timestamp   (timestamp)
        )
    """)
    conn.commit()
    cur.close(); conn.close()
    print("HDB++ schema ready.")


def archive_value(device, attr_name, value, quality="VALID"):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO hdb_fecb (device, attribute, value, quality, timestamp) "
            "VALUES (%s, %s, %s, %s, %s)",
            (device, attr_name, str(value), quality, datetime.datetime.now())
        )
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"Archive write error: {e}")


class FECBArchiver(Device):

    fecb_device   = device_property(dtype=str, default_value="fecb/c01/1")
    poll_interval = device_property(dtype=int, default_value=5)

    archived_count = attribute(label="Total archived", dtype=int,  access=AttrWriteType.READ)
    is_archiving   = attribute(label="Archiving",      dtype=bool, access=AttrWriteType.READ)
    last_archived  = attribute(label="Last archived",  dtype=str,  access=AttrWriteType.READ)

    def init_device(self):
        Device.init_device(self)
        self._archived_count = 0
        self._is_archiving   = False
        self._last_archived  = ""
        self._proxy          = None
        self._mysql_ok       = False
        self.set_state(DevState.INIT)
        self.set_status("Starting archiver...")
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _connect_mysql(self):
        try:
            init_schema()
            self._mysql_ok = True
            print("MySQL connected and schema ready")
            return True
        except Exception as e:
            self._mysql_ok = False
            print(f"MySQL not available: {e}")
            return False

    def _connect_fecb(self):
        try:
            self._proxy = tango.DeviceProxy(FECB_URL)
            self._proxy.ping()
            return True
        except Exception as e:
            self._proxy = None
            return False

    def _run(self):
        # Try MySQL — if not available, still run but skip archiving
        mysql_available = self._connect_mysql()
        if not mysql_available:
            self.set_state(DevState.ALARM)
            self.set_status("MySQL not available — monitoring only, not archiving")
            print("WARNING: MySQL not available. Archiver will monitor but not store data.")

        self._is_archiving = True

        while self._is_archiving:
            # Connect to FECB if needed
            if self._proxy is None:
                if not self._connect_fecb():
                    self.set_state(DevState.INIT)
                    self.set_status("Waiting for FECB device...")
                    time.sleep(self.poll_interval)
                    continue
                else:
                    state = DevState.ON if mysql_available else DevState.ALARM
                    self.set_state(state)
                    self.set_status(
                        f"Archiving {len(ATTRS_TO_ARCHIVE)} attrs every {self.poll_interval}s"
                        if mysql_available else
                        f"Monitoring {len(ATTRS_TO_ARCHIVE)} attrs (MySQL unavailable)"
                    )

            # Poll and optionally archive each attribute
            failed = 0
            for attr in ATTRS_TO_ARCHIVE:
                try:
                    result = self._proxy.read_attribute(attr)
                    val = result.value
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    print(f"[{now}] {attr} = {val}")
                    with threading.Lock():
                        self._archived_count += 1
                        self._last_archived = f"{attr}={val}"
                    if mysql_available:
                        archive_value("fecb/c01/1", attr, val)
                except tango.DevFailed:
                    failed += 1
                except Exception as e:
                    print(f"Error reading {attr}: {e}")
                    failed += 1

            if failed == len(ATTRS_TO_ARCHIVE):
                self._proxy = None
                self.set_state(DevState.INIT)
                self.set_status("FECB disconnected. Waiting for reconnect...")

            time.sleep(self.poll_interval)

    def read_archived_count(self): return self._archived_count
    def read_is_archiving(self):   return self._is_archiving
    def read_last_archived(self):  return self._last_archived

    @command(dtype_out=str)
    def StopArchiving(self):
        self._is_archiving = False
        self.set_state(DevState.OFF)
        self.set_status("Archiving stopped.")
        return "Stopped."

    @command(dtype_out=str)
    def StartArchiving(self):
        if not self._is_archiving:
            self._is_archiving = True
            t = threading.Thread(target=self._run, daemon=True)
            t.start()
            return "Started."
        return "Already running."

    @command(dtype_in=str, dtype_out=str)
    def GetHistory(self, argin):
        """argin: '<attr_name> <N>'  e.g. 'sol_atten_ch1 10'"""
        parts = argin.strip().split()
        if len(parts) != 2:
            return "Usage: '<attr_name> <N>'"
        attr_name, n = parts[0], int(parts[1])
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "SELECT timestamp, value FROM hdb_fecb "
                "WHERE device=%s AND attribute=%s "
                "ORDER BY timestamp DESC LIMIT %s",
                ("fecb/c01/1", attr_name, n)
            )
            rows = cur.fetchall()
            cur.close(); conn.close()
            if not rows:
                return f"No history for {attr_name}"
            return "\n".join(f"{ts}  {val}" for ts, val in rows)
        except Exception as e:
            return f"DB error: {e}"


if __name__ == "__main__":
    FECBArchiver.run_server()
