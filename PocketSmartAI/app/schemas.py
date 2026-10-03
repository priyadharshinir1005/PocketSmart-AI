from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PlannerType = Literal["home", "party", "jewelry"]


class APIModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", allow_inf_nan=False)


class RegisterRequest(APIModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email_shape(cls, value: str) -> str:
        if value.count("@") != 1 or "." not in value.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address.")
        return value.lower()


class LoginRequest(APIModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RoomItemRequest(APIModel):
    name: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=100)


class RoomRequest(APIModel):
    name: str = Field(min_length=1, max_length=60)
    items: list[RoomItemRequest] = Field(min_length=1, max_length=12)


class HomePlannerRequest(APIModel):
    budget: float = Field(ge=100, le=10_000_000)
    city: str = Field(default="", max_length=100)
    style: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=1200)
    rooms: list[RoomRequest] = Field(min_length=1, max_length=8)


class PartyPlannerRequest(APIModel):
    budget: float = Field(ge=100, le=10_000_000)
    guests: int = Field(ge=1, le=5000)
    event_type: str = Field(min_length=2, max_length=80)
    city: str = Field(default="", max_length=100)
    venue_preference: str = Field(default="", max_length=100)
    dietary_needs: str = Field(default="", max_length=400)
    priorities: str = Field(default="", max_length=700)


class JewelryPlannerRequest(APIModel):
    budget: float = Field(ge=100, le=10_000_000)
    occasion: str = Field(min_length=2, max_length=100)
    style: str = Field(min_length=2, max_length=100)
    outfit_description: str = Field(default="", max_length=800)


class Allocation(APIModel):
    category: str = Field(min_length=1, max_length=80)
    amount: float = Field(ge=0)
    rationale: str = Field(default="", max_length=240)


class RecommendedItem(APIModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=400)
    estimated_unit_price: float = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=100)
    platforms: list[str] = Field(default_factory=list, max_length=5)


class RecommendationDraft(APIModel):
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=800)
    budget_breakdown: list[Allocation] = Field(default_factory=list, max_length=12)
    recommendations: list[RecommendedItem] = Field(default_factory=list, max_length=20)
    savings_tips: list[str] = Field(default_factory=list, max_length=8)
    style_notes: list[str] = Field(default_factory=list, max_length=8)
    image_observation: str | None = Field(default=None, max_length=400)
