"""Teaching the program an unknown headset dongle.

Four steps, not two: one "on" and one "off" would also be told apart by a
battery reading or a counter, and a wrong byte means headphones that grab the
sound at random. Two full cycles throw those out — see core/dongle.deduce,
which does the actual working-out. This is the plumbing around it: the buckets
the reports land in, the listener that fills them, and the report offered to a
person at the end.
"""
import time

from . import __version__, log
from .core.dongle import MAX_CAPTURE, Dongle, deduce, product_name

_log = log.get("wizard")


class Wizard:
    STEPS = ("on1", "off1", "on2", "off2")

    def __init__(self, cfg, dongle_ids, resync_dongle, device_name, on_change):
        """`dongle_ids` answers which USB device the priority headset is on;
        `resync_dongle` starts or stops the program's own listener to match the
        settings — it steps aside while the wizard runs and comes back after;
        `device_name` names an endpoint for the report; `on_change` tells the
        page the state moved."""
        self._cfg = cfg
        self._dongle_ids = dongle_ids
        self._resync = resync_dongle
        self._device_name = device_name
        self._on_change = on_change
        # The run, while there is one: its buckets and its own listener, which
        # holds the dongle instead of the program's watcher.
        self._run: dict | None = None
        self._dongle: Dongle | None = None

    @property
    def running(self) -> bool:
        return self._run is not None

    def start(self) -> dict:
        """Begin teaching. Listening runs from here to the end without a break:
        the reports simply land in the bucket of whichever step is running, so
        nothing is lost while the person is reaching for the headset."""
        self.stop()
        ids = self._dongle_ids()
        if ids is None:
            return {"error": "no_dongle"}
        self._run = {"ids": ids, "step": "", "last": 0.0,
                     "steps": {s: [] for s in self.STEPS}}
        self._resync()                        # let go of the watcher, if any
        self._dongle = Dongle(ids[0], ids[1], self._report, learn=True)
        self._dongle.start()
        return self.state()

    def step(self, step: str) -> dict:
        """Move to a step. Everything arriving from now on belongs to it."""
        if self._run is None:
            return {"error": "not_running"}
        if step not in self.STEPS:
            raise ValueError(f"no such step: {step}")
        self._run["step"] = step
        self._run["last"] = 0.0
        return self.state()

    def _report(self, data: bytes) -> None:
        """Called from a dongle thread for every report that arrives."""
        run = self._run
        if run is None or run["step"] not in run["steps"]:
            return
        bucket = run["steps"][run["step"]]
        if len(bucket) < MAX_CAPTURE:
            bucket.append(data)
        run["last"] = time.monotonic()

    def state(self) -> dict:
        """What the page needs to draw the current step.

        "settled" is the answer to the only hard question here: has the dongle
        finished speaking? A headset takes seconds to power up and then sends
        several reports in a row; moving on in the middle of that would file the
        rest of them under the next step.
        """
        run = self._run
        if run is None:
            return {"running": False}
        counts = {s: len(v) for s, v in run["steps"].items()}
        heard = counts.get(run["step"], 0)
        return {"running": True, "step": run["step"], "counts": counts,
                "heard": heard,
                "settled": bool(heard) and time.monotonic() - run["last"] > 1.2}

    def stop(self) -> None:
        if self._dongle is not None:
            self._dongle.stop()
            self._dongle = None
        self._run = None

    def finish(self) -> dict:
        """Read the four buckets, save what was learned, and prepare the report."""
        run = self._run
        if run is None:
            return {"error": "not_running"}
        ids = run["ids"]
        steps = run["steps"]
        on = steps["on1"] + steps["on2"]
        off = steps["off1"] + steps["off2"]
        rule = deduce(on, off) if on and off else None
        usb = f"{ids[0]:04X}:{ids[1]:04X}"
        name = (product_name(*ids)
                or self._device_name(self._cfg.get("auto_device")) or usb)
        if rule is not None:
            rule = {**rule, "name": name}
            rules = {**self._cfg.get("dongle_rules"), usb: rule}
            self._cfg.set("dongle_rules", rules)
            # They just taught it; switching it on themselves afterwards would be
            # a step that exists only to be clicked.
            self._cfg.set("watch_dongle", True)
        text = self._report_text(usb, name, rule, steps)
        self.stop()
        self._resync()
        self._on_change()
        return {"ok": rule is not None, "name": name, "usb": usb,
                "detail": self._detail(rule), "report": text,
                "url": self._issue_url(usb, name, rule is not None, text)}

    @staticmethod
    def _detail(rule: dict | None) -> str:
        if rule is None:
            return ""
        pos, val = rule["marker"]
        return (f"report 0x{rule['report']:02X}, byte {rule['state_at']}: "
                f"on 0x{rule['on']:02X}, off 0x{rule['off']:02X} "
                f"(marker byte {pos} = 0x{val:02X})")

    def _report_text(self, usb: str, name: str, rule: dict | None, steps: dict) -> str:
        """The whole finding as plain text, ready to be read by a person.

        Repeated lines are collapsed: a dongle that says the same thing forty
        times adds nothing but length, and the count says it better.
        """
        out = [f"Dongle: {usb} — {name or 'unnamed'}",
               f"Audio device: {self._device_name(self._cfg.get('auto_device'))}",
               f"Program: {__version__}", ""]
        if rule is None:
            out.append("Result: no byte told the two states apart.")
        else:
            out.append(f"Result: {self._detail(rule)}")
            if rule.get("also"):
                out.append("Other bytes that would have worked too: " + ", ".join(
                    f"byte {i}: on 0x{a:02X}, off 0x{b:02X}" for i, a, b in rule["also"]))
        for step in self.STEPS:
            seen: dict[str, int] = {}
            for data in steps[step]:
                line = data.hex(" ")
                seen[line] = seen.get(line, 0) + 1
            out.append("")
            out.append(f"[{step}] {len(steps[step])} reports")
            out.extend(f"  {line}" + (f"   ×{n}" if n > 1 else "")
                       for line, n in seen.items())
        return "\n".join(out)

    @staticmethod
    def _issue_url(usb: str, name: str, ok: bool, text: str) -> str:
        """The report form, with its fields already filled in.

        Through the template rather than a blank issue: the template carries the
        label and the questions, and its field ids are what these parameters
        fill. Sending it is the person's click and their decision — the program
        itself sends nothing anywhere, ever.
        """
        from urllib.parse import urlencode
        query = urlencode({
            "template": "dongle.yml",
            "title": f"Dongle: {name or usb}",
            "model": name,
            "ids": usb,
            "reports": text,
            "worked": "yes" if ok else "no",
        })
        return f"https://github.com/electronic-mars/mas/issues/new?{query}"
