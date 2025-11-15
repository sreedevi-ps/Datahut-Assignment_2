import scrapy
import json
import re
from urllib.parse import urljoin
from styleunion.items import ProductItem


class StyleUnionSpiderJSON(scrapy.Spider):
    """
    Extract product data from Shopify's JSON data instead of HTML
    Shopify stores product info in <script> tags as JSON
    """
    name = "styleunion_spider_json"
    allowed_domains = ["styleunion.in"]

    start_urls = [
        "https://styleunion.in/collections/new-in-women?page=1"
    ]

    custom_settings = {
        "CONCURRENT_REQUESTS": 2,
        "DOWNLOAD_DELAY": 3,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 3,
        "AUTOTHROTTLE_MAX_DELAY": 10,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 2.0,
        "DEPTH_LIMIT": 0,  # hope it will be considered as unlimited
    }

    def parse(self, response):
        """Parse listing page and follow product links"""
        
        product_links = response.css("a[href*='/products/']::attr(href)").getall()
        
        seen = set()
        for link in product_links:
            if '/products/' in link:
                base_link = link.split('?')[0]
                if base_link not in seen:
                    seen.add(base_link)
                    full_url = urljoin(response.url, base_link)
                    
                    # Request the .json version of the product page
                    json_url = full_url + '.json'
                    self.logger.info(f"Requesting JSON: {json_url}")
                    yield scrapy.Request(json_url, callback=self.parse_product_json)
        
        # Pagination
        current_page = self._extract_page_number(response.url)
        if product_links and current_page < 100:  # Limiting to 100 for 1200
            next_page_url = self._build_next_page_url(response.url, current_page)
            yield scrapy.Request(next_page_url, callback=self.parse)

    def parse_product_json(self, response):
        """Parse product from Shopify JSON API"""
        
        try:
            data = json.loads(response.text)
            product = data.get('product', {})
            
            if not product:
                self.logger.warning(f"No product data in JSON: {response.url}")
                return
            
            self.logger.info(f"Parsing product: {product.get('title')}")
            
            item = ProductItem()
            
            # Basic info
            item['product_url'] = response.url.replace('.json', '')
            item['product_name'] = product.get('title')
            item['description'] = self._clean_html(product.get('body_html', ''))
            item['currency'] = '₹'
            
            # Get first variant for default values
            variants = product.get('variants', [])
            if variants:
                first_variant = variants[0]
                item['price'] = float(first_variant.get('price', 0))
                item['sku'] = first_variant.get('sku')
            else:
                item['price'] = None
                item['sku'] = None
            
            # Extract sizes and colors from all variants
            sizes = set()
            colors = set()
            
            for variant in variants:
                option1 = variant.get('option1')  # Usually size
                option2 = variant.get('option2')  # Usually color
                option3 = variant.get('option3')  # Sometimes material/style
                
                # Try to determine which is size and which is color
                if option1:
                    # If it looks like a size (XS, S, M, L, XL, etc.)
                    if re.match(r'^(XXS|XS|S|M|L|XL|XXL|XXXL|\d+)$', str(option1).strip().upper()):
                        sizes.add(str(option1).strip())
                    else:
                        colors.add(str(option1).strip())
                
                if option2:
                    colors.add(str(option2).strip())
            
            item['size_list'] = sorted(list(sizes)) if sizes else []
            item['color_list'] = sorted(list(colors)) if colors else []
            item['size'] = item['size_list'][0] if item['size_list'] else None
            item['color'] = item['color_list'][0] if item['color_list'] else None
            
            # Images
            images = []
            for img in product.get('images', []):
                img_url = img.get('src')
                if img_url:
                    # Add https: if needed
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    # Add width parameter
                    if '?' in img_url:
                        img_url = img_url + '&width=1200'
                    else:
                        img_url = img_url + '?width=1200'
                    images.append(img_url)
            
            item['image_urls'] = images
            
            # Product details (tags, type, vendor)
            details = {}
            if product.get('product_type'):
                details['Product Type'] = product.get('product_type')
            if product.get('vendor'):
                details['Vendor'] = product.get('vendor')
            
            # Try to extract from description or tags
            tags = product.get('tags', [])
            for tag in tags:
                if ':' in str(tag):
                    key, value = tag.split(':', 1)
                    details[key.strip()] = value.strip()
            
            item['product_details'] = details
            
            # Care instructions - try to extract from description
            item['care_instructions'] = self._extract_care_instructions(product.get('body_html', ''))
            
            self.logger.info(f"Extracted: {item['product_name']} - ₹{item['price']}")
            
            yield item
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error for {response.url}: {e}")
        except Exception as e:
            self.logger.error(f"Error parsing {response.url}: {e}")

    def _clean_html(self, html_text):
        """Remove HTML tags and clean text"""
        if not html_text:
            return ""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html_text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_care_instructions(self, body_html):
        """Extract care instructions from product description"""
        if not body_html:
            return None
        
        text = self._clean_html(body_html)
        
        # Look for care instruction patterns
        care_patterns = [
            r'(Hand Wash.*?(?:Fade|Clean)\.)',
            r'(Machine Wash.*?(?:Fade|Clean)\.)',
            r'(Wash.*?Dry.*?Iron.*?)',
        ]
        
        for pattern in care_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        
        return None

    def _extract_page_number(self, url):
        """Extract current page number from URL"""
        if "page=" in url:
            try:
                return int(url.split("page=")[1].split("&")[0])
            except (ValueError, IndexError):
                return 1
        return 1

    def _build_next_page_url(self, url, current_page):
        """Build next page URL"""
        if "page=" in url:
            return url.replace(f"page={current_page}", f"page={current_page + 1}")
        else:
            separator = "&" if "?" in url else "?"
            return f"{url}{separator}page={current_page + 1}"