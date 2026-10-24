from pydantic import BaseModel, Field


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class Register(Credentials):
    confirm_password: str


class ProgressUpdate(BaseModel):
    write_session: str = Field(min_length=32, max_length=32)
    sequence: int = Field(ge=1, le=2_000_000_000)
    position_seconds: float = Field(ge=0, allow_inf_nan=False)
