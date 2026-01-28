"""Utilities to sort and score open PR-related issues for relevance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class Issue:
    """Simple issue model used for relevance analysis."""

    id: int
    title: str
    body: str = ""
    labels: Optional[List[str]] = None
    author: Optional[str] = None

    def label_set(self) -> set[str]:
        return set(self.labels or [])


def score_issue(issue: Issue, keywords: Iterable[str]) -> int:
    """Compute a relevance score for an issue given target keywords."""

    haystack = f"{issue.title}\n{issue.body}".lower()
    weight_title = 3
    weight_body = 1
    score = 0

    for keyword in keywords:
        kw = keyword.lower().strip()
        if not kw:
            continue
        if kw in issue.title.lower():
            score += weight_title
        if kw in issue.body.lower():
            score += weight_body
    return score


def analyze_pr_issues(issues: Iterable[Issue], keywords: Iterable[str]) -> List[Issue]:
    """Return issues sorted by descending relevance score."""

    keyword_list = [kw for kw in keywords if kw.strip()]
    scored = [
        (score_issue(issue, keyword_list), issue)
        for issue in issues
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [issue for _, issue in scored]

