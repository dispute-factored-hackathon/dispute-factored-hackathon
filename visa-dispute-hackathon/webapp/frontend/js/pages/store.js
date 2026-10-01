import { apiRequest } from "../api.js";
import { requireCustomer } from "../auth.js";
import {
    addToCart,
    animateAddToCart,
    emitStoreMetric,
    updateCartBadges,
} from "../components/store-cart.js";

const page = document.querySelector("#store-page");
const grid = document.querySelector("#product-grid");
const error = document.querySelector("#store-error");

function money(value) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function renderProduct(product) {
    const article = document.createElement("article");
    article.className = "product-card";
    article.innerHTML = `
        <div class="product-card-visual" aria-hidden="true"></div>
        <div class="product-card-content">
            <span class="product-badge" hidden></span>
            <h3></h3><p></p>
            <div class="product-card-footer"><strong></strong><a>Details</a></div>
            <div class="quick-buy">
                <label>Qty <select class="quick-quantity" aria-label="Quantity"></select></label>
                <button class="quick-add" type="button">Add to cart</button>
            </div>
        </div>`;
    article.querySelector(".product-card-visual").textContent = product.emoji;
    const badge = article.querySelector(".product-badge");
    if (product.badge) { badge.textContent = product.badge; badge.hidden = false; }
    article.querySelector("h3").textContent = product.name;
    article.querySelector("p").textContent = product.tagline;
    article.querySelector("strong").textContent = money(product.price);
    const link = article.querySelector("a");
    link.href = `/shop/products/${encodeURIComponent(product.product_id)}`;
    link.setAttribute("aria-label", `View ${product.name}`);
    const quantity = article.querySelector(".quick-quantity");
    quantity.replaceChildren(...Array.from({ length: 10 }, (_, index) => {
        const option = document.createElement("option");
        option.value = String(index + 1);
        option.textContent = String(index + 1);
        return option;
    }));
    const addButton = article.querySelector("button");
    addButton.addEventListener("click", async (event) => {
        const selectedQuantity = Number(quantity.value);
        addButton.disabled = true;
        addButton.textContent = selectedQuantity === 1 ? "Added!" : `${selectedQuantity} added!`;
        addToCart(product.product_id, selectedQuantity);
        updateCartBadges();
        emitStoreMetric("add_to_cart", {
            source: "catalog",
            product_id: product.product_id,
            quantity: selectedQuantity,
        });
        await animateAddToCart({
            event,
            sourceElement: article.querySelector(".product-card-visual"),
            emoji: product.emoji,
        });
        addButton.disabled = false;
        addButton.textContent = "Add to cart";
    });
    return article;
}

async function initialize() {
    const customer = await requireCustomer();
    if (!customer) return;
    page.hidden = false;
    updateCartBadges();
    emitStoreMetric("catalog_viewed");
    try {
        const products = await apiRequest("/store/products", { method: "GET" });
        grid.replaceChildren(...products.map(renderProduct));
    } catch (requestError) {
        console.error("Unable to load Shady Business catalog:", requestError);
        error.textContent = "Our van is temporarily empty. Reload the page to try again.";
        error.hidden = false;
    }
}

initialize();
