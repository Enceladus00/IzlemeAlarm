from decimal import Decimal, ROUND_HALF_UP, localcontext


_SCORE_QUANTUM = Decimal("0.0001")
_LN_NINE = Decimal("9").ln()


def calculate_score(
    x: Decimal,
    *,
    x_esik: Decimal | None = None,
    x_kesin: Decimal | None = None,
    binary_limit: Decimal | None = None,
    force_zero: bool = False,
) -> Decimal:
    if force_zero:
        return Decimal("0.0000")
    if binary_limit is not None:
        return Decimal("1.0000") if x >= binary_limit else Decimal("0.0000")
    if x_esik is None or x_kesin is None or x_kesin <= x_esik:
        raise ValueError("Valid x_esik and x_kesin values are required.")

    if not x.is_finite() or not x_esik.is_finite() or not x_kesin.is_finite():
        raise ValueError("Scoring values must be finite.")
    with localcontext() as context:
        context.prec = 28
        scale = (x_kesin - x_esik) / _LN_NINE
        z = (x - x_esik) / scale
        if z >= Decimal("50"):
            return Decimal("1.0000")
        if z <= Decimal("-50"):
            return Decimal("0.0000")
        exp_z = z.exp()
        probability = (
            Decimal("1") / (Decimal("1") + (-z).exp())
            if z >= 0
            else exp_z / (Decimal("1") + exp_z)
        )
        return probability.quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)
