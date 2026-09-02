import os
import tango
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

DEVICE_NAME = os.environ.get("FECB_DEVICE", "fecb/proxy/1")
FECB_DIRECT = "fecb/c01/1"

COMMANDS = [
    {"id": "INIT",                    "cmd": "NullCmd",              "hint": "null handshake -- initialise connection to FECB", "params": []},
    {"id": "QUIT",                    "cmd": None,                   "hint": "quit the control session", "params": []},
    {"id": "RBRESET",                 "cmd": "RBReset",              "hint": "reset the FECB", "params": []},
    {"id": "REBOOTFPS",               "cmd": "RebootFPS",            "hint": "reboot the FPS", "params": []},
    {"id": "REBOOTSRV",               "cmd": "RebootSrv",            "hint": "reboot the server", "params": []},
    {"id": "RFCM SW",                 "cmd": "RFCMSwitch",           "hint": "rfcm_sw <rfcm_sw> val=0,1", "params": []},
    {"id": "SET ATTN",                "cmd": "SetAttn",
     "hint": "set attn <ch1> <ch2>  ch1=0.0 to 31.5  ch2=0.0 to 31.5  step 0.5 dB",
     "params": [
         {"name": "sol_atten_ch1", "label": "Channel 1 Attenuation (0.0-31.5 dB, step 0.5)"},
         {"name": "sol_atten_ch2", "label": "Channel 2 Attenuation (0.0-31.5 dB, step 0.5)"},
     ]},
    {"id": "SET DOMON TIME INTERVAL", "cmd": "SetDomonTimeInterval",
     "hint": "setDomonTimeInterval <domontimeInterval> where domontimeInterval is in seconds",
     "params": [{"name": "domontimeinterval", "label": "Time Interval (seconds)"}]},
    {"id": "SET MAINTENANCE",         "cmd": "SetMaintenance",       "hint": "put FECB into maintenance mode", "params": []},
    {"id": "SET RESET",               "cmd": "SetReset",             "hint": "reset FECB settings", "params": []},
    {"id": "SET SHUTDOWN",            "cmd": "SetShutdown",          "hint": "shutdown the FECB", "params": []},
    {"id": "SET TIME",                "cmd": "SetTime",              "hint": "set system time <time_string>",
     "params": [{"name": "time", "label": "Time String"}]},
    {"id": "SET NOISEFREQ",           "cmd": "SetNoiseFreq",         "hint": "set noise frequency <noisefreq>",
     "params": [{"name": "noisefreq", "label": "Noise Frequency"}]},
    {"id": "SET_RFNOISE",             "cmd": "SetRFNoise",
     "hint": "setrfnoise -- 0, 25, 50, 100 percent duty cycle",
     "params": [{"name": "fe_ngycle", "label": "Duty Cycle % (0, 25, 50, 100)"}]},
    {"id": "SET_WALSHFREQ",           "cmd": "SetWalshFreq",
     "hint": "set walsh frequency <walshfreq>",
     "params": [{"name": "walshfreq", "label": "Walsh Frequency"}]},
    {"id": "SET_WALSHPATERN",         "cmd": "SetWalsh",
     "hint": "set walsh pattern <walshpattern>",
     "params": [{"name": "walshpattern", "label": "Walsh Pattern"}]},
    {"id": "SET RF SYS",              "cmd": "SetRFSys",
     "hint": "setrfsys <band_select_ch1> <band_select_ch2>",
     "params": [
         {"name": "band_select_ch1", "label": "Band Ch1 (e.g. L or 325)"},
         {"name": "band_select_ch2", "label": "Band Ch2 (e.g. S or 610)"},
     ]},
    {"id": "SET URF SYS",             "cmd": "SetURFSys",
     "hint": "seturfsys <band_ch1> <band_ch2> <rf_swap> <sol_atten_ch1> <sol_atten_ch2> <fe_ngcal> <fe_walsh_sw> <fe_walsh_grp> <fe_ngcycle> <rfcm_sw> <setwalsh> <walshfreq> <noisefreq>",
     "params": [
         {"name": "band_select_ch1", "label": "Band Ch1 (150,190,235,290,325,350,410,470,600,610,685,725,770,850,1060,1170,1280,1390,1420)"},
         {"name": "band_select_ch2", "label": "Band Ch2 (same values as ch1)"},
         {"name": "rf_swap",         "label": "RF Swap (0/1)"},
         {"name": "sol_atten_ch1",   "label": "Sol Atten Ch1 (-1,0,1,14,30,44)"},
         {"name": "sol_atten_ch2",   "label": "Sol Atten Ch2 (-1,0,1,14,30,44)"},
         {"name": "fe_ngcal",        "label": "FE NG Cal (-1,0,1,2,3)"},
         {"name": "fe_walsh_sw",     "label": "FE Walsh SW (0/1)"},
         {"name": "fe_walsh_grp",    "label": "FE Walsh GRP (0/1)"},
         {"name": "fe_ngcycle",      "label": "FE NG Cycle (0,25,50,100)"},
         {"name": "rfcm_sw",         "label": "RFCM SW (0/1)"},
         {"name": "setwalsh",        "label": "Set Walsh"},
         {"name": "walshfreq",       "label": "Walsh Freq"},
         {"name": "noisefreq",       "label": "Noise Freq"},
     ]},
    {"id": "SET WALSH",    "cmd": "SetWalsh",   "hint": "set walsh pattern value",
     "params": [{"name": "walshpattern", "label": "Walsh Pattern Value"}]},
    {"id": "SET WALSHGRP", "cmd": "SetWalshGrp","hint": "set walsh group (0/1)",
     "params": [{"name": "fe_walsh_grp", "label": "Walsh Group (0/1)"}]},
    {"id": "SEL FEBOX",    "cmd": "SelFEBox",   "hint": "select FE box <febox_id>",
     "params": [{"name": "febox", "label": "FE Box ID"}]},
    {"id": "SEL UFEBOX",   "cmd": "SelUFEBox",  "hint": "select UFE box <ufebox_id>",
     "params": [{"name": "ufebox", "label": "UFE Box ID"}]},
    {"id": "ST32DIG",      "cmd": "ST32Dig",    "hint": "32 digit status read", "params": []},
    {"id": "ST64DIG",      "cmd": "ST64Dig",    "hint": "64 digit status read", "params": []},
]


