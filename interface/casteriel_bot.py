import asyncio
import json
import random
import re
import unicodedata
import time
from pathlib import Path
from typing import Optional, Tuple

import discord

from core.config import SETTINGS
from core.time_utils import is_active_now as _is_active_now, now_local
from states.mood import Mood, roll_mood_1d6, mood_label
from content.loader import Content

print("RUNNING:", __file__)

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

ALWAYS_AWAKE_DEFAULT = False  # Horario ON. Usa !wake para forzar.
FORCE_MOOD = None  # Mood.SERENO / Mood.ADVERTENCIA / Mood.CLAUSURA / Mood.SILENCIO / None

OFFROL_CHANNEL_NAME = "interacciones-off-rol"

DEFAULT_GUILD_ID = 722211219855114271
DEFAULT_CHANNEL_NAME = getattr(SETTINGS, "general_channel_name", "general")

# Dogma operacional (nuevo)
DOGMA_OPERACIONAL_PATH = Path(__file__).resolve().parents[1] / "dogmas" / "dogma_operacional.json"

# Anti-random / escalado insistencia
INSIST_WINDOW_S = 10 * 60       # ventana de 10 min para contar insistencia por usuario/canal
INSIST_RESET_S = 12 * 60        # si pasan 12 min, resetea
MAX_DOGMA_REPLIES_BEFORE_COOLDOWN = 3  # "no más de 3 respuestas antes del cooldown"
DOGMA_COOLDOWN_S = 90           # cooldown general por usuario/canal para dogma (suave, ajustable)

# ============================================================
# OVERRIDE MANUAL DE DESPERTAR (FORZAR WAKE)
# ============================================================

MANUAL_AWAKE = False
MANUAL_AWAKE_UNTIL: Optional[float] = None

def _now_ts() -> float:
    return time.time()

def manual_awake_active() -> bool:
    global MANUAL_AWAKE, MANUAL_AWAKE_UNTIL
    if not MANUAL_AWAKE:
        return False
    if MANUAL_AWAKE_UNTIL is None:
        return True
    if _now_ts() <= MANUAL_AWAKE_UNTIL:
        return True
    MANUAL_AWAKE = False
    MANUAL_AWAKE_UNTIL = None
    return False

def set_manual_awake(on: bool, minutes: Optional[int] = None):
    global MANUAL_AWAKE, MANUAL_AWAKE_UNTIL
    MANUAL_AWAKE = bool(on)
    if not on:
        MANUAL_AWAKE_UNTIL = None
        return
    if minutes is None:
        MANUAL_AWAKE_UNTIL = None
    else:
        minutes = max(1, int(minutes))
        MANUAL_AWAKE_UNTIL = _now_ts() + minutes * 60

def is_active_now() -> bool:
    if manual_awake_active():
        return True
    if ALWAYS_AWAKE_DEFAULT:
        return True
    return _is_active_now()

# ============================================================
# DISCORD
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.dm_messages = True

client = discord.Client(intents=intents)
content = Content()

# ============================================================
# MOOD DIARIO + TENSIÓN GLOBAL
# ============================================================
current_mood: Mood = Mood.OBSERVANDO
mood_date_key: str | None = None

tension_global: int = 2
last_global_event_ts: float = time.time()

def clamp(n: int, lo: int, hi: int) -> int:
    return lo if n < lo else hi if n > hi else n

def bump_tension(delta: int):
    global tension_global, last_global_event_ts
    tension_global = clamp(tension_global + delta, 0, 10)
    last_global_event_ts = time.time()

def decay_tension():
    global tension_global, last_global_event_ts
    now = time.time()
    if now - last_global_event_ts > 8 * 60 and tension_global > 0:
        tension_global -= 1
        last_global_event_ts = now

def refresh_daily_mood():
    global current_mood, mood_date_key
    today = now_local().strftime("%Y-%m-%d")
    if mood_date_key != today:
        current_mood = roll_mood_1d6()
        mood_date_key = today
        print(f"🎲 Mood del día: {mood_label(current_mood)}")

def effective_mood(base: Mood) -> Mood:
    t = tension_global
    if t >= 9: return Mood.SILENCIO
    if t >= 7: return Mood.CLAUSURA
    if t >= 5: return Mood.ADVERTENCIA
    if t >= 3: return Mood.EVALUANDO
    if t <= 1 and base in (Mood.EVALUANDO, Mood.ADVERTENCIA):
        return Mood.OBSERVANDO
    return base

