"""A switching cycle bound to the device, not to the position.

The order list is stored in full, including devices that are absent right now.
A device that disappeared is skipped, but the order of the rest does not shift;
one that comes back takes its old place again. Without this, someone who has
learned "two clicks — headphones" misses exactly when they changed nothing
themselves.
"""
from .. import log
from . import devices
from .config import Config

_log = log.get("switcher")


class Switcher:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def ordered_ids(self) -> list[str]:
        return list(self.cfg.get("cycle"))

    def seed_if_empty(self) -> None:
        """On a clean install the cycle is empty and a left click does nothing. We
        put every output device in it — the program works right away, and the user
        removes what they do not need."""
        if self.ordered_ids():
            return
        ids = [d.id for d in devices.list_devices(only_active=True) if d.is_output]
        if ids:
            self.cfg.set("cycle", ids)
            _log.info("cycle filled in on first run: %d devices", len(ids))

    def available(self) -> list[str]:
        """Devices from the cycle that are present right now, in the given order."""
        present = {d.id for d in devices.list_devices(only_active=True) if d.is_output}
        return [i for i in self.ordered_ids() if i in present]

    def next_id(self) -> str | None:
        ring = self.available()
        if not ring:
            return None
        current = devices.default_id(is_output=True)
        if current in ring:
            return ring[(ring.index(current) + 1) % len(ring)]
        # The current device is outside the cycle (for example, Windows reset the
        # default) — we start from the beginning of the list instead of guessing.
        return ring[0]

    def switch_to(self, device_id: str) -> devices.Device | None:
        """None means "did not switch" — both the chime and the icon must know it."""
        if not devices.set_default(device_id, self.cfg.get("switch_communications")):
            return None
        return self.device_by_id(device_id)

    @staticmethod
    def device_by_id(device_id: str) -> devices.Device | None:
        return next((d for d in devices.list_devices(only_active=False) if d.id == device_id), None)

    def toggle_in_cycle(self, device_id: str, enabled: bool) -> list[str]:
        order = self.ordered_ids()
        if enabled and device_id not in order:
            order.append(device_id)
        elif not enabled and device_id in order:
            order.remove(device_id)
        self.cfg.set("cycle", order)
        return order

    def reorder(self, device_ids: list[str]) -> list[str]:
        """The order is set by dragging. Devices missing from the new list but
        present in the old one are kept at the tail — otherwise a device that is
        absent right now would silently drop out of the cycle."""
        old = self.ordered_ids()
        kept = [i for i in device_ids if i in old]
        tail = [i for i in old if i not in kept]
        order = kept + tail
        self.cfg.set("cycle", order)
        return order
