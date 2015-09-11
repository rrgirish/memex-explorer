import scrapy


class BaseScraper(scrapy.Spider):
    name = 'base'

    def __init__(self, start_urls=[], *args, **kwargs):
        self.start_urls = start_urls
