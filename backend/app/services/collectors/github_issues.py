"""Bounded collector for public GitHub repository issues via its official REST API.

Pull requests are excluded because their endpoints are returned in the issues
collection but are not customer feedback. Usernames are deliberately not stored.
"""
import json
import os
import re
import time
from urllib.parse import quote, urlsplit

import requests

from app.errors.exceptions import CollectionError
from app.services.collectors.base import BaseCollector, CollectorResult, normalized_record
from app.services.collectors.security import ssrf_safe_connections, validate_url_ssrf


API_BASE = "https://api.github.com"
API_VERSION = "2026-03-10"
MAX_PAGE_SIZE = 100
MAX_ISSUE_TEXT_CHARS = 20_000
_OWNER_OR_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def _repository(source_url):
    try:
        parsed = urlsplit(source_url or "")
        if (parsed.scheme != "https" or parsed.hostname != "github.com"
                or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or parsed.query or parsed.fragment):
            raise ValueError
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2:
            raise ValueError
        owner, repo = parts
        if repo.endswith(".git"):
            repo = repo[:-4]
        if not _OWNER_OR_REPO.fullmatch(owner) or not _OWNER_OR_REPO.fullmatch(repo):
            raise ValueError
        return owner, repo
    except (ValueError, TypeError):
        raise CollectionError(
            "Enter a public GitHub repository URL such as https://github.com/owner/repository.",
            code="COLLECTION_INVALID_URL",
        )


