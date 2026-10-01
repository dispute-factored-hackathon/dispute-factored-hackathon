import { ApiError, apiRequest } from "../api.js";
import { requireCustomer } from "../auth.js";
import {
    addToCart,
    animateAddToCart,
    emitStoreMetric,
    updateCartBadges,
} from "../components/store-cart.js";

const page = document.querySelector("#product-page");
const detail = document.querySelector("#product-detail");
const error = document.querySelector("#product-error");

function productId() {
    return decodeURIComponent(window.location.pathname.split("/").filter(Boolean).at(-1) || "");
}

function money(value) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function render(product) {
    document.title = `${product.name} · Shady Business`;
    detail.innerHTML = `
        <div class="product-detail-visual" aria-hidden="true"></div>
        <div class="product-detail-copy">
            <span class="product-badge" hidden></span><p class="store-kicker"></p><h1></h1>
            <p class="description"></p><strong class="product-price"></strong>
            <div class="product-buy-controls">
                <label>Quantity <select class="product-quantity" aria-label="Quantity"></select></label>
                <button class="shady-button" type="button">Add to cart</button>
            </div>
        </div>`;
    detail.querySelector(".product-detail-visual").textContent = product.emoji;
    detail.querySelector(".store-kicker").textContent = product.category;
    detail.querySelector("h1").textContent = product.name;
    detail.querySelector(".description").textContent = product.description;
    detail.querySelector(".product-price").textContent = money(product.price);
    const badge = detail.querySelector(".product-badge");
    if (product.badge) { badge.textContent = product.badge; badge.hidden = false; }
    const quantity = detail.querySelector(".product-quantity");
    quantity.replaceChildren(...Array.from({ length: 10 }, (_, index) => {
        const option = document.createElement("option");
        option.value = String(index + 1);
        option.textContent = String(index + 1);
        return option;
    }));
    const addButton = detail.querySelector("button");
    addButton.addEventListener("click", async (event) => {
        const selectedQuantity = Number(quantity.value);
        addButton.disabled = true;
        addButton.textContent = selectedQuantity === 1 ? "Added!" : `${selectedQuantity} added!`;
        addToCart(product.product_id, selectedQuantity);
        updateCartBadges();
        emitStoreMetric("add_to_cart", {
            source: "product",
            product_id: product.product_id,
            quantity: selectedQuantity,
        });
        await animateAddToCart({
            event,
            sourceElement: detail.querySelector(".product-detail-visual"),
            emoji: product.emoji,
        });
        addButton.disabled = false;
        addButton.textContent = "Add to cart";
    });
}

async function initialize() {
    const customer = await requireCustomer();
    if (!customer) return;
    page.hidden = false;
    updateCartBadges();
    try {
        const product = await apiRequest(`/store/products/${encodeURIComponent(productId())}`, { method: "GET" });
        render(product);
        emitStoreMetric("product_viewed", { product_id: product.product_id });
    } catch (requestError) {
        error.textContent = requestError instanceof ApiError && requestError.status === 404
            ? "That questionable product has disappeared from the van."
            : "We could not load this product. Please try again.";
        error.hidden = false;
    }
}

initialize();
