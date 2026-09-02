import socket
import threading
import gmrt_protocol as proto


class FECBLink:
    def __init__(self, host="", port=proto.PORT):
        self.host         = host
        self.port         = port
        self._server_sock = None
        self._conn        = None
        self._lock        = threading.Lock()

    def start(self):
        """Start listening and accept one hardware client connection."""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(1)
        conn, addr = self._server_sock.accept()
        self._conn = conn
        return addr

    def wait_for_reconnect(self):
        """Wait for hardware client to reconnect after disconnect."""
        print(f"Waiting for hardware client to reconnect on port {self.port}")
        try:
            conn, addr = self._server_sock.accept()
            with self._lock:
                if self._conn:
                    try: self._conn.close()
                    except: pass
                self._conn = conn
            print(f"Hardware client reconnected from {addr}")
            return addr
        except OSError as e:
            print(f"Reconnect failed: {e}")
            return None

    def is_connected(self):
        return self._conn is not None

    def stop(self):
        with self._lock:
            for s in (self._conn, self._server_sock):
                if s:
                    try: s.close()
                    except OSError: pass
            self._conn = None
            self._server_sock = None

    def send_command(self, cmd_id, cmd_name, names=None, values=None, timeout=5.0):
        """Send command and read ONE response."""
        if self._conn is None:
            raise ConnectionError("Hardware client not connected")
        raw_cmd = proto.build_command(cmd_id, cmd_name, names, values)
        with self._lock:
            try:
                self._conn.sendall(raw_cmd)
            except (BrokenPipeError, OSError) as e:
                self._conn = None
                raise ConnectionError(f"Broken pipe sending command: {e}")
            _print_cmd(cmd_id, cmd_name, names, values)
            self._conn.settimeout(timeout)
            try:
                raw = self._recv_exact(proto.DEVRESP_FMT.size)
            except (BrokenPipeError, OSError, ConnectionResetError) as e:
                self._conn = None
                raise ConnectionError(f"Broken pipe receiving response: {e}")
            if raw is None:
                self._conn = None
                raise ConnectionError("Hardware disconnected")
            resp = proto.parse_response(raw)
            _print_resp(resp)
        return resp

    def send_command_twice(self, cmd_id, cmd_name, names=None, values=None, timeout=8.0):
        """
        Send command and read TWO responses in one locked session.
        Used for DoMon:
          1st response: ack ('Command received successfully')
          2nd response: ALL monitoring data (BAND_SELECT_CH1, SOL_ATTEN, CB_TEMP etc.)
        Returns (resp1, resp2).
        """
        if self._conn is None:
            raise ConnectionError("Hardware client not connected")
        raw_cmd = proto.build_command(cmd_id, cmd_name, names, values)
        with self._lock:
            # Send command
            try:
                self._conn.sendall(raw_cmd)
            except (BrokenPipeError, OSError) as e:
                self._conn = None
                raise ConnectionError(f"Broken pipe sending command: {e}")
            _print_cmd(cmd_id, cmd_name, names, values)
            self._conn.settimeout(timeout)

            # Read FIRST response (ack)
            try:
                raw1 = self._recv_exact(proto.DEVRESP_FMT.size)
            except (BrokenPipeError, OSError, ConnectionResetError) as e:
                self._conn = None
                raise ConnectionError(f"Broken pipe on 1st response: {e}")
            if raw1 is None:
                self._conn = None
                raise ConnectionError("Hardware disconnected on 1st response")
            resp1 = proto.parse_response(raw1)
            p1 = len([p for p in resp1["params"] if p[0].strip()])
            print(f"=== 1st response: code={resp1['code']} msg={resp1['message']} params={p1}")

            # Read SECOND response (monitoring data)
            try:
                raw2 = self._recv_exact(proto.DEVRESP_FMT.size)
            except (BrokenPipeError, OSError, ConnectionResetError) as e:
                self._conn = None
                raise ConnectionError(f"Broken pipe on 2nd response: {e}")
            if raw2 is None:
                self._conn = None
                raise ConnectionError("Hardware disconnected on 2nd response")
            resp2 = proto.parse_response(raw2)
            p2 = len([p for p in resp2["params"] if p[0].strip()])
            print(f"=== 2nd response: code={resp2['code']} msg={resp2['message']} params={p2}")
            _print_resp(resp2)

        return resp1, resp2

    def read_one_response(self, timeout=8.0):
        """
        Read one response without sending a command.
        Timeout does NOT kill the connection.
        """
        if self._conn is None:
            raise ConnectionError("Hardware not connected")
        with self._lock:
            self._conn.settimeout(timeout)
            try:
                raw = self._recv_exact(proto.DEVRESP_FMT.size)
            except TimeoutError:
                raise TimeoutError("Timed out waiting for monitoring data")
            except (BrokenPipeError, OSError, ConnectionResetError) as e:
                self._conn = None
                raise ConnectionError(f"Broken pipe: {e}")
            if raw is None:
                self._conn = None
                raise ConnectionError("Hardware disconnected")
            resp = proto.parse_response(raw)
            _print_resp(resp)
        return resp


    def flush_pending(self):
        """Discard any unread response packets before sending DoMon."""
        if self._conn is None:
            return
        self._conn.settimeout(0.1)  # very short timeout
        flushed = 0
        while True:
            try:
                raw = self._recv_exact(proto.DEVRESP_FMT.size)
                if raw is None:
                    break
                flushed += 1
                print(f"Flushed 1 pending packet")
            except (TimeoutError, OSError):
                break
        if flushed:
            print(f"Flushed {flushed} pending packet(s) before DoMon")

    def send_command_domon(self, timeout=8.0):
        """
        Send DoMon command and read ALL responses until socket timeout.
        Combines params from every response packet into one dict.
        Typical flow:
          Packet 1: ack (Command received successfully, 0 params)
          Packet 2: header (TIME_OF_DAY, TOTALRESP, MCMCARD)
          Packet 3+: card data (BAND_SELECT_CH1, SOL_ATTEN, CB_TEMP, etc.)
        """
        if self._conn is None:
            raise ConnectionError("Hardware client not connected")
        raw_cmd = proto.build_command("203", "domon")
        all_responses = []

        with self._lock:
            # Flush any leftover packets from previous commands
            self.flush_pending()

            try:
                self._conn.sendall(raw_cmd)
            except (BrokenPipeError, OSError) as e:
                self._conn = None
                raise ConnectionError(f"Broken pipe sending DoMon: {e}")

            print("=== DoMon: reading all responses...")
            self._conn.settimeout(timeout)

            while True:
                try:
                    raw = self._recv_exact(proto.DEVRESP_FMT.size)
                    if raw is None:
                        self._conn = None
                        break
                    resp = proto.parse_response(raw)
                    params = [(n.strip(), v.strip()) for n, v in resp["params"]
                              if n.strip() and v.strip()]
                    print(f"    Packet {len(all_responses)+1}: "
                          f"code={resp['code']} msg={resp['message'][:30]} "
                          f"params={len(params)}")
                    all_responses.append(resp)
                    # Short timeout for subsequent packets
                    self._conn.settimeout(3.0)
                except TimeoutError:
                    print(f"    No more packets (got {len(all_responses)} total)")
                    break
                except (BrokenPipeError, OSError, ConnectionResetError) as e:
                    self._conn = None
                    break

        return all_responses

    def _recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = self._conn.recv(n - len(buf))
            except socket.timeout:
                raise TimeoutError("Timed out waiting for hardware response")
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)


def _print_cmd(cmd_id, cmd_name, names, values):
    names = names or []; values = values or []
    print(f"\n=== Sent: {cmd_name} (id={cmd_id})")
    for n, v in zip(names, values):
        print(f"    {n} = {v}")
    print("====================")


def _print_resp(resp):
    print(f"=== Response: code={resp['code']} msg={resp['message']}")
    params = [(n, v) for n, v in resp["params"] if n.strip()]
    for n, v in params[:6]:
        print(f"    {n} = {v}")
    if len(params) > 6:
        print(f"    ... +{len(params)-6} more params")
