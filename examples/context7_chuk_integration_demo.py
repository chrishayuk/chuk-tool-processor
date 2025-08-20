#!/usr/bin/env python3
"""
Resilient Context7 Client - Enhanced Rate Limiting

This version handles aggressive rate limiting with exponential backoff,
multiple retry strategies, and intelligent request spacing.
"""

import asyncio
import json
import time
import random
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from chuk_tool_processor.mcp.setup_mcp_http_streamable import setup_mcp_http_streamable
from chuk_tool_processor.registry.provider import ToolRegistryProvider


class ResilientContext7Client:
    """
    Enhanced Context7 client with aggressive rate limiting protection.
    
    Features:
    - Exponential backoff with jitter
    - Multiple retry strategies
    - Daily request tracking
    - Intelligent request spacing
    - Comprehensive caching
    """
    
    def __init__(
        self, 
        cache_file: str = "context7_cache.json",
        initial_delay: float = 10.0,  # Start with longer delays
        max_delay: float = 120.0,    # Cap at 2 minutes
        max_retries: int = 3,
        daily_request_limit: int = 50  # Conservative daily limit
    ):
        self.cache_file = Path(cache_file)
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.daily_request_limit = daily_request_limit
        
        self.current_delay = initial_delay
        self.last_request_time = 0.0
        self.stream_manager = None
        
        # Request tracking
        self.daily_requests = 0
        self.last_reset_date = datetime.now().date()
        
        # Cache management
        self.library_cache = self._load_cache()
        self.documentation_cache = self._load_doc_cache()
        
        # Enhanced known libraries
        self.known_libraries = {
            "react": "/facebook/react",
            "next.js": "/vercel/next.js",
            "nextjs": "/vercel/next.js",
            "vue": "/vuejs/vue",
            "vue.js": "/vuejs/vue",
            "angular": "/angular/angular",
            "svelte": "/sveltejs/svelte",
            "nuxt": "/nuxt/nuxt",
            "nuxt.js": "/nuxt/nuxt",
            "supabase": "/supabase/supabase",
            "firebase": "/firebase/firebase-js-sdk",
            "tailwind": "/tailwindlabs/tailwindcss",
            "tailwindcss": "/tailwindlabs/tailwindcss",
            "bootstrap": "/twbs/bootstrap",
            "mongodb": "/mongodb/docs",
            "express": "/expressjs/express",
            "fastapi": "/tiangolo/fastapi",
            "django": "/django/django",
            "flask": "/pallets/flask",
            "prisma": "/prisma/prisma",
            "trpc": "/trpc/trpc",
            "zod": "/colinhacks/zod",
            "typescript": "/microsoft/typescript",
            "node": "/nodejs/node",
            "nodejs": "/nodejs/node",
            "webpack": "/webpack/webpack",
            "vite": "/vitejs/vite",
            "rollup": "/rollup/rollup",
            "esbuild": "/evanw/esbuild",
            "parcel": "/parcel-bundler/parcel",
            "redux": "/reduxjs/redux",
            "mobx": "/mobxjs/mobx",
            "axios": "/axios/axios",
            "lodash": "/lodash/lodash",
            "moment": "/moment/moment",
            "date-fns": "/date-fns/date-fns",
            "chartjs": "/chartjs/chart-js",
            "d3": "/d3/d3",
            "threejs": "/mrdoob/three-js",
            "electron": "/electron/electron",
            "gatsby": "/gatsbyjs/gatsby",
            "remix": "/remix-run/remix",
            "astro": "/withastro/astro"
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def initialize(self):
        """Initialize the Context7 connection."""
        servers = [{
            "name": "context7",
            "url": "https://mcp.context7.com/mcp"
        }]
        
        _, self.stream_manager = await setup_mcp_http_streamable(
            servers=servers,
            namespace="context7",
            connection_timeout=30.0,
            default_timeout=90.0,  # Longer timeout for rate-limited responses
            enable_retries=True,
            max_retries=1  # Reduce retries to minimize rate limiting
        )
        
        # Reset daily counter if needed
        self._check_daily_reset()
        
        print("✅ Resilient Context7 client initialized")
        print(f"📊 Daily requests used: {self.daily_requests}/{self.daily_request_limit}")
    
    async def close(self):
        """Clean up resources."""
        if self.stream_manager:
            await self.stream_manager.close()
        self._save_cache()
        self._save_doc_cache()
        print("🧹 Resilient Context7 client closed")
    
    def _check_daily_reset(self):
        """Reset daily counter if it's a new day."""
        today = datetime.now().date()
        if today > self.last_reset_date:
            self.daily_requests = 0
            self.last_reset_date = today
            self.current_delay = self.initial_delay  # Reset delay
            print(f"🌅 New day: Reset request counter and delays")
    
    def _check_daily_limit(self) -> bool:
        """Check if we've exceeded daily request limit."""
        self._check_daily_reset()
        return self.daily_requests >= self.daily_request_limit
    
    async def _smart_rate_limit_delay(self, is_retry: bool = False):
        """
        Intelligent rate limiting with exponential backoff and jitter.
        """
        if self._check_daily_limit():
            print(f"⚠️ Daily request limit reached ({self.daily_request_limit}). Waiting until tomorrow.")
            raise RuntimeError("Daily request limit exceeded")
        
        # Calculate delay
        base_delay = self.current_delay
        if is_retry:
            # Exponential backoff for retries
            base_delay = min(base_delay * 2, self.max_delay)
            self.current_delay = base_delay
        
        # Add jitter to avoid thundering herd
        jitter = random.uniform(0.8, 1.2)
        actual_delay = base_delay * jitter
        
        # Consider time since last request
        elapsed = time.time() - self.last_request_time
        if elapsed < actual_delay:
            wait_time = actual_delay - elapsed
            print(f"⏱️ Smart rate limiting: waiting {wait_time:.1f}s (base: {base_delay:.1f}s)")
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()
        self.daily_requests += 1
    
    async def _get_tool(self, tool_name: str):
        """Get a tool from the registry."""
        registry = await ToolRegistryProvider.get_registry()
        tool = await registry.get_tool(tool_name, "context7")
        if not tool:
            raise RuntimeError(f"Tool not found: context7:{tool_name}")
        return tool
    
    async def _execute_with_retry(self, tool_name: str, **params) -> Tuple[bool, Optional[str]]:
        """
        Execute a tool with intelligent retry logic.
        
        Returns:
            (success: bool, result: Optional[str])
        """
        tool = await self._get_tool(tool_name)
        
        for attempt in range(self.max_retries + 1):
            try:
                # Apply rate limiting
                await self._smart_rate_limit_delay(is_retry=attempt > 0)
                
                # Execute the tool
                result = await tool.execute(**params)
                
                # Check for rate limiting
                if "rate limited" in str(result).lower():
                    if attempt < self.max_retries:
                        print(f"   ⚠️ Rate limited (attempt {attempt + 1}/{self.max_retries + 1}). Backing off...")
                        # Increase delay for next attempt
                        self.current_delay = min(self.current_delay * 1.5, self.max_delay)
                        continue
                    else:
                        print(f"   ❌ Rate limited after {self.max_retries + 1} attempts")
                        return False, None
                
                # Success - reduce delay for future requests
                if self.current_delay > self.initial_delay:
                    self.current_delay = max(self.current_delay * 0.9, self.initial_delay)
                
                return True, str(result)
                
            except Exception as e:
                if attempt < self.max_retries:
                    print(f"   ⚠️ Error (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                    continue
                else:
                    print(f"   ❌ Failed after {self.max_retries + 1} attempts: {e}")
                    return False, None
        
        return False, None
    
    async def search_library(self, library_name: str) -> Optional[str]:
        """
        Search for a library with comprehensive caching and fallbacks.
        """
        # Check cache first
        cache_key = library_name.lower().strip()
        if cache_key in self.library_cache:
            print(f"📋 Using cached library ID for '{library_name}': {self.library_cache[cache_key]}")
            return self.library_cache[cache_key]
        
        # Check known libraries
        if cache_key in self.known_libraries:
            library_id = self.known_libraries[cache_key]
            print(f"📋 Using known library ID for '{library_name}': {library_id}")
            # Cache it
            self.library_cache[cache_key] = library_id
            return library_id
        
        # Check daily limit before making API call
        if self._check_daily_limit():
            print(f"⚠️ Daily limit reached, using fallback for '{library_name}'")
            return self._get_fallback_library_id(library_name)
        
        # Perform actual search
        print(f"🔍 Searching for library: {library_name}")
        
        success, result = await self._execute_with_retry(
            "resolve-library-id",
            libraryName=library_name,
            timeout=60.0
        )
        
        if success and result:
            # Parse the result to extract library ID
            library_id = self._extract_library_id(result)
            if library_id:
                print(f"   ✅ Found library ID: {library_id}")
                # Cache the result
                self.library_cache[cache_key] = library_id
                return library_id
        
        # Fallback
        print(f"   ⚠️ Search failed or no results, using fallback")
        return self._get_fallback_library_id(library_name)
    
    def _extract_library_id(self, response: str) -> Optional[str]:
        """Extract library ID from search response."""
        lines = response.split('\n')
        for line in lines[:30]:  # Check more lines
            line = line.strip()
            if line.startswith('/') and line.count('/') >= 2:
                # Extract just the /org/project part
                parts = line.split()
                if parts and len(parts[0].split('/')) >= 3:
                    return parts[0]
        return None
    
    def _get_fallback_library_id(self, library_name: str) -> Optional[str]:
        """Get fallback library ID with intelligent matching."""
        # Try variations of the name
        variations = [
            library_name.lower(),
            library_name.lower().replace('-', ''),
            library_name.lower().replace('.js', ''),
            library_name.lower().replace('js', ''),
            library_name.lower().replace('.', ''),
            library_name.lower().replace(' ', ''),
        ]
        
        for variation in variations:
            if variation in self.known_libraries:
                fallback_id = self.known_libraries[variation]
                print(f"   📋 Using fallback library ID: {fallback_id}")
                # Cache the mapping
                self.library_cache[library_name.lower().strip()] = fallback_id
                return fallback_id
        
        print(f"   ❌ No fallback available for '{library_name}'")
        return None
    
    async def get_documentation(
        self, 
        library_id: str, 
        topic: str = None, 
        tokens: int = 8000,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Get documentation with intelligent caching and rate limiting.
        """
        # Create cache key
        cache_key = f"{library_id}:{topic or 'general'}:{tokens}"
        
        # Check cache first
        if use_cache and cache_key in self.documentation_cache:
            cache_entry = self.documentation_cache[cache_key]
            # Check if cache is still fresh (1 day)
            if time.time() - cache_entry['timestamp'] < 86400:
                print(f"📋 Using cached documentation for {library_id}")
                return cache_entry['content']
        
        # Check daily limit
        if self._check_daily_limit():
            print(f"⚠️ Daily limit reached, skipping documentation request")
            return None
        
        # Ensure reasonable token range
        tokens = max(1000, min(tokens, 10000))
        
        print(f"📚 Getting documentation for: {library_id}")
        if topic:
            print(f"   Topic: {topic}")
        print(f"   Tokens: {tokens}")
        
        params = {
            "context7CompatibleLibraryID": library_id,
            "tokens": tokens,
            "timeout": 90.0
        }
        if topic:
            params["topic"] = topic
        
        success, result = await self._execute_with_retry("get-library-docs", **params)
        
        if success and result and len(result) > 100:
            print(f"   ✅ Retrieved {len(result):,} characters")
            code_examples = result.count('```')
            if code_examples > 0:
                print(f"   📖 Code examples: {code_examples}")
            
            # Cache the result
            if use_cache:
                self.documentation_cache[cache_key] = {
                    'content': result,
                    'timestamp': time.time()
                }
            
            return result
        else:
            print(f"   ❌ Documentation request failed or returned minimal content")
            return None
    
    async def get_library_documentation(
        self, 
        library_name: str, 
        topic: str = None, 
        tokens: int = 8000,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        High-level method: search for library and get its documentation.
        """
        # Get library ID
        library_id = await self.search_library(library_name)
        if not library_id:
            return None
        
        # Get documentation
        return await self.get_documentation(library_id, topic, tokens, use_cache)
    
    def _load_cache(self) -> Dict[str, str]:
        """Load library cache from file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_cache(self):
        """Save library cache to file."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.library_cache, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}")
    
    def _load_doc_cache(self) -> Dict[str, Dict]:
        """Load documentation cache from file."""
        doc_cache_file = self.cache_file.with_suffix('.docs.json')
        if doc_cache_file.exists():
            try:
                with open(doc_cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_doc_cache(self):
        """Save documentation cache to file."""
        try:
            doc_cache_file = self.cache_file.with_suffix('.docs.json')
            with open(doc_cache_file, 'w') as f:
                json.dump(self.documentation_cache, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save doc cache: {e}")
    
    def get_status(self) -> Dict:
        """Get client status and statistics."""
        self._check_daily_reset()
        return {
            "daily_requests": self.daily_requests,
            "daily_limit": self.daily_request_limit,
            "current_delay": self.current_delay,
            "cached_libraries": len(self.library_cache),
            "cached_docs": len(self.documentation_cache),
            "known_libraries": len(self.known_libraries),
            "requests_remaining": max(0, self.daily_request_limit - self.daily_requests)
        }


# Example usage with enhanced resilience

async def example_resilient_workflow():
    """Example of resilient workflow that handles aggressive rate limiting."""
    print("🌐 Resilient Context7 Workflow Example")
    print("=" * 50)
    
    async with ResilientContext7Client(
        initial_delay=15.0,  # Start with 15 second delays
        daily_request_limit=20  # Conservative limit
    ) as client:
        
        # Show status
        status = client.get_status()
        print(f"📊 Client status: {status['requests_remaining']} requests remaining today")
        
        # Example 1: Get React documentation (will likely use cache/known library)
        print("\n📖 Getting React hooks documentation...")
        react_docs = await client.get_library_documentation(
            "react",
            topic="useState useEffect useCallback useMemo",
            tokens=6000
        )
        
        if react_docs:
            print(f"   ✅ Success: {len(react_docs):,} characters")
            # Show preview
            preview = react_docs[:200].replace('\n', ' ') + "..."
            print(f"   📄 Preview: {preview}")
        
        # Example 2: Try a different library
        print("\n📖 Getting Vue.js documentation...")
        vue_docs = await client.get_library_documentation(
            "vue.js",
            topic="composition api setup",
            tokens=5000
        )
        
        if vue_docs:
            print(f"   ✅ Success: {len(vue_docs):,} characters")
        
        # Show final status
        final_status = client.get_status()
        print(f"\n📊 Final status: {final_status['requests_remaining']} requests remaining")
        print(f"💾 Cache stats: {final_status['cached_libraries']} libraries, {final_status['cached_docs']} docs")


if __name__ == "__main__":
    asyncio.run(example_resilient_workflow())