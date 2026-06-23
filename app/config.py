"""Configuración leída desde variables de entorno (.env o Dokploy → Environment)."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MESSAGE_TEMPLATE = (
    'Por lo que has hablado con "{setter}" y lo que has rellenado te paso '
    "este vídeo, que es muy importante que veas antes de la llamada, te va a "
    "ayudar a entender todo mejor: {link}"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base de datos. Por defecto SQLite para desarrollo local; en producción
    # docker-compose la sobreescribe con la URL de Postgres.
    database_url: str = "sqlite:///./data/library.db"

    # DeepInfra / DeepSeek
    deepinfra_api_key: str = ""
    deepinfra_model: str = "deepseek-ai/DeepSeek-V4-Flash"
    deepinfra_base_url: str = "https://api.deepinfra.com/v1/openai"
    request_timeout: int = 90

    # URL pública usada para construir los links trackeados (/r/<token>).
    base_url: str = "http://localhost:8000"

    # Seguridad
    secret_key: str = "dev-secret-change-me"
    admin_token: str = ""

    # Idiomas preferidos para la transcripción, en orden.
    transcript_langs: str = "es,en"

    # ── Mensaje al lead ──────────────────────────────────────────────
    # Plantilla del mensaje. Placeholders disponibles: {setter} {link}
    # {contact_name} {pain}. {link} se rellena con el link trackeado (o la
    # URL directa de YouTube si tracked_links_in_message=False).
    message_template: str = DEFAULT_MESSAGE_TEMPLATE
    # Nombre del setter/closer por defecto (se puede sobreescribir por lead).
    default_setter: str = ""
    # True: el mensaje lleva /r/<token> (con tracking). False: la URL de YouTube directa.
    tracked_links_in_message: bool = True

    @field_validator("message_template")
    @classmethod
    def _fallback_template(cls, v: str) -> str:
        # Si el entorno pasa un valor vacío (p.ej. ${MESSAGE_TEMPLATE:-}), usa el default.
        return v if (v and v.strip()) else DEFAULT_MESSAGE_TEMPLATE

    @property
    def langs(self) -> list[str]:
        return [c.strip() for c in self.transcript_langs.split(",") if c.strip()]

    @property
    def llm_enabled(self) -> bool:
        """True si hay API key; si no, la app funciona en modo demo (mock)."""
        return bool(self.deepinfra_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
