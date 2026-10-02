from webapp.backend.models.store import StoreProduct

STORE_PRODUCTS = (
    StoreProduct(
        product_id="invisible-umbrella",
        name="Invisible Umbrella",
        tagline="Stay dry. Allegedly.",
        description=(
            "A premium umbrella made from 100% transparent imagination. "
            "Handle included; weather protection sold separately in another dimension."
        ),
        category="Questionable essentials",
        price=39.90,
        emoji="☂️",
        badge="Bestseller-ish",
    ),
    StoreProduct(
        product_id="wifi-rock",
        name="Wi-Fi Extender Rock",
        tagline="A stronger signal, spiritually.",
        description=(
            "Place this authentic-looking rock near your router and believe very hard. "
            "Compatible with every network because it connects to none of them."
        ),
        category="Suspicious technology",
        price=64.50,
        emoji="🪨",
        badge="No firmware required",
    ),
    StoreProduct(
        product_id="meeting-escape-button",
        name="Emergency Meeting Escape Button",
        tagline="For calls that should have been emails.",
        description=(
            "A large red button that plays a convincing doorbell sound and displays "
            "a tasteful reminder to leave the meeting."
        ),
        category="Office survival",
        price=27.00,
        emoji="🚨",
    ),
    StoreProduct(
        product_id="executive-air",
        name="Executive Air — Limited Edition",
        tagline="The same air, but with leadership.",
        description=(
            "A sealed jar of boardroom-grade atmosphere. Notes of quarterly targets, "
            "cold coffee, and confident nodding."
        ),
        category="Luxury nonsense",
        price=118.75,
        emoji="🫙",
        badge="Only 9,999 left",
    ),
    StoreProduct(
        product_id="left-handed-mug",
        name="Left-Handed Coffee Mug",
        tagline="The handle is on the other side.",
        description=(
            "Revolutionary ceramic engineering for left-handed drinkers. "
            "Rotate 180 degrees for an instant right-handed compatibility upgrade."
        ),
        category="Domestic innovation",
        price=22.40,
        emoji="☕",
    ),
    StoreProduct(
        product_id="cloud-storage-box",
        name="Physical Cloud Storage Box",
        tagline="Put your files somewhere fluffy.",
        description=(
            "A cardboard box labeled CLOUD. Holds up to 2 TB of printed screenshots "
            "depending on font size and folding technique."
        ),
        category="Suspicious technology",
        price=51.25,
        emoji="☁️",
        badge="Offline-first",
    ),
)
