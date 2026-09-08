from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict
import hashlib
import json
from typing import Optional
from threading import RLock

from PIL import Image

from model.hair_style import HairStyle

class RenderCache:
    """Small LRU cache for completed card images."""
    def __init__(self, max_entries: int = 64, renderer_version: int = 2):
        self.max_entries=max(1,int(max_entries))
        self.renderer_version=renderer_version
        self._items=OrderedDict()
        self._lock=RLock()

    def key(self, style: HairStyle, width: int, height: int, seed: int, supersample: int, show_background: bool=False):
        payload=(self.renderer_version,width,height,seed,supersample,show_background,asdict(style))
        raw=json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()
        return hashlib.sha1(raw).digest()

    def get(self,key) -> Optional[Image.Image]:
        with self._lock:
            image=self._items.get(key)
            if image is None: return None
            self._items.move_to_end(key)
            return image.copy()

    def put(self,key,image: Image.Image) -> None:
        with self._lock:
            self._items[key]=image.copy()
            self._items.move_to_end(key)
            while len(self._items)>self.max_entries:
                self._items.popitem(last=False)

    def clear(self):
        with self._lock:
            self._items.clear()
