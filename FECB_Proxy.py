import tango
from tango import DevState
from tango.server import Device, command, device_property


class FECBProxy(Device):

    fecb_device = device_property(dtype=str, default_value="fecb/c01/1")

    def init_device(self):
        Device.init_device(self)
        self._dev = None
        self._connect()

    def _connect(self):
        try:
            self._dev = tango.DeviceProxy("fecb/c01/1")
            self._dev.ping()
            self.set_state(DevState.ON)
            self.set_status("Forwarding to fecb/c01/1")
        except tango.DevFailed as e:
            self._dev = None
            self.set_state(DevState.INIT)
            self.set_status(f"Cannot reach fecb/c01/1: {e.args[0].desc}")

    def _f(self, c, a=None):
        # Reconnect if needed
        if self._dev is None:
            self._connect()
        if self._dev is None:
            raise ConnectionError("Cannot reach fecb/c01/1")
        try:
            result = self._dev.command_inout(c, a) if a is not None \
                     else self._dev.command_inout(c)
            # Sync state from real FECB
            try:
                self.set_state(self._dev.state())
                self.set_status(self._dev.status())
            except Exception:
                pass
            return str(result) if result is not None else ""
        except tango.DevFailed as e:
            # Try to sync FECB state even on error
            try:
                self.set_state(self._dev.state())
                self.set_status(self._dev.status())
            except Exception:
                pass
            raise

    @command(dtype_out=str)
    def NullCmd(self):              return self._f("NullCmd")
    @command(dtype_out=str)
    def RBReset(self):              return self._f("RBReset")
    @command(dtype_out=str)
    def DoMon(self):
        """DoMon needs longer timeout — sets 30s before calling FECB."""
        if self._dev is None:
            self._connect()
        if self._dev is None:
            raise ConnectionError("Cannot reach fecb/c01/1")
        try:
            self._dev.set_timeout_millis(30000)  # 30 seconds for DoMon
            result = self._dev.command_inout("DoMon")
            self.set_state(self._dev.state())
            self.set_status(self._dev.status())
            return str(result) if result is not None else ""
        except Exception:
            raise
        finally:
            try:
                self._dev.set_timeout_millis(3000)  # restore default
            except Exception:
                pass
    @command(dtype_in=str, dtype_out=str)
    def SetRFSys(self, a):          return self._f("SetRFSys", a)
    @command(dtype_in=str, dtype_out=str)
    def SetURFSys(self, a):         return self._f("SetURFSys", a)
    @command(dtype_in=str, dtype_out=str)
    def SetAttn(self, a):           return self._f("SetAttn", a)
    @command(dtype_in=str, dtype_out=str)
    def SetDomonTimeInterval(self, a): return self._f("SetDomonTimeInterval", a)
    @command(dtype_out=str)
    def SetMaintenance(self):       return self._f("SetMaintenance")
    @command(dtype_out=str)
    def SetReset(self):             return self._f("SetReset")
    @command(dtype_out=str)
    def SetShutdown(self):          return self._f("SetShutdown")
    @command(dtype_in=str, dtype_out=str)
    def SetTime(self, a):           return self._f("SetTime", a)
    @command(dtype_in=str, dtype_out=str)
    def SetNoiseFreq(self, a):      return self._f("SetNoiseFreq", a)
    @command(dtype_in=str, dtype_out=str)
    def SetRFNoise(self, a):        return self._f("SetRFNoise", a)
    @command(dtype_out=str)
    def WalshPattern(self):         return self._f("WalshPattern")
    @command(dtype_in=str, dtype_out=str)
    def SetWalsh(self, a):          return self._f("SetWalsh", a)
    @command(dtype_in=str, dtype_out=str)
    def SetWalshGrp(self, a):       return self._f("SetWalshGrp", a)
    @command(dtype_in=str, dtype_out=str)
    def SetWalshFreq(self, a):      return self._f("SetWalshFreq", a)
    @command(dtype_out=str)
    def RFCMSwitch(self):           return self._f("RFCMSwitch")
    @command(dtype_in=str, dtype_out=str)
    def SelFEBox(self, a):          return self._f("SelFEBox", a)
    @command(dtype_in=str, dtype_out=str)
    def SelUFEBox(self, a):         return self._f("SelUFEBox", a)
    @command(dtype_out=str)
    def RebootFPS(self):            return self._f("RebootFPS")
    @command(dtype_out=str)
    def RebootSrv(self):            return self._f("RebootSrv")
    @command(dtype_out=str)
    def ST32Dig(self):              return self._f("ST32Dig")
    @command(dtype_out=str)
    def ST64Dig(self):              return self._f("ST64Dig")


if __name__ == "__main__":
    FECBProxy.run_server()
