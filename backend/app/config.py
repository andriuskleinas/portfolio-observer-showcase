from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="PT_", extra="ignore")

    base_currency: str = "USD"
    data_dir: Path = ROOT / "data"
    database_url: str | None = None
    fx_provider_url: str = "https://api.frankfurter.dev/v1"
    ibkr_flex_token: str | None = None
    ibkr_flex_query_id: str | None = None

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir / 'portfolio.db'}"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"


settings = Settings()
