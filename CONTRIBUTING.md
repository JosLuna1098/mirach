# Contributing to Mirach

Thanks for thinking about contributing — Mirach is a small, focused project and
clear contributions are very welcome.

This guide covers how to set up a development environment, run the test and
lint commands the CI uses, and what to expect in the pull request flow.

## Project layout

Mirach is a Python daemon plus a thin trigger script. The
[Architecture section of the README](README.md#architecture) has the
source-tree map and the data flow between components.

## Development setup

You need **Python 3.11 or newer** and **PortAudio** (Linux: `sudo apt install
portaudio19-dev` or your distro's equivalent — needed by `sounddevice`).

```bash
git clone https://github.com/JosLuna1098/mirach.git
cd mirach
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

If a change touches the audio resampling code path, also install the optional
`quality` extra so the SciPy code path is exercised:

```bash
pip install -e ".[dev,quality]"
```

You do **not** need the Whisper / Piper / OpenCode runtime to run the test
suite — the tests stub out the heavy dependencies.

## Running the same checks CI runs

```bash
pytest -v
ruff check .
ruff format --check .
```

CI runs this matrix:

- `ubuntu-latest` × Python 3.11 and 3.12 — **the supported runtime, required for merge.**
- `windows-latest` and `macos-latest` × Python 3.11 and 3.12 — informational only.

Mirach is built and tested on Linux. Windows / macOS jobs help us catch
obvious portability regressions, but a red Windows job will not block a merge
on its own.

## Commit style

We follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <subject>
```

Common types: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `ci`, `style`.

Examples from the existing history:

- `fix: auto-set executable bit on user scripts at load and install time`
- `docs: fix dates to 2026 and add inspiration credit`

Keep commits focused; one logical change per commit makes review and revert
much easier.

## Pull request flow

1. Fork the repo and create a branch from `master`.
2. Make your change. Add or update tests for any behavior change.
3. Run `pytest`, `ruff check .` and `ruff format --check .` locally.
4. Push your branch and open a PR against `master`. The PR template will guide
   the description.
5. CI runs the full matrix. Merge is gated on the **Linux** jobs going green.
6. A maintainer will review. Small, focused PRs are the fastest path to a
   merge.

If you are unsure whether an idea fits the project, open an issue first using
the Feature request template — a short conversation usually saves rework.

## Code of conduct

Participation is governed by the
[Contributor Covenant 2.1](.github/CODE_OF_CONDUCT.md). Be kind, focused on
the work, and assume good faith.

## Reporting security issues

Please do **not** open a public issue for security findings. See
[`.github/SECURITY.md`](.github/SECURITY.md) for the private disclosure
channel.

## License

By contributing, you agree that your contributions will be licensed under the
project's [MIT License](LICENSE).