class GitHubIssuesCollector(BaseCollector):
    collector_type = "github_issues_api"

    @classmethod
    def capabilities(cls):
        return {
            "collectorType": cls.collector_type,
            "available": True,
            "unavailableReason": None,
            "supportsPreview": True,
            "supportsPagination": True,
            "requiresCredentials": False,
        }

    def _api_url(self, source):
        owner, repo = _repository(source.url)
        url = f"{API_BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/issues"
        validate_url_ssrf(url)
        return url, owner, repo

    def validate_source(self, source):
        self._api_url(source)

    def _headers(self):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": self.limits.user_agent,
        }
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _fetch_page(self, api_url, page):
        params = {"state": "all", "sort": "created", "direction": "desc",
                  "per_page": MAX_PAGE_SIZE, "page": page}
        for attempt in range(self.limits.max_retries + 1):
            try:
                with ssrf_safe_connections():
                    response = requests.get(
                        api_url, params=params, headers=self._headers(),
                        timeout=self.limits.timeout_seconds, allow_redirects=False,
                        stream=True,
                    )
            except requests.Timeout:
                if attempt < self.limits.max_retries:
                    time.sleep(min(2 ** attempt, 5))
                    continue
                raise CollectionError("GitHub API request timed out.", code="COLLECTION_TIMEOUT")
            except requests.RequestException:
                if attempt < self.limits.max_retries:
                    time.sleep(min(2 ** attempt, 5))
                    continue
                raise CollectionError("Could not reach the GitHub API.", code="COLLECTION_HTTP_ERROR")

            if response.status_code == 429 or (
                response.status_code == 403
                and (response.headers.get("X-RateLimit-Remaining") == "0"
                     or response.headers.get("Retry-After"))
            ):
                response.close()
                raise CollectionError(
                    "GitHub API rate limit reached. Try again after the provider resets the limit.",
                    code="COLLECTION_RATE_LIMITED",
                )
            if response.status_code in {500, 502, 503, 504} and attempt < self.limits.max_retries:
                response.close()
                time.sleep(min(2 ** attempt, 5))
                continue
            if response.status_code == 403:
                response.close()
                raise CollectionError(
                    "GitHub denied access to this repository through its public API.",
                    code="COLLECTION_NOT_PERMITTED",
                )
            if response.status_code == 404:
                response.close()
                raise CollectionError(
                    "The repository is not available through GitHub's public API.",
                    code="COLLECTION_UNSUPPORTED_SOURCE",
                )
            if response.status_code in {301, 302, 303, 307, 308}:
                response.close()
                raise CollectionError(
                    "GitHub redirected this repository API request; redirects are not followed.",
                    code="COLLECTION_HTTP_ERROR",
                )
            if response.status_code >= 400:
                status = response.status_code
                response.close()
                if status in {500, 502, 503, 504}:
                    raise CollectionError("GitHub API is temporarily unavailable.", code="COLLECTION_HTTP_ERROR")
                raise CollectionError(f"GitHub API returned HTTP {status}.", code="COLLECTION_HTTP_ERROR")

            content_length = response.headers.get("Content-Length")
            maximum = int(self.limits.max_response_mb * 1024 * 1024)
            try:
                if content_length and int(content_length) > maximum:
                    response.close()
                    raise CollectionError("The GitHub API response was too large.", code="COLLECTION_RESPONSE_TOO_LARGE")
                chunks, size = [], 0
                for chunk in response.iter_content(8192):
                    size += len(chunk)
                    if size > maximum:
                        response.close()
                        raise CollectionError("The GitHub API response was too large.", code="COLLECTION_RESPONSE_TOO_LARGE")
                    chunks.append(chunk)
                response.close()
                payload = json.loads(b"".join(chunks).decode(response.encoding or "utf-8"))
            except CollectionError:
                raise
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                response.close()
                raise CollectionError("GitHub returned malformed issue data.", code="COLLECTION_PARSE_ERROR")
            if not isinstance(payload, list):
                raise CollectionError("GitHub returned an unexpected issue response.", code="COLLECTION_PARSE_ERROR")
            return payload, response.status_code
        raise CollectionError("GitHub API request failed.", code="COLLECTION_HTTP_ERROR")

    def _normalize_issue(self, issue, owner, repo):
        if not isinstance(issue, dict) or "pull_request" in issue:
            return None
        issue_id = issue.get("id")
        number = issue.get("number")
        title = issue.get("title")
        if issue_id is None or not isinstance(number, int) or not isinstance(title, str):
            return None
        title = title[:500]
        body = issue.get("body") if isinstance(issue.get("body"), str) else ""
        body = body[:MAX_ISSUE_TEXT_CHARS]
        text = f"{title}\n\n{body}" if body else title
        labels = [
            label["name"][:100]
            for label in (issue.get("labels") or [])[:20]
            if isinstance(label, dict) and isinstance(label.get("name"), str)
        ]
        return normalized_record(
            external_review_id=str(issue_id),
            review_text=text,
            reviewer_name=None,
            rating=None,
            review_date=issue.get("created_at"),
            review_url=f"https://github.com/{owner}/{repo}/issues/{number}",
            language=None,
            source_metadata={
                "provider": "GitHub REST API",
                "repository": f"{owner}/{repo}",
                "issueNumber": number,
                "state": issue.get("state") if issue.get("state") in {"open", "closed"} else None,
                "labels": labels,
                "bodyTruncated": len(issue.get("body") or "") > MAX_ISSUE_TEXT_CHARS
                if isinstance(issue.get("body"), str) else False,
            },
        )

    def _collect(self, source, options=None):
        self.validate_source(source)
        options = options or {}
        api_url, owner, repo = self._api_url(source)
        max_pages = min(max(int(options.get("maxPages") or self.limits.max_pages), 1), self.limits.max_pages)
        max_records = min(max(int(options.get("maxRecords") or self.limits.max_records), 1), self.limits.max_records)
        result = CollectorResult(adapter=self.collector_type, normalized_url=source.url)
        for page in range(1, max_pages + 1):
            payload, status = self._fetch_page(api_url, page)
            result.pages_fetched += 1
            result.http_status = status
            result.fetch_status = "success"
            result.candidate_items_found += sum(1 for issue in payload if isinstance(issue, dict) and "pull_request" not in issue)
            for issue in payload:
                record = self._normalize_issue(issue, owner, repo)
                if record is None:
                    continue
                result.items_parsed += 1
                result.records.append(record)
                if len(result.records) >= max_records:
                    result.truncated = True
                    break
            if result.truncated or len(payload) < MAX_PAGE_SIZE:
                break
            if page < max_pages:
                time.sleep(self.limits.request_delay_seconds)
        result.items_after_filter = len(result.records)
        if not result.records:
            result.result_code = "COLLECTION_NO_REVIEWS_FOUND"
            result.result_message = "The public repository API returned no issue records."
        else:
            result.result_code = "COLLECTION_SUCCESS"
            result.result_message = f"{len(result.records)} public GitHub issue records were collected."
        return result

    def health_check(self, source):
        try:
            api_url, _, _ = self._api_url(source)
            self._fetch_page(api_url, 1)
            return {"available": True, "message": "GitHub repository API is accessible."}
        except CollectionError as exc:
            return {"available": False, "message": exc.message}

    def preview(self, source, options=None):
        result = self._collect(source, {**(options or {}), "maxRecords": 5, "maxPages": 1})
        return {
            "sourceType": source.type,
            "collectorType": self.collector_type,
            "detectedRecordCountEstimate": len(result.records),
            "candidateItemsFound": result.candidate_items_found,
            "fetchStatus": result.fetch_status,
            "httpStatus": result.http_status,
            "sampleRecords": result.records[:3],
            "detectedFields": ["review_text", "review_date", "review_url"],
            "warnings": ["GitHub issues do not provide a customer rating."] if result.records else [result.result_message],
        }

    def collect(self, source, options=None):
        result = self._collect(source, options)
        result.warnings.append("GitHub issues are community reports, not a representative customer-review sample.")
        return result

    def normalize_record(self, raw):
        return raw
