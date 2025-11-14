# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class StyleunionItem(scrapy.Item):
   
  product_url= scrapy.Field()
  product_name= scrapy.Field()
  price= scrapy.Field()
  sku= scrapy.Field()
  size= scrapy.Field()
  color= scrapy.Field()
  size_list= scrapy.Field()
  color_list= scrapy.Field()
  description= scrapy.Field()
  care_instructions= scrapy.Field()
  image_urls= scrapy.Field()
  product_details= scrapy.Field()
  currency= scrapy.Field()