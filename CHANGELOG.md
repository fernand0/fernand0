# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- File-based caching for GitHub API and RSS feed responses with configurable TTL
- Workflow status badge to README showing GitHub Actions build status
- Comprehensive `.gitignore` for Python projects

### Changed
- Improved workflow efficiency with conditional commits (only commit when content changes)

### Fixed
- Token validation error messages now provide clearer guidance

---

## [1.1.0] - 2026-02-27

### Added
- YAML configuration file (`config.yaml`) for easy customization without code changes
- MIT License
- Pre-commit hooks for linting and formatting (ruff, mypy)
- Comprehensive test suite with 66 tests covering validation, formatting, fetching, and caching
- Token validation with format checking and API verification
- Type hints throughout the codebase (75% coverage)
- Setup documentation in README with step-by-step instructions
- pyproject.toml for modern Python dependency management
- GitHub Actions workflow improvements:
  - Install via `pip install -e ".[dev]"`
  - Optional linting steps (non-blocking)
  - Content-aware commit skipping

### Changed
- Refactored `build_readme.py` with proper dataclasses and configuration loading
- Moved from hardcoded configuration to external YAML file
- Updated requirements.txt to use editable install reference
- Improved error handling in API responses

### Fixed
- GraphQL query key mismatch (`contributions` → `repositoriesContributedTo`)
- None handling in nested dictionary access for API responses
- Token validation now properly checks for None responses

### Removed
- Hardcoded DEFAULT_BLOGS and DEFAULT_MASTODON (now loaded from config.yaml)

---

## [1.0.0] - 2020-08-06

### Added
- Initial release of self-updating GitHub profile README generator
- Automatic fetching of GitHub repositories and contributions
- RSS/Atom feed parsing for blog posts
- Mastodon integration for social media posts
- Markdown formatting and injection into README
- Daily scheduled GitHub Actions workflow
- Inspired by [Simon Willison's self-updating profile README](https://simonwillison.net/2020/Jul/10/self-updating-profile-readme/)

---

## Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| 1.1.0 | 2026-02-27 | Major refactor: config file, tests, caching, type hints |
| 1.0.0 | 2020-08-06 | Initial release |

---

## Upcoming

### Planned
- Support for additional social platforms (Bluesky, LinkedIn)
- CLI argument parsing (--dry-run, --verbose, --config)
- Rate limiting and retry logic for API calls
- Dependabot configuration for automated dependency updates

[Unreleased]: https://github.com/fernand0/fernand0/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/fernand0/fernand0/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/fernand0/fernand0/releases/tag/v1.0.0
