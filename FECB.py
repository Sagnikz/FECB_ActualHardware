import threading
import re

from tango import DevState, AttrWriteType, DebugIt
from tango.server import Device, attribute, command, device_property
from gmrt_link import FECBLink


class FECB(Device):

    port = device_property(dtype=int, default_value=3005)
    subsystemId = device_property(dtype=str, default_value="fecb")
    systemIp = device_property(dtype=str, default_value="127.0.0.1")

    last_message = attribute(
        label="Last message",
        dtype=str,
        access=AttrWriteType.READ
    )

    last_code = attribute(
        label="Last response code",
        dtype=int,
        access=AttrWriteType.READ
    )

    band_select_ch1 = attribute(
        label="Band ch1",
        dtype=str,
        access=AttrWriteType.READ
    )

    band_select_ch2 = attribute(
        label="Band ch2",
        dtype=str,
        access=AttrWriteType.READ
    )

    sol_atten_ch1 = attribute(
        label="Attenuation ch1",
        dtype=str,
        access=AttrWriteType.READ
    )

    sol_atten_ch2 = attribute(
        label="Attenuation ch2",
        dtype=str,
        access=AttrWriteType.READ
    )

    def init_device(self):
        Device.init_device(self)

        self._last_message = ""
        self._last_code = -1
        self._band_select_ch1 = ""
        self._band_select_ch2 = ""
        self._sol_atten_ch1 = ""
        self._sol_atten_ch2 = ""

        self._link = FECBLink(
            host=self.systemIp,
            port=self.port
        )

        self.set_state(DevState.INIT)
        self.set_status("Waiting for FECB hardware client to connect...")

        t = threading.Thread(
            target=self._accept_loop,
            daemon=True
        )
        t.start()

    def _accept_loop(self):
        try:
            addr = self._link.start()

            self.set_state(DevState.ON)
            self.set_status(f"FECB hardware connected from {addr}")
            print(f"Hardware connected from {addr}")

        except OSError as e:
            self.set_state(DevState.FAULT)
            self.set_status(f"Failed to start socket link: {e}")
            return

        while True:
            while self._link.is_connected():
                import time
                time.sleep(1)

            self.set_state(DevState.INIT)
            self.set_status(
                "Hardware disconnected. Waiting for reconnect..."
            )

            print(
                "Hardware disconnected. "
                "Waiting for reconnect on port",
                self._link.port
            )

            addr = self._link.wait_for_reconnect()

            if addr:
                self.set_state(DevState.ON)
                self.set_status(
                    f"FECB hardware reconnected from {addr}"
                )

    def delete_device(self):
        self._link.stop()

    def read_last_message(self):
        return self._last_message

    def read_last_code(self):
        return self._last_code

    def read_band_select_ch1(self):
        return self._band_select_ch1

    def read_band_select_ch2(self):
        return self._band_select_ch2

    def read_sol_atten_ch1(self):
        return self._sol_atten_ch1

    def read_sol_atten_ch2(self):
        return self._sol_atten_ch2

    def _clean_value(self, value):
        """
        Clean unwanted characters and trailing command-status text.

        Examples:
            1420mmand OK       -> 1420
            -37.5897nd OK      -> -37.5897
            EH1 ommand OK      -> EH1
            11:2:14and OK      -> 11:2:14
            MCM Command OK     -> MCM
        """
        if value is None:
            return ""

        value = str(value)
        value = value.replace("\x00", "")
        value = value.replace("\0", "")
        value = value.strip()

        unwanted_suffixes = [
            "Command OK",
            "ommand OK",
            "mmand OK",
            "mand OK",
            "mode",
            "an mode",
            "de",
            "an",
            "n",
            "and OK",
            "nd OK",
            "d OK"
        ]

        for suffix in unwanted_suffixes:
            if value.lower().endswith(suffix.lower()):
                value = value[:-len(suffix)].strip()
                break

        return value

    def _do(self, cmd_id, cmd_name, names=None, values=None):
        if not self._link.is_connected():
            self.set_state(DevState.INIT)
            self.set_status(
                "Hardware not connected — waiting for reconnect"
            )
            raise ConnectionError("Hardware client not connected")

        try:
            resp = self._link.send_command(
                cmd_id,
                cmd_name,
                names,
                values
            )

        except ConnectionError as e:
            self.set_state(DevState.INIT)
            self.set_status(f"Hardware disconnected: {e}")
            raise

        except TimeoutError as e:
            self.set_state(DevState.FAULT)
            self.set_status(str(e))
            raise ConnectionError(str(e))

        self._last_code = resp["code"]

        msg = self._clean_value(resp["message"])

        all_params = []

        for n, v in resp["params"]:
            clean_name = self._clean_value(n)
            clean_value = self._clean_value(v)

            if clean_name and clean_value:
                all_params.append((clean_name, clean_value))

        if not msg and all_params:
            msg = " | ".join(
                f"{n}={v}" for n, v in all_params
            )
        elif not msg:
            msg = f"OK (code={resp['code']})"

        for name, val in all_params:
            nu = name.upper()

            if nu == "BAND_SELECT_M_CH1":
                self._band_select_ch1 = val
            elif nu == "BAND_SELECT_M_CH2":
                self._band_select_ch2 = val
            elif nu in ("SOL_ATTEN_M_CH1", "ATTEN_CH1"):
                self._sol_atten_ch1 = val
            elif nu in ("SOL_ATTEN_M_CH2", "ATTEN_CH2"):
                self._sol_atten_ch2 = val

        print(
            f"CMD {cmd_name}: "
            f"code={resp['code']} "
            f"params={len(all_params)} "
            f"msg={msg[:80]}"
        )

        self._last_message = msg

        if resp["alarm"]["level"] > 0:
            self.set_state(DevState.ALARM)
            self.set_status(
                f"Alarm: {resp['alarm']['description']}"
            )
        else:
            self.set_state(DevState.ON)
            self.set_status(msg)

        return msg

    @command(dtype_out=str)
    @DebugIt()
    def NullCmd(self):
        return self._do("201", "null")

    @command(dtype_out=str)
    @DebugIt()
    def RBReset(self):
        return self._do("202", "reset")

    @command(dtype_out=str)
    @DebugIt()
    def DoMon(self):
        """
        DOMON -- read ALL monitoring data from deviceClientfecb.
        """
        if not self._link.is_connected():
            self.set_state(DevState.INIT)
            self.set_status("Hardware not connected")
            raise ConnectionError("Hardware client not connected")

        try:
            responses = self._link.send_command_domon(timeout=8.0)

        except ConnectionError as e:
            self.set_state(DevState.INIT)
            self.set_status(f"Hardware disconnected: {e}")
            raise

        if not responses:
            self.set_state(DevState.ON)
            self.set_status("DoMon: no response received")
            return "No response received"

        all_params = {}

        for resp in responses:
            for n, v in resp["params"]:
                n = self._clean_value(n)
                v = self._clean_value(v)

                if n and v:
                    all_params[n] = v

        print(
            f"DoMon: {len(responses)} packets, "
            f"{len(all_params)} total params"
        )

        print(f"Keys: {list(all_params.keys())}")

        for i, resp in enumerate(responses):
            print(f"\n--- DEVRESP_FMT Packet {i+1} ---")
            print(f"  code    : {resp['code']}")
            print(f"  event   : {resp['event']}")
            print(f"  message : {repr(resp['message'])}")

            print(
                f"  alarm   : id={resp['alarm']['id']} "
                f"level={resp['alarm']['level']} "
                f"desc={repr(resp['alarm']['description'])}"
            )

            for n, v in resp["params"]:
                n_clean = self._clean_value(n)
                v_clean = self._clean_value(v)

                if n_clean:
                    print(
                        f"    {n_clean} = {repr(v_clean)}"
                    )

        self._last_code = responses[0]["code"]

        for name, val in all_params.items():
            nu = name.upper()

            if nu in ("BAND_SELECT_CH1", "BAND_SELECT_M_CH1"):
                self._band_select_ch1 = val

            elif nu in ("BAND_SELECT_CH2", "BAND_SELECT_M_CH2"):
                self._band_select_ch2 = val

            elif nu in ("SOL_ATTEN_CH1", "SOL_ATTEN_M_CH1"):
                self._sol_atten_ch1 = val

            elif nu in ("SOL_ATTEN_CH2", "SOL_ATTEN_M_CH2"):
                self._sol_atten_ch2 = val

        if all_params:
            msg = " | ".join(
                f"{n}={v}" for n, v in all_params.items()
            )
        else:
            msg = self._clean_value(
                responses[-1]["message"]
            )

            if not msg:
                msg = "OK"

        print(f"DoMon msg: {msg[:120]}")

        self._last_message = msg
        self.set_state(DevState.ON)
        self.set_status(msg[:200])

        return msg

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetRFSys(self, argin):
        parts = argin.strip().split()

        if len(parts) != 2:
            raise ValueError("Usage: '<band_ch1> <band_ch2>'")

        fb1, fb2 = parts

        names = [
            "band_select_ch1",
            "band_select_ch2",
            "rf_swap",
            "sol_atten_ch1",
            "sol_atten_ch2",
            "fe_ngcal",
            "fe_walsh_sw",
            "fe_walsh_grp",
            "fe_ngcycle",
            "rfcm_sw",
            "ngset"
        ]

        values = [
            fb1, fb2, "0", "0", "0",
            "0", "2", "1", "1", "1", "1"
        ]

        result = self._do(
            "2", "setrfsys", names, values
        )

        self._band_select_ch1 = fb1
        self._band_select_ch2 = fb2

        return result

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetURFSys(self, argin):
        parts = argin.strip().split()

        if len(parts) != 13:
            raise ValueError(
                "SetURFSys expects 13 params"
            )

        names = [
            "band_select_ch1",
            "band_select_ch2",
            "rf_swap",
            "sol_atten_ch1",
            "sol_atten_ch2",
            "fe_ngcal",
            "fe_walsh_sw",
            "fe_walsh_grp",
            "fe_ngcycle",
            "rfcm_sw",
            "setwalsh",
            "walshfreq",
            "noisefreq"
        ]

        return self._do(
            "15", "seturfsys", names, parts
        )

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetAttn(self, argin):
        parts = argin.strip().split()

        if len(parts) != 2:
            raise ValueError(
                "Usage: '<ch1_dB> <ch2_dB>'"
            )

        ch1, ch2 = parts

        result = self._do(
            "204",
            "setattn",
            ["sol_atten_ch1", "sol_atten_ch2"],
            [ch1, ch2]
        )

        self._sol_atten_ch1 = ch1
        self._sol_atten_ch2 = ch2

        return result

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetDomonTimeInterval(self, argin):
        return self._do(
            "205",
            "setdomontimeinterval",
            ["domontimeinterval"],
            [argin.strip()]
        )

    @command(dtype_out=str)
    @DebugIt()
    def SetMaintenance(self):
        return self._do("206", "setmaintenance")

    @command(dtype_out=str)
    @DebugIt()
    def SetReset(self):
        return self._do("207", "setreset")

    @command(dtype_out=str)
    @DebugIt()
    def SetShutdown(self):
        return self._do("208", "setshutdown")

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetTime(self, argin):
        return self._do(
            "209",
            "settime",
            ["time"],
            [argin.strip()]
        )

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetNoiseFreq(self, argin):
        return self._do(
            "222",
            "noisefreq",
            ["noisefreq"],
            [argin.strip()]
        )

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetRFNoise(self, argin):
        return self._do(
            "223",
            "setrfnoise",
            ["fe_ngycle"],
            [argin.strip()]
        )

    @command(dtype_out=str)
    @DebugIt()
    def WalshPattern(self):
        return self._do(
            "213",
            "walshpatern",
            ["walshpattern"],
            ["4"]
        )

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetWalsh(self, argin):
        return self._do(
            "213",
            "walshpatern",
            ["walshpattern"],
            [argin.strip()]
        )

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetWalshGrp(self, argin):
        return self._do(
            "214",
            "walshgrp",
            ["fe_walsh_grp"],
            [argin.strip()]
        )

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SetWalshFreq(self, argin):
        return self._do(
            "221",
            "walshfreq",
            ["walshfreq"],
            [argin.strip()]
        )

    @command(dtype_out=str)
    @DebugIt()
    def RFCMSwitch(self):
        return self._do(
            "216",
            "rfcm_sw",
            ["rfcm_sw"],
            ["1"]
        )

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SelFEBox(self, argin):
        return self._do(
            "217",
            "selfebox",
            ["febox"],
            [argin.strip()]
        )

    @command(dtype_in=str, dtype_out=str)
    @DebugIt()
    def SelUFEBox(self, argin):
        return self._do(
            "218",
            "selufebox",
            ["ufebox"],
            [argin.strip()]
        )

    @command(dtype_out=str)
    @DebugIt()
    def RebootFPS(self):
        return self._do("219", "rebootfps")

    @command(dtype_out=str)
    @DebugIt()
    def RebootSrv(self):
        return self._do("220", "rebootsrv")

    @command(dtype_out=str)
    @DebugIt()
    def ST32Dig(self):
        return self._do("224", "st32dig")

    @command(dtype_out=str)
    @DebugIt()
    def ST64Dig(self):
        return self._do("225", "st64dig")


if __name__ == "__main__":
    FECB.run_server()
