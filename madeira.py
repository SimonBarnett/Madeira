from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from amazon_paapi import AmazonApi 
import time
import json
import os
import requests
import jwt
from pseudo_categories import PSEUDO_CATEGORIES
import random
import string
import hashlib
from flask import Flask, request, jsonify
import bcrypt
import json
import datetime

app = Flask(__name__)
# Enable CORS with verbose logging
CORS(app, resources={
    r"/*": {  # Wildcard to match all routes
        "origins": "http://walrus:8282",
        "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
}, supports_credentials=False)

SECRET_KEY = "itsananagramjanet"  # Replace with a secure key
USERS_FILE = "users_categories.json"
USERS_PRODUCTS_FILE = "users_products.json"
CONFIG_FILE = "config.json"
DEFAULT_CATEGORIES = ["283155", "172282"]
USERS_SETTINGS_FILE = "users_settings.json"

# region Helper Functions
def load_users_categories():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {USERS_FILE}: {str(e)}")
            return {}
    return {}

def save_users_categories(users_data):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users_data, f, indent=4)
    except Exception as e:
        print(f"Error saving {USERS_FILE}: {str(e)}")

def get_user_categories(user_id):
    users_data = load_users_categories()
    if user_id not in users_data:
        users_data[user_id] = DEFAULT_CATEGORIES
        save_users_categories(users_data)
    return users_data.get(user_id, [])

def load_users_products():
    """Load Wix products for all users using their wixClientId from users_settings.json."""
    users_settings = load_users_settings()
    users_products = {}
    
    for user_id, settings in users_settings.items():
        wix_client_id = settings.get("wixClientId")
        if not wix_client_id:
            print(f"No wixClientId found for user {user_id}")
            users_products[user_id] = []
            continue

        token_url = "https://www.wixapis.com/oauth2/token"
        payload = {
            "clientId": wix_client_id,
            "grantType": "anonymous"
        }
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(token_url, json=payload, headers=headers)
            if response.status_code != 200:
                print(f"Error getting token for user {user_id}: {response.status_code} - {response.text}")
                users_products[user_id] = []
                continue
            token_data = response.json()
            access_token = token_data["access_token"]
            print(f"Access Token for user {user_id}: {access_token}")
        except Exception as e:
            print(f"Token fetch error for user {user_id}: {str(e)}")
            users_products[user_id] = []
            continue

        collections_url = "https://www.wixapis.com/stores-reader/v1/collections/query"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        def fetch_collections(limit=10, offset=0):
            query_payload = {
                "query": {
                    "paging": {"limit": limit, "offset": offset}
                },
                "includeNumberOfProducts": True
            }
            response = requests.post(collections_url, headers=headers, json=query_payload)
            if response.status_code != 200:
                print(f"Error fetching collections for user {user_id}: {response.status_code} - {response.text}")
                return None
            return response.json()

        products_url = "https://www.wixapis.com/stores/v1/products/query"

        def fetch_products_for_collection(collection_id, limit=10, offset=0):
            filter_str = json.dumps({"collections.id": {"$hasSome": [collection_id]}})
            query_payload = {
                "query": {
                    "filter": filter_str,
                    "paging": {"limit": limit, "offset": offset}
                }
            }
            response = requests.post(products_url, headers=headers, json=query_payload)
            if response.status_code != 200:
                print(f"Error fetching products for collection {collection_id} for user {user_id}: {response.status_code} - {response.text}")
                return None
            return response.json()

        all_collections = []
        limit = 10
        offset = 0

        while True:
            result = fetch_collections(limit=limit, offset=offset)
            if not result or "collections" not in result or not result["collections"]:
                break

            collections = result["collections"]
            filtered_collections = [
                {
                    "id": col["id"],
                    "name": col["name"],
                    "numberOfProducts": col["numberOfProducts"],
                    "products": []
                }
                for col in collections
                if not col["id"].startswith("00000000")
            ]
            all_collections.extend(filtered_collections)
            print(f"Fetched {len(collections)} collections, kept {len(filtered_collections)} for user {user_id} (offset {offset} to {offset + limit - 1})")
            offset += limit
            if len(collections) < limit:
                break

        all_products = []
        for collection in all_collections:
            collection_id = collection["id"]
            collection_name = collection["name"]
            offset = 0

            while True:
                result = fetch_products_for_collection(collection_id, limit=limit, offset=offset)
                if not result or "products" not in result or not result["products"]:
                    break

                products = result["products"]
                for product in products:
                    current_price = float(product.get("price", {}).get("formatted", {}).get("price", "0").replace("$", "").replace("£", "").replace(",", "") or 0.0)
                    original_price = float(product.get("discountedPrice", {}).get("formatted", {}).get("price", str(current_price)).replace("$", "").replace("£", "").replace(",", "") or current_price)
                    discount = ((original_price - current_price) / original_price) * 100 if original_price > current_price else 0
                    base_url = (
                        product.get("productPageUrl", {}).get("base", "").rstrip("/") + "/" +
                        product.get("productPageUrl", {}).get("path", "").lstrip("/")
                    )
                    product_url = f"{base_url}?referer={user_id}"
                    all_products.append({
                        "source": user_id,
                        "id": product.get("id", ""),
                        "title": product.get("name", ""),
                        "product_url": product_url,
                        "current_price": current_price,
                        "original_price": original_price,
                        "discount_percent": round(discount, 2),
                        "image_url": product.get("media", {}).get("mainMedia", {}).get("thumbnail", {}).get("url", ""),
                        "qty": (
                            int(product.get("stock", {}).get("quantity", 0))
                            if product.get("stock", {}).get("trackQuantity", False)
                            else -1
                        ),
                        "category": collection_name,
                        "user_id": user_id
                    })
                print(f"Fetched {len(products)} products for collection {collection_name} for user {user_id} (offset {offset} to {offset + limit - 1})")
                offset += limit
                if len(products) < limit:
                    break

        users_products[user_id] = all_products
        print(f"Total products fetched for user {user_id}: {len(all_products)}")

    return users_products

def save_users_products(users_products):
    with open(USERS_PRODUCTS_FILE, 'w') as f:
        json.dump(users_products, f, indent=4)

def get_user_products(user_id):
    users_products = load_users_products()
    return users_products.get(user_id, [])

