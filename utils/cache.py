"""
MPL-2.0 LICENSE

The contents of this file are taken from:
https://github.com/Rapptz/RoboDanny/blob/582804d238c8ae302ab9aed6a1b5b8d928ba837f/cogs/utils/cache.py#L34-L68

This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

import time
from typing import Any


class ExpiringCache(dict):
    def __init__(self, seconds: float):
        self.__ttl: float = seconds
        super().__init__()

    def __verify_cache_integrity(self):
        # Have to do this in two steps...
        current_time = time.monotonic()
        to_remove = [k for (k, (v, t)) in self.items() if current_time > (t + self.__ttl)]
        for k in to_remove:
            del self[k]

    def __contains__(self, key: str | int):
        self.__verify_cache_integrity()
        return super().__contains__(key)

    def __getitem__(self, key: str | int):
        self.__verify_cache_integrity()
        return super().__getitem__(key)

    def __setitem__(self, key: str | int, value: Any):
        super().__setitem__(key, (value, time.monotonic()))
