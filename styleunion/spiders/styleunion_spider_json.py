import scrapy
import json
import re
from urllib.parse import urljoin
from styleunion.items import ProductItem
from scrapy.exceptions import CloseSpider


class StyleUnionSpiderJSON(scrapy.Spider):
   
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
        "DEPTH_LIMIT": 100,
        # Export settings
        "FEEDS": {
            "output.json": {
                "format": "json",
                "encoding": "utf8",
                "indent": 2,
                "overwrite": True,
            },
            "output.csv": {
                "format": "csv",
                "encoding": "utf8",
                "overwrite": True,
            },
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_count = 0
        self.max_products = 1000

    def parse(self, response):
        

        if self.product_count >= self.max_products:
            self.logger.info(
                f"Reached maximum products limit: {
                    self.max_products}")
            raise CloseSpider(f'Reached maximum products: {self.max_products}')

        product_links = response.css(
            "a[href*='/products/']::attr(href)").getall()

        seen = set()
        for link in product_links:
            if self.product_count >= self.max_products:
                break

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
        if self.product_count < self.max_products and product_links:
            current_page = self._extract_page_number(response.url)
            if current_page < 100:  # Safety limit
                next_page_url = self._build_next_page_url(
                    response.url, current_page)
                self.logger.info(f"Moving to page {current_page + 1}")
                yield scrapy.Request(next_page_url, callback=self.parse)

    def parse_product_json(self, response):
        """Parse product from Shopify JSON API"""

        if self.product_count >= self.max_products:
            return

        try:
            data = json.loads(response.text)
            product = data.get('product', {})

            if not product:
                self.logger.warning(f"No product data in JSON: {response.url}")
                return

            if self.product_count >= self.max_products:
                self.logger.info("Reached 1000 items. Stopping spider.")
                raise CloseSpider("Reached 1000 items")

            self.product_count += 1

            item = ProductItem()

            # Basic info
            item['product_url'] = response.url.replace('.json', '')
            item['product_name'] = product.get('title')
            item['currency'] = '₹'

            # Extract product details and description
            body_html = product.get('body_html', '')
            product_details_dict, description_str = self._extract_details_and_description(
                body_html)
            item['product_details'] = product_details_dict
            item['description'] = description_str

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
                option1 = variant.get('option1')
                option2 = variant.get('option2')
                option3 = variant.get('option3')

                # Try to determine which is size and which is color
                if option1:
                    option1_upper = str(option1).strip().upper()
                    # If it looks like a size (XS, S, M, L, XL, etc.)
                    if re.match(
                        r'^(XXS|XS|S|M|L|XL|XXL|XXXL|\d+)$',
                            option1_upper):
                        sizes.add(str(option1).strip())
                    else:
                        colors.add(str(option1).strip())

                if option2:
                    option2_str = str(option2).strip()
                    option2_upper = option2_str.upper()
                    # Check if option2 is a size
                    if re.match(
                        r'^(XXS|XS|S|M|L|XL|XXL|XXXL|\d+)$',
                            option2_upper):
                        sizes.add(option2_str)
                    else:
                        colors.add(option2_str)

                if option3:
                    colors.add(str(option3).strip())

            # Sort sizes properly (XS, S, M, L, XL, XXL)
            size_order = {
                'XXS': 1,
                'XS': 2,
                'S': 3,
                'M': 4,
                'L': 5,
                'XL': 6,
                'XXL': 7,
                'XXXL': 8}
            sorted_sizes = sorted(
                list(sizes),
                key=lambda x: size_order.get(x.upper(), 999)
            )

            item['size_list'] = sorted_sizes if sorted_sizes else []
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

            # Care instructions
            item['care_instructions'] = self._extract_care_instructions(
                body_html)

            self.logger.info(
                f"✓ Extracted: {item['product_name']} - ₹{item['price']}")

            yield item

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error for {response.url}: {e}")
        except Exception as e:
            self.logger.error(f"Error parsing {response.url}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def _extract_details_and_description(self, body_html):
        """
        Extract product details as dict and description from body HTML.
        Returns: (product_details_dict, description_string)
        """
        if not body_html:
            return {}, ""

        text = self._clean_html(body_html)

        # Pattern to find "Product Details" section and extract until
        # "Description"
        details_match = re.search(
            r'Product Details[:\s]*(.*?)(?:Description[:\s]+(.*))?$',
            text,
            re.IGNORECASE | re.DOTALL
        )

        product_details_dict = {}
        description = ""

        if details_match:
            product_details_text = details_match.group(1).strip()
            description = details_match.group(
                2).strip() if details_match.group(2) else ""

            # Parse product details into dictionary
            # Split by common separators and newlines
            # First, try to split by multiple spaces or newlines followed by
            # capital letters
            segments = re.split(
                r'\n+|(?<=\w)\s{2,}(?=[A-Z])',
                product_details_text)

            for segment in segments:
                segment = segment.strip()
                if not segment:
                    continue

                # Try to split by colon
                if ':' in segment:
                    parts = segment.split(':', 1)
                    key = parts[0].strip()
                    value = parts[1].strip() if len(parts) > 1 else ""
                    if key and value:
                        product_details_dict[key] = value
                else:
                    # Try to match pattern "Key Value" where Key contains
                    # letters/spaces
                    match = re.match(
                        r'^([A-Za-z\s]+?)\s+([\w%\s,/\-]+)$', segment)
                    if match:
                        key = match.group(1).strip()
                        value = match.group(2).strip()
                        if key and value and len(
                                key) < 50:  # Avoid false matches
                            product_details_dict[key] = value

            # Clean description - remove care instructions
            if description:
                # Remove "Wash and Care" section
                description = re.sub(
                    r'Wash and Care[:\s]*.*?(?:Fade|Clean)\.?',
                    '',
                    description,
                    flags=re.IGNORECASE | re.DOTALL
                )
                # Clean up extra whitespace
                description = re.sub(r'\s+', ' ', description).strip()
        else:
            # Fallback: Look for common product detail keywords anywhere in
            # text
            detail_keywords = [
                'Fabric Type',
                'Weave Type',
                'Pattern',
                'Length',
                'Fit',
                'Waist Rise',
                'Pockets',
                'Cut Shape',
                'Neckline',
                'Sleeve']

            for keyword in detail_keywords:
                pattern = rf'{keyword}[:\s]+([^\n\.]+)'
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    # Clean up value
                    value = re.sub(r'\s+', ' ', value)
                    product_details_dict[keyword] = value

            # If we found details, try to extract description as the rest
            if product_details_dict:
                # Try to find "Description" section
                desc_match = re.search(
                    r'Description[:\s]+(.*)', text, re.IGNORECASE | re.DOTALL)
                if desc_match:
                    description = desc_match.group(1).strip()
                    # Remove care instructions
                    description = re.sub(
                        r'Wash and Care[:\s]*.*?(?:Fade|Clean)\.?',
                        '',
                        description,
                        flags=re.IGNORECASE | re.DOTALL
                    )
                    description = re.sub(r'\s+', ' ', description).strip()
            else:
                # No details found, whole text might be description
                description = text

        return product_details_dict, description

    def _clean_html(self, html_text):
        """Remove HTML tags and clean text"""
        if not html_text:
            return ""
        # Remove script and style tags with their content
        html_text = re.sub(
            r'<script[^>]*>.*?</script>',
            '',
            html_text,
            flags=re.DOTALL | re.IGNORECASE)
        html_text = re.sub(
            r'<style[^>]*>.*?</style>',
            '',
            html_text,
            flags=re.DOTALL | re.IGNORECASE)
        # Replace common HTML elements with appropriate text markers
        text = re.sub(r'<br\s*/?>', '\n', html_text)
        text = re.sub(r'</p>', '\n\n', text)
        text = re.sub(r'<li>', '\n- ', text)
        text = re.sub(r'</li>', '\n', text)
        # Remove all remaining HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        # Normalize whitespace but keep paragraph breaks
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)
        # Clean up extra spaces within lines
        text = re.sub(r' +', ' ', text)
        return text.strip()

    def _extract_care_instructions(self, body_html):
        """Extract care instructions from product description"""
        if not body_html:
            return None

        text = self._clean_html(body_html)

        # Look for "Wash and Care" section with various patterns
        care_patterns = [
            r'(?:Wash and Care|Care Instructions?|Washing Instructions?)[:\s]+((?:(?:Hand|Machine)?\s*Wash|Do Not|Dry|Iron|Bleach|Clean|Hang|Fade|Tumble)[^\n]*(?:\n(?:(?:Hand|Machine)?\s*Wash|Do Not|Dry|Iron|Bleach|Clean|Hang|Fade|Tumble)[^\n]*)*)',
            r'((?:Hand Wash|Machine Wash)[^\.]+\.(?:[^\.]+\.)*?(?:Fade|Clean)[^\.]*\.)',
        ]

        for pattern in care_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                care_text = match.group(1).strip()
                # Clean up and format
                care_text = re.sub(r'\s+', ' ', care_text)
                care_text = re.sub(r'\s*\.\s*', '. ', care_text)
                # Remove trailing incomplete sentences
                sentences = care_text.split('.')
                valid_sentences = []
                for sentence in sentences:
                    sentence = sentence.strip()
                    if sentence and re.search(
                        r'(wash|dry|iron|bleach|clean|fade|hang|tumble)',
                        sentence,
                            re.IGNORECASE):
                        valid_sentences.append(sentence)

                if valid_sentences:
                    return '. '.join(
                        valid_sentences) + ('.' if not valid_sentences[-1].endswith('.') else '')

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
            return url.replace(
                f"page={current_page}", f"page={
                    current_page + 1}")
        else:
            separator = "&" if "?" in url else "?"
            return f"{url}{separator}page={current_page + 1}"
