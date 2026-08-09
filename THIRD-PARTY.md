# Third-party components

Master Audio Switcher is distributed under GPL-3.0-or-later. Below is
everything that goes into the build or takes part in making it, and on what
terms.

## Libraries in the build

| Component | License | What for |
|---|---|---|
| [pywebview](https://pywebview.flowrl.com/) 6.2.1 | BSD-3-Clause | the program window, on the WebView2 engine |
| [pystray](https://github.com/moses-palmer/pystray) 0.19.5 | LGPL-3.0 | the tray icon |
| [pycaw](https://github.com/AndreMiras/pycaw) | MIT | volume and mixer through Core Audio |
| [comtypes](https://github.com/enthought/comtypes) 1.4.16 | MIT | talking to Windows COM interfaces |
| [Pillow](https://python-pillow.org/) 12.3.0 | MIT-CMU | preparing raster icons |
| [winrt-runtime](https://github.com/pywinrt/pywinrt) with `Windows.Media.Control` and `Windows.Foundation` 3.2.1 | MIT | player state through WinRT |
| [psutil](https://github.com/giampaolo/psutil) 7.2.2 | BSD-3-Clause | program names in the mixer |
| [bottle](https://bottlepy.org/) 0.13.4 | MIT | comes with pywebview, serves the page locally |
| [pythonnet](https://pythonnet.github.io/), clr-loader, cffi, pycparser | MIT | pywebview dependencies |
| [pywin32-ctypes](https://github.com/enthought/pywin32-ctypes) 0.2.3 | BSD-3-Clause | build dependency |
| six, typing-extensions, packaging, altgraph, pefile, proxy-tools | MIT / PSF-2.0 / Apache-2.0 / BSD | indirect dependencies |

The LGPL-3.0 of pystray is compatible with GPL-3.0: the program as a whole stays
under GPL-3.0, while pystray itself stays under its own license, with sources
available at the link above.

## Build tool

[PyInstaller](https://pyinstaller.org/) 6.21.0 — GPL-2.0-or-later with a special
exception that explicitly permits distributing the programs it builds under any
license. The PyInstaller bootloader ends up inside the executable on exactly
those terms.

## Icons

Device, mark and interface icons come from the free
[Hugeicons](https://hugeicons.com) set (`@hugeicons/core-free-icons` 4.2.3),
licensed **MIT**. The source files the set is generated from live in
`assets/icons-src/`; the build needs neither network nor npm.

```
MIT License

Copyright (c) Hugeicons

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR OTHER DEALINGS IN THE SOFTWARE.
```

The application icon was drawn for this project and is distributed with it under
GPL-3.0.
