"""
Asynchronous REST client for Neatsvor API.
Exact copy of neatsvor_rest.py logic, but with async/await.
"""

import hashlib
import logging
from typing import Any, Dict, Optional, List
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientTimeout, ClientResponseError

_LOGGER = logging.getLogger(__name__)


class NeatsvorRestError(Exception):
    """REST API exception."""
    pass


class NeatsvorRestAsync:
    """
    Asynchronous client for Neatsvor REST API.
    """

    def __init__(self, email: str, password: str, region: str = "ru", config: Optional[Dict] = None):
        """
        Initialize REST client.

        Args:
            email: User email
            password: Password
            region: Region (ru/cn/de)
            config: Configuration (optional)
        """
        self.email = email
        self.password = password
        self.region = region

        # Load region configuration
        from custom_components.neatsvor.const import COUNTRIES
        country_data = COUNTRIES.get(region, COUNTRIES["ru"])

        # Default configuration
        self.config = config or {
            'base_url': country_data["rest_url"],
            'app_key': "d2263964a26eb296c61ee5a6287fc572",
            'app_secret': "f334e01bf384126ee7af12f7a2b61774",
            'package_name': "com.blackvision.libos2",
            'source': "libos",
            'reg_id': "",
            'country': region,
            'user_agent': "okhttp/4.9.1"
        }

        self.session: Optional[aiohttp.ClientSession] = None
        self.user_id: Optional[str] = None
        self.app_token: Optional[str] = None
        self.iot_token: Optional[str] = None
        self.client_id: Optional[str] = None

        self.timeout = ClientTimeout(total=60, connect=30)

    async def __aenter__(self):
        """Enter context manager."""
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            headers={"User-Agent": self.config['user_agent']}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        if self.session:
            await self.session.close()

    @staticmethod
    def md5(text: str) -> str:
        """MD5 hashing."""
        return hashlib.md5(text.encode()).hexdigest()

    # ------------------------------------------------------------------
    # LOW-LEVEL METHODS - ONLY FOR REQUESTS WITH iot_token
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        """
        Headers for requests with iot_token.
        EXACTLY AS IN ORIGINAL - raises error if token missing!
        """
        if not self.iot_token:
            raise NeatsvorRestError("SDK token missing. Call login_sdk() first.")
        return {
            "token": self.iot_token,
            "User-Agent": self.config['user_agent'],
            "Accept-Language": "ru",
        }

    async def _api_data(self, response: aiohttp.ClientResponse) -> Any:
        """
        Check API response.
        EXACTLY AS IN ORIGINAL.
        """
        try:
            data = await response.json()
        except Exception as e:
            raise NeatsvorRestError(f"Failed to parse JSON: {e}")

        code = str(data.get("code", ""))
        if code != "10000":
            msg = data.get("msg", "Unknown API error")
            _LOGGER.error("API error [%s]: %s", code, msg)
            raise NeatsvorRestError(f"API error {code}: {msg}")

        return data.get("data")

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        """
        Execute request WITH iot_token.
        EXACTLY AS IN ORIGINAL - always uses _headers()
        """
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": self.config['user_agent']}
            )

        url = urljoin(self.config['base_url'], path)
        headers = kwargs.pop("headers", None)

        if headers is None:
            headers = self._headers()  # Always take headers with token!

        _LOGGER.debug("%s %s", method, url)

        try:
            async with self.session.request(
                method=method,
                url=url,
                headers=headers,
                **kwargs
            ) as response:
                response.raise_for_status()
                return await self._api_data(response)

        except ClientResponseError as e:
            _LOGGER.error("HTTP error %s: %s", e.status, e.message)
            raise NeatsvorRestError(f"HTTP {e.status}: {e.message}")
        except Exception as e:
            _LOGGER.error("Request failed: %s", e)
            raise NeatsvorRestError(f"Request failed: {e}")

    async def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        """GET request with iot_token."""
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, json: Optional[Dict] = None) -> Any:
        """POST request with iot_token."""
        return await self._request("POST", path, json=json)

    # ------------------------------------------------------------------
    # AUTHORIZATION - DIRECT CALLS, WITHOUT _request()!
    # ------------------------------------------------------------------

    async def login(self):
        """User authentication."""
        _LOGGER.debug("=== START LOGIN ===")
        _LOGGER.debug("Email: %s", self.email)
        _LOGGER.debug("Base URL: %s", self.config['base_url'])

        if not self.session:
            _LOGGER.debug("Creating new session")
            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": self.config['user_agent']}
            )

        try:
            # 1. Check account status
            _LOGGER.debug("Step 1 - Account status request")
            url = urljoin(
                self.config['base_url'],
                "/mis/user/account/status"
            )
            _LOGGER.debug("Status URL: %s", url)

            async with self.session.get(
                url,
                params={
                    "loginName": self.email,
                    "globalRoaming": self.config['country'],
                    "source": self.config['source'],
                }
            ) as response:
                _LOGGER.debug("Status response: %s", response.status)
                if response.status != 200:
                    text = await response.text()
                    _LOGGER.error("Error response: %s", text[:200])
                    raise Exception(f"HTTP {response.status}")

                data = await response.json()
                _LOGGER.debug("Status response: %s", data)
                enc = data.get("data", {}).get("encryptType", 1)
                _LOGGER.debug("encryptType = %s", enc)

            # 2. Select login endpoint
            login_path = "/mis/user/login/account/v2" if enc == 2 else "/mis/user/login/account"
            url = urljoin(self.config['base_url'], login_path)
            _LOGGER.debug("Step 2 - Login via %s", login_path)

            # 3. Execute login
            password_md5 = self.md5(self.password)
            _LOGGER.debug("Sending login data")

            async with self.session.post(
                url,
                json={
                    "loginName": self.email,
                    "password": password_md5,
                    "countryCode": self.config['country'],
                    "globalRoaming": "7",
                    "registrationId": self.config['reg_id'],
                    "source": self.config['source'],
                }
            ) as response:
                _LOGGER.debug("Login response status: %s", response.status)
                if response.status != 200:
                    text = await response.text()
                    _LOGGER.error("Login error: %s", text[:200])
                    raise Exception(f"HTTP {response.status}")

                data = await self._api_data(response)
                self.user_id = str(data["id"])
                self.app_token = data["token"]

            _LOGGER.debug("✅ Login OK user_id=%s", self.user_id)
            _LOGGER.debug("=== LOGIN COMPLETED ===")
            return True

        except asyncio.TimeoutError:
            _LOGGER.error("❌ Login timeout")
            raise
        except Exception as e:
            _LOGGER.error("❌ Login error: %s", e)
            raise

    async def login_sdk(self):
        """SDK login."""
        if not self.app_token:
            raise NeatsvorRestError("login() first")

        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": self.config['user_agent']}
            )

        url = urljoin(
            self.config['base_url'],
            "/mis/user/login/sdk"
        )

        # Direct call with appToken header, as in original
        async with self.session.post(
            url,
            headers={"appToken": self.app_token},
            json={
                "nickName": self.email,
                "systemType": "1",
                "appKey": self.config['app_key'],
                "appSecret": self.config['app_secret'],
                "packageName": self.config['package_name'],
                "userId": self.user_id,
            }
        ) as response:
            data = await self._api_data(response)
            self.iot_token = data["token"]
            self.client_id = data["clientId"]

        _LOGGER.info("SDK OK client_id=%s", self.client_id)
        _LOGGER.debug("Received iot_token: %s...", self.iot_token[:10] if self.iot_token else 'None')

    # ------------------------------------------------------------------
    # DEVICES - USE _get/_post WITH iot_token
    # ------------------------------------------------------------------

    async def get_homes(self) -> List[Dict]:
        """Get list of homes."""
        return await self._get("/mis/home/query/infoList")

    async def get_devices(self, home_id: Optional[str] = None) -> List[Dict]:
        """Get list of devices."""
        if not home_id:
            homes = await self.get_homes()
            home_id = next(h["id"] for h in homes if h.get("isDefault"))

        return await self._get(
            "/mis/device/home/device",
            params={"homeId": home_id}
        )

    async def get_device_dp(self, device_id: int, pid: str) -> List[Dict]:
        """Get DP for device."""
        _LOGGER.info("Requesting DP for device_id=%s, pid=%s", device_id, pid)
        return await self._get(
            "/mis/product/get/dp",
            params={
                "pid": pid,
                "deviceId": device_id,
            }
        )

    async def get_dp_schema(self, device_id: int, pid: str) -> Dict[int, Dict]:
        """
        Get DP schema for device.

        Returns:
            Dictionary {dp_id: {code, type, enum}}
        """
        raw = await self.get_device_dp(device_id, pid)
        schema = {}

        for dp in raw:
            dp_id = dp.get("dpNum")
            if dp_id is None:
                continue

            # Convert enum
            enum = None
            if dp.get("dpEnum"):
                # dpEnum: {"stop": 0, "forward": 1} → {0: "stop", 1: "forward"}
                enum = {v: k for k, v in dp["dpEnum"].items()}

            # Determine type
            data_type = dp.get("dataType")
            type_name = None
            if data_type == 0:
                type_name = 'bool'
            elif data_type == 1:
                type_name = 'number'
            elif data_type == 2:
                type_name = 'enum'
            elif data_type == 3:
                type_name = 'raw'
            else:
                type_name = 'unknown'

            schema[dp_id] = {
                "code": dp.get("dpCode"),
                "type": data_type,
                "type_name": type_name,
                "enum": enum,
                "raw": dp
            }

        _LOGGER.info("Retrieved DP schema: %s data points", len(schema))
        return schema

    async def get_consumables(self, device_id: int) -> List[Dict]:
        """Get consumables information."""
        return await self._get(
            "/mis/device/query/consume",
            params={"deviceId": device_id}
        )

    async def get_device_info(self, device_id: int) -> Dict:
        """Get device information."""
        return await self._get(
            "/mis/device/query/device",
            params={"deviceId": device_id}
        )

    # ------------------------------------------------------------------
    # STATISTICS AND HISTORY
    # ------------------------------------------------------------------

    async def get_clean_records(self, device_id: int, offset: int = 0, limit: int = 10) -> List[Dict]:
        """Get cleaning history."""
        return await self._get(
            "/mis/device/query/clean/record",
            params={
                "deviceId": device_id,
                "offset": offset,
                "limit": limit,
            }
        )

    async def get_clean_sum(self, device_id: int) -> Dict:
        """Get total cleaning statistics."""
        return await self._get(
            "/mis/device/query/clean/sum",
            params={"deviceId": device_id}
        )

    # ------------------------------------------------------------------
    # MAPS
    # ------------------------------------------------------------------

    async def get_map_list(self, device_id: int, offset: int = 0, limit: int = 10) -> List[Dict]:
        """Get list of saved maps."""
        raw = await self._get(
            "/mis/device/query/map",
            params={
                "deviceId": device_id,
                "offset": offset,
                "limit": limit,
            }
        )

        maps = []
        for item in raw:
            maps.append({
                'map_id': item.get('mapId'),
                'device_map_id': item.get('deviceMapId'),
                'name': item.get('mapName', 'Unnamed'),
                'app_map_url': item.get('appMapUrl'),
                'dev_map_url': item.get('devMapUrl'),
                'estimated_area_cm2': int(item.get('estimatedArea', 0)),
                'estimated_area_m2': int(item.get('estimatedArea', 0)) / 10000,
                'app_map_md5': item.get('appMapMd5Value'),
                'dev_map_md5': item.get('devMapMd5Value'),
                'config_info': item.get('configInfo', '')
            })

        return maps

    async def download_map(self, map_url: str) -> bytes:
        """Download binary map from URL."""
        _LOGGER.info("Downloading map: %s", map_url)

        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": self.config['user_agent']}
            )

        async with self.session.get(map_url) as response:
            response.raise_for_status()
            return await response.read()

    # ------------------------------------------------------------------
    # CLEANING DATA - NO TOKEN REQUIRED (PUBLIC URLs)
    # ------------------------------------------------------------------

    async def get_clean_record_data(self, record_url: str) -> Optional[bytes]:
        """Download cleaning record map data from recordUrl."""
        _LOGGER.info("Loading cleaning data: %s", record_url)

        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": self.config['user_agent']}
            )

        try:
            async with self.session.get(record_url) as response:
                response.raise_for_status()

                content_type = response.headers.get('Content-Type', '')
                data = await response.read()

                _LOGGER.info("Status: %s, Content-Type: %s, Size: %s bytes", response.status, content_type, len(data))

                # Check if it's a GZIP file
                if len(data) > 2 and data[:2] == b'\x1f\x8b':
                    _LOGGER.info("Received GZIP file, size: %s bytes", len(data))
                    return data
                else:
                    _LOGGER.warning("Not GZIP file. First bytes: %s", data[:4].hex())
                    return None

        except Exception as e:
            _LOGGER.error("Error loading cleaning data %s: %s", record_url, e)
            return None

    async def decode_clean_map_data(self, gzip_data: bytes) -> Optional[Dict]:
        """Decode map from GZIP data of cleaning record."""
        from custom_components.neatsvor.liboshome.map.map_decoder import MapDecoder
        import tempfile
        import os
        import aiofiles

        if not gzip_data:
            _LOGGER.error("Empty data for decoding")
            return None

        _LOGGER.info("Decoding cleaning map, GZIP size: %s bytes", len(gzip_data))

        try:
            # Save to temporary file ASYNCHRONOUSLY
            async with aiofiles.tempfile.NamedTemporaryFile(suffix='.bv', delete=False) as f:
                await f.write(gzip_data)
                temp_path = f.name

            try:
                # USE ASYNCHRONOUS VERSION!
                map_data = await MapDecoder.decode_app_map_async(temp_path)

                if map_data:
                    _LOGGER.info("Map decoded: %sx%s", map_data.get('width', 0), map_data.get('height', 0))
                    return map_data
                else:
                    _LOGGER.error("Error decoding map")
                    return None

            finally:
                # Delete temporary file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except Exception as e:
            _LOGGER.error("Error decoding cleaning map: %s", e)
            return None