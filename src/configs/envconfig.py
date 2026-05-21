from pydantic_settings import BaseSettings, SettingsConfigDict

class EnvConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    DATA_ABS_PATH: str

env_settings = EnvConfig()