from app.plugins.fields import PluginField
from pydantic import BaseModel, ConfigDict


class Config(BaseModel):
    model_config = ConfigDict(extra="allow")

    hello: str = PluginField(default="world", description="问候词")
