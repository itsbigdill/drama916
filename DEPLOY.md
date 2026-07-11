# Deploying drama916 to Alibaba Cloud Function Compute

The app is a single stateful HTTP server (`python web.py`) that needs `ffmpeg`.
It's packaged as a container so it runs identically anywhere. Below is the
Function Compute (FC 3.0) path — one always-warm instance behind a public URL.

**You run these steps** — they need your Alibaba credentials, which I don't handle.

## 0. One-time prerequisites
- An Alibaba Cloud account with **Function Compute** and **Container Registry (ACR)** enabled, region **Singapore (ap-southeast-1)**.
- Docker installed locally (this Mac doesn't have it yet: `brew install --cask docker`, then open Docker Desktop).
- Serverless Devs: `npm i -g @serverless-devs/s` then `s config add` (or `export`
  `ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET`).

## 1. Refresh the showcase reel baked into the image (optional)
```bash
./seed_showcase.sh          # curates runs_seed/ (~67M, 4 films, public)
```

## 2. Build and push the image to ACR
Create an ACR namespace (e.g. `drama916`) and an `amd64` build — FC runs x86, so
build with `--platform linux/amd64` on this Apple-Silicon Mac.
```bash
REGISTRY=registry-intl.ap-southeast-1.aliyuncs.com
NS=<your-acr-namespace>
IMAGE=$REGISTRY/$NS/drama916:latest

docker login $REGISTRY                       # ACR username + the registry password you set
docker build --platform linux/amd64 -t $IMAGE .
docker push $IMAGE
```

## 3. Point the config at the image + set the key
- In `s.yaml`, replace `<ACR_IMAGE_URI>` with `$IMAGE` from above.
- Export the DashScope key so `s.yaml` picks it up:
```bash
export DASHSCOPE_API_KEY=sk-...              # the Singapore intl key from .env
```

## 4. Deploy
```bash
s deploy
```
Serverless Devs prints the HTTP trigger URL at the end — that's the public demo
link for the Devpost submission. Open it and confirm the "Recent generations"
rail shows the four seeded films, then run one logline end to end.

## Redeploy after a code change
```bash
docker build --platform linux/amd64 -t $IMAGE . && docker push $IMAGE
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
