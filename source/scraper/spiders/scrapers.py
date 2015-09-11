import scrapy


class BaseScraper(scrapy.Spider):
    name = 'base'

    def __init__(self, allowed_domains='', start_urls=[], *args, **kwargs):
        self.allowed_domains = allowed_domains
        self.start_urls = start_urls
        super(BaseScraper, self).__init__(*args, **kwargs)

    def parse(self, response):
        print(response)
