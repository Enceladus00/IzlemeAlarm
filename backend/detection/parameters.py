from decimal import Decimal
from datetime import date
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
            raise ValueError("Score thresholds must be numeric.")
        return value

    @field_validator("x_esik", "x_kesin")
    @classmethod
    def validate_finite_counts(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Score thresholds must be finite.")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> "CountScoreParameters":
        if self.x_kesin <= self.x_esik:
            raise ValueError("x_kesin must be greater than x_esik.")
        return self


class IntegerCountScoreParameters(CountScoreParameters):
    @field_validator("x_esik", "x_kesin")
    @classmethod
    def validate_integer_counts(cls, value: Decimal) -> Decimal:
        if value != value.to_integral_value():
            raise ValueError("Count thresholds must be integers.")
        return value


class WindowParameters(RuleParameterValues):
    window_days: int = Field(default=7, gt=0)

    @field_validator("window_days", mode="before")
    @classmethod
    def reject_boolean_window(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Window length must be a positive whole number of days.")
        return value


class R01Values(CurrencyLimits, IntegerCountScoreParameters, WindowParameters):
    minimum_income_ratio: Decimal = Field(gt=0)
    income_currency: str = Field(pattern=r"^[A-Z]{3}$")
    band_low: Decimal = Field(default=Decimal("0.9"), gt=0, lt=1)
    above_check: Decimal = Field(default=Decimal("1.1"), gt=1)

    @field_validator("band_low", "above_check", mode="before")
    @classmethod
    def reject_boolean_bands(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Transaction bands must be numeric.")
        return value

    @field_validator("band_low", "above_check")
    @classmethod
    def validate_finite_bands(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Transaction bands must be finite.")
        return value

    @field_validator("minimum_income_ratio", mode="before")
    @classmethod
    def reject_boolean_ratio(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Income ratio must be numeric.")
        return value

    @field_validator("minimum_income_ratio")
    @classmethod
    def validate_finite_ratio(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Income ratio must be finite.")
        return value

    @model_validator(mode="after")
    def validate_income_currency_limit(self) -> "R01Values":
        if self.income_currency not in self.limits:
            raise ValueError("A transaction limit must be configured for income_currency.")
        return self


class R02Values(CurrencyLimits):
    pass


class R03Values(CurrencyLimits, IntegerCountScoreParameters, WindowParameters):
    cash_channels: list[Literal["atm", "mobile", "internet", "branch"]]

    @field_validator("cash_channels")
    @classmethod
    def validate_channels(
        cls, value: list[str]
    ) -> list[str]:
        if not value or len(value) != len(set(value)):
            raise ValueError("At least one unique cash channel is required.")
        return value


class CashAccountParameters(RuleParameterValues):
    cash_accounts: list[int] = Field(default_factory=list)

    @field_validator("cash_accounts", mode="before")
    @classmethod
    def reject_boolean_accounts(cls, value: Any) -> Any:
        if isinstance(value, list) and any(isinstance(item, bool) for item in value):
            raise ValueError("Cash account IDs must be positive integers.")
        return value

    @field_validator("cash_accounts")
    @classmethod
    def validate_cash_accounts(cls, value: list[int]) -> list[int]:
        if any(account_id <= 0 for account_id in value) or len(value) != len(set(value)):
            raise ValueError("Cash account IDs must be unique positive integers.")
        return value


class R04Values(CountScoreParameters, WindowParameters):
    pass


class R05Values(CountScoreParameters):
    history_days: int = Field(gt=0)
    kappa: Decimal = Field(ge=0)
    mad_floor: Decimal = Field(gt=0)
    income_bands: int = Field(ge=2)

    @field_validator("history_days", "income_bands", mode="before")
    @classmethod
    def reject_boolean_counts(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Expected a whole number.")
        return value

    @field_validator("kappa", "mad_floor", mode="before")
    @classmethod
    def reject_boolean_decimals(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Expected a numeric value.")
        return value

    @field_validator("kappa", "mad_floor")
    @classmethod
    def validate_finite_decimals(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Values must be finite.")
        return value


class R06Values(CountScoreParameters):
    history_weeks: int = Field(gt=0)
    min_count: int = Field(gt=0)
    season_factor: dict[date, Decimal] = Field(default_factory=dict)

    @field_validator("history_weeks", "min_count", mode="before")
    @classmethod
    def reject_boolean_counts(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Expected a positive whole number.")
        return value

    @field_validator("season_factor", mode="before")
    @classmethod
    def parse_season_factor(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(
            isinstance(item, bool) for item in value.values()
        ):
            raise ValueError("Season factors must be positive numbers.")
        return value

    @field_validator("season_factor")
    @classmethod
    def validate_season_factor(cls, value: dict[date, Decimal]) -> dict[date, Decimal]:
        if any(not factor.is_finite() or factor <= 0 for factor in value.values()):
            raise ValueError("Season factors must be finite positive numbers.")
        return value


class R07Values(CurrencyLimits, CountScoreParameters):
    dormant_days: int = Field(gt=0)
    window_days: int = Field(gt=0)

    @field_validator("dormant_days", "window_days", mode="before")
    @classmethod
    def reject_boolean_days(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Day counts must be positive whole numbers.")
        return value


class R08Values(CurrencyLimits, CountScoreParameters):
    account_age_days: int = Field(gt=0)

    @field_validator("account_age_days", mode="before")
    @classmethod
    def reject_boolean_days(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Account age must be a positive whole number of days.")
        return value


class R09Values(CurrencyLimits, CountScoreParameters, WindowParameters):
    baseline_days: int = Field(gt=0)
    cash_channels: list[Literal["atm", "mobile", "internet", "branch"]]

    @field_validator("baseline_days", mode="before")
    @classmethod
    def reject_boolean_days(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Baseline length must be a positive whole number of days.")
        return value

    @field_validator("cash_channels")
    @classmethod
    def validate_channels(cls, value: list[str]) -> list[str]:
        if not value or len(value) != len(set(value)):
            raise ValueError("At least one unique cash channel is required.")
        return value


class R10Values(CurrencyLimits, CountScoreParameters, CashAccountParameters):
    window_hours: int = Field(gt=0)
    ratio_low: Decimal = Field(ge=0)
    ratio_high: Decimal = Field(gt=0)

    @field_validator("window_hours", mode="before")
    @classmethod
    def reject_boolean_hours(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Window length must be a positive whole number of hours.")
        return value

    @field_validator("ratio_low", "ratio_high", mode="before")
    @classmethod
    def reject_boolean_ratios(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Ratios must be numeric.")
        return value

    @field_validator("ratio_low", "ratio_high")
    @classmethod
    def validate_finite_ratios(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Ratios must be finite.")
        return value

    @model_validator(mode="after")
    def validate_ratio_range(self) -> "R10Values":
        if self.ratio_low >= self.ratio_high:
            raise ValueError("ratio_high must be greater than ratio_low.")
        return self


class R11Values(IntegerCountScoreParameters, WindowParameters, CashAccountParameters):
    pass


class R12Values(CountScoreParameters, WindowParameters, CashAccountParameters):
    cv_threshold: Decimal = Field(gt=0)
    cv_multiplier: Decimal = Field(gt=0)

    @field_validator("cv_threshold", "cv_multiplier", mode="before")
    @classmethod
    def reject_boolean_cv_values(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Variation settings must be numeric.")
        return value

    @field_validator("cv_threshold", "cv_multiplier")
    @classmethod
    def validate_finite_cv_values(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Variation settings must be finite.")
        return value


class R13Values(IntegerCountScoreParameters, WindowParameters, CashAccountParameters):
    max_step_hours: int = Field(gt=0)
    decay_low: Decimal = Field(gt=0, lt=1)
    decay_high: Decimal = Field(gt=0, lt=1)
    max_depth: int = Field(ge=2, le=20)

    @field_validator("max_step_hours", "max_depth", mode="before")
    @classmethod
    def reject_boolean_graph_counts(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Graph bounds must be whole numbers.")
        return value

    @field_validator("decay_low", "decay_high", mode="before")
    @classmethod
    def reject_boolean_decay(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Decay factors must be numeric.")
        return value

    @field_validator("decay_low", "decay_high")
    @classmethod
    def validate_finite_decay(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Decay factors must be finite.")
        return value

    @model_validator(mode="after")
    def validate_decay_bounds(self) -> "R13Values":
        if self.decay_high < self.decay_low:
            raise ValueError("decay_high must be greater than or equal to decay_low.")
        return self


class R14Values(IntegerCountScoreParameters, WindowParameters, CashAccountParameters):
    max_cycle_length: int = Field(ge=3, le=20)
    min_retained: Decimal = Field(ge=0, le=1)
    pingpong_tolerance: Decimal = Field(ge=0)

    @field_validator("max_cycle_length", mode="before")
    @classmethod
    def reject_boolean_cycle_length(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Cycle length must be a whole number.")
        return value

    @field_validator("min_retained", "pingpong_tolerance", mode="before")
    @classmethod
    def reject_boolean_tolerances(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Tolerances must be numeric.")
        return value

    @field_validator("min_retained", "pingpong_tolerance")
    @classmethod
    def validate_finite_tolerances(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Tolerances must be finite.")
        return value


class R15Values(WindowParameters, CashAccountParameters):
    suspicious_status: Literal["confirmed_suspicious"]
    gamma: Decimal = Field(ge=0, le=1)

    @field_validator("gamma", mode="before")
    @classmethod
    def reject_boolean_gamma(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("gamma must be numeric.")
        return value

    @field_validator("gamma")
    @classmethod
    def validate_finite_gamma(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("gamma must be finite.")
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
