# Cloudflare Tunnel Draft

This folder is intentionally **not live**. It contains the example pieces needed to expose Aervyx through Cloudflare Tunnel later.

## Files

- `config.example.yml`: copy to `config.yml` and replace the placeholder tunnel ID before use
- `YOUR-TUNNEL-ID.json`: do not commit this credentials file; place it beside `config.yml` only when you are ready to run the tunnel

## Intended Hostnames

- `aervyx.net` -> frontend (`http://frontend:3000`)
- `api.aervyx.net` -> backend (`http://backend:8000`)

## Activation Reminder

Nothing in this folder is active until you:

1. create a real Cloudflare Tunnel in Zero Trust
2. copy `config.example.yml` to `config.yml`
3. place the matching credentials JSON file in this folder
4. start the `cloudflared` profile from `docker-compose.prod.yml`
