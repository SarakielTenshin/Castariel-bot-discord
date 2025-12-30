import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _must(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Falta {name} en .env")
    return val

@dataclass(frozen=True)
class Settings:
    # Discord
    discord_token: str = _must("DISCORD_TOKEN")

    # Owner / control secreto
    owner_id: int = int(_must("OWNER_ID"))  # tu user id de Discord
    puppet_pass: str = _must("PUPPET_PASS") # contraseña/frase secreta

    # Canal objetivo para “lunes silencioso”
    general_channel_name: str = os.getenv("GENERAL_CHANNEL_NAME", "chat-general")

    # Horario (CDMX)
    tz_name: str = os.getenv("TZ_NAME", "America/Mexico_City")

    # Actividad
    active_start_h: int = int(os.getenv("ACTIVE_START_H", "10"))
    active_start_m: int = int(os.getenv("ACTIVE_START_M", "0"))
    active_end_h: int = int(os.getenv("ACTIVE_END_H", "18"))
    active_end_m: int = int(os.getenv("ACTIVE_END_M", "0"))

    # Ritmo
    reaction_delay_s: int = int(os.getenv("REACTION_DELAY_S", "3"))
    reply_delay_s: int = int(os.getenv("REPLY_DELAY_S", "10"))

    # “Dados”
    reaction_dice_lo: int = int(os.getenv("REACTION_DICE_LO", "1"))
    reaction_dice_hi: int = int(os.getenv("REACTION_DICE_HI", "2"))
    random_reply_dice_lo: int = int(os.getenv("RANDOM_REPLY_DICE_LO", "1"))
    random_reply_dice_hi: int = int(os.getenv("RANDOM_REPLY_DICE_HI", "2"))

    # Cooldowns
    channel_reply_cooldown_s: int = int(os.getenv("CHANNEL_REPLY_COOLDOWN_S", "25"))
    mention_interactions_limit: int = int(os.getenv("MENTION_INTERACTIONS_LIMIT", "3"))
    mention_session_window_s: int = int(os.getenv("MENTION_SESSION_WINDOW_S", "900"))  # 15 min
    mention_rest_cooldown_s: int = int(os.getenv("MENTION_REST_COOLDOWN_S", "1200"))   # 20 min

    # Lunes mediodía: si nadie habló, habla
    monday_noon_hour: int = int(os.getenv("MONDAY_NOON_H", "12"))
    monday_noon_min: int = int(os.getenv("MONDAY_NOON_M", "0"))
    monday_quiet_check_window_s: int = int(os.getenv("MONDAY_QUIET_WINDOW_S", "7200")) # 2 horas (10->12)

SETTINGS = Settings()