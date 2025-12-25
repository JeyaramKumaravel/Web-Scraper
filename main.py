"""
Moviesda Web Scraper
Scrapes movie download links (MP4) and images (JPG) from moviesda15.com
Follows all redirects to get the final direct MP4 URLs
"""

import os
import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class MoviesdaScraper:
    """Web scraper for Moviesda website."""
    
    def __init__(self, delay: float = None):
        """
        Initialize the scraper.
        
        Args:
            delay: Delay between requests in seconds (to be respectful to the server)
                   If None, uses REQUEST_DELAY from .env or defaults to 1.0
        """
        # Load configuration from environment
        self.base_url = os.getenv("BASE_URL", "https://moviesda15.com")
        self.delay = delay if delay is not None else float(os.getenv("REQUEST_DELAY", "1.0"))
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
    
    def _get_soup(self, url: str) -> Optional[BeautifulSoup]:
        """
        Fetch a URL and return a BeautifulSoup object.
        
        Args:
            url: URL to fetch
            
        Returns:
            BeautifulSoup object or None if request fails
        """
        try:
            time.sleep(self.delay)
            response = self.session.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            return BeautifulSoup(response.text, "lxml")
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def _make_absolute_url(self, href: str) -> str:
        """Convert relative URL to absolute URL."""
        if href.startswith("http"):
            return href
        return urljoin(self.base_url, href)
    
    def search_movie(self, query: str, base_url: str = None, max_results: int = 10) -> list[dict]:
        """
        Search for movies by name using A-Z index.
        Supports both moviesda and isaidub websites.
        
        Args:
            query: Movie name to search for
            base_url: Base URL to search on (if None, uses self.base_url)
            max_results: Maximum number of results to return
            
        Returns:
            List of matching movies with title and url
        """
        if base_url is None:
            base_url = self.base_url
        
        # Strip year from query if present (e.g., "Ted (2012)" -> "Ted")
        query_clean = re.sub(r"\s*\(\d{4}\)\s*$", "", query).strip()
        query_lower = query_clean.lower().strip()
        first_letter = query_lower[0] if query_lower else 'a'
        
        # Detect which site we're searching
        is_isaidub = "isaidub" in base_url
        
        # Build search URL based on site
        if is_isaidub:
            # isaidub uses /tamil-atoz-dubbed-movies/{letter} pattern
            if first_letter.isalpha():
                search_url = f"{base_url}/tamil-atoz-dubbed-movies/{first_letter}"
            else:
                search_url = f"{base_url}/tamil-atoz-dubbed-movies/"
        else:
            # moviesda uses /tamil-movies/{letter}/ pattern
            if first_letter.isalpha():
                search_url = f"{base_url}/tamil-movies/{first_letter}/"
            else:
                search_url = f"{base_url}/tamil-atoz-movies/"
        
        print(f"Searching for '{query_clean}' on: {base_url}")
        print(f"Search URL: {search_url}")
        
        matches = []
        page = 1
        
        while len(matches) < max_results:
            if page == 1:
                url = search_url
            else:
                # Different pagination for different sites
                if is_isaidub:
                    # isaidub A-Z uses /{letter}/{page} format
                    url = f"{search_url}/{page}"
                else:
                    url = f"{search_url}?page={page}"
            
            soup = self._get_soup(url)
            if not soup:
                break
            
            found_any = False
            
            # Find movie links
            for div in soup.select("div.f"):
                link = div.find("a", href=True)
                if link:
                    href = link.get("href", "")
                    text = link.get_text(strip=True)
                    
                    # Check for movie URLs (both sites)
                    is_movie = (
                        ("-tamil-movie" in href or "-movie" in href or "-tamil-web-series" in href or
                         "-tamil-dubbed-movie" in href or "-tamil-dubbed-web-series" in href)
                        and text
                    )
                    
                    if is_movie:
                        found_any = True
                        # Check if query matches the movie title
                        if query_lower in text.lower():
                            # Make URL absolute
                            if href.startswith("http"):
                                full_url = href
                            else:
                                full_url = urljoin(base_url, href)
                            
                            if not any(m["url"] == full_url for m in matches):
                                matches.append({
                                    "title": text,
                                    "url": full_url
                                })
                                print(f"Found: {text}")
                                
                                if len(matches) >= max_results:
                                    break
            
            if not found_any or len(matches) >= max_results:
                break
            
            page += 1
            if page > 5:  # Limit pages to search
                break
        
        return matches
    
    def smart_search_movie(self, query: str, base_url: str = None, max_results: int = 5) -> list[dict]:
        """
        Smart search for movies by guessing URL patterns and verifying they exist.
        This is a fallback when A-Z index search fails.
        
        Args:
            query: Movie name to search for
            base_url: Target site URL (e.g., https://isaidub.love)
            max_results: Maximum number of results to return
            
        Returns:
            List of matching movies with title and url
        """
        if base_url is None:
            base_url = self.base_url
        
        # Strip year from query if present (e.g., "Ted (2012)" -> "Ted")
        year_match = re.search(r"\((\d{4})\)", query)
        year = year_match.group(1) if year_match else None
        query_clean = re.sub(r"\s*\(\d{4}\)\s*$", "", query).strip()
        
        # Detect site type
        is_isaidub = "isaidub" in base_url
        
        print(f"Smart search: '{query_clean}' (year: {year}) on {base_url}")
        
        matches = []
        
        # Generate possible URL patterns
        movie_slug = query_clean.lower().replace(" ", "-").replace("'", "")
        
        # Common URL patterns for both sites
        possible_urls = []
        
        if is_isaidub:
            if year:
                possible_urls.append(f"{base_url}/movie/{movie_slug}-{year}-tamil-dubbed-movie/")
            # Try without year too
            possible_urls.append(f"{base_url}/movie/{movie_slug}-tamil-dubbed-movie/")
        else:
            # Moviesda patterns - try -movie/ first (preferred), then -tamil-movie/
            if year:
                possible_urls.append(f"{base_url}/{movie_slug}-{year}-movie/")
                possible_urls.append(f"{base_url}/{movie_slug}-{year}-tamil-movie/")
            possible_urls.append(f"{base_url}/{movie_slug}-movie/")
            possible_urls.append(f"{base_url}/{movie_slug}-tamil-movie/")
        
        # Try each URL pattern
        for test_url in possible_urls:
            print(f"Trying URL: {test_url}")
            soup = self._get_soup(test_url)
            
            if soup:
                # Page exists! Extract title from page
                title_tag = soup.find("title")
                if title_tag:
                    page_title = title_tag.get_text(strip=True)
                    # Extract movie name from page title
                    title = re.sub(r"\s*(Tamil Dubbed Movie Download|Download|isaiDub|Moviesda).*", "", page_title, flags=re.IGNORECASE).strip()
                    if not title:
                        title = f"{query_clean} ({year})" if year else query_clean
                    
                    matches.append({
                        "title": title,
                        "url": test_url
                    })
                    print(f"Found via URL guess: {title}")
                    
                    if len(matches) >= max_results:
                        break
        
        return matches
    
    def get_movies_from_category(self, category_url: str, max_pages: int = 1) -> list[dict]:
        """
        Get all movies from a category page.
        Supports both moviesda and isaidub websites.
        
        Args:
            category_url: URL of the category page (e.g., tamil-2025-movies)
            max_pages: Maximum number of pages to scrape
            
        Returns:
            List of movie dictionaries with title and url
        """
        movies = []
        
        # Detect which site we're scraping
        is_isaidub = "isaidub" in category_url
        
        for page in range(1, max_pages + 1):
            if page == 1:
                url = category_url
            else:
                # Different pagination for different sites
                if is_isaidub:
                    url = f"{category_url}?get-page={page}"
                else:
                    url = f"{category_url}?page={page}"
            
            print(f"Scraping category page {page}: {url}")
            soup = self._get_soup(url)
            
            if not soup:
                break
            
            # Find movie links using div.f a selector
            for div in soup.select("div.f"):
                link = div.find("a", href=True)
                if link:
                    href = link.get("href", "")
                    text = link.get_text(strip=True)
                    
                    # Filter for movie/series pages
                    # moviesda: -tamil-movie/, -tamil-web-series/
                    # isaidub: /movie/...-tamil-dubbed-movie/
                    is_movie = (
                        ("-tamil-movie" in href or "-tamil-web-series" in href or 
                         "-tamil-dubbed-movie" in href or "-tamil-dubbed-web-series" in href)
                        and text
                    )
                    
                    if is_movie:
                        # Make URL absolute using category URL as base
                        if href.startswith("http"):
                            full_url = href
                        else:
                            from urllib.parse import urlparse
                            parsed = urlparse(category_url)
                            base = f"{parsed.scheme}://{parsed.netloc}"
                            full_url = urljoin(base, href)
                        
                        # Avoid duplicates
                        if not any(m["url"] == full_url for m in movies):
                            movies.append({
                                "title": text,
                                "url": full_url
                            })
        
        return movies
    
    def get_movie_images(self, soup: BeautifulSoup, movie_url: str = None) -> dict:
        """
        Extract movie poster and screenshot images from the movie page.
        
        Args:
            soup: BeautifulSoup object of the movie page
            movie_url: URL of the movie page (to determine correct base URL)
            
        Returns:
            Dictionary with poster_url and screenshots list
        """
        images = {
            "poster_url": None,
            "screenshots": []
        }
        
        # Determine base URL from movie_url
        if movie_url:
            from urllib.parse import urlparse
            parsed = urlparse(movie_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            base_url = self.base_url
        
        # Find all images on the page
        for img in soup.find_all("img"):
            src = img.get("src", "")
            alt = img.get("alt", "")
            
            # Make URL absolute using correct base URL
            if src:
                if src.startswith("http"):
                    abs_src = src
                else:
                    abs_src = urljoin(base_url, src)
            else:
                continue
            
            # Movie poster - usually in /uploads/posters/ directory
            if "/uploads/posters/" in abs_src or "poster" in alt.lower():
                images["poster_url"] = abs_src
                print(f"Found poster: {abs_src}")
            
            # Screenshots - usually in /uploads/screen_shots/ directory
            elif "/uploads/screen_shots/" in abs_src or "screenshot" in alt.lower():
                images["screenshots"].append(abs_src)
        
        # Also check picture elements for poster
        for picture in soup.find_all("picture"):
            source = picture.find("source")
            img = picture.find("img")
            
            if source:
                srcset = source.get("srcset", "")
                if srcset and "/uploads/posters/" in srcset:
                    src_url = srcset.split()[0]
                    if src_url.startswith("http"):
                        images["poster_url"] = src_url
                    else:
                        images["poster_url"] = urljoin(base_url, src_url)
            
            if img and not images["poster_url"]:
                src = img.get("src", "")
                if src and "/uploads/posters/" in src:
                    if src.startswith("http"):
                        images["poster_url"] = src
                    else:
                        images["poster_url"] = urljoin(base_url, src)
        
        return images
    
    def get_quality_options(self, movie_url: str) -> tuple[list[dict], dict]:
        """
        Get available quality options for a movie and also extract images.
        
        Args:
            movie_url: URL of the movie page
            
        Returns:
            Tuple of (list of quality options, images dict)
        """
        print(f"Getting quality options: {movie_url}")
        soup = self._get_soup(movie_url)
        
        if not soup:
            return [], {}
        
        # Extract images from the movie page
        images = self.get_movie_images(soup, movie_url)
        
        qualities = []
        
        # Determine base URL from movie_url
        from urllib.parse import urlparse
        parsed = urlparse(movie_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # First, look for "Original" or "Season" links which lead to quality/episode selection
        # Patterns: -original-movie (moviesda), -movie-original (isaidub), -season- (TV series), /movie/{id}/ (isaidub numeric)
        for div in soup.select("div.f"):
            link = div.find("a", href=True)
            if link:
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                # Check for Original quality selection page (URL patterns)
                if "-original-movie" in href or "-movie-original" in href:
                    if href.startswith("http"):
                        full_url = href
                    else:
                        full_url = urljoin(base_url, href)
                    return self._get_quality_from_original_page(full_url, base_url), images
                
                # Check for isaidub numeric pattern: /movie/{id}/ with "Original" in text
                if re.match(r".*/movie/\d+/?$", href) and "original" in text.lower():
                    if href.startswith("http"):
                        full_url = href
                    else:
                        full_url = urljoin(base_url, href)
                    print(f"Following original link (numeric): {full_url}")
                    return self._get_quality_from_original_page(full_url, base_url), images
                
                # Check for Season links (TV series) - follow to get episodes
                if "-season-" in href and "-dubbed-movie" in href:
                    if href.startswith("http"):
                        season_url = href
                    else:
                        season_url = urljoin(base_url, href)
                    print(f"Following season link: {season_url}")
                    # Get episodes from season page
                    season_qualities = self._get_episodes_from_season_page(season_url, base_url)
                    if season_qualities:
                        return season_qualities, images
                
                # Also check for direct quality links by URL pattern
                if any(q in href for q in ["-1080p-", "-720p-", "-480p-", "-360p-"]):
                    if href.startswith("http"):
                        full_url = href
                    else:
                        full_url = urljoin(base_url, href)
                    qualities.append({
                        "quality": text,
                        "url": full_url
                    })
                
                # Check for isaidub numeric URLs with resolution in text (e.g., "Ted (480x320)")
                # These are quality options that lead directly to download pages
                elif re.match(r".*/movie/\d+/?$", href) and re.search(r"\d+x\d+", text):
                    if href.startswith("http"):
                        full_url = href
                    else:
                        full_url = urljoin(base_url, href)
                    qualities.append({
                        "quality": text,
                        "url": full_url,
                        "is_direct_download": True  # These go straight to download page
                    })
        
        # If no qualities found and URL contains "season", try scanning for moviesda episode URLs
        if not qualities and "season" in movie_url.lower() and "moviesda" in base_url:
            print("No qualities found, scanning for moviesda episode URLs...")
            episodes = self._scan_moviesda_episodes(movie_url, base_url)
            if episodes:
                qualities = episodes
        
        return qualities, images
    
    def _scan_moviesda_episodes(self, movie_url: str, base_url: str) -> list[dict]:
        """
        Scan for moviesda web series episodes by trying sequential episode URLs.
        Moviesda episodes are at /download/{series-name}-season-{n}-epi-{n}/
        
        Args:
            movie_url: URL of the series page
            base_url: Base URL of the site
            
        Returns:
            List of episode qualities
        """
        episodes = []
        
        # Extract series name and season from URL
        # Try multiple URL formats:
        # /{series-name}-season-01-2025-tamil-movie/
        # /{series-name}-season-01-2025-movie-tamil-movie/
        # /{series-name}-season-01-tamil-movie/
        match = re.search(r"/([^/]+?)-season-(\d+)(?:-\d{4})?(?:-[^/]+)?-tamil-movie/?$", movie_url)
        if not match:
            # Try simpler pattern
            match = re.search(r"/([^/]+)-season-(\d+)", movie_url)
        
        if not match:
            print(f"Could not parse series URL: {movie_url}")
            return []
        
        series_slug = match.group(1)
        season_num = match.group(2)
        
        print(f"Scanning episodes for: {series_slug} Season {season_num}")
        
        # Try up to 20 episodes
        for epi_num in range(1, 21):
            epi_str = str(epi_num).zfill(2)
            episode_url = f"{base_url}/download/{series_slug}-season-{season_num}-epi-{epi_str}/"
            
            print(f"Trying episode URL: {episode_url}")
            soup = self._get_soup(episode_url)
            
            if soup:
                # Check if page has download links
                download_links = soup.select("div.dlink a")
                if download_links:
                    # Extract title from page
                    title_tag = soup.find("title")
                    episode_title = f"Episode {epi_num}"
                    if title_tag:
                        episode_title = title_tag.get_text(strip=True).split(" - ")[0]
                    
                    episodes.append({
                        "quality": episode_title,
                        "url": episode_url,
                        "is_direct_download": True
                    })
                    print(f"Found: {episode_title}")
                else:
                    # No download links, likely end of series
                    break
            else:
                # Episode doesn't exist, likely end of series
                break
        
        # Reverse for ascending order if needed
        # episodes.reverse()
        
        return episodes
    
    def _get_quality_from_original_page(self, original_url: str, base_url: str = None) -> list[dict]:
        """
        Get quality options from the "Original" page.
        
        Args:
            original_url: URL of the original quality page
            base_url: Base URL to use for constructing absolute URLs
            
        Returns:
            List of quality options
        """
        print(f"Getting qualities from original page: {original_url}")
        soup = self._get_soup(original_url)
        
        if not soup:
            return []
        
        if not base_url:
            from urllib.parse import urlparse
            parsed = urlparse(original_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        qualities = []
        
        for div in soup.select("div.f"):
            link = div.find("a", href=True)
            if link:
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                # Look for quality pages by URL pattern (e.g., -1080p-, -720p-)
                if any(q in href for q in ["-1080p-", "-720p-", "-480p-", "-360p-"]):
                    if href.startswith("http"):
                        full_url = href
                    else:
                        full_url = urljoin(base_url, href)
                    qualities.append({
                        "quality": text,
                        "url": full_url
                    })
                # Also check for isaidub numeric URLs with quality in text (e.g., "Leo (720p HD)")
                elif re.match(r".*/movie/\d+/?$", href) and re.search(r"(1080p|720p|480p|360p)", text, re.IGNORECASE):
                    if href.startswith("http"):
                        full_url = href
                    else:
                        full_url = urljoin(base_url, href)
                    qualities.append({
                        "quality": text,
                        "url": full_url
                    })
        
        return qualities
    
    def _get_episodes_from_season_page(self, season_url: str, base_url: str = None) -> list[dict]:
        """
        Get episode downloads from a season page (for TV series).
        Episodes have direct download links like /download/page/{id}/
        
        Args:
            season_url: URL of the season page
            base_url: Base URL to use for constructing absolute URLs
            
        Returns:
            List of episode qualities with downloads
        """
        print(f"Getting episodes from season page: {season_url}")
        soup = self._get_soup(season_url)
        
        if not soup:
            return []
        
        if not base_url:
            from urllib.parse import urlparse
            parsed = urlparse(season_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        episodes = []
        current_episode = None
        
        # Parse list items for episode info and download links
        for li in soup.find_all("li"):
            # Check for download links in list items
            link = li.find("a", href=True)
            if link:
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                # Direct download link
                if "/download/" in href:
                    if href.startswith("http"):
                        download_url = href
                    else:
                        download_url = urljoin(base_url, href)
                    
                    # Extract episode info from text (e.g., "Wednesday 2025 Season 02 (Epi 08)")
                    episode_name = text if text else f"Episode"
                    
                    current_episode = {
                        "quality": episode_name,
                        "url": download_url,  # For direct download, URL is the download page
                        "is_direct_download": True
                    }
                    episodes.append(current_episode)
            
            # Check for file size info
            li_text = li.get_text(strip=True)
            size_match = re.search(r"File Size[:\s]*(\d+\.?\d*\s*[GMKT]B)", li_text, re.IGNORECASE)
            if size_match and current_episode:
                current_episode["file_size"] = size_match.group(1)
        
        # Reverse to get ascending order (Ep 01, 02, 03...)
        episodes.reverse()
        
        return episodes

    def get_download_links(self, quality_url: str) -> list[dict]:
        """
        Get download links from a quality page.
        
        Args:
            quality_url: URL of the quality selection page
            
        Returns:
            List of download links with filename, size, and urls
        """
        print(f"Getting download links: {quality_url}")
        soup = self._get_soup(quality_url)
        
        if not soup:
            return []
        
        # Determine base URL from quality_url
        from urllib.parse import urlparse
        parsed = urlparse(quality_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        downloads = []
        
        # Look for download links using li a.coral selector
        for link in soup.select("li a.coral"):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            
            if "/download/" in href:
                if href.startswith("http"):
                    full_url = href
                else:
                    full_url = urljoin(base_url, href)
                download_info = {
                    "filename": text,
                    "intermediate_url": full_url,
                    "direct_links": []
                }
                downloads.append(download_info)
        
        # Also try looking for any links containing .mp4 in text
        if not downloads:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                if "/download/" in href and (".mp4" in text.lower() or "hd" in text.lower()):
                    if href.startswith("http"):
                        full_url = href
                    else:
                        full_url = urljoin(base_url, href)
                    download_info = {
                        "filename": text,
                        "intermediate_url": full_url,
                        "direct_links": []
                    }
                    downloads.append(download_info)
        
        # Extract file size if available
        for li in soup.find_all("li"):
            text = li.get_text(strip=True)
            size_match = re.search(r"File Size[:\s]*(\d+\.?\d*\s*[GMKT]B)", text, re.IGNORECASE)
            if size_match and downloads:
                downloads[-1]["file_size"] = size_match.group(1)
        
        # Now get the actual download server links and follow through to final MP4
        for download in downloads:
            if "intermediate_url" in download:
                server_links = self._get_server_links(download["intermediate_url"])
                download["direct_links"] = server_links
        
        return downloads
    
    def _get_server_links(self, intermediate_url: str) -> list[dict]:
        """
        Get the actual download server links from the intermediate download page.
        This follows the redirect chain to get the final MP4 URLs.
        
        Args:
            intermediate_url: URL of the intermediate download page
            
        Returns:
            List of server links with final MP4 URLs
        """
        print(f"Getting server links (Level 1): {intermediate_url}")
        soup = self._get_soup(intermediate_url)
        
        if not soup:
            return []
        
        servers = []
        
        # Use div.dlink a selector for download server links
        for div in soup.select("div.dlink"):
            link = div.find("a", href=True)
            if link:
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                if href.startswith("http"):
                    # This is Level 1 server link (e.g., download.moviespage.site)
                    # Now follow to Level 2 to get the final MP4 URL
                    final_mp4_url = self._get_final_mp4_url(href)
                    
                    servers.append({
                        "server_name": text,
                        "level1_url": href,
                        "mp4_url": final_mp4_url
                    })
                    
                    # Only need one server usually (they're the same)
                    if final_mp4_url:
                        break
        
        # Fallback: look for any external download links
        if not servers:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                
                if ("download" in text.lower() or "server" in text.lower()):
                    # Exclude main site domains, but include external servers
                    if href.startswith("http") and "moviesda15.com" not in href and "isaidub.love" not in href:
                        final_mp4_url = self._get_final_mp4_url(href)
                        servers.append({
                            "server_name": text,
                            "level1_url": href,
                            "mp4_url": final_mp4_url
                        })
                        if final_mp4_url:
                            break
        
        return servers
    
    def _get_final_mp4_url(self, level1_url: str) -> Optional[str]:
        """
        Follow the Level 1 server URL to get the final direct MP4 URL.
        
        Supports:
        - Moviesda: downloadpage.site -> moviespage.site -> biggshare.xyz/hotshare.link
        - Isaidub: dubmv.top -> dubshare.one
        
        Args:
            level1_url: URL from the first download server page
            
        Returns:
            Direct MP4 URL or None if not found
        """
        print(f"Getting final MP4 URL (Level 2): {level1_url}")
        soup = self._get_soup(level1_url)
        
        if not soup:
            return None
        
        # CDN domains that serve MP4 files
        cdn_domains = ["biggshare", "hotshare", "dubshare", "dubmv", "uptodub", "uptomkv"]
        
        # Look for download server links on this page
        for div in soup.select("div.dlink"):
            link = div.find("a", href=True)
            if link:
                href = link.get("href", "")
                
                # Check if this is the final MP4 URL
                is_mp4 = ".mp4" in href.lower()
                is_cdn = any(cdn in href.lower() for cdn in cdn_domains)
                
                if is_mp4 or is_cdn:
                    print(f"Found MP4 URL: {href}")
                    return href
                
                # If it's another redirect, follow it (Level 3)
                if href.startswith("http") and "download" in href.lower():
                    final_url = self._follow_final_redirect(href)
                    if final_url:
                        return final_url
        
        # Also check for direct mp4 links anywhere
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            is_mp4 = ".mp4" in href.lower()
            is_cdn = any(cdn in href.lower() for cdn in cdn_domains)
            
            if is_mp4 or is_cdn:
                print(f"Found MP4 URL: {href}")
                return href
        
        return None
    
    def _follow_final_redirect(self, url: str) -> Optional[str]:
        """
        Follow a final redirect to get the MP4 URL if needed.
        
        Args:
            url: URL that might redirect to MP4
            
        Returns:
            MP4 URL or None
        """
        print(f"Following redirect (Level 3): {url}")
        soup = self._get_soup(url)
        
        if not soup:
            return None
        
        # CDN domains that serve MP4 files
        cdn_domains = ["biggshare", "hotshare", "dubshare", "uptodub", "uptomkv"]
        
        # Look for MP4 links
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            is_mp4 = ".mp4" in href.lower()
            is_cdn = any(cdn in href.lower() for cdn in cdn_domains)
            
            if is_mp4 or is_cdn:
                return href
        
        return None
    
    def scrape_movie(self, movie_url: str) -> dict:
        """
        Scrape all download information for a single movie including images.
        
        Args:
            movie_url: URL of the movie page
            
        Returns:
            Dictionary with movie info, images, and all download links
        """
        result = {
            "movie_url": movie_url,
            "poster_url": None,
            "screenshots": [],
            "qualities": []
        }
        
        # Extract movie title from URL
        title_match = re.search(r"/([^/]+)-\d{4}-tamil", movie_url)
        if title_match:
            result["title"] = title_match.group(1).replace("-", " ").title()
        
        # Get quality options and images
        qualities, images = self.get_quality_options(movie_url)
        
        # Add images to result
        result["poster_url"] = images.get("poster_url")
        result["screenshots"] = images.get("screenshots", [])
        
        for quality in qualities:
            # Check if this is a direct download (TV series episode or resolution page)
            if quality.get("is_direct_download"):
                # The URL points to a page with download links (like episodes or resolution pages)
                # Extract downloads from this page
                print(f"Getting downloads from: {quality['url']}")
                
                # Get the page
                quality_soup = self._get_soup(quality["url"])
                if quality_soup:
                    downloads = []
                    
                    from urllib.parse import urlparse
                    parsed = urlparse(quality["url"])
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    
                    # First check if this page has div.dlink server links directly (moviesda episode pages)
                    dlink_servers = quality_soup.select("div.dlink a")
                    if dlink_servers:
                        # This is a moviesda download page - get server links directly
                        server_links = self._get_server_links(quality["url"])
                        
                        downloads.append({
                            "filename": quality["quality"],
                            "intermediate_url": quality["url"],
                            "direct_links": server_links,
                            "file_size": ""
                        })
                    else:
                        # Otherwise parse list items for download info (isaidub style)
                        current_download = None
                        
                        for li in quality_soup.find_all("li"):
                            link = li.find("a", href=True)
                            if link:
                                href = link.get("href", "")
                                text = link.get_text(strip=True)
                                
                                if "/download/" in href:
                                    if href.startswith("http"):
                                        download_url = href
                                    else:
                                        download_url = urljoin(base_url, href)
                                    
                                    # Get MP4 URL from download page
                                    server_links = self._get_server_links(download_url)
                                    
                                    current_download = {
                                        "filename": text,
                                        "intermediate_url": download_url,
                                        "direct_links": server_links,
                                        "file_size": ""
                                    }
                                    downloads.append(current_download)
                            
                            # Check for file size info
                            li_text = li.get_text(strip=True)
                            size_match = re.search(r"File Size[:\s]*(\d+\.?\d*\s*[GMKT]B)", li_text, re.IGNORECASE)
                            if size_match and current_download:
                                current_download["file_size"] = size_match.group(1)
                    
                    quality_info = {
                        "quality": quality["quality"],
                        "downloads": downloads
                    }
                else:
                    quality_info = {
                        "quality": quality["quality"],
                        "downloads": []
                    }
            else:
                # Normal flow - get download links from quality page
                quality_info = {
                    "quality": quality["quality"],
                    "downloads": self.get_download_links(quality["url"])
                }
            result["qualities"].append(quality_info)
        
        return result
    
    def scrape_category(self, category_url: str, max_pages: int = 1, max_movies: int = 10) -> list[dict]:
        """
        Scrape all movies from a category.
        
        Args:
            category_url: URL of the category (e.g., https://moviesda15.com/tamil-2025-movies/)
            max_pages: Maximum number of category pages to scrape
            max_movies: Maximum number of movies to scrape
            
        Returns:
            List of movie data with download links
        """
        movies = self.get_movies_from_category(category_url, max_pages)
        print(f"\nFound {len(movies)} movies")
        
        results = []
        
        for i, movie in enumerate(movies[:max_movies]):
            print(f"\n--- Scraping movie {i+1}/{min(len(movies), max_movies)}: {movie['title']} ---")
            movie_data = self.scrape_movie(movie["url"])
            movie_data["title"] = movie["title"]
            results.append(movie_data)
        
        return results


def main():
    """Main function to run the scraper."""
    # All configuration now comes from .env file
    scraper = MoviesdaScraper()
    
    # Load settings from environment
    # Support comma-separated list of category URLs for multi-site scraping
    category_urls_str = os.getenv("CATEGORY_URLS", os.getenv("CATEGORY_URL", "https://moviesda15.com/tamil-2025-movies/"))
    category_urls = [url.strip() for url in category_urls_str.split(",") if url.strip()]
    
    max_pages = int(os.getenv("MAX_PAGES", "1"))
    max_movies = int(os.getenv("MAX_MOVIES", "5"))
    search_query = os.getenv("SEARCH_QUERY", "").strip()
    
    print("=" * 60)
    print("Web Scraper - Moviesda + Isaidub - MP4 + Images")
    print("=" * 60)
    
    results = []
    
    if search_query:
        # Search mode - parse comma-separated list of movie names
        search_list = [q.strip() for q in search_query.split(",") if q.strip()]
        
        # Extract base URLs from category URLs
        base_urls = []
        for cat_url in category_urls:
            from urllib.parse import urlparse
            parsed = urlparse(cat_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            if base not in base_urls:
                base_urls.append(base)
        
        print(f"\nSearch List: {search_list}")
        print(f"Searching on {len(base_urls)} sites:")
        for url in base_urls:
            print(f"  - {url}")
        print("Note: This is for educational purposes only.\n")
        
        # Search for each movie in the list
        for idx, movie_name in enumerate(search_list):
            print(f"\n{'='*50}")
            print(f"[{idx+1}/{len(search_list)}] Searching for: '{movie_name}'")
            print(f"{'='*50}")
            
            # Search on all base URLs until we find a match
            found = False
            for base_url in base_urls:
                # First try A-Z index search
                matching_movies = scraper.search_movie(movie_name, base_url=base_url, max_results=1)
                
                # If not found, try smart search with Google site: operator
                if not matching_movies:
                    print(f"A-Z index search failed, trying smart search...")
                    matching_movies = scraper.smart_search_movie(movie_name, base_url=base_url, max_results=1)
                
                if matching_movies:
                    movie = matching_movies[0]  # Get first match
                    print(f"\n--- Scraping: {movie['title']} ---")
                    movie_data = scraper.scrape_movie(movie["url"])
                    movie_data["title"] = movie["title"]
                    results.append(movie_data)
                    found = True
                    break  # Found on this site, move to next movie
            
            if not found:
                print(f"\nNo movies found matching '{movie_name}' on any site")
    else:
        # Category mode - scrape from all category URLs
        print(f"\nCategory URLs: {len(category_urls)} sites")
        for url in category_urls:
            print(f"  - {url}")
        print(f"Max Pages: {max_pages} | Max Movies per site: {max_movies}")
        print("Note: This is for educational purposes only.\n")
        
        # Scrape from each category URL
        for cat_idx, category_url in enumerate(category_urls):
            print(f"\n{'='*60}")
            print(f"[SITE {cat_idx+1}/{len(category_urls)}] {category_url}")
            print(f"{'='*60}")
            
            site_results = scraper.scrape_category(
                category_url=category_url,
                max_pages=max_pages,
                max_movies=max_movies
            )
            results.extend(site_results)
    
    if not results:
        print("\nNo movies to save.")
        return
    
    # Save results to JSON
    output_file = "scraped_movies.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Save results to separate M3U playlists (one per movie)
    m3u_dir = "playlists"
    save_to_m3u(results, m3u_dir)
    
    print(f"\n{'=' * 60}")
    print(f"JSON saved to: {output_file}")
    print(f"M3U Playlists saved to: {m3u_dir}/ folder")
    print(f"Total movies scraped: {len(results)}")
    print("=" * 60)
    
    # Print summary
    for movie in results:
        print(f"\n[MOVIE] {movie.get('title', 'Unknown')}")
        
        # Print images
        if movie.get("poster_url"):
            print(f"   [POSTER] {movie['poster_url']}")
        if movie.get("screenshots"):
            print(f"   [SCREENSHOTS] {len(movie['screenshots'])} found")
            for i, screenshot in enumerate(movie["screenshots"][:3]):  # Show first 3
                print(f"      [{i+1}] {screenshot}")
        
        # Print qualities and downloads
        for quality in movie.get("qualities", []):
            print(f"   [QUALITY] {quality['quality']}")
            for dl in quality.get("downloads", []):
                print(f"      [FILE] {dl.get('filename', 'Unknown')}")
                if "file_size" in dl:
                    print(f"         Size: {dl['file_size']}")
                for server in dl.get("direct_links", []):
                    if server.get("mp4_url"):
                        print(f"         [MP4] {server['mp4_url']}")
                    else:
                        print(f"         [LINK] {server.get('level1_url', 'N/A')}")


def save_to_m3u(results: list[dict], output_dir: str = "playlists") -> None:
    """
    Save scraped results to separate M3U playlist files per movie.
    Each movie gets its own .m3u file named after the movie title.
    
    Format:
    #EXTM3U
    #EXTINF:-1 group-title="Series" tvg-logo="...",Display Title
    https://...mp4
    
    Args:
        results: List of movie data dictionaries
        output_dir: Directory to save M3U files (default: "playlists")
    """
    import os
    from urllib.parse import urlparse, unquote
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    created_files = []
    
    for movie in results:
        title = movie.get("title", "Unknown Movie")
        poster_url = movie.get("poster_url", "")
        
        # Skip movies with no qualities/downloads
        if not movie.get("qualities"):
            continue
        
        # Count total videos for this movie
        total_videos = 0
        for quality in movie.get("qualities", []):
            for dl in quality.get("downloads", []):
                total_videos += len(dl.get("direct_links", []))
        
        # Set group title based on video count
        content_type = "Series" if total_videos > 4 else "Movies"
        
        # Sanitize title for filename (remove invalid characters)
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_', '(', ')')).strip()
        safe_title = safe_title.replace(' ', '_')
        
        # Create M3U file for this movie
        m3u_path = os.path.join(output_dir, f"{safe_title}.m3u")
        
        with open(m3u_path, "w", encoding="utf-8") as f:
            # Write M3U header
            f.write("#EXTM3U\n")
            
            for quality in movie.get("qualities", []):
                for dl in quality.get("downloads", []):
                    for server in dl.get("direct_links", []):
                        mp4_url = server.get("mp4_url")
                        
                        if mp4_url:
                            # Extract quality from MP4 URL filename (e.g., 1080p, 720p, 360p)
                            parsed_url = urlparse(mp4_url)
                            mp4_filename = unquote(parsed_url.path.split("/")[-1])
                            
                            # Find quality pattern in filename
                            quality_match = re.search(r'(1080p|720p|480p|360p)', mp4_filename, re.IGNORECASE)
                            quality_str = quality_match.group(1) if quality_match else ""
                            
                            # Check if HD is in filename
                            hd_suffix = " HD" if "HD" in mp4_filename else ""
                            
                            # Create clean display title: "Movie Title Year Quality HD"
                            display_title = f"{title} {quality_str}{hd_suffix}".strip()
                            
                            # Write EXTINF line with metadata in the exact format:
                            # #EXTINF:-1 group-title="..." tvg-logo="...",Title
                            f.write(f'#EXTINF:-1 group-title="{content_type}"')
                            
                            # Add tvg-logo for poster if available
                            if poster_url:
                                f.write(f' tvg-logo="{poster_url}"')
                            
                            f.write(f",{display_title}\n")
                            
                            # Write the actual URL
                            f.write(f"{mp4_url}\n")
        
        created_files.append(m3u_path)
        print(f"Created: {m3u_path}")
    
    print(f"\nTotal M3U files created: {len(created_files)} in '{output_dir}/' folder")


if __name__ == "__main__":
    main()

