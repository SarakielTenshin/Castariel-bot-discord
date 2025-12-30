# core/time_utils.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from core.config import SETTINGS


@dataclass(frozen=True)
class ActiveWindow:
    # Lunes=0 ... Domingo=6
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)  # L-V
    start: dtime = dtime(10, 0)  # 10:00
    end: dtime = dtime(18, 0)    # 18:00 (fin exclusivo)


def _get_tz() -> ZoneInfo:
    tz_name = getattr(SETTINGS, "tz_name", None) or "America/Mexico_City"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        # fallback seguro
        return ZoneInfo("America/Mexico_City")


def now_local() -> datetime:
    """Datetime con tz local (TZ_NAME)."""
    return datetime.now(_get_tz())


def _get_active_window() -> ActiveWindow:
    """
    Defaults: L-V 10:00-18:00.
    Si algún día quieres parametrizarlo por SETTINGS, puedes agregar:
      SETTINGS.active_start = "10:00"
      SETTINGS.active_end = "18:00"
      SETTINGS.active_weekdays = "0,1,2,3,4"
    pero NO es requerido para que funcione.
    """
    # defaults
    weekdays = (0, 1, 2, 3, 4)
    start_h, start_m = 10, 0
    end_h, end_m = 18, 0

    # opcional por env/config (si existe)
    wd = getattr(SETTINGS, "active_weekdays", None)
    if isinstance(wd, str) and wd.strip():
        try:
            weekdays = tuple(int(x.strip()) for x in wd.split(",") if x.strip() != "")
        except Exception:
            weekdays = (0, 1, 2, 3, 4)

    st = getattr(SETTINGS, "active_start", None)
    if isinstance(st, str) and st.strip():
        try:
            hh, mm = st.split(":")
            start_h, start_m = int(hh), int(mm)
        except Exception:
            start_h, start_m = 10, 0

    en = getattr(SETTINGS, "active_end", None)
    if isinstance(en, str) and en.strip():
        try:
            hh, mm = en.split(":")
            end_h, end_m = int(hh), int(mm)
        except Exception:
            end_h, end_m = 18, 0

    return ActiveWindow(
        weekdays=weekdays,
        start=dtime(start_h, start_m),
        end=dtime(end_h, end_m),
    )


def is_active_now() -> bool:
    """
    Regla estricta:
      - Solo L-V
      - Solo 10:00 <= hora < 18:00
    """
    n = now_local()
    win = _get_active_window()

    if n.weekday() not in win.weekdays:
        return False

    t = n.timetz().replace(tzinfo=None)  # compara como naive time
    return (t >= win.start) and (t < win.end)