# ============================================================
# TEXTO + TOKENS
# ============================================================
WORD = re.compile(r"[a-z0-9ñáéíóúü]+", re.I)

def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def tokens(s: str) -> set[str]:
    s = strip_accents((s or "").lower())
    return set(WORD.findall(s))

def clean_line(text: str) -> str:
    if not text:
        return "…"
    lines = [l.strip() for l in str(text).split("\n") if l.strip()]
    seen, out = set(), []
    for l in lines:
        k = l.lower()
        if k not in seen:
            seen.add(k)
            out.append(l)
    return "\n".join(out) if out else "…"

def split_sentences(text: str) -> list[str]:
    return re.split(r'(?<=[\.\!\?])\s+', clean_line(text))

def limit_sentences(text: str, n: int) -> str:
    s = split_sentences(text)
    return " ".join(s[:max(1, n)]).strip() if s else "…"

def as_action(line: str) -> str:
    return f"*{line}*"

# ============================================================
# ESTILO POR MOOD
# ============================================================
CLOSE_TAGS = ["Silencio.", "Suficiente.", "No insistas.", "Basta.", "…"]
CLOSE_EMOJIS = ["🕯️", "👁️", "✨"]

def style_by_mood(text: str, mood: Mood) -> str:
    base = clean_line(text)

    if mood == Mood.SILENCIO:
        return limit_sentences(base, 1)

    if mood == Mood.CLAUSURA:
        return "\n".join([
            as_action("Castariel repliega las alas."),
            limit_sentences(base, 1),
            random.choice(CLOSE_EMOJIS),
        ])

    if mood == Mood.ADVERTENCIA:
        out = limit_sentences(base, 1)
        if random.random() < 0.12:
            out += "\n" + as_action(random.choice(CLOSE_TAGS))
        return out

    if mood == Mood.EVALUANDO:
        if random.random() < 0.30:
            return as_action("Castariel observa.") + "\n" + limit_sentences(base, 1)
        return limit_sentences(base, 1)

    if mood == Mood.OBSERVANDO:
        if random.random() < 0.22:
            return as_action("Castariel inclina la cabeza.") + "\n" + limit_sentences(base, 1)
        return limit_sentences(base, 1)

    if mood == Mood.SERENO:
        return limit_sentences(base, 2)

    return base

async def delayed_send(channel: discord.abc.Messageable, text: str, mood: Mood):
    try:
        async with channel.typing():
            await asyncio.sleep(getattr(SETTINGS, "reply_delay_s", 0.8))
        await channel.send(style_by_mood(text, mood))
    except Exception as e:
        print("SEND ERROR:", repr(e))

# ============================================================
# CRÓNICA (soporta formato viejo y nuevo)
# ============================================================
QUESTION_TYPES = {
    "POR_QUE": {"porque", "porq", "porqué", "por que", "por qué", "razon", "razón", "motivo"},
    "CUANDO": {"cuando", "cuándo", "cuanto tiempo", "en cuanto", "fecha", "momento"},
    "DONDE": {"donde", "dónde", "lugar", "ubicacion", "ubicación"},
    "QUIEN": {"quien", "quién"},
    "QUE": {"que", "qué"},
}

def detect_question_type(text: str) -> str | None:
    t = strip_accents((text or "").lower())
    # checks simple contains (multiword first)
    if "por que" in t or "por qué" in t or "porqué" in t or "porque" in t:
        return "POR_QUE"
    if "cuando" in t or "cuándo" in t:
        return "CUANDO"
    if "donde" in t or "dónde" in t:
        return "DONDE"
    if re.search(r"\bquien\b|\bquién\b", t):
        return "QUIEN"
    if re.search(r"\bque\b|\bqué\b", t):
        return "QUE"
    return None

def _pick_from_list(lines: list) -> str | None:
    pool = [x for x in lines if isinstance(x, str) and x.strip()]
    return random.choice(pool) if pool else None

