#! /bin/sh

set -ex

keyfile="$GITHUB_WORKSPACE/edgewall_github_key"
known_hosts="$GITHUB_WORKSPACE/edgewall_host_key"

if [ -n "$EDGEWALL_KEY_BASE64" ]; then
    echo "$EDGEWALL_KEY_BASE64" | base64 -d >"$keyfile"
    echo "$EDGEWALL_HOST_KEY" >"$known_hosts"
    chmod 0600 "$keyfile"
    scp -i "$keyfile" -o "UserKnownHostsFile $known_hosts" \
        dist/Trac-* github@edgewall.org:/var/ftp/pub/trac/incoming
else
    echo "::warning:: Skipped uploading package files to edgewall.org" 1>&2
fi
