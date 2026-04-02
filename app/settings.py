from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)



def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().casefold()
    return normalized in {"1", "true", "yes", "on", "y"}


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8080"))
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "15"))
    playlist_timeout_seconds: int = int(os.getenv("PLAYLIST_TIMEOUT_SECONDS", "10"))
    state_file: Path = Path(os.getenv("STATE_FILE", str(DATA_DIR / "state.json")))
    config_file: Path = Path(os.getenv("CONFIG_FILE", str(DATA_DIR / "config.json")))
    config_backup_dir: Path = Path(os.getenv("CONFIG_BACKUP_DIR", str(BACKUP_DIR)))
    config_backup_keep: int = int(os.getenv("CONFIG_BACKUP_KEEP", "25"))
    app_name: str = os.getenv("APP_NAME", "onradio-cover-bridge")
    app_version: str = os.getenv("APP_VERSION", "1.0.0")
    app_contact: str = os.getenv("APP_CONTACT", "")
    amazon_cover_enabled: bool = _env_flag("AMAZON_COVER_ENABLED", True)
    amazon_cover_marketplace: str = os.getenv("AMAZON_COVER_MARKETPLACE", "www.amazon.de").strip() or "www.amazon.de"
    amazon_cover_timeout_seconds: int = int(os.getenv("AMAZON_COVER_TIMEOUT_SECONDS", "10"))
    amazon_musicbrainz_fallback_enabled: bool = _env_flag("MUSICBRAINZ_FALLBACK_ENABLED", True)
    weather_enabled: bool = _env_flag("WEATHER_ENABLED", True)
    weather_location_name: str = os.getenv("WEATHER_LOCATION_NAME", "Falkensee").strip() or "Falkensee"
    weather_country_code: str = os.getenv("WEATHER_COUNTRY_CODE", "DE").strip().upper() or "DE"
    weather_timezone: str = os.getenv("WEATHER_TIMEZONE", "Europe/Berlin").strip() or "Europe/Berlin"
    weather_cache_seconds: int = int(os.getenv("WEATHER_CACHE_SECONDS", "1800"))
    weather_timeout_seconds: int = int(os.getenv("WEATHER_TIMEOUT_SECONDS", "10"))
    display_power_button_enabled: bool = _env_flag("DISPLAY_POWER_BUTTON_ENABLED", True)
    display_local_audio_button_enabled: bool = _env_flag("DISPLAY_LOCAL_AUDIO_BUTTON_ENABLED", True)
    display_controller_qr_enabled: bool = _env_flag("DISPLAY_CONTROLLER_QR_ENABLED", True)
    power_button_local_only: bool = _env_flag("POWER_BUTTON_LOCAL_ONLY", True)
    poweroff_delay_seconds: int = int(os.getenv("POWEROFF_DELAY_SECONDS", "2"))
    controller_url_override: str = os.getenv("CONTROLLER_URL_OVERRIDE", "").strip()
    controller_public_host: str = os.getenv("CONTROLLER_PUBLIC_HOST", "").strip()
    controller_url_scheme: str = os.getenv("CONTROLLER_URL_SCHEME", "http").strip() or "http"
    update_source_zip_url: str = os.getenv("UPDATE_SOURCE_ZIP_URL", "").strip()
    update_git_branch: str = os.getenv("UPDATE_GIT_BRANCH", "main").strip() or "main"
    selftest_timeout_seconds: int = int(os.getenv("SELFTEST_TIMEOUT_SECONDS", "15"))
    upnp_discovery_cache_seconds: int = int(os.getenv("UPNP_DISCOVERY_CACHE_SECONDS", "120"))
    upnp_request_timeout_seconds: int = int(os.getenv("UPNP_REQUEST_TIMEOUT_SECONDS", "6"))

    @property
    def user_agent(self) -> str:
        contact = self.app_contact.strip() or "local-use"
        return f"{self.app_name}/{self.app_version} ({contact})"


settings = Settings()
