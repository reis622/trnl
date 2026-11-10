# Publishing trnl (maintainer notes)

Repo: https://github.com/reis622/trnl

1. **Release** (what the one-line installers use): bump `version` in `pyproject.toml` and `src/trnl/__init__.py`,
   commit, then `git tag vX.Y.Z && git push --tags`. `.github/workflows/release.yml` runs the tests, builds the
   wheel + sdist and attaches them to the GitHub release `vX.Y.Z`. `install.ps1` / `install.sh` pick the
   `trnl-X.Y.Z-py3-none-any.whl` asset of the latest release (GitHub API), falling back to the `main` source zip.
2. **Pre-converted OPUS-MT models**: release `models-v1` holds `en_tr`, `tr_en`, `ja_en` `-opus-int8.zip`
   (~70 MB each, CC-BY 4.0 Helsinki-NLP OPUS-MT; each zip carries the original README/LICENSE). Rebuild them with
   `python -m trnl.setup_data --export-opus DIR`. The URL pattern is `PRECONVERTED` in `src/trnl/setup_data.py`.
3. **PyPI (optional, not done yet)**: the name `trnl` was free on PyPI. On pypi.org add a pending publisher
   (project `trnl`, owner `reis622`, repo `trnl`, workflow `bundles.yml`, environment `pypi`), then run the
   *bundles* workflow manually with "publish to PyPI" ticked. Alternative: `python -m build && twine upload dist/*`.
   Afterwards `pipx install trnl` works.
4. **Standalone bundles (optional)**: Actions > *bundles* > Run workflow (tag `vX.Y.Z`) builds PyInstaller bundles
   (Windows x64, macOS arm64/x64, Linux x64) and `SHA256SUMS.txt` into that release. They are needed only for:
   - **Homebrew**: repo `github.com/reis622/homebrew-tap`, copy `packaging/homebrew/trnl.rb` to `Formula/trnl.rb`,
     fill the sha256 values (TODO until bundles exist) -> `brew install reis622/tap/trnl`.
   - **Scoop**: repo `github.com/reis622/scoop-bucket`, add `bucket/trnl.json` (fill the hash, TODO)
     -> `scoop bucket add trnl https://github.com/reis622/scoop-bucket` and `scoop install trnl`.
   - **winget**: fill `InstallerSha256` (TODO) in `packaging/winget/manifests/r/reis622/trnl/1.1.0/`,
     `winget validate <dir>`, then a PR to microsoft/winget-pkgs (or `wingetcreate submit <dir>`).
   - **AUR**: `trnl-bin` from `packaging/aur/PKGBUILD` (fill sha256, TODO; `makepkg --printsrcinfo > .SRCINFO`).