def load_config():
    default_config = {
        "amazon_uk": {"ACCESS_KEY": "", "SECRET_KEY": "", "ASSOCIATE_TAG": "", "COUNTRY": ""},
        "ebay_uk": {"APP_ID": ""},
        "awin": {"API_TOKEN": ""},
        "cj": {"API_KEY": "", "WEBSITE_ID": ""}
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_config = json.load(f)
                for section in default_config:
                    if section in loaded_config:
                        default_config[section].update(loaded_config[section])
                return loaded_config
        except Exception as e:
            print(f"Error loading {CONFIG_FILE}: {str(e)}")
    return default_config

def save_config(config):
    default_config = {
        "amazon_uk": {"ACCESS_KEY": "", "SECRET_KEY": "", "ASSOCIATE_TAG": "", "COUNTRY": ""},
        "ebay_uk": {"APP_ID": ""},
        "awin": {"API_TOKEN": ""},
        "cj": {"API_KEY": "", "WEBSITE_ID": ""}
    }
    for section in config:
        if section in default_config:
            default_config[section].update(config[section])
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(default_config, f, indent=4)
    except Exception as e:
        print(f"Error saving {CONFIG_FILE}: {str(e)}")

def get_amazon_category_title(browse_node_id):
    config = load_config()
    if all(config.get("amazon_uk", {}).values()):
        amazon = AmazonApi(config["amazon_uk"]["ACCESS_KEY"], config["amazon_uk"]["SECRET_KEY"],
                           config["amazon_uk"]["ASSOCIATE_TAG"], config["amazon_uk"]["COUNTRY"])
        try:
            browse_nodes = amazon.get_browse_nodes(
                browse_node_ids=[browse_node_id],
                resources=["BrowseNodes.DisplayName"]
            )
            if browse_nodes and browse_nodes.browse_nodes:
                return browse_nodes.browse_nodes[0].display_name
        except Exception as e:
            print(f"Error fetching category title for {browse_node_id}: {str(e)}")
    def find_category_recursive(categories, target_id):
        for category in categories:
            if category.get("id") == target_id:
                return category.get("name")
            if "subcategories" in category:
                result = find_category_recursive(category["subcategories"], target_id)
                if result is not None:
                    return result
    return find_category_recursive(PSEUDO_CATEGORIES, browse_node_id)

def get_immediate_subcategories(parent_id):
    config = load_config()
    if not all(config.get("amazon_uk", {}).values()):
        return []
    amazon = AmazonApi(config["amazon_uk"]["ACCESS_KEY"], config["amazon_uk"]["SECRET_KEY"],
                       config["amazon_uk"]["ASSOCIATE_TAG"], config["amazon_uk"]["COUNTRY"])
    try:
        browse_nodes = amazon.get_browse_nodes(
            browse_node_ids=[parent_id],
            resources=["BrowseNodes.Children"]
        )
        if browse_nodes and browse_nodes.browse_nodes:
            return [{"id": node.browse_node_id, "name": node.display_name} for node in browse_nodes.browse_nodes[0].children]
        return []
    except Exception as e:
        print(f"Error fetching subcategories for {parent_id}: {str(e)}")
        return []

def filter_categories_with_products(category_ids, min_discount_percent):
    config = load_config()
    all_discounted_items = []
    for cat_id in category_ids:
        if all(config.get("amazon_uk", {}).values()):
            all_discounted_items.extend(search_amazon_uk_discounted(cat_id, min_discount_percent))
        if all(config.get("ebay_uk", {}).values()):
            all_discounted_items.extend(search_ebay_uk_discounted(cat_id, min_discount_percent))
        if config.get("awin", {}).get("API_TOKEN"):
            all_discounted_items.extend(search_awin_uk_discounted(cat_id, min_discount_percent))
        if all(config.get("cj", {}).values()):
            all_discounted_items.extend(search_cj_uk_discounted(cat_id, min_discount_percent))
    filtered_categories = []
    for cat_id in category_ids:
        if any(item for item in all_discounted_items if "BrowseNodeId" in item and item["BrowseNodeId"] == cat_id):
            category_title = get_amazon_category_title(cat_id) or cat_id
            filtered_categories.append({"id": cat_id, "name": category_title})
    return filtered_categories

def find_node(categories, target_id):
    for category in categories:
        if category['id'] == target_id:
            return category
        if 'subcategories' in category:
            result = find_node(category['subcategories'], target_id)
            if result is not None:
                return result
    return None

def find_pseudo_subcategories(parent_id, categories):
    node = find_node(categories, parent_id)
    if node and 'subcategories' in node:
        return [{'id': subcat['id'], 'name': subcat['name']} for subcat in node['subcategories']]
    return []

def load_users_settings():
    if os.path.exists(USERS_SETTINGS_FILE):
        try:
            with open(USERS_SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {USERS_SETTINGS_FILE}: {str(e)}")
            return {}
    return {}

def save_users_settings(users_settings):
    try:
        with open(USERS_SETTINGS_FILE, 'w') as f:
            json.dump(users_settings, f, indent=4)
    except Exception as e:
        print(f"Error saving {USERS_SETTINGS_FILE}: {str(e)}")

def get_user_settings(user_id):
    users_settings = load_users_settings()
    return users_settings.get(user_id, {})
# endregion Helper Functions

# region Detailed Fetch
def get_amazon_uk_full_details(asins, category):
    config = load_config()
    if not all(config.get("amazon_uk", {}).values()):
        return []
    amazon = AmazonApi(config["amazon_uk"]["ACCESS_KEY"], config["amazon_uk"]["SECRET_KEY"],
                       config["amazon_uk"]["ASSOCIATE_TAG"], config["amazon_uk"]["COUNTRY"])
    full_item_data = []
    try:
        item_response = amazon.get_items(
            item_ids=asins,
            resources=["ItemInfo.ByLineInfo", "ItemInfo.ContentInfo", "ItemInfo.Features", 
                       "ItemInfo.ProductInfo", "ItemInfo.Title", "Images.Primary.Large", 
                       "Offers.Listings.Price", "DetailPageURL"]
        )
        for item in item_response.items:
            current_price = item.offers.listings[0].price.amount if item.offers and item.offers.listings else None
            if item.offers and item.offers.listings and item.offers.listings[0].price.savings:
                savings = item.offers.listings[0].price.savings.amount
                original_price = current_price + savings
                discount_percent = float(item.offers.listings[0].price.savings.percentage)
            else:
                original_price = current_price
                discount_percent = 0.0
            item_data = {
                "source": "amazon_uk",
                "id": item.asin,
                "title": item.item_info.title.display_value if item.item_info.title else None,
                "product_url": item.detail_page_url,
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": discount_percent,
                "image_url": item.images.primary.large.url if item.images and item.images.primary else None,
                "category": category,
                "manufacturer": item.item_info.by_line_info.manufacturer.display_value if item.item_info.by_line_info and item.item_info.by_line_info.manufacturer else None,
                "dimensions": item.item_info.product_info.item_dimensions.display_value if item.item_info.product_info and item.item_info.product_info.item_dimensions else None,
                "features": item.item_info.features.display_values if item.item_info.features else []
            }
            full_item_data.append(item_data)
        time.sleep(1)
    except Exception as e:
        print(f"Amazon UK Error: {str(e)}")
    return full_item_data

def get_ebay_uk_full_details(item_ids, category):
    config = load_config()
    if not all(config.get("ebay_uk", {}).values()):
        return []
    url = "https://api.ebay.com/buy/browse/v1/item"
    headers = {"Authorization": f"Bearer {config['ebay_uk']['APP_ID']}"}
    full_item_data = []
    for item_id in item_ids:
        try:
            params = {"item_id": item_id}
            response = requests.get(url, headers=headers, params=params)
            item = response.json()
            current_price = float(item["price"]["value"])
            original_price_value = item.get("originalPrice", {}).get("value", current_price)
            original_price = float(original_price_value)
            discount = ((original_price - current_price) / original_price) * 100 if original_price > current_price else 0.0
            item_data = {
                "source": "ebay_uk",
                "id": item["itemId"],
                "title": item["title"],
                "product_url": item["itemWebUrl"],
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": round(discount, 2),
                "image_url": item["image"]["imageUrl"] if "image" in item else None,
                "category": category,
                "manufacturer": item.get("brand", None),
                "features": item.get("shortDescription", "").split(". ") if item.get("shortDescription") else []
            }
            full_item_data.append(item_data)
            time.sleep(1)
        except Exception as e:
            print(f"eBay UK Error for {item_id}: {str(e)}")
    return full_item_data

def get_awin_uk_full_details(product_ids, category):
    config = load_config()
    if not config.get("awin", {}).get("API_TOKEN"):
        return []
    url = f"https://api.awin.com/publishers/{config['awin']['API_TOKEN']}/products"
    full_item_data = []
    for product_id in product_ids:
        try:
            params = {"productId": product_id, "region": "UK"}
            response = requests.get(url, params=params)
            product = response.json()["products"][0]
            current_price = float(product["price"]["amount"])
            original_price = float(product.get("originalPrice", current_price))
            discount = ((original_price - current_price) / original_price) * 100 if original_price > current_price else 0.0
            item_data = {
                "source": "awin_uk",
                "id": product["productId"],
                "title": product["name"],
                "product_url": product["url"],
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": round(discount, 2),
                "image_url": product.get("imageUrl", None),
                "category": category,
                "manufacturer": product.get("brand", None),
                "dimensions": product.get("dimensions", None),
                "features": product.get("description", "").split(". ") if product.get("description") else []
            }
            full_item_data.append(item_data)
            time.sleep(1)
        except Exception as e:
            print(f"Awin UK Error for {product_id}: {str(e)}")
    return full_item_data

def get_cj_uk_full_details(skus, category):
    config = load_config()
    if not all(config.get("cj", {}).values()):
        return []
    url = "https://product-search.api.cj.com/v2/product-search"
    headers = {"Authorization": f"Bearer {config['cj']['API_KEY']}"}
    full_item_data = []
    for sku in skus:
        try:
            params = {
                "website-id": config["cj"]["WEBSITE_ID"],
                "sku": sku,
                "country": "UK"
            }
            response = requests.get(url, headers=headers, params=params)
            product = response.json()["products"][0]
            current_price = float(product["price"])
            original_price = float(product.get("salePrice", current_price))
            discount = ((original_price - current_price) / original_price) * 100 if original_price > current_price else 0.0
            item_data = {
                "source": "cj_uk",
                "id": product["sku"],
                "title": product["name"],
                "product_url": product["buyUrl"],
                "current_price": current_price,
                "original_price": original_price,
                "discount_percent": round(discount, 2),
                "image_url": product.get("imageUrl", None),
                "category": category,
                "manufacturer": product.get("manufacturerName", None),
                "dimensions": product.get("dimensions", None),
                "features": product.get("description", "").split(". ") if product.get("description") else []
            }
            full_item_data.append(item_data)
            time.sleep(1)
        except Exception as e:
            print(f"CJ UK Error for {sku}: {str(e)}")
    return full_item_data
# endregion Detailed Fetch

# region Search
def search_amazon_uk_discounted(browse_node_id, min_discount_percent=20):
    config = load_config()
    if not all(config.get("amazon_uk", {}).values()):
        return []
    amazon = AmazonApi(config["amazon_uk"]["ACCESS_KEY"], config["amazon_uk"]["SECRET_KEY"],
                       config["amazon_uk"]["ASSOCIATE_TAG"], config["amazon_uk"]["COUNTRY"])
    asins = []
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        return []
    try:
        search_params = {
            "BrowseNodeId": browse_node_id,
            "ItemCount": 10,
            "Resources": ["Offers.Listings.Price", "Offers.Summaries.HighestPrice"]
        }
        for page in range(1, 11):
            search_params["ItemPage"] = page
            search_result = amazon.search_items(**search_params)
            if not search_result or not search_result.items:
                break
            for item in search_result.items:
                if (item.offers and item.offers.listings and item.offers.listings[0].price and 
                    item.offers.listings[0].price.savings and 
                    item.offers.listings[0].price.savings.percentage >= min_discount_percent):
                    asins.append(item.asin)
            time.sleep(1)
        return get_amazon_uk_full_details(asins, category=category_title)
    except Exception as e:
        print(f"Amazon UK Search Error: {str(e)}")
        return []

def search_ebay_uk_discounted(browse_node_id, min_discount_percent=20):
    config = load_config()
    if not all(config.get("ebay_uk", {}).values()):
        return []
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        return []
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {"Authorization": f"Bearer {config['ebay_uk']['APP_ID']}"}
    params = {
        "q": category_title,
        "filter": "condition:NEW,availability:UK",
        "limit": "10",
        "sort": "-price"
    }
    item_ids = []
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        for item in data.get("itemSummaries", []):
            current_price = float(item["price"]["value"])
            original_price = float(item.get("originalPrice", {}).get("value", current_price))
            if original_price > current_price:
                discount = ((original_price - current_price) / original_price) * 100
                if discount >= min_discount_percent:
                    item_ids.append(item["itemId"])
        return get_ebay_uk_full_details(item_ids, category=category_title)
    except Exception as e:
        print(f"eBay UK Search Error: {str(e)}")
        return []

def search_awin_uk_discounted(browse_node_id, min_discount_percent=20):
    config = load_config()
    if not config.get("awin", {}).get("API_TOKEN"):
        return []
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        return []
    url = f"https://api.awin.com/publishers/{config['awin']['API_TOKEN']}/products"
    params = {
        "region": "UK",
        "search": category_title,
        "discount": "true"
    }
    product_ids = []
    try:
        response = requests.get(url, params=params)
        data = response.json()
        for product in data.get("products", []):
            current_price = float(product["price"]["amount"])
            original_price = float(product.get("originalPrice", current_price))
            if original_price > current_price:
                discount = ((original_price - current_price) / original_price) * 100
                if discount >= min_discount_percent:
                    product_ids.append(product["productId"])
        return get_awin_uk_full_details(product_ids, category=category_title)
    except Exception as e:
        print(f"Awin UK Search Error: {str(e)}")
        return []

def search_cj_uk_discounted(browse_node_id, min_discount_percent=20):
    config = load_config()
    if not all(config.get("cj", {}).values()):
        return []
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        return []
    url = "https://product-search.api.cj.com/v2/product-search"
    headers = {"Authorization": f"Bearer {config['cj']['API_KEY']}"}
    params = {
        "website-id": config["cj"]["WEBSITE_ID"],
        "keywords": category_title,
        "country": "UK",
        "sale-price": "true"
    }
    skus = []
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        for product in data.get("products", []):
            current_price = float(product["price"])
            original_price = float(product.get("salePrice", current_price))
            if original_price > current_price:
                discount = ((original_price - current_price) / original_price) * 100
                if discount >= min_discount_percent:
                    skus.append(product["sku"])
        return get_cj_uk_full_details(skus, category=category_title)
    except Exception as e:
        print(f"CJ UK Search Error: {str(e)}")
        return []

def search_wix_discounted(browse_node_id, min_discount_percent=20):
    """Search for discounted Wix products across all users matching browse_node_id."""
    users_settings = load_users_settings()
    all_discounted_products = []
    
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        print(f"No category title found for browse_node_id {browse_node_id}")
        return []

    for user_id, settings in users_settings.items():
        wix_client_id = settings.get("wixClientId")
        if not wix_client_id:
            print(f"No wixClientId found for user {user_id}")
            continue

        token_url = "https://www.wixapis.com/oauth2/token"
        payload = {
            "clientId": wix_client_id,
            "grantType": "anonymous"
        }
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(token_url, json=payload, headers=headers)
            if response.status_code != 200:
                print(f"Error getting token for user {user_id}: {response.status_code} - {response.text}")
                continue
            token_data = response.json()
            access_token = token_data["access_token"]
            print(f"Access Token for user {user_id}: {access_token}")
        except Exception as e:
            print(f"Token fetch error for user {user_id}: {str(e)}")
            continue

        collections_url = "https://www.wixapis.com/stores-reader/v1/collections/query"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        def fetch_collections(limit=10, offset=0):
            query_payload = {
                "query": {
                    "paging": {"limit": limit, "offset": offset}
                },
                "includeNumberOfProducts": True
            }
            response = requests.post(collections_url, headers=headers, json=query_payload)
            if response.status_code != 200:
                print(f"Error fetching collections for user {user_id}: {response.status_code} - {response.text}")
                return None
            return response.json()

        products_url = "https://www.wixapis.com/stores/v1/products/query"

        def fetch_products_for_collection(collection_id, limit=10, offset=0):
            filter_str = json.dumps({"collections.id": {"$hasSome": [collection_id]}})
            query_payload = {
                "query": {
                    "filter": filter_str,
                    "paging": {"limit": limit, "offset": offset}
                }
            }
            response = requests.post(products_url, headers=headers, json=query_payload)
            if response.status_code != 200:
                print(f"Error fetching products for collection {collection_id} for user {user_id}: {response.status_code} - {response.text}")
                return None
            return response.json()

        limit = 10
        offset = 0
        matching_collection = None

        while True:
            result = fetch_collections(limit=limit, offset=offset)
            if not result or "collections" not in result or not result["collections"]:
                break

            collections = result["collections"]
            for col in collections:
                if col["name"].lower() == category_title.lower() and not col["id"].startswith("00000000"):
                    matching_collection = col
                    break
            if matching_collection:
                break

            offset += limit
            if len(collections) < limit:
                break

        if not matching_collection:
            print(f"No matching collection found for category '{category_title}' for user {user_id}")
            continue

        collection_id = matching_collection["id"]
        offset = 0
        discounted_products = []

        while True:
            result = fetch_products_for_collection(collection_id, limit=limit, offset=offset)
            if not result or "products" not in result or not result["products"]:
                break

            products = result["products"]
            for product in products:
                current_price = float(product.get("price", {}).get("formatted", {}).get("price", "0").replace("$", "").replace("£", "").replace(",", "") or 0.0)
                original_price = float(product.get("discountedPrice", {}).get("formatted", {}).get("price", str(current_price)).replace("$", "").replace("£", "").replace(",", "") or current_price)
                if original_price > current_price:
                    discount = ((original_price - current_price) / original_price) * 100
                    if discount >= min_discount_percent:
                        base_url = (
                            product.get("productPageUrl", {}).get("base", "").rstrip("/") + "/" +
                            product.get("productPageUrl", {}).get("path", "").lstrip("/")
                        )
                        product_url = f"{base_url}?referer={user_id}"
                        discounted_products.append({
                            "source": user_id,
                            "id": product.get("id", ""),
                            "title": product.get("name", ""),
                            "product_url": product_url,
                            "current_price": current_price,
                            "original_price": original_price,
                            "discount_percent": round(discount, 2),
                            "image_url": product.get("media", {}).get("mainMedia", {}).get("thumbnail", {}).get("url", ""),
                            "qty": (
                                int(product.get("stock", {}).get("quantity", 0))
                                if product.get("stock", {}).get("trackQuantity", False)
                                else -1
                            ),
                            "category": matching_collection["name"],
                            "user_id": user_id
                        })

            offset += limit
            if len(products) < limit:
                break

        all_discounted_products.extend(discounted_products)
        print(f"Found {len(discounted_products)} discounted products for user {user_id} in category '{category_title}'")

    return all_discounted_products

def search_amazon_uk_all(browse_node_id):
    config = load_config()
    if not all(config.get("amazon_uk", {}).values()):
        return []
    amazon = AmazonApi(config["amazon_uk"]["ACCESS_KEY"], config["amazon_uk"]["SECRET_KEY"],
                       config["amazon_uk"]["ASSOCIATE_TAG"], config["amazon_uk"]["COUNTRY"])
    asins = []
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        return []
    try:
        search_params = {
            "BrowseNodeId": browse_node_id,
            "ItemCount": 10,
            "Resources": ["ItemInfo.Title", "Offers.Listings.Price", "Images.Primary.Large", "DetailPageURL"]
        }
        for page in range(1, 11):
            search_params["ItemPage"] = page
            search_result = amazon.search_items(**search_params)
            if not search_result or not search_result.items:
                break
            for item in search_result.items:
                asins.append(item.asin)
            time.sleep(1)
        return get_amazon_uk_full_details(asins, category=category_title)
    except Exception as e:
        print(f"Amazon UK Search Error: {str(e)}")
        return []

def search_ebay_uk_all(browse_node_id):
    config = load_config()
    if not all(config.get("ebay_uk", {}).values()):
        return []
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        return []
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {"Authorization": f"Bearer {config['ebay_uk']['APP_ID']}"}
    params = {
        "q": category_title,
        "filter": "condition:NEW,availability:UK",
        "limit": "10"
    }
    item_ids = []
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        for item in data.get("itemSummaries", []):
            item_ids.append(item["itemId"])
        return get_ebay_uk_full_details(item_ids, category=category_title)
    except Exception as e:
        print(f"eBay UK Search Error: {str(e)}")
        return []

def search_awin_uk_all(browse_node_id):
    config = load_config()
    if not config.get("awin", {}).get("API_TOKEN"):
        return []
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        return []
    url = f"https://api.awin.com/publishers/{config['awin']['API_TOKEN']}/products"
    params = {
        "region": "UK",
        "search": category_title
    }
    product_ids = []
    try:
        response = requests.get(url, params=params)
        data = response.json()
        for product in data.get("products", []):
            product_ids.append(product["productId"])
        return get_awin_uk_full_details(product_ids, category=category_title)
    except Exception as e:
        print(f"Awin UK Search Error: {str(e)}")
        return []

def search_cj_uk_all(browse_node_id):
    config = load_config()
    if not all(config.get("cj", {}).values()):
        return []
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        return []
    url = "https://product-search.api.cj.com/v2/product-search"
    headers = {"Authorization": f"Bearer {config['cj']['API_KEY']}"}
    params = {
        "website-id": config["cj"]["WEBSITE_ID"],
        "keywords": category_title,
        "country": "UK"
    }
    skus = []
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        for product in data.get("products", []):
            skus.append(product["sku"])
        return get_cj_uk_full_details(skus, category=category_title)
    except Exception as e:
        print(f"CJ UK Search Error: {str(e)}")
        return []

def search_wix_all(browse_node_id):
    """Search for all Wix products across all users matching browse_node_id."""
    users_settings = load_users_settings()
    all_products = []
    
    category_title = get_amazon_category_title(browse_node_id)
    if not category_title:
        print(f"No category title found for browse_node_id {browse_node_id}")
        return []

    for user_id, settings in users_settings.items():
        wix_client_id = settings.get("wixClientId")
        if not wix_client_id:
            print(f"No wixClientId found for user {user_id}")
            continue

        token_url = "https://www.wixapis.com/oauth2/token"
        payload = {
            "clientId": wix_client_id,
            "grantType": "anonymous"
        }
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(token_url, json=payload, headers=headers)
            if response.status_code != 200:
                print(f"Error getting token for user {user_id}: {response.status_code} - {response.text}")
                continue
            token_data = response.json()
            access_token = token_data["access_token"]
            print(f"Access Token for user {user_id}: {access_token}")
        except Exception as e:
            print(f"Token fetch error for user {user_id}: {str(e)}")
            continue

        collections_url = "https://www.wixapis.com/stores-reader/v1/collections/query"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

        def fetch_collections(limit=10, offset=0):
            query_payload = {
                "query": {
                    "paging": {"limit": limit, "offset": offset}
                },
                "includeNumberOfProducts": True
            }
            response = requests.post(collections_url, headers=headers, json=query_payload)
            if response.status_code != 200:
                print(f"Error fetching collections for user {user_id}: {response.status_code} - {response.text}")
                return None
            return response.json()

        products_url = "https://www.wixapis.com/stores/v1/products/query"

        def fetch_products_for_collection(collection_id, limit=10, offset=0):
            filter_str = json.dumps({"collections.id": {"$hasSome": [collection_id]}})
            query_payload = {
                "query": {
                    "filter": filter_str,
                    "paging": {"limit": limit, "offset": offset}
                }
            }
            response = requests.post(products_url, headers=headers, json=query_payload)
            if response.status_code != 200:
                print(f"Error fetching products for collection {collection_id} for user {user_id}: {response.status_code} - {response.text}")
                return None
            return response.json()

        limit = 10
        offset = 0
        matching_collection = None

        while True:
            result = fetch_collections(limit=limit, offset=offset)
            if not result or "collections" not in result or not result["collections"]:
                break

            collections = result["collections"]
            for col in collections:
                if col["name"].lower() == category_title.lower() and not col["id"].startswith("00000000"):
                    matching_collection = col
                    break
            if matching_collection:
                break

            offset += limit
            if len(collections) < limit:
                break

        if not matching_collection:
            print(f"No matching collection found for category '{category_title}' for user {user_id}")
            continue

        collection_id = matching_collection["id"]
        offset = 0
        category_products = []

        while True:
            result = fetch_products_for_collection(collection_id, limit=limit, offset=offset)
            if not result or "products" not in result or not result["products"]:
                break

            products = result["products"]
            for product in products:
                current_price = float(product.get("price", {}).get("formatted", {}).get("price", "0").replace("$", "").replace("£", "").replace(",", "") or 0.0)
                original_price = float(product.get("discountedPrice", {}).get("formatted", {}).get("price", str(current_price)).replace("$", "").replace("£", "").replace(",", "") or current_price)
                discount = ((original_price - current_price) / original_price) * 100 if original_price > current_price else 0.0
                base_url = (
                    product.get("productPageUrl", {}).get("base", "").rstrip("/") + "/" +
                    product.get("productPageUrl", {}).get("path", "").lstrip("/")
                )
                product_url = f"{base_url}?referer={user_id}"
                category_products.append({
                    "source": user_id,
                    "id": product.get("id", ""),
                    "title": product.get("name", ""),
                    "product_url": product_url,
                    "current_price": current_price,
                    "original_price": original_price,
                    "discount_percent": round(discount, 2),
                    "image_url": product.get("media", {}).get("mainMedia", {}).get("thumbnail", {}).get("url", ""),
                    "qty": (
                        int(product.get("stock", {}).get("quantity", 0))
                        if product.get("stock", {}).get("trackQuantity", False)
                        else -1
                    ),
                    "category": matching_collection["name"],
                    "user_id": user_id
                })

            offset += limit
            if len(products) < limit:
                break

        all_products.extend(category_products)
        print(f"Found {len(category_products)} products for user {user_id} in category '{category_title}'")

    return all_products
# endregion Search

# region Management Endpoints
@app.route('/')
def home():
    return render_template('login.html')  # Serves login.html at /

@app.route('/CatMgr')
def catmgr():
    return render_template('CatMgr.html')  # Serves CatMgr.html

@app.route('/affiliate')
def affiliate():
    return render_template('affiliate.html')  # Serves affiliate.html

@app.route('/listings')
def listings():
    return render_template('listings.html')  # Serves listings.html

@app.route('/test')
def test():
    return "Test route from madeira.py on 443!"

@app.route('/config', methods=['GET'])
def get_config():
    config = load_config()
    return jsonify({"status": "success", "count": len(config), "config": config})

@app.route('/config/<affiliate>', methods=['PATCH'])
def replace_config(affiliate):
    config = load_config()
    data = request.get_json()
    if not data or not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Request body must contain a dictionary of credentials"}), 400
    config[affiliate] = data
    save_config(config)
    return jsonify({
        "status": "success",
        "message": f"Credentials for {affiliate} replaced",
        "credentials": config[affiliate]
    })

@app.route('/<USERid>/user', methods=['GET'])
def get_user_settings_endpoint(USERid):
    try:
        settings = get_user_settings(USERid)
        return jsonify({
            "status": "success",
            "contact_name": settings.get("contact_name", ""),
            "website_url": settings.get("website_url", ""),
            "email_address": settings.get("email_address", ""),
            "phone_number": settings.get("phone_number", ""),
            "wixClientId": settings.get("wixClientId", "")
        })
    except Exception as e:
        print(f"Error in /<USERid>/user GET: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/<USERid>/user', methods=['PUT'])
def put_user_settings(USERid):
    if not request.json:
        return jsonify({"status": "error", "message": "Request body must contain settings"}), 400
    settings = request.json
    required_fields = ["contact_name", "website_url", "email_address", "phone_number", "wixClientId"]
    if not all(field in settings for field in required_fields):
        return jsonify({"status": "error", "message": "Settings must include all required fields"}), 400
    users_settings = load_users_settings()
    users_settings[USERid] = settings
    save_users_settings(users_settings)
    return jsonify({"status": "success", "message": f"Settings for user {USERid} replaced", "settings": settings})

@app.route('/<USERid>/user', methods=['PATCH'])
def patch_user_settings(USERid):
    if not request.json:
        return jsonify({"status": "error", "message": "Request body must contain settings"}), 400
    new_settings = request.json
    users_settings = load_users_settings()
    current_settings = users_settings.get(USERid, {})
    valid_fields = ["contact_name", "website_url", "email_address", "phone_number", "wixClientId"]
    for key in new_settings:
        if key in valid_fields:
            current_settings[key] = new_settings[key]
    users_settings[USERid] = current_settings
    save_users_settings(users_settings)
    return jsonify({"status": "success", "message": f"Settings for user {USERid} updated", "settings": current_settings})

@app.route('/<USERid>/mycategories', methods=['GET'])
def get_user_categories_endpoint(USERid):
    try:
        categories = get_user_categories(USERid)
        return jsonify({"status": "success", "count": len(categories), "categories": categories})
    except Exception as e:
        print(f"Error in /<USERid>/mycategories for USERid {USERid}: {str(e)}")
        return jsonify({"status": "error", "message": f"Failed to retrieve categories: {str(e)}"}), 500

@app.route('/<USERid>/mycategories', methods=['PUT'])
def put_user_categories(USERid):
    if not request.json or 'categories' not in request.json:
        return jsonify({"status": "error", "message": "Request body must contain 'categories' list"}), 400
    new_categories = request.json['categories']
    if not isinstance(new_categories, list):
        return jsonify({"status": "error", "message": "'categories' must be a list"}), 400
    users_data = load_users_categories()
    users_data[USERid] = new_categories
    save_users_categories(users_data)
    return jsonify({"status": "success", "message": f"Categories for user {USERid} replaced", "categories": new_categories})

@app.route('/<USERid>/mycategories', methods=['PATCH'])
def patch_user_categories(USERid):
    if not request.json or 'categories' not in request.json:
        return jsonify({"status": "error", "message": "Request body must contain 'categories' list"}), 400
    new_categories = request.json['categories']
    if not isinstance(new_categories, list):
        return jsonify({"status": "error", "message": "'categories' must be a list"}), 400
    users_data = load_users_categories()
    current_categories = set(users_data.get(USERid, []))
    current_categories.update(new_categories)
    users_data[USERid] = list(current_categories)
    save_users_categories(users_data)
    return jsonify({"status": "success", "message": f"Categories for user {USERid} patched", "categories": users_data[USERid]})

@app.route('/<USERid>/mycategories', methods=['DELETE'])
def delete_user_category(USERid):
    category_id = request.args.get('category_id')
    if not category_id:
        return jsonify({"status": "error", "message": "Query parameter 'category_id' is required"}), 400
    users_data = load_users_categories()
    if USERid in users_data and category_id in users_data[USERid]:
        users_data[USERid].remove(category_id)
        save_users_categories(users_data)
        return jsonify({"status": "success", "message": f"Category {category_id} removed for user {USERid}", "categories": users_data[USERid]})
    return jsonify({"status": "error", "message": f"Category {category_id} not found for user {USERid}"}), 404

@app.route('/categories', methods=['GET'])
def get_all_categories():
    config = load_config()
    parent_id = request.args.get('parent_id')
    amazon_config = config.get("amazon_uk", {})
    has_valid_amazon_config = all(amazon_config.get(field, "") for field in ["ACCESS_KEY", "SECRET_KEY", "ASSOCIATE_TAG", "COUNTRY"])
    
    if has_valid_amazon_config and parent_id:
        categories = get_immediate_subcategories(parent_id)
    elif not parent_id:
        categories = [{"id": cat["id"], "name": cat["name"]} for cat in PSEUDO_CATEGORIES]
    else:
        categories = find_pseudo_subcategories(parent_id, PSEUDO_CATEGORIES)
    
    return jsonify({"status": "success", "count": len(categories), "categories": categories})

@app.route('/<USERid>/products', methods=['GET'])
def get_user_product_list(USERid):
    products = get_user_products(USERid)
    return jsonify({"status": "success", "count": len(products), "products": products})

@app.route('/<USERid>/products/<product_id>', methods=['GET'])
def reduce_product_quantity(USERid, product_id):
    qty = request.args.get('qty', type=int)
    if qty is None or qty >= 0:
        return jsonify({"status": "error", "message": "Query parameter 'qty' must be a negative integer"}), 400
    users_products = load_users_products()
    if USERid not in users_products:
        return jsonify({"status": "error", "message": f"User {USERid} not found"}), 404
    current_products = users_products[USERid]
    product_to_update = next((p for p in current_products if p["id"] == product_id), None)
    if not product_to_update:
        return jsonify({"status": "error", "message": f"Product {product_id} not found for user {USERid}"}), 404
    current_qty = product_to_update["qty"]
    if current_qty != -1:
        product_to_update["qty"] = max(0, current_qty + qty)
    users_products[USERid] = current_products
    save_users_products(users_products)
    return jsonify({"status": "success", "message": f"Quantity reduced for product {product_id}", "product": product_to_update})

@app.route('/discounted-products', methods=['GET'])
def get_all_discounted_products():
    category_id = request.args.get('category_id')
    if not category_id:
        return jsonify({"status": "error", "message": "Query parameter 'category_id' is required"}), 400
    all_items = []
    config = load_config()
    search_categories = [category_id]
    
    for cat_id in search_categories:
        if all(config.get("amazon_uk", {}).values()):
            all_items.extend(search_amazon_uk_all(cat_id))
        if all(config.get("ebay_uk", {}).values()):
            all_items.extend(search_ebay_uk_all(cat_id))
        if config.get("awin", {}).get("API_TOKEN"):
            all_items.extend(search_awin_uk_all(cat_id))
        if all(config.get("cj", {}).values()):
            all_items.extend(search_cj_uk_all(cat_id))
        all_items.extend(search_wix_all(cat_id))

    return jsonify({"status": "success", "count": len(all_items), "products": all_items})

@app.route('/referal', methods=['POST'])
def handle_referral():
    """
    Handle referral callbacks from Wix scripts and store in users_settings.json.
    Expects JSON payload with either page visit or order data.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        users_settings = load_users_settings()
        
        referer = data.get("referer", "none")
        timestamp = data.get("timestamp")
        
        if not timestamp:
            return jsonify({"status": "error", "message": "Timestamp is required"}), 400

        if referer not in users_settings:
            users_settings[referer] = {
                "contact_name": "",
                "website_url": "",
                "email_address": "",
                "phone_number": "",
                "wixClientId": "",
                "referrals": {
                    "visits": [],
                    "orders": []
                }
            }
        elif "referrals" not in users_settings[referer]:
            users_settings[referer]["referrals"] = {
                "visits": [],
                "orders": []
            }

        if "page" in data:
            referral_data = {
                "page": data["page"],
                "timestamp": timestamp
            }
            users_settings[referer]["referrals"]["visits"].append(referral_data)
            print(f"Stored page visit for referer {referer}: {referral_data}")
        
        elif "orderId" in data:
            referral_data = {
                "orderId": data["orderId"],
                "buyer": data["buyer"],
                "total": data["total"],
                "timestamp": timestamp
            }
            users_settings[referer]["referrals"]["orders"].append(referral_data)
            print(f"Stored order for referer {referer}: {referral_data}")
        
        else:
            return jsonify({"status": "error", "message": "Invalid referral data format"}), 400

        save_users_settings(users_settings)
        
        return jsonify({
            "status": "success",
            "message": "Referral data recorded",
            "referer": referer,
            "timestamp": timestamp
        })

    except Exception as e:
        print(f"Error in referral endpoint: {str(e)}")
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

def load_users_settings():
    """Load users_settings.json file."""
    try:
        with open('users_settings.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get("email", "").strip()
        plain_password = data.get("password", "").strip()

        if not email or not plain_password:
            return jsonify({"status": "error", "message": "Email and password are required"}), 400

        users_settings = load_users_settings()
        matching_user_id = None
        for user_id, settings in users_settings.items():
            stored_email = settings.get("email_address", "").strip()
            if stored_email and stored_email.lower() == email.lower():
                stored_hashed_password = settings.get("password", "")
                if isinstance(stored_hashed_password, str):
                    stored_hashed_password = stored_hashed_password.encode('utf-8')
                if bcrypt.checkpw(plain_password.encode('utf-8'), stored_hashed_password):
                    matching_user_id = user_id
                    break

        if not matching_user_id:
            return jsonify({"status": "error", "message": "Invalid email or password"}), 401

        token_payload = {"userId": matching_user_id, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
        token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256")

        return jsonify({"status": "success", "message": "Login successful", "token": token, "userId": matching_user_id}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

@app.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        email = data.get("email")
        phone = data.get("phone")
        plain_password = data.get("password")

        if not email or not phone or not plain_password:
            return jsonify({"status": "error", "message": "Email, phone, and password are required"}), 400

        users_settings = load_users_settings()
        if email in users_settings:
            return jsonify({"status": "error", "message": "Email already registered"}), 400

        hashed_password = bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt())
        users_settings[email] = {
            "email_address": email,
            "phone_number": phone,
            "password": hashed_password.decode('utf-8'),
            "contact_name": "",
            "website_url": "",
            "wixClientId": "",
            "referrals": {"visits": [], "orders": []}
        }
        save_users_settings(users_settings)
        return jsonify({"status": "success", "message": "Signup successful"}), 201
    except Exception as e:
        print(f"Error in signup endpoint: {str(e)}")
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

@app.route('/update-password', methods=['POST'])
def update_password():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        email = data.get("email", "").strip()
        new_password = data.get("password", "").strip()

        if not email or not new_password:
            return jsonify({"status": "error", "message": "Email and password are required"}), 400

        users_settings = load_users_settings()
        matching_user_id = None
        for user_id, settings in users_settings.items():
            stored_email = settings.get("email_address", "").strip()
            if stored_email and stored_email.lower() == email.lower():
                matching_user_id = user_id
                break

        if not matching_user_id:
            return jsonify({"status": "error", "message": f"No user found with email '{email}'"}), 404

        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        users_settings[matching_user_id]["password"] = hashed_password.decode('utf-8')
        save_users_settings(users_settings)
        return jsonify({"status": "success", "message": f"Password updated for user with email '{email}'", "user_id": matching_user_id}), 200
    except Exception as e:
        print(f"Error in update-password endpoint: {str(e)}")
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

@app.route('/reset-password', methods=['POST'])
def reset_password():
    """Handle password reset by generating a new password and updating users_settings.json."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        email = data.get("email")
        if not email:
            return jsonify({"status": "error", "message": "Email is required"}), 400

        users_settings = load_users_settings()

        if email not in users_settings:
            return jsonify({"status": "error", "message": "Email not found"}), 404

        new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        hashed_new_password = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
        users_settings[email]["password"] = hashed_new_password

        phone = users_settings[email]["phone_number"]
        print(f"New password for {email}: {new_password} (hashed: {hashed_new_password}, would be sent to {phone})")

        save_users_settings(users_settings)
        return jsonify({"status": "success", "message": "A new password has been generated and would be sent to your phone"}), 200

    except Exception as e:
        print(f"Error in reset-password endpoint: {str(e)}")
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500

@app.route('/<USERid>/visits', methods=['GET'])
def get_user_visits(USERid):
    """Fetch the list of visits for a user from users_settings.json."""
    try:
        users_settings = load_users_settings()
        if USERid not in users_settings:
            return jsonify({"status": "error", "message": f"User {USERid} not found"}), 404

        referrals = users_settings[USERid].get("referrals", {})
        visits = referrals.get("visits", [])
        return jsonify({
            "status": "success",
            "count": len(visits),
            "visits": visits
        })
    except Exception as e:
        print(f"Error in /<USERid>/visits GET: {str(e)}")
        return jsonify({"status": "error", "message": f"Failed to retrieve visits: {str(e)}"}), 500

@app.route('/<USERid>/orders', methods=['GET'])
def get_user_orders(USERid):
    """Fetch the list of orders for a user from users_settings.json."""
    try:
        users_settings = load_users_settings()
        if USERid not in users_settings:
            return jsonify({"status": "error", "message": f"User {USERid} not found"}), 404

        referrals = users_settings[USERid].get("referrals", {})
        orders = referrals.get("orders", [])
        return jsonify({
            "status": "success",
            "count": len(orders),
            "orders": orders
        })
    except Exception as e:
        print(f"Error in /<USERid>/orders GET: {str(e)}")
        return jsonify({"status": "error", "message": f"Failed to retrieve orders: {str(e)}"}), 500

# endregion Management Endpoints

# region Velo Public Endpoints
@app.route('/<USERid>/discounted-products', methods=['GET'])
def get_user_discounted_products(USERid):
    category_id = request.args.get('category_id')
    min_discount = request.args.get('min_discount', default=20, type=int)
    root_category_ids = get_user_categories(USERid)
    all_discounted_items = []
    config = load_config()
    search_categories = [category_id] if category_id else root_category_ids
    
    for cat_id in search_categories:
        if all(config.get("amazon_uk", {}).values()):
            all_discounted_items.extend(search_amazon_uk_discounted(cat_id, min_discount))
        if all(config.get("ebay_uk", {}).values()):
            all_discounted_items.extend(search_ebay_uk_discounted(cat_id, min_discount))
        if config.get("awin", {}).get("API_TOKEN"):
            all_discounted_items.extend(search_awin_uk_discounted(cat_id, min_discount))
        if all(config.get("cj", {}).values()):
            all_discounted_items.extend(search_cj_uk_discounted(cat_id, min_discount))
        all_discounted_items.extend(search_wix_discounted(cat_id, min_discount))

    return jsonify({
        "status": "success",
        "count": len(all_discounted_items),
        "products": all_discounted_items,
        "min_discount": min_discount
    })

@app.route('/<USERid>/categories', methods=['GET'])
def get_categories(USERid):
    parent_id = request.args.get('parent_id')
    min_discount = request.args.get('min_discount', default=20, type=int)
    all_categories = []
    root_category_ids = get_user_categories(USERid)
    
    try:
        if parent_id:
            subcategories = get_immediate_subcategories(parent_id)
            if subcategories:
                subcategory_ids = [cat["id"] for cat in subcategories]
                all_categories = filter_categories_with_products(subcategory_ids, min_discount)
        else:
            all_categories = filter_categories_with_products(root_category_ids, min_discount)
        
        return jsonify({
            "status": "success",
            "count": len(all_categories),
            "categories": all_categories,
            "min_discount": min_discount
        }) if all_categories else jsonify({
            "status": "success",
            "count": 0,
            "categories": [],
            "message": f"No categories with products at {min_discount}% discount found."
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error fetching categories: {str(e)}"}), 500
# endregion Velo Public Endpoints

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)