def pick_cronica_reply(text: str) -> str | None:
    """
    Nuevo formato (recomendado):
      cronica_mundana["lugares"]["Rajid"] = { "observaciones": [...], "porques": [...], ... }

    Formato viejo:
      cronica_mundana["lugares"]["Rajid"] = [ "...", "..." ]
    """
    try:
        cron = getattr(content, "cronica_mundana", None)
        if not isinstance(cron, dict):
            return None

        mt = tokens(text)
        qtype = detect_question_type(text)

        pools: list[str] = []

        for block in ("lugares", "eventos", "figuras"):
            sec = cron.get(block, {})
            if not isinstance(sec, dict):
                continue

            for name, payload in sec.items():
                nt = {w for w in tokens(name) if len(w) >= 3}
                if not (nt and len(nt & mt) >= 1):
                    continue

                # Formato viejo: lista plana
                if isinstance(payload, list):
                    picked = _pick_from_list(payload)
                    if picked:
                        pools.append(picked)
                    continue

                # Formato nuevo: dict por categorías
                if isinstance(payload, dict):
                    # elegir categoría por tipo de pregunta si existe
                    preferred_keys = []
                    if qtype == "POR_QUE":
                        preferred_keys = ["porques", "lectura", "juicio", "advertencias"]
                    elif qtype == "CUANDO":
                        preferred_keys = ["cuandos", "umbral", "condiciones"]
                    else:
                        preferred_keys = ["observaciones", "identidad", "conducta", "clima", "umbral", "seleccion", "custodia"]

                    for k in preferred_keys:
                        v = payload.get(k)
                        if isinstance(v, list):
                            picked = _pick_from_list(v)
                            if picked:
                                pools.append(picked)
                                break

                    # fallback: cualquier lista dentro
                    if not pools:
                        for v in payload.values():
                            if isinstance(v, list):
                                picked = _pick_from_list(v)
                                if picked:
                                    pools.append(picked)
                                    break

        return random.choice(pools) if pools else None
    except Exception as e:
        print("CRONICA ERROR:", repr(e))
        return None

# ============================================================
# DOGMA OPERACIONAL (nuevo, desde JSON en disco)
# ============================================================
dogma_operacional: dict | None = None
dogma_operacional_mtime: float = 0.0

def load_dogma_operacional(force: bool = False) -> dict | None:
    global dogma_operacional, dogma_operacional_mtime
    try:
        if not DOGMA_OPERACIONAL_PATH.exists():
            return None
        mtime = DOGMA_OPERACIONAL_PATH.stat().st_mtime
        if (not force) and dogma_operacional is not None and abs(mtime - dogma_operacional_mtime) < 0.001:
            return dogma_operacional
        with DOGMA_OPERACIONAL_PATH.open("r", encoding="utf-8") as f:
            dogma_operacional = json.load(f)
        dogma_operacional_mtime = mtime
        print("📜 Dogma operacional cargado:", str(DOGMA_OPERACIONAL_PATH))
        return dogma_operacional
    except Exception as e:
        print("DOGMA LOAD ERROR:", repr(e))
        return dogma_operacional

# Heurísticas de intención (baratas, suficientes)
KW_MIEDO = {"miedo", "temor", "asusta", "asustado", "asustada", "panico", "pánico", "ansiedad", "terror", "horror", "me da miedo", "tengo miedo"}
KW_AYUDA = {"ayuda", "ayudame", "ayúdame", "auxilio", "socorro", "necesito ayuda", "me ayudas", "me puede ayudar"}
KW_CONFESION = {"confieso", "confesion", "confesión", "perdon", "perdón", "culpa", "me equivoque", "me equivoqué", "hice", "he hecho", "no debi", "no debí"}
KW_BURLA = {"jaja", "jeje", "lol", "xd", "lmao", "ridiculo", "ridículo", "pendejo", "tonto", "payaso", "meme", "cállate", "callate"}
KW_CURIOSIDAD = {"por que", "por qué", "porque", "que es", "qué es", "como", "cómo", "cuando", "cuándo", "donde", "dónde", "quien", "quién", "explica", "explícame"}

def classify_situation(text: str, is_mentioned: bool, insist_count: int) -> str | None:
    t = strip_accents((text or "").lower())

    # Insistencia primero (si ya insiste)
    if insist_count >= 2:
        return "insistencia"

    # Burla
    if any(k in t for k in KW_BURLA):
        return "burla"

    # Miedo
    if any(k in t for k in KW_MIEDO):
        return "miedo"

    # Petición de ayuda
    if any(k in t for k in KW_AYUDA):
        return "peticion_de_ayuda"

    # Confesión
    if any(k in t for k in KW_CONFESION):
        return "confesion"

    # Curiosidad (solo si menciona o pregunta)
    if is_mentioned and any(k in t for k in KW_CURIOSIDAD):
        return "curiosidad"

    # Si lo mencionan y no hay crónica: default = curiosidad
    if is_mentioned:
        return "curiosidad"

    return None

