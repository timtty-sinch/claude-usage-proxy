from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ModelPricing:
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cache_read_per_mtok: Decimal
    cache_creation_per_mtok: Decimal


# Prices in USD per million tokens
MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-opus-4-5": ModelPricing(
        input_per_mtok=Decimal("15.00"),
        output_per_mtok=Decimal("75.00"),
        cache_read_per_mtok=Decimal("1.50"),
        cache_creation_per_mtok=Decimal("18.75"),
    ),
    "claude-sonnet-4-5": ModelPricing(
        input_per_mtok=Decimal("3.00"),
        output_per_mtok=Decimal("15.00"),
        cache_read_per_mtok=Decimal("0.30"),
        cache_creation_per_mtok=Decimal("3.75"),
    ),
    "claude-haiku-4-5": ModelPricing(
        input_per_mtok=Decimal("0.80"),
        output_per_mtok=Decimal("4.00"),
        cache_read_per_mtok=Decimal("0.08"),
        cache_creation_per_mtok=Decimal("1.00"),
    ),
    "claude-opus-4-6": ModelPricing(
        input_per_mtok=Decimal("15.00"),
        output_per_mtok=Decimal("75.00"),
        cache_read_per_mtok=Decimal("1.50"),
        cache_creation_per_mtok=Decimal("18.75"),
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_per_mtok=Decimal("3.00"),
        output_per_mtok=Decimal("15.00"),
        cache_read_per_mtok=Decimal("0.30"),
        cache_creation_per_mtok=Decimal("3.75"),
    ),
    # Legacy models
    "claude-3-5-sonnet": ModelPricing(
        input_per_mtok=Decimal("3.00"),
        output_per_mtok=Decimal("15.00"),
        cache_read_per_mtok=Decimal("0.30"),
        cache_creation_per_mtok=Decimal("3.75"),
    ),
    "claude-3-5-haiku": ModelPricing(
        input_per_mtok=Decimal("0.80"),
        output_per_mtok=Decimal("4.00"),
        cache_read_per_mtok=Decimal("0.08"),
        cache_creation_per_mtok=Decimal("1.00"),
    ),
    "claude-3-opus": ModelPricing(
        input_per_mtok=Decimal("15.00"),
        output_per_mtok=Decimal("75.00"),
        cache_read_per_mtok=Decimal("1.50"),
        cache_creation_per_mtok=Decimal("18.75"),
    ),
    "claude-3-sonnet": ModelPricing(
        input_per_mtok=Decimal("3.00"),
        output_per_mtok=Decimal("15.00"),
        cache_read_per_mtok=Decimal("0.30"),
        cache_creation_per_mtok=Decimal("3.75"),
    ),
    "claude-3-haiku": ModelPricing(
        input_per_mtok=Decimal("0.25"),
        output_per_mtok=Decimal("1.25"),
        cache_read_per_mtok=Decimal("0.03"),
        cache_creation_per_mtok=Decimal("0.30"),
    ),
}

# Maps dated snapshot strings to canonical model IDs
MODEL_ALIASES: dict[str, str] = {
    "claude-3-5-sonnet-20241022": "claude-3-5-sonnet",
    "claude-3-5-sonnet-20240620": "claude-3-5-sonnet",
    "claude-3-5-haiku-20241022": "claude-3-5-haiku",
    "claude-3-opus-20240229": "claude-3-opus",
    "claude-3-sonnet-20240229": "claude-3-sonnet",
    "claude-3-haiku-20240307": "claude-3-haiku",
    "claude-sonnet-4-5-20251001": "claude-sonnet-4-5",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5",
}

ZERO = Decimal("0")


def get_pricing(model: str) -> ModelPricing | None:
    canonical = MODEL_ALIASES.get(model, model)
    return MODEL_PRICING.get(canonical)


@dataclass
class CostBreakdown:
    input_cost: Decimal
    output_cost: Decimal
    cache_read_cost: Decimal
    cache_creation_cost: Decimal
    total_cost: Decimal


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> CostBreakdown:
    pricing = get_pricing(model)
    if pricing is None:
        zero = ZERO
        return CostBreakdown(zero, zero, zero, zero, zero)

    mtok = Decimal("1_000_000")
    input_cost = pricing.input_per_mtok * Decimal(input_tokens) / mtok
    output_cost = pricing.output_per_mtok * Decimal(output_tokens) / mtok
    cache_read_cost = pricing.cache_read_per_mtok * Decimal(cache_read_tokens) / mtok
    cache_creation_cost = pricing.cache_creation_per_mtok * Decimal(cache_creation_tokens) / mtok
    total_cost = input_cost + output_cost + cache_read_cost + cache_creation_cost

    return CostBreakdown(
        input_cost=input_cost,
        output_cost=output_cost,
        cache_read_cost=cache_read_cost,
        cache_creation_cost=cache_creation_cost,
        total_cost=total_cost,
    )
