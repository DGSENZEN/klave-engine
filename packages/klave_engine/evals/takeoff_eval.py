"""Quantity takeoff evaluation against fixture expected values."""

from pydantic import BaseModel

from klave_engine.takeoff.quantities import QuantityReport


class TakeoffEvalResult(BaseModel):
    quantity_name: str
    expected_value: float
    actual_value: float
    absolute_error: float
    percentage_error: float
    passed: bool


def evaluate_takeoff(
    report: QuantityReport,
    expected: dict[str, float],
    max_percentage_error: float = 5.0,
) -> list[TakeoffEvalResult]:
    actual_by_name = {item.name: item.value for item in report.items}
    results = []
    for name, expected_value in sorted(expected.items()):
        actual = actual_by_name.get(name, 0.0)
        absolute_error = abs(actual - expected_value)
        if expected_value != 0:
            percentage_error = 100.0 * absolute_error / abs(expected_value)
        else:
            percentage_error = 0.0 if absolute_error == 0 else 100.0
        results.append(
            TakeoffEvalResult(
                quantity_name=name,
                expected_value=expected_value,
                actual_value=actual,
                absolute_error=round(absolute_error, 4),
                percentage_error=round(percentage_error, 4),
                passed=percentage_error <= max_percentage_error,
            )
        )
    return results
