# -*- coding: utf-8 -*-
"""Atlas Venue B POS — module root.

The post-install hook lives in hooks.py; it is imported here so the manifest
entry 'post_init_hook': 'post_init_hook' resolves to atlas_pos_seed.post_init_hook.
"""

from .hooks import post_init_hook
