"""Seed aspect vocabulary + synonym normalization for the Phase 4 aspect
extractor. Kept in one small, easily-edited config module rather than
scattered through route/service code, per the Phase 4 brief.

Not "hundreds of domain-specific mappings" — a small, generic starter set
covering common product/service-review aspects. Extend as needed.
"""

# Canonical aspect name -> surface forms that should be extracted as that aspect.
# The canonical name is also matched directly.
ASPECT_SEED_TERMS = {
    "price": ["price", "pricing", "cost", "expensive", "cheap", "affordable"],
    "delivery": ["delivery", "shipping", "shipment", "delivered", "courier"],
    "packaging": ["packaging", "package", "box", "wrapping"],
    "customer service": ["customer service", "support", "customer support", "helpline"],
    "battery": ["battery", "battery life", "charge", "charging"],
    "performance": ["performance", "speed", "lag", "fast", "slow"],
    "usability": ["usability", "ease of use", "user friendly", "user-friendly", "interface"],
    "quality": ["quality", "build quality", "durability", "sturdy"],
    "design": ["design", "look", "appearance", "style"],
    "availability": ["availability", "stock", "in stock", "out of stock"],
    "sound": ["sound", "audio", "sound quality"],
    "camera": ["camera", "photo", "picture quality"],
    "screen": ["screen", "display"],
}

# Flat synonym -> canonical map, derived from ASPECT_SEED_TERMS plus a few
# explicit extras. This is what ASPECT_EXTRACTION_FLOW's "normalize candidate
# names" step calls.
ASPECT_SYNONYMS = {
    surface: canonical
    for canonical, surfaces in ASPECT_SEED_TERMS.items()
    for surface in surfaces
}
ASPECT_SYNONYMS.update({
    "shipment": "delivery",
    "cost": "price",
    "pricing": "price",
})

MIN_ASPECT_FREQUENCY = 1
