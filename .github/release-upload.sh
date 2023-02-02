#! /bin/sh

set -ex

keyfile="$GITHUB_WORKSPACE/id_rsa"
known_hosts="$GITHUB_WORKSPACE/known_hosts"

openssl aes-256-cbc \
     -d -base64 -in contrib/travis/id_rsa.enc -out "$keyfile" \
     -K "$ENCRYPTED_C097E63A4DDF_KEY" -iv "$ENCRYPTED_C097E63A4DDF_IV" \
|| rm -f "$keyfile"

if [ -f "$keyfile" ]; then
    cp contrib/travis/edgewall_host_key "$known_hosts"
    chmod 0600 "$keyfile"
    scp -i "$keyfile" -o "UserKnownHostsFile $known_hosts" \
        dist/Trac-* travis@edgewall.org:/var/ftp/pub/trac/incoming
else
    echo "::warning:: Skipped uploading package files to edgewall.org" 1>&2
fi
