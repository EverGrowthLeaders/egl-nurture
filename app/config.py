"""Configuración leída desde variables de entorno (.env o Dokploy → Environment)."""

from functools import lru_cache

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

    # Seguridad / sesiones (firma la cookie de login y hashea IPs).
    secret_key: str = "dev-secret-change-me"

    # Bootstrap opcional de la primera cuenta al arrancar (cómodo en Dokploy).
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_tenant_name: str = "EGL"

    # Idiomas preferidos para la transcripción, en orden.
    transcript_langs: str = "es,en"

    # yt-dlp: en servidores (IP de datacenter) YouTube pide "no soy un bot".
    # Ruta a un cookies.txt de YouTube montado en el contenedor.
    ytdlp_cookiefile: str = ""
    # Clientes de player a probar (coma-separado), p.ej. "android,web,tv". Vacío = default.
    ytdlp_player_client: str = ""

    # Nota: el setter por defecto y la plantilla de mensaje ahora son POR TENANT
    # (se editan en Settings). DEFAULT_MESSAGE_TEMPLATE es solo el valor inicial.

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