def pick_from_operational(situation: str, subkey: str) -> str | None:
    data = load_dogma_operacional()
    if not isinstance(data, dict):
        return None
    sec = data.get(situation)
    if not isinstance(sec, dict):
        return None
    pool = sec.get(subkey)
    if not isinstance(pool, list):
        return None
    return _pick_from_list(pool)

def pick_operational_reply(situation: str, mood: Mood, insist_count: int) -> str | None:
    # SILENCIO: idealmente no texto; si situación es insistencia, devolver emoji/nada
    if mood == Mood.SILENCIO:
        if situation == "insistencia":
            return pick_from_operational("insistencia", "silencio") or "…"
        return None

    if situation == "insistencia":
        if insist_count <= 1:
            return pick_from_operational("insistencia", "primer_aviso")
        if insist_count == 2:
            return pick_from_operational("insistencia", "segundo_aviso")
        # 3 o más → clausura (y sube tensión)
        return pick_from_operational("insistencia", "clausura")

    if situation == "miedo":
        # mood alto → advertencias/cierres más probable
        if mood in (Mood.ADVERTENCIA, Mood.CLAUSURA):
            if random.random() < 0.55:
                return pick_from_operational("miedo", "advertencias") or pick_from_operational("miedo", "orientaciones")
            return pick_from_operational("miedo", "cierres") or pick_from_operational("miedo", "anclas")
        # normal → anclas/orientaciones
        if random.random() < 0.55:
            return pick_from_operational("miedo", "anclas") or pick_from_operational("miedo", "orientaciones")
        return pick_from_operational("miedo", "orientaciones") or pick_from_operational("miedo", "anclas")

    if situation == "burla":
        if mood in (Mood.ADVERTENCIA, Mood.CLAUSURA):
            return pick_from_operational("burla", "clausura") or pick_from_operational("burla", "advertencia")
        if random.random() < 0.65:
            return pick_from_operational("burla", "distancia") or pick_from_operational("burla", "advertencia")
        return pick_from_operational("burla", "advertencia") or pick_from_operational("burla", "distancia")

    if situation == "curiosidad":
        t = mood
        # Si mood tenso, tratar como mal formulada/umbral
        if t in (Mood.ADVERTENCIA, Mood.CLAUSURA):
            if random.random() < 0.6:
                return pick_from_operational("curiosidad", "mal_formulada") or pick_from_operational("curiosidad", "umbral")
            return pick_from_operational("curiosidad", "umbral") or pick_from_operational("curiosidad", "mal_formulada")
        # normal
        if random.random() < 0.7:
            return pick_from_operational("curiosidad", "bien_formulada") or pick_from_operational("curiosidad", "umbral")
        return pick_from_operational("curiosidad", "umbral") or pick_from_operational("curiosidad", "bien_formulada")

    if situation == "confesion":
        if mood in (Mood.ADVERTENCIA, Mood.CLAUSURA):
            if random.random() < 0.5:
                return pick_from_operational("confesion", "umbral") or pick_from_operational("confesion", "instruccion")
            return pick_from_operational("confesion", "instruccion") or pick_from_operational("confesion", "reconocimiento")
        if random.random() < 0.55:
            return pick_from_operational("confesion", "reconocimiento") or pick_from_operational("confesion", "instruccion")
        return pick_from_operational("confesion", "instruccion") or pick_from_operational("confesion", "reconocimiento")

    if situation == "peticion_de_ayuda":
        if mood in (Mood.ADVERTENCIA, Mood.CLAUSURA):
            if random.random() < 0.55:
                return pick_from_operational("peticion_de_ayuda", "limite") or pick_from_operational("peticion_de_ayuda", "condicion")
            return pick_from_operational("peticion_de_ayuda", "condicion") or pick_from_operational("peticion_de_ayuda", "criterio")
        if random.random() < 0.5:
            return pick_from_operational("peticion_de_ayuda", "criterio") or pick_from_operational("peticion_de_ayuda", "condicion")
        return pick_from_operational("peticion_de_ayuda", "condicion") or pick_from_operational("peticion_de_ayuda", "criterio")

    return None

