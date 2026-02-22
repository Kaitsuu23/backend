"""
Proxy configuration for bypassing YouTube restrictions
"""
import os

# Free proxy lists (rotate these if one doesn't work)
FREE_PROXIES = [
    # Format: 'http://ip:port' or 'socks5://ip:port'
    # These are examples - you need to get fresh proxies from free proxy sites
    # Visit: https://www.proxy-list.download/HTTPS
    #        https://free-proxy-list.net/
    #        https://www.sslproxies.org/
]

# Paid proxy services (recommended for production)
# Uncomment and add your proxy if you have one
PAID_PROXY = os.environ.get('PROXY_URL', None)
# Example: 'http://username:password@proxy.example.com:8080'
# Or: 'socks5://username:password@proxy.example.com:1080'

def get_proxy():
    """Get proxy URL to use"""
    # Priority: Paid proxy > Free proxies
    if PAID_PROXY:
        print(f"Using paid proxy: {PAID_PROXY[:20]}...")  # Log proxy (hide full URL)
        return PAID_PROXY
    
    # Try free proxies (not reliable, but worth trying)
    if FREE_PROXIES:
        import random
        proxy = random.choice(FREE_PROXIES)
        print(f"Using free proxy: {proxy[:20]}...")
        return proxy
    
    print("No proxy configured!")
    return None

def get_ydl_proxy_opts():
    """Get yt-dlp proxy options"""
    proxy = get_proxy()
    if proxy:
        print(f"Proxy options: proxy={proxy[:30]}..., timeout=30")
        return {
            'proxy': proxy,
            'socket_timeout': 30,
        }
    print("No proxy options - using direct connection")
    return {}
