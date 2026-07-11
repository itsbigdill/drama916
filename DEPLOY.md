# Deploying drama916 to Alibaba Cloud Function Compute

The app is a single stateful HTTP server (`python web.py`) that needs `ffmpeg`.
It's packaged as a container so it runs identically anywhere. Below is the
Function Compute (FC 3.0) path — one always-warm instance behind a public URL.

**You run the credentialed steps** (login / push / deploy) — they need your
Alibaba access keys, which I don't handle. Everything else is already set up.

## 0. Prerequisites — DONE on this Mac
Already installed and verified July 11:
- **Docker via colima** (headless, no Docker Desktop) — daemon running (`colima status`).
- **docker CLI** and **Serverless Devs** (`s`, v3.1.10).
- The image is **already built and smoke-tested** as `drama916:test`
  (linux/amd64, ffmpeg present, all 4 seeded films serve, health check green).

If colima ever stops: `colima start`. To rebuild the image:
`./seed_showcase.sh && docker build --platform linux/amd64 -t drama916:test .`

You still need, on your side:
- An Alibaba account with **Function Compute** + **Container Registry (ACR)** in
  **Singapore (ap-southeast-1)** — this is the wife's account.
- Your Alibaba access keys: `s config add` (or export
  `ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET`).

## 1. Tag the built image for your ACR + push
Create an ACR namespace (e.g. `drama916`) in the Singapore registry, then:
```bash
REGISTRY=registry-intl.ap-southeast-1.aliyuncs.com
NS=<your-acr-namespace>
IMAGE=$REGISTRY/$NS/drama916:latest

docker login $REGISTRY                       # ACR username + the registry password you set
docker tag drama916:test $IMAGE              # the image is already built
docker push $IMAGE
```

## 2. Point the config at the image + set the key
- In `s.yaml`, replace `<ACR_IMAGE_URI>` with `$IMAGE` from above.
- Export the DashScope key so `s.yaml` picks it up:
```bash
export DASHSCOPE_API_KEY=sk-...              # the Singapore intl key from .env
```

## 3. Deploy
```bash
s deploy
```
Serverless Devs prints the HTTP trigger URL at the end — that's the public demo
link for the Devpost submission. Open it and confirm the "Recent generations"
rail shows the four seeded films, then run one logline end to end.

## Redeploy after a code change
```bash
./seed_showcase.sh   # only if you changed the showcase films
docker build --platform linux/amd64 -t drama916:test .
docker tag drama916:test $IMAGE && docker push $IMAGE
s deploy                                     # picks up the new image
```

## Notes / gotchas
- **One run at a time.** State is a single in-memory job (it's a demo, not a farm).
  The provisioned instance (target 1) keeps that state alive; don't raise the
  instance count or concurrent renders will collide.
- **New films are ephemeral.** Runs generated on the deployed instance live on its
  local disk and vanish on redeploy/recycle; only the `runs_seed/` films are
  permanent. To persist user films, mount an NAS at `/app/runs` (FC → NAS).
- **Cost.** Each render calls Qwen/HappyHorse (~$3–7 as the seed captions show).
  The anonymous public URL means anyone can spend the key — share it for judging,
  then tear down (`s remove`) or set `authType: function` afterwards.
- **Fallback host.** The same image runs on any container platform (ECS, SAE,
  Render, Fly) if FC's stateful model gives trouble — just run the image with
  `DASHSCOPE_API_KEY` set and expose port 9000.