# Estado para insistencia/cooldown dogma (por usuario/canal)
user_channel_insist: dict[tuple[int, int], dict] = {}
user_channel_dogma_cd: dict[tuple[int, int], float] = {}
user_channel_dogma_burst: dict[tuple[int, int], dict] = {}

def _insist_count(user_id: int, channel_id: int, is_mentioned: bool) -> int:
    """
    Cuenta insistencia cuando mencionan a Castariel repetidamente.
    """
    if not is_mentioned:
        return 0
    key = (user_id, channel_id)
    now = _now_ts()
    st = user_channel_insist.get(key)
    if st is None:
        user_channel_insist[key] = {"first": now, "last": now, "count": 1}
        return 1

    # reset si pasó mucho
    if now - st["last"] > INSIST_RESET_S:
        st["first"] = now
        st["last"] = now
        st["count"] = 1
        return 1

    st["last"] = now
    # cuenta dentro de ventana
    if now - st["first"] <= INSIST_WINDOW_S:
        st["count"] += 1
    else:
        st["first"] = now
        st["count"] = 1
    return int(st["count"])

def _dogma_can_reply(user_id: int, channel_id: int) -> bool:
    """
    Cooldown + máximo 3 respuestas rápidas por usuario/canal.
    """
    key = (user_id, channel_id)
    now = _now_ts()

    # cooldown duro
    cd = user_channel_dogma_cd.get(key, 0.0)
    if now < cd:
        return False

    # burst control (máx 3 respuestas)
    burst = user_channel_dogma_burst.get(key)
    if burst is None:
        user_channel_dogma_burst[key] = {"first": now, "count": 0}
        burst = user_channel_dogma_burst[key]

    # reset burst si pasa ventana
    if now - burst["first"] > INSIST_WINDOW_S:
        burst["first"] = now
        burst["count"] = 0

    if burst["count"] >= MAX_DOGMA_REPLIES_BEFORE_COOLDOWN:
        user_channel_dogma_cd[key] = now + DOGMA_COOLDOWN_S
        burst["count"] = 0
        burst["first"] = now
        return False

    return True

def _dogma_mark_replied(user_id: int, channel_id: int):
    key = (user_id, channel_id)
    now = _now_ts()
    burst = user_channel_dogma_burst.get(key)
    if burst is None:
        user_channel_dogma_burst[key] = {"first": now, "count": 1}
    else:
        burst["count"] += 1

# ============================================================
# OFFROL: REACCIONES + “SI QUEDA EN SILENCIO 60 MIN”
# ============================================================

PRAISE_EMOJIS = ["🙏", "✨", "🕯️", "🪽", "👁️", "📜", "🌙", "⭐", "🔥", "👑", "🤍"]

OFFROL_REACTION_COOLDOWN_S = 180
OFFROL_IDLE_NUDGE_AFTER_S = 60 * 60
OFFROL_NUDGE_GLOBAL_COOLDOWN_S = 2 * 60 * 60

offrol_last_activity_ts: dict[int, float] = {}
offrol_last_reaction_ts: dict[int, float] = {}
offrol_last_nudge_ts_global: float = 0.0
offrol_last_nudged_for_activity: dict[int, float] = {}

def _choose_reaction_emojis(mood: Mood) -> list[str]:
    if mood == Mood.SILENCIO:
        return [random.choice(["👁️", "🕯️"])]

    if mood == Mood.CLAUSURA:
        return [random.choice(["🕯️", "👁️", "📜"])]

    one = random.choice(PRAISE_EMOJIS)
    if random.random() < 0.20:
        two = random.choice([e for e in PRAISE_EMOJIS if e != one] or PRAISE_EMOJIS)
        return [one, two]
    return [one]

def _pick_offrol_nudge_line() -> str:
    pool = None
    try:
        pool = getattr(content, "elogios_offrol", None)
    except Exception:
        pool = None

    if isinstance(pool, list) and pool:
        lines = [x for x in pool if isinstance(x, str) and x.strip()]
        if lines:
            return random.choice(lines)

    for attr in ("parabolas", "cierres"):
        try:
            p = getattr(content, attr, None)
            if isinstance(p, list) and p:
                lines = [x for x in p if isinstance(x, str) and x.strip()]
                if lines:
                    return limit_sentences(random.choice(lines), 1)
        except Exception:
            pass

    fallback = [
        "Que no se apague la mano que escribe.",
        "Lo dicho queda en pie. Prosigue.",
        "Bien. No lo abandones.",
        "Se te ha visto. Continúa.",
        "Mantén el pulso. No cedas.",
    ]
    return random.choice(fallback)

