import re


class CleanProductPipeline:
    """Pipeline to clean and validate scraped product data"""
    
    def process_item(self, item, spider):
        """Clean each field of the item"""
        
        # Clean product name
        if item.get('product_name'):
            item['product_name'] = self._clean_text(item['product_name'])
        
        # Ensure price is float or None
        if item.get('price'):
            if isinstance(item['price'], str):
                item['price'] = self._extract_numeric_price(item['price'])
        
        # Clean SKU
        if item.get('sku'):
            item['sku'] = self._clean_text(item['sku'])
        
        # Clean size and color
        if item.get('size'):
            item['size'] = self._clean_text(item['size'])
        
        if item.get('color'):
            item['color'] = self._clean_text(item['color'])
        
        # Clean lists
        if item.get('size_list'):
            item['size_list'] = [self._clean_text(s) for s in item['size_list'] if s]
        
        if item.get('color_list'):
            item['color_list'] = [self._clean_text(c) for c in item['color_list'] if c]
        
        # Clean description
        if item.get('description'):
            item['description'] = self._clean_description(item['description'])
        
        # Clean care instructions
        if item.get('care_instructions'):
            item['care_instructions'] = self._clean_text(item['care_instructions'])
        
        # Validate and clean image URLs
        if item.get('image_urls'):
            item['image_urls'] = self._validate_image_urls(item['image_urls'])
        
        # Clean product details dictionary
        if item.get('product_details'):
            cleaned_details = {}
            for key, value in item['product_details'].items():
                clean_key = self._clean_text(key)
                clean_value = self._clean_text(value)
                if clean_key and clean_value:
                    cleaned_details[clean_key] = clean_value
            item['product_details'] = cleaned_details
        
        return item
    
    def _clean_text(self, text):
        """Remove extra whitespace and clean text"""
        if not text:
            return text
        
        # Replace multiple spaces/newlines with single space
        text = re.sub(r'\s+', ' ', text)
        # Remove leading/trailing whitespace
        text = text.strip()
        return text
    
    def _extract_numeric_price(self, price_text):
        """Extract numeric price from text"""
        if not price_text:
            return None
        
        # Remove currency symbols and commas
        price_match = re.search(r'[\d,]+(?:\.\d{2})?', str(price_text).replace(',', ''))
        if price_match:
            return float(price_match.group())
        return None
    
    def _clean_description(self, description):
        """Clean and format description text"""
        if not description:
            return description
        
        # Remove excessive whitespace
        description = re.sub(r'\s+', ' ', description)
        
        # Remove common boilerplate text patterns
        patterns_to_remove = [
            r'Made in India.*?(?=\.|$)',
            r'Disclaimer.*?(?=\.|$)',
            r'Manufactured and Marketed By:.*?(?=\.|$)',
            r'Product color may slightly vary.*?(?=\.|$)',
        ]
        
        for pattern in patterns_to_remove:
            description = re.sub(pattern, '', description, flags=re.IGNORECASE | re.DOTALL)
        
        # Clean up extra spaces
        description = re.sub(r'\s+', ' ', description).strip()
        
        return description
    
    def _validate_image_urls(self, urls):
        """Validate and clean image URLs"""
        if not urls:
            return []
        
        clean_urls = []
        for url in urls:
            if url and isinstance(url, str):
                # Remove any whitespace
                url = url.strip()
                
                # Ensure it's a valid URL
                if url.startswith('http') and 'no-image' not in url.lower():
                    # Avoid duplicates
                    if url not in clean_urls:
                        clean_urls.append(url)
        
        return clean_urls