def get_proxy():
    try:
        p = tango.DeviceProxy(DEVICE_NAME)
        p.ping()
        return p, None
    except tango.DevFailed as e:
        return None, str(e.args[0].desc)
    except Exception as e:
        return None, str(e)


@app.route("/")
def index():
    return render_template("index.html", commands=COMMANDS, device=DEVICE_NAME)


@app.route("/api/status")
def status():
    proxy, err = get_proxy()
    if err:
        return jsonify({"state": "INIT", "status": err, "connected": False})
    try:
        fecb = tango.DeviceProxy(FECB_DIRECT)
        state = str(proxy.state())
        return jsonify({
            "state":        state,
            "status":       proxy.status(),
            "connected":    True,
            "last_message": str(fecb.last_message),
            "last_code":    int(fecb.last_code),
            "band_ch1":     str(fecb.band_select_ch1),
            "band_ch2":     str(fecb.band_select_ch2),
            "atten_ch1":    str(fecb.sol_atten_ch1),
            "atten_ch2":    str(fecb.sol_atten_ch2),
        })
    except Exception as e:
        return jsonify({"state": "INIT", "status": str(e), "connected": False})


@app.route("/api/execute", methods=["POST"])
def execute():
    data      = request.json
    cmd_id    = data.get("cmd_id")
    tango_cmd = data.get("tango_cmd")
    argin     = data.get("argin", None)

    if tango_cmd is None:
        return jsonify({"success": False,
                        "output": f"'{cmd_id}' has no Tango command mapped."})

    proxy, err = get_proxy()
    if err:
        return jsonify({"success": False,
                        "output": f"Cannot connect to device: {err}"})
    try:
        # DoMon needs longer timeout for multiple responses
        if tango_cmd == "DoMon":
            proxy.set_timeout_millis(60000)  # 60 seconds for DoMon
        result = proxy.command_inout(tango_cmd, argin) \
                 if argin else proxy.command_inout(tango_cmd)
        if tango_cmd == "DoMon":
            proxy.set_timeout_millis(3000)  # restore default
        return jsonify({"success": True,
                        "output": str(result) if result is not None else "OK"})
    except tango.DevFailed as e:
        return jsonify({"success": False,
                        "output": f"ERROR: {e.args[0].desc}"})
    except Exception as e:
        return jsonify({"success": False, "output": f"ERROR: {e}"})


if __name__ == "__main__":
    print(f"FECB GUI starting. Device: {DEVICE_NAME}")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=False, host="0.0.0.0", port=5000)
