# homebrew-dogshell

Homebrew tap for [dogshell](https://docs.datadoghq.com/developers/guide/dogshell/), the Datadog CLI tool.

## Install

```bash
brew tap heathdutton/dogshell
brew install dogshell
```

## Usage

```bash
# Configure with your Datadog API/App keys
dogshell --help
```

See the [official docs](https://docs.datadoghq.com/developers/guide/dogshell/) for full usage.

## Updates

The formula is automatically updated weekly via GitHub Actions when new versions of the `datadog` Python package are released.
