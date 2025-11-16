from scrapy import Item, Field


class ProductItem(Item):
    product_url = Field()
    product_name = Field()
    price = Field()
    sku = Field()
    size = Field()
    color = Field()
    size_list = Field()
    color_list = Field()
    description = Field()
    care_instructions = Field()
    image_urls = Field()
    product_details = Field()
    currency = Field()

    # <-- Newline
