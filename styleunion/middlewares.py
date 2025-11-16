import time
import random
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.utils.response import response_status_message


class CustomRetryMiddleware(RetryMiddleware):
    """
    Custom retry middleware that handles 429 rate limit errors
    with exponential backoff using Twisted's async delay
    """

    def __init__(self, settings):
        super().__init__(settings)
        self.max_retry_times = settings.getint('RETRY_TIMES', 5)
        self.retry_http_codes = set(
            int(x) for x in settings.getlist(
                'RETRY_HTTP_CODES', [
                    429, 503, 504]))
        self.priority_adjust = settings.getint('RETRY_PRIORITY_ADJUST', -1)

    def process_response(self, request, response, spider):
        """Process responses and retry if needed"""

        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)

            # Special handling for 429 (rate limit)
            if response.status == 429:
                retry_times = request.meta.get('retry_times', 0) + 1

                if retry_times <= self.max_retry_times:
                    # Exponential backoff: 10, 20, 40, 80, 160 seconds
                    backoff_time = min(10 *
                                       (2 ** retry_times), 300)  # Max 5 minutes
                    jitter = random.uniform(0, 5)  # Add random jitter
                    wait_time = backoff_time + jitter

                    spider.logger.warning(
                        f"Rate limited (429) on {
                            request.url}. " f"Waiting {
                            wait_time:.1f} seconds before retry {retry_times}/{
                            self.max_retry_times}")

                    time.sleep(wait_time)

                    retryreq = request.copy()
                    retryreq.meta['retry_times'] = retry_times
                    retryreq.dont_filter = True
                    retryreq.priority = request.priority + self.priority_adjust

                    return retryreq
                else:
                    spider.logger.error(
                        f"Gave up retrying {
                            request.url} after {retry_times} times (429 rate limit)")

            # Use default retry logic for other codes
            return self._retry(request, reason, spider) or response

        return response


class RandomUserAgentMiddleware:
    """Rotate user agents to avoid detection"""

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

    def process_request(self, request, spider):
        """Randomly select a user agent for each request"""
        user_agent = random.choice(self.USER_AGENTS)
        request.headers['User-Agent'] = user_agent


class RateLimitHandlerMiddleware:
    """Add delays and handle rate limiting more gracefully"""

    def __init__(self):
        self.last_request_time = {}

    def process_request(self, request, spider):
        """Add extra delay between requests to the same domain"""
        domain = request.url.split('/')[2]

        # Ensure minimum time between requests to same domain
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]
            min_delay = 5  # Minimum 5 seconds between requests

            if elapsed < min_delay:
                time.sleep(min_delay - elapsed + random.uniform(0, 2))

        self.last_request_time[domain] = time.time()
        return None
