"""pytest 全局配置：规避 Windows WMI 挂起，预热 platform.uname 缓存。"""
import socket

import platform


def _warm_uname() -> None:
    try:
        result = platform.uname_result(
            system="Windows",
            node=socket.gethostname(),
            release="11",
            version="10.0.22631",
            machine="AMD64",
        )
        platform._uname_cache = result  # noqa: SLF001
    except Exception:  # noqa: BLE001, S110
        pass


_warm_uname()
