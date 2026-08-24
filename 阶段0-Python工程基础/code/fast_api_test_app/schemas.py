from pydantic import BaseModel, ConfigDict, Field


class TaskResponse(BaseModel):
    id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    completed: bool

    model_config = ConfigDict(str_strip_whitespace=True)



class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    completed: bool = False

    model_config = ConfigDict(str_strip_whitespace=True)

