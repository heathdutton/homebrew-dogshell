#!/usr/bin/env python3
"""
Generates/updates the Homebrew formula for dogshell by fetching all
package metadata directly from the PyPI JSON API.

No dependency on pip, poet, or any installed packages.
Always fetches canonical URLs and sha256 hashes fresh from PyPI.
"""

import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request

FORMULA_PATH = "Formula/dogshell.rb"
PACKAGE = "datadog"
PYTHON_VERSION = "3.13"


def pypi_info(package, version=None):
    """Fetch package info from PyPI JSON API."""
    if version:
        url = f"https://pypi.org/pypi/{package}/{version}/json"
    else:
        url = f"https://pypi.org/pypi/{package}/json"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def get_runtime_deps(data, depth=0):
    """Recursively discover runtime dependencies from PyPI requires_dist.

    Filters out extras, dev deps, and Python 2 only deps.
    Returns a flat set of canonical package names.
    """
    if depth > 5:
        return set()
    deps = set()
    requires = data["info"].get("requires_dist") or []
    for req in requires:
        # Skip extras (e.g., 'foo ; extra == "dev"')
        if "extra ==" in req or "extra==" in req:
            continue
        # Skip Python 2 only deps
        if 'python_version < "3' in req or "python_version<" in req:
            continue
        # Extract package name (first token before any version specifier)
        name = re.split(r"[;>=<!\s\[]", req)[0].strip().lower()
        if name and name != PACKAGE:
            deps.add(name)
            # Recurse into transitive deps
            try:
                sub_data = pypi_info(name)
                deps |= get_runtime_deps(sub_data, depth + 1)
            except Exception:
                pass
    return deps


def get_sdist(data):
    """Extract sdist URL and sha256 from PyPI response."""
    for f in data["urls"]:
        if f["packagetype"] == "sdist":
            return f["url"], f["digests"]["sha256"]
    raise RuntimeError(f"No sdist found for {data['info']['name']} {data['info']['version']}")


def verify_sha256(url, expected_sha):
    """Download the file and verify its sha256 matches PyPI's claim."""
    with tempfile.NamedTemporaryFile() as tmp:
        urllib.request.urlretrieve(url, tmp.name)
        actual = hashlib.sha256(open(tmp.name, "rb").read()).hexdigest()
    if actual != expected_sha:
        raise RuntimeError(f"SHA256 mismatch for {url}: expected {expected_sha}, got {actual}")


def current_formula_state():
    """Parse current version and all resource URLs from the formula."""
    if not os.path.exists(FORMULA_PATH):
        return None, set()
    with open(FORMULA_PATH) as f:
        content = f.read()
    m = re.search(r'datadog-(\d+\.\d+\.\d+)', content)
    version = m.group(1) if m else None
    urls = set(re.findall(r'url "([^"]+)"', content))
    return version, urls


def resource_stanza(name, url, sha256):
    """Generate a Homebrew resource block."""
    return f'''  resource "{name}" do
    url "{url}"
    sha256 "{sha256}"
  end'''


def generate_formula(pkg_url, pkg_sha, resources):
    """Generate the complete formula file."""
    resource_blocks = "\n\n".join(resources)
    return f'''class Dogshell < Formula
  include Language::Python::Virtualenv

  desc "CLI tool for interacting with the Datadog API"
  homepage "https://docs.datadoghq.com/developers/guide/dogshell/"
  url "{pkg_url}"
  sha256 "{pkg_sha}"
  license "BSD-3-Clause"

  depends_on "python@{PYTHON_VERSION}"

{resource_blocks}

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "usage:", shell_output("#{{bin}}/dogshell -h")
  end
end
'''


def set_output(key, value):
    """Set a GitHub Actions output variable."""
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write(f"{key}={value}\n")
    print(f"  {key}={value}")


def main():
    print("Fetching latest datadog version from PyPI...")
    data = pypi_info(PACKAGE)
    latest = data["info"]["version"]
    current, current_urls = current_formula_state()
    print(f"  Current: {current}")
    print(f"  Latest:  {latest}")

    # Get main package sdist
    pkg_url, pkg_sha = get_sdist(data)
    print(f"  {PACKAGE}: {pkg_url}")

    # Discover runtime deps dynamically from PyPI metadata
    deps = get_runtime_deps(data)
    print(f"  Dependencies: {sorted(deps)}")

    # Collect all new URLs to compare against current formula
    new_urls = {pkg_url}

    # Get each dependency's latest sdist
    resources = []
    for dep in sorted(deps):
        dep_data = pypi_info(dep)
        dep_url, dep_sha = get_sdist(dep_data)
        dep_version = dep_data["info"]["version"]
        print(f"  {dep} {dep_version}: {dep_url}")
        new_urls.add(dep_url)
        resources.append((dep, dep_url, dep_sha))

    # Check if anything actually changed
    if current == latest and new_urls == current_urls:
        print("Already up to date (version and all dependency URLs match).")
        set_output("updated", "false")
        return

    if current == latest:
        print("Same datadog version, but dependency URLs changed. Updating...")
    else:
        print(f"Updating datadog {current} -> {latest}...")

    # Verify all downloads
    print("Verifying SHA256 checksums...")
    verify_sha256(pkg_url, pkg_sha)
    resource_stanzas = []
    for dep, dep_url, dep_sha in resources:
        verify_sha256(dep_url, dep_sha)
        resource_stanzas.append(resource_stanza(dep, dep_url, dep_sha))

    formula = generate_formula(pkg_url, pkg_sha, resource_stanzas)

    os.makedirs(os.path.dirname(FORMULA_PATH), exist_ok=True)
    with open(FORMULA_PATH, "w") as f:
        f.write(formula)

    print(f"Formula written for datadog {latest}.")
    set_output("updated", "true")
    set_output("version", latest)


if __name__ == "__main__":
    main()
