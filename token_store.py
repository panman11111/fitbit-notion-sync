"""
token_store — Fitbitトークンの永続化・読み込み共通モジュール

公開API:
  - update_github_secret(name, value, repo, pat) -> None
  - persist_tokens(access_token, refresh_token) -> None
  - load_tokens() -> tuple[str, str]

内部API:
  - _encrypt_secret(secret_value, public_key_b64) -> str
"""

from __future__ import annotations

import base64
import os
import re

import requests
from dotenv import load_dotenv


# ------------------------------------------------------------------ #
# 内部ヘルパー
# ------------------------------------------------------------------ #


def _encrypt_secret(secret_value: str, public_key_b64: str) -> str:
    """
    GitHub Secrets API 用に NaCl Sealed Box で暗号化する。

    Args:
        secret_value: 暗号化するシークレット文字列
        public_key_b64: base64エンコードされた公開鍵（GitHub APIから取得）

    Returns:
        base64エンコードされた暗号化済み文字列
    """
    from nacl import encoding, public

    public_key_bytes = base64.b64decode(public_key_b64)
    public_key = public.PublicKey(public_key_bytes, encoding.RawEncoder)
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


# ------------------------------------------------------------------ #
# 公開API
# ------------------------------------------------------------------ #


def update_github_secret(name: str, value: str, repo: str, pat: str) -> None:
    """
    GitHub Secrets API でリポジトリシークレットを更新する。

    Args:
        name: シークレット名（例: "FITBIT_ACCESS_TOKEN"）
        value: シークレットの値
        repo: "owner/repo" 形式のリポジトリ名
        pat: GitHub Personal Access Token (BOT_PAT)

    Raises:
        RuntimeError: 公開鍵取得またはシークレット更新に失敗した場合
    """
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base_url = f"https://api.github.com/repos/{repo}/actions/secrets"

    # リポジトリの公開鍵を取得
    key_resp = requests.get(f"{base_url}/public-key", headers=headers)
    if key_resp.status_code != 200:
        raise RuntimeError(
            f"Failed to get GitHub Actions public key: {key_resp.status_code} {key_resp.text}"
        )

    key_data = key_resp.json()
    key_id: str = key_data["key_id"]
    public_key_b64: str = key_data["key"]

    encrypted_value = _encrypt_secret(value, public_key_b64)

    put_resp = requests.put(
        f"{base_url}/{name}",
        headers=headers,
        json={"encrypted_value": encrypted_value, "key_id": key_id},
    )
    if put_resp.status_code not in (201, 204):
        raise RuntimeError(
            f"Failed to update GitHub secret '{name}': {put_resp.status_code} {put_resp.text}"
        )


def persist_tokens(access_token: str, refresh_token: str) -> None:
    """
    Fitbitトークンを永続化する。

    - GITHUB_ACTIONS=true のとき: BOT_PAT を使って GitHub Secrets API を更新
    - それ以外のとき: .env ファイルを更新（ローカル実行）

    Args:
        access_token: 新しいFitbitアクセストークン
        refresh_token: 新しいFitbitリフレッシュトークン

    Raises:
        RuntimeError: GITHUB_ACTIONS=true 時に BOT_PAT または GITHUB_REPOSITORY が未設定の場合
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        _persist_tokens_to_secrets(access_token, refresh_token)
    else:
        _persist_tokens_to_dotenv(access_token, refresh_token)


def load_tokens() -> tuple[str, str]:
    """
    環境変数からFitbitトークンを読み込む。

    .env ファイルがあれば load_dotenv() を実行してから環境変数を読む。

    Returns:
        (access_token, refresh_token) のタプル

    Raises:
        RuntimeError: FITBIT_ACCESS_TOKEN または FITBIT_REFRESH_TOKEN が未設定・空文字の場合
    """
    load_dotenv()

    access_token = os.environ.get("FITBIT_ACCESS_TOKEN", "")
    refresh_token = os.environ.get("FITBIT_REFRESH_TOKEN", "")

    if not access_token:
        raise RuntimeError(
            "FITBIT_ACCESS_TOKEN が設定されていません。"
            "環境変数または .env ファイルで設定してください。"
        )
    if not refresh_token:
        raise RuntimeError(
            "FITBIT_REFRESH_TOKEN が設定されていません。"
            "環境変数または .env ファイルで設定してください。"
        )

    return (access_token, refresh_token)


# ------------------------------------------------------------------ #
# 内部実装
# ------------------------------------------------------------------ #


def _persist_tokens_to_secrets(access_token: str, refresh_token: str) -> None:
    """GitHub Secrets API を使ってトークンを更新する（GitHub Actions 専用）"""
    pat = os.environ.get("BOT_PAT", "")
    if not pat:
        raise RuntimeError(
            "BOT_PAT が設定されていません。"
            "GitHub Actions の環境変数に BOT_PAT を追加してください。"
        )

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        raise RuntimeError(
            "GITHUB_REPOSITORY が設定されていません。"
            "GitHub Actions では自動設定されるはずです。"
        )

    update_github_secret("FITBIT_ACCESS_TOKEN", access_token, repo, pat)
    update_github_secret("FITBIT_REFRESH_TOKEN", refresh_token, repo, pat)


def _persist_tokens_to_dotenv(access_token: str, refresh_token: str) -> None:
    """ローカル実行時に .env ファイルへトークンを書き込む"""
    env_path = ".env"

    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = _upsert_env_var(content, "FITBIT_ACCESS_TOKEN", access_token)
        content = _upsert_env_var(content, "FITBIT_REFRESH_TOKEN", refresh_token)
    else:
        content = (
            f"FITBIT_ACCESS_TOKEN={access_token}\n"
            f"FITBIT_REFRESH_TOKEN={refresh_token}\n"
        )

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)


def _upsert_env_var(content: str, key: str, value: str) -> str:
    """
    .env 形式の文字列内で指定キーの値を更新する。
    キーが存在しない場合は末尾に追記する。

    Args:
        content: .env ファイルの全文
        key: 環境変数名
        value: 新しい値

    Returns:
        更新後の .env 文字列
    """
    pattern = re.compile(rf"^({re.escape(key)}=).*$", re.MULTILINE)
    if pattern.search(content):
        return pattern.sub(rf"\g<1>{value}", content)

    # 末尾改行を正規化してから追記
    if content and not content.endswith("\n"):
        content += "\n"
    content += f"{key}={value}\n"
    return content
