"use strict";
/* Optional FABRIX API bridge. When the FastAPI app is available it becomes the
   authoritative store for identity, catalog, cart, favorites and orders. When it
   is not available, every page keeps using the original localStorage demo. */
(() => {
  const TOKEN_KEY = "fabrix-api-token";
  const USER_KEY = "fabrix-api-user";
  const ENABLED_KEY = "fabrix-api-enabled";
  const nativeGet = localStorage.getItem.bind(localStorage);
  const nativeSet = localStorage.setItem.bind(localStorage);
  const query = new URLSearchParams(location.search);
  const apiPort = String(window.FABRIX_API_PORT || "8000");
  const sameOriginApi = location.port === apiPort;
  const localPreview =
    /^https?:$/.test(location.protocol) && /^(127\.0\.0\.1|localhost)$/.test(location.hostname);
  const optedIn =
    query.get("api") === "1" || nativeGet(ENABLED_KEY) === "1" || localPreview;

  const read = (key, fallback) => {
    try {
      const value = JSON.parse(nativeGet(key));
      return value === null ? fallback : value;
    } catch {
      return fallback;
    }
  };

  let suppressWriteThrough = false;
  let cartTimer = null;
  const storage = {
    set(key, value) {
      suppressWriteThrough = true;
      try {
        nativeSet(key, value);
      } finally {
        suppressWriteThrough = false;
      }
    },
  };

  const bgFor = (id) => ((Number(id) - 1) % 4) + 1;
  const catalogArray = () => {
    if (Array.isArray(window.products)) return window.products;
    if (typeof products !== "undefined" && Array.isArray(products)) {
      window.products = products;
      return products;
    }
    return null;
  };
  const INFERRED = {
    1: ["Metal", "Modern", "Silver"],
    2: ["Natural fiber", "Rustic", "Beige"],
    3: ["Natural fiber", "Minimal", "Gray"],
    4: ["Natural fiber", "Rustic", "Beige"],
    5: ["Clay", "Minimal", "Gray"],
    6: ["Wood", "Rustic", "Brown"],
    7: ["Clay", "Minimal", "Beige"],
    8: ["Metal", "Modern", "Silver"],
    9: ["Natural fiber", "Rustic", "Beige"],
    10: ["Wood", "Rustic", "Brown"],
    11: ["Clay", "Minimal", "Gray"],
    12: ["Natural fiber", "Minimal", "White"],
  };

  function mapProduct(p) {
    const list = catalogArray();
    const previous = list ? list.find((item) => item.id === p.id) || {} : {};
    const inferred = INFERRED[p.id] || [null, null, null];
    return {
      ...previous,
      id: p.id,
      slug: p.slug,
      name: p.name,
      maker: p.artisan || p.studio || previous.maker || "FABRIX Maker",
      artisan: p.artisan,
      studio: p.studio,
      price: p.price,
      category: p.category,
      tag: p.tag || p.tags?.[0] || previous.tag || "Handmade",
      bg: previous.bg || bgFor(p.id),
      stock: Number.isFinite(p.available_stock) ? p.available_stock : p.stock,
      material: p.material || inferred[0] || previous.material,
      style: p.style || inferred[1] || previous.style,
      color: p.color || inferred[2] || previous.color,
      description: p.description || previous.description,
      details: p.details || previous.details || {},
      rating: p.rating,
      reviews_count: p.reviews_count,
      image: p.image || previous.image,
      images: p.images || [],
      featured: p.featured,
      status: p.status,
    };
  }

  function mapAddress(a) {
    return {
      id: a.id,
      fullName: a.full_name,
      email: a.email,
      phone: a.phone || "",
      street: a.line1,
      city: a.city,
      country: a.country,
      postal: a.postal_code,
      isDefault: a.is_default,
    };
  }

  function mapOrder(order, ownerEmail) {
    const children = (order.seller_orders || []).map((child) => ({
      id: child.seller_order_number,
      maker: child.seller_name,
      status: child.status,
      subtotal: child.subtotal,
      shipping: child.shipping,
      total: child.total,
      lines: (child.items || []).map((item) => ({
        id: item.id,
        productId: item.product_id,
        name: item.name,
        price: item.unit_price,
        qty: item.quantity,
      })),
    }));
    const addr = order.shipping_address || {};
    return {
      id: order.order_number,
      owner: ownerEmail || order.customer_email,
      created: new Date(order.placed_at).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      }),
      address: {
        fullName: order.customer_name,
        email: order.customer_email,
        phone: addr.phone || "",
        street: addr.line1 || "",
        city: addr.city || "",
        country: addr.country || "",
        postal: addr.postal_code || "",
      },
      subtotal: order.subtotal,
      shipping: order.shipping,
      total: order.total,
      payment: order.payment_status || `Paid (${order.payment_method})`,
      children,
    };
  }

  let resolveReady;
  const bridge = {
    enabled: false,
    base: window.FABRIX_API_BASE || (sameOriginApi ? "" : `http://127.0.0.1:${apiPort}`),
    catalogLoaded: false,
    ready: new Promise((resolve) => {
      resolveReady = resolve;
    }),

    token() {
      return nativeGet(TOKEN_KEY) || "";
    },
    setToken(token) {
      nativeSet(TOKEN_KEY, token);
    },
    clearToken() {
      nativeRemove(TOKEN_KEY);
      nativeRemove(USER_KEY);
    },
    online() {
      return Boolean(this.enabled && this.token());
    },

    async request(path, options = {}) {
      const { method = "GET", body, auth = true, full = false, headers = {} } = options;
      const url = full ? `${this.base}${path}` : `${this.base}/api/v1${path}`;
      const requestHeaders = { ...headers };
      if (body !== undefined) requestHeaders["Content-Type"] = "application/json";
      if (auth && this.token()) requestHeaders.Authorization = `Bearer ${this.token()}`;
      const response = await fetch(url, {
        method,
        headers: requestHeaders,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const text = await response.text();
      let data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        data = text;
      }
      if (!response.ok) {
        const detail = data && data.detail ? data.detail : `Request failed (${response.status})`;
        const error = new Error(typeof detail === "string" ? detail : "Request failed");
        error.status = response.status;
        error.data = data;
        throw error;
      }
      return data;
    },

    async login(payload) {
      const result = await this.request("/auth/login", {
        method: "POST",
        body: payload,
        auth: false,
      });
      this.setToken(result.access_token);
      storage.set(USER_KEY, JSON.stringify(result.user));
      return result;
    },
    async register(payload) {
      const result = await this.request("/auth/register", {
        method: "POST",
        body: payload,
        auth: false,
      });
      this.setToken(result.access_token);
      storage.set(USER_KEY, JSON.stringify(result.user));
      return result;
    },
    async logout() {
      try {
        await this.request("/auth/logout", { method: "POST" });
      } catch {
        /* JWT logout is client-side; ignore offline failures. */
      }
      this.clearToken();
    },

    async loadCatalog() {
      const data = await this.request("/products?page_size=100", { auth: false });
      const catalog = catalogArray();
      if (!catalog) return;
      const mapped = data.items.map(mapProduct);
      mapped.forEach((product) => {
        const index = catalog.findIndex((item) => item.id === product.id);
        if (index >= 0) catalog[index] = product;
        else catalog.push(product);
      });
      this.catalogLoaded = true;
      window.dispatchEvent(new CustomEvent("fabrix:catalog", { detail: catalog }));
    },

    async migrateLocalState() {
      const localCart = read("fabrix-cart", {});
      const entries = Object.entries(localCart || {})
        .map(([product_id, quantity]) => ({ product_id: Number(product_id), quantity: Number(quantity) }))
        .filter((item) => Number.isInteger(item.product_id) && item.quantity > 0);
      if (entries.length) {
        try {
          await this.request("/cart/sync", { method: "POST", body: { items: entries } });
        } catch {
          /* Keep server cart if migration fails. */
        }
      }
      const favorites = read("fabrix-favorites", []);
      if (Array.isArray(favorites)) {
        await Promise.allSettled(
          favorites.map((id) => this.request(`/favorites/${Number(id)}`, { method: "POST" }))
        );
      }
    },

    async hydrate() {
      if (!this.token()) return false;
      let user;
      try {
        user = await this.request("/auth/me");
      } catch (error) {
        if (error.status === 401) this.clearToken();
        return false;
      }
      storage.set(USER_KEY, JSON.stringify(user));

      const isAdmin = user.role === "admin";
      const canSell = Boolean(user.can_sell) && !isAdmin;
      const tasks = {
        cart: this.request("/cart"),
        favorites: this.request("/favorites/ids"),
        orders: this.request("/orders"),
        addresses: this.request("/users/me/addresses"),
        notifications: this.request("/users/me/notifications"),
        store: canSell ? this.request("/seller/store") : Promise.resolve(null),
        drafts: canSell ? this.request("/products/mine") : Promise.resolve([]),
        sellerOrders: canSell ? this.request("/orders/seller/orders") : Promise.resolve([]),
        reviews: this.request("/reviews/mine"),
      };
      if (isAdmin) {
        tasks.adminStores = this.request("/admin/stores");
        tasks.adminProducts = this.request("/admin/products");
        tasks.adminSellerOrders = this.request("/admin/seller-orders");
        tasks.reports = this.request("/admin/reviews/reports");
        tasks.stats = this.request("/admin/stats");
      }
      const keys = Object.keys(tasks);
      const settled = await Promise.allSettled(keys.map((key) => tasks[key]));
      const value = (key, fallback) => {
        const index = keys.indexOf(key);
        return index >= 0 && settled[index].status === "fulfilled" ? settled[index].value : fallback;
      };

      const cart = value("cart", { items: [] });
      const favorites = value("favorites", { ids: [] });
      const orders = value("orders", { items: [] });
      const addresses = value("addresses", []);
      const notifications = value("notifications", { items: [] });
      const store = value("store", null);
      const drafts = value("drafts", []);
      const reviews = value("reviews", []);

      storage.set(
        "fabrix-cart",
        JSON.stringify(
          (cart.items || []).reduce((acc, item) => {
            acc[item.product_id] = item.quantity;
            return acc;
          }, {})
        )
      );
      storage.set("fabrix-favorites", JSON.stringify(favorites.ids || []));

      const mapStore = (row) => ({
        id: row.id,
        name: row.name,
        story: row.story,
        state: row.state,
        notes: row.notes || "",
        craft: row.craft,
      });
      const mapDraft = (product) => ({
        id: product.id,
        name: product.name,
        description: product.description || "",
        category: product.category,
        material: product.material || "Handmade material",
        price: product.price,
        stock: product.stock,
        state: product.status,
      });
      const mapReport = (report) => ({
        id: report.id,
        reviewId: report.review_id,
        reason: report.reason,
        status: report.status,
      });

      this.hydrated = {
        user: {
          ...user,
          name: user.full_name,
          canShop: user.can_shop,
          canSell: user.can_sell,
        },
        cart,
        favorites: favorites.ids || [],
        orders: (orders.items || []).map((order) => mapOrder(order, user.email)),
        reviews: (reviews || []).map((review) => ({
          key: `api-${review.id}`,
          productId: review.product_id,
          itemId: review.order_item_id,
          rating: review.rating,
          message: review.message,
          author: review.author,
        })),
        addresses: (addresses || []).map(mapAddress),
        notifications: (notifications.items || []).map((item) => ({
          id: item.id,
          message: item.message,
          when: new Date(item.created_at).toLocaleDateString("en-US", {
            year: "numeric",
            month: "short",
            day: "numeric",
          }),
        })),
        store: store
          ? mapStore(store)
          : { name: "Your Handmade Studio", story: "", state: "Draft", notes: "" },
        drafts: (drafts || []).map(mapDraft),
        reports: (value("reports", { items: [] }).items || []).map(mapReport),
        sellerOrders: (value("sellerOrders", []) || []).map((child) => ({
          id: child.seller_order_number,
          maker: child.seller_name,
          status: child.status,
          subtotal: child.subtotal,
          shipping: child.shipping,
          total: child.total,
          lines: (child.items || []).map((item) => ({
            id: item.id,
            productId: item.product_id,
            name: item.name,
            price: item.unit_price,
            qty: item.quantity,
          })),
        })),
        adminStores: (value("adminStores", []) || []).map(mapStore),
        adminProducts: (value("adminProducts", []) || []).map(mapDraft),
        adminSellerOrders: (value("adminSellerOrders", []) || []).map((child) => ({
          id: child.seller_order_number,
          maker: child.seller_name,
          status: child.status,
          subtotal: child.subtotal,
          shipping: child.shipping,
          total: child.total,
          lines: (child.items || []).map((item) => ({
            id: item.id,
            productId: item.product_id,
            name: item.name,
            price: item.unit_price,
            qty: item.quantity,
          })),
        })),
        stats: value("stats", null),
        personalization: Boolean(user.personalization),
        consent: Boolean(user.consent),
      };
      this.dispatchHydrated();
      return this.hydrated;
    },

    dispatchHydrated() {
      window.dispatchEvent(new CustomEvent("fabrix:hydrated", { detail: this.hydrated }));
    },

    async hydrateState(state) {
      const data = await this.hydrate();
      if (!data) return state;
      Object.assign(state, data);
      return state;
    },

    async checkout(payload) {
      const order = await this.request("/orders/checkout", { method: "POST", body: payload });
      return mapOrder(order, payload.address.email);
    },

    async event(productId, eventType, eventId) {
      if (!this.enabled || !productId) return;
      await this.request("/recommendations/events", {
        method: "POST",
        body: { product_id: Number(productId), event_type: eventType, event_id: eventId },
      }).catch(() => null);
    },
  };

  function nativeRemove(key) {
    localStorage.removeItem(key);
  }

  async function syncFavorites(value, beforeValue) {
    let after = [];
    let before = [];
    try {
      after = JSON.parse(value);
      before = JSON.parse(beforeValue || "[]");
    } catch {
      return;
    }
    if (!Array.isArray(after) || !Array.isArray(before)) return;
    const added = after.filter((id) => !before.includes(id));
    const removed = before.filter((id) => !after.includes(id));
    await Promise.allSettled([
      ...added.map((id) => bridge.request(`/favorites/${Number(id)}`, { method: "POST" })),
      ...removed.map((id) => bridge.request(`/favorites/${Number(id)}`, { method: "DELETE" })),
      ...added.map((id) =>
        bridge.event(id, "FAVORITE_ADD", `fav-${Date.now()}-${id}-${Math.random().toString(36).slice(2, 7)}`)
      ),
    ]);
  }

  function scheduleCartSync(value, beforeValue) {
    clearTimeout(cartTimer);
    cartTimer = setTimeout(async () => {
      let parsed;
      let before = {};
      try {
        parsed = JSON.parse(value);
        before = JSON.parse(beforeValue || "{}") || {};
      } catch {
        return;
      }
      const items = Object.entries(parsed || {})
        .map(([product_id, quantity]) => ({ product_id: Number(product_id), quantity: Number(quantity) }))
        .filter((item) => Number.isInteger(item.product_id) && item.quantity > 0);
      await bridge.request("/cart/sync", { method: "POST", body: { items } }).catch(() => null);
      const added = items.filter((item) => !Number(before[item.product_id]));
      await Promise.allSettled(
        added.map((item) =>
          bridge.event(
            item.product_id,
            "CART_ADD",
            `cart-${Date.now()}-${item.product_id}-${Math.random().toString(36).slice(2, 7)}`
          )
        )
      );
    }, 250);
  }

  localStorage.setItem = function (key, value) {
    const previous = nativeGet(key);
    nativeSet(key, value);
    if (suppressWriteThrough || !bridge.enabled || !bridge.token()) return;
    if (key === "fabrix-favorites") syncFavorites(value, previous);
    if (key === "fabrix-cart") scheduleCartSync(value, previous);
  };

  async function init() {
    try {
      if (!sameOriginApi && !optedIn) return;
      await bridge.request("/health", { auth: false, full: true });
      bridge.enabled = true;
      nativeSet(ENABLED_KEY, "1");
      await bridge.loadCatalog();
      if (bridge.token()) await bridge.hydrate();
    } catch {
      bridge.enabled = false;
    } finally {
      document.documentElement.dataset.fabrixApi = bridge.enabled ? "online" : "offline";
      resolveReady(bridge.enabled);
    }
  }

  window.FabrixAPI = bridge;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
