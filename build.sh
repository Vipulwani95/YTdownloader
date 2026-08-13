#!/usr/bin/env bash
set -e

# Install Deno (required by yt-dlp for YouTube JS extraction)
curl -fsSL https://deno.land/install.sh | sh
export DENO_INSTALL="$HOME/.deno"
export PATH="$DENO_INSTALL/bin:$PATH"

# Verify Deno is available
deno --version

# Install Python dependencies
pip install -r requirements.txt
