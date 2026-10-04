# Runs ON THE VPS. Key arrives in $K (exported by the calling shell from stdin). Generates
# the four Konsole sounds through the clean datacenter network, prints status + hashes.
set -e
mkdir -p /root/kxsfx && cd /root/kxsfx
req(){
  curl -4 -sS --max-time 180 -X POST "https://api.us.elevenlabs.io/v1/sound-generation" \
    -H "xi-api-key: $K" -H "Content-Type: application/json" \
    -d "$2" -o "$1" -w "%{http_code} $1\n"
}
req kx-stamp.mp3 '{"text":"single heavy rubber stamp pressed onto paper, crisp decisive thud with a short paper tail, close microphone, dry","duration_seconds":1.2,"prompt_influence":0.6}'
req kx-tick.mp3  '{"text":"one very short soft digital tick, muted and precise, like a mechanical counter incrementing once, dry","duration_seconds":0.5,"prompt_influence":0.6}'
req kx-click.mp3 '{"text":"single soft mechanical switch click, tactile and satisfying, quiet, dry","duration_seconds":0.5,"prompt_influence":0.6}'
req kx-seal.mp3  '{"text":"soft wax seal pressed onto paper, gentle paper crinkle, single press, close microphone","duration_seconds":1,"prompt_influence":0.6}'
echo "== results =="
sha256sum kx-*.mp3
ls -la kx-*.mp3
