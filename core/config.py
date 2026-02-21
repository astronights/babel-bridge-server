from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongodb_uri: str
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 10080  # 7 days
    google_api_key: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
