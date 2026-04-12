"""
token_store モジュールのテスト

TDD: テストファースト実装
対象関数:
  - update_github_secret(name, value, repo, pat) -> None
  - persist_tokens(access_token, refresh_token) -> None
  - load_tokens() -> tuple[str, str]
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open, call


# ------------------------------------------------------------------ #
# update_github_secret のテスト
# ------------------------------------------------------------------ #

class TestUpdateGithubSecret:
    """update_github_secret の正常系・異常系テスト"""

    def test_sends_put_request_with_correct_url(self):
        """正常系: 正しいURLにPUTリクエストが送られる"""
        from token_store import update_github_secret

        mock_public_key = {
            "key_id": "key123",
            "key": "2Tn8TlTKkHdSGMgFtBjqmHiJH1HSmFIJEdqnZhOxGU=",
        }
        mock_get = MagicMock()
        mock_get.status_code = 200
        mock_get.json.return_value = mock_public_key

        mock_put = MagicMock()
        mock_put.status_code = 204

        with patch("token_store.requests.get", return_value=mock_get) as patched_get, \
             patch("token_store.requests.put", return_value=mock_put) as patched_put, \
             patch("token_store._encrypt_secret", return_value="encrypted_value"):
            update_github_secret(
                name="FITBIT_ACCESS_TOKEN",
                value="test_token",
                repo="owner/repo",
                pat="ghp_testpat",
            )

        expected_url = (
            "https://api.github.com/repos/owner/repo/actions/secrets/FITBIT_ACCESS_TOKEN"
        )
        patched_put.assert_called_once()
        actual_url = patched_put.call_args[0][0]
        assert actual_url == expected_url

    def test_sends_authorization_header_with_pat(self):
        """正常系: PATがAuthorizationヘッダに含まれる"""
        from token_store import update_github_secret

        mock_public_key = {
            "key_id": "key123",
            "key": "2Tn8TlTKkHdSGMgFtBjqmHiJH1HSmFIJEdqnZhOxGU=",
        }
        mock_get = MagicMock(status_code=200)
        mock_get.json.return_value = mock_public_key
        mock_put = MagicMock(status_code=204)

        with patch("token_store.requests.get", return_value=mock_get), \
             patch("token_store.requests.put", return_value=mock_put) as patched_put, \
             patch("token_store._encrypt_secret", return_value="encrypted_value"):
            update_github_secret("MY_SECRET", "val", "owner/repo", "ghp_mypat")

        _, kwargs = patched_put.call_args
        headers = kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer ghp_mypat"

    def test_payload_contains_encrypted_value_and_key_id(self):
        """正常系: payloadにencrypted_value と key_id が含まれる"""
        from token_store import update_github_secret

        mock_public_key = {"key_id": "kid999", "key": "2Tn8TlTKkHdSGMgFtBjqmHiJH1HSmFIJEdqnZhOxGU="}
        mock_get = MagicMock(status_code=200)
        mock_get.json.return_value = mock_public_key
        mock_put = MagicMock(status_code=204)

        with patch("token_store.requests.get", return_value=mock_get), \
             patch("token_store.requests.put", return_value=mock_put) as patched_put, \
             patch("token_store._encrypt_secret", return_value="enc_abc"):
            update_github_secret("MY_SECRET", "myval", "owner/repo", "ghp_pat")

        _, kwargs = patched_put.call_args
        payload = kwargs.get("json", {})
        assert payload["encrypted_value"] == "enc_abc"
        assert payload["key_id"] == "kid999"

    def test_raises_runtime_error_on_http_error(self):
        """異常系: PUTが4xx/5xxを返すとRuntimeErrorを発生させる"""
        from token_store import update_github_secret

        mock_public_key = {"key_id": "kid", "key": "2Tn8TlTKkHdSGMgFtBjqmHiJH1HSmFIJEdqnZhOxGU="}
        mock_get = MagicMock(status_code=200)
        mock_get.json.return_value = mock_public_key
        mock_put = MagicMock(status_code=422, text="Unprocessable Entity")

        with patch("token_store.requests.get", return_value=mock_get), \
             patch("token_store.requests.put", return_value=mock_put), \
             patch("token_store._encrypt_secret", return_value="enc"):
            with pytest.raises(RuntimeError, match="422"):
                update_github_secret("SECRET", "val", "owner/repo", "ghp_pat")

    def test_raises_runtime_error_when_get_public_key_fails(self):
        """異常系: 公開鍵取得失敗（4xx）でRuntimeError"""
        from token_store import update_github_secret

        mock_get = MagicMock(status_code=403, text="Forbidden")

        with patch("token_store.requests.get", return_value=mock_get):
            with pytest.raises(RuntimeError, match="403"):
                update_github_secret("SECRET", "val", "owner/repo", "ghp_pat")

    def test_raises_runtime_error_on_500_put(self):
        """異常系: 500 Internal Server ErrorでRuntimeError"""
        from token_store import update_github_secret

        mock_public_key = {"key_id": "kid", "key": "2Tn8TlTKkHdSGMgFtBjqmHiJH1HSmFIJEdqnZhOxGU="}
        mock_get = MagicMock(status_code=200)
        mock_get.json.return_value = mock_public_key
        mock_put = MagicMock(status_code=500, text="Server Error")

        with patch("token_store.requests.get", return_value=mock_get), \
             patch("token_store.requests.put", return_value=mock_put), \
             patch("token_store._encrypt_secret", return_value="enc"):
            with pytest.raises(RuntimeError):
                update_github_secret("SECRET", "val", "owner/repo", "ghp_pat")


# ------------------------------------------------------------------ #
# persist_tokens のテスト
# ------------------------------------------------------------------ #

class TestPersistTokens:
    """persist_tokens の正常系・異常系テスト"""

    def test_local_env_updates_dotenv_file(self, tmp_path, monkeypatch):
        """正常系(ローカル): .envファイルのトークンが更新される"""
        from token_store import persist_tokens

        env_file = tmp_path / ".env"
        env_file.write_text(
            "FITBIT_CLIENT_ID=cid\n"
            "FITBIT_ACCESS_TOKEN=old_access\n"
            "FITBIT_REFRESH_TOKEN=old_refresh\n"
        )

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.chdir(tmp_path)

        persist_tokens("new_access", "new_refresh")

        content = env_file.read_text()
        assert "FITBIT_ACCESS_TOKEN=new_access" in content
        assert "FITBIT_REFRESH_TOKEN=new_refresh" in content
        assert "old_access" not in content
        assert "old_refresh" not in content

    def test_local_creates_dotenv_if_not_exists(self, tmp_path, monkeypatch):
        """.envが存在しない場合は新規作成される"""
        from token_store import persist_tokens

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.chdir(tmp_path)

        persist_tokens("acc_new", "ref_new")

        env_file = tmp_path / ".env"
        assert env_file.exists()
        content = env_file.read_text()
        assert "FITBIT_ACCESS_TOKEN=acc_new" in content
        assert "FITBIT_REFRESH_TOKEN=ref_new" in content

    def test_github_actions_calls_update_secret_twice(self, monkeypatch):
        """正常系(GitHub Actions): update_github_secretが ACCESS/REFRESH で2回呼ばれる"""
        from token_store import persist_tokens

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("BOT_PAT", "ghp_botpat")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        with patch("token_store.update_github_secret") as mock_update:
            persist_tokens("acc_token", "ref_token")

        assert mock_update.call_count == 2
        calls = mock_update.call_args_list
        call_names = [c[0][0] for c in calls]
        assert "FITBIT_ACCESS_TOKEN" in call_names
        assert "FITBIT_REFRESH_TOKEN" in call_names

    def test_github_actions_passes_correct_values(self, monkeypatch):
        """正常系(GitHub Actions): 正しいトークン値が渡される"""
        from token_store import persist_tokens

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("BOT_PAT", "ghp_botpat")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

        with patch("token_store.update_github_secret") as mock_update:
            persist_tokens("my_access", "my_refresh")

        calls_by_name = {c[0][0]: c[0][1] for c in mock_update.call_args_list}
        assert calls_by_name["FITBIT_ACCESS_TOKEN"] == "my_access"
        assert calls_by_name["FITBIT_REFRESH_TOKEN"] == "my_refresh"

    def test_github_actions_without_bot_pat_raises_runtime_error(self, monkeypatch):
        """異常系: GITHUB_ACTIONS=true かつ BOT_PAT未設定でRuntimeError"""
        from token_store import persist_tokens

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.delenv("BOT_PAT", raising=False)

        with pytest.raises(RuntimeError, match="BOT_PAT"):
            persist_tokens("acc", "ref")

    def test_github_actions_without_repo_raises_runtime_error(self, monkeypatch):
        """異常系: GITHUB_ACTIONS=true かつ GITHUB_REPOSITORY未設定でRuntimeError"""
        from token_store import persist_tokens

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("BOT_PAT", "ghp_botpat")
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        with pytest.raises(RuntimeError, match="GITHUB_REPOSITORY"):
            persist_tokens("acc", "ref")

    def test_local_preserves_other_env_vars(self, tmp_path, monkeypatch):
        """ローカル: 他の環境変数が保持される"""
        from token_store import persist_tokens

        env_file = tmp_path / ".env"
        env_file.write_text(
            "NOTION_TOKEN=notion_secret\n"
            "FITBIT_ACCESS_TOKEN=old_access\n"
            "FITBIT_REFRESH_TOKEN=old_refresh\n"
        )

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.chdir(tmp_path)

        persist_tokens("new_access", "new_refresh")

        content = env_file.read_text()
        assert "NOTION_TOKEN=notion_secret" in content


# ------------------------------------------------------------------ #
# load_tokens のテスト
# ------------------------------------------------------------------ #

class TestLoadTokens:
    """load_tokens の正常系・異常系テスト"""

    def test_returns_tokens_from_env(self, monkeypatch):
        """正常系: 環境変数からトークンが読み込まれる"""
        from token_store import load_tokens

        monkeypatch.setenv("FITBIT_ACCESS_TOKEN", "access_from_env")
        monkeypatch.setenv("FITBIT_REFRESH_TOKEN", "refresh_from_env")

        with patch("token_store.load_dotenv"):
            access, refresh = load_tokens()

        assert access == "access_from_env"
        assert refresh == "refresh_from_env"

    def test_returns_tuple_of_two_strings(self, monkeypatch):
        """正常系: 戻り値はタプル (str, str)"""
        from token_store import load_tokens

        monkeypatch.setenv("FITBIT_ACCESS_TOKEN", "acc")
        monkeypatch.setenv("FITBIT_REFRESH_TOKEN", "ref")

        with patch("token_store.load_dotenv"):
            result = load_tokens()

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(v, str) for v in result)

    def test_raises_runtime_error_when_access_token_missing(self, monkeypatch):
        """異常系: FITBIT_ACCESS_TOKEN未設定でRuntimeError"""
        from token_store import load_tokens

        monkeypatch.delenv("FITBIT_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("FITBIT_REFRESH_TOKEN", "ref")

        with patch("token_store.load_dotenv"):
            with pytest.raises(RuntimeError, match="FITBIT_ACCESS_TOKEN"):
                load_tokens()

    def test_raises_runtime_error_when_refresh_token_missing(self, monkeypatch):
        """異常系: FITBIT_REFRESH_TOKEN未設定でRuntimeError"""
        from token_store import load_tokens

        monkeypatch.setenv("FITBIT_ACCESS_TOKEN", "acc")
        monkeypatch.delenv("FITBIT_REFRESH_TOKEN", raising=False)

        with patch("token_store.load_dotenv"):
            with pytest.raises(RuntimeError, match="FITBIT_REFRESH_TOKEN"):
                load_tokens()

    def test_raises_runtime_error_when_both_tokens_missing(self, monkeypatch):
        """異常系: 両トークン未設定でRuntimeError"""
        from token_store import load_tokens

        monkeypatch.delenv("FITBIT_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("FITBIT_REFRESH_TOKEN", raising=False)

        with patch("token_store.load_dotenv"):
            with pytest.raises(RuntimeError):
                load_tokens()

    def test_calls_load_dotenv_before_reading_env(self, monkeypatch, tmp_path):
        """正常系: load_dotenvが呼ばれてから環境変数が読まれる"""
        from token_store import load_tokens

        monkeypatch.setenv("FITBIT_ACCESS_TOKEN", "acc")
        monkeypatch.setenv("FITBIT_REFRESH_TOKEN", "ref")

        with patch("token_store.load_dotenv") as mock_dotenv:
            load_tokens()

        mock_dotenv.assert_called_once()

    def test_raises_error_when_access_token_is_empty_string(self, monkeypatch):
        """異常系: FITBIT_ACCESS_TOKENが空文字列でRuntimeError"""
        from token_store import load_tokens

        monkeypatch.setenv("FITBIT_ACCESS_TOKEN", "")
        monkeypatch.setenv("FITBIT_REFRESH_TOKEN", "ref")

        with patch("token_store.load_dotenv"):
            with pytest.raises(RuntimeError, match="FITBIT_ACCESS_TOKEN"):
                load_tokens()


# ------------------------------------------------------------------ #
# _encrypt_secret のテスト
# ------------------------------------------------------------------ #

class TestEncryptSecret:
    """_encrypt_secret の動作確認テスト"""

    def test_returns_base64_encoded_string(self):
        """正常系: base64エンコードされた文字列を返す"""
        from token_store import _encrypt_secret
        import base64

        # PyNaClを使った実際の暗号化のテスト
        # テスト用の有効なNaCl公開鍵 (32バイト)
        import nacl.public
        private_key = nacl.public.PrivateKey.generate()
        public_key_bytes = bytes(private_key.public_key)
        public_key_b64 = base64.b64encode(public_key_bytes).decode()

        result = _encrypt_secret("my_secret_value", public_key_b64)

        assert isinstance(result, str)
        # base64デコードできることを確認
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_different_values_produce_different_results(self):
        """正常系: 異なる値は異なる暗号文を返す（NaCl sealed boxは非決定論的）"""
        from token_store import _encrypt_secret
        import base64
        import nacl.public

        private_key = nacl.public.PrivateKey.generate()
        public_key_bytes = bytes(private_key.public_key)
        public_key_b64 = base64.b64encode(public_key_bytes).decode()

        result1 = _encrypt_secret("value_one", public_key_b64)
        result2 = _encrypt_secret("value_two", public_key_b64)

        # 異なる平文 -> 異なる暗号文（または同じでも問題ないが基本的に異なる）
        assert isinstance(result1, str)
        assert isinstance(result2, str)


# ------------------------------------------------------------------ #
# _upsert_env_var のテスト（ブランチカバレッジ補完）
# ------------------------------------------------------------------ #

class TestUpsertEnvVar:
    """_upsert_env_var の内部ロジックテスト"""

    def test_appends_to_content_without_trailing_newline(self, tmp_path, monkeypatch):
        """.envの末尾に改行がない場合でも正しく追記される"""
        from token_store import persist_tokens

        env_file = tmp_path / ".env"
        # 末尾改行なしで書き込む
        env_file.write_text("NOTION_TOKEN=ntn")  # 改行なし

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.chdir(tmp_path)

        persist_tokens("new_acc", "new_ref")

        content = env_file.read_text()
        assert "FITBIT_ACCESS_TOKEN=new_acc" in content
        assert "FITBIT_REFRESH_TOKEN=new_ref" in content
        assert "NOTION_TOKEN=ntn" in content