async def offrol_watchdog_loop():
    global offrol_last_nudge_ts_global

    await client.wait_until_ready()

    while not client.is_closed():
        try:
            await asyncio.sleep(30)

            if not is_active_now():
                continue

            refresh_daily_mood()
            decay_tension()
            eff = FORCE_MOOD if FORCE_MOOD is not None else effective_mood(current_mood)

            if eff == Mood.SILENCIO:
                continue

            now = _now_ts()
            if now - offrol_last_nudge_ts_global < OFFROL_NUDGE_GLOBAL_COOLDOWN_S:
                continue

            for ch_id, last_ts in list(offrol_last_activity_ts.items()):
                idle = now - last_ts
                if idle < OFFROL_IDLE_NUDGE_AFTER_S:
                    continue

                already_for = offrol_last_nudged_for_activity.get(ch_id)
                if already_for is not None and abs(already_for - last_ts) < 1.0:
                    continue

                ch = client.get_channel(ch_id)
                if not isinstance(ch, discord.TextChannel):
                    continue

                if (ch.name or "").strip().lower() != OFFROL_CHANNEL_NAME.lower():
                    continue

                line = _pick_offrol_nudge_line()
                await delayed_send(ch, line, eff)

                offrol_last_nudge_ts_global = now
                offrol_last_nudged_for_activity[ch_id] = last_ts
                break

        except Exception as e:
            print("OFFROL WATCHDOG ERROR:", repr(e))

# ============================================================
# PUPPET / TITIRITERO + COMANDOS DE DUEÑO
# ============================================================
def is_owner(user_id: int) -> bool:
    try:
        return int(getattr(SETTINGS, "owner_id", 0)) == int(user_id)
    except Exception:
        return False

def puppet_ok(passwd: str) -> bool:
    try:
        return (passwd or "").strip() == (getattr(SETTINGS, "puppet_pass", "") or "").strip()
    except Exception:
        return False

def parse_prefixed_quoted(rest: str, prefix: str) -> tuple[str | None, str]:
    r = rest.lstrip()
    if not r.startswith(prefix):
        return None, rest

    r2 = r[len(prefix):].lstrip()
    if not r2:
        return None, rest

    if r2[0] in ('"', "'"):
        q = r2[0]
        end = r2.find(q, 1)
        if end == -1:
            return None, rest
        value = r2[1:end]
        new_rest = r2[end+1:].lstrip()
        return value, new_rest

    m = re.match(r"([^\s]+)\s*(.*)$", r2)
    if not m:
        return None, rest
    return m.group(1), m.group(2).lstrip()

def parse_channel_token(rest: str) -> tuple[str | None, int | None, str]:
    r = rest.lstrip()
    if not r:
        return None, None, rest

    if r.startswith("<#"):
        m = re.match(r"<#(\d+)>\s*(.*)$", r)
        if m:
            return None, int(m.group(1)), m.group(2).lstrip()

    if r.startswith("#"):
        name, new_rest = parse_prefixed_quoted(r, "#")
        if name:
            return name, None, new_rest

    return None, None, rest

def parse_csay(text: str) -> tuple[str | None, int | None, str | None, int | None, str | None]:
    t = (text or "").strip()
    if not t.lower().startswith("!csay"):
        return (None, None, None, None, None)

    rest = t[5:].lstrip()
    parts = rest.split(maxsplit=1)
    if len(parts) < 2:
        return (None, None, None, None, None)

    passwd = parts[0]
    rest = parts[1].lstrip()

    guild_token, rest = parse_prefixed_quoted(rest, "@")
    guild_id = None
    if guild_token and guild_token.isdigit():
        guild_id = int(guild_token)

    chan_name, chan_id, rest = parse_channel_token(rest)
    msg = rest.strip()

    return (passwd, guild_id, chan_name, chan_id, msg)

def parse_owner_simple(text: str) -> Tuple[Optional[str], Optional[str]]:
    t = (text or "").strip()
    if not t.startswith("!"):
        return None, None

    parts = t.split()
    cmd = parts[0].lower()

    if cmd not in ("!wake", "!sleep", "!cstatus"):
        return None, None

    if len(parts) < 2:
        return cmd, None

    passwd = parts[1]
    extra = " ".join(parts[2:]).strip() if len(parts) > 2 else ""
    return cmd, (passwd + (" " + extra if extra else ""))

