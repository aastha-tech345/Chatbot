import { Application, ApiRoute } from "@/types";

export const discoveredRoutes: ApiRoute[] = [
  { id: "r1", method: "GET", endpoint: "/products", description: "Get all products", authRequired: false, status: "Available" },
  { id: "r2", method: "GET", endpoint: "/products/{id}", description: "Get product by ID", authRequired: false, status: "Available" },
  { id: "r3", method: "POST", endpoint: "/cart", description: "Add to cart", authRequired: true, status: "Available" },
  { id: "r4", method: "GET", endpoint: "/cart", description: "View cart", authRequired: true, status: "Available" },
  { id: "r5", method: "DELETE", endpoint: "/cart/{id}", description: "Remove from cart", authRequired: true, status: "Available" },
  { id: "r6", method: "POST", endpoint: "/orders", description: "Create order", authRequired: true, status: "Available" },
  { id: "r7", method: "GET", endpoint: "/orders/{id}", description: "Get order details", authRequired: true, status: "Available" },
  { id: "r8", method: "GET", endpoint: "/search", description: "Search products", authRequired: false, status: "Available" }
];

export const applications: Application[] = [
  { id: "ecommerce", name: "E-commerce", appId: "ecommerce", type: "Web Application", baseUrl: "https://api.yourapp.com", docsUrl: "https://api.yourapp.com/docs", description: "Online store for products, cart, orders and payments.", status: "Active", routes: 24, totalCalls: 1200, successRate: 98.5, responseTime: 320, createdAt: "2026-09-10 10:30", updatedAt: "2026-09-14 12:45", icon: "ShoppingCart", tags: ["ecommerce", "shopping", "products", "orders"], endpoints: discoveredRoutes },
  { id: "his", name: "Hospital Management", appId: "his", type: "Web Application", baseUrl: "http://localhost:8001", docsUrl: "http://localhost:8001/docs", description: "Hospital records, patients, appointments and billing.", status: "Active", routes: 18, totalCalls: 850, successRate: 97.8, responseTime: 410, createdAt: "2026-09-11 09:00", updatedAt: "2026-09-12 18:20", icon: "Hospital", tags: ["healthcare", "patients"], endpoints: discoveredRoutes.slice(0, 6) },
  { id: "pharmacy", name: "Pharmacy", appId: "pharmacy", type: "REST API", baseUrl: "http://localhost:8002", docsUrl: "http://localhost:8002/docs", description: "Medication catalog and prescription fulfillment.", status: "Inactive", routes: 12, totalCalls: 240, successRate: 94.2, responseTime: 520, createdAt: "2026-09-09 14:10", updatedAt: "2026-09-10 13:55", icon: "Pill", tags: ["pharmacy"], endpoints: discoveredRoutes.slice(0, 5) },
  { id: "hrm", name: "HRM", appId: "hrm", type: "Internal Service", baseUrl: "http://localhost:3333", docsUrl: "http://localhost:3333/docs", description: "HR management system and employee workflows.", status: "Inactive", routes: 8, totalCalls: 120, successRate: 91.4, responseTime: 610, createdAt: "2026-09-08 11:45", updatedAt: "2026-09-08 16:00", icon: "Users", tags: ["hr"], endpoints: discoveredRoutes.slice(0, 4) },
  { id: "inventory", name: "Inventory", appId: "inventory", type: "REST API", baseUrl: "http://localhost:8004", docsUrl: "http://localhost:8004/docs", description: "Inventory management and stock operations.", status: "Active", routes: 15, totalCalls: 690, successRate: 99.1, responseTime: 280, createdAt: "2026-09-05 08:00", updatedAt: "2026-09-14 10:20", icon: "Package", tags: ["inventory"], endpoints: discoveredRoutes.slice(0, 7) }
];
