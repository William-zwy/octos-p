"""One-time website login; read passwords from an external file, print no secrets."""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


def credentials(path):
    fields = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        parts = re.split(r"[:：=]", line, maxsplit=1)
        if len(parts) != 2:
            continue
        label, value = parts[0].strip().lower(), parts[1].strip()
        if any(word in label for word in ("账号", "账户", "邮箱", "email", "username")):
            fields["email"] = value
        elif "密码" in label or "password" in label:
            fields["password"] = value
    if not all(fields.get(key) for key in ("email", "password")):
        raise ValueError("expected labelled account/email and password lines")
    return fields


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    source, output = Path(args.credentials).resolve(), Path(args.output).resolve()
    if source.is_relative_to(root) or output.is_relative_to(root) or output.exists():
        print("Credentials/output must be external; output must be new")
        return 2
    try:
        payload = json.dumps(credentials(source)).encode("utf-8")
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        request = urllib.request.Request("https://arc-bench.com/api/auth/login", data=payload,
                                         headers={"Content-Type": "application/json"}, method="POST")
        with opener.open(request, timeout=45) as response:
            response.read()  # Never log the response or credentials.
        cookies = "; ".join(f"{cookie.name}={cookie.value}" for cookie in jar)
        if not cookies:
            raise ValueError("login returned no session cookie")
        output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("ARC_BENCH_SESSION_COOKIE=" + cookies + "\n")
            handle.write("ARC_BENCH_HTTP_TIMEOUT_SECONDS=45\n")
        print("Session saved outside repository; run doctor to verify")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"Login failed (HTTP {exc.code}); credentials were not logged")
    except (OSError, ValueError):
        print("Login/file format unavailable; credentials were not logged")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
