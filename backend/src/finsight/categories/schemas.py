from pydantic import BaseModel, ConfigDict


class CategoryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    household_id: int | None
