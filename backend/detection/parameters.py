from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


CUSTOMER_TYPES = ("BIREYSEL", "KURUMSAL")
ParameterStatus = Literal["UNSET", "PROVISIONAL", "APPROVED"]


class RuleParameterValues(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleParameterSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ParameterStatus
    values: dict[str, Any]


class CurrencyLimits(RuleParameterValues):
    limits: dict[str, Decimal]

    @field_validator("limits", mode="before")
    @classmethod
    def reject_boolean_limits(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(
            isinstance(limit, bool) for limit in value.values()
        ):
            raise ValueError("Currency limits must be numeric amounts.")
        return value

    @field_validator("limits")
    @classmethod
    def validate_limits(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        if not value:
            raise ValueError("At least one currency limit is required.")
        for currency, limit in value.items():
            if (
                len(currency) != 3
                or not currency.isascii()
                or not currency.isalpha()
                or currency != currency.upper()
                or not limit.is_finite()
                or limit <= 0
            ):
                raise ValueError("Currency limits must use uppercase ISO codes and positive amounts.")
        return value


class CountScoreParameters(RuleParameterValues):
    x_esik: Decimal = Field(ge=0)
    x_kesin: Decimal = Field(gt=0)

    @field_validator("x_esik", "x_kesin", mode="before")
    @classmethod
    def reject_boolean_counts(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Count thresholds must be integers.")
        return value

    @field_validator("x_esik", "x_kesin")
    @classmethod
    def validate_integer_counts(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError("Count thresholds must be finite integers.")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> "CountScoreParameters":
        if self.x_kesin <= self.x_esik:
            raise ValueError("x_kesin must be greater than x_esik.")
        return self


class R01Values(CurrencyLimits, CountScoreParameters):
    minimum_income_ratio: Decimal = Field(gt=0)
    income_currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("minimum_income_ratio", mode="before")
    @classmethod
    def reject_boolean_ratio(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Income ratio must be numeric.")
        return value


class R02Values(CurrencyLimits):
    pass


class R03Values(CurrencyLimits, CountScoreParameters):
    cash_channels: list[Literal["atm", "mobile", "internet", "branch"]]

    @field_validator("cash_channels")
    @classmethod
    def validate_channels(
        cls, value: list[str]
    ) -> list[str]:
        if not value or len(value) != len(set(value)):
            raise ValueError("At least one unique cash channel is required.")
        return value


def validate_rule_parameters(
    rule_code: str,
    values_model: type[RuleParameterValues],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(thresholds, dict) or set(thresholds) != set(CUSTOMER_TYPES):
        raise ValueError("Thresholds must define BIREYSEL and KURUMSAL parameter sets.")

    normalized: dict[str, Any] = {}
    for customer_type in CUSTOMER_TYPES:
        try:
            parameter_set = RuleParameterSet.model_validate(thresholds[customer_type])
            if parameter_set.status == "UNSET":
                if parameter_set.values:
                    raise ValueError("UNSET parameter sets must have empty values.")
                normalized[customer_type] = {
                    "status": "UNSET",
                    "values": {},
                }
                continue
            typed_values = values_model.model_validate(parameter_set.values)
            normalized[customer_type] = {
                "status": parameter_set.status,
                "values": typed_values.model_dump(mode="json"),
            }
        except (ValidationError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid {customer_type} parameters for {rule_code}: {exc}"
            ) from exc
    return normalized


def parameter_set_for(
    thresholds: dict[str, Any], customer_type: str
) -> dict[str, Any] | None:
    if customer_type not in CUSTOMER_TYPES:
        return None
    return thresholds[customer_type]