def get_guild_by_id(guild_id: int) -> discord.Guild | None:
    try:
        return client.get_guild(int(guild_id))
    except Exception:
        return None

def find_text_channel_in_guild(guild: discord.Guild, channel_name: str) -> discord.TextChannel | None:
    target = (channel_name or "").strip().lower()
    for ch in guild.text_channels:
        if (ch.name or "").strip().lower() == target:
            return ch
    return None

async def puppet_send_to_target(guild_id: int | None, channel_name: str | None, channel_id: int | None, msg: str, mood: Mood) -> bool:
    gid = int(guild_id) if guild_id else int(DEFAULT_GUILD_ID)
    guild = get_guild_by_id(gid)
    if not guild:
        print("PUPPET: No encontré guild id:", gid)
        return False

    ch = None
    if channel_id:
        ch = guild.get_channel(channel_id)

    if ch is None:
        cname = (channel_name or DEFAULT_CHANNEL_NAME).strip()
        ch = find_text_channel_in_guild(guild, cname)

    if not isinstance(ch, discord.TextChannel):
        print("PUPPET: No encontré canal. name/id:", channel_name, channel_id)
        return False

    await delayed_send(ch, msg, mood)
    return True

# ============================================================
# EVENTOS DISCORD
# ============================================================
@client.event
async def on_ready():
    refresh_daily_mood()
    load_dogma_operacional(force=True)
    print(f"🔥 CASTERIEL HA DESPERTADO 🔥 {client.user}")
    print("GUILDS:", [(g.name, g.id) for g in client.guilds])
    if manual_awake_active():
        print("🟢 OVERRIDE MANUAL ACTIVO (WAKE).")

    try:
        asyncio.create_task(offrol_watchdog_loop())
    except Exception as e:
        print("WATCHDOG START ERROR:", repr(e))

