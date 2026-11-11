import { ActiveFilters, Product } from "../types";

export const FALLBACK_CATALOG: Product[] = [
  {
    id: 0,
    name: "UBC Hoodie",
    category: "clothing",
    description: "Cozy cotton hoodie with UBC branding.",
    price: 45,
    image: "https://i.ebayimg.com/image//w4oAAOSwyt9e34Mg/s-l1200.jpg",
  },
  {
    id: 1,
    name: "MacBook Air",
    category: "electronics",
    description: "13-inch laptop with M2 chip.",
    price: 1299,
    image: "https://techcrunch.com/wp-content/uploads/2022/07/CMC_1580.jpg",
  },
  {
    id: 2,
    name: "Bluetooth Headphones",
    category: "electronics",
    description: "Noise-cancelling headphones.",
    price: 199,
    image: "https://ca.shopatshowcase.com/cdn/shop/files/Bluetooth.jpg?v=1701031654",
  },
  {
    id: 3,
    name: "Smartwatch",
    category: "electronics",
    description: "Fitness tracking and notifications on your wrist.",
    price: 249,
    image: "https://cdn.mos.cms.futurecdn.net/QqpRXaFyFsabHTovTZb9DK.jpg",
  },
  {
    id: 4,
    name: "USB-C Hub",
    category: "electronics",
    description: "Multiport adapter for laptops.",
    price: 59,
    image:
      "https://mm.digikey.com/Volume0/opasdata/d220001/derivates/6/002/179/521/MFG_5G3AGBB-USB-C-HUB_web%28640x640%29.jpg",
  },
  {
    id: 5,
    name: "Running Shoes",
    category: "clothing",
    description: "Comfortable sports shoes.",
    price: 89,
    image:
      "https://images.puma.com/image/upload/f_auto,q_auto,b_rgb:fafafa,w_2000,h_2000/global/310218/01/sv01/fnd/PNA/fmt/png/FAST-R-NITRO%E2%84%A2-Elite-2-Women's-Running-Shoes",
  },
  {
    id: 6,
    name: "Backpack",
    category: "accessories",
    description: "Spacious and durable.",
    price: 49,
    image: "https://store.duolingo.com/cdn/shop/files/20240722_Duo7113V2.png?v=1743460964",
  },
  {
    id: 7,
    name: "T-Shirt",
    category: "clothing",
    description: "Soft cotton material.",
    price: 15,
    image: "https://i.ebayimg.com/images/g/w4oAAOSwyt9e34Mg/s-l1200.jpg",
  },
  {
    id: 8,
    name: "Denim Jacket",
    category: "clothing",
    description: "Classic jean jacket for everyday wear.",
    price: 75,
    image:
      "https://kmartau.mo.cloudinary.net/de38e64a-3886-4fa3-91e6-c8301e541122.jpg?tx=c_fill,w_3840,h_4800",
  },
  {
    id: 9,
    name: "Organic Apples",
    category: "groceries",
    description: "Fresh red apples.",
    price: 4,
    image:
      "https://amosinstitute.com/static/15e70de89c11d5ba7d1f6681fa0ba798/27ea3/organic-apples.png",
  },
  {
    id: 10,
    name: "Whole Wheat Bread",
    category: "groceries",
    description: "Healthy and nutritious.",
    price: 3,
    image:
      "https://www.allrecipes.com/thmb/_piMRxT9zYHP39Lnz6-lObHzEWw=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/AR-6773-simple-whole-wheat-bread-DDMFS-4x3-B-969e7bce922948959cb9e85aa4b2ff0d.jpg",
  },
  {
    id: 11,
    name: "Almond Milk",
    category: "groceries",
    description: "Non-dairy milk alternative.",
    price: 5,
    image:
      "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSPvLbZ7Kvht63xbfEwXpDKxzEHMFNozrJMJQ&s",
  },
  {
    id: 12,
    name: "Brown Rice",
    category: "groceries",
    description: "Nutritious whole grain rice.",
    price: 6,
    image:
      "https://www.southasiancentral.ca/wp-content/uploads/LAXMI-BROWN-BASMATI-RICE-4X10-LB-600x600.webp",
  },
];

/**
 * Deterministic client-side product filter matching `backend/services/filter_engine.py`.
 * Used when the user dismisses a constraint chip in the UI for instant 0ms grid updates.
 */
export function filterCatalog(catalog: Product[], filters: ActiveFilters): Product[] {
  let results = catalog;

  if (filters.category) {
    const cat = filters.category.trim().toLowerCase();
    results = results.filter((p) => p.category.toLowerCase() === cat);
  }

  if (filters.min_price !== undefined && filters.min_price !== null) {
    const min = Number(filters.min_price);
    results = results.filter((p) => p.price >= min);
  }

  if (filters.max_price !== undefined && filters.max_price !== null) {
    const max = Number(filters.max_price);
    results = results.filter((p) => p.price <= max);
  }

  if (filters.keyword) {
    const kw = filters.keyword.trim().toLowerCase();
    results = results.filter(
      (p) =>
        p.name.toLowerCase().includes(kw) || p.description.toLowerCase().includes(kw)
    );
  }

  return results;
}
