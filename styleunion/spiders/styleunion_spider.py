import scrapy
import re
from urllib.parse import urljoin
from styleunion.items import ProductItem


class StyleUnionSpider(scrapy.Spider):
    name = "styleunion_spider"
    allowed_domains = ["styleunion.in"]

    start_urls = [
        "https://styleunion.in/collections/new-in-women?page=1"
    ]

    custom_settings = {
        "CONCURRENT_REQUESTS": 1,
        "DOWNLOAD_DELAY": 5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 5,
        "AUTOTHROTTLE_MAX_DELAY": 15,
    }

    def parse(self, response):
        """Parse listing page and follow product links"""
        
        # Try multiple selectors for product links
        product_links = (
            response.css("a.product-card__link::attr(href)").getall() or
            response.css("a.card-wrapper::attr(href)").getall() or
            response.css("div.product-card a::attr(href)").getall() or
            response.css("a[href*='/products/']::attr(href)").getall() or
            response.xpath("//a[contains(@href, '/products/')]/@href").getall()
        )
        
        self.logger.info(f"Found {len(product_links)} product links on {response.url}")
        
        if not product_links:
            self.logger.warning(f"No product links found! Saving response to debug.html")
            with open('debug.html', 'wb') as f:
                f.write(response.body)
        
        # Remove duplicates and extract base product URLs
        seen = set()
        unique_links = []
        for link in product_links:
            if '/products/' in link:
                # Get base URL without variant/query parameters
                base_link = link.split('?')[0]
                if base_link not in seen:
                    seen.add(base_link)
                    unique_links.append(base_link)
        
        self.logger.info(f"After deduplication: {len(unique_links)} unique products")
        
        for link in unique_links:
            full_url = urljoin(response.url, link)
            self.logger.info(f"Following product URL: {full_url}")
            yield scrapy.Request(full_url, callback=self.parse_product)

        # Pagination
        if unique_links:
            current_page = self._extract_page_number(response.url)
            next_page_url = self._build_next_page_url(response.url, current_page)
            
            self.logger.info(f"Moving to next page: {next_page_url}")
            yield scrapy.Request(next_page_url, callback=self.parse)

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

    def parse_product(self, response):
        """Extract product data"""
        
        self.logger.info(f"Parsing product: {response.url}")
        
        item = ProductItem()
        item["product_url"] = response.url

        # NAME
        item["product_name"] = (
            response.css("h1.product-title::text").get() or
            response.css("h1.product__title::text").get() or
            response.css("h1::text").get() or
            response.xpath("//h1/text()").get()
        )
        if item["product_name"]:
            item["product_name"] = item["product_name"].strip()

        # PRICE - extract numeric value
        price_text = (
            response.css("span.price-item--regular::text").get() or
            response.css("span.price::text").get() or
            response.css("span.product-price::text").get() or
            response.css("div.price span::text").get() or
            response.xpath("//span[contains(@class, 'price')]/text()").get()
        )
        item["price"] = self._extract_price(price_text)

        # SKU
        sku = (
            response.css("span.product-sku::text").get() or
            response.css("span.sku::text").get() or
            response.xpath("//span[contains(@class, 'sku')]/text()").get() or
            response.xpath("//dt[contains(text(), 'SKU')]/following-sibling::dd/text()").get()
        )
        item["sku"] = sku.strip() if sku else None

        # IMAGES - filter out placeholder and unrelated images
        images = (
            response.css("img.product-media__img::attr(src)").getall() or
            response.css("img.product__media-item::attr(src)").getall() or
            response.css("div.product-images img::attr(src)").getall() or
            response.xpath("//div[contains(@class, 'product')]//img/@src").getall()
        )
        
        item["image_urls"] = self._clean_image_urls(images, response.url)

        # DESCRIPTION - better parsing
        item["description"] = self._extract_description(response)

        # SIZE AND COLOR EXTRACTION
        sizes, colors = self._extract_variants(response)
        item["size_list"] = sizes
        item["color_list"] = colors
        item["size"] = sizes[0] if sizes else None
        item["color"] = colors[0] if colors else None

        # CARE INSTRUCTIONS - extract from description
        item["care_instructions"] = self._extract_care_instructions(response)

        # PRODUCT DETAILS - extract from structured data
        item["product_details"] = self._extract_product_details(response)

        # CURRENCY
        item["currency"] = "₹"

        self.logger.info(f"Extracted item: {item.get('product_name', 'NO NAME')}")

        yield item

    def _extract_price(self, price_text):
        """Extract numeric price from text"""
        if not price_text:
            return None
        
        # Remove currency symbols and extract number
        price_match = re.search(r'[\d,]+(?:\.\d{2})?', price_text.replace(',', ''))
        if price_match:
            return float(price_match.group())
        return None

    def _clean_image_urls(self, images, base_url):
        """Clean and filter image URLs"""
        abs_images = []
        seen = set()
        
        for src in images:
            if not src:
                continue
                
            # Skip placeholder images
            if 'no-image' in src.lower():
                continue
            
            # Make absolute URL
            if src.startswith("//"):
                img_url = "https:" + src
            elif src.startswith("/"):
                img_url = urljoin(base_url, src)
            elif src.startswith("http"):
                img_url = src
            else:
                continue
            
            # Add width parameter if needed
            if "width=" not in img_url:
                if "?" in img_url:
                    img_url = img_url.split("?")[0] + "?width=1200"
                    if "v=" in src:
                        version = re.search(r'v=(\d+)', src)
                        if version:
                            img_url = img_url.replace("?width=", f"?v={version.group(1)}&width=")
                else:
                    img_url = img_url + "?width=1200"
            
            # Only add main product images (filter out related product thumbnails)
            if img_url not in seen and ('width=1200' in img_url or 'width=800' in img_url):
                if 'width=300' not in img_url:  # Skip thumbnail images
                    seen.add(img_url)
                    abs_images.append(img_url)
        
        return abs_images[:10]  # Limit to first 10 images

    def _extract_description(self, response):
        """Extract and clean product description"""
        # Try to find description section
        desc_selectors = [
            "//div[contains(@class, 'description')]//p//text()",
            "//div[@class='product__description']//text()",
            "//div[contains(text(), 'Description')]/following-sibling::*//text()",
        ]
        
        desc_text = []
        for selector in desc_selectors:
            texts = response.xpath(selector).getall()
            if texts:
                desc_text = texts
                break
        
        if not desc_text:
            # Fallback to getting all text
            desc_text = response.css("div.product__description *::text").getall()
        
        # Clean and join
        cleaned = []
        for text in desc_text:
            text = text.strip()
            if text and len(text) > 2:
                # Skip section headers
                if text not in ['Details', 'More Info', 'Product Details', 'Wash and Care', 
                               'Made in India', 'Disclaimer', 'Description']:
                    cleaned.append(text)
        
        return " ".join(cleaned)

    def _extract_variants(self, response):
        """Extract size and color variants separately"""
        # Get all option text from select dropdown
        options = response.css("select option::text").getall()
        
        sizes = []
        colors = set()
        
        for option in options:
            option = option.strip()
            
            # Skip default options
            if not option or 'choose' in option.lower() or 'select' in option.lower():
                continue
            
            # Parse format: "SIZE / COLOR - PRICE"
            if '/' in option:
                parts = option.split('/')
                if len(parts) >= 2:
                    size = parts[0].strip()
                    color_price = parts[1].strip()
                    
                    # Extract color (before the dash)
                    if '-' in color_price:
                        color = color_price.split('-')[0].strip()
                    else:
                        color = color_price.strip()
                    
                    # Clean size (remove price if present)
                    size = re.sub(r'\s*-\s*₹[\d,]+\.?\d*', '', size).strip()
                    
                    if size and size not in sizes:
                        sizes.append(size)
                    if color:
                        colors.add(color)
            else:
                # Just a size, no color info
                size = re.sub(r'\s*-\s*₹[\d,]+\.?\d*', '', option).strip()
                if size:
                    sizes.append(size)
        
        return sizes, list(colors)

    def _extract_care_instructions(self, response):
        """Extract care instructions from description or dedicated section"""
        # Try multiple patterns
        care_patterns = [
            response.xpath("//h3[contains(translate(text(),'CARE','care'),'care')]/following-sibling::p//text()").getall(),
            response.xpath("//strong[contains(translate(text(),'CARE','care'),'care')]/parent::*/following-sibling::*//text()").getall(),
            response.xpath("//text()[contains(translate(.,'CARE','care'),'care') and contains(., 'Wash')]").getall(),
        ]
        
        for pattern_result in care_patterns:
            if pattern_result:
                care_text = " ".join([t.strip() for t in pattern_result if t.strip()])
                # Extract only the care instruction part
                if 'Hand Wash' in care_text or 'Machine Wash' in care_text or 'Dry Clean' in care_text:
                    # Clean up the text
                    care_text = re.sub(r'\s+', ' ', care_text)
                    return care_text
        
        # Fallback: search in full description
        full_text = " ".join(response.css("*::text").getall())
        care_match = re.search(r'(Hand Wash.*?(?:Fade|Clean)\.)', full_text, re.IGNORECASE | re.DOTALL)
        if care_match:
            return care_match.group(1).strip()
        
        return None

    def _extract_product_details(self, response):
        """Extract product details as dictionary"""
        details = {}
        
        # Method 1: Look for "Product Details" section
        detail_texts = response.xpath(
            "//strong[contains(text(), 'Product Details')]/parent::*/following-sibling::*//text()"
        ).getall()
        
        if not detail_texts:
            # Method 2: Look in description area
            detail_texts = response.xpath(
                "//div[contains(@class, 'description')]//text()"
            ).getall()
        
        # Parse "Key: Value" format
        for text in detail_texts:
            text = text.strip()
            if ':' in text and len(text) < 100:  # Likely a detail line
                parts = text.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    if key and value and key not in ['Details', 'Description']:
                        details[key] = value
        
        return details if details else {}