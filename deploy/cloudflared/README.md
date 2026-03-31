# Cloudflare Tunnel Draft

This folder is intentionally **not live**. It contains the example pieces needed to expose Aervyx through Cloudflare Tunnel later.

## Files

- `config.example.yml`: copy to `config.yml` and replace the placeholder tunnel ID before use
- `staging.config.example.yml`: staging variant for `staging.aervyx.net`, `api-staging.aervyx.net`, and the GitHub deploy hook endpoint
- `YOUR-TUNNEL-ID.json`: do not commit this credentials file; place it beside `config.yml` only when you are ready to run the tunnel

## Intended Hostnames

- `aervyx.net` -> frontend (`http://frontend:3000`)
- `api.aervyx.net` -> backend (`http://backend:8000`)
- `staging.aervyx.net` -> frontend (`http://frontend:3000`)
- `api-staging.aervyx.net` -> backend (`http://backend:8000`)
- `deploy-staging.aervyx.net` -> host-side webhook listener (`http://host.docker.internal:9100`)

## Activation Reminder

Nothing in this folder is active until you:

1. create a real Cloudflare Tunnel in Zero Trust
2. copy `config.example.yml` to `config.yml`
3. place the matching credentials JSON file in this folder
4. start the `cloudflared` profile from `docker-compose.prod.yml`

## Staging Note

The staging webhook route relies on Docker's `host-gateway` mapping so the
`cloudflared` container can reach a host-side listener on
`host.docker.internal:9100`.
