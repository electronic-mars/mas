# Releasing

Everything here is done by a person, deliberately. The build itself happens on
GitHub — never publish a binary built on a developer machine, because nobody can
reproduce it and you cannot prove what went into it.

## Before the first public release

- [ ] **Make the repository public.** Settings → General → Change visibility.
      Until then the release links in the program and on the site are dead ends.
- [ ] **Enable Sponsors** (Settings → Sponsors) so the button in the repository
      header does something. The Patreon entry in `.github/FUNDING.yml` works
      without it.
- [ ] **Enable Discussions** if you want the "Question or idea" link in the issue
      templates to lead somewhere. Otherwise delete that link from
      `.github/ISSUE_TEMPLATE/config.yml`.
- [ ] **Publish the site.** Copy `site/` into a repository called
      `electronic-mars.github.io` and enable Pages on it. Then point the support
      button of the program at `support.html` there instead of straight at
      Patreon — see the note at the top of that file.

## Cutting a release

1. **Decide the version** and put it in exactly one place:
   `src/mas/__init__.py`. The window, the executable's properties and the
   installer all read it from there.
2. **Write the changelog entry.** Move things out of "Unreleased" into a section
   named after the version, with the date.
3. **Run both suites** and look at the output, not just the exit code:
   ```
   .venv\Scripts\python.exe tests\test_smoke.py
   .venv\Scripts\python.exe tests\test_device_icons.py
   ```
4. **Refresh the screenshots** if anything in the window changed:
   ```
   .venv\Scripts\python.exe tools\shots.py
   ```
5. **Commit, then tag and push.** The tag is what triggers the build:
   ```
   git tag v1.0.0
   git push origin main --tags
   ```
6. **Watch the run** in Actions. It builds the executable, builds the installer,
   runs the tests again on a clean machine, and opens a **draft** release with
   both files and `SHA256SUMS.txt`.
7. **Check the draft before publishing it.** Download the installer, install it
   on this machine, run it once, uninstall it. Ten minutes that catch the kind of
   thing no test can.
8. **Publish the release.**

## Right after publishing

- [ ] **VirusTotal.** Upload the installer and the archive at
      https://www.virustotal.com — an unsigned PyInstaller program that
      synthesises keystrokes, reads HID and enumerates processes will be flagged
      by somebody. Knowing which engines, before a user tells you, is worth the
      two minutes. Send a false-positive report to any engine that flags it;
      every vendor has a free form.
- [ ] **Add the note to the release** if anything flagged: which engine, and that
      the sources and the build log are public.
- [ ] **winget.** Once the release exists, submit a manifest to
      `microsoft/winget-pkgs` — a pull request with three small YAML files, no
      review beyond automated checks. It gives `winget install
      electronic-mars.MasterAudioSwitcher`, which reads far better in a README
      than a download link, and it is the channel experienced people use.

## What is deliberately not automated

- **Signing.** The program is unsigned, so SmartScreen warns about it. A
  certificate needs an identity check and a hardware key, and it costs a few
  hundred a year. The Microsoft Store signs packages for you and is the cheapest
  way to get rid of the warning — but the store needs an MSIX package, and in
  that container the registry autostart, the HID access and the settings folder
  all work differently. That is its own piece of work, after the first release.
- **Update checking.** The About tab opens the releases page in a browser. It
  does not download anything, and it never will without being asked: an
  auto-updater is the one feature that turns a small utility into something that
  can break a machine while nobody is looking.
