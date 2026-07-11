# Deploying drama916 to Alibaba Cloud Function Compute (zip / no registry)

drama916 runs as a **Python 3.10 Web Function** on FC — no container registry.
Everything (app, deps, ffmpeg, showcase films) ships in one code zip, uploaded
via OSS. The app writes to `/tmp` on FC (the code dir is read-only).

**Alisa** does the account setup (verification, activate FC, activate OSS, RAM
keys). **Dan** builds the zip + deploys. Credentialed steps are Dan's/Alisa's —
I don't handle keys.

## 0. Prerequisites
Already done on this Mac (July 11): the zip is **built** at
`fc-build/drama916-fc.zip` (~145M) and its parts are verified — deps are
linux-x86_64/cp310, ffmpeg/ffprobe are amd64 static, the app serves the seeded
rail from `/tmp` in a FC-like test. Rebuild anytime with `./build_fc_zip.sh`.

On Alisa's Alibaba account (region **Singapore, ap-southeast-1**):
- **Function Compute** activated (pay-as-you-go).
- **OSS** activated + a bucket (e.g. `drama916-code`) in Singapore.
- Real-name verification done (gates the above).

## 1. Upload the zip to OSS
The zip is 145M — over FC's 100M direct-upload limit — so it goes through OSS.
In the OSS console (Singapore) → bucket `drama916-code` → **Upload** →
`fc-build/drama916-fc.zip`. Note the bucket name + object key
(`drama916-fc.zip`).

## 2. Create the Web Function (FC console, Singapore)
Functions → **Create Function** → **Use Code** (not container):
- **Runtime**: Python 3.10
- **Function type / request type**: **Web Function** (app listens on a port)
- **Code**: **Upload via OSS** → bucket `drama916-code`, object `drama916-fc.zip`
- **Startup Command**: `bash bootstrap`
- **Listening Port**: `9000`
- **Specifications**: **1 vCPU**, **2 GB** memory, **512 MB** disk
- **Timeout**: `600`
- **Instance Concurrency**: `20`
- **Minimum Instances**: `1`  ← keeps one instance warm so the in-memory run
  state survives (don't set 0)
- **Environment Variables**:
  - `DASHSCOPE_API_KEY` = `sk-...` (the Singapore intl key)
  - (`RUNS_DIR` and `PORT` are set by `bootstrap`, no need to add them)

Create.

## 3. Make the HTTP trigger public
Function → **Triggers** → HTTP trigger → **Authentication: No Authentication**
(anonymous).
⚠️ Default is Signature auth → browsers get `MissingRequiredHeader: Date` and the
URL won't open. Must be **No Auth** for a public demo link.

## 4. Open the URL
The HTTP trigger shows the public URL — that's the Devpost demo link. Open it,
confirm the "Recent generations" rail shows the 4 seeded films, then run one
logline end to end. (First cold start pulls the 145M code + boots ffmpeg — give
it a moment; `Minimum Instances: 1` keeps it warm after.)

## Redeploy after a code change
```bash
./build_fc_zip.sh                 # rebuild the zip
# re-upload fc-build/drama916-fc.zip to the OSS bucket (overwrite)
# FC console → function → Code → re-point/refresh the OSS object, or bump it
```

## Notes / gotchas
- **One run at a time.** State is a single in-memory job. `Minimum Instances: 1`
  keeps it alive; don't raise instance count or concurrent renders collide.
- **New films are ephemeral.** Renders on the deployed instance live in `/tmp`
  and vanish on recycle; only the 4 seeded films are permanent (re-copied from
  the code package at each boot). To persist user films, write them to OSS.
- **Disk.** A render writes stills + 8 clips + audio + the cut into `/tmp`
  (~150M). 512M disk covers it; bump if you hit `No space left`.
- **ffmpeg.** Bundled as static amd64 binaries in `bin/`; `bootstrap` puts them
  on `PATH`. No system ffmpeg needed.
- **Cost.** Each render calls Qwen/HappyHorse (~$3–7). The anonymous URL means
  anyone can spend the key — share for judging, then `s remove` / set auth back.
- **Can't test FC locally.** The zip's parts are verified (arch, /tmp writes,
  integrity), but the FC function itself (startup command, OSS pull, web mode)
  is verified on first deploy. If the startup command field rejects
  `bash bootstrap`, try `./bootstrap`.
