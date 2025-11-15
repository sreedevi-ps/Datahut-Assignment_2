import scrapy
import json
import re
from urllib.parse import urljoin
from ..items import StyleunionItem


class StyleunionSpiderSpider(scrapy.Spider):
    name = "styleunion_spider"
    allowed_domains = ["styleunion.in"]
    start_urls = ["https://styleunion.in/collections/new-in-women?page=1"]

    custom_settings = {
        "FEEDS":{
            "data.json":{"format":"json","encoding":"utf8","overwrite":True},
            "data.csv":{"format":"csv","encoding":"utf8","overwrite":True},
        },
        "CLOSESPIDER_ITEMCOUNT":1200,
        "DOWNLOAD_DELAY":1.0,
        "CONCURRENT_REQUESTS":4,
        "CONCURRENT_REQUESTS_PER_DOMAIN":4,
        "RETRY_TIMES":3,
        "JOBDIR":"crawls/styleunion-1",
        "DUPEFILTER_CLASS":"scrapy.dupefilters.RFPDupeFilter",
    }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.item_count=0

    def parse(self, response):
        product_links=response.css("a.full-unstyled-link::attr(href)").getall()
        for link in product_links:
            full_url=urljoin(response.url,link)
            yield scrapy.Request(full_url,callback=self.parse_product)

        next_page=response.css("a.pagination__next::attr(href)").get()
        if next_page:
            next_url=urljoin(response.url,next_page)
            self.logger.info(f"Navigating to next page: {next_url}")
            yield scrapy.Request(next_url,callback=self.parse)
            
    def parse_product(self, response):
        item=StyleunionItem()
        item["product_url"]=response.url
        item["currency"]="₹"

        # Extract product name
        item["product_name"]=response.css("h1.product__title::text").get(default="").strip()
        # Extract price
        price_sale=response.css("span.price-item--sale::text").get()
        price_regular=response.css("span.price-item--regular::text").get()
        price_text=price_sale or price_regular 
        item["price"]=self.clean_price(price_text)
        
        # Extract JSON
        json_script=response.xpath('//script[@id="ProductJson-product-template"]/text()').get()
        product_data={}
        if json_script:
          try:
            product_data=json.loads(json_script)
          except json.JSONDecodeError:
            self.logger.error(f"Failed to parse JSON for {response.url}")

        variants=product_data.get("variants",[])
        # Extract SKU
        if variants:
            item["sku"]=variants[0].get("barcode",str(product_data.get("id",""))).strip()
        else:
            item["sku"]=response.css("span.product__sku::text").get(default="").strip() or str(product_data.get("id",""))
        # Extract sizes and colors
         # === 5. Size & Color Lists (from variants) === 
        sizes = sorted({v["option1"] for v in variants if v["option1"] and v["option1"] != "Default 
Title"}) 
        colors = sorted({v["option2"] for v in variants if v["option2"] and v["option2"] != "Default 
Title"}) 
        item["size_list"] = list(sizes) 
        item["color_list"] = list(colors) 
        item["size"] = list(sizes)[0] if sizes else "" 
        item["color"] = list(colors)[0] if colors else "" 
 
        # === 6. Image URLs (high-res, width=1200) === 
        media = product_data.get("media", []) 
        item["image_urls"] = [ 
            img["src"] for img in media 
            if "1200" in img["src"] or "width=1200" in img["src"] 
        ] 
        # Fallback: extract from srcset 
        if not item["image_urls"]: 
            srcset = response.css("img.product__media::attr(srcset)").getall() 
            urls = re.findall(r'(https?://[^\s,]+1200w)', " ".join(srcset)) 
            item["image_urls"] = urls 
 
        # === 7. Description === 
        desc_parts = response.css("div.product__description ::text").getall() 
        item["description"] = " ".join([t.strip() for t in desc_parts if t.strip()]) 
 
        # === 8. Care Instructions === 
        care_tab = response.xpath( 
            "//div[contains(@class,'accordion__title') and contains(., 'Care')]//following
sibling::div//text()" 
        ).getall() 
        item["care_instructions"] = " ".join([t.strip() for t in care_tab if t.strip()]) 
 
        # === 9. Product Details (from <p><strong>Key:</strong> Value</p>) === 
        details = {} 
        for p in response.css("div.product__details p"): 
            text = p.xpath("string()").get() 
            if ":" in text: 
                key, value = text.split(":", 1) 
                details[key.strip()] = value.strip() 
        item["product_details"] = details 
 
        # === 10. Final Logging === 
        self.item_count += 1 
        if self.item_count % 100 == 0: 
            self.logger.info(f"Scraped {self.item_count} products") 
 
        yield item 
 
    def clean_price(self, price_str): 
        """Convert '₹799' or '799' → 799.0""" 
        if not price_str: 
return None 
return float(re.sub(r"[^\d.]", "", price_str.strip()))
        

        yield item