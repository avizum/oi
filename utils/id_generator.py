"""
GPL-3.0 LICENSE

Copyright (C) 2021-2024  Shobhits7, avizum

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import time
from datetime import datetime, timezone


class IDGenerator:
    def __init__(self, worker_id: int) -> None:

        if worker_id not in (0, 1):
            raise ValueError("Worker ID must be 0 or 1")

        self.worker_id: int = worker_id
        self.epoch_start: int = int(datetime(2021, 7, 22, 10, 22, 14, 709000, tzinfo=timezone.utc).timestamp() * 1000)
        self.sequence = 0
        self.last_ms = -1
        self.worker_id_bits = 1
        self.sequence_bits = 5
        self.max_sequence = (1 << self.sequence_bits) - 1
        self.worker_id_shift = self.sequence_bits
        self.timestamp_shift = self.worker_id_bits + self.sequence_bits

    def current_ms(self) -> int:
        return int(time.time() * 1000)

    def generate(self) -> int:
        current_time = self.current_ms()

        if current_time < self.last_ms:
            raise Exception("Can not generate ID")

        if current_time == self.last_ms:
            self.sequence = (self.sequence + 1) & self.max_sequence

            if self.sequence == 0:
                while current_time == self.last_ms:
                    current_time = self.current_ms()
        else:
            self.sequence = 0

        self.last_ms = current_time
        elapsed_time = current_time - self.epoch_start

        return (elapsed_time << self.timestamp_shift) | (self.worker_id << self.worker_id_shift) | self.sequence
