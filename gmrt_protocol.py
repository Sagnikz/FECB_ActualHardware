import struct
import time

PORT    = 3005
MAXDATA = 128
DATALEN = 64
MSGLEN  = 128

BASICFLDS_FMT = struct.Struct("<i f h h {0}s {0}s {0}s 8s".format(DATALEN))
DATAPKT_FMT   = struct.Struct("<h {0}s {0}s".format(MAXDATA * DATALEN))
RESPALARM_FMT = struct.Struct("<h h {0}s".format(MSGLEN))

PARSECMD_FMT = struct.Struct(
    "<i f h h"
    f"{DATALEN}s {DATALEN}s {DATALEN}s 8s"
    f"h {MAXDATA*DATALEN}s {MAXDATA*DATALEN}s"
)

DEVRESP_FMT = struct.Struct(
    "<h h {0}s h h {0}s h {1}s {1}s i f h h {2}s {2}s {2}s 8s".format(
        MSGLEN, MAXDATA*DATALEN, DATALEN)
)


def _pad(s, n):
    b = s.encode("ascii") if isinstance(s, str) else s
    return b.ljust(n, b"\0")


def build_basicflds(cmd_id, cmd_name, subsysid="fecb", seq=11,
                    version=11.0, priority=1, timeout=10):
    timestamp = time.strftime("%d-%b-%Y %H:%M:%S")
    return (seq, version, priority, timeout,
            _pad(subsysid, DATALEN), _pad(cmd_name, DATALEN),
            _pad(timestamp, DATALEN), _pad(cmd_id, 8))


def build_datapkt(names, values):
    numpkt   = len(names)
    prmnames = b"".join(_pad(n, DATALEN) for n in names)
    prmvals  = b"".join(_pad(v, DATALEN) for v in values)
    return (numpkt,
            prmnames.ljust(MAXDATA*DATALEN, b"\0"),
            prmvals.ljust(MAXDATA*DATALEN,  b"\0"))


def build_command(cmd_id, cmd_name, names=None, values=None):
    names  = names  or []
    values = values or []
    return PARSECMD_FMT.pack(*build_basicflds(cmd_id, cmd_name),
                             *build_datapkt(names, values))


def _unpack_datapkt_fields(numpkt, prmnames_raw, prmvalues_raw):
    names  = [prmnames_raw [i*DATALEN:(i+1)*DATALEN].decode("ascii","ignore").replace("\x00","").strip() for i in range(numpkt)]
    values = [prmvalues_raw[i*DATALEN:(i+1)*DATALEN].decode("ascii","ignore").replace("\x00","").strip() for i in range(numpkt)]
    return list(zip(names, values))


def parse_command(raw):
    f = PARSECMD_FMT.unpack(raw)
    return {
        "seq": f[0], "version": f[1], "priority": f[2], "timeout": f[3],
        "subsysid":  f[4].decode("ascii","ignore").replace("\x00","").strip(),
        "cmd_name":  f[5].decode("ascii","ignore").replace("\x00","").strip(),
        "timestamp": f[6].decode("ascii","ignore").replace("\x00","").strip(),
        "cmd_id":    f[7].decode("ascii","ignore").replace("\x00","").strip(),
        "params":    _unpack_datapkt_fields(f[8], f[9], f[10]),
    }


def build_response(code, event, message, alarm_id, alarm_level,
                   alarm_desc, names, values, cmd):
    numpkt   = len(names)
    prmnames = b"".join(_pad(n, DATALEN) for n in names).ljust(MAXDATA*DATALEN, b"\0")
    prmvals  = b"".join(_pad(v, DATALEN) for v in values).ljust(MAXDATA*DATALEN, b"\0")
    return DEVRESP_FMT.pack(
        code, event, _pad(message, MSGLEN),
        alarm_id, alarm_level, _pad(alarm_desc, MSGLEN),
        numpkt, prmnames, prmvals,
        cmd["seq"], cmd["version"], cmd["priority"], cmd["timeout"],
        _pad(cmd["subsysid"], DATALEN), _pad(cmd["cmd_name"], DATALEN),
        _pad(cmd["timestamp"], DATALEN), _pad(cmd["cmd_id"], 8),
    )


def parse_response(raw):
    f = DEVRESP_FMT.unpack(raw)
    return {
        "code":    f[0],
        "event":   f[1],
        "message": f[2].decode("ascii","ignore").replace("\x00","").strip(),
        "alarm":   {"id": f[3], "level": f[4],
                    "description": f[5].decode("ascii","ignore").replace("\x00","").strip()},
        "params":  _unpack_datapkt_fields(f[6], f[7], f[8]),
        "basicflds": {
            "seq": f[9], "version": f[10], "priority": f[11], "timeout": f[12],
            "subsysid":  f[13].decode("ascii","ignore").replace("\x00","").strip(),
            "cmd_name":  f[14].decode("ascii","ignore").replace("\x00","").strip(),
            "timestamp": f[15].decode("ascii","ignore").replace("\x00","").strip(),
            "cmd_id":    f[16].decode("ascii","ignore").replace("\x00","").strip(),
        },
    }
