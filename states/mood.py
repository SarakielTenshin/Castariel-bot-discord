from enum import Enum
import random

class Mood(Enum):
    SERENO = 1
    OBSERVANDO = 2
    EVALUANDO = 3
    ADVERTENCIA = 4
    CLAUSURA = 5
    SILENCIO = 6

def roll_mood_1d6() -> Mood:
    return Mood(random.randint(1, 6))

def mood_label(m: Mood) -> str:
    return {
        Mood.SERENO: "SERENO",
        Mood.OBSERVANDO: "OBSERVANDO",
        Mood.EVALUANDO: "EVALUANDO",
        Mood.ADVERTENCIA: "ADVERTENCIA",
        Mood.CLAUSURA: "CLAUSURA",
        Mood.SILENCIO: "SILENCIO",
    }[m]

# Respuestas cortas de saludo según mood (acción en cursiva, voz normal)
SALUDOS_POR_MOOD: dict[Mood, list[str]] = {
    Mood.SERENO: [
        "*Castariel inclina el rostro.*\nLa calma persiste.",
        "*Las alas permanecen inmóviles.*\nEl saludo fue registrado."
    ],
    Mood.OBSERVANDO: [
        "*Castariel observa en silencio.*",
        "*Una mirada basta.*"
    ],
    Mood.EVALUANDO: [
        "Habla. Estoy escuchando.",
        "Continúa."
    ],
    Mood.ADVERTENCIA: [
        "El tono importa.",
        "Mide tus palabras."
    ],
    Mood.CLAUSURA: [
        "*Castariel no responde.*"
    ],
    Mood.SILENCIO: []
}