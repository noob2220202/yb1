from typing import Literal

from pydantic import BaseModel, Field, model_validator

ComboType = Literal["draw_dnb0", "draw_ah05", "draw_ah15", "ahplus1_margin1", "ahplus2_margin2"]


class EqualizeRequest(BaseModel):
    combo_type: ComboType
    odds_a: float = Field(..., gt=1.0, description="다리 A 오즈")
    odds_b: float = Field(..., gt=1.0, description="다리 B 오즈")
    target_profit: float | None = Field(None, gt=0)
    total_stake: float | None = Field(None, gt=0)

    @model_validator(mode="after")
    def _one_of_target(self) -> "EqualizeRequest":
        if self.target_profit is None and self.total_stake is None:
            raise ValueError("target_profit 또는 total_stake 중 하나는 필요합니다")
        return self