@client.event
async def on_message(message: discord.Message):
    global tension_global

    if message.author.bot or not message.content:
        return

    txt = message.content.strip()

    # ----------------------------------------------------------
    # 0) COMANDOS DE DUEÑO (funcionan incluso si está fuera de horario)
    # ----------------------------------------------------------
    cmd, payload = parse_owner_simple(txt)
    if cmd is not None:
        if not is_owner(message.author.id):
            return
        if payload is None:
            return

        parts = payload.split(maxsplit=1)
        passwd = parts[0]
        extra = parts[1].strip() if len(parts) > 1 else ""

        if not puppet_ok(passwd):
            return

        if cmd == "!wake":
            minutes = None
            if extra and extra.isdigit():
                minutes = int(extra)
            set_manual_awake(True, minutes=minutes)
            try:
                if minutes:
                    await message.channel.send(f"🕯️ Castariel permanece despierto ({minutes} min).")
                else:
                    await message.channel.send("🕯️ Castariel permanece despierto (sin expiración).")
            except Exception:
                pass
            return

        if cmd == "!sleep":
            set_manual_awake(False)
            try:
                await message.channel.send("🕯️ Castariel vuelve al horario.")
            except Exception:
                pass
            return

        if cmd == "!cstatus":
            refresh_daily_mood()
            decay_tension()
            eff = FORCE_MOOD if FORCE_MOOD is not None else effective_mood(current_mood)

            active = is_active_now()
            override = manual_awake_active()

            until_txt = "∞"
            if MANUAL_AWAKE_UNTIL is not None:
                try:
                    until_txt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(MANUAL_AWAKE_UNTIL))
                except Exception:
                    until_txt = str(MANUAL_AWAKE_UNTIL)

            msg = [
                f"🕯️ **Estado de Castariel**",
                f"- Activo ahora (horario/override): **{active}**",
                f"- Override manual (wake): **{override}**" + (f" (hasta {until_txt})" if override else ""),
                f"- Mood del día: **{mood_label(current_mood)}**",
                f"- Mood efectivo: **{mood_label(eff)}**",
                f"- Tensión global: **{tension_global}/10**",
                f"- Hora local: **{now_local().strftime('%Y-%m-%d %H:%M:%S')}**",
            ]
            try:
                await message.channel.send("\n".join(msg))
            except Exception:
                pass
            return

    # ----------------------------------------------------------
    # 1) PUPPET (funciona incluso si está fuera de horario)
    # ----------------------------------------------------------
    refresh_daily_mood()
    decay_tension()
    eff = FORCE_MOOD if FORCE_MOOD is not None else effective_mood(current_mood)

    passwd, guild_id, chan_name, chan_id, puppet_msg = parse_csay(txt)
    if passwd is not None:
        if not is_owner(message.author.id):
            return
        if not puppet_ok(passwd):
            return
        if not puppet_msg:
            return

        if message.guild is None:
            ok = await puppet_send_to_target(guild_id, chan_name, chan_id, puppet_msg, eff)
            if ok:
                try:
                    await message.channel.send("🕯️ Concedido.")
                except Exception:
                    pass
            return

        target_channel = None
        if message.guild:
            if chan_id:
                target_channel = message.guild.get_channel(chan_id)
            if target_channel is None and chan_name:
                target_channel = find_text_channel_in_guild(message.guild, chan_name)

        if target_channel is None:
            target_channel = message.channel

        try:
            await message.delete()
        except Exception:
            pass

        await delayed_send(target_channel, puppet_msg, eff)
        return

    # ----------------------------------------------------------
    # 2) OFFROL: registra actividad SIEMPRE (aunque fuera de horario)
    #    y reacciona SOLO si está activo (horario/override)
    # ----------------------------------------------------------
    channel_name = getattr(message.channel, "name", "") or ""
    is_offrol = (channel_name.strip().lower() == OFFROL_CHANNEL_NAME.lower())

    if is_offrol and isinstance(message.channel, discord.TextChannel):
        offrol_last_activity_ts[message.channel.id] = _now_ts()

        if is_active_now():
            now = _now_ts()
            last_r = offrol_last_reaction_ts.get(message.channel.id, 0.0)
            if now - last_r >= OFFROL_REACTION_COOLDOWN_S:
                try:
                    emojis = _choose_reaction_emojis(eff)
                    for em in emojis:
                        await message.add_reaction(em)
                    offrol_last_reaction_ts[message.channel.id] = now
                except Exception as e:
                    print("OFFROL REACTION ERROR:", repr(e))

    # ----------------------------------------------------------
    # 3) GATE DE HORARIO PARA “vida normal”
    # ----------------------------------------------------------
    if not is_active_now():
        return

    # ----------------------------------------------------------
    # 4) NORMAL (crónica + dogma operacional)
    # ----------------------------------------------------------
    is_mentioned = client.user in message.mentions if client.user else False

    # insistencia solo cuenta si lo mencionan
    ch_id = message.channel.id if hasattr(message.channel, "id") else 0
    insist_count = _insist_count(message.author.id, ch_id, is_mentioned)

    if is_mentioned:
        # presión sube tensión
        bump_tension(+1)
        eff = FORCE_MOOD if FORCE_MOOD is not None else effective_mood(current_mood)

    # 4A) intenta crónica primero (si hay entidad)
    cron_line = pick_cronica_reply(txt)
    if cron_line and (is_mentioned or is_offrol):
        if eff == Mood.SILENCIO:
            return
        await delayed_send(message.channel, cron_line, eff)
        return

    # 4B) dogma operacional (solo si lo mencionan o si ya hay insistencia alta)
    situation = classify_situation(txt, is_mentioned=is_mentioned, insist_count=insist_count)
    if situation is None:
        return

    # Si no lo mencionaron y no es insistencia, no respondemos (mantiene distancia)
    if (not is_mentioned) and situation != "insistencia":
        return

    # Control anti-spam dogma
    if not _dogma_can_reply(message.author.id, ch_id):
        return

    # Escalado: insistencia fuerte sube tensión adicional
    if situation == "insistencia" and insist_count >= 3:
        bump_tension(+2)
        eff = FORCE_MOOD if FORCE_MOOD is not None else effective_mood(current_mood)

    if situation in ("burla",):
        bump_tension(+1)
        eff = FORCE_MOOD if FORCE_MOOD is not None else effective_mood(current_mood)

    # SILENCIO: en dogma preferimos no hablar
    reply = pick_operational_reply(situation, eff, insist_count=insist_count)
    if not reply:
        return

    _dogma_mark_replied(message.author.id, ch_id)

    await delayed_send(message.channel, reply, eff)
    return

def main():
    client.run(SETTINGS.discord_token)

if __name__ == "__main__":
    main()
