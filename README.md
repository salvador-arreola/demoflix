# Demoflix — Compute Engine + Cloud Storage

**Repository name: `demoflix`.** Small demo app: **four sample titles** always appear in the UI, using **public-domain NASA photographs** shipped under `app/static/demo/` (see [ATTRIBUTION.md](ATTRIBUTION.md)). Anything **you upload** is stored **on disk** when running locally, or in a **Cloud Storage bucket** when `GCS_BUCKET_NAME` is set (e.g. on a Compute Engine VM).

Push this project to Git (GitHub, GitLab, etc.) as **`demoflix`**, then **clone that repo on the VM** to run the app.

## Behavior

| Mode | How to enable | Uploads |
|------|----------------|---------|
| **Local** | Do **not** set `GCS_BUCKET_NAME` | Files under `data/posters/`, list in `data/catalog.json` |
| **GCP** | Set `GCS_BUCKET_NAME` | Objects under `posters/` in the bucket, list in `catalog.json` |

Demo posters are served from the app bundle (`static/demo/`), not from GCS; only your uploads use the bucket in GCP mode.

## Requirements

- Python 3.10+
- **Local mode**: no Google credentials needed for browsing and uploading.
- **GCS mode**: Application Default Credentials (`gcloud auth application-default login` locally, or the VM service account on GCE).

### Install dependencies (any environment)

From the **repository root** (the `demoflix` folder after clone):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `GCS_BUCKET_NAME` | If set, uploads go to this bucket (name only, no `gs://`). |
| `DATA_DIR` | Optional. Local mode only: where `data/` lives (default: `<project>/data`). |

See [`.env.example`](.env.example).

## Run locally (disk only)

```bash
git clone https://github.com/salvador-arreola/demoflix.git
cd demoflix
# create venv + pip install (see above)
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

Official remote: [github.com/salvador-arreola/demoflix](https://github.com/salvador-arreola/demoflix). You can use SSH instead: `git clone git@github.com:salvador-arreola/demoflix.git`. Open `http://127.0.0.1:8080`. Uploads are saved under `data/`.

## Run locally against Cloud Storage

```bash
cd demoflix
export GCS_BUCKET_NAME="your-unique-bucket"
gcloud auth application-default login
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

Give your user (or ADC) permission to write objects to the bucket. For thumbnails to load in the browser, the bucket usually needs **public read** for demo buckets (e.g. principal `allUsers` → **Storage Object Viewer**) or another pattern you prefer.

## Deploy on Compute Engine

Use a VM with a service account that has `roles/storage.objectAdmin` on the bucket, open port **8080** in a firewall rule, and set `GCS_BUCKET_NAME` when you run the app.

### 1. Project and bucket

```bash
gcloud config set project PROJECT_ID
gsutil mb -l REGION gs://BUCKET
```

### 2. Service account and bucket IAM

```bash
gcloud iam service-accounts create demoflix-sa \
  --display-name="Demoflix GCE"

SA_EMAIL="demoflix-sa@PROJECT_ID.iam.gserviceaccount.com"

gsutil iam ch serviceAccount:${SA_EMAIL}:roles/storage.objectAdmin gs://BUCKET
```

### 3. Firewall (port 8080)

Tighten `--source-ranges` to your IP or network; `0.0.0.0/0` is only for quick tests.

```bash
gcloud compute firewall-rules create allow-demoflix-8080 \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=demoflix
```

### 4. Create the VM

```bash
gcloud compute instances create VM_NAME \
  --zone=ZONE \
  --machine-type=e2-small \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --tags=demoflix \
  --service-account=${SA_EMAIL} \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

### 5. Clone `demoflix` on the VM and install

SSH into the VM (`gcloud compute ssh VM_NAME --zone=ZONE`), then:

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip
cd ~
git clone https://github.com/salvador-arreola/demoflix.git
cd demoflix
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

This repo is **public**, so HTTPS clone on the VM is enough. If you fork it or make it private, use SSH keys on the VM, a [credential helper](https://git-scm.com/book/en/v2/Git-Tools-Credential-Storage), or a deploy token.

Run the app (set `BUCKET` to your bucket name):

```bash
export GCS_BUCKET_NAME=BUCKET
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

To update the app after you push new commits:

```bash
cd ~/demoflix
git pull
source .venv/bin/activate
pip install -r requirements.txt   # if dependencies changed
```

For anything beyond a quick demo, use `tmux`/`screen`, a process manager, or a reverse proxy in front of `uvicorn` as you normally would.

Get the VM’s external IP and open `http://EXTERNAL_IP:8080`.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web UI |
| GET | `/api/health` | `storage`: `local` or `gcs` |
| GET | `/api/movies` | Four demos + your uploads |
| POST | `/api/movies` | `multipart/form-data`: `title`, `poster` |

## Project layout

- [`app/main.py`](app/main.py) — routing, local vs GCS storage.
- [`app/static/demo/`](app/static/demo/) — bundled public-domain demo JPEGs (see [ATTRIBUTION.md](ATTRIBUTION.md)).

Max upload size: 5 MB. Formats: JPEG, PNG, WebP, GIF.

## License

Educational / demo use.
