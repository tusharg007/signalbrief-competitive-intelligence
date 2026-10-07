"""Generate local secrets without overwriting an existing configuration."""
import secrets
from pathlib import Path


def main() -> None:
    target = Path(".env")
    template = Path(".env.example").read_text(encoding="utf-8")
    for key in ("ADMIN_PASSWORD", "WEBHOOK_API_KEY", "SESSION_SECRET"):
        template = template.replace(f"{key}=\n", f"{key}={secrets.token_urlsafe(36)}\n", 1)
    try:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(template)
    except FileExistsError:
        print("Existing .env preserved. Configure it locally; secrets are never printed.")
        return
    print("Created .env with random credentials. Open it locally to configure your model key and Zapier URL.")


if __name__ == "__main__":
    main()
