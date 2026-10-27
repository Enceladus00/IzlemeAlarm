import importlib
import inspect
import pkgutil

from backend.detection.metadata import RuleStrategy
import backend.detection.rules as rule_package


def load_rule_registry() -> dict[str, RuleStrategy]:
    strategies: dict[str, RuleStrategy] = {}
    for module_info in pkgutil.iter_modules(rule_package.__path__):
        module = importlib.import_module(f"{rule_package.__name__}.{module_info.name}")
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            if (
                candidate is RuleStrategy
                or not issubclass(candidate, RuleStrategy)
                or candidate.__module__ != module.__name__
            ):
                continue
            strategy = candidate()
            code = strategy.definition.code
            if code in strategies:
                raise RuntimeError(f"Duplicate detection rule implementation: {code}")
            strategies[code] = strategy
    return strategies
